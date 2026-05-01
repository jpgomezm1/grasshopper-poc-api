"""License enforcement · GH-S8-BE-05.

Centralizes the rule: "school_admin cannot register a new student if the
school's active license is expired or its seats cap is reached".

Used by the school-admin invitation / registration flow. The super_admin
flow bypasses this (they own the platform).
"""
from __future__ import annotations

from datetime import datetime
from typing import Tuple
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.db.models import License, LicenseStatus, School, User, UserRole


def _current_active_license(db: DBSession, school_id: UUID) -> License | None:
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


def can_register_student(db: DBSession, school_id: UUID) -> Tuple[bool, str]:
    """Return (allowed, reason).

    Reasons:
        - "ok"
        - "school_archived"
        - "license_missing"
        - "license_expired"
        - "license_cancelled"
        - "seats_exhausted"
    """
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        return False, "school_not_found"
    if school.archived_at is not None:
        return False, "school_archived"

    lic = _current_active_license(db, school_id)
    if not lic:
        # legacy path: respect the flag on the school directly
        if not school.license_active:
            return False, "license_cancelled"
        if school.license_expires_at and school.license_expires_at <= datetime.utcnow():
            return False, "license_expired"
        return False, "license_missing"

    used = (
        db.query(func.count(User.id))
        .filter(
            User.school_id == school_id,
            User.role == UserRole.STUDENT,
            User.is_active.is_(True),
        )
        .scalar()
        or 0
    )
    if used >= lic.seats:
        return False, "seats_exhausted"
    return True, "ok"


def assert_can_register_student(db: DBSession, school_id: UUID) -> None:
    """Same as `can_register_student` but raises 403 with a friendly message."""
    from fastapi import HTTPException, status

    ok, reason = can_register_student(db, school_id)
    if ok:
        return

    detail_map = {
        "school_not_found": ("School not found.", status.HTTP_404_NOT_FOUND),
        "school_archived": (
            "El colegio está archivado. Contacte al administrador de Grasshopper.",
            status.HTTP_403_FORBIDDEN,
        ),
        "license_missing": (
            "El colegio no tiene licencia activa. Contacte al administrador de Grasshopper.",
            status.HTTP_403_FORBIDDEN,
        ),
        "license_expired": (
            "La licencia del colegio expiró. Renueve para registrar nuevos estudiantes.",
            status.HTTP_403_FORBIDDEN,
        ),
        "license_cancelled": (
            "La licencia del colegio fue cancelada.",
            status.HTTP_403_FORBIDDEN,
        ),
        "seats_exhausted": (
            "El cupo de estudiantes de la licencia está completo. Solicite ampliación de seats.",
            status.HTTP_403_FORBIDDEN,
        ),
    }
    detail, code = detail_map.get(
        reason, ("No se puede registrar el estudiante en este colegio.", status.HTTP_403_FORBIDDEN)
    )
    raise HTTPException(status_code=code, detail=detail)
