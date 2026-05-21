"""Extracurricular activities · F-001 (2026-05-21).

Endpoints:
  - Student-facing (`/me/activities`):
      POST   / · create
      GET    / · list (own)
      PATCH  /{id} · update (own)
      DELETE /{id} · delete (own)
  - Advisor-facing (`/gh/students/{id}/activities`):
      GET / · read-only, scoped via _can_access_clinical_data
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.clinical import _can_access_clinical_data
from app.db.database import get_db
from app.db.models import ExtracurricularActivity, User, UserRole
from app.schemas.extracurriculars import (
    ExtracurricularCreate,
    ExtracurricularList,
    ExtracurricularOut,
    ExtracurricularUpdate,
)
from app.services import extracurricular_service
from app.services.auth_service import get_current_user


# ---------------------------------------------------------------------------
# Student-facing router (/me/activities)
# ---------------------------------------------------------------------------

router_me = APIRouter(prefix="/me/activities", tags=["StudentMe · Activities"])


def _require_student(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )


@router_me.post(
    "",
    response_model=ExtracurricularOut,
    status_code=201,
    summary="F-001 · create an extracurricular activity",
)
def create_my_activity(
    body: ExtracurricularCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)
    try:
        row = extracurricular_service.create_activity(
            db,
            user=current_user,
            category=body.category,
            name=body.name,
            role=body.role,
            hours_per_week=body.hours_per_week,
            start_date=body.start_date,
            end_date=body.end_date,
            description=body.description,
            achievements=body.achievements,
            evidence_urls=body.evidence_urls,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ExtracurricularOut.model_validate(row)


@router_me.get(
    "",
    response_model=ExtracurricularList,
    summary="F-001 · list my extracurricular activities",
)
def list_my_activities(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)
    rows, total = extracurricular_service.list_activities_for_user(
        db, current_user.id
    )
    return ExtracurricularList(
        items=[ExtracurricularOut.model_validate(r) for r in rows],
        total=total,
    )


@router_me.patch(
    "/{activity_id}",
    response_model=ExtracurricularOut,
    summary="F-001 · update one of my activities",
)
def update_my_activity(
    activity_id: UUID,
    body: ExtracurricularUpdate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)
    row = extracurricular_service.get_activity(db, activity_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="activity not found")
    try:
        updated = extracurricular_service.update_activity(
            db,
            row=row,
            **{k: v for k, v in body.model_dump(exclude_unset=True).items()},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ExtracurricularOut.model_validate(updated)


@router_me.delete(
    "/{activity_id}",
    status_code=204,
    summary="F-001 · delete one of my activities",
)
def delete_my_activity(
    activity_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)
    row = extracurricular_service.get_activity(db, activity_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="activity not found")
    extracurricular_service.delete_activity(db, row)


# ---------------------------------------------------------------------------
# Advisor-facing router (/gh/students/{id}/activities)
# ---------------------------------------------------------------------------

router_gh = APIRouter(prefix="/gh/students", tags=["GH Advisor · Activities"])


def _resolve_student_clinical(db: DBSession, student_id: UUID, current_user: User) -> User:
    """Reuse existing clinical access gate from `app.api.v1.clinical`."""
    student = (
        db.query(User)
        .filter(User.id == student_id, User.role == UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="student not found")
    if not _can_access_clinical_data(current_user, student):
        raise HTTPException(
            status_code=403,
            detail="forbidden · student not in your clinical scope",
        )
    return student


@router_gh.get(
    "/{student_id}/activities",
    response_model=ExtracurricularList,
    summary="F-001 · read student's extracurricular activities (psy/advisor read-only)",
)
def list_student_activities(
    student_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _resolve_student_clinical(db, student_id, current_user)
    rows, total = extracurricular_service.list_activities_for_user(db, student.id)
    return ExtracurricularList(
        items=[ExtracurricularOut.model_validate(r) for r in rows],
        total=total,
    )
