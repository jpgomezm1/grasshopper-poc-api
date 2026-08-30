"""La ficha académica del estudiante · `GET/PUT /me/academic-profile`.

Verónica (Paso 3 · College List): *"para construir esto es importante
preguntarle al estudiante su GPA (promedio acumulado) y su sistema de colegio
… ¿tienes AP? ¿cuántas? ¿qué puntajes? ¿tienes SAT?"*.

AH eligió (2026-08-30) que viva en "Mi perfil" como una ficha que el estudiante
llena y **actualiza**: las notas suben, el SAT se repite, el IB previsto
cambia. Un dato congelado en el onboarding envejece mal justo en el año en que
más importa.

## Sólo el dueño

No hay `student_id` en ninguna ruta: se lee y se escribe la ficha de quien
llama. Un parámetro ahí sería la puerta para editarle las notas a otro.

El staff del colegio y los asesores ven estos datos por sus propios canales
(el dossier, el reporte que el estudiante les manda), que ya tienen su control
de acceso. Duplicar aquí una vista para ellos sería un segundo permiso que
mantener sincronizado.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import academic_profile_service as servicio

router = APIRouter(prefix="/me/academic-profile", tags=["Ficha académica"])


class MateriaAP(BaseModel):
    materia: str = Field(max_length=120)
    # Opcional: se puede estar cursando un AP y todavía no tener puntaje.
    puntaje: Optional[int] = None


class FichaIn(BaseModel):
    gpa: Optional[float] = None
    gpa_scale: Optional[float] = None
    sat_score: Optional[int] = None
    sat_taken_on: Optional[date] = None
    ap_scores: Optional[List[MateriaAP]] = None
    ib_predicted_total: Optional[int] = None


def _solo_estudiante(user: User) -> None:
    # La ficha es del estudiante. Un padre o un asesor que quiera ver estos
    # datos los tiene por sus propios canales, con su propio permiso.
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta ficha es del estudiante.",
        )


@router.get("")
def leer(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """La ficha de quien llama · con las claves en `None` si está vacía."""
    _solo_estudiante(current_user)
    return servicio.a_diccionario(servicio.obtener(db, current_user))


@router.put("")
def guardar(
    ficha: FichaIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Crea o actualiza · valida todo antes de tocar nada.

    Los errores salen como 422 con el motivo en español: el estudiante tiene
    que poder corregirlo sin adivinar. Un promedio de 42 o un SAT de 95 no son
    "datos imperfectos" — harían que el producto le dijera que una universidad
    es alcanzable cuando no lo es.
    """
    _solo_estudiante(current_user)
    try:
        guardada = servicio.guardar(
            db,
            current_user,
            {
                **ficha.model_dump(exclude={"ap_scores"}),
                "ap_scores": [m.model_dump() for m in (ficha.ap_scores or [])],
            },
        )
    except servicio.DatoInvalido as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    db.commit()
    db.refresh(guardada)
    return servicio.a_diccionario(guardada)
