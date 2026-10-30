"""Qué puede usar un usuario · plan (D-1) × grado × la matriz de `app/data/permisos.py` (D-2).

Una sola pregunta y una sola función: `permisos(db, user)`. El front la lee por
`GET /me/permisos` para mostrar candados (D-4) y el backend la usa para negar
(D-3). Ninguno de los dos decide por su cuenta.

Cada función y cada test dice si se puede usar y, si no, por qué:

- `plan`               · su plan no lo incluye (`plan_requerido` dice cuál sí).
- `no_es_de_su_grado`  · existe, pero no es de su etapa (D1: cada grado ve lo suyo).
- `no_disponible`      · el demo lo pide y todavía no existe en la plataforma.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.data import permisos as matriz
from app.services import plan_service


@dataclass(frozen=True)
class Acceso:
    permitido: bool
    motivo: Optional[str] = None          # plan · no_es_de_su_grado · no_disponible
    plan_requerido: Optional[str] = None


@dataclass
class Permisos:
    plan: str
    origen: str
    tramo: Optional[str]
    funciones: Dict[str, Acceso] = field(default_factory=dict)
    tests: Dict[str, Acceso] = field(default_factory=dict)
    ingles: Acceso = field(default_factory=lambda: Acceso(False))


def tramo_de(user: Any) -> Optional[str]:
    """La ruta de la malla (grado_9…12, profesional) o None si no se sabe."""
    from app.api.v1.onboarding_chat import _hechos_del_usuario
    from app.data import onboarding_hechos as catalogo

    hechos = _hechos_del_usuario(user)
    if not hechos.get("grade") and getattr(user, "grade", None):
        hechos["grade"] = str(user.grade)
    return catalogo.ruta(hechos)


def _alcanza(plan: str, requerido: str) -> bool:
    return matriz.ORDEN_PLAN.get(plan, 0) >= matriz.ORDEN_PLAN[requerido]


def _todos_los_tests() -> tuple:
    vistos: list = []
    for ids in matriz.TESTS_POR_TRAMO.values():
        for t in ids:
            if t not in vistos:
                vistos.append(t)
    return tuple(vistos)


def permisos(db: Any, user: Any) -> Permisos:
    from app.db.models import UserRole

    p = plan_service.plan_vigente(db, user)
    tramo = tramo_de(user) if user.role == UserRole.STUDENT else None
    # Quien no es estudiante (equipo, colegio, acudiente) no se filtra por grado.
    sin_filtro_de_grado = user.role != UserRole.STUDENT or tramo is None
    resultado = Permisos(plan=p.plan, origen=p.origen, tramo=tramo)

    for clave, spec in matriz.FUNCIONES.items():
        requerido = spec["plan"]
        if clave in matriz.NO_DISPONIBLE:
            acceso = Acceso(False, "no_disponible", requerido)
        elif not _alcanza(p.plan, requerido):
            acceso = Acceso(False, "plan", requerido)
        elif (
            not sin_filtro_de_grado
            and clave in matriz.FUNCION_SOLO_EN_TRAMOS
            and tramo not in matriz.FUNCION_SOLO_EN_TRAMOS[clave]
        ):
            acceso = Acceso(False, "no_es_de_su_grado", requerido)
        else:
            acceso = Acceso(True)
        resultado.funciones[clave] = acceso

    puede_tests = _alcanza(p.plan, matriz.FUNCIONES["tests"]["plan"])
    de_su_grado = matriz.TESTS_POR_TRAMO.get(tramo, ()) if tramo else ()
    for test_id in _todos_los_tests():
        if not sin_filtro_de_grado and test_id not in de_su_grado:
            resultado.tests[test_id] = Acceso(False, "no_es_de_su_grado", "pago")
        elif not puede_tests:
            resultado.tests[test_id] = Acceso(False, "plan", "pago")
        else:
            resultado.tests[test_id] = Acceso(True)

    if not sin_filtro_de_grado and tramo not in matriz.INGLES_EN_TRAMOS:
        resultado.ingles = Acceso(False, "no_es_de_su_grado", "pago")
    elif not puede_tests:
        resultado.ingles = Acceso(False, "plan", "pago")
    else:
        resultado.ingles = Acceso(True)
    return resultado


def puede(db: Any, user: Any, funcion: str) -> Acceso:
    """Atajo para el bloqueo en el backend (D-3)."""
    return permisos(db, user).funciones[funcion]


def puede_test(db: Any, user: Any, test_id: str) -> Acceso:
    """Atajo para el bloqueo en el backend (D-3). Un test fuera de la matriz no se bloquea."""
    return permisos(db, user).tests.get(test_id, Acceso(True))
