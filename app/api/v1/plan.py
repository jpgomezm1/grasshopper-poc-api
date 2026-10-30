"""El plan del usuario · `GET /me/plan` (D-1, Sprint 4).

Solo informa: hoy no bloquea nada. El front lo va a leer para el muro de pago
(D-4) y el backend para bloquear las funciones pagas (D-3). La regla vive en
`app/services/plan_service.py` y solo ahí.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services import permisos_service, plan_service

router = APIRouter(prefix="/me", tags=["Plan"])


class PlanResponse(BaseModel):
    # gratis · pago · vip
    plan: str
    # rol · licencia · propio · ninguno
    origen: str
    hasta: Optional[datetime] = None


@router.get("/plan", response_model=PlanResponse)
def mi_plan(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlanResponse:
    p = plan_service.plan_vigente(db, current_user)
    return PlanResponse(plan=p.plan, origen=p.origen, hasta=p.hasta)


# ---------------------------------------------------------------------------
# D-2 · qué puede usar · plan × grado × la matriz de `app/data/permisos.py`
# ---------------------------------------------------------------------------


class AccesoOut(BaseModel):
    permitido: bool
    # plan · no_es_de_su_grado · no_disponible
    motivo: Optional[str] = None
    plan_requerido: Optional[str] = None


class PermisosResponse(BaseModel):
    plan: str
    origen: str
    # grado_9 · grado_10 · grado_11 · grado_12 · profesional · None si no se sabe
    tramo: Optional[str]
    funciones: Dict[str, AccesoOut]
    tests: Dict[str, AccesoOut]
    ingles: AccesoOut


def _a(acceso) -> AccesoOut:
    return AccesoOut(
        permitido=acceso.permitido, motivo=acceso.motivo, plan_requerido=acceso.plan_requerido,
    )


@router.get("/permisos", response_model=PermisosResponse)
def mis_permisos(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PermisosResponse:
    """Qué puede usar, y si no, por qué · el front pinta candados con esto (D-4)."""
    p = permisos_service.permisos(db, current_user)
    return PermisosResponse(
        plan=p.plan,
        origen=p.origen,
        tramo=p.tramo,
        funciones={k: _a(v) for k, v in p.funciones.items()},
        tests={k: _a(v) for k, v in p.tests.items()},
        ingles=_a(p.ingles),
    )
