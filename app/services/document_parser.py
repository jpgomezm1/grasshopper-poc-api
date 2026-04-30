"""Document parser · extract text from PDFs / images.

GH-S5-BE-02 · Sprint 5.

Pipeline:
    bytes (file content) -> text (str)

Strategies:
    1. PDF + pdfplumber → fast text extraction (~50ms / page)
    2. PDF without text layer (scanned) → fall through to Claude vision-based path
    3. Image (jpg/png/heic) → forwarded to vision path in external_test_parser

NOTE: this module deliberately does NOT call Claude. Vision is handled in
`external_test_parser.py` so the prompt can include both image AND structured
output instructions in a single call. Here we only do "cheap" text extraction.

Dependencies:
    pdfplumber (vendored as part of S5 setup) · falls back gracefully if absent
    so the storage_service stub flow doesn't break in dev.
"""
from __future__ import annotations

import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


SUPPORTED_PDF = {"application/pdf", "application/x-pdf"}
SUPPORTED_IMAGE = {"image/jpeg", "image/jpg", "image/png", "image/heic", "image/heif"}


class DocumentParseError(RuntimeError):
    """Raised when a document is malformed or extraction fails."""


def is_pdf(content_type: Optional[str], filename: Optional[str]) -> bool:
    if content_type and content_type.lower() in SUPPORTED_PDF:
        return True
    if filename and filename.lower().endswith(".pdf"):
        return True
    return False


def is_image(content_type: Optional[str], filename: Optional[str]) -> bool:
    if content_type and content_type.lower() in SUPPORTED_IMAGE:
        return True
    if filename:
        lower = filename.lower()
        return lower.endswith((".jpg", ".jpeg", ".png", ".heic", ".heif"))
    return False


def extract_pdf_text(file_bytes: bytes) -> Tuple[str, dict]:
    """Extract text from a PDF using pdfplumber.

    Returns:
        (text, metadata) · metadata has page_count, has_text_layer (bool),
        and char_count.

    Raises:
        DocumentParseError if the PDF is malformed.
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        # In dev without pdfplumber installed we fall back to a "no text" path.
        # Vision will pick this up later. Log it so the deploy install is caught.
        logger.warning(
            "pdfplumber not installed · returning empty text · "
            "vision fallback will run · add pdfplumber to requirements.txt for prod"
        )
        return "", {"page_count": 0, "has_text_layer": False, "char_count": 0, "extractor": "noop"}

    pages: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                pages.append(txt)
            page_count = len(pdf.pages)
    except Exception as exc:
        raise DocumentParseError(f"pdfplumber failed: {exc}") from exc

    full_text = "\n\n".join(pages).strip()
    return full_text, {
        "page_count": page_count,
        "has_text_layer": bool(full_text),
        "char_count": len(full_text),
        "extractor": "pdfplumber",
    }


def extract_text_from_upload(
    file_bytes: bytes,
    content_type: Optional[str],
    filename: Optional[str],
) -> Tuple[str, dict]:
    """Top-level dispatcher.

    Returns ("", metadata) if the upload is an image · caller should send the
    image bytes to Claude vision in `external_test_parser`.
    """
    if is_pdf(content_type, filename):
        return extract_pdf_text(file_bytes)

    if is_image(content_type, filename):
        return "", {
            "page_count": 1,
            "has_text_layer": False,
            "char_count": 0,
            "extractor": "image-passthrough",
        }

    raise DocumentParseError(
        f"unsupported content_type={content_type!r} filename={filename!r}"
    )
