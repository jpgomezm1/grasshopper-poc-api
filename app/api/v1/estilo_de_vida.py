"""El cuestionario de estilo de vida y presupuesto · E-3, Sprint 4 · `/me/estilo-de-vida`.

Ver `estilo_de_vida_service` para el porqué. Leer no lleva llave (lo que ya
respondió sigue siendo suyo); guardar sí (`estilo_de_vida`: pago, 11° y 12°).
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.api.v1.llave_plan import requiere
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import estilo_de_vida_service as svc

router = APIRouter(prefix="/me/estilo-de-vida", tags=["StudentMe"])


class Respuestas(BaseModel):
    respuestas: Dict[str, Any]


def _solo_estudiante(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para estudiantes.")


@router.get("")
def leer(current_user: User = Depends(get_current_user)):
    _solo_estudiante(current_user)
    return svc.estado(current_user)


@router.put("", dependencies=[Depends(requiere("estilo_de_vida"))])
def guardar(
    payload: Respuestas,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _solo_estudiante(current_user)
    try:
        return svc.guardar(db, current_user, payload.respuestas)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
