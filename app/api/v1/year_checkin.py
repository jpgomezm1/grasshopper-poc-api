"""Memoria entre años · `GET /api/v1/year-checkin`.

Fase 2 de 4 de la malla completa (Cimientos = fase 1, migración 067). Expone
al frontend la comparación "qué dijo el año pasado vs qué dice hoy" y, cuando
corresponde (`is_new_grade=True`), el mensaje de check-in con el que debería
arrancar la conversación en vez del onboarding normal.

No requiere body ni query params: opera siempre sobre `current_user`, igual
que `/onboarding-chat/inicio` — es información propia, no de un tercero, así
que no hay superficie IDOR que verificar (a diferencia de `/snapshots/*`, que
sí recibe un `session_id` ajeno).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.schemas.year_memory import (
    AnioAnteriorOut,
    HoyOut,
    PerfilDeclaradoOut,
    TestTomadoOut,
    YearCheckinResponse,
)
from app.services.year_checkin_service import build_checkin_message
from app.services.year_memory_service import PerfilDeclarado, get_year_comparison

router = APIRouter(prefix="/year-checkin", tags=["Memoria entre años"])


def _perfil_out(perfil: PerfilDeclarado) -> PerfilDeclaradoOut:
    return PerfilDeclaradoOut(
        pasion=perfil.pasion,
        hobbies=perfil.hobbies,
        fortalezas=perfil.fortalezas,
        objetivo=perfil.objetivo,
        interes_exterior=perfil.interes_exterior,
        paises=perfil.paises,
        presupuesto=perfil.presupuesto,
    )


@router.get("", response_model=YearCheckinResponse)
def year_checkin(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> YearCheckinResponse:
    comparacion = get_year_comparison(db, current_user)

    # La llamada a la IA sólo ocurre cuando hay algo que decir · ver
    # `year_checkin_service.build_checkin_message` (devuelve None de una vez
    # si `is_new_grade` es False, sin gastar una llamada).
    mensaje = build_checkin_message(db, current_user, comparacion)

    previous_out = None
    if comparacion.previous is not None:
        previous_out = AnioAnteriorOut(
            school_year=comparacion.previous.school_year,
            grade=comparacion.previous.grade,
            perfil=_perfil_out(comparacion.previous.perfil),
            tests_available=comparacion.previous.tests_available,
            route_available=comparacion.previous.route_available,
        )

    today_out = HoyOut(
        grade=comparacion.today.grade,
        perfil=_perfil_out(comparacion.today.perfil),
        tests_taken=[
            TestTomadoOut(test_id=t["test_id"], taken_at=t["taken_at"])
            for t in comparacion.today.tests_taken
        ],
        active_routes=comparacion.today.active_routes,
    )

    return YearCheckinResponse(
        has_memory=comparacion.has_memory,
        is_new_grade=comparacion.is_new_grade,
        previous=previous_out,
        today=today_out,
        changed_fields=comparacion.changed_fields,
        checkin_message=mensaje,
    )
