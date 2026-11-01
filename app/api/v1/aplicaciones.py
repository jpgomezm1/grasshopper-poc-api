"""El kit de aplicación de 12° · E-4, Sprint 4 · `/me/aplicaciones`.

Ver `kit_aplicacion_service` para el porqué. Aquí, la plomería:

- Leer NO lleva llave del plan: lo que la persona ya armó sigue siendo suyo
  aunque baje de plan (misma regla de `llave_plan`). Crear, editar y borrar sí.
- Cada aplicación es de quien la creó: editar o borrar una ajena da 404, no
  403, para no confirmar que el id existe.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.api.v1.llave_plan import requiere
from app.db.database import get_db
from app.db.models import AplicacionUniversidad, User, UserRole
from app.services import kit_aplicacion_service as kit

router = APIRouter(prefix="/me/aplicaciones", tags=["StudentMe"])


class AplicacionIn(BaseModel):
    universidad: str = Field(min_length=1, max_length=200)
    programa: Optional[str] = Field(default=None, max_length=200)
    pais: str
    fecha_limite: Optional[date] = None


class AplicacionPatch(BaseModel):
    universidad: Optional[str] = Field(default=None, min_length=1, max_length=200)
    programa: Optional[str] = Field(default=None, max_length=200)
    pais: Optional[str] = None
    fecha_limite: Optional[date] = None
    # Para borrar la fecha (None en `fecha_limite` significa "no la cambies").
    sin_fecha: bool = False
    listos: Optional[List[str]] = None


def _solo_estudiante(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para estudiantes.")


def _pais_valido(pais: str) -> str:
    if pais not in kit.PAISES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "País no reconocido.")
    return pais


def _limpio(texto: Optional[str]) -> Optional[str]:
    if texto is None:
        return None
    return texto.strip() or None


def _suya(db: DBSession, user: User, aplicacion_id: UUID) -> AplicacionUniversidad:
    a = (
        db.query(AplicacionUniversidad)
        .filter(AplicacionUniversidad.id == aplicacion_id, AplicacionUniversidad.user_id == user.id)
        .first()
    )
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa aplicación.")
    return a


@router.get("")
def listar(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    _solo_estudiante(current_user)
    return kit.listar(db, current_user)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere("kit_aplicacion"))],
)
def crear(
    payload: AplicacionIn,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _solo_estudiante(current_user)
    universidad = _limpio(payload.universidad)
    if not universidad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escribe el nombre de la universidad.")
    total = db.query(AplicacionUniversidad).filter(AplicacionUniversidad.user_id == current_user.id).count()
    if total >= kit.MAX_APLICACIONES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Puedes llevar hasta {kit.MAX_APLICACIONES} aplicaciones. Borra alguna que ya no uses.",
        )
    a = AplicacionUniversidad(
        user_id=current_user.id,
        universidad=universidad,
        programa=_limpio(payload.programa),
        pais=_pais_valido(payload.pais),
        fecha_limite=payload.fecha_limite,
        listos=[],
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return kit.serializar(a)


@router.patch("/{aplicacion_id}", dependencies=[Depends(requiere("kit_aplicacion"))])
def editar(
    aplicacion_id: UUID,
    payload: AplicacionPatch,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _solo_estudiante(current_user)
    a = _suya(db, current_user, aplicacion_id)
    if payload.universidad is not None:
        universidad = _limpio(payload.universidad)
        if not universidad:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escribe el nombre de la universidad.")
        a.universidad = universidad
    if payload.programa is not None:
        a.programa = _limpio(payload.programa)
    if payload.pais is not None:
        a.pais = _pais_valido(payload.pais)
    if payload.sin_fecha:
        a.fecha_limite = None
    elif payload.fecha_limite is not None:
        a.fecha_limite = payload.fecha_limite
    validos = kit.ids_validos(a.pais)
    if payload.listos is not None:
        desconocidos = set(payload.listos) - validos
        if desconocidos:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Documento no reconocido.")
        a.listos = sorted(set(payload.listos))
    else:
        # Si cambió el país, lo que ya no aplica deja de contar como listo.
        a.listos = sorted(set(a.listos or []) & validos)
    db.commit()
    db.refresh(a)
    return kit.serializar(a)


@router.delete(
    "/{aplicacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requiere("kit_aplicacion"))],
)
def borrar(
    aplicacion_id: UUID,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _solo_estudiante(current_user)
    db.delete(_suya(db, current_user, aplicacion_id))
    db.commit()
