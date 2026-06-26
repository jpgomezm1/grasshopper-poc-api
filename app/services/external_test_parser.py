"""External test parser · IA pipeline.

GH-S5-BE-04 · Sprint 5.

Flow:
    upload bytes + test_type
        -> document_parser.extract_text_from_upload  (pdfplumber for PDFs)
        -> if no text layer: vision path (image bytes sent to Claude vision)
        -> prompt template per test_type (parse_<type>.txt)
        -> Claude completion · expects strict JSON
        -> validation against ParserResult / Parsed* Pydantic schemas
        -> ParserResult or raise ParseError

PII guard:
    - We deliberately DO NOT log `document_text` or `student_name`.
    - `ai_client.call_claude` already truncates `input_size` log to char count.
    - Errors include test_type and confidence but NEVER the raw text.

Confidence threshold for `parsing_status`:
    confidence >= 0.7 → done
    0.4 <= confidence < 0.7 → needs_review
    confidence < 0.4 → failed (treat as no usable output)
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from app.core.ai_client import get_client, load_prompt
from app.config import get_settings
from app.schemas.external_tests import (
    ParsedBig5,
    ParsedIStrong,
    ParsedMBTI,
    ParsedRIASEC,
    ParserResult,
    TestType,
)
from app.services.document_parser import (
    DocumentParseError,
    extract_text_from_upload,
    is_image,
)

logger = logging.getLogger(__name__)


PARSER_VERSION = "v1"
CONFIDENCE_DONE = 0.7
CONFIDENCE_REVIEW = 0.4

# Map test_type → (prompt filename, parsed payload schema)
_PROMPT_MAP: dict[TestType, tuple[str, type]] = {
    "mbti": ("parse_mbti", ParsedMBTI),
    "istrong": ("parse_istrong", ParsedIStrong),
    "big5": ("parse_big5", ParsedBig5),
    "riasec": ("parse_riasec", ParsedRIASEC),
}


class ParseError(RuntimeError):
    """Parser pipeline failure (extractor, AI, or schema validation)."""


@dataclass
class ParseOutcome:
    """Internal struct returned to the route layer."""

    result: Optional[ParserResult]
    raw_text: str
    parsing_status: str  # "done" | "needs_review" | "failed"
    error_message: Optional[str]
    # Metadata de la llamada IA (M-001) · None si no hubo llamada (extracción
    # falló, PDF sin texto) o si la llamada falló antes de devolver tokens.
    usage: Optional[dict] = None


# -----------------------------------------------------------------------------
# JSON extraction helper · Claude sometimes wraps the JSON in ```json fences
# even when asked not to. Be defensive.
# -----------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Find the JSON object inside Claude's response."""
    text = text.strip()

    # 1) Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) Stripped of fences
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3) Greedy: first { ... last }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = text[first : last + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ParseError(f"Claude response is not valid JSON: {exc}")

    raise ParseError("Claude response contains no JSON object")


# -----------------------------------------------------------------------------
# Vision path · used when the PDF has no text layer or the upload is an image
# -----------------------------------------------------------------------------

def _call_claude_messages(messages: list) -> tuple[str, dict]:
    """Llama a Claude (texto o visión) y devuelve ``(texto, metadata)``.

    La metadata alimenta el tracking M-001 (``model``/``tokens_input``/
    ``tokens_output``/``latency_ms``). Robustez Fase C2: timeout explícito +
    reintentos (antes el SDK pelado esperaba hasta 10 min sin reintentos) y el
    texto sale del primer bloque con ``.text`` (no ``content[0]``, que puede no
    ser texto).
    """
    settings = get_settings()
    client = get_client().with_options(timeout=120.0, max_retries=2)
    start = time.time()
    response = client.messages.create(
        model=settings.ai_model,
        max_tokens=settings.ai_max_tokens or 1500,
        temperature=0,  # determinista para parsing
        messages=messages,
    )
    meta: dict = {
        "model": settings.ai_model,
        "latency_ms": int((time.time() - start) * 1000),
    }
    usage = getattr(response, "usage", None)
    meta["tokens_input"] = getattr(usage, "input_tokens", None)
    meta["tokens_output"] = getattr(usage, "output_tokens", None)

    text: Optional[str] = None
    for block in getattr(response, "content", []) or []:
        t = getattr(block, "text", None)
        if t is not None:
            text = t
            break
    if text is None:
        raise ParseError("Claude response has no text block")
    return text, meta


def _call_claude_vision(
    prompt_text: str, image_bytes: bytes, image_mime: str
) -> tuple[str, dict]:
    """Call Claude with an image attachment.

    Uses the configured ai_model (Sonnet recommended for vision · falls back
    to whatever is set; per D-008 we reuse the POC model).
    """
    import base64
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    return _call_claude_messages([
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_mime,
                        "data": b64,
                    },
                },
                {"type": "text", "text": prompt_text},
            ],
        }
    ])


def _call_claude_text(prompt_text: str) -> tuple[str, dict]:
    """Call Claude with plain text only · cheaper path."""
    return _call_claude_messages([{"role": "user", "content": prompt_text}])


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------

def parse_external_test(
    *,
    test_type: TestType,
    file_bytes: bytes,
    content_type: Optional[str],
    filename: Optional[str],
) -> ParseOutcome:
    """Parse an uploaded external test result.

    This function is fully synchronous · the route layer wraps it in a
    BackgroundTask so the HTTP response returns immediately.
    """
    if test_type not in _PROMPT_MAP:
        raise ParseError(f"unknown test_type: {test_type!r}")

    prompt_name, payload_schema = _PROMPT_MAP[test_type]

    # 1) Try cheap text extraction first
    try:
        raw_text, meta = extract_text_from_upload(file_bytes, content_type, filename)
    except DocumentParseError as exc:
        return ParseOutcome(
            result=None,
            raw_text="",
            parsing_status="failed",
            error_message=f"document extraction failed: {exc}",
        )

    use_vision = not raw_text or meta.get("has_text_layer") is False

    # 2) Build the prompt
    template = load_prompt(prompt_name)
    prompt_text = template.replace(
        "{document_text}",
        raw_text or "(no extractable text · use the attached image)",
    )

    # 3) Call Claude
    usage_meta: Optional[dict] = None
    try:
        if use_vision and is_image(content_type, filename):
            raw_response, usage_meta = _call_claude_vision(
                prompt_text, file_bytes, content_type or "image/png"
            )
        elif use_vision:
            # PDF without text layer · we'd ideally render to image and send.
            # In Sprint 5 we keep it simple: re-attempt as text with the empty
            # body. If the PDF really has no text and is also not an image we
            # treat as failed.
            if not raw_text:
                return ParseOutcome(
                    result=None,
                    raw_text="",
                    parsing_status="failed",
                    error_message=(
                        "PDF has no text layer and image rendering is not "
                        "available in S5 dev · upload as image (PNG/JPG) instead"
                    ),
                )
            raw_response, usage_meta = _call_claude_text(prompt_text)
        else:
            raw_response, usage_meta = _call_claude_text(prompt_text)
    except Exception as exc:  # pragma: no cover - network errors
        logger.warning("claude call failed test_type=%s err=%s", test_type, exc)
        return ParseOutcome(
            result=None,
            raw_text=raw_text,
            parsing_status="failed",
            error_message=f"AI call failed: {exc}",
        )

    # 4) Extract + validate JSON
    try:
        data = _extract_json(raw_response)
    except ParseError as exc:
        return ParseOutcome(
            result=None,
            raw_text=raw_text,
            parsing_status="failed",
            error_message=str(exc),
            usage=usage_meta,
        )

    # Force test_type & parser_version (defensive · don't trust Claude on these)
    data["test_type"] = test_type
    data["parser_version"] = PARSER_VERSION

    try:
        result = ParserResult.model_validate(data)
    except ValidationError as exc:
        # Validation errors are extremely informative for prompt iteration.
        # We log a short tag, NOT the raw_text.
        logger.warning("parser validation failed test_type=%s n_errors=%d", test_type, len(exc.errors()))
        return ParseOutcome(
            result=None,
            raw_text=raw_text,
            parsing_status="needs_review",
            error_message=f"schema validation failed: {exc.errors()[:3]!r}",
            usage=usage_meta,
        )

    # 5) Bucket by confidence
    if result.confidence >= CONFIDENCE_DONE:
        status = "done"
    elif result.confidence >= CONFIDENCE_REVIEW:
        status = "needs_review"
    else:
        status = "failed"

    logger.info(
        "external test parsed test_type=%s status=%s confidence=%.2f",
        test_type,
        status,
        result.confidence,
    )

    return ParseOutcome(
        result=result,
        raw_text=raw_text,
        parsing_status=status,
        error_message=None,
        usage=usage_meta,
    )
