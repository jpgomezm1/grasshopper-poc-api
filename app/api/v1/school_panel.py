"""School panel router · GH-S9-BE-01..07.

All endpoints are scoped to `current_user.school_id`. The school is implicit
from the JWT · we never accept a school_id in the path or body. The single
`/school/me/*` namespace prevents path-based IDOR by construction.

Permission matrix:

    school_admin    · ALL endpoints + invite students+psychologists
    psychologist    · ALL read endpoints + invite students only
    super_admin     · acts on its bound school_id (test path), or 403 if none
    student         · 403

Endpoints:

    GET  /school/me                      · school summary + license usage
    GET  /school/me/dashboard            · KPIs (cached 5 min)
    GET  /school/me/reports              · cohort reports (cached 5 min)
    GET  /school/me/students             · paginated cohort with filters
    GET  /school/me/students/export.csv  · CSV download (same filters)
    GET  /school/me/students/{user_id}   · 360 view of one student
    POST /school/me/logo                 · upload school logo
    GET  /school/me/invitations          · paginated invitations
    POST /school/me/invitations          · create invitation
    DELETE /school/me/invitations/{id}   · revoke pending invitation
    POST /invitations/{token}/accept     · public · creates user

Audit logging:
    Every mutation (invite create/revoke, logo upload, accept) calls
    audit_service.log_action with `school_admin` or `psychologist` actor.
"""
from __future__ import annotations

import csv
import io
import logging
import math
import re
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, asc, desc
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
)
from app.config import get_settings
from app.core.rate_limiter import limiter
from app.db.database import get_db


def _rate_limit_invitation_accept(request: Request) -> None:
    """GH-S11-INFRA-04 · per-IP rate limit for the public invitation accept."""
    from app.core.rate_limiter import rate_limit
    s = get_settings()
    return rate_limit(s.rate_limit_invitations_accept)(request)
from app.db.models import (
    Invitation,
    InvitationStatus,
    OnboardingStatus,
    School,
    User,
    UserRole,
)
from app.schemas.invitation import (
    InvitationAccept,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationListResponse,
    InvitationResponse,
)
from app.schemas.school import SchoolWithStats, SchoolResponse
from app.schemas.school_panel import (
    CohortReportsResponse,
    SchoolDashboardKpis,
    StudentDetailResponse,
    StudentListResponse,
    StudentRow,
)
from app.services import school_panel_service
from app.services.audit_service import log_action
from app.core.url_safety import build_safe_url
from app.services.invitation_service import (
    create_invitation,
    lookup_token,
    mark_accepted,
    revoke_invitation,
    role_can_invite,
)
from app.services.license_service import _current_active_license
from app.services.storage_service import (
    StorageError,
    build_school_path,
    get_signed_url,
    upload_file,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/school/me", tags=["School Panel"])
public_router = APIRouter(prefix="/invitations", tags=["School Panel · public accept"])


# ============================================================================
# Authorization helpers · the entire router is gated by these
# ============================================================================


def _get_school_for_caller(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> tuple[School, User]:
    """Dependency: returns (school, user) ensuring isolation."""
    if current_user.role not in (
        UserRole.SCHOOL_ADMIN,
        UserRole.PSYCHOLOGIST,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only school staff can access the panel.",
        )
    if not current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not bound to a school. Contact a super_admin.",
        )
    school = db.query(School).filter(School.id == current_user.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    if school.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El colegio está archivado.",
        )
    return school, current_user


def _is_school_admin(user: User) -> bool:
    return user.role in (UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN)


def _is_psychologist(user: User) -> bool:
    return user.role == UserRole.PSYCHOLOGIST


# ============================================================================
# School summary
# ============================================================================


@router.get(
    "",
    response_model=SchoolWithStats,
    summary="GH-S9-BE-01 · school summary + counts (caller's school).",
)
def get_my_school(
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
):
    school, _user = bundle
    students = (
        db.query(func.count(User.id))
        .filter(User.school_id == school.id, User.role == UserRole.STUDENT)
        .scalar()
        or 0
    )
    psychs = (
        db.query(func.count(User.id))
        .filter(User.school_id == school.id, User.role == UserRole.PSYCHOLOGIST)
        .scalar()
        or 0
    )
    lic = _current_active_license(db, school.id)
    payload = SchoolResponse.model_validate(school).model_dump()
    payload.update(
        students_count=int(students),
        psychologists_count=int(psychs),
        license_tier=lic.tier if lic else None,
        license_seats=lic.seats if lic else None,
        license_expires_at=lic.expires_at if lic else school.license_expires_at,
    )
    return SchoolWithStats(**payload)


# ============================================================================
# Dashboard · GH-S9-BE-01
# ============================================================================


@router.get(
    "/dashboard",
    response_model=SchoolDashboardKpis,
    summary="GH-S9-BE-01 · KPIs of the school cohort (cached 5 min)",
)
def get_dashboard(
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
    refresh: bool = Query(False, description="Bypass 5-min cache."),
):
    school, _user = bundle
    return school_panel_service.build_dashboard_kpis(db, school, refresh=refresh)


# ============================================================================
# Cohort reports · GH-S9-BE-05
# ============================================================================


@router.get(
    "/reports",
    response_model=CohortReportsResponse,
    summary="GH-S9-BE-05 · cohort reports (distribution + at-risk students)",
)
def get_reports(
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
    refresh: bool = Query(False),
):
    school, _user = bundle
    return school_panel_service.build_cohort_reports(db, school, refresh=refresh)


# ============================================================================
# Students list + filters · GH-S9-BE-02
# ============================================================================


def _apply_filters(
    q,
    *,
    search: Optional[str],
    invited_since: Optional[datetime],
    invited_until: Optional[datetime],
):
    if search:
        like = f"%{search.strip().lower()}%"
        q = q.filter(or_(func.lower(User.email).like(like), func.lower(func.coalesce(User.name, '')).like(like)))
    if invited_since:
        q = q.filter(User.created_at >= invited_since)
    if invited_until:
        q = q.filter(User.created_at <= invited_until)
    return q


def _students_filter_pipeline(
    db: DBSession,
    school_id: UUID,
    *,
    search: Optional[str],
    invited_since: Optional[datetime],
    invited_until: Optional[datetime],
    journey_status: Optional[str],
    min_tests: Optional[int],
    page: int,
    page_size: int,
) -> tuple[List[User], dict, int]:
    """Returns (page_users, signals_map, total)."""
    # We can't filter by journey_status / min_tests at SQL level cleanly because
    # both are derived. So we fetch ALL students of the school (cap at 5000),
    # compute signals, filter in Python, and paginate.
    base = (
        db.query(User)
        .filter(User.school_id == school_id, User.role == UserRole.STUDENT)
    )
    base = _apply_filters(
        base, search=search, invited_since=invited_since, invited_until=invited_until
    )
    students = base.order_by(User.created_at.desc()).limit(5000).all()

    user_ids = [u.id for u in students]
    signals = school_panel_service._batch_student_signals(db, school_id, user_ids)

    # apply derived filters
    rows: List[StudentRow] = []
    user_map = {u.id: u for u in students}
    now = datetime.utcnow()
    for u in students:
        sig = signals.get(u.id, {})
        if min_tests is not None and sig.get("tests_completed_count", 0) < min_tests:
            continue
        row = school_panel_service.build_student_row(u, sig, now=now)
        if journey_status and row.journey_status != journey_status:
            continue
        rows.append(row)

    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    page_users = [user_map[r.id] for r in page_rows]
    return page_users, {u.id: signals.get(u.id, {}) for u in page_users}, total


@router.get(
    "/students",
    response_model=StudentListResponse,
    summary="GH-S9-BE-02 · paginated cohort with filters",
)
def list_students(
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: Optional[str] = Query(None, max_length=200),
    journey_status: Optional[str] = Query(
        None, description="no_iniciado | en_progreso | completado | perdido"
    ),
    min_tests: Optional[int] = Query(None, ge=0, le=10),
    invited_since: Optional[datetime] = Query(None),
    invited_until: Optional[datetime] = Query(None),
):
    school, _user = bundle
    page_users, signals, total = _students_filter_pipeline(
        db,
        school.id,
        search=search,
        invited_since=invited_since,
        invited_until=invited_until,
        journey_status=journey_status,
        min_tests=min_tests,
        page=page,
        page_size=page_size,
    )
    items = [
        school_panel_service.build_student_row(u, signals.get(u.id, {}))
        for u in page_users
    ]
    total_pages = max(1, math.ceil(total / page_size)) if total else 0
    return StudentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ============================================================================
# Students CSV export · GH-S9-BE-06
# ============================================================================


@router.get(
    "/students/export.csv",
    summary="GH-S9-BE-06 · CSV export of the cohort (filters honored)",
)
def export_students_csv(
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
    request: Request = None,
    search: Optional[str] = Query(None, max_length=200),
    journey_status: Optional[str] = Query(None),
    min_tests: Optional[int] = Query(None, ge=0, le=10),
    invited_since: Optional[datetime] = Query(None),
    invited_until: Optional[datetime] = Query(None),
):
    school, user = bundle

    # large export · single page of 5000 max
    page_users, signals, _total = _students_filter_pipeline(
        db,
        school.id,
        search=search,
        invited_since=invited_since,
        invited_until=invited_until,
        journey_status=journey_status,
        min_tests=min_tests,
        page=1,
        page_size=5000,
    )

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "user_id",
            "email",
            "name",
            "journey_status",
            "completion_pct",
            "tests_completed",
            "has_consolidated_profile",
            "last_active_at",
            "invited_at",
        ]
    )
    for u in page_users:
        sig = signals.get(u.id, {})
        row = school_panel_service.build_student_row(u, sig)
        w.writerow(
            [
                str(row.id),
                row.email,
                row.name or "",
                row.journey_status,
                row.completion_pct,
                row.tests_completed_count,
                "1" if row.has_consolidated_profile else "0",
                row.last_active_at.isoformat() if row.last_active_at else "",
                row.invited_at.isoformat() if row.invited_at else "",
            ]
        )

    buf.seek(0)
    fname = f"grasshopper-{school.slug}-cohort-{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ============================================================================
# Student detail · GH-S9-BE-03
# ============================================================================


@router.get(
    "/students/{user_id}",
    response_model=StudentDetailResponse,
    summary="GH-S9-BE-03 · 360 view (psychologist read-only)",
)
def get_student_detail(
    user_id: UUID,
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
):
    school, caller = bundle

    student = (
        db.query(User)
        .filter(User.id == user_id, User.role == UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    # IDOR guard · belong to the same school
    if str(student.school_id) != str(school.id):
        # do not leak existence of cross-school student
        raise HTTPException(status_code=404, detail="Student not found.")

    return school_panel_service.build_student_detail(
        db,
        student,
        read_only_for_caller=_is_psychologist(caller),
    )


# ============================================================================
# Logo upload · GH-S9-BE-07
# ============================================================================


_ALLOWED_LOGO_MIME = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
_LOGO_MAX_MB = 2


@router.post(
    "/logo",
    response_model=SchoolResponse,
    summary="GH-S9-BE-07 · upload school logo (school_admin only)",
)
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
):
    school, caller = bundle
    if not _is_school_admin(caller):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only school_admin can upload the school logo.",
        )

    if file.content_type not in _ALLOWED_LOGO_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type: {file.content_type}.",
        )

    data = await file.read()
    if len(data) > _LOGO_MAX_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Logo exceeds {_LOGO_MAX_MB}MB.",
        )

    # GH-S11 hardening · magic-byte verification + SVG sanitization (S9 gap)
    from app.core.file_validation import validate_image_bytes

    fv = validate_image_bytes(
        data,
        allow_svg=True,
        max_bytes=_LOGO_MAX_MB * 1024 * 1024,
    )
    if not fv.ok:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File signature invalid · {fv.reason}",
        )

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", file.filename or "logo")
    path = build_school_path(school.id, "logos", f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{safe_name}")
    try:
        obj = upload_file(path, data, content_type=file.content_type, max_size_mb=_LOGO_MAX_MB)
    except StorageError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")

    school.logo_url = obj.path  # store the relative path; signed URLs minted on read
    school.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(school)

    log_action(
        db,
        user=caller,
        action="school.upload_logo",
        resource_type="school",
        resource_id=str(school.id),
        payload={"path": obj.path, "content_type": file.content_type, "size_bytes": len(data)},
        request=request,
    )
    school_panel_service.invalidate_cache(school.id)

    return SchoolResponse.model_validate(school)


# ============================================================================
# Invitations · CRUD + accept (public)
# ============================================================================


def _build_accept_url(token: str, request: Optional[Request]) -> str:
    """Compose the accept URL using a validated request Origin.

    GH-F1-SECURITY · Tarea 3 · delega en app.core.url_safety.build_safe_url
    para la validación contra la whitelist (lógica centralizada; evita
    duplicación con el helper de /forgot-password).

    Fallback order (gestionado en build_safe_url):
      1. request.headers["origin"] si está en settings.allowed_origins_set
      2. settings.frontend_base_url  (URL canónica prod · siempre segura)
      3. "http://localhost:5173"      (dev fallback cuando no hay request)
    """
    origin_header = request.headers.get("origin") if request else None
    return build_safe_url(origin_header=origin_header, path=f"/invite/{token}")


def _to_invitation_response(
    inv: Invitation,
    *,
    inviter_email: Optional[str] = None,
    request: Optional[Request] = None,
    include_accept_url: bool = False,
) -> InvitationResponse:
    return InvitationResponse(
        id=inv.id,
        school_id=inv.school_id,
        email=inv.email,
        role=inv.role,  # type: ignore[arg-type]
        status=inv.status,  # type: ignore[arg-type]
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        invited_by_user_id=inv.invited_by_user_id,
        invited_by_email=inviter_email,
        accept_url=_build_accept_url(inv.token, request) if include_accept_url else None,
        created_at=inv.created_at,
    )


@router.get(
    "/invitations",
    response_model=InvitationListResponse,
    summary="GH-S9 · list invitations (own school)",
)
def list_invitations(
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    role_filter: Optional[str] = Query(None, alias="role"),
):
    school, _user = bundle
    q = db.query(Invitation).filter(Invitation.school_id == school.id)
    if status_filter:
        q = q.filter(Invitation.status == status_filter)
    if role_filter:
        q = q.filter(Invitation.role == role_filter)
    total = q.count()
    rows = (
        q.order_by(Invitation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    inviter_ids = {r.invited_by_user_id for r in rows if r.invited_by_user_id}
    email_map: dict = {}
    if inviter_ids:
        for u in db.query(User.id, User.email).filter(User.id.in_(inviter_ids)).all():
            email_map[u.id] = u.email

    items = [
        _to_invitation_response(r, inviter_email=email_map.get(r.invited_by_user_id))
        for r in rows
    ]
    total_pages = max(1, math.ceil(total / page_size)) if total else 0
    return InvitationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S9 · create invitation (school_admin or psychologist)",
)
def post_invitation(
    payload: InvitationCreate,
    request: Request,
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
):
    school, caller = bundle

    if not role_can_invite(caller.role, payload.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role ({caller.role.value}) cannot invite '{payload.role}'.",
        )

    # avoid creating an invitation for an email that already belongs to the school
    existing_user = (
        db.query(User).filter(User.email == payload.email.lower()).first()
    )
    if existing_user and str(existing_user.school_id) == str(school.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That user already belongs to your school.",
        )

    inv = create_invitation(
        db,
        school=school,
        email=payload.email,
        role=payload.role,
        invited_by=caller,
        expires_in_days=payload.expires_in_days or 14,
    )

    log_action(
        db,
        user=caller,
        action="invitation.create",
        resource_type="invitation",
        resource_id=str(inv.id),
        payload={
            "school_id": str(school.id),
            "role": inv.role,
            "email_domain": (inv.email.split("@", 1)[1] if "@" in inv.email else None),
        },
        request=request,
    )

    # Best-effort email · stub if Resend not configured (S7 pattern).
    # QA-AUD-001 fix: send_email helper now exists in email_service.
    # QA-AUD-036 mitigation: log uses inv.id (not token prefix) on failure.
    try:
        from app.services.email_service import send_email

        accept_url = _build_accept_url(inv.token, request)
        result = send_email(
            to=inv.email,
            subject=f"Invitación a {school.name} · Grasshopper",
            html_body=f"""
            <p>Hola,</p>
            <p>El equipo de <b>{school.name}</b> te invita a unirte a Grasshopper como
            <b>{inv.role}</b>.</p>
            <p>Para activar tu cuenta entra a este enlace antes de
            {inv.expires_at.strftime('%Y-%m-%d')}:</p>
            <p><a href="{accept_url}">{accept_url}</a></p>
            <p>Si no esperabas este correo, puedes ignorarlo.</p>
            """,
            text_body=f"Invitación a {school.name}. Activa tu cuenta: {accept_url}",
        )
        if not result.delivered:
            logger.info(
                "invitation.email_not_delivered inv_id=%s school_id=%s provider=%s reason=%s",
                inv.id,
                inv.school_id,
                result.provider,
                result.reason,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "invitation.email_send_failed inv_id=%s school_id=%s err=%s",
            inv.id,
            inv.school_id,
            exc,
        )

    school_panel_service.invalidate_cache(school.id)

    return _to_invitation_response(inv, inviter_email=caller.email, request=request, include_accept_url=True)


@router.delete(
    "/invitations/{invitation_id}",
    response_model=InvitationResponse,
    summary="GH-S9 · revoke a pending invitation",
)
def delete_invitation(
    invitation_id: UUID,
    request: Request,
    bundle: tuple = Depends(_get_school_for_caller),
    db: DBSession = Depends(get_db),
):
    school, caller = bundle
    inv = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if not inv or str(inv.school_id) != str(school.id):
        raise HTTPException(status_code=404, detail="Invitation not found.")

    # psychologist can only revoke invitations they themselves issued for students
    if caller.role == UserRole.PSYCHOLOGIST:
        if inv.role != "student" or str(inv.invited_by_user_id) != str(caller.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Psychologists can only revoke their own student invitations.",
            )

    inv = revoke_invitation(db, inv)

    log_action(
        db,
        user=caller,
        action="invitation.revoke",
        resource_type="invitation",
        resource_id=str(inv.id),
        payload={"school_id": str(school.id), "role": inv.role},
        request=request,
    )

    return _to_invitation_response(inv, inviter_email=caller.email)


# ============================================================================
# Public accept · POST /invitations/{token}/accept (no auth)
# ============================================================================


@public_router.get(
    "/{token}",
    summary="GH-S9 · public · invitation lookup (returns school name + role)",
)
def get_invitation_by_token(token: str, db: DBSession = Depends(get_db)):
    inv, reason = lookup_token(db, token)
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if reason != "ok":
        # do not leak details · provide enough to render an error page
        return {
            "status": reason,
            "school_id": str(inv.school_id),
            "role": inv.role,
            "email": inv.email,
        }
    school = db.query(School).filter(School.id == inv.school_id).first()
    return {
        "status": "ok",
        "school_id": str(inv.school_id),
        "school_name": school.name if school else None,
        "role": inv.role,
        "email": inv.email,
        "expires_at": inv.expires_at.isoformat(),
    }


@public_router.post(
    "/{token}/accept",
    response_model=InvitationAcceptResponse,
    summary="GH-S9 · public · accept invitation and create user",
    dependencies=[Depends(_rate_limit_invitation_accept)],
)
def accept_invitation(
    token: str,
    payload: InvitationAccept,
    request: Request,
    db: DBSession = Depends(get_db),
):
    inv, reason = lookup_token(db, token)
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if reason != "ok":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Invitation is {reason}.",
        )

    school = db.query(School).filter(School.id == inv.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    if school.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El colegio está archivado.",
        )

    # license + seats: only for student invitations
    if inv.role == "student":
        from app.services.license_service import assert_can_register_student
        assert_can_register_student(db, school.id)

    # if user already exists with same email, attach to school (only if not yet linked)
    existing = db.query(User).filter(User.email == inv.email.lower()).first()
    if existing:
        if existing.school_id and str(existing.school_id) != str(school.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That email already belongs to a different school.",
            )
        existing.school_id = school.id
        # Promote role only if it represents an upgrade vs current
        target_role = UserRole(inv.role)
        if existing.role == UserRole.STUDENT and target_role in (
            UserRole.PSYCHOLOGIST,
            UserRole.SCHOOL_ADMIN,
        ):
            existing.role = target_role
        # always update password to the freshly chosen one
        existing.hashed_password = get_password_hash(payload.password)
        if payload.name and not existing.name:
            existing.name = payload.name
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        user = existing
    else:
        target_role = UserRole(inv.role)
        user = User(
            email=inv.email.lower(),
            hashed_password=get_password_hash(payload.password),
            name=payload.name,
            role=target_role,
            school_id=school.id,
            onboarding_status=(
                OnboardingStatus.COMPLETED
                if target_role in (UserRole.PSYCHOLOGIST, UserRole.SCHOOL_ADMIN)
                else OnboardingStatus.NOT_STARTED
            ),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    mark_accepted(db, inv, user)

    log_action(
        db,
        user=user,
        action="invitation.accept",
        resource_type="invitation",
        resource_id=str(inv.id),
        payload={"school_id": str(school.id), "role": inv.role},
        request=request,
    )
    school_panel_service.invalidate_cache(school.id)

    access_token = create_access_token(data={"sub": str(user.id)})
    return InvitationAcceptResponse(
        access_token=access_token,
        user_id=user.id,
        role=inv.role,  # type: ignore[arg-type]
        school_id=school.id,
        email=user.email,
    )
