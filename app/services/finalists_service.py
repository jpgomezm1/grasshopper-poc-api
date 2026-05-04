"""Finalists comparator service · GH-ADVISOR-CLINICAL Bloque G.

Side-by-side comparison of 2-3 finalist programs an advisor selected from the
student's top 5 recommendations. Pulls program metadata + a short
psychographic fit string and accepts manual pros/cons from the advisor.

Stateless · no persistence (caller renders inline · prints if needed).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    ConsolidatedProfileCache,
    Program,
    User,
)
from app.schemas.clinical import (
    FinalistComparisonItem,
    FinalistsResponse,
)

logger = logging.getLogger(__name__)


def _short_psychographic_fit(profile: Dict[str, Any], program: Optional[Program]) -> Optional[str]:
    interests = profile.get("interests") or []
    work_style = profile.get("work_style")
    if not program:
        return None
    if interests:
        return (
            f"Encaja con áreas de interés ({', '.join(interests[:2])}) · "
            f"trabajo {work_style.lower() if work_style else 'compatible'}."
        )
    return f"Programa en {program.country or 'destino internacional'} · revisar match en sesión."


def build_finalists(
    db: DBSession,
    student: User,
    program_ids: List[str],
    advisor_pros_cons: Dict[str, Dict[str, str]],
) -> FinalistsResponse:
    if not program_ids:
        return FinalistsResponse(student_user_id=student.id, items=[])

    cache = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == student.id)
        .first()
    )
    profile_dict: Dict[str, Any] = {}
    try:
        if cache and cache.profile_data:
            profile_dict = dict(cache.profile_data)
    except Exception:
        profile_dict = {}

    programs = (
        db.query(Program).filter(Program.program_id.in_(program_ids)).all()
    )
    programs_by_id = {p.program_id: p for p in programs}

    items: List[FinalistComparisonItem] = []
    for pid in program_ids:
        p = programs_by_id.get(pid)
        if not p:
            # Skip silently · UI handles missing
            continue
        pros_cons = advisor_pros_cons.get(pid) or {}
        items.append(
            FinalistComparisonItem(
                program_id=p.program_id,
                program_slug=p.slug,
                program_name=p.name,
                institution=p.institution,
                country=p.country,
                city=p.city,
                duration_months=p.duration_months,
                cost_total=p.cost_total,
                currency=p.currency,
                budget_tier=p.budget_tier,
                language_requirement=p.language_requirement,
                psychographic_fit_short=_short_psychographic_fit(profile_dict, p),
                employability=p.employability if isinstance(p.employability, dict) else None,
                ranking=p.ranking if isinstance(p.ranking, dict) else None,
                advisor_pros=pros_cons.get("pros"),
                advisor_cons=pros_cons.get("cons"),
            )
        )
    return FinalistsResponse(student_user_id=student.id, items=items)
