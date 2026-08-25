"""Práctica para exámenes de admisión (SAT · IELTS).

Reunión con la clienta del 2026-08-24 (min. 40:22): *"yo lo que necesito es
pasar el test, no que nadie me certifique... es solamente para hacer el test"*.
No es el examen: es material de práctica propio. El porqué completo está en el
docstring de `app/data/exam_prep.py`.

## Dos decisiones de este router

**El aviso viaja en TODAS las respuestas.** `disclaimer` (y `trademark` cuando
hay un examen concreto) sale en los cuatro endpoints. La instrucción de la
clienta fue explícita: el encuadre va en pantalla, no en letra chica. Ponerlo
sólo en el listado dejaría la pantalla de práctica —la que el estudiante mira
durante veinte minutos— sin ningún aviso. Hay un test que recorre los cuatro y
falla si alguno lo omite.

**No hay gate de consentimiento ni de aviso psicométrico.** Los tests
vocacionales exigen `_disclaimer_accepted` (F-005) y consentimiento parental
(M-006) porque producen una lectura sobre la persona que después leen su familia
y un asesor. Esto no: son ejercicios de gramática y de álgebra, no se guarda
nada, no se infiere nada del estudiante y no alimenta ningún perfil. Aplicarle
el gate sería tratar un cuaderno de práctica como un instrumento psicológico.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.data import exam_prep as banco
from app.db.database import get_db
from app.db.models import User
from app.services import exam_prep_service

router = APIRouter(prefix="/exam-prep", tags=["Exam Prep"])


class CheckAnswersRequest(BaseModel):
    """Lo que el estudiante marcó · {id_del_ejercicio: opción elegida}."""

    answers: Dict[str, Any] = Field(default_factory=dict)


def _examen_o_404(exam_id: str) -> Dict[str, Any]:
    examen = banco.get_examen(exam_id)
    if examen is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Esa práctica no existe.",
        )
    return examen


@router.get("")
def listar_examenes(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Qué prácticas hay y cuál le tiene sentido a este estudiante.

    Nunca esconde un examen: devuelve los dos con su `recommendation`. Ver
    "se recomienda, no se bloquea" en `exam_prep_service`.
    """
    return exam_prep_service.catalogo(db, current_user)


@router.get("/{exam_id}")
def detalle_examen(
    exam_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """La ficha: habilidades, en qué nivel arranca cada una y qué NO cubre."""
    _examen_o_404(exam_id)
    return exam_prep_service.detalle(db, current_user, exam_id)


@router.get("/{exam_id}/practice")
def obtener_practica(
    exam_id: str,
    skill: Optional[str] = None,
    limit: int = Query(default=banco.TAMANO_SESION, ge=1, le=exam_prep_service.MAX_EJERCICIOS_POR_SESION),
    round: int = Query(default=1, ge=1),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Una tanda de ejercicios SIN las respuestas.

    `round` sirve para pedir la siguiente tanda sin repetir: la selección es
    determinista (no hay `random`), así que sin este parámetro quien vuelve
    vería siempre los mismos ejercicios. No se guarda por qué ronda va cada
    estudiante — no hay tabla y hoy nadie leería ese dato.
    """
    _examen_o_404(exam_id)
    try:
        return exam_prep_service.sesion(
            db,
            current_user,
            exam_id,
            skill_id=skill,
            limite=limit,
            ronda=round,
        )
    except ValueError:
        # Sólo puede venir de un `skill` que no existe en este examen: el examen
        # ya se validó arriba.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Esa habilidad no existe en esta práctica.",
        )


@router.post("/{exam_id}/practice/check")
def revisar_practica(
    exam_id: str,
    request: CheckAnswersRequest,
    current_user: User = Depends(get_current_user),
):
    """Corrige lo respondido y devuelve la explicación de CADA ejercicio.

    No se persiste nada, así que no necesita `db`. La explicación viaja también
    cuando la respuesta fue correcta: acertar por descarte y no saber por qué es
    el escenario que esta práctica intenta evitar.
    """
    _examen_o_404(exam_id)
    return exam_prep_service.evaluar(exam_id, request.answers)
