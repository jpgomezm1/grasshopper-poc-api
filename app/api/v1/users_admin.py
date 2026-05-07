"""Super-admin global user CRUD + lifecycle + bulk + impersonation.

GH-SUPERADMIN-EXPERIENCE · 2026-05-05 · Bloques A · B · E · F.

All endpoints require role=super_admin. School-scoped admins (school_admin,
psychologist) are blocked: those flows live in /v1/school-admin/* already.

Audit log: every mutation calls `log_action`. Never logs plaintext passwords
(reset returns the temp password ONCE in the response, never persisted in
audit payload).

Security review (gh-security-reviewer):
  - reset password: temp generated server-side · response carries it once ·
    NOT in audit payload · NOT in logger output
  - suspend: stamps `suspended_at` (decoupled from is_active) · sessions are
    rejected at next request because get_current_user re-reads the user
  - impersonation: actor MUST be super_admin · target MUST NOT be · single
    active session per actor · banner forced via /me endpoint flag · audit
    on start, stop, AND every action while impersonating (caller responsibility)
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import List, Optional, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user, get_password_hash, create_access_token
from app.db.database import get_db
from app.db.models import (
    AuditLog,
    ImpersonationScope,
    ImpersonationSession,
    School,
    User,
    UserRole,
    VocationalTestResult,
    JournalEntry,
    Route,
    ProfileVersion,
)
from app.services.audit_service import log_action


router = APIRouter(prefix="/admin", tags=["Admin · Users"])


# --------------------------------------------------------------------------- #
# Guards                                                                      #
# --------------------------------------------------------------------------- #

def _require_super_admin(user: User) -> User:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · super_admin only",
        )
    return user


def _generate_temp_password(length: int = 14) -> str:
    """Cryptographically random temp password · returned ONCE in response."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# --------------------------------------------------------------------------- #
# Schemas                                                                     #
# --------------------------------------------------------------------------- #

class AdminUserOut(BaseModel):
    id: UUID
    email: str
    name: Optional[str] = None
    role: UserRole
    school_id: Optional[UUID] = None
    school_name: Optional[str] = None
    is_active: bool
    suspended_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    created_by_user_id: Optional[UUID] = None

    model_config = {"from_attributes": True}


class AdminUserListResponse(BaseModel):
    items: List[AdminUserOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminUserCreateIn(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    role: UserRole
    school_id: Optional[UUID] = None
    password: Optional[str] = Field(
        None,
        description="Optional · if omitted a temp password is generated and returned",
    )


class AdminUserCreateOut(BaseModel):
    user: AdminUserOut
    temp_password: Optional[str] = Field(
        None,
        description="Returned ONCE if password was auto-generated · save it now",
    )


class AdminUserUpdateIn(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    role: Optional[UserRole] = None
    school_id: Optional[UUID] = None


class AdminPasswordResetOut(BaseModel):
    user_id: UUID
    temp_password: str = Field(..., description="One-time · save it now")
    sent_via_email: bool = False


class AdminBulkMoveSchoolIn(BaseModel):
    user_ids: List[UUID] = Field(..., min_length=1, max_length=500)
    target_school_id: UUID


class AdminBulkResetJourneyIn(BaseModel):
    user_ids: List[UUID] = Field(..., min_length=1, max_length=500)


class AdminBulkMergeIn(BaseModel):
    keep_user_id: UUID
    merge_user_ids: List[UUID] = Field(..., min_length=1, max_length=20)


class AdminBulkDeleteIn(BaseModel):
    user_ids: List[UUID] = Field(..., min_length=1, max_length=500)


class AdminBulkResultOut(BaseModel):
    affected: int
    skipped: int
    errors: List[str] = Field(default_factory=list)


class ImpersonationStartIn(BaseModel):
    scope: Literal["read_only", "read_write"] = "read_only"


class ImpersonationStartOut(BaseModel):
    session_id: UUID
    token: str
    target_user: AdminUserOut
    scope: str
    expires_at: datetime


# --------------------------------------------------------------------------- #
# Bloque A · global user CRUD                                                 #
# --------------------------------------------------------------------------- #

def _to_admin_user(u: User, school_name_map: Optional[dict] = None) -> AdminUserOut:
    return AdminUserOut(
        id=u.id,
        email=u.email,
        name=u.name,
        role=u.role,
        school_id=u.school_id,
        school_name=(school_name_map or {}).get(u.school_id) if u.school_id else None,
        is_active=u.is_active,
        suspended_at=u.suspended_at,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
        created_by_user_id=u.created_by_user_id,
    )


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="GH-SUPERADMIN · Bloque A · paginated user list",
)
def list_users(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    role: Optional[UserRole] = None,
    school_id: Optional[UUID] = None,
    status_filter: Optional[Literal["active", "suspended", "inactive"]] = Query(None, alias="status"),
    q: Optional[str] = Query(None, description="Search by email or name"),
):
    _require_super_admin(current_user)
    qry = db.query(User)
    if role is not None:
        qry = qry.filter(User.role == role)
    if school_id is not None:
        qry = qry.filter(User.school_id == school_id)
    if status_filter == "suspended":
        qry = qry.filter(User.suspended_at.isnot(None))
    elif status_filter == "inactive":
        qry = qry.filter(User.is_active == False)  # noqa: E712
    elif status_filter == "active":
        qry = qry.filter(User.is_active == True, User.suspended_at.is_(None))  # noqa: E712
    if q:
        like = f"%{q.lower()}%"
        qry = qry.filter(or_(func.lower(User.email).like(like), func.lower(User.name).like(like)))

    total = qry.count()
    rows = (
        qry.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    school_ids = {r.school_id for r in rows if r.school_id}
    name_map = {}
    if school_ids:
        for sid, name in db.query(School.id, School.name).filter(School.id.in_(school_ids)).all():
            name_map[sid] = name
    items = [_to_admin_user(r, name_map) for r in rows]
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return AdminUserListResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserOut,
    summary="GH-SUPERADMIN · Bloque A · user detail",
)
def get_user(
    user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    name_map = {}
    if u.school_id:
        s = db.query(School).filter(School.id == u.school_id).first()
        if s:
            name_map[s.id] = s.name
    return _to_admin_user(u, name_map)


@router.post(
    "/users",
    response_model=AdminUserCreateOut,
    status_code=status.HTTP_201_CREATED,
    summary="GH-SUPERADMIN · Bloque A · create user (any role)",
)
def create_user(
    payload: AdminUserCreateIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    email_lower = payload.email.lower()
    if db.query(User).filter(User.email == email_lower).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    if payload.school_id:
        school = db.query(School).filter(School.id == payload.school_id).first()
        if not school:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "School not found")

    temp_password = payload.password or _generate_temp_password()
    hashed = get_password_hash(temp_password)

    user = User(
        email=email_lower,
        hashed_password=hashed,
        name=payload.name,
        role=payload.role,
        school_id=payload.school_id,
        created_by_user_id=current_user.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(
        db,
        user=current_user,
        action="user.admin_create",
        resource_type="user",
        resource_id=str(user.id),
        payload={
            "email": email_lower,
            "role": payload.role.value,
            "school_id": str(payload.school_id) if payload.school_id else None,
            # NEVER include temp_password in payload
        },
        request=request,
    )

    return AdminUserCreateOut(
        user=_to_admin_user(user),
        # only return temp_password if we generated it
        temp_password=temp_password if not payload.password else None,
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    summary="GH-SUPERADMIN · Bloque A · update user",
)
def update_user(
    user_id: UUID,
    payload: AdminUserUpdateIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    changes: dict = {}
    if payload.email is not None:
        new_email = payload.email.lower()
        if new_email != u.email:
            if db.query(User).filter(User.email == new_email).first():
                raise HTTPException(status.HTTP_409_CONFLICT, "Email already taken")
            changes["email"] = {"old": u.email, "new": new_email}
            u.email = new_email
    if payload.name is not None and payload.name != u.name:
        changes["name"] = {"old": u.name, "new": payload.name}
        u.name = payload.name
    if payload.role is not None and payload.role != u.role:
        # Soft rule: do NOT allow demoting another super_admin via PATCH
        if u.role == UserRole.SUPER_ADMIN and u.id != current_user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot change role of another super_admin")
        changes["role"] = {"old": u.role.value, "new": payload.role.value}
        u.role = payload.role
    if payload.school_id is not None and payload.school_id != u.school_id:
        if payload.school_id and not db.query(School).filter(School.id == payload.school_id).first():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "School not found")
        changes["school_id"] = {
            "old": str(u.school_id) if u.school_id else None,
            "new": str(payload.school_id),
        }
        u.school_id = payload.school_id

    if changes:
        u.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(u)
        log_action(
            db,
            user=current_user,
            action="user.admin_update",
            resource_type="user",
            resource_id=str(u.id),
            payload={"changes": changes},
            request=request,
        )

    return _to_admin_user(u)


@router.post(
    "/users/{user_id}/suspend",
    response_model=AdminUserOut,
    summary="GH-SUPERADMIN · Bloque A · suspend user (soft)",
)
def suspend_user(
    user_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    reason: Optional[str] = Query(None, max_length=500),
):
    _require_super_admin(current_user)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if u.id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot suspend yourself")
    if u.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot suspend another super_admin")

    if u.suspended_at is None:
        u.suspended_at = datetime.utcnow()
        db.commit()
        db.refresh(u)
        log_action(
            db,
            user=current_user,
            action="user.suspend",
            resource_type="user",
            resource_id=str(u.id),
            payload={"reason": reason},
            request=request,
        )
    return _to_admin_user(u)


@router.post(
    "/users/{user_id}/reactivate",
    response_model=AdminUserOut,
    summary="GH-SUPERADMIN · Bloque A · reactivate suspended user",
)
def reactivate_user(
    user_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if u.suspended_at is not None or not u.is_active:
        u.suspended_at = None
        u.is_active = True
        db.commit()
        db.refresh(u)
        log_action(
            db,
            user=current_user,
            action="user.reactivate",
            resource_type="user",
            resource_id=str(u.id),
            request=request,
        )
    return _to_admin_user(u)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminPasswordResetOut,
    summary="GH-SUPERADMIN · Bloque A · reset password (returns temp password ONCE)",
)
def reset_user_password(
    user_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate new temp password · return it ONCE in response · NEVER log plaintext.

    Email send is best-effort: if SMTP fails or is not configured, we still
    return the temp password to the super_admin with `sent_via_email=False` so
    they can copy/paste manually. The audit log records the reset event but
    NEVER the password.
    """
    _require_super_admin(current_user)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    temp_password = _generate_temp_password()
    u.hashed_password = get_password_hash(temp_password)
    # Invalidate any pending recovery tokens
    u.password_reset_token = None
    u.password_reset_expires = None
    db.commit()

    sent_via_email = False
    try:
        from app.services.email_service import send_password_reset_email  # type: ignore
        send_password_reset_email(u.email, temp_password)
        sent_via_email = True
    except Exception:
        sent_via_email = False

    log_action(
        db,
        user=current_user,
        action="user.password_reset",
        resource_type="user",
        resource_id=str(u.id),
        payload={"sent_via_email": sent_via_email},  # NEVER include temp_password
        request=request,
    )
    return AdminPasswordResetOut(
        user_id=u.id, temp_password=temp_password, sent_via_email=sent_via_email
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="GH-SUPERADMIN · Bloque A · soft delete user",
)
def delete_user(
    user_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if u.id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete yourself")
    if u.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot delete another super_admin")

    # Soft delete: keep row + relations · just block login
    u.is_active = False
    u.suspended_at = u.suspended_at or datetime.utcnow()
    db.commit()
    log_action(
        db,
        user=current_user,
        action="user.admin_delete",
        resource_type="user",
        resource_id=str(u.id),
        request=request,
    )


# --------------------------------------------------------------------------- #
# Bloque F · bulk operations                                                  #
# --------------------------------------------------------------------------- #

def _resolve_students(db: DBSession, user_ids: List[UUID]) -> List[User]:
    rows = db.query(User).filter(User.id.in_(user_ids)).all()
    return rows


@router.post(
    "/users/bulk/move-school",
    response_model=AdminBulkResultOut,
    summary="GH-SUPERADMIN · Bloque F · bulk move students to another school",
)
def bulk_move_school(
    payload: AdminBulkMoveSchoolIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    target = db.query(School).filter(School.id == payload.target_school_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target school not found")

    rows = _resolve_students(db, payload.user_ids)
    affected = 0
    skipped = 0
    errors: List[str] = []
    for u in rows:
        if u.role != UserRole.STUDENT:
            skipped += 1
            errors.append(f"{u.id} · not a student (skipped)")
            continue
        old_school = u.school_id
        u.school_id = target.id
        log_action(
            db,
            user=current_user,
            action="user.bulk_move_school",
            resource_type="user",
            resource_id=str(u.id),
            payload={"old_school_id": str(old_school) if old_school else None, "new_school_id": str(target.id)},
            request=request,
            commit=False,
        )
        affected += 1
    skipped += len(payload.user_ids) - len(rows)
    db.commit()
    return AdminBulkResultOut(affected=affected, skipped=skipped, errors=errors)


@router.post(
    "/users/bulk/reset-journey",
    response_model=AdminBulkResultOut,
    summary="GH-SUPERADMIN · Bloque F · wipe student journey state",
)
def bulk_reset_journey(
    payload: AdminBulkResetJourneyIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    rows = _resolve_students(db, payload.user_ids)
    affected = 0
    skipped = 0
    errors: List[str] = []
    for u in rows:
        if u.role != UserRole.STUDENT:
            skipped += 1
            errors.append(f"{u.id} · not a student (skipped)")
            continue
        # Clear journey artifacts; keep auth + school link.
        db.query(VocationalTestResult).filter(VocationalTestResult.user_id == u.id).delete(synchronize_session=False)
        db.query(JournalEntry).filter(JournalEntry.user_id == u.id).delete(synchronize_session=False)
        db.query(Route).filter(Route.user_id == u.id).delete(synchronize_session=False)
        db.query(ProfileVersion).filter(ProfileVersion.user_id == u.id).delete(synchronize_session=False)
        u.onboarding_answers = {}
        u.ai_analysis_cache = None
        u.ai_analysis_cached_at = None
        log_action(
            db,
            user=current_user,
            action="user.bulk_reset_journey",
            resource_type="user",
            resource_id=str(u.id),
            request=request,
            commit=False,
        )
        affected += 1
    skipped += len(payload.user_ids) - len(rows)
    db.commit()
    return AdminBulkResultOut(affected=affected, skipped=skipped, errors=errors)


@router.post(
    "/users/bulk/merge",
    response_model=AdminBulkResultOut,
    summary="GH-SUPERADMIN · Bloque F · merge duplicate students into one",
)
def bulk_merge(
    payload: AdminBulkMergeIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Conservative merge · only moves journey-related rows; soft-deletes the
    duplicates instead of removing FK targets to avoid surprises in the audit
    trail. School & role of `keep_user_id` are preserved.
    """
    _require_super_admin(current_user)
    keeper = db.query(User).filter(User.id == payload.keep_user_id).first()
    if not keeper:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "keep_user_id not found")
    if keeper.role != UserRole.STUDENT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "keep_user_id is not a student")

    duplicates = db.query(User).filter(User.id.in_(payload.merge_user_ids)).all()
    affected = 0
    errors: List[str] = []
    for d in duplicates:
        if d.id == keeper.id:
            errors.append(f"{d.id} · same as keeper (skipped)")
            continue
        if d.role != UserRole.STUDENT:
            errors.append(f"{d.id} · not a student (skipped)")
            continue
        for cls in (VocationalTestResult, JournalEntry, Route, ProfileVersion):
            db.query(cls).filter(cls.user_id == d.id).update({cls.user_id: keeper.id}, synchronize_session=False)
        d.is_active = False
        d.suspended_at = d.suspended_at or datetime.utcnow()
        log_action(
            db,
            user=current_user,
            action="user.bulk_merge",
            resource_type="user",
            resource_id=str(d.id),
            payload={"merged_into": str(keeper.id)},
            request=request,
            commit=False,
        )
        affected += 1
    db.commit()
    return AdminBulkResultOut(affected=affected, skipped=0, errors=errors)


@router.post(
    "/users/bulk/delete",
    response_model=AdminBulkResultOut,
    summary="GH-SUPERADMIN · Bloque F · soft delete students en masse",
)
def bulk_delete(
    payload: AdminBulkDeleteIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    rows = _resolve_students(db, payload.user_ids)
    affected = 0
    errors: List[str] = []
    for u in rows:
        if u.id == current_user.id or u.role == UserRole.SUPER_ADMIN:
            errors.append(f"{u.id} · protected role (skipped)")
            continue
        u.is_active = False
        u.suspended_at = u.suspended_at or datetime.utcnow()
        log_action(
            db,
            user=current_user,
            action="user.bulk_delete",
            resource_type="user",
            resource_id=str(u.id),
            request=request,
            commit=False,
        )
        affected += 1
    db.commit()
    return AdminBulkResultOut(affected=affected, skipped=len(payload.user_ids) - affected, errors=errors)


# --------------------------------------------------------------------------- #
# Bloque E · impersonation                                                    #
# --------------------------------------------------------------------------- #

@router.post(
    "/impersonate/{user_id}/start",
    response_model=ImpersonationStartOut,
    summary="GH-SUPERADMIN · Bloque E · start impersonation session",
)
def start_impersonation(
    user_id: UUID,
    payload: ImpersonationStartIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hard rules:
      - actor MUST be super_admin
      - target MUST NOT be super_admin (no peer-impersonation, no self)
      - only one active session per actor (close prior one first)
      - JWT carries impersonation marker so middleware enforces banner + scope
    """
    _require_super_admin(current_user)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target user not found")
    if target.role == UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot impersonate another super_admin")
    if target.id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot impersonate yourself")
    if target.suspended_at is not None or not target.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Target user is not active")

    # Close any active session for this actor (no chained impersonations)
    db.query(ImpersonationSession).filter(
        ImpersonationSession.actor_user_id == current_user.id,
        ImpersonationSession.ended_at.is_(None),
    ).update({"ended_at": datetime.utcnow()}, synchronize_session=False)

    token_str = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=30)

    session = ImpersonationSession(
        id=uuid4(),
        actor_user_id=current_user.id,
        target_user_id=target.id,
        token=token_str,
        scope=payload.scope,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent", "")[:255] if request.headers.get("user-agent") else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # JWT for the impersonation session: subject = target, with explicit
    # impersonation claims so middleware can detect it.
    jwt_token = create_access_token(
        data={
            "sub": str(target.id),
            "imp_actor": str(current_user.id),
            "imp_session": str(session.id),
            "imp_scope": payload.scope,
        },
        expires_delta=timedelta(minutes=30),
    )

    log_action(
        db,
        user=current_user,
        action="impersonation.start",
        resource_type="user",
        resource_id=str(target.id),
        payload={
            "session_id": str(session.id),
            "scope": payload.scope,
            "actor_user_id": str(current_user.id),
        },
        request=request,
    )

    return ImpersonationStartOut(
        session_id=session.id,
        token=jwt_token,
        target_user=_to_admin_user(target),
        scope=payload.scope,
        expires_at=expires_at,
    )


@router.post(
    "/impersonate/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="GH-SUPERADMIN · Bloque E · stop active impersonation",
)
def stop_impersonation(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Closes the most recent active impersonation initiated by the caller.

    Caller can be the super_admin (with their original token) OR the
    impersonated user itself ("Salir" button) — in the latter case the
    JWT carries `imp_actor`.
    """
    actor_id = current_user.id
    # If the caller is currently impersonating someone, the JWT carries imp_actor.
    # We don't have the JWT payload here directly — service uses request scope.
    # Look up by either actor or target as fallback.
    sess = (
        db.query(ImpersonationSession)
        .filter(
            ImpersonationSession.ended_at.is_(None),
            or_(
                ImpersonationSession.actor_user_id == actor_id,
                ImpersonationSession.target_user_id == actor_id,
            ),
        )
        .order_by(ImpersonationSession.started_at.desc())
        .first()
    )
    if not sess:
        return  # idempotent

    sess.ended_at = datetime.utcnow()
    db.commit()
    log_action(
        db,
        user=current_user,
        action="impersonation.stop",
        resource_type="user",
        resource_id=str(sess.target_user_id),
        payload={"session_id": str(sess.id), "actor_user_id": str(sess.actor_user_id)},
        request=request,
    )
