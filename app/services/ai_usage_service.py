"""Tiny helper to record AI calls into `ai_usage_log` (Bloque J).

Usage: at the end of every AI service call (anthropic / openai / whisper),
`record_ai_usage(...)`. Best-effort · failures are swallowed so they never
break the user-facing flow.

Cost tables are conservative defaults; tune as needed.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession


logger = logging.getLogger(__name__)


# Cost per 1k tokens (USD) · approximate at 2026-05-05.
_COSTS_PER_1K = {
    # Anthropic
    "claude-3-haiku-20240307": (0.00025, 0.00125),
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-opus-20240229": (0.015, 0.075),
    # Fase C (B-049) · modelo anterior del proyecto (aún puede venir por env)
    "claude-sonnet-4-5": (0.003, 0.015),
    # Fase C2 (2026-06-12) · modelo actual (settings.ai_model) · mismo precio
    # que 4-5: $3/$15 por millón de tokens.
    "claude-sonnet-4-6": (0.003, 0.015),
    # OpenAI
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.005, 0.015),
    "whisper-1": (0.006, 0.0),  # per-minute · stored as (rate, 0)
}


def estimate_cost_usd(model: str, tokens_input: Optional[int], tokens_output: Optional[int]) -> Optional[float]:
    rates = _COSTS_PER_1K.get(model)
    if not rates:
        return None
    rate_in, rate_out = rates
    cost = 0.0
    if tokens_input:
        cost += (tokens_input / 1000.0) * rate_in
    if tokens_output:
        cost += (tokens_output / 1000.0) * rate_out
    return round(cost, 6)


def record_ai_usage(
    db: DBSession,
    *,
    provider: str,
    model: str,
    feature: str,
    tokens_input: Optional[int] = None,
    tokens_output: Optional[int] = None,
    latency_ms: Optional[int] = None,
    user_id: Optional[UUID] = None,
    cost_usd: Optional[float] = None,
) -> None:
    """Best-effort write · never raises."""
    try:
        from app.db.models import AIUsageLog
        if cost_usd is None:
            cost_usd = estimate_cost_usd(model, tokens_input, tokens_output)
        row = AIUsageLog(
            provider=provider,
            model=model,
            feature=feature,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            user_id=user_id,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        logger.warning("record_ai_usage failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
