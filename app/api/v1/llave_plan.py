"""La llave del plan · negar en el BACKEND lo que el plan o el grado no abren (D-3, Sprint 4).

Dependencias de FastAPI que consultan `permisos_service` (la matriz de D-2) y,
si no alcanza, responden **402** con un detalle que el front entiende:

    {"code": "plan_requerido", "message": "...", "funcion": "...",
     "plan_requerido": "pago", "motivo": "plan"}

`message` es lo que `apiFetch` muestra si nadie lo atrapa; el muro de pago
(D-4) lee el resto para decir qué plan lo abre.

## Qué se bloquea y qué no

Se bloquea lo que CREA o GENERA (responder un test, generar una lectura, usar
el chat, buscar programas…). No se bloquea LEER lo que la persona ya hizo: si
baja de plan, no pierde sus resultados ni su hoja de vida guardada; solo deja
de poder hacer cosas nuevas. Por eso la llave va en endpoints concretos y no
en todos los de un estudiante.

Solo aplica a estudiantes: equipo, colegio y acudientes salen con plan `pago`
(origen `rol`) y pasan siempre.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services import permisos_service
from app.services.permisos_service import Acceso

CODIGO = "plan_requerido"

_MENSAJE = {
    "plan": "Esto es parte del plan {plan}. Un asesor te puede ayudar a activarlo.",
    "no_es_de_su_grado": "Esto no hace parte de tu etapa.",
    "no_disponible": "Esto todavía no está disponible.",
}


def _negar(funcion: str, acceso: Acceso) -> HTTPException:
    plan = acceso.plan_requerido or "pago"
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "code": CODIGO,
            "message": _MENSAJE.get(acceso.motivo or "plan", _MENSAJE["plan"]).format(
                plan="VIP" if plan == "vip" else "pago",
            ),
            "funcion": funcion,
            "plan_requerido": plan,
            "motivo": acceso.motivo,
        },
    )


def requiere(funcion: str) -> Callable:
    """`dependencies=[Depends(requiere("chat_hopper"))]` en un endpoint o un router."""

    def _llave(
        db: DBSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> None:
        acceso = permisos_service.puede(db, current_user, funcion)
        if not acceso.permitido:
            raise _negar(funcion, acceso)

    return _llave


def requiere_test(
    test_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Para rutas con `{test_id}` · el plan Y el grado de ese test."""
    acceso = permisos_service.puede_test(db, current_user, test_id)
    if not acceso.permitido:
        raise _negar(f"test:{test_id}", acceso)


def requiere_ingles(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    acceso = permisos_service.permisos(db, current_user).ingles
    if not acceso.permitido:
        raise _negar("ingles", acceso)


def requiere_lectura_nueva(
    only_cached: bool = False,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """La lectura de un test: generarla es pago; leer una ya guardada
    (`?only_cached=true`, lo que usan el perfil y el PDF) no se bloquea."""
    if only_cached:
        return
    acceso = permisos_service.puede(db, current_user, "lectura_tests")
    if not acceso.permitido:
        raise _negar("lectura_tests", acceso)
