"""Avisa a los estudiantes cuyo plan vence pronto · D-5, Sprint 4.

Pensado para correr **una vez al día** (Heroku Scheduler; el backend no tiene
programador propio). No guarda estado: avisa cuando al plan le quedan
**exactamente 15 días** y otra vez a los **3**. Una corrida diaria manda cada
aviso una sola vez; si un día no corre, ese aviso se pierde (es un recordatorio,
no un cobro).

Pasar a `gratis` NO necesita este script: un plan vencido deja de contar solo
(`plan_service.plan_vigente`).

Uso:
    ./venv/Scripts/python scripts/avisar_vencimientos_planes.py            # muestra a quién avisaría
    ./venv/Scripts/python scripts/avisar_vencimientos_planes.py --enviar   # manda los correos

⚠️ `DATABASE_URL` del `.env` local es la base de PRODUCCIÓN.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DIAS_DE_AVISO = (15, 3)


def a_quien_avisar(db: Any, hoy: Optional[date] = None) -> List[dict]:
    """Planes propios vigentes que vencen en exactamente 15 o 3 días."""
    from app.db.models import User, UserPlan
    from app.services import plan_service

    hoy = hoy or date.today()
    fechas = {hoy + timedelta(days=d): d for d in DIAS_DE_AVISO}
    inicio = datetime.combine(min(fechas), datetime.min.time())
    fin = datetime.combine(max(fechas), datetime.max.time())
    candidatos = (
        db.query(UserPlan)
        .filter(UserPlan.hasta.isnot(None), UserPlan.hasta >= inicio, UserPlan.hasta <= fin)
        .all()
    )
    avisos = []
    ahora = datetime.combine(hoy, datetime.min.time())
    for fila in candidatos:
        dias = fechas.get(fila.hasta.date())
        if dias is None:
            continue
        u = db.query(User).filter(User.id == fila.user_id).first()
        if u is None:
            continue
        vigente = plan_service.plan_vigente(db, u, ahora)
        # Solo si ESTA fila es la que rige: si ya renovó, no se le avisa.
        if vigente.origen != "propio" or vigente.hasta != fila.hasta:
            continue
        avisos.append({"user": u, "plan": fila.plan, "hasta": fila.hasta, "dias": dias})
    return avisos


def enviar(aviso: dict) -> None:
    from app.services.email_service import send_email

    u = aviso["user"]
    nombre_plan = "VIP" if aviso["plan"] == "vip" else "pago"
    send_email(
        to=u.email,
        subject=f"Tu plan {nombre_plan} de Mentoring vence en {aviso['dias']} días",
        html_body=(
            f"<p>Hola{(' ' + u.name.split()[0]) if u.name else ''}:</p>"
            f"<p>Tu plan {nombre_plan} vence el {aviso['hasta']:%d/%m/%Y}. Si quieres renovarlo, "
            "escríbele a tu asesor o responde este correo.</p>"
            "<p>Lo que ya hiciste en Mentoring (tus tests y tu hoja de vida) sigue siendo tuyo.</p>"
            "<p>Hopper, de Mentoring</p>"
        ),
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
            print(f"  {a['dias']:>2} días · {a['user'].email} · plan {a['plan']} · vence {a['hasta']:%Y-%m-%d}")
            if args.enviar:
                enviar(a)
        print(f"\n{len(avisos)} aviso(s) · {'ENVIADOS' if args.enviar else 'simulación, usa --enviar'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
