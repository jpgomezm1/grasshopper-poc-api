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

from app.api.v1.llave_plan import requiere  # noqa: E402

# D-3 · Sprint 4 · la llave del plan, para TODO este router: la práctica de SAT e IELTS es pago, y solo de 11°, 12° y profesional.
# Ver `app/api/v1/llave_plan.py` y la matriz en `app/data/permisos.py`.
router = APIRouter(prefix="/exam-prep", tags=["Exam Prep"], dependencies=[Depends(requiere("practica_examenes"))])


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

    I-1 · Sprint 4 · trae solo los ejercicios que el estudiante no ha
    respondido (`exam_practice_seen`), así que no se repiten entre visitas.
    Cuando ya respondió todo, `items` viene vacío y `exhausted` en `true`: la
    pantalla lo dice y ofrece empezar de nuevo (`DELETE …/practice/seen`).

    `round` se sigue aceptando por compatibilidad, pero con memoria ya no
    decide nada: era la forma de no repetir cuando no se guardaba qué había
    visto cada quien.
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
    db: DBSession = Depends(get_db),
):
    """Corrige lo respondido y devuelve la explicación de CADA ejercicio.

    La explicación viaja también cuando la respuesta fue correcta: acertar por
    descarte y no saber por qué es el escenario que esta práctica intenta evitar.

    I-1 · Sprint 4 · además marca esos ejercicios como respondidos, para que la
    siguiente tanda no los repita. Se marca AQUÍ y no al entregar la tanda: si
    la persona contesta 3 de 10 y se va, los otros 7 tienen que volver a salir.
    No se guarda si acertó.
    """
    _examen_o_404(exam_id)
    resultado = exam_prep_service.evaluar(exam_id, request.answers)
    exam_prep_service.registrar_respondidos(
        db, current_user, exam_id, [r["id"] for r in resultado.get("results", [])],
    )
    return resultado


@router.delete("/{exam_id}/practice/seen")
def reiniciar_practica(
    exam_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Olvida lo respondido de este examen · "empezar de nuevo".

    Lo ofrece la pantalla cuando ya practicó todo el banco. Solo afecta a quien
    lo pide y solo a este examen.
    """
    _examen_o_404(exam_id)
    return {
        "exam": exam_id,
        "reset": exam_prep_service.reiniciar(db, current_user, exam_id),
        "disclaimer": banco.AVISO_NO_OFICIAL,
    }
