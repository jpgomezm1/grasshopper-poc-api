"""Materias electivas recomendadas · reunión clienta 2026-08-24 (min. 27:00).

    "Si yo he puesto en decimo que quiero estudiar ingenieria, el sistema
    deberia poderme decir si en tu colegio tienes matematicas avanzadas,
    calculo, geometria avanzada, pues esas son las materias que deberias
    escoger como electivas."

Solo lectura, solo el propio estudiante (mismo patrón que `/me/activities` y
`/me/study-preferences`): no hay nada que escribir aquí, la recomendación se
deriva de datos que ya existen (`study_area` del onboarding + `grade` +
`School.subjects_offered`, si el colegio ya lo cargó).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.schemas.electives import ElectivesResponse
from app.services.electives_service import recommend_electives

router = APIRouter(prefix="/me/electives", tags=["StudentMe · Electives"])


@router.get(
    "",
    response_model=ElectivesResponse,
    summary="Materias electivas recomendadas para el área de estudio ya declarada",
)
def get_my_electives(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )
    data = recommend_electives(db, current_user)
    return ElectivesResponse(**data)
