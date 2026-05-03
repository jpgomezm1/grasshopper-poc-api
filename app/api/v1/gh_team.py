"""GH internal team endpoints · GH-ROLES-001.

Two surfaces:

1. **Student-side contact request** · `POST /students/me/request-gh-contact`
   Lets a B2B student opt-in to be visible to the gh_advisor / gh_commercial
   roles. The flag stays on `users` (no separate table · low-volume signal).

2. **GH-team-side dashboards** · `/gh/*`
    - `GET /gh/students`                              gh_advisor + super_admin
    - `GET /gh/students/{user_id}`                    gh_advisor + super_admin
    - `GET /gh/contact-requests`                      gh_advisor + gh_commercial + super_admin
    - `PATCH /gh/contact-requests/{user_id}/status`   gh_commercial + super_admin

Visibility rules (server-side, never trust the client):
- gh_advisor sees students where `school_id IS NULL` (B2C)
                   OR `gh_contact_requested_at IS NOT NULL` (opt-in B2B).
- gh_commercial does NOT see students individually · only the contact-requests
  list (which is itself a subset of opted-in students).
- super_admin can hit every endpoint here for support purposes.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    GH_CONTACT_REQUEST_STATUSES,
    School,
    User,
    UserRole,
)
from app.schemas.gh_team import (
    GhContactRequestIn,
    GhContactRequestList,
    GhContactRequestListItem,
    GhContactRequestOut,
    GhContactStatusUpdate,
    GhStudentListResponse,
    GhStudentSummary,
)
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)


students_router = APIRouter(prefix="/students", tags=["Students · Self"])
gh_router = APIRouter(prefix="/gh", tags=["GH Team"])


# =============================================================================
# Auth guards
# =============================================================================


def _require_student(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only students can request GH contact.",
        )


def _require_gh_advisor_or_super(user: User) -> None:
    if user.role not in (UserRole.GH_ADVISOR, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · gh_advisor or super_admin only.",
        )


def _require_gh_team(user: User) -> None:
    """Anyone in the GH internal team (advisor + commercial + super_admin)."""
    if user.role not in (
        UserRole.GH_ADVISOR,
        UserRole.GH_COMMERCIAL,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · gh_advisor, gh_commercial or super_admin only.",
        )


def _require_gh_commercial_or_super(user: User) -> None:
    if user.role not in (UserRole.GH_COMMERCIAL, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · gh_commercial or super_admin only.",
        )


# =============================================================================
# Helpers
# =============================================================================


def _student_to_summary(user: User, school: Optional[School]) -> GhStudentSummary:
    return GhStudentSummary(
        id=user.id,
        email=user.email,
        name=user.name,
        school_id=user.school_id,
        school_name=school.name if school else None,
        onboarding_status=(
            user.onboarding_status.value
            if user.onboarding_status is not None
            and hasattr(user.onboarding_status, "value")
            else str(user.onboarding_status or "not_started")
        ),
        english_cefr_level=user.english_cefr_level,
        english_test_completed=bool(user.english_test_completed),
        is_b2c=user.school_id is None,
        has_contact_request=user.gh_contact_requested_at is not None,
        gh_contact_status=user.gh_contact_status,  # type: ignore[arg-type]
        gh_contact_requested_at=user.gh_contact_requested_at,
        gh_contact_message=user.gh_contact_message,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


# =============================================================================
# Student-facing
# =============================================================================


@students_router.post(
    "/me/request-gh-contact",
    response_model=GhContactRequestOut,
    status_code=status.HTTP_200_OK,
    summary="GH-ROLES-001 · student opts-in to contact GH advisors",
)
def request_gh_contact(
    body: GhContactRequestIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotent · re-submitting before resolution refreshes message + timestamp.

    Once status moves out of `pending` (in_progress / converted / declined),
    the student CAN re-submit and we reset the lifecycle to `pending` so the
    GH team sees the new context. We log every transition to audit.
    """
    _require_student(current_user)

    previous_status = current_user.gh_contact_status

    current_user.gh_contact_requested_at = datetime.utcnow()
    current_user.gh_contact_message = (body.message or "").strip() or None
    current_user.gh_contact_status = "pending"

    log_action(
        db,
        user=current_user,
        action="gh_contact.requested",
        resource_type="user",
        resource_id=str(current_user.id),
        payload={
            "previous_status": previous_status,
            "new_status": "pending",
            "had_message": bool(current_user.gh_contact_message),
        },
        commit=False,
    )

    db.commit()
    db.refresh(current_user)

    return GhContactRequestOut(
        requested_at=current_user.gh_contact_requested_at,
        status=current_user.gh_contact_status,  # type: ignore[arg-type]
        message=current_user.gh_contact_message,
    )


@students_router.get(
    "/me/gh-contact-status",
    response_model=Optional[GhContactRequestOut],
    summary="GH-ROLES-001 · student reads their own contact-request state",
)
def my_gh_contact_status(
    current_user: User = Depends(get_current_user),
):
    """Returns the current request state or null if none exists."""
    _require_student(current_user)
    if current_user.gh_contact_requested_at is None:
        return None
    return GhContactRequestOut(
        requested_at=current_user.gh_contact_requested_at,
        status=current_user.gh_contact_status or "pending",  # type: ignore[arg-type]
        message=current_user.gh_contact_message,
    )


# =============================================================================
# GH-team-facing
# =============================================================================


@gh_router.get(
    "/students",
    response_model=GhStudentListResponse,
    summary="GH-ROLES-001 · list students visible to gh_advisor",
)
def gh_list_students(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    scope: str = Query(
        "all",
        regex="^(all|b2c|contact_requested)$",
        description="all | b2c | contact_requested",
    ),
    search: Optional[str] = Query(None, max_length=200),
):
    _require_gh_advisor_or_super(current_user)

    q = db.query(User).filter(User.role == UserRole.STUDENT, User.is_active.is_(True))

    if scope == "b2c":
        q = q.filter(User.school_id.is_(None))
    elif scope == "contact_requested":
        q = q.filter(User.gh_contact_requested_at.isnot(None))
    else:  # 'all' = the union (B2C OR opted-in B2B)
        q = q.filter(
            or_(
                User.school_id.is_(None),
                User.gh_contact_requested_at.isnot(None),
            )
        )

    if search:
        like = f"%{search.strip().lower()}%"
        q = q.filter(or_(User.email.ilike(like), User.name.ilike(like)))

    total = q.count()
    rows = (
        q.order_by(User.gh_contact_requested_at.desc().nullslast(), User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    school_ids = {u.school_id for u in rows if u.school_id is not None}
    schools_by_id: dict = {}
    if school_ids:
        for s in db.query(School).filter(School.id.in_(school_ids)).all():
            schools_by_id[s.id] = s

    items = [_student_to_summary(u, schools_by_id.get(u.school_id)) for u in rows]

    return GhStudentListResponse(items=items, total=total, page=page, page_size=page_size)


@gh_router.get(
    "/students/{user_id}",
    response_model=GhStudentSummary,
    summary="GH-ROLES-001 · gh_advisor reads a single visible student",
)
def gh_get_student(
    user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gh_advisor_or_super(current_user)

    student = (
        db.query(User)
        .filter(User.id == user_id, User.role == UserRole.STUDENT, User.is_active.is_(True))
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Visibility gate · super_admin bypasses the rule.
    if current_user.role != UserRole.SUPER_ADMIN:
        if student.school_id is not None and student.gh_contact_requested_at is None:
            raise HTTPException(
                status_code=403,
                detail="Forbidden · this student has not opted-in to GH contact.",
            )

    school = (
        db.query(School).filter(School.id == student.school_id).first()
        if student.school_id
        else None
    )
    return _student_to_summary(student, school)


@gh_router.get(
    "/contact-requests",
    response_model=GhContactRequestList,
    summary="GH-ROLES-001 · list pending GH contact requests",
)
def gh_list_contact_requests(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: str = Query("pending", alias="status", description="pending|in_progress|converted|declined|all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    _require_gh_team(current_user)

    q = db.query(User).filter(
        User.role == UserRole.STUDENT,
        User.gh_contact_requested_at.isnot(None),
    )
    if status_filter != "all":
        if status_filter not in GH_CONTACT_REQUEST_STATUSES:
            raise HTTPException(status_code=400, detail="invalid status filter")
        q = q.filter(User.gh_contact_status == status_filter)

    total = q.count()
    rows = (
        q.order_by(User.gh_contact_requested_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    school_ids = {u.school_id for u in rows if u.school_id is not None}
    schools_by_id: dict = {}
    if school_ids:
        for s in db.query(School).filter(School.id.in_(school_ids)).all():
            schools_by_id[s.id] = s

    items = [
        GhContactRequestListItem(
            user_id=u.id,
            email=u.email,
            name=u.name,
            school_id=u.school_id,
            school_name=schools_by_id[u.school_id].name if u.school_id in schools_by_id else None,
            is_b2c=u.school_id is None,
            gh_contact_status=u.gh_contact_status,  # type: ignore[arg-type]
            gh_contact_requested_at=u.gh_contact_requested_at,
            gh_contact_message=u.gh_contact_message,
        )
        for u in rows
    ]
    return GhContactRequestList(items=items, total=total)


@gh_router.patch(
    "/contact-requests/{user_id}/status",
    response_model=GhContactRequestListItem,
    summary="GH-ROLES-001 · update contact-request status",
)
def gh_update_contact_status(
    user_id: UUID,
    body: GhContactStatusUpdate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_gh_commercial_or_super(current_user)

    student = (
        db.query(User)
        .filter(User.id == user_id, User.role == UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if student.gh_contact_requested_at is None:
        raise HTTPException(
            status_code=409,
            detail="Cannot update status · student has no active contact request.",
        )

    previous = student.gh_contact_status
    student.gh_contact_status = body.status

    log_action(
        db,
        user=current_user,
        action="gh_contact.status_changed",
        resource_type="user",
        resource_id=str(student.id),
        payload={"from": previous, "to": body.status},
        commit=False,
    )

    db.commit()
    db.refresh(student)

    school = (
        db.query(School).filter(School.id == student.school_id).first()
        if student.school_id
        else None
    )
    return GhContactRequestListItem(
        user_id=student.id,
        email=student.email,
        name=student.name,
        school_id=student.school_id,
        school_name=school.name if school else None,
        is_b2c=student.school_id is None,
        gh_contact_status=student.gh_contact_status,  # type: ignore[arg-type]
        gh_contact_requested_at=student.gh_contact_requested_at,
        gh_contact_message=student.gh_contact_message,
    )
