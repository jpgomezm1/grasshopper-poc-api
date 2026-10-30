"""El plan vigente de un usuario · UNA función decide (D-1, Sprint 4).

Regla, en este orden (decisiones D1, D2 y D9 de JP, 2026-10-29):

1. **No es estudiante** (equipo, colegio, papá/mamá) → `pago`, origen `rol`.
   Los planes son del estudiante; a quien lo acompaña no se le bloquea nada por
   esta vía (lo que ve papá/mamá según el plan del hijo es D-7).
2. **Su colegio tiene licencia vigente** → `pago`, origen `licencia`. Se
   calcula, no se guarda: si la licencia vence, cambia solo.
3. **Tiene un plan propio vigente** (`user_plans`) → ese, origen `propio`.
4. **Nada de lo anterior** → `gratis`.

Por qué una sola función: este repo ya sufrió "dos sitios decidiendo lo mismo"
(ver `journey-compass/CLAUDE.md`, el bug P0-8). Todo lo que necesite saber el
plan —el bloqueo en el backend (D-3), el muro de pago en el front (D-4), el
panel de la agencia (D-5)— llama a `plan_vigente`.

Hoy esto NO bloquea nada: solo informa. El bloqueo es D-2/D-3.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

PLAN_GRATIS = "gratis"
PLAN_PAGO = "pago"
PLAN_VIP = "vip"
PLANES = (PLAN_GRATIS, PLAN_PAGO, PLAN_VIP)


@dataclass(frozen=True)
class PlanVigente:
    plan: str
    # rol · licencia · propio · ninguno
    origen: str
    # Hasta cuándo, si se sabe · None = sin vencimiento o no aplica.
    hasta: Optional[datetime] = None


def plan_propio_vigente(db: Any, user_id: Any, ahora: Optional[datetime] = None) -> Optional[Any]:
    """La fila de `user_plans` que rige hoy · la más reciente que esté vigente."""
    from sqlalchemy import or_

    from app.db.models import UserPlan

    ahora = ahora or datetime.utcnow()
    return (
        db.query(UserPlan)
        .filter(
            UserPlan.user_id == user_id,
            UserPlan.desde <= ahora,
            or_(UserPlan.hasta.is_(None), UserPlan.hasta > ahora),
        )
        .order_by(UserPlan.desde.desc(), UserPlan.creado_en.desc())
        .first()
    )


def plan_vigente(db: Any, user: Any, ahora: Optional[datetime] = None) -> PlanVigente:
    from app.db.models import UserRole
    from app.services.license_service import licencia_vigente

    if user.role != UserRole.STUDENT:
        return PlanVigente(PLAN_PAGO, "rol")

    if user.school_id is not None:
        lic = licencia_vigente(db, user.school_id)
        if lic is not None:
            return PlanVigente(PLAN_PAGO, "licencia", lic.expires_at)

    propio = plan_propio_vigente(db, user.id, ahora)
    if propio is not None and propio.plan in PLANES:
        return PlanVigente(propio.plan, "propio", propio.hasta)

    return PlanVigente(PLAN_GRATIS, "ninguno")
