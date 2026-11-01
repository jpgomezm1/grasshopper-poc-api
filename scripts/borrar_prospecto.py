"""Borrar los datos de un prospecto que lo pide · Habeas Data (X-5, Sprint 4).

El consentimiento del bot gratuito le dice a la persona *"Puedo pedir que los
borren cuando quiera"* (Ley 1581/2012, derecho de supresión). Hasta este script
no había cómo cumplirlo.

## Procedimiento

1. La persona lo pide (correo, WhatsApp, o a través del equipo comercial).
2. Se corre SIN `--aplicar` para ver qué se encontró con ese contacto.
3. Se corre con `--aplicar`. Queda en la auditoría (`prospecto.suprimido`) con
   cuántas filas se borraron, sin guardar el contacto (sería guardar justo lo
   que pidió borrar).
4. Se le confirma a la persona.

Borra los prospectos de las tres fuentes (bot gratuito, perfilador, quiz). Si la
persona además tiene cuenta, borrar la cuenta es otro procedimiento: lo hace la
propia persona desde su perfil, o soporte con `privacy.py`.

    ./venv/Scripts/python scripts/borrar_prospecto.py --email persona@correo.com
    ./venv/Scripts/python scripts/borrar_prospecto.py --telefono "+57 300 000 0000" --aplicar

⚠️ `DATABASE_URL` del `.env` local es la base de PRODUCCIÓN. `--aplicar` borra ahí.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email")
    parser.add_argument("--telefono")
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args()
    if not args.email and not args.telefono:
        parser.error("hace falta --email o --telefono")

    from app.db.database import SessionLocal
    from app.services import prospectos_service
    from app.services.audit_service import log_action

    db = SessionLocal()
    try:
        cuenta = prospectos_service.borrar_por_contacto(
            db, email=args.email, telefono=args.telefono, aplicar=args.aplicar
        )
        print(f"Encontrados: {cuenta}")
        if args.aplicar and any(cuenta.values()):
            log_action(
                db, user=None, action="prospecto.suprimido", resource_type="prospecto",
                payload={"filas": cuenta, "por": "email" if args.email else "telefono"},
            )
            print("BORRADOS y registrados en la auditoría.")
        elif not args.aplicar:
            print("Simulación: nada se borró. Usa --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
