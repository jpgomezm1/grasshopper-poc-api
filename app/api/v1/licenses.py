"""Licenses router · GH-S8-BE-04.

Direct license operations by id (super_admin only):
- PATCH  /licenses/{id}            · update tier/seats/expires/status/notes
- GET    /licenses/{id}            · read

(creation lives under POST /schools/{school_id}/licenses for clarity)
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import License, LicenseStatus, School, User, UserRole
from app.schemas.license import LicenseResponse, LicenseUpdate
from app.services.audit_service import log_action


router = APIRouter(prefix="/licenses", tags=["Licenses"])


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can manage licenses.",
        )


@router.get(
    "/{license_id}",
    response_model=LicenseResponse,
    summary="GH-S8-BE-04 · read license by id",
)
def get_license(
    license_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lic = db.query(License).filter(License.id == license_id).first()
    if not lic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found.")
    if current_user.role == UserRole.SUPER_ADMIN:
        return LicenseResponse.model_validate(lic)
    if current_user.role in (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST):
        if str(current_user.school_id) == str(lic.school_id):
            return LicenseResponse.model_validate(lic)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")


@router.patch(
    "/{license_id}",
    response_model=LicenseResponse,
    summary="GH-S8-BE-04 · partial update of a license (super_admin only)",
)
def update_license(
    license_id: UUID,
    payload: LicenseUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    lic = db.query(License).filter(License.id == license_id).first()
    if not lic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found.")

    diff: dict = {}
    if payload.tier is not None and payload.tier != lic.tier:
        diff["tier"] = {"from": lic.tier, "to": payload.tier}
        lic.tier = payload.tier
    if payload.seats is not None and payload.seats != lic.seats:
        diff["seats"] = {"from": lic.seats, "to": payload.seats}
        lic.seats = payload.seats
    if payload.starts_at is not None and payload.starts_at != lic.starts_at:
        diff["starts_at"] = {"to": payload.starts_at.isoformat()}
        lic.starts_at = payload.starts_at
    if payload.expires_at is not None and payload.expires_at != lic.expires_at:
        diff["expires_at"] = {"to": payload.expires_at.isoformat()}
        lic.expires_at = payload.expires_at
    if payload.status is not None and payload.status != lic.status:
        diff["status"] = {"from": lic.status, "to": payload.status}
        lic.status = payload.status
    if payload.notes is not None and payload.notes != lic.notes:
        diff["notes"] = True
        lic.notes = payload.notes

    lic.updated_at = datetime.utcnow()

    # Mirror to school flag if status flips
    if payload.status is not None:
        school = db.query(School).filter(School.id == lic.school_id).first()
        if school:
            school.license_active = (lic.status == LicenseStatus.ACTIVE.value)
            if lic.status == LicenseStatus.ACTIVE.value and lic.expires_at:
                school.license_expires_at = lic.expires_at

    db.commit()
    db.refresh(lic)

    if diff:
        action = (
            "license.cancel"
            if payload.status == LicenseStatus.CANCELLED.value
            else "license.update"
        )
        log_action(
            db,
            user=current_user,
            action=action,
            resource_type="license",
            resource_id=str(lic.id),
            payload=diff,
            request=request,
        )

    return LicenseResponse.model_validate(lic)
