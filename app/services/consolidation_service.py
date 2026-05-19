"""AI Analysis Engine cruzado · Sprint 6.

Construye el `ConsolidatedProfile` a partir de TODOS los resultados de tests
psicométricos del estudiante (internos + externos parseados en S5) cruzados
con sus answers del journey y datos demográficos.

Coordina:
  - input gathering (DB → canonical dict)
  - hashing (cache key)
  - prompt rendering (consolidate_profile.txt)
  - claude call (low temp · sonnet 4.5)
  - validation (Pydantic ConsolidatedProfile)
  - persistence en `consolidated_profiles` (cache)

GH-S6-BE-03/04/06 · added 2026-04-30.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.core.ai_client import call_claude, get_client, load_prompt
from app.db.models import (
    ConsolidatedProfileCache,
    Session,
    User,
    VocationalTestResult,
)
from app.schemas.consolidated_profile import ConsolidatedProfile

logger = logging.getLogger(__name__)
settings = get_settings()


# Cache TTL · 24h (BE-06)
CACHE_TTL = timedelta(hours=24)

PROMPT_VERSION = "consolidate_v1"


# ---------------------------------------------------------------------------
# Input gathering
# ---------------------------------------------------------------------------


def _latest_session_answers(db: DBSession, user_id: UUID) -> Dict[str, Any]:
    """Return the most-recent journey session answers (or empty dict)."""
    sess = (
        db.query(Session)
        .filter(Session.user_id == user_id)
        .order_by(Session.updated_at.desc())
        .first()
    )
    return (sess.answers if sess and sess.answers else {}) or {}


def gather_user_inputs(db: DBSession, user: User) -> Dict[str, Any]:
    """Collect all inputs that feed the consolidate prompt.

    Result is canonical (sorted keys, deterministic) so we can hash it.
    """
    voc_results: List[VocationalTestResult] = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        .order_by(VocationalTestResult.test_id.asc())
        .all()
    )

    tests_block: List[Dict[str, Any]] = []
    for vr in voc_results:
        tests_block.append(
            {
                "test_id": vr.test_id,
                "source": vr.source or "internal",
                "scores": vr.scores or {},
                "completed_at": vr.created_at.isoformat() if vr.created_at else None,
            }
        )

    journey_answers = _latest_session_answers(db, user.id)

    demographic = {
        "name": user.name,
        "english_cefr_level": user.english_cefr_level,
        "english_test_completed": bool(user.english_test_completed),
        "school_id": str(user.school_id) if user.school_id else None,
        "budget_band": user.budget_band,
        "budget_max_usd": user.budget_max_usd,
        "preferred_countries": list(user.preferred_countries or []),
        "life_stage": journey_answers.get("lifeStage"),
        "time_horizon": journey_answers.get("timeHorizon"),
        "clarity_level": journey_answers.get("clarityLevel"),
        "geo_preference": journey_answers.get("geoPreference"),
    }

    return {
        "user_id": str(user.id),
        "demographic": demographic,
        "tests": tests_block,
        "journey_answers": journey_answers,
    }


def hash_inputs(inputs: Dict[str, Any]) -> str:
    """Deterministic SHA-256 of the input dict, ignoring user_id (per-user table)."""
    payload = {k: v for k, v in inputs.items() if k != "user_id"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def _format_demographic_block(d: Dict[str, Any]) -> str:
    rows = []
    if d.get("life_stage"):
        rows.append(f"- Etapa: {d['life_stage']}")
    if d.get("time_horizon"):
        rows.append(f"- Horizonte temporal: {d['time_horizon']}")
    if d.get("clarity_level"):
        rows.append(f"- Nivel de claridad: {d['clarity_level']}")
    if d.get("english_cefr_level"):
        rows.append(f"- Nivel de inglés (CEFR): {d['english_cefr_level']}")
    if d.get("budget_band"):
        rows.append(f"- Presupuesto cualitativo: {d['budget_band']}")
    if d.get("budget_max_usd"):
        rows.append(f"- Presupuesto techo: USD {d['budget_max_usd']}")
    if d.get("preferred_countries"):
        rows.append(
            f"- Países preferidos: {', '.join(d['preferred_countries'])}"
        )
    if d.get("geo_preference"):
        rows.append(f"- Preferencia geográfica (journey): {d['geo_preference']}")
    return "\n".join(rows) if rows else "- (Sin datos demográficos adicionales)"


def _format_tests_block(tests: List[Dict[str, Any]]) -> str:
    if not tests:
        return "(El estudiante aún no tiene tests registrados.)"
    parts = []
    for t in tests:
        scores_compact = json.dumps(t["scores"], ensure_ascii=False, sort_keys=True)
        parts.append(
            f"### {t['test_id']} · source={t['source']}\n"
            f"scores: {scores_compact}"
        )
    return "\n\n".join(parts)


def _format_journey_block(answers: Dict[str, Any]) -> str:
    if not answers:
        return "(Sin journey de onboarding completado)"
    rows = []
    for key in sorted(answers.keys()):
        val = answers[key]
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val) or "—"
        rows.append(f"- {key}: {val}")
    return "\n".join(rows)


def render_consolidate_prompt(inputs: Dict[str, Any]) -> str:
    template = load_prompt("consolidate_profile")
    return template.format(
        demographic_block=_format_demographic_block(inputs["demographic"]),
        tests_block=_format_tests_block(inputs["tests"]),
        journey_answers_block=_format_journey_block(inputs["journey_answers"]),
    )


# ---------------------------------------------------------------------------
# AI call · Claude Sonnet 4.5
# ---------------------------------------------------------------------------


def _call_claude_for_consolidation(
    prompt: str,
    user_id: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Direct call (bypassing the journey-tuned `call_claude`) so we can
    control max_tokens + temperature for this specific task.

    Returns (text, metadata).
    """
    client = get_client()
    start = time.time()
    metadata: Dict[str, Any] = {"model": settings.ai_model, "prompt_version": PROMPT_VERSION}

    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else None
        metadata["latency_ms"] = int((time.time() - start) * 1000)
        # Anthropic SDK: response.usage.input_tokens / output_tokens
        if hasattr(response, "usage") and response.usage is not None:
            metadata["tokens_input"] = getattr(response.usage, "input_tokens", None)
            metadata["tokens_output"] = getattr(response.usage, "output_tokens", None)
        logger.info(
            "Consolidation AI call OK",
            extra={
                "user_id": user_id,
                "latency_ms": metadata.get("latency_ms"),
                "input_size": len(prompt),
                "output_size": len(text or ""),
            },
        )
        return text, metadata
    except Exception as e:
        logger.error(
            "Consolidation AI call failed",
            extra={"user_id": user_id, "error": str(e)},
        )
        metadata["error"] = str(e)
        return None, metadata


# ---------------------------------------------------------------------------
# JSON cleanup helpers
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the model added them."""
    t = (text or "").strip()
    if t.startswith("```"):
        # remove leading ```... and trailing ```
        lines = t.split("\n")
        # drop first line (``` or ```json)
        lines = lines[1:]
        # drop trailing ``` if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def parse_consolidated_profile(raw: str) -> ConsolidatedProfile:
    cleaned = _strip_code_fences(raw)
    data = json.loads(cleaned)
    return ConsolidatedProfile(**data)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _is_cache_valid(row: ConsolidatedProfileCache, expected_hash: str) -> bool:
    if row is None:
        return False
    if row.invalidated_at is not None:
        return False
    if row.profile_hash != expected_hash:
        return False
    if row.generated_at is None:
        return False
    return datetime.utcnow() - row.generated_at < CACHE_TTL


def get_cached_profile(
    db: DBSession, user_id: UUID
) -> Optional[ConsolidatedProfileCache]:
    return (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == user_id)
        .first()
    )


def invalidate_cache(db: DBSession, user_id: UUID) -> None:
    """Mark the cache row invalidated (used when a new test arrives)."""
    row = get_cached_profile(db, user_id)
    if row is not None:
        row.invalidated_at = datetime.utcnow()
        db.commit()


# ---------------------------------------------------------------------------
# Public entrypoint · generate or reuse
# ---------------------------------------------------------------------------


class ConsolidationFailure(RuntimeError):
    """Raised when AI fails to produce a valid ConsolidatedProfile."""


class NoTestsAvailable(ConsolidationFailure):
    """Raised when the student has not completed any psychometric test yet.

    This is NOT a service failure — it's an expected "empty state" and callers
    should translate it to a 200 OK response with an empty bundle (see
    /recommendations/me · B-010 QA round 2).
    """


def generate_or_get_profile(
    db: DBSession,
    user: User,
    force_refresh: bool = False,
) -> Tuple[ConsolidatedProfile, ConsolidatedProfileCache, bool]:
    """Main API. Returns (profile, cache_row, cached_flag).

    cached_flag is True when we reused an existing valid cache row.
    """
    inputs = gather_user_inputs(db, user)
    expected_hash = hash_inputs(inputs)

    cache_row = get_cached_profile(db, user.id)

    if (
        not force_refresh
        and cache_row is not None
        and _is_cache_valid(cache_row, expected_hash)
    ):
        logger.info(
            "Consolidation cache HIT",
            extra={"user_id": str(user.id), "hash": expected_hash[:12]},
        )
        try:
            cached_profile = ConsolidatedProfile(**cache_row.profile_data)
            return cached_profile, cache_row, True
        except Exception as e:
            logger.warning(
                "Cache row corrupted · regenerating",
                extra={"user_id": str(user.id), "error": str(e)},
            )

    # MISS → call AI
    if not inputs["tests"]:
        raise NoTestsAvailable(
            "El estudiante todavía no tiene tests psicométricos registrados."
        )

    prompt = render_consolidate_prompt(inputs)
    raw, metadata = _call_claude_for_consolidation(prompt, str(user.id))

    if raw is None:
        raise ConsolidationFailure(
            "El motor de análisis IA no respondió · reintenta en breve."
        )

    try:
        profile = parse_consolidated_profile(raw)
    except Exception as e:
        logger.error(
            "Failed to parse ConsolidatedProfile from AI output",
            extra={"user_id": str(user.id), "error": str(e), "raw_preview": (raw or "")[:300]},
        )
        raise ConsolidationFailure(
            "Análisis no disponible · reintenta en breve."
        ) from e

    # Stamp metadata on the validated profile
    profile.model_used = metadata.get("model")
    profile.prompt_version = PROMPT_VERSION
    profile.generated_at = datetime.utcnow()

    # Persist (UPSERT-like)
    if cache_row is None:
        cache_row = ConsolidatedProfileCache(
            user_id=user.id,
            profile_hash=expected_hash,
            profile_data=profile.model_dump(mode="json"),
            recommendations_data=[],
            model_used=metadata.get("model"),
            prompt_version=PROMPT_VERSION,
            tokens_input=metadata.get("tokens_input"),
            tokens_output=metadata.get("tokens_output"),
            latency_ms=metadata.get("latency_ms"),
            generated_at=datetime.utcnow(),
            invalidated_at=None,
        )
        db.add(cache_row)
    else:
        cache_row.profile_hash = expected_hash
        cache_row.profile_data = profile.model_dump(mode="json")
        cache_row.recommendations_data = []  # reset · will be filled by recommender
        cache_row.model_used = metadata.get("model")
        cache_row.prompt_version = PROMPT_VERSION
        cache_row.tokens_input = metadata.get("tokens_input")
        cache_row.tokens_output = metadata.get("tokens_output")
        cache_row.latency_ms = metadata.get("latency_ms")
        cache_row.generated_at = datetime.utcnow()
        cache_row.invalidated_at = None

    db.commit()
    db.refresh(cache_row)

    return profile, cache_row, False
