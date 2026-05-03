"""Schools router · GH-S2-BE-08 + GH-S8-BE-01/02/04 · CRUD completo + licencias.

Endpoints:

- POST   /schools                   · super_admin · crea colegio (auto-slug)
- GET    /schools                   · super_admin · lista paginada con stats
                                      · school_admin/psychologist · solo el suyo
- GET    /schools/{id}              · super_admin · cualquiera
                                      · school_admin/psychologist · solo el suyo
- PATCH  /schools/{id}              · super_admin · update parcial
- DELETE /schools/{id}              · super_admin · soft delete (D-017)
- POST   /schools/{id}/restore      · super_admin · revierte archive
- GET    /schools/{id}/users        · super_admin o school_admin (su colegio)
- POST   /schools/{id}/licenses     · super_admin · alta de licencia
- GET    /schools/{id}/licenses     · super_admin · histórico
                                      · school_admin · su colegio
- GET    /schools/{id}/license/usage · super_admin o school_admin (su colegio)

Licenses individuales viven también en `/licenses/{id}` (PATCH) en
`app/api/v1/licenses.py`.

Permisos:
  - Super admin: acceso global.
  - School admin / psychologist: solo el `school_id` que figura en su token.
  - Student / anónimo: 403.

Audit: cada mutación llama a `audit_service.log_action`.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    AuditLog,
    License,
    LicenseStatus,
    LicenseTier,
    School,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.license import (
    LicenseCreate,
    LicenseResponse,
    LicenseUsage,
)
from app.schemas.school import (
    SchoolCreate,
    SchoolDetailResponse,
    SchoolListResponse,
    SchoolResponse,
    SchoolStudentsBreakdown,
    SchoolTeam,
    SchoolTeamMember,
    SchoolUpdate,
    SchoolUsageMetrics,
    SchoolWithStats,
)
from app.services.audit_service import log_action
from app.services.student_lead_scoring import (
    compute_school_usage_metrics,
    score_students_for_school,
    summarize_bands,
)


router = APIRouter(prefix="/schools", tags=["Schools"])


# ----------------------------- helpers -----------------------------

def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can manage schools.",
        )


def _ensure_super_or_own_school(user: User, school_id: UUID) -> None:
    if user.role == UserRole.SUPER_ADMIN:
        return
    if user.role in (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST):
        if str(user.school_id) == str(school_id):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden · cannot access schools other than your own.",
    )


def _slugify(value: str) -> str:
    """Best-effort slug from name. Keeps ASCII lowercase + hyphens."""
    norm = unicodedata.normalize("NFKD", value)
    norm = norm.encode("ascii", "ignore").decode("ascii")
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return norm or "school"


def _unique_slug(db: DBSession, base: str) -> str:
    """Ensure the slug is unique by suffixing -2, -3, ... if needed."""
    candidate = base
    n = 2
    while db.query(School.id).filter(School.slug == candidate).first():
        candidate = f"{base}-{n}"
        n += 1
        if n > 999:  # safety
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not generate unique slug.",
            )
    return candidate


def _current_license(db: DBSession, school_id: UUID) -> Optional[License]:
    """Return the latest active (non-expired) license, if any."""
    now = datetime.utcnow()
    return (
        db.query(License)
        .filter(
            License.school_id == school_id,
            License.status == LicenseStatus.ACTIVE.value,
            or_(License.expires_at.is_(None), License.expires_at > now),
        )
        .order_by(License.created_at.desc())
        .first()
    )


def _school_with_stats(db: DBSession, school: School) -> SchoolWithStats:
    students = (
        db.query(func.count(User.id))
        .filter(User.school_id == school.id, User.role == UserRole.STUDENT)
        .scalar()
        or 0
    )
    psychologists = (
        db.query(func.count(User.id))
        .filter(User.school_id == school.id, User.role == UserRole.PSYCHOLOGIST)
        .scalar()
        or 0
    )
    lic = _current_license(db, school.id)
    payload = SchoolResponse.model_validate(school).model_dump()
    payload.update(
        students_count=int(students),
        psychologists_count=int(psychologists),
        license_tier=lic.tier if lic else None,
        license_seats=lic.seats if lic else None,
        license_expires_at=lic.expires_at if lic else school.license_expires_at,
    )
    return SchoolWithStats(**payload)


# ----------------------------- CRUD schools -----------------------------

@router.post(
    "",
    response_model=SchoolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S8-BE-01 · create school (super_admin only)",
)
def create_school(
    payload: SchoolCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    raw_slug = payload.slug.strip().lower() if payload.slug else _slugify(payload.name)
    slug = _unique_slug(db, raw_slug)

    school = School(
        name=payload.name.strip(),
        slug=slug,
        logo_url=payload.logo_url,
        license_active=payload.license_active,
        license_expires_at=payload.license_expires_at,
        # Fiscal identity
        rut=payload.rut,
        razon_social=payload.razon_social,
        direccion_fiscal=payload.direccion_fiscal,
        tipo_persona=payload.tipo_persona,
        # Commercial contact
        commercial_contact_name=payload.commercial_contact_name,
        commercial_contact_role=payload.commercial_contact_role,
        commercial_contact_email=payload.commercial_contact_email,
        commercial_contact_phone=payload.commercial_contact_phone,
        # Academic contact
        academic_contact_name=payload.academic_contact_name,
        academic_contact_email=payload.academic_contact_email,
        academic_contact_phone=payload.academic_contact_phone,
        # Center metadata
        estimated_students=payload.estimated_students,
        city=payload.city,
        country=payload.country,
        timezone=payload.timezone,
        academic_year=payload.academic_year,
    )

    db.add(school)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A school with the same slug already exists.",
        )
    db.refresh(school)

    log_action(
        db,
        user=current_user,
        action="school.create",
        resource_type="school",
        resource_id=str(school.id),
        payload={"name": school.name, "slug": school.slug},
        request=request,
    )

    return SchoolResponse.model_validate(school)


@router.get(
    "",
    response_model=SchoolListResponse,
    summary="GH-S8-BE-01 · paginated list of schools (super_admin) · own school (school staff)",
)
def list_schools(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=200),
    include_archived: bool = Query(False),
):
    """Returns SchoolListResponse with pagination + per-row stats."""
    if current_user.role == UserRole.SUPER_ADMIN:
        q = db.query(School)
        if not include_archived:
            q = q.filter(School.archived_at.is_(None))
        if search:
            term = f"%{search.strip().lower()}%"
            q = q.filter(or_(func.lower(School.name).like(term), School.slug.like(term)))
        total = q.count()
        rows = (
            q.order_by(School.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    elif current_user.role in (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST):
        if not current_user.school_id:
            return SchoolListResponse(items=[], total=0, page=page, page_size=page_size, total_pages=0)
        row = db.query(School).filter(School.id == current_user.school_id).first()
        rows = [row] if row else []
        total = len(rows)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

    items = [_school_with_stats(db, r) for r in rows]
    total_pages = max(1, math.ceil(total / page_size)) if total else 0
    return SchoolListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{school_id}",
    response_model=SchoolWithStats,
    summary="Get school by id (with stats)",
)
def get_school(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")
    _ensure_super_or_own_school(current_user, school.id)
    return _school_with_stats(db, school)


@router.patch(
    "/{school_id}",
    response_model=SchoolResponse,
    summary="GH-S8-BE-01 · update school (super_admin only)",
)
def update_school(
    school_id: UUID,
    payload: SchoolUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    diff: dict = {}
    if payload.name is not None and payload.name.strip() != school.name:
        diff["name"] = {"from": school.name, "to": payload.name.strip()}
        school.name = payload.name.strip()
    if payload.slug is not None and payload.slug.lower() != school.slug:
        new_slug = payload.slug.strip().lower()
        # uniqueness check (avoid colliding with another school)
        clash = db.query(School.id).filter(School.slug == new_slug, School.id != school.id).first()
        if clash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A school with the same slug already exists.",
            )
        diff["slug"] = {"from": school.slug, "to": new_slug}
        school.slug = new_slug
    if payload.logo_url is not None and payload.logo_url != school.logo_url:
        diff["logo_url"] = True
        school.logo_url = payload.logo_url
    if payload.license_active is not None and payload.license_active != school.license_active:
        diff["license_active"] = {"from": school.license_active, "to": payload.license_active}
        school.license_active = payload.license_active
    if payload.license_expires_at is not None and payload.license_expires_at != school.license_expires_at:
        diff["license_expires_at"] = {"to": payload.license_expires_at.isoformat()}
        school.license_expires_at = payload.license_expires_at

    # Bloque A · Sprint super_admin fixes 2026-05-03 · fiscal + contactos + centro
    _EXTENDED_FIELDS = (
        "rut",
        "razon_social",
        "direccion_fiscal",
        "tipo_persona",
        "commercial_contact_name",
        "commercial_contact_role",
        "commercial_contact_email",
        "commercial_contact_phone",
        "academic_contact_name",
        "academic_contact_email",
        "academic_contact_phone",
        "estimated_students",
        "city",
        "country",
        "timezone",
        "academic_year",
    )
    for fname in _EXTENDED_FIELDS:
        new_value = getattr(payload, fname, None)
        if new_value is None:
            continue
        # EmailStr → str cast for storage comparison
        if hasattr(new_value, "lower") and not isinstance(new_value, str):
            new_value = str(new_value)
        current = getattr(school, fname)
        if new_value != current:
            diff[fname] = {"from": current, "to": new_value}
            setattr(school, fname, new_value)

    school.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(school)

    if diff:
        log_action(
            db,
            user=current_user,
            action="school.update",
            resource_type="school",
            resource_id=str(school.id),
            payload=diff,
            request=request,
        )

    return SchoolResponse.model_validate(school)


@router.delete(
    "/{school_id}",
    status_code=status.HTTP_200_OK,
    summary="GH-S8-BE-01 · soft-delete school (D-017 · sets archived_at)",
)
def archive_school(
    school_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")
    if school.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="School is already archived.",
        )

    school.archived_at = datetime.utcnow()
    school.license_active = False
    # cancel active licenses so the school cannot operate further
    for lic in db.query(License).filter(
        License.school_id == school.id,
        License.status == LicenseStatus.ACTIVE.value,
    ).all():
        lic.status = LicenseStatus.CANCELLED.value
        lic.updated_at = datetime.utcnow()
    db.commit()

    log_action(
        db,
        user=current_user,
        action="school.archive",
        resource_type="school",
        resource_id=str(school.id),
        payload={"slug": school.slug, "name": school.name},
        request=request,
    )

    return {"id": str(school.id), "archived_at": school.archived_at.isoformat()}


@router.post(
    "/{school_id}/restore",
    response_model=SchoolResponse,
    summary="GH-S8-BE-01 · undo archive (super_admin only)",
)
def restore_school(
    school_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")
    if school.archived_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="School is not archived.",
        )

    school.archived_at = None
    school.license_active = True
    db.commit()
    db.refresh(school)

    log_action(
        db,
        user=current_user,
        action="school.restore",
        resource_type="school",
        resource_id=str(school.id),
        request=request,
    )

    return SchoolResponse.model_validate(school)


# ----------------------------- school users -----------------------------

@router.get(
    "/{school_id}/users",
    summary="List school users (super_admin or that school's admin)",
)
def list_school_users(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    role: Optional[str] = Query(None, description="filter by role"),
):
    _ensure_super_or_own_school(current_user, school_id)

    q = db.query(User).filter(User.school_id == school_id)
    if role:
        try:
            q = q.filter(User.role == UserRole(role))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    users = q.order_by(User.created_at.desc()).all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "role": u.role.value if u.role else None,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


# ----------------------------- licenses -----------------------------

@router.post(
    "/{school_id}/licenses",
    response_model=LicenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S8-BE-04 · create license (super_admin only)",
)
def create_license(
    school_id: UUID,
    payload: LicenseCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    license_row = License(
        school_id=school.id,
        tier=payload.tier,
        seats=payload.seats,
        starts_at=payload.starts_at or datetime.utcnow(),
        expires_at=payload.expires_at,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(license_row)

    # Mirror to the legacy school.license_active flag while we keep both in sync
    if payload.status == LicenseStatus.ACTIVE.value:
        school.license_active = True
        school.license_expires_at = payload.expires_at

    db.commit()
    db.refresh(license_row)

    log_action(
        db,
        user=current_user,
        action="license.create",
        resource_type="license",
        resource_id=str(license_row.id),
        payload={
            "school_id": str(school.id),
            "tier": license_row.tier,
            "seats": license_row.seats,
            "expires_at": license_row.expires_at.isoformat() if license_row.expires_at else None,
        },
        request=request,
    )

    return LicenseResponse.model_validate(license_row)


@router.get(
    "/{school_id}/licenses",
    response_model=List[LicenseResponse],
    summary="GH-S8-BE-04 · list licenses for a school",
)
def list_licenses(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_or_own_school(current_user, school_id)
    rows = (
        db.query(License)
        .filter(License.school_id == school_id)
        .order_by(License.created_at.desc())
        .all()
    )
    return [LicenseResponse.model_validate(r) for r in rows]


@router.get(
    "/{school_id}/license/usage",
    response_model=LicenseUsage,
    summary="GH-S8-BE-05 · current license + seat usage",
)
def get_license_usage(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_or_own_school(current_user, school_id)

    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    lic = _current_license(db, school.id)
    seats = lic.seats if lic else 0
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
    seats_used = int(seats_used)
    is_expired = bool(lic and lic.expires_at and lic.expires_at <= datetime.utcnow())
    return LicenseUsage(
        license=LicenseResponse.model_validate(lic) if lic else None,
        seats=seats,
        seats_used=seats_used,
        seats_remaining=max(0, seats - seats_used),
        is_expired=is_expired,
        is_within_seats=(seats_used < seats) if seats else False,
    )


# ----------------------------- Bloque A · detail page endpoints -----------------------------


@router.get(
    "/{school_id}/detail",
    response_model=SchoolDetailResponse,
    summary="Bloque A · rich detail (Overview tab) · super_admin only",
)
def get_school_detail(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rich detail used by `SchoolDetailPage`.

    Combines `SchoolWithStats` + usage metrics + team list. The team
    breakdown excludes archived users. Metrics are computed in real-time;
    for portfolios > 100 students consider caching at the service layer.
    """
    _ensure_super_admin(current_user)
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    base = _school_with_stats(db, school).model_dump()

    metrics = SchoolUsageMetrics(**compute_school_usage_metrics(db, school.id))

    admins_q = (
        db.query(User)
        .filter(
            User.school_id == school.id,
            User.role == UserRole.SCHOOL_ADMIN,
        )
        .order_by(User.created_at.desc())
        .all()
    )
    psychologists_q = (
        db.query(User)
        .filter(
            User.school_id == school.id,
            User.role == UserRole.PSYCHOLOGIST,
        )
        .order_by(User.created_at.desc())
        .all()
    )

    def _to_member(u: User) -> SchoolTeamMember:
        return SchoolTeamMember(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role.value,
            is_active=bool(u.is_active),
            last_login_at=None,  # placeholder · last login tracking is BE-future
            created_at=u.created_at,
        )

    team = SchoolTeam(
        school_admins=[_to_member(u) for u in admins_q],
        psychologists=[_to_member(u) for u in psychologists_q],
    )

    return SchoolDetailResponse(**base, metrics=metrics, team=team)


@router.get(
    "/{school_id}/students",
    response_model=SchoolStudentsBreakdown,
    summary="Bloque A · list students with lead scoring (super_admin)",
)
def list_school_students_with_scores(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    band: Optional[str] = Query(None, pattern=r"^(hot|warm|cold)$"),
    limit: int = Query(200, ge=1, le=500),
):
    """Lead-quality scoring of students for the Alumnos tab.

    The scoring is deterministic (no LLM call) · see
    `app.services.student_lead_scoring`. Super_admin only · school_admin
    has its own `/schools/{id}/students` (different shape) under
    school_panel · no PII leak.
    """
    _ensure_super_admin(current_user)
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    rows = score_students_for_school(db, school.id, limit=limit)
    if band:
        rows = [r for r in rows if r.score_band == band]
    bands = summarize_bands(rows)
    return SchoolStudentsBreakdown(
        items=rows,
        total=len(rows),
        hot=bands["hot"],
        warm=bands["warm"],
        cold=bands["cold"],
    )


@router.get(
    "/{school_id}/team",
    response_model=SchoolTeam,
    summary="Bloque A · school team (admins + psychologists)",
)
def get_school_team(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_or_own_school(current_user, school_id)
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    admins_q = (
        db.query(User)
        .filter(
            User.school_id == school.id,
            User.role == UserRole.SCHOOL_ADMIN,
        )
        .order_by(User.created_at.desc())
        .all()
    )
    psychologists_q = (
        db.query(User)
        .filter(
            User.school_id == school.id,
            User.role == UserRole.PSYCHOLOGIST,
        )
        .order_by(User.created_at.desc())
        .all()
    )

    def _to_member(u: User) -> SchoolTeamMember:
        return SchoolTeamMember(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role.value,
            is_active=bool(u.is_active),
            last_login_at=None,
            created_at=u.created_at,
        )

    return SchoolTeam(
        school_admins=[_to_member(u) for u in admins_q],
        psychologists=[_to_member(u) for u in psychologists_q],
    )


@router.get(
    "/{school_id}/metrics",
    response_model=SchoolUsageMetrics,
    summary="Bloque A · usage + health metrics (super_admin or own school)",
)
def get_school_metrics(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_or_own_school(current_user, school_id)
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")
    data = compute_school_usage_metrics(db, school.id)
    return SchoolUsageMetrics(**data)
