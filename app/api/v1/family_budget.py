"""La calculadora financiera del acudiente · `/me/hijos/{id}/presupuesto`.

Verónica (Padres de Familia, Paso 2): *"Calculadora Financiera. Módulo PRIVADO
para ingresar presupuesto disponible para la educación de su hijo."*

## Quién puede

Sólo un acudiente, y sólo sobre un hijo con el que tenga una relación **activa**
(`is_active`). Una relación revocada —divorcio, cambio de custodia— deja de dar
acceso por esta puerta.

Un 404 (y no un 403) cuando no hay relación: confirmar que ese estudiante
existe ya es información que no le toca a quien no es su acudiente.

## Y quién NO

**El estudiante no ve esto.** No hay ruta suya que lo lea, el dato no toca sus
columnas de presupuesto, y no viaja a su recomendador ni al reporte que le
manda a su colegio. "Privado" es la palabra que ella usó, y aquí significa eso.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import family_budget_service as servicio

router = APIRouter(prefix="/me/hijos", tags=["Calculadora financiera"])


class PresupuestoIn(BaseModel):
    anual_max: Optional[int] = Field(default=None, ge=0)
    moneda: Optional[str] = Field(default=None, max_length=3)
    con_financiacion: Optional[bool] = None
    nota: Optional[str] = Field(default=None, max_length=2000)


def _relacion_o_404(db: DBSession, current_user: User, student_id: UUID):
    if current_user.role != UserRole.PARENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta calculadora es del acudiente.",
        )
    relacion = servicio.relacion_activa(db, current_user, student_id)
    if relacion is None:
        # Mismo mensaje que si no existiera · no se confirma la existencia de
        # un estudiante ajeno.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return relacion


@router.get("/{student_id}/presupuesto")
def leer(
    student_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """El presupuesto y qué alcanza · el rango del catálogo va siempre.

    Aunque no haya presupuesto guardado se devuelve el rango de lo que existe:
    es justo cuando más le sirve a un padre que todavía no sabe qué números
    manejar.
    """
    relacion = _relacion_o_404(db, current_user, student_id)
    return servicio.a_diccionario(servicio.obtener(db, relacion))


@router.put("/{student_id}/presupuesto")
def guardar(
    datos: PresupuestoIn,
    student_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Guarda y responde con qué alcanza · en una sola vuelta."""
    relacion = _relacion_o_404(db, current_user, student_id)
    try:
        guardado = servicio.guardar(db, relacion, datos.model_dump())
    except servicio.DatoInvalido as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    db.commit()
    db.refresh(guardado)
    return servicio.a_diccionario(guardado)
