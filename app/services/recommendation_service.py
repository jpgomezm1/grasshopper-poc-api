"""Recommender filtrado por catálogo Grasshopper · Sprint 6.

Pipeline:
    1. Toma ConsolidatedProfile del usuario (de consolidation_service)
    2. Filtra catálogo por presupuesto + país preferido (BE-05)
       · evita que IA tenga el catálogo entero como contexto
       · acota alucinación
    3. Renderiza prompt con catálogo filtrado + perfil
    4. Llama Claude Sonnet 4.5 (low temp)
    5. Valida output contra catálogo · descarta IDs inventados (BE-04)
    6. Persiste en consolidated_profiles.recommendations_data (cache · BE-06)

GH-S6-BE-04/05/06 · added 2026-04-30.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.core.ai_client import get_client, load_prompt
from app.data.ofertas import get_all_ofertas
from app.db.models import ConsolidatedProfileCache, User
from app.schemas.consolidated_profile import (
    ConsolidatedProfile,
    RecommendedProgram,
)
from app.services.consolidation_service import (
    ConsolidationFailure,
    generate_or_get_profile,
)

logger = logging.getLogger(__name__)
settings = get_settings()


PROMPT_VERSION = "recommend_v1"

# Hard cap of programs we send to the model · keeps prompt size sane.
CATALOG_CAP_FOR_PROMPT = 25


# ---------------------------------------------------------------------------
# Pre-IA filter (BE-05)
# ---------------------------------------------------------------------------


_BUDGET_TIER_ORDER = {"bajo": 0, "medio": 1, "alto": 2}


def _oferta_max_cost_usd(oferta: Dict[str, Any]) -> Optional[int]:
    """Best-effort numeric cost in USD (or None if not parseable)."""
    cost = oferta.get("cost") or {}
    if cost.get("currency") not in (None, "USD"):
        # Catalog mostly USD; if other currency, skip numeric comparison
        return None
    val = cost.get("max")
    if isinstance(val, (int, float)):
        return int(val)
    return None


def _budget_match_kind(
    oferta: Dict[str, Any],
    budget_band: Optional[str],
    budget_max_usd: Optional[int],
) -> str:
    """Return 'under' | 'match' | 'stretch'."""
    if budget_max_usd is not None:
        cost = _oferta_max_cost_usd(oferta)
        if cost is None:
            return "match"
        if cost <= int(budget_max_usd * 0.7):
            return "under"
        if cost <= budget_max_usd:
            return "match"
        if cost <= int(budget_max_usd * 1.3):
            return "stretch"
        return "stretch"

    # Fallback to qualitative tier
    if not budget_band:
        return "match"
    user_tier = _BUDGET_TIER_ORDER.get(budget_band, 1)
    program_tier = _BUDGET_TIER_ORDER.get(oferta.get("budgetTier", "medio"), 1)
    delta = program_tier - user_tier
    if delta < 0:
        return "under"
    if delta == 0:
        return "match"
    return "stretch"


def filter_catalog(
    user: User,
    profile: ConsolidatedProfile,
    cap: int = CATALOG_CAP_FOR_PROMPT,
) -> List[Dict[str, Any]]:
    """Filter the catalog before passing to AI.

    Filters applied:
      - Budget: includes 'under' + 'match'; allows 'stretch' only if
        score by interest match is high (we keep them but tag them).
      - Preferred countries: prefers (not exclude) those countries.
      - Drops programs that clearly fail language requirement vs CEFR.

    Output is sorted by a heuristic relevance score so that if we cap
    the list, we keep the most likely matches.
    """
    all_ofertas = get_all_ofertas()

    budget_band = user.budget_band
    budget_max_usd = user.budget_max_usd
    preferred_countries = set(user.preferred_countries or [])
    cefr = (user.english_cefr_level or "").upper().strip()

    interests_lower = {i.lower() for i in (profile.interests or [])}
    paths_lower = {p.lower() for p in (profile.suggested_career_paths or [])}
    riasec_codes = {h.code for h in (profile.holland_codes or [])}

    # Heuristic CEFR ordering (rough)
    cefr_rank = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
    user_lang_rank = cefr_rank.get(cefr, 0)

    lang_req_to_min_rank = {
        "ninguno": 0,
        "basico": 2,
        "intermedio": 3,
        "avanzado": 5,
    }

    filtered: List[Tuple[float, Dict[str, Any], str]] = []

    for o in all_ofertas:
        # Language hard-filter (only if user has a CEFR level on file)
        if user_lang_rank > 0:
            req = (
                (o.get("eligibility") or {}).get("languageRequirement", "ninguno")
            )
            min_rank = lang_req_to_min_rank.get(req, 0)
            if user_lang_rank < min_rank:
                continue

        # Budget
        kind = _budget_match_kind(o, budget_band, budget_max_usd)
        if kind == "stretch":
            # keep but downweight; keep only if there's strong interest match
            pass

        # Heuristic score
        score = 0.0
        if kind == "under":
            score += 0.5
        elif kind == "match":
            score += 1.0
        elif kind == "stretch":
            score += 0.1

        # Country preference
        countries = set(o.get("countries") or [])
        if preferred_countries and (preferred_countries & countries):
            score += 1.0

        # Tag/interest match (rough)
        tags = set(t.lower() for t in (o.get("tags") or []))
        name_lower = (o.get("name") or "").lower()
        short_lower = (o.get("shortDescription") or "").lower()
        category = (o.get("category") or "").lower()

        for token in interests_lower | paths_lower:
            if not token:
                continue
            small = token.split()[0]  # crude · match first word
            if small in name_lower or small in short_lower or small in tags or small in category:
                score += 0.4

        # Loose RIASEC mapping (crude)
        if "I" in riasec_codes and category in {"academic", "study_abroad"}:
            score += 0.2
        if "R" in riasec_codes and category in {"work_travel", "internships"}:
            score += 0.2
        if "S" in riasec_codes and category in {"volunteer", "language"}:
            score += 0.2
        if "A" in riasec_codes and category in {"language", "study_abroad"}:
            score += 0.1
        if "E" in riasec_codes and category in {"internships", "work_travel"}:
            score += 0.2

        filtered.append((score, o, kind))

    # Drop budget=stretch with very low score · keep prompt focused
    filtered = [(s, o, k) for (s, o, k) in filtered if not (k == "stretch" and s < 0.6)]

    # If after filtering we have nothing, fall back to top-by-budget tier
    if not filtered:
        for o in all_ofertas[:cap]:
            kind = _budget_match_kind(o, budget_band, budget_max_usd)
            filtered.append((0.5, o, kind))

    # Sort desc by heuristic score, then cap
    filtered.sort(key=lambda triple: triple[0], reverse=True)
    capped = filtered[:cap]

    # Inject the budget_fit hint so prompt can keep it
    out = []
    for _, o, kind in capped:
        slim = {
            "program_id": o["id"],
            "program_slug": o.get("slug"),
            "program_name": o["name"],
            "category": o.get("category"),
            "countries": o.get("countries", []),
            "duration": o.get("duration"),
            "budget_tier": o.get("budgetTier"),
            "cost": o.get("cost"),
            "tags": o.get("tags", []),
            "language_requirement": (o.get("eligibility") or {}).get(
                "languageRequirement"
            ),
            "short_description": o.get("shortDescription"),
            "_budget_fit_hint": kind,
        }
        out.append(slim)
    return out


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def _format_profile_block(profile: ConsolidatedProfile) -> str:
    holland = ", ".join(
        f"{h.code} ({h.label}) {h.score}" for h in (profile.holland_codes or [])
    ) or "—"
    dims = "; ".join(
        f"{d.name}: {d.level}" for d in (profile.personality_dimensions or [])
    ) or "—"
    return (
        f"- Resumen: {profile.summary_narrative}\n"
        f"- Fortalezas: {', '.join(profile.strengths)}\n"
        f"- Intereses: {', '.join(profile.interests)}\n"
        f"- Valores: {', '.join(profile.values) or '—'}\n"
        f"- Estilo de aprendizaje: {profile.learning_style or '—'}\n"
        f"- Estilo de trabajo: {profile.work_style or '—'}\n"
        f"- Holland top: {holland}\n"
        f"- Personalidad: {dims}\n"
        f"- Caminos sugeridos: {', '.join(profile.suggested_career_paths) or '—'}\n"
        f"- Constraints: {', '.join(profile.constraints) or '—'}"
    )


def _format_constraints_block(user: User) -> str:
    rows = []
    if user.budget_band:
        rows.append(f"- Presupuesto cualitativo: {user.budget_band}")
    if user.budget_max_usd:
        rows.append(f"- Presupuesto techo: USD {user.budget_max_usd}")
    if user.preferred_countries:
        rows.append(
            f"- Países preferidos: {', '.join(user.preferred_countries)}"
        )
    if user.english_cefr_level:
        rows.append(f"- Inglés CEFR: {user.english_cefr_level}")
    return "\n".join(rows) if rows else "(sin constraints adicionales)"


def _format_catalog_block(catalog: List[Dict[str, Any]]) -> str:
    parts = []
    for c in catalog:
        cost = c.get("cost") or {}
        cost_str = (
            f"{cost.get('min')}-{cost.get('max')} {cost.get('currency','USD')}"
            if cost
            else "n/a"
        )
        dur = c.get("duration") or {}
        dur_str = (
            f"{dur.get('min')}-{dur.get('max')} {dur.get('type','')}"
            if dur
            else "n/a"
        )
        parts.append(
            f"- id={c['program_id']} · {c['program_name']} · "
            f"categoría={c.get('category','-')} · "
            f"países={', '.join(c.get('countries') or [])} · "
            f"duración={dur_str} · costo={cost_str} · "
            f"budget_tier={c.get('budget_tier','-')} · "
            f"idioma_req={c.get('language_requirement','-')} · "
            f"budget_fit_hint={c.get('_budget_fit_hint','-')} · "
            f"tags={','.join(c.get('tags') or [])}"
        )
    return "\n".join(parts)


def render_recommend_prompt(
    profile: ConsolidatedProfile,
    user: User,
    catalog: List[Dict[str, Any]],
    limit: int,
) -> str:
    template = load_prompt("recommend_programs")
    return template.format(
        limit=limit,
        profile_block=_format_profile_block(profile),
        constraints_block=_format_constraints_block(user),
        catalog_block=_format_catalog_block(catalog),
    )


# ---------------------------------------------------------------------------
# AI call
# ---------------------------------------------------------------------------


def _call_claude_for_recommendations(
    prompt: str,
    user_id: str,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> Tuple[Optional[str], Dict[str, Any]]:
    client = get_client()
    start = time.time()
    metadata: Dict[str, Any] = {
        "model": settings.ai_model,
        "prompt_version": PROMPT_VERSION,
    }
    try:
        response = client.messages.create(
            model=settings.ai_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else None
        metadata["latency_ms"] = int((time.time() - start) * 1000)
        if hasattr(response, "usage") and response.usage is not None:
            metadata["tokens_input"] = getattr(response.usage, "input_tokens", None)
            metadata["tokens_output"] = getattr(response.usage, "output_tokens", None)
        logger.info(
            "Recommend AI call OK",
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
            "Recommend AI call failed",
            extra={"user_id": user_id, "error": str(e)},
        )
        metadata["error"] = str(e)
        return None, metadata


# ---------------------------------------------------------------------------
# Output validation against catalog (BE-04)
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def validate_against_catalog(
    raw_recs: List[Dict[str, Any]],
    catalog: List[Dict[str, Any]],
) -> Tuple[List[RecommendedProgram], List[str]]:
    """Drop any recommendation whose program_id is not in the filtered catalog.

    Returns (valid_list, dropped_ids).
    """
    by_id = {c["program_id"]: c for c in catalog}
    valid: List[RecommendedProgram] = []
    dropped: List[str] = []

    for r in raw_recs:
        pid = r.get("program_id")
        if pid not in by_id:
            dropped.append(str(pid))
            continue
        cat = by_id[pid]
        # Hydrate fields the model may have missed
        merged = {
            **r,
            "program_id": pid,
            "program_slug": r.get("program_slug") or cat.get("program_slug"),
            "program_name": r.get("program_name") or cat["program_name"],
            "countries": r.get("countries") or cat.get("countries", []),
            "budget_tier": r.get("budget_tier") or cat.get("budget_tier"),
        }
        if not merged.get("budget_fit"):
            merged["budget_fit"] = cat.get("_budget_fit_hint", "match")
        try:
            valid.append(RecommendedProgram(**merged))
        except Exception as e:
            logger.warning(
                "Recommendation discarded · failed schema validation",
                extra={"program_id": pid, "error": str(e)},
            )
            dropped.append(str(pid))

    return valid, dropped


def parse_recommendations(raw: str) -> List[Dict[str, Any]]:
    cleaned = _strip_code_fences(raw)
    data = json.loads(cleaned)
    recs = data.get("recommendations") or []
    if not isinstance(recs, list):
        raise ValueError("recommendations is not a list")
    return recs


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


class RecommendationFailure(RuntimeError):
    """Raised when the recommender pipeline cannot produce valid output."""


def generate_recommendations(
    db: DBSession,
    user: User,
    limit: int = 5,
    force_refresh: bool = False,
) -> Tuple[ConsolidatedProfile, List[RecommendedProgram], ConsolidatedProfileCache, bool]:
    """End-to-end · returns (profile, recommendations, cache_row, cached_flag).

    cached_flag is True when both profile AND recommendations came from cache.
    """
    # 1) Profile (own cache)
    try:
        profile, cache_row, profile_cached = generate_or_get_profile(
            db, user, force_refresh=force_refresh
        )
    except ConsolidationFailure:
        raise

    # 2) If profile was cached AND we already have recommendations stored,
    #    AND not forcing refresh, reuse them.
    if (
        profile_cached
        and not force_refresh
        and cache_row.recommendations_data
        and isinstance(cache_row.recommendations_data, list)
        and len(cache_row.recommendations_data) > 0
    ):
        try:
            recs = [RecommendedProgram(**r) for r in cache_row.recommendations_data]
            logger.info(
                "Recommendation cache HIT",
                extra={"user_id": str(user.id), "count": len(recs)},
            )
            return profile, recs[:limit], cache_row, True
        except Exception as e:
            logger.warning(
                "Cached recommendations corrupted · regenerating",
                extra={"user_id": str(user.id), "error": str(e)},
            )

    # 3) Filter catalog
    catalog = filter_catalog(user, profile)
    if not catalog:
        raise RecommendationFailure(
            "No hay programas en el catálogo que cumplan tus filtros básicos."
        )

    # 4) Render + call
    prompt = render_recommend_prompt(profile, user, catalog, limit=limit)
    raw, metadata = _call_claude_for_recommendations(prompt, str(user.id))

    if raw is None:
        raise RecommendationFailure(
            "El motor de recomendación no respondió · reintenta en breve."
        )

    # 5) Parse + validate
    try:
        raw_recs = parse_recommendations(raw)
    except Exception as e:
        logger.error(
            "Failed to parse recommendations JSON",
            extra={"user_id": str(user.id), "error": str(e), "raw_preview": (raw or "")[:300]},
        )
        raise RecommendationFailure(
            "Recomendaciones no disponibles · reintenta en breve."
        ) from e

    valid_recs, dropped_ids = validate_against_catalog(raw_recs, catalog)
    if dropped_ids:
        logger.warning(
            "Discarded hallucinated program_ids",
            extra={"user_id": str(user.id), "dropped": dropped_ids[:10], "count": len(dropped_ids)},
        )

    # Sort by score desc + cap
    valid_recs.sort(key=lambda r: r.match_score, reverse=True)
    valid_recs = valid_recs[:limit]

    if not valid_recs:
        raise RecommendationFailure(
            "El recomendador devolvió 0 programas válidos · reintenta en breve."
        )

    # 6) Persist
    cache_row.recommendations_data = [r.model_dump(mode="json") for r in valid_recs]
    cache_row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cache_row)

    return profile, valid_recs, cache_row, False
