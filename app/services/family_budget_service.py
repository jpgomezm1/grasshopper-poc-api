"""La calculadora financiera del acudiente · P8.

Verónica (Padres de Familia, Paso 2): *"Calculadora Financiera. Módulo PRIVADO
para ingresar presupuesto disponible para la educación de su hijo."*

## Qué la hace una calculadora y no un campo de texto

Guardar un número no le sirve de nada a nadie. Lo que un padre quiere saber al
escribir "15.000 USD" es **qué compra eso**: cuántas de las opciones reales
caen dentro, cuáles se quedan cerca, y cuál es el rango de lo que hay.

Eso se puede responder porque el catálogo de ofertas SÍ tiene precios — los 17
los tienen. Es la diferencia con la College List, donde 0 de 2.562 programas
tienen datos de admisión y por eso no se puede clasificar nada.

## Privado quiere decir privado

El presupuesto del acudiente **no toca** `User.budget_band` ni
`User.budget_max_usd`, que son del estudiante y las lee su recomendador. Si lo
hiciera, al hijo le cambiarían las recomendaciones sin saber por qué — y de ahí
a inferir la cifra de su familia hay un paso.

Este módulo sólo lee el catálogo y responde al padre. No escribe nada del
estudiante, y nada de aquí viaja a su pantalla ni a su reporte al colegio.

## Lo que NO hace: convertir monedas

Si el padre declara COP y las ofertas están en USD, no se inventa una tasa. Se
dice que no se puede comparar y ya. Una tasa desactualizada en una decisión de
educación es peor que no dar el dato: la familia planearía sobre un número
falso.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.data.ofertas import OFERTAS
from app.db.models import FamilyBudget, ParentRelationship, User

logger = logging.getLogger(__name__)

MONEDAS_VALIDAS = ("USD", "COP", "EUR")


class DatoInvalido(ValueError):
    """Lo que el acudiente escribió no puede ser cierto · se le dice cuál."""


def relacion_activa(
    db: DBSession, parent: User, student_id
) -> Optional[ParentRelationship]:
    """La relación viva entre este acudiente y ese hijo, o `None`.

    `is_active` es una revocación blanda (divorcio, cambio de custodia). Un
    acudiente revocado no debe poder leer ni escribir el presupuesto por esta
    puerta, así que se filtra aquí y no en cada llamada.
    """
    return (
        db.query(ParentRelationship)
        .filter(
            ParentRelationship.parent_user_id == parent.id,
            ParentRelationship.student_user_id == student_id,
            ParentRelationship.is_active.is_(True),
        )
        .first()
    )


def obtener(db: DBSession, relacion: ParentRelationship) -> Optional[FamilyBudget]:
    return (
        db.query(FamilyBudget)
        .filter(FamilyBudget.parent_relationship_id == relacion.id)
        .first()
    )


def guardar(
    db: DBSession, relacion: ParentRelationship, datos: Dict[str, Any]
) -> FamilyBudget:
    """Crea o actualiza · valida antes de tocar la fila."""
    monto = datos.get("anual_max")
    moneda = (datos.get("moneda") or "").upper() or None

    if monto is not None:
        if int(monto) < 0:
            raise DatoInvalido("El presupuesto no puede ser negativo.")
        if not moneda:
            raise DatoInvalido("Falta la moneda: 15.000 no es lo mismo en dólares que en pesos.")
    if moneda and moneda not in MONEDAS_VALIDAS:
        raise DatoInvalido(
            f"Moneda no reconocida. Las que manejamos: {', '.join(MONEDAS_VALIDAS)}."
        )

    presupuesto = obtener(db, relacion)
    if presupuesto is None:
        presupuesto = FamilyBudget(parent_relationship_id=relacion.id)
        db.add(presupuesto)

    presupuesto.anual_max = monto
    presupuesto.moneda = moneda
    presupuesto.con_financiacion = datos.get("con_financiacion")
    presupuesto.nota = (datos.get("nota") or "").strip()[:2000] or None
    presupuesto.updated_at = datetime.utcnow()

    db.flush()
    return presupuesto


def _precio(oferta: Dict[str, Any]) -> tuple[Optional[int], Optional[int], Optional[str]]:
    costo = oferta.get("cost") or {}
    return costo.get("min"), costo.get("max"), costo.get("currency")


def que_alcanza(presupuesto: Optional[FamilyBudget]) -> Dict[str, Any]:
    """Qué compra ese presupuesto, contra el catálogo real.

    Devuelve siempre la misma forma, aunque no haya presupuesto: así la
    pantalla puede mostrar el rango de lo que existe incluso antes de que el
    acudiente escriba nada — que es justo cuando más le sirve saberlo.
    """
    con_precio = [
        (o, *_precio(o)) for o in OFERTAS if (_precio(o)[0] is not None)
    ]

    monedas = {c for (_o, _mn, _mx, c) in con_precio if c}

    # El rango va SEPARADO POR MONEDA, no en un solo mínimo-máximo global.
    # Juntarlas daría "de 500 a 18.000 EUR/USD", que es exactamente lo que
    # este módulo promete no hacer dos párrafos más abajo cuando se niega a
    # convertir. Y el denominador de aquí es el mismo que el de
    # `alcanzables.de`, así que el acudiente no lee 17 arriba y 10 abajo sin
    # que nadie le explique de dónde salió la diferencia.
    rangos = []
    for moneda in sorted(monedas):
        de_esa = [
            (mn, mx) for (_o, mn, mx, c) in con_precio if c == moneda
        ]
        minimos = [mn for (mn, _mx) in de_esa if mn is not None]
        maximos = [mx for (_mn, mx) in de_esa if mx is not None]
        rangos.append({
            "moneda": moneda,
            "min": min(minimos) if minimos else None,
            "max": max(maximos) if maximos else None,
            "cuantas": len(de_esa),
        })

    resultado: Dict[str, Any] = {
        "total_con_precio": len(con_precio),
        "rangos_por_moneda": rangos,
        "alcanzables": None,
        "cerca": None,
        "aviso": None,
    }

    if presupuesto is None or presupuesto.anual_max is None or not presupuesto.moneda:
        return resultado

    # Nada de tasas de cambio inventadas · ver la cabecera.
    comparables = [
        (o, mn, mx) for (o, mn, mx, c) in con_precio if c == presupuesto.moneda
    ]
    if not comparables:
        resultado["aviso"] = (
            f"Las opciones del catálogo están en {', '.join(sorted(monedas)) or 'otra moneda'} "
            f"y tu presupuesto en {presupuesto.moneda}. No las convertimos con una tasa "
            "nuestra: preferimos no darte un número que podría estar desactualizado."
        )
        return resultado

    techo = presupuesto.anual_max
    dentro = [o for (o, mn, _mx) in comparables if mn is not None and mn <= techo]
    # "Cerca" = hasta un 25% por encima · es el rango donde una beca, un
    # crédito o ahorrar un año más lo vuelven posible, y esconderlo dejaría a
    # la familia sin ver opciones que sí están a su alcance.
    cerca = [
        o
        for (o, mn, _mx) in comparables
        if mn is not None and techo < mn <= techo * 1.25
    ]

    resultado["alcanzables"] = {
        "cuantas": len(dentro),
        "de": len(comparables),
        "ejemplos": [o["name"] for o in dentro[:3]],
    }
    resultado["cerca"] = {
        "cuantas": len(cerca),
        "ejemplos": [o["name"] for o in cerca[:3]],
    }
    return resultado


def a_diccionario(presupuesto: Optional[FamilyBudget]) -> Dict[str, Any]:
    """La forma que ve el acudiente · con el vacío explícito, no ausente."""
    return {
        "anual_max": presupuesto.anual_max if presupuesto else None,
        "moneda": presupuesto.moneda if presupuesto else None,
        "con_financiacion": presupuesto.con_financiacion if presupuesto else None,
        "nota": presupuesto.nota if presupuesto else None,
        "updated_at": presupuesto.updated_at.isoformat() if presupuesto else None,
        "que_alcanza": que_alcanza(presupuesto),
    }
