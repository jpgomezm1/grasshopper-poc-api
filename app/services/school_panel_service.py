"""School panel service · GH-S9-BE-01/02/03/04/05.

Centralizes the cohort-level logic exposed by `/school/me/*`:

    - `classify_journey(user, ...)`       · journey_status decision (GH-S9-BE-04)
    - `compute_completion_pct(user, ...)` · 0-100 progress proxy
    - `build_dashboard_kpis(school)`      · cached 5 min per school
    - `build_cohort_reports(school)`      · cohort distributions
    - `students_query(school)`            · filter + paginate scaffold

Caching:
    Dashboard + reports are cached in-process (TTL 5 min, per school_id).
    Same pattern used in `app/api/v1/admin.py`. Bypassable via `refresh=True`.

Isolation:
    All queries take a `school_id: UUID` and filter `User.school_id == school_id`.
    Callers (routers) MUST validate that the requested school matches the
    caller's `school_id` (or that the caller is super_admin).
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    ConsolidatedProfileCache,
    JournalEntry,
    JournalEntryType,
    OnboardingStatus,
    Report,
    Route,
    SavedOferta,
    School,
    Session as JourneySession,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.school_panel import (
    CohortBucket,
    CohortReportsResponse,
    JournalEntrySummary,
    LicenseSnapshot,
    RecommendationSummary,
    SchoolDashboardKpis,
    StudentDetailResponse,
    StudentRow,
    TestSummary,
    TopProgramHit,
)
from app.services.license_service import _current_active_license


logger = logging.getLogger(__name__)


# In-process cache: {school_id_str: (timestamp, payload)}
_DASHBOARD_CACHE: Dict[str, Tuple[float, SchoolDashboardKpis]] = {}
_REPORTS_CACHE: Dict[str, Tuple[float, CohortReportsResponse]] = {}
_TTL_SECONDS = 300  # 5 minutes


# ============================================================================
# Classification logic · GH-S9-BE-04
# ============================================================================

# Public so QA-02 can import it directly.
COMPLETION_WEIGHTS = {
    "onboarding_completed": 20,    # finished onboarding
    "tests_per_unit": 12,          # each completed test (cap 5 → 60)
    "consolidated_profile": 12,    # has cached IA profile
    "saved_offers": 4,             # at least one bookmarked oferta
    "report_generated": 4,         # at least one PDF report
}
LOST_INACTIVE_DAYS = 21  # if last activity > 21d AND not completed → "perdido"
DECIDED_MIN_PCT = 80     # >=80% → "completado" (a.k.a. decidido)
PROGRESS_MIN_PCT = 15    # >=15% → "en_progreso"


def compute_completion_pct(
    *,
    onboarding_completed: bool,
    tests_completed: int,
    has_profile: bool,
    has_saved: bool,
    has_report: bool,
) -> int:
    """Deterministic 0-100 completion score · drives classification."""
    score = 0
    if onboarding_completed:
        score += COMPLETION_WEIGHTS["onboarding_completed"]
    score += min(5, max(0, tests_completed)) * COMPLETION_WEIGHTS["tests_per_unit"]
    if has_profile:
        score += COMPLETION_WEIGHTS["consolidated_profile"]
    if has_saved:
        score += COMPLETION_WEIGHTS["saved_offers"]
    if has_report:
        score += COMPLETION_WEIGHTS["report_generated"]
    return max(0, min(100, score))


def classify_journey(
    *,
    completion_pct: int,
    last_active_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> str:
    """Classify a student into one of: no_iniciado · en_progreso · completado · perdido.

    Rules (in order):
        1. completion_pct >= DECIDED_MIN_PCT → completado
        2. last_active_at older than LOST_INACTIVE_DAYS AND completion < DECIDED_MIN_PCT
           AND completion > 0 → perdido (i.e. started but ghosted)
        3. completion_pct >= PROGRESS_MIN_PCT → en_progreso
        4. else → no_iniciado
    """
    now = now or datetime.utcnow()
    if completion_pct >= DECIDED_MIN_PCT:
        return "completado"
    if (
        last_active_at is not None
        and (now - last_active_at) >= timedelta(days=LOST_INACTIVE_DAYS)
        and completion_pct < DECIDED_MIN_PCT
        and completion_pct > 0
    ):
        return "perdido"
    if completion_pct >= PROGRESS_MIN_PCT:
        return "en_progreso"
    return "no_iniciado"


# ============================================================================
# Per-student aggregator · used by list + detail
# ============================================================================


def _student_signal(db: DBSession, user: User) -> Dict[str, Any]:
    """Pull all signals required to compute completion_pct + journey_status.

    Optimized for one-shot aggregation; for the list endpoint we batch this
    via SQL group-by and pass through a different code path · see
    `_batch_student_signals`.
    """
    tests_count = (
        db.query(func.count(VocationalTestResult.id))
        .filter(VocationalTestResult.user_id == user.id)
        .scalar()
        or 0
    )
    has_profile = (
        db.query(ConsolidatedProfileCache.id)
        .filter(
            ConsolidatedProfileCache.user_id == user.id,
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .first()
        is not None
    )
    has_saved = (
        db.query(SavedOferta.id).filter(SavedOferta.user_id == user.id).first()
        is not None
    )
    has_report = (
        db.query(Report.id).filter(Report.user_id == user.id).first() is not None
    )

    onboarding_completed = user.onboarding_status == OnboardingStatus.COMPLETED

    completion_pct = compute_completion_pct(
        onboarding_completed=onboarding_completed,
        tests_completed=int(tests_count),
        has_profile=has_profile,
        has_saved=has_saved,
        has_report=has_report,
    )

    last_active_at = user.updated_at  # proxy: any mutation bumps updated_at

    return {
        "tests_completed_count": int(tests_count),
        "has_consolidated_profile": has_profile,
        "has_saved": has_saved,
        "has_report": has_report,
        "completion_pct": completion_pct,
        "journey_status": classify_journey(
            completion_pct=completion_pct,
            last_active_at=last_active_at,
        ),
        "last_active_at": last_active_at,
    }


def _batch_student_signals(
    db: DBSession, school_id: UUID, user_ids: List[UUID]
) -> Dict[UUID, Dict[str, Any]]:
    """Batched signals for cohort listing.

    Returns {user_id: {tests_count, has_profile, has_saved, has_report}}.
    Skips per-user N+1 queries that the single-row helper would issue.
    """
    if not user_ids:
        return {}

    # tests count by user
    tests_rows = (
        db.query(VocationalTestResult.user_id, func.count(VocationalTestResult.id))
        .filter(VocationalTestResult.user_id.in_(user_ids))
        .group_by(VocationalTestResult.user_id)
        .all()
    )
    tests_map = {r[0]: int(r[1]) for r in tests_rows}

    # consolidated profile flag
    profile_rows = (
        db.query(ConsolidatedProfileCache.user_id)
        .filter(
            ConsolidatedProfileCache.user_id.in_(user_ids),
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .all()
    )
    profile_set = {r[0] for r in profile_rows}

    saved_rows = (
        db.query(SavedOferta.user_id)
        .filter(SavedOferta.user_id.in_(user_ids))
        .distinct()
        .all()
    )
    saved_set = {r[0] for r in saved_rows}

    report_rows = (
        db.query(Report.user_id)
        .filter(Report.user_id.in_(user_ids))
        .distinct()
        .all()
    )
    report_set = {r[0] for r in report_rows}

    return {
        uid: {
            "tests_completed_count": int(tests_map.get(uid, 0)),
            "has_consolidated_profile": uid in profile_set,
            "has_saved": uid in saved_set,
            "has_report": uid in report_set,
        }
        for uid in user_ids
    }


# ============================================================================
# Dashboard KPIs · GH-S9-BE-01
# ============================================================================


def build_dashboard_kpis(
    db: DBSession, school: School, refresh: bool = False
) -> SchoolDashboardKpis:
    """KPIs of the school. Cached 5 min in-process per school_id."""
    key = str(school.id)
    now_t = time.time()
    if not refresh:
        hit = _DASHBOARD_CACHE.get(key)
        if hit and (now_t - hit[0]) < _TTL_SECONDS:
            return hit[1]

    now = datetime.utcnow()

    students = (
        db.query(User)
        .filter(User.school_id == school.id, User.role == UserRole.STUDENT)
        .all()
    )
    student_ids = [u.id for u in students]
    signals = _batch_student_signals(db, school.id, student_ids)

    buckets = Counter()
    completed_journey = 0
    tests_total = 0
    pcts: List[int] = []
    for u in students:
        sig = signals.get(u.id, {})
        completion_pct = compute_completion_pct(
            onboarding_completed=u.onboarding_status == OnboardingStatus.COMPLETED,
            tests_completed=sig.get("tests_completed_count", 0),
            has_profile=sig.get("has_consolidated_profile", False),
            has_saved=sig.get("has_saved", False),
            has_report=sig.get("has_report", False),
        )
        status = classify_journey(
            completion_pct=completion_pct,
            last_active_at=u.updated_at,
            now=now,
        )
        buckets[status] += 1
        if status == "completado":
            completed_journey += 1
        tests_total += sig.get("tests_completed_count", 0)
        pcts.append(completion_pct)

    total_students = len(students)
    avg_tests = (tests_total / total_students) if total_students else 0.0

    reports_30d = (
        db.query(func.count(Report.id))
        .join(User, User.id == Report.user_id)
        .filter(User.school_id == school.id, Report.created_at >= now - timedelta(days=30))
        .scalar()
        or 0
    )

    # license snapshot (reuses the same predicate as license_service)
    lic = _current_active_license(db, school.id)
    seats_used = (
        db.query(func.count(User.id))
        .filter(
            User.school_id == school.id,
            User.role == UserRole.STUDENT,
            User.is_active.is_(True),
        )
        .scalar()
        or 0
    )
    license_snapshot = LicenseSnapshot(
        tier=lic.tier if lic else None,
        seats_total=lic.seats if lic else 0,
        seats_used=int(seats_used),
        expires_at=lic.expires_at if lic else school.license_expires_at,
        is_expired=bool(lic and lic.expires_at and lic.expires_at <= now),
    )

    # holland codes & recommended paths · best-effort from VocationalTestResult JSON.
    holland_counter: Counter = Counter()
    paths_counter: Counter = Counter()
    if student_ids:
        riasec_rows = (
            db.query(VocationalTestResult.scores)
            .filter(
                VocationalTestResult.user_id.in_(student_ids),
                VocationalTestResult.test_id.in_(["riasec", "holland", "istrong"]),
            )
            .all()
        )
        for (scores,) in riasec_rows:
            if isinstance(scores, dict):
                # take top-2 letters as the "code" proxy
                # accepts either {"R": 12, "I": 10, ...} or {"holland_code": "RIA"}
                if isinstance(scores.get("holland_code"), str):
                    code = scores["holland_code"][:3].upper()
                    if code:
                        holland_counter[code] += 1
                else:
                    letters = [
                        k for k in ("R", "I", "A", "S", "E", "C") if k in scores
                    ]
                    if letters:
                        ranked = sorted(letters, key=lambda k: -float(scores.get(k, 0)))
                        code = "".join(ranked[:3])
                        if code:
                            holland_counter[code] += 1

        # recommended paths · top routes selected per session (proxy)
        path_rows = (
            db.query(Route.key, func.count(Route.id))
            .join(JourneySession, JourneySession.id == Route.session_id)
            .filter(JourneySession.user_id.in_(student_ids))
            .group_by(Route.key)
            .order_by(func.count(Route.id).desc())
            .limit(10)
            .all()
        )
        for key_, count in path_rows:
            paths_counter[key_] = int(count)

    top_holland = [
        CohortBucket(code=code, label=code, count=cnt)
        for code, cnt in holland_counter.most_common(5)
    ]
    top_paths = [
        CohortBucket(code=k, label=k.replace("_", " ").title(), count=v)
        for k, v in paths_counter.most_common(5)
    ]

    payload = SchoolDashboardKpis(
        school_id=school.id,
        school_name=school.name,
        total_students=total_students,
        students_no_iniciado=int(buckets.get("no_iniciado", 0)),
        students_en_progreso=int(buckets.get("en_progreso", 0)),
        students_completado=int(buckets.get("completado", 0)),
        students_perdido=int(buckets.get("perdido", 0)),
        students_with_completed_journey=completed_journey,
        avg_tests_per_student=round(avg_tests, 2),
        tests_completed_total=int(tests_total),
        reports_generated_30d=int(reports_30d),
        active_license=license_snapshot,
        top_holland_codes_in_cohort=top_holland,
        top_recommended_paths=top_paths,
        cached_at=now,
    )
    _DASHBOARD_CACHE[key] = (now_t, payload)
    return payload


# ============================================================================
# Cohort reports · GH-S9-BE-05
# ============================================================================


def build_cohort_reports(
    db: DBSession, school: School, refresh: bool = False
) -> CohortReportsResponse:
    key = str(school.id)
    now_t = time.time()
    if not refresh:
        hit = _REPORTS_CACHE.get(key)
        if hit and (now_t - hit[0]) < _TTL_SECONDS:
            return hit[1]

    now = datetime.utcnow()
    students = (
        db.query(User)
        .filter(User.school_id == school.id, User.role == UserRole.STUDENT)
        .all()
    )
    student_ids = [u.id for u in students]
    signals = _batch_student_signals(db, school.id, student_ids)

    journey_counter: Counter = Counter()
    holland_counter: Counter = Counter()
    mbti_counter: Counter = Counter()
    pcts: List[int] = []
    rows_perdido: List[StudentRow] = []

    for u in students:
        sig = signals.get(u.id, {})
        completion_pct = compute_completion_pct(
            onboarding_completed=u.onboarding_status == OnboardingStatus.COMPLETED,
            tests_completed=sig.get("tests_completed_count", 0),
            has_profile=sig.get("has_consolidated_profile", False),
            has_saved=sig.get("has_saved", False),
            has_report=sig.get("has_report", False),
        )
        status = classify_journey(
            completion_pct=completion_pct,
            last_active_at=u.updated_at,
            now=now,
        )
        journey_counter[status] += 1
        pcts.append(completion_pct)

        if status == "perdido":
            rows_perdido.append(
                StudentRow(
                    id=u.id,
                    email=u.email,
                    name=u.name,
                    journey_status=status,
                    completion_pct=completion_pct,
                    tests_completed_count=sig.get("tests_completed_count", 0),
                    has_consolidated_profile=sig.get("has_consolidated_profile", False),
                    last_active_at=u.updated_at,
                    invited_at=u.created_at,
                    created_at=u.created_at,
                )
            )

    # holland + mbti distribution from tests
    if student_ids:
        rows = (
            db.query(VocationalTestResult.test_id, VocationalTestResult.scores)
            .filter(VocationalTestResult.user_id.in_(student_ids))
            .all()
        )
        test_popularity: Counter = Counter()
        for test_id, scores in rows:
            test_popularity[test_id] += 1
            if test_id in ("riasec", "holland", "istrong") and isinstance(scores, dict):
                if isinstance(scores.get("holland_code"), str):
                    code = scores["holland_code"][:3].upper()
                    if code:
                        holland_counter[code] += 1
                else:
                    letters = [
                        k for k in ("R", "I", "A", "S", "E", "C") if k in scores
                    ]
                    if letters:
                        ranked = sorted(letters, key=lambda k: -float(scores.get(k, 0)))
                        code = "".join(ranked[:3])
                        if code:
                            holland_counter[code] += 1
            elif test_id == "mbti" and isinstance(scores, dict):
                mtype = scores.get("type") or scores.get("mbti_type")
                if isinstance(mtype, str) and len(mtype) == 4:
                    mbti_counter[mtype.upper()] += 1
    else:
        test_popularity = Counter()

    completion_rate = (
        100.0 * sum(1 for p in pcts if p >= DECIDED_MIN_PCT) / len(pcts)
        if pcts
        else 0.0
    )
    avg_tests = (
        sum(s.get("tests_completed_count", 0) for s in signals.values()) / len(signals)
        if signals
        else 0.0
    )

    payload = CohortReportsResponse(
        school_id=school.id,
        school_name=school.name,
        distribution_journey_status=[
            CohortBucket(code=s, label=s, count=int(c))
            for s, c in journey_counter.most_common()
        ],
        distribution_holland=[
            CohortBucket(code=k, label=k, count=int(v))
            for k, v in holland_counter.most_common(10)
        ],
        distribution_mbti=[
            CohortBucket(code=k, label=k, count=int(v))
            for k, v in mbti_counter.most_common(8)
        ],
        completion_rate_pct=round(completion_rate, 2),
        avg_tests_per_student=round(avg_tests, 2),
        most_popular_tests=[
            CohortBucket(code=t, label=t.upper(), count=int(c))
            for t, c in test_popularity.most_common(10)
        ],
        students_to_review=rows_perdido[:25],
        cached_at=now,
    )
    _REPORTS_CACHE[key] = (now_t, payload)
    return payload


# ============================================================================
# Cache invalidation · called when school data changes (logo, invite, accept)
# ============================================================================


def invalidate_cache(school_id: UUID) -> None:
    """Drop both caches for the given school."""
    key = str(school_id)
    _DASHBOARD_CACHE.pop(key, None)
    _REPORTS_CACHE.pop(key, None)


# ============================================================================
# Build StudentRow from User + signals
# ============================================================================


def build_student_row(
    user: User, signals: Dict[str, Any], now: Optional[datetime] = None
) -> StudentRow:
    now = now or datetime.utcnow()
    completion_pct = compute_completion_pct(
        onboarding_completed=user.onboarding_status == OnboardingStatus.COMPLETED,
        tests_completed=signals.get("tests_completed_count", 0),
        has_profile=signals.get("has_consolidated_profile", False),
        has_saved=signals.get("has_saved", False),
        has_report=signals.get("has_report", False),
    )
    status = classify_journey(
        completion_pct=completion_pct,
        last_active_at=user.updated_at,
        now=now,
    )
    return StudentRow(
        id=user.id,
        email=user.email,
        name=user.name,
        journey_status=status,
        completion_pct=completion_pct,
        tests_completed_count=signals.get("tests_completed_count", 0),
        has_consolidated_profile=signals.get("has_consolidated_profile", False),
        last_active_at=user.updated_at,
        invited_at=user.created_at,
        created_at=user.created_at,
    )


# ============================================================================
# Student detail aggregator · GH-S9-BE-03
# ============================================================================


def build_student_detail(
    db: DBSession,
    user: User,
    *,
    read_only_for_caller: bool,
) -> StudentDetailResponse:
    sig = _student_signal(db, user)
    tests_rows = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        .order_by(VocationalTestResult.created_at.desc())
        .all()
    )
    tests = [
        TestSummary(
            test_id=r.test_id,
            completed_at=r.created_at,
            source=r.source or "internal",
            scores=r.scores or {},
        )
        for r in tests_rows
    ]

    profile_row = (
        db.query(ConsolidatedProfileCache)
        .filter(
            ConsolidatedProfileCache.user_id == user.id,
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .first()
    )
    consolidated = None
    recommendations: List[RecommendationSummary] = []
    if profile_row:
        consolidated = profile_row.profile_data
        for rec in (profile_row.recommendations_data or [])[:25]:
            if not isinstance(rec, dict):
                continue
            recommendations.append(
                RecommendationSummary(
                    program_id=str(
                        rec.get("program_id") or rec.get("id") or rec.get("slug") or ""
                    ),
                    name=rec.get("name") or rec.get("title"),
                    fit_score=rec.get("fit_score") or rec.get("score"),
                    rationale=rec.get("rationale") or rec.get("why"),
                )
            )

    journal_rows = (
        db.query(JournalEntry)
        .join(JourneySession, JourneySession.id == JournalEntry.session_id)
        .filter(JourneySession.user_id == user.id)
        .order_by(JournalEntry.created_at.desc())
        .limit(50)
        .all()
    )
    journal = [
        JournalEntrySummary(
            id=j.id,
            entry_type=j.entry_type.value if hasattr(j.entry_type, "value") else str(j.entry_type),
            content=j.content,
            created_at=j.created_at,
            auto_generated=bool(j.auto_generated),
        )
        for j in journal_rows
    ]

    saved_rows = (
        db.query(SavedOferta.oferta_id)
        .filter(SavedOferta.user_id == user.id)
        .all()
    )
    saved = [str(r[0]) for r in saved_rows]

    return StudentDetailResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        school_id=user.school_id,
        journey_status=sig["journey_status"],
        completion_pct=sig["completion_pct"],
        onboarding_status=user.onboarding_status.value if hasattr(user.onboarding_status, "value") else str(user.onboarding_status),
        english_cefr_level=user.english_cefr_level,
        tests=tests,
        consolidated_profile=consolidated,
        recommendations=recommendations,
        journal_entries=journal,
        saved_offers=saved,
        last_active_at=user.updated_at,
        created_at=user.created_at,
        read_only_for_caller=read_only_for_caller,
    )
