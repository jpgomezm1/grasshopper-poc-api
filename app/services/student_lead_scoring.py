"""Student lead scoring · Bloque A · Sprint super_admin fixes 2026-05-03.

Scoring deterministic (no LLM call) que evalúa cada estudiante de un colegio
como **lead potencial** para el equipo Grasshopper · combina señales de
engagement + perfil + intención. Output: 0..100 + banda + 1 línea de
narrativa.

NO inventa narrativa con IA en este sprint · la rationale se compone con
plantillas determinísticas a partir de los hitos cumplidos. La memoria del
proyecto pide reusar fallback templates cuando IA no aporte (D-005). Si
después se quiere un toque IA, se cambia `_rationale()` por una llamada al
ai-specialist usando el mismo input.

Pesos (suma 100):
    journey_progress       30
    tests_completed        20
    consolidated_profile   15
    english_test           10
    budget_band defined    10
    preferred_countries    10
    contact_request_open   5

Banda:
    score >= 70 → 'hot'
    score >= 40 → 'warm'
    else        → 'cold'
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List
from uuid import UUID

from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func

from app.db.models import (
    ConsolidatedProfileCache,
    Session as JourneySession,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.school import StudentLeadScore


# Maximum journey steps · used to derive a 0..1 progress ratio. The journey
# uses 12 onboarding steps + 3 phases · we treat completed_steps length as
# proxy and saturate at 12.
_JOURNEY_TARGET_STEPS = 12


def _journey_progress_ratio(session: JourneySession | None) -> float:
    if session is None:
        return 0.0
    completed = session.completed_steps or []
    if isinstance(completed, list):
        n = len(completed)
    else:
        n = 0
    if session.is_completed:
        return 1.0
    return min(1.0, n / float(_JOURNEY_TARGET_STEPS))


def _band(score: int) -> str:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def _rationale(
    *,
    score: int,
    journey_progress: float,
    tests_completed: int,
    has_profile: bool,
    cefr: str | None,
    budget_band: str | None,
    preferred_countries: List[str],
    has_open_contact_request: bool,
) -> str:
    """1-2 line narrative · plantilla determinística (D-005)."""
    bits: List[str] = []
    if journey_progress >= 0.95:
        bits.append("Journey completo")
    elif journey_progress >= 0.5:
        bits.append(f"Journey al {int(journey_progress * 100)}%")
    if tests_completed >= 3:
        bits.append(f"{tests_completed} tests aplicados")
    elif tests_completed >= 1:
        bits.append(f"{tests_completed} test(s)")
    if has_profile:
        bits.append("perfil consolidado")
    if cefr and cefr.upper() not in ("A1", "A2"):
        bits.append(f"inglés {cefr}")
    if budget_band:
        bits.append(f"presupuesto {budget_band}")
    if preferred_countries:
        if len(preferred_countries) == 1:
            bits.append(f"interés {preferred_countries[0]}")
        else:
            bits.append(
                f"interés {preferred_countries[0]} +{len(preferred_countries) - 1}"
            )
    if has_open_contact_request:
        bits.append("solicitó contacto")

    if not bits:
        return "Aún sin señales suficientes para evaluar."
    head = "Lead caliente · " if score >= 70 else "Lead tibio · " if score >= 40 else "Aún frío · "
    return head + " · ".join(bits)


def _score_one(
    *,
    user: User,
    session: JourneySession | None,
    tests_completed: int,
    has_profile: bool,
    has_open_contact_request: bool,
) -> StudentLeadScore:
    journey_progress = _journey_progress_ratio(session)
    score_f = 0.0

    # journey progress · 30 pts
    score_f += 30.0 * journey_progress

    # tests · 20 pts (saturado a 4)
    score_f += 20.0 * min(1.0, tests_completed / 4.0)

    # consolidated profile · 15 pts
    if has_profile:
        score_f += 15.0

    # english · 10 pts si CEFR conocido y >= B1
    cefr = (user.english_cefr_level or "").upper()
    if cefr and cefr in ("B1", "B2", "C1", "C2"):
        score_f += 10.0

    # budget band defined · 10 pts (señal de seriedad)
    if user.budget_band:
        score_f += 10.0

    # preferred countries · 10 pts
    countries = list(user.preferred_countries or [])
    if countries:
        score_f += 10.0

    # open contact request · 5 pts
    if has_open_contact_request:
        score_f += 5.0

    score = int(round(min(100.0, score_f)))

    return StudentLeadScore(
        user_id=user.id,
        email=user.email,
        name=user.name,
        onboarding_status=user.onboarding_status.value
        if user.onboarding_status
        else "not_started",
        journey_progress=round(journey_progress, 3),
        tests_completed=tests_completed,
        has_consolidated_profile=has_profile,
        english_cefr_level=user.english_cefr_level,
        budget_band=user.budget_band,
        preferred_countries=countries,
        score=score,
        score_band=_band(score),
        rationale=_rationale(
            score=score,
            journey_progress=journey_progress,
            tests_completed=tests_completed,
            has_profile=has_profile,
            cefr=user.english_cefr_level,
            budget_band=user.budget_band,
            preferred_countries=countries,
            has_open_contact_request=has_open_contact_request,
        ),
    )


def score_students_for_school(
    db: DBSession,
    school_id: UUID,
    *,
    limit: int | None = None,
) -> List[StudentLeadScore]:
    """Score all active student users belonging to a school.

    Returns a list ordered by score desc. The query is bounded · 1 query for
    users + 1 aggregate per signal (small N, B2B portfolios). For the current
    seeds this is well under 50 rows / school.
    """
    students: List[User] = (
        db.query(User)
        .filter(
            User.school_id == school_id,
            User.role == UserRole.STUDENT,
            User.is_active.is_(True),
        )
        .order_by(User.created_at.desc())
        .all()
    )
    if not students:
        return []

    user_ids = [u.id for u in students]

    # Tests completed · 1 query group-by user_id
    test_counts = dict(
        db.query(VocationalTestResult.user_id, func.count(VocationalTestResult.id))
        .filter(VocationalTestResult.user_id.in_(user_ids))
        .group_by(VocationalTestResult.user_id)
        .all()
    )

    # Consolidated profiles · 1 query
    profile_users = set(
        r[0]
        for r in db.query(ConsolidatedProfileCache.user_id)
        .filter(
            ConsolidatedProfileCache.user_id.in_(user_ids),
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .all()
    )

    # Sessions per user · take latest one for journey progress
    sessions_by_user: dict[UUID, JourneySession] = {}
    sessions = (
        db.query(JourneySession)
        .filter(JourneySession.user_id.in_(user_ids))
        .order_by(JourneySession.updated_at.desc())
        .all()
    )
    for s in sessions:
        if s.user_id not in sessions_by_user:
            sessions_by_user[s.user_id] = s

    rows: List[StudentLeadScore] = []
    for user in students:
        row = _score_one(
            user=user,
            session=sessions_by_user.get(user.id),
            tests_completed=int(test_counts.get(user.id, 0)),
            has_profile=user.id in profile_users,
            has_open_contact_request=(
                user.gh_contact_status in ("pending", "in_progress")
                if user.gh_contact_status
                else False
            ),
        )
        rows.append(row)

    rows.sort(key=lambda r: r.score, reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return rows


def summarize_bands(rows: Iterable[StudentLeadScore]) -> dict:
    """Convenience for the breakdown response."""
    hot = sum(1 for r in rows if r.score_band == "hot")
    warm = sum(1 for r in rows if r.score_band == "warm")
    cold = sum(1 for r in rows if r.score_band == "cold")
    return {"hot": hot, "warm": warm, "cold": cold}


def _ensure_user_has_contact_status_columns() -> None:
    """No-op · documents that columns 'gh_contact_status' & friends are added
    by migration 013 (`013_add_gh_team_roles`). Kept for grep-ability when
    debugging schema mismatch errors during cold-start of the service.
    """
    return None


# ---------------------------------------------------------------------------
# School usage metrics · used by SchoolDetailPage tab Métricas
# ---------------------------------------------------------------------------


def compute_school_usage_metrics(db: DBSession, school_id: UUID) -> dict:
    """Returns a dict suitable for the SchoolUsageMetrics schema."""
    from datetime import timedelta
    from app.db.models import Report

    now = datetime.utcnow()
    cutoff_30d = now - timedelta(days=30)

    students_total = (
        db.query(func.count(User.id))
        .filter(
            User.school_id == school_id,
            User.role == UserRole.STUDENT,
            User.is_active.is_(True),
        )
        .scalar()
        or 0
    )

    students_completed = (
        db.query(func.count(User.id))
        .filter(
            User.school_id == school_id,
            User.role == UserRole.STUDENT,
            User.onboarding_status == "completed",
        )
        .scalar()
        or 0
    )

    students_with_profile = (
        db.query(func.count(ConsolidatedProfileCache.id.distinct()))
        .join(User, User.id == ConsolidatedProfileCache.user_id)
        .filter(
            User.school_id == school_id,
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .scalar()
        or 0
    )

    tests_30d = (
        db.query(func.count(VocationalTestResult.id))
        .join(User, User.id == VocationalTestResult.user_id)
        .filter(
            User.school_id == school_id,
            VocationalTestResult.created_at >= cutoff_30d,
        )
        .scalar()
        or 0
    )

    reports_30d = 0
    last_activity = None
    try:
        reports_30d = (
            db.query(func.count(Report.id))
            .filter(
                Report.school_id_at_render == school_id,
                Report.created_at >= cutoff_30d,
            )
            .scalar()
            or 0
        )
    except Exception:  # noqa: BLE001 · table may not exist in older envs
        reports_30d = 0

    # Active in last 30d → users with session updated_at >= cutoff
    active_30d = (
        db.query(func.count(User.id.distinct()))
        .join(JourneySession, JourneySession.user_id == User.id)
        .filter(
            User.school_id == school_id,
            JourneySession.updated_at >= cutoff_30d,
        )
        .scalar()
        or 0
    )

    last_activity_row = (
        db.query(func.max(JourneySession.updated_at))
        .join(User, User.id == JourneySession.user_id)
        .filter(User.school_id == school_id)
        .scalar()
    )
    if last_activity_row:
        last_activity = last_activity_row

    activity_rate = 0.0
    if students_total > 0:
        activity_rate = round(100.0 * active_30d / students_total, 1)

    # Health score · simple composite · adjustable
    health = 0
    if students_total > 0:
        health += int(40 * min(1.0, active_30d / max(1, students_total)))
        health += int(30 * min(1.0, students_completed / max(1, students_total)))
        health += int(30 * min(1.0, students_with_profile / max(1, students_total)))
    health = max(0, min(100, health))

    return {
        "students_total": int(students_total),
        "students_active_30d": int(active_30d),
        "students_completed_journey": int(students_completed),
        "students_with_profile": int(students_with_profile),
        "tests_completed_30d": int(tests_30d),
        "reports_generated_30d": int(reports_30d),
        "activity_rate_pct": activity_rate,
        "health_score": health,
        "last_activity_at": last_activity,
    }
