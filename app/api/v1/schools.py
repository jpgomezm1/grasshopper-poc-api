"""Schools router · placeholder CRUD for Sprint 2.

GH-S2-BE-08 · provides minimum endpoints required to:
- Allow super_admin to create the first schools (used by E2E in S2-QA-01).
- Read the list of schools (used by the FE to populate dropdowns when
  registering staff via /auth/register-school-user).

Full CRUD (update / soft delete / pagination / filters) is delivered in
Sprint 8 · GH-S8-BE-01,02. This file intentionally stays small until then.
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import School, User, UserRole
from app.schemas.school import SchoolCreate, SchoolResponse


router = APIRouter(prefix="/schools", tags=["Schools"])


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can manage schools.",
        )


@router.post(
    "",
    response_model=SchoolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S2-BE-08 · create school (super_admin only)",
)
def create_school(
    payload: SchoolCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    school = School(
        name=payload.name.strip(),
        slug=payload.slug.strip().lower(),
        logo_url=payload.logo_url,
        license_active=payload.license_active,
        license_expires_at=payload.license_expires_at,
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
    return SchoolResponse.model_validate(school)


@router.get(
    "",
    response_model=List[SchoolResponse],
    summary="GH-S2-BE-08 · list schools (super_admin or school staff)",
)
def list_schools(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List schools.

    - super_admin sees all
    - school_admin and psychologist see only their own school
    - student / others get 403
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        rows = db.query(School).order_by(School.name.asc()).all()
        return [SchoolResponse.model_validate(s) for s in rows]

    if current_user.role in (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST):
        if not current_user.school_id:
            return []
        row = db.query(School).filter(School.id == current_user.school_id).first()
        return [SchoolResponse.model_validate(row)] if row else []

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden.",
    )


@router.get(
    "/{school_id}",
    response_model=SchoolResponse,
    summary="GH-S2-BE-08 · get school by id",
)
def get_school(
    school_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found.")

    # super_admin can see any · school staff only their own
    if current_user.role == UserRole.SUPER_ADMIN:
        return SchoolResponse.model_validate(school)
    if current_user.role in (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST):
        if str(current_user.school_id) == str(school.id):
            return SchoolResponse.model_validate(school)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden · cannot read schools other than your own.",
    )
