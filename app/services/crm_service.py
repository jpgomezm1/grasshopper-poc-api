"""CRM enriched service · GH-CRM-001 · Sprint CRM enriquecido 2026-05-03.

Composes the read-side of the CRM module:

    - `list_leads`            · paginated + filterable lead list
    - `compute_kpis`          · aggregated KPIs (cacheable 5 min)
    - `get_lead_detail`       · full snapshot for the detail page
    - `update_pipeline_status` · status PATCH + audit + bitrix sync log mock
    - `regenerate_ai_analysis` · invokes the AI prompt with caching

Privacy model (D-025 + Habeas Data):
    - Journal entries → only metadata (count + types · last_at).
      Content is NEVER returned by any function in this module.
    - Hop chat sessions → only count + last timestamp.
    - The AI prompt receives demographics + scoring + program candidates.
      It does NOT receive raw journal content nor chat transcripts.

Lead origin rules (mirror the schema docstring):
    - "grasshopper": school_id IS NULL OR (school_id NOT NULL AND
                     gh_contact_status = 'converted')
    - "school_radar": school_id NOT NULL AND
                      gh_contact_status IN (NULL, 'pending', 'in_progress')
                      AND score >= 60 (hard threshold to respect ownership).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude, load_prompt
from app.core.ai_json import AIJsonError, parse_ai_json
from app.config import get_settings
from app.db.models import (
    AuditLog,
    BitrixSyncLog,
    BitrixSyncStatus,
    ConsolidatedProfileCache,
    JournalEntry,
    Program,
    School,
    Session as JourneySession,
    SessionEvent,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.crm import (
    CrmActivityEntry,
    CrmActivityLog,
    CrmAiAnalysis,
    CrmConsolidatedProfileLite,
    CrmDemographics,
    CrmHopSessionMeta,
    CrmJournalMeta,
    CrmJourneySnapshot,
    CrmKpisResponse,
    CrmLeadDetailResponse,
    CrmLeadListItem,
    CrmLeadListResponse,
    CrmNextAction,
    CrmProgramMatch,
    CrmScoreBreakdown,
    CrmTestSnapshot,
    LeadOrigin,
    ScoreBreakdownSignal,
)
from app.services.student_lead_scoring import _band as score_band  # reuse banding
from app.services.student_lead_scoring import _journey_progress_ratio


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hard threshold to expose a "school_radar" lead in the CRM. Below this we
# respect ownership of the colegio and hide the row even from gh_commercial.
SCHOOL_RADAR_MIN_SCORE = 60

# AI cache TTL · 7 days
AI_CACHE_TTL = timedelta(days=7)

# Score weights · MUST mirror student_lead_scoring._score_one
_SIGNAL_WEIGHTS = [
    ("journey_progress", "Avance del journey", 30),
    ("tests_completed", "Tests psicométricos", 20),
    ("consolidated_profile", "Perfil consolidado", 15),
    ("english_cefr", "Nivel de inglés", 10),
    ("budget_band", "Presupuesto definido", 10),
    ("preferred_countries", "Países preferidos", 10),
    ("contact_request", "Solicitud de contacto", 5),
]


# ---------------------------------------------------------------------------
# Helpers · scoring per single user (lighter than scoring_service for one row)
# ---------------------------------------------------------------------------


def _compute_signals(
    *,
    user: User,
    session: Optional[JourneySession],
    tests_completed: int,
    has_profile: bool,
    has_open_contact_request: bool,
) -> Tuple[int, List[ScoreBreakdownSignal]]:
    """Re-run the scoring logic but emit the per-signal contributions.

    The scoring service exposes only the final score · here we duplicate
    the math because the FE breakdown tab needs each signal's contribution
    (and a 1-line evidence string).
    """
    signals: List[ScoreBreakdownSignal] = []
    score_f = 0.0

    # journey progress · 30 pts
    journey_progress = _journey_progress_ratio(session)
    contrib = round(30.0 * journey_progress, 2)
    score_f += contrib
    signals.append(
        ScoreBreakdownSignal(
            key="journey_progress",
            label="Avance del journey",
            weight=30,
            contributed=contrib,
            evidence=(
                f"Journey al {int(journey_progress * 100)}%"
                if journey_progress < 0.95
                else "Journey completado"
            ),
        )
    )

    # tests · 20 pts (saturado a 4)
    tests_ratio = min(1.0, tests_completed / 4.0)
    contrib = round(20.0 * tests_ratio, 2)
    score_f += contrib
    signals.append(
        ScoreBreakdownSignal(
            key="tests_completed",
            label="Tests psicométricos",
            weight=20,
            contributed=contrib,
            evidence=(
                f"{tests_completed} test(s) completados"
                if tests_completed > 0
                else "Sin tests aún"
            ),
        )
    )

    # consolidated profile · 15 pts
    contrib = 15.0 if has_profile else 0.0
    score_f += contrib
    signals.append(
        ScoreBreakdownSignal(
            key="consolidated_profile",
            label="Perfil consolidado",
            weight=15,
            contributed=contrib,
            evidence=(
                "Perfil consolidado generado"
                if has_profile
                else "Aún no genera perfil consolidado"
            ),
        )
    )

    # english CEFR · 10 pts si >= B1
    cefr = (user.english_cefr_level or "").upper()
    cefr_qualifies = cefr in ("B1", "B2", "C1", "C2")
    contrib = 10.0 if cefr_qualifies else 0.0
    score_f += contrib
    signals.append(
        ScoreBreakdownSignal(
            key="english_cefr",
            label="Nivel de inglés",
            weight=10,
            contributed=contrib,
            evidence=(
                f"Inglés {cefr}"
                if cefr
                else "Inglés sin medir"
            ),
        )
    )

    # budget band · 10 pts si está definido
    contrib = 10.0 if user.budget_band else 0.0
    score_f += contrib
    signals.append(
        ScoreBreakdownSignal(
            key="budget_band",
            label="Presupuesto definido",
            weight=10,
            contributed=contrib,
            evidence=(
                f"Presupuesto {user.budget_band}"
                if user.budget_band
                else "Presupuesto sin declarar"
            ),
        )
    )

    # preferred countries · 10 pts
    countries: List[str] = list(user.preferred_countries or [])
    contrib = 10.0 if countries else 0.0
    score_f += contrib
    signals.append(
        ScoreBreakdownSignal(
            key="preferred_countries",
            label="Países preferidos",
            weight=10,
            contributed=contrib,
            evidence=(
                f"Interés en {', '.join(countries[:3])}"
                if countries
                else "Sin países declarados"
            ),
        )
    )

    # open contact request · 5 pts
    contrib = 5.0 if has_open_contact_request else 0.0
    score_f += contrib
    signals.append(
        ScoreBreakdownSignal(
            key="contact_request",
            label="Solicitud de contacto",
            weight=5,
            contributed=contrib,
            evidence=(
                "Solicitó contacto"
                if has_open_contact_request
                else "Sin solicitud abierta"
            ),
        )
    )

    score = int(round(min(100.0, score_f)))
    return score, signals


def _classify_origin(user: User) -> LeadOrigin:
    """Origin = 'grasshopper' (own lead) | 'school_radar' (potential)."""
    if user.school_id is None:
        return "grasshopper"
    # Student of a school
    if (user.gh_contact_status or "") == "converted":
        return "grasshopper"
    return "school_radar"


def _derive_age(birthdate: Optional[date]) -> Optional[int]:
    if birthdate is None:
        return None
    today = date.today()
    years = today.year - birthdate.year
    if (today.month, today.day) < (birthdate.month, birthdate.day):
        years -= 1
    return max(0, years)


# ---------------------------------------------------------------------------
# Filtering & list
# ---------------------------------------------------------------------------


def _apply_origin_filter(query, origin: Optional[str]):
    """Encode the origin rules at the SQL level (best-effort · final origin
    is computed in Python because of the score threshold)."""
    if origin == "grasshopper":
        return query.filter(
            or_(
                User.school_id.is_(None),
                and_(
                    User.school_id.isnot(None),
                    User.gh_contact_status == "converted",
                ),
            )
        )
    if origin == "school_radar":
        return query.filter(
            User.school_id.isnot(None),
            or_(
                User.gh_contact_status.is_(None),
                User.gh_contact_status.in_(("pending", "in_progress")),
            ),
        )
    # 'all' or None → no SQL filter (final filter happens in Python after scoring)
    return query


def _candidate_users_query(
    db: DBSession,
    *,
    origin: Optional[str] = None,
    pipeline_status: Optional[str] = None,
    school_id: Optional[UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
):
    q = db.query(User).filter(
        User.role == UserRole.STUDENT,
        User.is_active.is_(True),
    )
    q = _apply_origin_filter(q, origin)
    if pipeline_status:
        q = q.filter(User.lead_pipeline_status == pipeline_status)
    if school_id is not None:
        q = q.filter(User.school_id == school_id)
    if date_from is not None:
        q = q.filter(User.created_at >= date_from)
    if date_to is not None:
        q = q.filter(User.created_at <= date_to)
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(
            or_(
                func.lower(User.email).like(like),
                func.lower(func.coalesce(User.name, "")).like(like),
            )
        )
    return q


def _bulk_score_users(
    db: DBSession, users: List[User]
) -> Dict[UUID, Tuple[int, List[ScoreBreakdownSignal], int, bool, bool, Optional[datetime]]]:
    """Returns user_id -> (score, signals, tests_completed, has_profile,
    has_open_contact_request, last_activity_at). Two grouped queries · O(N) memory.
    """
    if not users:
        return {}
    user_ids = [u.id for u in users]

    test_counts = dict(
        db.query(VocationalTestResult.user_id, func.count(VocationalTestResult.id))
        .filter(VocationalTestResult.user_id.in_(user_ids))
        .group_by(VocationalTestResult.user_id)
        .all()
    )

    profile_users = set(
        r[0]
        for r in db.query(ConsolidatedProfileCache.user_id)
        .filter(
            ConsolidatedProfileCache.user_id.in_(user_ids),
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .all()
    )

    sessions_by_user: Dict[UUID, JourneySession] = {}
    for s in (
        db.query(JourneySession)
        .filter(JourneySession.user_id.in_(user_ids))
        .order_by(JourneySession.updated_at.desc())
        .all()
    ):
        if s.user_id not in sessions_by_user:
            sessions_by_user[s.user_id] = s

    last_activity_by_user = {
        uid: s.updated_at for uid, s in sessions_by_user.items()
    }

    out: Dict[UUID, Tuple[int, List[ScoreBreakdownSignal], int, bool, bool, Optional[datetime]]] = {}
    for u in users:
        tests_n = int(test_counts.get(u.id, 0))
        has_profile = u.id in profile_users
        has_contact = (u.gh_contact_status or "") in ("pending", "in_progress")
        score, signals = _compute_signals(
            user=u,
            session=sessions_by_user.get(u.id),
            tests_completed=tests_n,
            has_profile=has_profile,
            has_open_contact_request=has_contact,
        )
        out[u.id] = (
            score,
            signals,
            tests_n,
            has_profile,
            has_contact,
            last_activity_by_user.get(u.id),
        )
    return out


def list_leads(
    db: DBSession,
    *,
    origin: Optional[str] = None,
    pipeline_status: Optional[str] = None,
    score_band_filter: Optional[str] = None,
    score_min: Optional[int] = None,
    score_max: Optional[int] = None,
    school_id: Optional[UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "score_desc",
) -> CrmLeadListResponse:
    """Returns paginated · filtered list of CRM leads.

    NOTE: scoring is in-memory per page candidate set. To stay bounded we
    fetch up to `page * page_size * 4` user rows, score, filter by score,
    sort, and slice. With current seeds (~30 users) this is trivial; for
    production scale a denormalized score column with periodic refresh
    is the natural follow-up.
    """
    q = _candidate_users_query(
        db,
        origin=origin if origin in ("grasshopper", "school_radar") else None,
        pipeline_status=pipeline_status,
        school_id=school_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    # Heuristic: fetch a generous window to allow Python-side score filtering
    # before paginating. Cap to avoid runaway queries.
    fetch_cap = max(500, page * page_size * 4)
    candidates = q.order_by(User.created_at.desc()).limit(fetch_cap).all()

    scoring = _bulk_score_users(db, candidates)

    school_names: Dict[UUID, str] = {}
    school_ids = {u.school_id for u in candidates if u.school_id}
    if school_ids:
        for sid, sname in db.query(School.id, School.name).filter(School.id.in_(school_ids)).all():
            school_names[sid] = sname

    rows: List[CrmLeadListItem] = []
    for u in candidates:
        score, _signals, tests_n, has_profile, _has_contact, last_activity = scoring[u.id]
        origin_v = _classify_origin(u)
        # Hide school_radar rows below score threshold (respect ownership)
        if origin_v == "school_radar" and score < SCHOOL_RADAR_MIN_SCORE:
            continue
        # Score band filter
        band_v = score_band(score)
        if score_band_filter and band_v != score_band_filter:
            continue
        if score_min is not None and score < score_min:
            continue
        if score_max is not None and score > score_max:
            continue
        # Origin requested but doesn't match (defensive: SQL filter is broad)
        if origin in ("grasshopper", "school_radar") and origin != origin_v:
            continue

        rows.append(
            CrmLeadListItem(
                user_id=u.id,
                email=u.email,
                name=u.name,
                avatar_url=None,
                origin=origin_v,
                school_id=u.school_id,
                school_name=school_names.get(u.school_id) if u.school_id else None,
                score=score,
                score_band=band_v,
                pipeline_status=u.lead_pipeline_status,  # type: ignore[arg-type]
                pipeline_status_at=u.lead_pipeline_status_at,
                gh_contact_status=u.gh_contact_status,
                gh_contact_requested_at=u.gh_contact_requested_at,
                last_activity_at=last_activity,
                tests_completed=tests_n,
                has_consolidated_profile=has_profile,
                created_at=u.created_at,
            )
        )

    # Sort
    if sort == "score_asc":
        rows.sort(key=lambda r: (r.score, r.created_at))
    elif sort == "created_desc":
        rows.sort(key=lambda r: r.created_at, reverse=True)
    elif sort == "created_asc":
        rows.sort(key=lambda r: r.created_at)
    elif sort == "last_activity_desc":
        rows.sort(
            key=lambda r: r.last_activity_at or r.created_at, reverse=True
        )
    else:  # default · score_desc
        rows.sort(key=lambda r: (r.score, r.created_at), reverse=True)

    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = rows[start:end]
    total_pages = max(1, math.ceil(total / page_size)) if total else 0

    return CrmLeadListResponse(
        items=page_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


def compute_kpis(db: DBSession) -> CrmKpisResponse:
    # Reuse the same candidate set the list endpoint would consider so KPIs
    # match (no surprises). Cap at 5000 active students which is well above
    # the catalog scale.
    users = (
        db.query(User)
        .filter(User.role == UserRole.STUDENT, User.is_active.is_(True))
        .limit(5000)
        .all()
    )
    scoring = _bulk_score_users(db, users)

    total = 0
    hot = 0
    pending_action = 0
    converted_30d = 0
    by_origin: Dict[str, int] = {"grasshopper": 0, "school_radar": 0}
    by_band: Dict[str, int] = {"hot": 0, "warm": 0, "cold": 0}
    by_pipe: Dict[str, int] = {}

    cutoff_30d = datetime.utcnow() - timedelta(days=30)

    for u in users:
        s = scoring.get(u.id)
        if not s:
            continue
        score = s[0]
        origin_v = _classify_origin(u)
        if origin_v == "school_radar" and score < SCHOOL_RADAR_MIN_SCORE:
            continue
        total += 1
        band_v = score_band(score)
        if band_v == "hot":
            hot += 1
        by_band[band_v] = by_band.get(band_v, 0) + 1
        by_origin[origin_v] = by_origin.get(origin_v, 0) + 1
        ps = u.lead_pipeline_status
        if ps:
            by_pipe[ps] = by_pipe.get(ps, 0) + 1
        # pending action: status pending OR (no pipeline status + open contact request)
        if ps == "pending" or (
            ps is None and (u.gh_contact_status or "") in ("pending", "in_progress")
        ):
            pending_action += 1
        if (
            ps == "converted"
            and u.lead_pipeline_status_at is not None
            and u.lead_pipeline_status_at >= cutoff_30d
        ):
            converted_30d += 1

    return CrmKpisResponse(
        total_leads=total,
        hot_leads=hot,
        pending_action=pending_action,
        converted_last_30d=converted_30d,
        by_origin=by_origin,
        by_band=by_band,
        by_pipeline_status=by_pipe,
    )


# ---------------------------------------------------------------------------
# Detail · journey snapshot (privacy-respecting)
# ---------------------------------------------------------------------------


def _get_journey_snapshot(db: DBSession, user: User) -> CrmJourneySnapshot:
    # Latest session for journey progress
    sess = (
        db.query(JourneySession)
        .filter(JourneySession.user_id == user.id)
        .order_by(JourneySession.updated_at.desc())
        .first()
    )
    journey_progress = _journey_progress_ratio(sess)

    tests_q = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        .order_by(VocationalTestResult.created_at.desc())
        .limit(10)
        .all()
    )
    tests = [
        CrmTestSnapshot(
            test_id=t.test_id,
            completed_at=t.created_at,
            scores=dict(t.scores or {}),
            source=t.source or "internal",
        )
        for t in tests_q
    ]

    # Consolidated profile (lite · just the synthesis · NEVER raw answers
    # if they exceed 300 chars)
    profile = None
    cp = (
        db.query(ConsolidatedProfileCache)
        .filter(
            ConsolidatedProfileCache.user_id == user.id,
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .first()
    )
    if cp:
        pdata = cp.profile_data or {}
        # The exact shape of the profile_data is controlled by the
        # consolidation_service · we extract conservatively.
        summary = pdata.get("synthesis") or pdata.get("summary") or pdata.get("text")
        if isinstance(summary, str):
            summary = summary[:300]
        else:
            summary = None
        interests = pdata.get("interests") or pdata.get("areas_of_interest") or []
        values = pdata.get("values") or []
        if not isinstance(interests, list):
            interests = []
        if not isinstance(values, list):
            values = []
        profile = CrmConsolidatedProfileLite(
            generated_at=cp.generated_at,
            has_profile=True,
            summary=summary,
            interests=[str(x) for x in interests[:6]],
            values=[str(x) for x in values[:6]],
        )

    # Journal · METADATA ONLY (D-025)
    journal_meta = CrmJournalMeta(total_entries=0, entries_by_type={}, last_entry_at=None)
    # Sessions of this user · then their journal entries
    if sess is not None or db.query(JourneySession).filter(JourneySession.user_id == user.id).count() > 0:
        # Aggregate counts grouping by entry_type across all sessions of this user
        rows = (
            db.query(JournalEntry.entry_type, func.count(JournalEntry.id), func.max(JournalEntry.created_at))
            .join(JourneySession, JourneySession.id == JournalEntry.session_id)
            .filter(JourneySession.user_id == user.id)
            .group_by(JournalEntry.entry_type)
            .all()
        )
        total_entries = 0
        last_at: Optional[datetime] = None
        types: Dict[str, int] = {}
        for et, count, max_at in rows:
            et_str = et.value if hasattr(et, "value") else str(et)
            types[et_str] = int(count)
            total_entries += int(count)
            if max_at is not None and (last_at is None or max_at > last_at):
                last_at = max_at
        journal_meta = CrmJournalMeta(
            total_entries=total_entries,
            entries_by_type=types,
            last_entry_at=last_at,
        )

    # Hop chat sessions · derive from SessionEvent (chat events) METADATA ONLY
    hop_meta = CrmHopSessionMeta(total_sessions=0, last_session_at=None)
    chat_event_types = ("hop_message", "chat_message", "ai_chat")
    chat_q = (
        db.query(
            func.count(SessionEvent.id),
            func.max(SessionEvent.created_at),
        )
        .join(JourneySession, JourneySession.id == SessionEvent.session_id)
        .filter(
            JourneySession.user_id == user.id,
            SessionEvent.event_type.in_(chat_event_types),
        )
        .first()
    )
    if chat_q:
        cnt, max_at = chat_q
        hop_meta = CrmHopSessionMeta(
            total_sessions=int(cnt or 0),
            last_session_at=max_at,
        )

    onboarding_status = (
        user.onboarding_status.value
        if user.onboarding_status is not None and hasattr(user.onboarding_status, "value")
        else str(user.onboarding_status or "not_started")
    )

    return CrmJourneySnapshot(
        onboarding_status=onboarding_status,
        journey_progress=round(journey_progress, 3),
        onboarding_answers=dict(user.onboarding_answers or {}),
        tests=tests,
        consolidated_profile=profile,
        journal=journal_meta,
        hop_sessions=hop_meta,
    )


# ---------------------------------------------------------------------------
# Detail · demographics
# ---------------------------------------------------------------------------


def _build_demographics(user: User) -> CrmDemographics:
    answers = dict(user.onboarding_answers or {})
    city = answers.get("city") or answers.get("ciudad")
    country = answers.get("country") or answers.get("pais") or answers.get("country_residence")
    languages = answers.get("languages") or answers.get("idiomas") or []
    if not isinstance(languages, list):
        languages = []

    return CrmDemographics(
        name=user.name,
        email=user.email,
        phone=user.phone,
        birthdate=user.birthdate,
        age=_derive_age(user.birthdate),
        city=str(city) if city else None,
        country=str(country) if country else None,
        budget_band=user.budget_band,
        budget_max_usd=user.budget_max_usd,
        preferred_countries=list(user.preferred_countries or []),
        languages=[str(x) for x in languages[:6]],
        english_cefr_level=user.english_cefr_level,
        english_test_completed=bool(user.english_test_completed),
        onboarding_answers=answers,
    )


# ---------------------------------------------------------------------------
# Detail · activity log
# ---------------------------------------------------------------------------


def _build_activity_log(db: DBSession, user: User) -> CrmActivityLog:
    items: List[CrmActivityEntry] = []

    # Contact request event
    if user.gh_contact_requested_at:
        items.append(
            CrmActivityEntry(
                at=user.gh_contact_requested_at,
                kind="contact_request",
                label=(
                    f"Solicitud de contacto · estado {user.gh_contact_status or 'pending'}"
                ),
                actor_email=user.email,
                payload={
                    "status": user.gh_contact_status,
                    "message": (user.gh_contact_message or "")[:300],
                },
            )
        )

    # Pipeline transition event
    if user.lead_pipeline_status and user.lead_pipeline_status_at:
        items.append(
            CrmActivityEntry(
                at=user.lead_pipeline_status_at,
                kind="pipeline_change",
                label=f"Pipeline · {user.lead_pipeline_status}",
                actor_email=None,
                payload={"status": user.lead_pipeline_status},
            )
        )

    # Bitrix sync events for this user
    bitrix_rows = (
        db.query(BitrixSyncLog)
        .filter(BitrixSyncLog.user_id == user.id)
        .order_by(BitrixSyncLog.created_at.desc())
        .limit(20)
        .all()
    )
    for br in bitrix_rows:
        items.append(
            CrmActivityEntry(
                at=br.created_at,
                kind="bitrix_sync",
                label=f"Sync Bitrix · {br.action} · {br.status}",
                actor_email=None,
                payload={
                    "entity_type": br.entity_type,
                    "entity_id": br.entity_id,
                    "provider": br.provider,
                    "attempts": br.attempts,
                },
            )
        )

    # Audit events scoped to this user
    audit_rows = (
        db.query(AuditLog)
        .filter(
            or_(
                AuditLog.resource_id == str(user.id),
                AuditLog.user_id == user.id,
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )
    actor_email_cache: Dict[UUID, Optional[str]] = {}
    for ar in audit_rows:
        actor_email = None
        if ar.user_id:
            if ar.user_id not in actor_email_cache:
                u = db.query(User.email).filter(User.id == ar.user_id).first()
                actor_email_cache[ar.user_id] = u[0] if u else None
            actor_email = actor_email_cache[ar.user_id]
        items.append(
            CrmActivityEntry(
                at=ar.created_at,
                kind="audit",
                label=f"{ar.action} · {ar.resource_type}",
                actor_email=actor_email,
                payload=dict(ar.payload or {}),
            )
        )

    items.sort(key=lambda x: x.at, reverse=True)
    items = items[:50]
    return CrmActivityLog(items=items, total=len(items))


# ---------------------------------------------------------------------------
# AI analysis · prompt invocation + caching
# ---------------------------------------------------------------------------


def _format_catalog_block(catalog: List[Program]) -> str:
    if not catalog:
        return "(catálogo vacío para este perfil · genera matches sin programas)"
    lines: List[str] = []
    for p in catalog:
        country = p.country or "n/d"
        cost_str = f"USD ${p.cost_total:,}" if p.cost_total else "n/d"
        lines.append(
            f"- {p.program_id} · {p.name} · {p.institution} · {country} · "
            f"{p.type} · {cost_str} · idioma: {p.language_requirement or 'n/d'}"
        )
    return "\n".join(lines)


def _format_narrative_block(snapshot: CrmJourneySnapshot) -> str:
    lines: List[str] = []
    if snapshot.consolidated_profile and snapshot.consolidated_profile.summary:
        lines.append(f"Síntesis: {snapshot.consolidated_profile.summary}")
    if snapshot.consolidated_profile and snapshot.consolidated_profile.interests:
        lines.append(
            f"Áreas de interés: {', '.join(snapshot.consolidated_profile.interests)}"
        )
    if snapshot.tests:
        test_ids = ", ".join(t.test_id for t in snapshot.tests[:5])
        lines.append(f"Tests aplicados: {test_ids}")
    if snapshot.journal.total_entries:
        lines.append(
            f"Journal: {snapshot.journal.total_entries} entradas (sin contenido por privacidad)"
        )
    if snapshot.hop_sessions.total_sessions:
        lines.append(
            f"Conversaciones con Hop: {snapshot.hop_sessions.total_sessions} sesiones"
        )
    if not lines:
        return "(sin señales narrativas adicionales)"
    return "\n".join(lines)


def _select_catalog_for_lead(
    db: DBSession, user: User, max_n: int = 5
) -> List[Program]:
    """Filter the catalog by preferred countries + budget band before AI."""
    q = db.query(Program).filter(Program.active.is_(True))
    countries = list(user.preferred_countries or [])
    if countries:
        q = q.filter(Program.country.in_(countries))
    if user.budget_band:
        # Map student budget bands to catalog tiers (best-effort).
        band_map = {
            "bajo": ["low"],
            "medio": ["low", "medium"],
            "alto": ["low", "medium", "high"],
            "low": ["low"],
            "medium": ["low", "medium"],
            "high": ["low", "medium", "high"],
            "premium": ["low", "medium", "high", "premium"],
        }
        tiers = band_map.get(user.budget_band.lower(), [])
        if tiers:
            q = q.filter(Program.budget_tier.in_(tiers))
    candidates = q.limit(max_n).all()
    if not candidates:
        # Fallback · anything active so the AI has *something* to anchor on
        candidates = (
            db.query(Program).filter(Program.active.is_(True)).limit(max_n).all()
        )
    return candidates


def _fallback_ai_analysis(
    *,
    user: User,
    score: int,
    band: str,
    catalog: List[Program],
) -> CrmAiAnalysis:
    """Deterministic plantilla cuando Claude falla (D-005 · template fallback).

    Mantiene el contrato de output · evita romper el FE.
    """
    if band == "hot":
        rationale = (
            f"Lead caliente con score {score}. Combina señales fuertes de "
            "engagement con la plataforma y datos demográficos suficientes para "
            "una conversación accionable. Recomendado priorizar contacto esta "
            "semana."
        )
    elif band == "warm":
        rationale = (
            f"Lead tibio con score {score}. Hay interés visible pero faltan "
            "señales clave para cerrar (puede ser presupuesto, países o tests). "
            "Vale la pena un acercamiento de bajo costo para recolectar info."
        )
    else:
        rationale = (
            f"Lead frío con score {score}. Aún no hay tracción suficiente para "
            "outreach activo · recomendado mantenerlo en nutrición pasiva "
            "(newsletter + reminders) hasta que avance el journey."
        )

    matches = [
        CrmProgramMatch(
            program_id=p.program_id,
            name=p.name,
            institution=p.institution,
            country=p.country,
            match_reason=(
                f"País {p.country or 'compatible'} · {p.type} · "
                f"{p.duration_months}m"
            )[:140],
        )
        for p in (catalog[:3] if catalog else [])
    ]

    if band == "hot":
        next_actions = [
            CrmNextAction(
                priority="high",
                action="Llamar al lead esta semana",
                why="Score alto y señales fuertes · ventana de oportunidad corta.",
            ),
            CrmNextAction(
                priority="medium",
                action="Enviar info detallada de los 3 programas top",
                why="El lead tiene suficiente claridad para evaluar opciones concretas.",
            ),
        ]
    elif band == "warm":
        next_actions = [
            CrmNextAction(
                priority="medium",
                action="Enviar formulario corto pidiendo presupuesto y país objetivo",
                why="Falta info clave · una micro-encuesta puede subir el score a hot.",
            ),
            CrmNextAction(
                priority="low",
                action="Agendar follow-up en 2 semanas",
                why="Dejar que el lead acumule más señales antes del outreach principal.",
            ),
        ]
    else:
        next_actions = [
            CrmNextAction(
                priority="low",
                action="Mantener en nurturing pasivo",
                why="Score bajo · empujar ahora desperdicia ciclos comerciales.",
            ),
        ]

    return CrmAiAnalysis(
        rationale=rationale,
        program_matches=matches,
        next_actions=next_actions,
        generated_at=datetime.utcnow(),
        model_used=None,
        cache_age_seconds=0,
        is_fallback=True,
    )


def _invoke_ai_analysis(
    *,
    user: User,
    score: int,
    signals: List[ScoreBreakdownSignal],
    snapshot: CrmJourneySnapshot,
    catalog: List[Program],
) -> CrmAiAnalysis:
    """Calls the prompt · parses JSON · falls back to template if anything
    breaks. Never raises."""
    settings = get_settings()
    band = score_band(score)

    try:
        template = load_prompt("crm_lead_analysis")
        # Fase C · sustitución por .replace() y NO .format(): el template trae
        # llaves literales (el JSON de ejemplo del output y `{"high","medium",
        # "low"}`) que .format() interpreta como placeholders → KeyError →
        # el análisis IA NUNCA corría y todo lead recibía la plantilla.
        # Mismo patrón que hop_chat_service.
        values = {
            "email": user.email,
            "name": user.name or "(sin nombre)",
            "age": _derive_age(user.birthdate) if user.birthdate else "n/d",
            "city": snapshot.onboarding_answers.get("city")
            or snapshot.onboarding_answers.get("ciudad")
            or "n/d",
            "country": snapshot.onboarding_answers.get("country")
            or snapshot.onboarding_answers.get("pais")
            or "n/d",
            "origin": _classify_origin(user),
            "onboarding_status": snapshot.onboarding_status,
            "gh_contact_status": user.gh_contact_status or "ninguna",
            "gh_contact_message": (user.gh_contact_message or "")[:280] or "(sin mensaje)",
            "score": score,
            "score_band": band,
            "journey_progress_pct": int((snapshot.journey_progress or 0) * 100),
            "tests_completed": len(snapshot.tests),
            "has_profile": "sí" if snapshot.consolidated_profile else "no",
            "english_cefr_level": user.english_cefr_level or "n/d",
            "budget_band": user.budget_band or "n/d",
            "budget_max_usd": user.budget_max_usd or "n/d",
            "preferred_countries": ", ".join(user.preferred_countries or []) or "n/d",
            "catalog_block": _format_catalog_block(catalog),
            "narrative_block": _format_narrative_block(snapshot),
        }
        prompt = template
        for key, val in values.items():
            prompt = prompt.replace("{" + key + "}", str(val))
    except Exception as exc:  # noqa: BLE001
        logger.warning("crm_lead_analysis prompt build failed · %s", exc)
        return _fallback_ai_analysis(user=user, score=score, band=band, catalog=catalog)

    raw = call_claude(
        prompt,
        session_id=f"crm-lead-{user.id}",
        prompt_version="crm_lead_analysis_v1",
    )
    if not raw:
        return _fallback_ai_analysis(user=user, score=score, band=band, catalog=catalog)

    # Fase C · parseo central robusto (fences + extracción del primer objeto).
    # El inline anterior usaba `lstrip("```json")`, que quita un SET de
    # caracteres (no el prefijo) y podía comerse el inicio del JSON.
    try:
        parsed = parse_ai_json(raw)
    except AIJsonError:
        logger.warning("crm_lead_analysis · could not parse AI output")
        return _fallback_ai_analysis(user=user, score=score, band=band, catalog=catalog)
    if not isinstance(parsed, dict):
        logger.warning("crm_lead_analysis · AI output is not a JSON object")
        return _fallback_ai_analysis(user=user, score=score, band=band, catalog=catalog)

    rationale = str(parsed.get("rationale") or "").strip()
    if not rationale:
        return _fallback_ai_analysis(user=user, score=score, band=band, catalog=catalog)

    program_matches: List[CrmProgramMatch] = []
    catalog_by_pid = {p.program_id: p for p in catalog}
    for pm in (parsed.get("program_matches") or [])[:3]:
        pid = str(pm.get("program_id") or "").strip()
        name = str(pm.get("name") or "").strip()
        match_reason = str(pm.get("match_reason") or "").strip()[:140]
        if not pid or not name or not match_reason:
            continue
        # If AI hallucinated a program_id, anchor to a catalog row by name.
        prog = catalog_by_pid.get(pid)
        if prog is None:
            # fallback: best-effort match by name in catalog
            for p in catalog:
                if p.name.lower() == name.lower():
                    prog = p
                    break
        program_matches.append(
            CrmProgramMatch(
                program_id=prog.program_id if prog else pid,
                name=prog.name if prog else name,
                institution=prog.institution if prog else None,
                country=prog.country if prog else None,
                match_reason=match_reason,
            )
        )

    next_actions: List[CrmNextAction] = []
    for na in (parsed.get("next_actions") or [])[:3]:
        prio = str(na.get("priority") or "medium").lower()
        if prio not in ("high", "medium", "low"):
            prio = "medium"
        action = str(na.get("action") or "").strip()
        why = str(na.get("why") or "").strip()
        if not action:
            continue
        next_actions.append(
            CrmNextAction(priority=prio, action=action, why=why)  # type: ignore[arg-type]
        )

    if not next_actions:
        # Minimum viable next_actions list
        return _fallback_ai_analysis(user=user, score=score, band=band, catalog=catalog)

    return CrmAiAnalysis(
        rationale=rationale,
        program_matches=program_matches,
        next_actions=next_actions,
        generated_at=datetime.utcnow(),
        model_used=settings.ai_model,
        cache_age_seconds=0,
        is_fallback=False,
    )


def _serialize_ai_analysis(analysis: CrmAiAnalysis) -> dict:
    """JSON-safe serialization for storing in the JSONB cache column."""
    return {
        "rationale": analysis.rationale,
        "program_matches": [pm.model_dump() for pm in analysis.program_matches],
        "next_actions": [na.model_dump() for na in analysis.next_actions],
        "generated_at": analysis.generated_at.isoformat(),
        "model_used": analysis.model_used,
        "is_fallback": analysis.is_fallback,
    }


def _deserialize_ai_analysis(payload: dict, cached_at: datetime) -> CrmAiAnalysis:
    program_matches = [CrmProgramMatch(**pm) for pm in (payload.get("program_matches") or [])]
    next_actions = [CrmNextAction(**na) for na in (payload.get("next_actions") or [])]
    age = (datetime.utcnow() - cached_at).total_seconds()
    return CrmAiAnalysis(
        rationale=str(payload.get("rationale") or ""),
        program_matches=program_matches,
        next_actions=next_actions,
        generated_at=cached_at,
        model_used=payload.get("model_used"),
        cache_age_seconds=int(max(0, age)),
        is_fallback=bool(payload.get("is_fallback", False)),
    )


def regenerate_ai_analysis(
    db: DBSession, user: User, *, force: bool = False
) -> CrmAiAnalysis:
    """Generates (or re-uses cache) the AI analysis. Persists into User row."""
    # Cache hit?
    if not force and user.ai_analysis_cache and user.ai_analysis_cached_at:
        if datetime.utcnow() - user.ai_analysis_cached_at < AI_CACHE_TTL:
            return _deserialize_ai_analysis(
                user.ai_analysis_cache, user.ai_analysis_cached_at
            )

    # Build inputs
    snapshot = _get_journey_snapshot(db, user)
    sess = (
        db.query(JourneySession)
        .filter(JourneySession.user_id == user.id)
        .order_by(JourneySession.updated_at.desc())
        .first()
    )
    tests_n = len(snapshot.tests)
    has_profile = snapshot.consolidated_profile is not None
    has_contact = (user.gh_contact_status or "") in ("pending", "in_progress")
    score, signals = _compute_signals(
        user=user,
        session=sess,
        tests_completed=tests_n,
        has_profile=has_profile,
        has_open_contact_request=has_contact,
    )

    catalog = _select_catalog_for_lead(db, user, max_n=5)
    analysis = _invoke_ai_analysis(
        user=user,
        score=score,
        signals=signals,
        snapshot=snapshot,
        catalog=catalog,
    )

    # Persist cache
    user.ai_analysis_cache = _serialize_ai_analysis(analysis)
    user.ai_analysis_cached_at = analysis.generated_at
    db.commit()
    return analysis


def get_cached_ai_analysis(user: User) -> Optional[CrmAiAnalysis]:
    """Returns the cached AI analysis if fresh · None otherwise."""
    if not user.ai_analysis_cache or not user.ai_analysis_cached_at:
        return None
    if datetime.utcnow() - user.ai_analysis_cached_at > AI_CACHE_TTL:
        return None
    return _deserialize_ai_analysis(user.ai_analysis_cache, user.ai_analysis_cached_at)


# ---------------------------------------------------------------------------
# Detail · top-level builder
# ---------------------------------------------------------------------------


def get_lead_detail(
    db: DBSession, user: User, *, include_ai: bool = True
) -> CrmLeadDetailResponse:
    sess = (
        db.query(JourneySession)
        .filter(JourneySession.user_id == user.id)
        .order_by(JourneySession.updated_at.desc())
        .first()
    )
    tests_n = (
        db.query(func.count(VocationalTestResult.id))
        .filter(VocationalTestResult.user_id == user.id)
        .scalar()
        or 0
    )
    has_profile = (
        db.query(ConsolidatedProfileCache)
        .filter(
            ConsolidatedProfileCache.user_id == user.id,
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .first()
        is not None
    )
    has_contact = (user.gh_contact_status or "") in ("pending", "in_progress")
    score, signals = _compute_signals(
        user=user,
        session=sess,
        tests_completed=int(tests_n),
        has_profile=has_profile,
        has_open_contact_request=has_contact,
    )
    band = score_band(score)
    rationale_short = _short_rationale(score=score, band=band, signals=signals)

    school_name = None
    if user.school_id:
        sn = db.query(School.name).filter(School.id == user.school_id).first()
        if sn:
            school_name = sn[0]

    snapshot = _get_journey_snapshot(db, user)
    demographics = _build_demographics(user)
    activity = _build_activity_log(db, user)

    ai = get_cached_ai_analysis(user) if include_ai else None

    # GH-COMMPROD-B2 · resolve assignee name eagerly (single hop · cached call site)
    assigned_to_name: Optional[str] = None
    if user.assigned_to_user_id is not None:
        assignee = (
            db.query(User).filter(User.id == user.assigned_to_user_id).first()
        )
        if assignee is not None:
            assigned_to_name = assignee.name or assignee.email

    return CrmLeadDetailResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        origin=_classify_origin(user),
        school_id=user.school_id,
        school_name=school_name,
        pipeline_status=user.lead_pipeline_status,  # type: ignore[arg-type]
        pipeline_status_at=user.lead_pipeline_status_at,
        pipeline_status_version=user.pipeline_status_version,
        gh_contact_status=user.gh_contact_status,
        gh_contact_message=user.gh_contact_message,
        gh_contact_requested_at=user.gh_contact_requested_at,
        assigned_to_user_id=user.assigned_to_user_id,
        assigned_to_name=assigned_to_name,
        assigned_at=user.assigned_at,
        score_breakdown=CrmScoreBreakdown(
            score=score,
            band=band,
            signals=signals,
            rationale=rationale_short,
        ),
        demographics=demographics,
        journey=snapshot,
        ai_analysis=ai,
        activity_log=activity,
    )


def _short_rationale(
    *, score: int, band: str, signals: List[ScoreBreakdownSignal]
) -> str:
    """1-line determinístico (idéntico patrón al scoring service)."""
    contributing = [s for s in signals if s.contributed >= 5]
    if not contributing:
        return "Aún sin señales suficientes para evaluar."
    head = (
        "Lead caliente · "
        if band == "hot"
        else "Lead tibio · "
        if band == "warm"
        else "Aún frío · "
    )
    bits = [s.evidence for s in contributing[:5]]
    return head + " · ".join(bits)


# ---------------------------------------------------------------------------
# Pipeline state machine · QA-AUD-072
# ---------------------------------------------------------------------------

# Mapa explícito de transiciones válidas.
# Cualquier transición no listada aquí → InvalidPipelineTransitionError → 409.
PIPELINE_VALID_TRANSITIONS: Dict[Optional[str], List[str]] = {
    None: ["pending", "contacted", "qualified", "converted", "declined"],
    "pending": ["contacted", "declined"],
    "contacted": ["qualified", "declined"],
    "qualified": ["converted", "declined"],
    "converted": ["declined"],
    "declined": ["pending"],
}


class StaleOpportunityError(Exception):
    """Lanzado cuando la versión del pipeline cambió concurrentemente.

    El router captura esta excepción y devuelve HTTP 409 Conflict con
    conflict_kind='stale'.
    """


class InvalidPipelineTransitionError(Exception):
    """Lanzado cuando la transición de estado no está en el state machine.

    El router captura esta excepción y devuelve HTTP 409 Conflict con
    conflict_kind='invalid_transition'.
    """


def _validate_pipeline_transition(
    from_status: Optional[str], to_status: str
) -> None:
    """Valida que la transición from → to es legal según el state machine.

    Raises:
        InvalidPipelineTransitionError: si la transición no está permitida.
    """
    allowed = PIPELINE_VALID_TRANSITIONS.get(from_status, [])
    if to_status not in allowed:
        raise InvalidPipelineTransitionError(
            f"Transición inválida: '{from_status}' → '{to_status}'. "
            f"Transiciones permitidas desde '{from_status}': {allowed}"
        )


# ---------------------------------------------------------------------------
# PATCH pipeline status
# ---------------------------------------------------------------------------


def update_pipeline_status(
    db: DBSession,
    user: User,
    *,
    new_status: str,
    note: Optional[str] = None,
    actor: User,
    request,  # FastAPI Request · for audit
    expected_version: Optional[int] = None,
) -> User:
    """Muta user.lead_pipeline_status con state machine + locking optimista.

    Implementa compare-and-swap atómico:
    1. Valida la transición en el state machine.
    2. Si expected_version se provee: UPDATE con WHERE version = expected_version.
    3. Si 0 filas afectadas → StaleOpportunityError (escritura concurrente).
    4. Post-commit: audit log + Bitrix mock + notificación al asignado.

    Args:
        expected_version: versión que el cliente leyó. None → backward-compat
            (sin verificar CAS).

    Raises:
        InvalidPipelineTransitionError: transición no permitida → 409.
        StaleOpportunityError: versión stale detectada → 409.
    """
    from app.services.audit_service import log_action

    previous = user.lead_pipeline_status

    # 1. Validar transición en el state machine
    _validate_pipeline_transition(previous, new_status)

    # 2. Atomic compare-and-swap
    now = datetime.utcnow()

    if expected_version is not None:
        stmt = (
            update(User)
            .where(User.id == user.id)
            .where(User.pipeline_status_version == expected_version)
            .values(
                lead_pipeline_status=new_status,
                lead_pipeline_status_at=now,
                pipeline_status_version=User.pipeline_status_version + 1,
                updated_at=now,
            )
        )
        result = db.execute(stmt)
        if result.rowcount == 0:
            raise StaleOpportunityError(
                f"Conflicto concurrente detectado en lead {user.id}. "
                "El estado fue modificado por otra sesión. "
                "Recarga el lead y reintenta."
            )
        db.commit()
        db.refresh(user)
    else:
        # Sin expected_version → escritura directa (clientes legacy / backward-compat)
        user.lead_pipeline_status = new_status
        user.lead_pipeline_status_at = now
        user.pipeline_status_version = (user.pipeline_status_version or 1) + 1
        db.flush()

    # Si el path CAS no hizo commit aún (path sin expected_version), lo hacemos aquí.
    # El path CAS ya commitó antes; el audit/bitrix/notif van en una segunda tx.
    if expected_version is None:
        # Audit (dentro de la tx principal en path sin CAS)
        try:
            log_action(
                db,
                user=actor,
                action="crm.pipeline_status_change",
                resource_type="user",
                resource_id=str(user.id),
                payload={
                    "previous": previous,
                    "new": new_status,
                    "note": (note or "")[:500],
                },
                request=request,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit log failed for crm.pipeline_status_change · %s", exc)

        # Bitrix sync log mock entry · D-020 stub policy
        try:
            sync = BitrixSyncLog(
                entity_type="user",
                entity_id=str(user.id),
                user_id=user.id,
                action=f"pipeline.{new_status}",
                payload={"previous": previous, "new": new_status, "note": (note or "")[:200]},
                bitrix_response=None,
                status=BitrixSyncStatus.STUB.value,
                provider="stub",
                attempts=0,
            )
            db.add(sync)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bitrix mock log failed for crm.pipeline_status_change · %s", exc)

        db.commit()
        db.refresh(user)
    else:
        # Path CAS: audit + bitrix en tx separada post-commit
        # (fallo externo no revierte el cambio de estado)
        try:
            log_action(
                db,
                user=actor,
                action="crm.pipeline_status_change",
                resource_type="user",
                resource_id=str(user.id),
                payload={
                    "previous": previous,
                    "new": new_status,
                    "note": (note or "")[:500],
                    "expected_version": expected_version,
                },
                request=request,
            )
            sync = BitrixSyncLog(
                entity_type="user",
                entity_id=str(user.id),
                user_id=user.id,
                action=f"pipeline.{new_status}",
                payload={"previous": previous, "new": new_status, "note": (note or "")[:200]},
                bitrix_response=None,
                status=BitrixSyncStatus.STUB.value,
                provider="stub",
                attempts=0,
            )
            db.add(sync)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("post-commit side effects failed for crm.pipeline_status_change · %s", exc)
            db.rollback()

    # GH-COMMPROD-A1 · notify the lead assignee when someone else moved
    # the pipeline status (skip self-action and unassigned leads).
    try:
        if (
            user.assigned_to_user_id
            and user.assigned_to_user_id != actor.id
        ):
            from app.services import notifications_service

            notifications_service.create_notification(
                db,
                user_id=user.assigned_to_user_id,
                type="lead.pipeline_changed",
                title=f"Pipeline movido · {user.name or user.email}",
                body=f"{previous or 'sin estado'} → {new_status}"
                + (f" · {actor.name or actor.email}" if actor else ""),
                data={
                    "lead_user_id": str(user.id),
                    "previous": previous,
                    "new": new_status,
                    "navigate_to": f"/admin/crm/leads/{user.id}",
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "notifications · pipeline_changed dispatch failed · %s", exc
        )

    return user


# ---------------------------------------------------------------------------
# Permission gate · school_radar leads must respect ownership for non-super
# ---------------------------------------------------------------------------


def can_access_lead(*, actor: User, target: User, target_score: int) -> bool:
    """Authorization rule for the detail endpoint.

    super_admin: unrestricted.
    gh_commercial: can see all leads EXCEPT students of a colegio that have
        NOT requested contact AND whose score is below SCHOOL_RADAR_MIN_SCORE.
        (The list endpoint already filters those · this is a defense in depth
        for the detail endpoint.)
    """
    if actor.role == UserRole.SUPER_ADMIN:
        return True
    if actor.role == UserRole.GH_COMMERCIAL:
        # School student that has NOT opted-in to contact
        if target.school_id is not None and (
            target.gh_contact_status is None
            or target.gh_contact_status in ("declined",)
        ):
            return target_score >= SCHOOL_RADAR_MIN_SCORE
        return True
    return False
