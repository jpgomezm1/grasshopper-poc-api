"""Student-facing /me/* endpoints.

GH-STUDENT-EXPERIENCE · Sprint student-facing 2026-05-05.

Surfaces the lightweight, student-side aggregations that power:

    Bloque B  · GET  /v1/me/team
    Bloque C  · GET  /v1/me/sessions
    Bloque C  · POST /v1/me/session-requests
    Bloque F  · GET  /v1/me/school-events
    Bloque F  · POST /v1/me/school-events/{id}/rsvp
    Bloque J  · GET  /v1/me/dashboard
    Bloque K  · POST /v1/me/quickprofile-import

REGLA DURA · 2026-05-05 (JP):
    NO mensajería bidireccional · NO chats · NO threads.
    Triggers 1-vía → tareas para el staff + notificaciones IN-BOX al staff.
    Esta surface NO crea ningún canal de respuesta del staff hacia el
    student dentro del producto.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    CohortPsychologistAssignment,
    EnglishTestResult,
    OnboardingStatus,
    OrientationSession,
    Route,
    RouteStatus,
    School,
    SchoolEvent,
    SchoolEventRSVP,
    Session as JourneySession,
    SessionNote,
    StudentCohortAssignment,
    Task,
    User,
    UserRole,
    VocationalTestResult,
)
from app.services import notifications_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["StudentMe"])


# ---------------------------------------------------------------------------
# Helpers · STUDENT-only access gate
# ---------------------------------------------------------------------------


def _require_student(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )


def _resolve_psy_for_student(db: DBSession, student: User) -> Optional[User]:
    """Return the psychologist visible to the student (if any).

    Resolution strategy:
      1. If student has a cohort assignment → first psy assigned to that cohort.
      2. Else if student.school_id → first psychologist of the school.
      3. Else → None (B2C student or no school).
    """
    if not student.school_id:
        return None

    # 1. via cohort
    assignments = (
        db.query(StudentCohortAssignment)
        .filter(StudentCohortAssignment.student_user_id == student.id)
        .all()
    )
    cohort_ids = [a.cohort_id for a in assignments]
    if cohort_ids:
        psy_link = (
            db.query(CohortPsychologistAssignment)
            .filter(CohortPsychologistAssignment.cohort_id.in_(cohort_ids))
            .first()
        )
        if psy_link:
            psy = (
                db.query(User)
                .filter(
                    User.id == psy_link.psychologist_user_id,
                    User.is_active == True,  # noqa: E712
                )
                .first()
            )
            if psy:
                return psy

    # 2. via school fallback
    psy = (
        db.query(User)
        .filter(
            User.school_id == student.school_id,
            User.role == UserRole.PSYCHOLOGIST,
            User.is_active == True,  # noqa: E712
        )
        .order_by(User.created_at.asc())
        .first()
    )
    return psy


def _resolve_advisor_for_student(db: DBSession, student: User) -> Optional[User]:
    """Return the gh advisor (or commercial fallback) assigned to the student.

    Reads `users.assigned_to_user_id` and validates target role belongs
    to the GH team. Returns None if unassigned or role mismatch.
    """
    if not student.assigned_to_user_id:
        return None
    target = (
        db.query(User)
        .filter(
            User.id == student.assigned_to_user_id,
            User.is_active == True,  # noqa: E712
            User.role.in_((UserRole.GH_ADVISOR, UserRole.GH_COMMERCIAL)),
        )
        .first()
    )
    return target


# ---------------------------------------------------------------------------
# Bloque B · GET /me/team
# ---------------------------------------------------------------------------


class TeamMemberOut(BaseModel):
    id: UUID
    name: Optional[str] = None
    email: str
    photo_url: Optional[str] = None  # reserved · users table has no photo today

    model_config = ConfigDict(from_attributes=True)


class MyTeamResponse(BaseModel):
    psy: Optional[TeamMemberOut] = None
    advisor: Optional[TeamMemberOut] = None


def _serialize_member(u: Optional[User]) -> Optional[TeamMemberOut]:
    if u is None:
        return None
    return TeamMemberOut(id=u.id, name=u.name, email=u.email, photo_url=None)


@router.get("/team", response_model=MyTeamResponse)
def get_my_team(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _require_student(current_user)
    psy = _resolve_psy_for_student(db, current_user)
    advisor = _resolve_advisor_for_student(db, current_user)
    return MyTeamResponse(
        psy=_serialize_member(psy),
        advisor=_serialize_member(advisor),
    )


# ---------------------------------------------------------------------------
# Bloque C · GET /me/sessions
# ---------------------------------------------------------------------------


class StudentVisibleNoteOut(BaseModel):
    id: UUID
    content: str
    created_at: datetime
    privacy: str

    model_config = ConfigDict(from_attributes=True)


class StudentSessionOut(BaseModel):
    id: UUID
    advisor_user_id: UUID
    advisor_name: Optional[str] = None
    scheduled_at: datetime
    duration_min: Optional[int] = None
    type: str
    status: str
    summary: Optional[str] = None
    shared_notes: List[StudentVisibleNoteOut] = Field(default_factory=list)


class StudentSessionsResponse(BaseModel):
    upcoming: List[StudentSessionOut] = Field(default_factory=list)
    past: List[StudentSessionOut] = Field(default_factory=list)


@router.get("/sessions", response_model=StudentSessionsResponse)
def list_my_sessions(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _require_student(current_user)

    rows = (
        db.query(OrientationSession)
        .filter(OrientationSession.student_user_id == current_user.id)
        .order_by(OrientationSession.scheduled_at.desc())
        .all()
    )

    advisor_cache: dict[UUID, User] = {}

    def _hydrate(s: OrientationSession) -> StudentSessionOut:
        adv = advisor_cache.get(s.advisor_user_id)
        if adv is None:
            adv = (
                db.query(User).filter(User.id == s.advisor_user_id).first()
            )
            if adv is not None:
                advisor_cache[s.advisor_user_id] = adv

        shared_notes = (
            db.query(SessionNote)
            .filter(
                SessionNote.session_id == s.id,
                SessionNote.privacy == "shared_with_student",
            )
            .order_by(SessionNote.created_at.desc())
            .all()
        )
        return StudentSessionOut(
            id=s.id,
            advisor_user_id=s.advisor_user_id,
            advisor_name=adv.name if adv else None,
            scheduled_at=s.scheduled_at,
            duration_min=s.duration_min,
            type=s.type,
            status=s.status,
            summary=s.summary,
            shared_notes=[
                StudentVisibleNoteOut(
                    id=n.id,
                    content=n.content,
                    created_at=n.created_at,
                    privacy=n.privacy,
                )
                for n in shared_notes
            ],
        )

    now = datetime.utcnow()
    upcoming: List[StudentSessionOut] = []
    past: List[StudentSessionOut] = []
    for s in rows:
        item = _hydrate(s)
        if s.scheduled_at >= now and s.status not in ("cancelled", "no_show"):
            upcoming.append(item)
        else:
            past.append(item)

    upcoming.sort(key=lambda x: x.scheduled_at)
    return StudentSessionsResponse(upcoming=upcoming, past=past)


# ---------------------------------------------------------------------------
# Bloque C · POST /me/session-requests
# ---------------------------------------------------------------------------


class SessionRequestIn(BaseModel):
    reason: str = Field(..., min_length=4, max_length=500)
    suggested_at: Optional[datetime] = None


class SessionRequestOut(BaseModel):
    ok: bool = True
    target_user_id: Optional[UUID] = None
    target_role: Optional[str] = None
    task_id: Optional[UUID] = None


@router.post(
    "/session-requests",
    response_model=SessionRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def request_session(
    payload: SessionRequestIn,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Student requests next orientation session.

    Implementation: creates a Task for the assigned advisor (preferred) or
    psy fallback + a notification. NO chat / NO bidirectional thread.
    """
    _require_student(current_user)

    target = _resolve_advisor_for_student(db, current_user)
    target_role = "gh_advisor"
    if target is None:
        target = _resolve_psy_for_student(db, current_user)
        target_role = "psychologist" if target else None

    if target is None:
        # No advisor / psy yet · we still record the request as a notification
        # to gh_commercial fallback team if one is assigned globally · for now
        # we just return ok=False so the FE shows GhContactCard CTA.
        return SessionRequestOut(ok=False)

    # Create task for the staff member · 1-way trigger.
    description = (
        f"Solicitud de sesión · {current_user.name or current_user.email} · "
        f"{payload.reason[:120]}"
    )
    task = Task(
        assigned_to_user_id=target.id,
        lead_user_id=current_user.id,
        description=description,
        priority="normal",
        status="open",
        created_by_user_id=current_user.id,
        due_at=payload.suggested_at,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        notifications_service.create_notification(
            db,
            user_id=target.id,
            type="task.created",
            title="Solicitud de sesión",
            body=(
                f"{current_user.name or current_user.email} pidió "
                f"agendar una sesión"
            ),
            data={
                "task_id": str(task.id),
                "lead_user_id": str(current_user.id),
                "navigate_to": "/tasks",
            },
        )
    except Exception as exc:  # pragma: no cover · best effort
        logger.warning("session-request notification failed · %s", exc)

    return SessionRequestOut(
        ok=True,
        target_user_id=target.id,
        target_role=target_role,
        task_id=task.id,
    )


# ---------------------------------------------------------------------------
# Bloque F · GET /me/school-events + POST RSVP
# ---------------------------------------------------------------------------


class StudentSchoolEventOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    starts_at: datetime
    ends_at: Optional[datetime] = None
    location: Optional[str] = None
    audience: str
    rsvp_status: Optional[str] = None  # 'going' | 'declined' | 'maybe' | None

    model_config = ConfigDict(from_attributes=True)


@router.get("/school-events", response_model=List[StudentSchoolEventOut])
def list_my_school_events(
    limit: int = 3,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _require_student(current_user)
    if not current_user.school_id:
        return []
    now = datetime.utcnow()
    rows = (
        db.query(SchoolEvent)
        .filter(
            SchoolEvent.school_id == current_user.school_id,
            SchoolEvent.archived_at.is_(None),
            SchoolEvent.starts_at >= now,
            SchoolEvent.audience.in_(("students", "both")),
        )
        .order_by(SchoolEvent.starts_at.asc())
        .limit(max(1, min(limit, 20)))
        .all()
    )

    rsvps = {
        r.event_id: r.status
        for r in db.query(SchoolEventRSVP)
        .filter(
            SchoolEventRSVP.user_id == current_user.id,
            SchoolEventRSVP.event_id.in_([e.id for e in rows]) if rows else False,
        )
        .all()
    }

    return [
        StudentSchoolEventOut(
            id=e.id,
            title=e.title,
            description=e.description,
            starts_at=e.starts_at,
            ends_at=e.ends_at,
            location=e.location,
            audience=e.audience,
            rsvp_status=rsvps.get(e.id),
        )
        for e in rows
    ]


class RsvpIn(BaseModel):
    status: str = Field(..., pattern=r"^(going|declined|maybe)$")


@router.post(
    "/school-events/{event_id}/rsvp",
    response_model=StudentSchoolEventOut,
)
def rsvp_school_event(
    event_id: UUID,
    payload: RsvpIn,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _require_student(current_user)
    if not current_user.school_id:
        raise HTTPException(status_code=403, detail="not a school member")

    event = (
        db.query(SchoolEvent)
        .filter(
            SchoolEvent.id == event_id,
            SchoolEvent.school_id == current_user.school_id,
            SchoolEvent.archived_at.is_(None),
        )
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="event not found")

    rsvp = (
        db.query(SchoolEventRSVP)
        .filter(
            SchoolEventRSVP.event_id == event.id,
            SchoolEventRSVP.user_id == current_user.id,
        )
        .first()
    )
    if rsvp:
        rsvp.status = payload.status
        rsvp.responded_at = datetime.utcnow()
    else:
        rsvp = SchoolEventRSVP(
            event_id=event.id,
            user_id=current_user.id,
            status=payload.status,
        )
        db.add(rsvp)
    db.commit()

    return StudentSchoolEventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        location=event.location,
        audience=event.audience,
        rsvp_status=rsvp.status,
    )


# ---------------------------------------------------------------------------
# Bloque J · GET /me/dashboard · auto-redirect flag + journey_completed_at
# ---------------------------------------------------------------------------


class StudentDashboardResponse(BaseModel):
    onboarding_status: str
    tests_completed: int
    routes_count: int
    should_show_completion: bool
    journey_completed_at: Optional[datetime] = None


def _evaluate_journey_complete(db: DBSession, student: User) -> tuple[bool, int, int]:
    """Returns (criteria_met, tests_count, routes_count)."""
    onboarding_done = student.onboarding_status == OnboardingStatus.COMPLETED

    voc_count = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == student.id)
        .count()
    )
    eng_done = 1 if student.english_test_completed else 0
    tests_count = voc_count + eng_done

    routes_count = (
        db.query(Route)
        .join(JourneySession, Route.session_id == JourneySession.id)
        .filter(
            JourneySession.user_id == student.id,
            Route.status == RouteStatus.ACTIVE,
        )
        .count()
    )
    criteria = onboarding_done and tests_count >= 3 and routes_count >= 2
    return criteria, tests_count, routes_count


@router.get("/dashboard", response_model=StudentDashboardResponse)
def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _require_student(current_user)
    criteria, tests_count, routes_count = _evaluate_journey_complete(
        db, current_user
    )

    should_show = False
    if criteria and current_user.journey_completed_at is None:
        # First time we cross the threshold · stamp + flag.
        current_user.journey_completed_at = datetime.utcnow()
        db.commit()
        db.refresh(current_user)
        should_show = True

    return StudentDashboardResponse(
        onboarding_status=current_user.onboarding_status.value
        if hasattr(current_user.onboarding_status, "value")
        else str(current_user.onboarding_status),
        tests_completed=tests_count,
        routes_count=routes_count,
        should_show_completion=should_show,
        journey_completed_at=current_user.journey_completed_at,
    )


# ---------------------------------------------------------------------------
# Bloque K · POST /me/quickprofile-import
# ---------------------------------------------------------------------------


class QuickProfileImportIn(BaseModel):
    """Free-form dict captured by `QuickProfilePage` BEFORE register.

    Stored in localStorage as `gh_quickprofile_data` and POSTed once
    after a successful registration. Service is permissive · unknown
    keys go straight into onboarding_answers (already JSON), known
    keys map onto top-level user fields.
    """

    name: Optional[str] = None
    phone: Optional[str] = None
    budget_band: Optional[str] = Field(default=None, pattern=r"^(bajo|medio|alto)$")
    budget_max_usd: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    preferred_countries: Optional[List[str]] = None
    answers: Optional[dict] = None


class QuickProfileImportOut(BaseModel):
    ok: bool = True
    onboarding_status: str
    name: Optional[str] = None


@router.post("/quickprofile-import", response_model=QuickProfileImportOut)
def import_quickprofile(
    payload: QuickProfileImportIn,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _require_student(current_user)

    if payload.name and not current_user.name:
        current_user.name = payload.name[:255]
    if payload.phone and not current_user.phone:
        current_user.phone = payload.phone[:50]
    if payload.budget_band:
        current_user.budget_band = payload.budget_band
    if payload.budget_max_usd is not None:
        current_user.budget_max_usd = payload.budget_max_usd
    if payload.preferred_countries:
        current_user.preferred_countries = list(payload.preferred_countries)[:20]
    if payload.answers:
        merged = dict(current_user.onboarding_answers or {})
        # Don't clobber existing answers · quickprofile is the seed.
        for k, v in payload.answers.items():
            merged.setdefault(k, v)
        current_user.onboarding_answers = merged
        if current_user.onboarding_status == OnboardingStatus.NOT_STARTED:
            current_user.onboarding_status = OnboardingStatus.IN_PROGRESS

    db.commit()
    db.refresh(current_user)

    return QuickProfileImportOut(
        ok=True,
        onboarding_status=current_user.onboarding_status.value
        if hasattr(current_user.onboarding_status, "value")
        else str(current_user.onboarding_status),
        name=current_user.name,
    )
