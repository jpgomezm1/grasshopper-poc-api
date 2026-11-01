"""Avisa a los estudiantes que una fecha límite de aplicación se acerca · E-4, Sprint 4.

Pensado para correr **una vez al día** (Heroku Scheduler; el backend no tiene
programador propio). Manda una notificación en la app cuando a una aplicación
le quedan **14, 7 o 1 día(s)**.

A diferencia de `avisar_vencimientos_planes.py`, aquí sí se mira qué ya se
avisó (en las notificaciones de la persona): si un día no corre, al siguiente
manda el aviso que toca y no se pierde. Y nunca manda dos veces el mismo
umbral de la misma aplicación. Si la persona cambia la fecha, se avisa de
nuevo contra la fecha nueva.

Uso:
    ./venv/Scripts/python scripts/avisar_fechas_aplicacion.py            # muestra a quién avisaría
    ./venv/Scripts/python scripts/avisar_fechas_aplicacion.py --enviar   # crea las notificaciones
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

UMBRALES = (14, 7, 1)
TIPO = "aplicacion.fecha_cercana"


def _umbral(dias: int) -> Optional[int]:
    """El aviso que toca con N días restantes: el umbral más chico que aún los cubre."""
    candidatos = [u for u in UMBRALES if dias <= u]
    return min(candidatos) if candidatos else None


def a_quien_avisar(db: Any, hoy: Optional[date] = None) -> List[dict]:
    from app.db.models import AplicacionUniversidad, Notification

    hoy = hoy or date.today()
    filas = (
        db.query(AplicacionUniversidad)
        .filter(
            AplicacionUniversidad.fecha_limite.isnot(None),
            AplicacionUniversidad.fecha_limite >= hoy,
            AplicacionUniversidad.fecha_limite <= hoy + timedelta(days=max(UMBRALES)),
        )
        .all()
    )
    avisos = []
    for a in filas:
        dias = (a.fecha_limite - hoy).days
        umbral = _umbral(dias)
        if umbral is None:
            continue
        ya = (
            db.query(Notification)
            .filter(Notification.user_id == a.user_id, Notification.type == TIPO)
            .all()
        )
        enviado = any(
            (n.data or {}).get("aplicacion_id") == str(a.id)
            and (n.data or {}).get("umbral") == umbral
            and (n.data or {}).get("fecha_limite") == a.fecha_limite.isoformat()
            for n in ya
        )
        if not enviado:
            avisos.append({"aplicacion": a, "dias": dias, "umbral": umbral})
    return avisos


def enviar(db: Any, aviso: dict) -> None:
    from app.services import kit_aplicacion_service as kit
    from app.services.notifications_service import create_notification

    a = aviso["aplicacion"]
    dias = aviso["dias"]
    datos = kit.serializar(a)
    faltan = datos["total"] - datos["listos"]
    cuando = "mañana" if dias == 1 else "hoy" if dias == 0 else f"en {dias} días"
    cuerpo = (
        f"Te faltan {faltan} de {datos['total']} cosas del kit."
        if faltan
        else "Ya tienes todo el kit listo. Confirma que la enviaste."
    )
    create_notification(
        db,
        user_id=a.user_id,
        type=TIPO,
        title=f"La fecha límite de {a.universidad} es {cuando}",
        body=cuerpo,
        data={
            "navigate_to": "/aplicaciones",
            "aplicacion_id": str(a.id),
            "umbral": aviso["umbral"],
            "fecha_limite": a.fecha_limite.isoformat(),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--enviar", action="store_true")
    args = parser.parse_args()

    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        avisos = a_quien_avisar(db)
        for a in avisos:
            ap = a["aplicacion"]
            print(f"  {a['dias']:>2} días · {ap.universidad} · user {ap.user_id} · vence {ap.fecha_limite}")
            if args.enviar:
                enviar(db, a)
        print(f"\n{len(avisos)} aviso(s) · {'ENVIADOS' if args.enviar else 'simulación, usa --enviar'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
