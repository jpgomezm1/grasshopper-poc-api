"""`GET /school/me/tablero` · el tablero agregado y anónimo · F-2 / F-4, Sprint 4.

Ver `tablero_anonimo_service`. Lo ve el administrador de la organización
(colegio, programa o empresa); el super admin, el de la organización a la que
esté atado. Es lo único que ve, de sus participantes, el personal de un
programa o una empresa (`org_privacidad`).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import School, User, UserRole
from app.services import tablero_anonimo_service

router = APIRouter(prefix="/school/me", tags=["Organización · tablero anónimo"])


@router.get("/tablero")
def tablero(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    if current_user.role not in (UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador de la organización.")
    if not current_user.school_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No estás asociado a ninguna organización.")
    school = db.query(School).filter(School.id == current_user.school_id).first()
    if school is None or school.archived_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos tu organización.")
    return tablero_anonimo_service.armar(db, school)
