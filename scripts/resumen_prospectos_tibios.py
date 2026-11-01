"""Resumen diario de prospectos tibios para el equipo comercial (G-4, Sprint 4).

Los calientes avisan al momento (`aviso_prospectos.avisar_caliente`). Los tibios
no ameritan un correo cada uno, pero sí que alguien los mire en el día: su ruta
sugerida es ofrecerles el perfilamiento. Este script manda UN correo con los
tibios nuevos de las últimas 24 horas, a los mismos destinatarios del aviso de
calientes (`AVISO_PROSPECTOS_EMAIL` o los comerciales activos).

Para Heroku Scheduler, una vez al día (sugerido: 7:00 hora Colombia = 12:00 UTC):

    python scripts/resumen_prospectos_tibios.py --enviar

**No está activado.** Activarlo es decisión de JP. Sin `--enviar` solo muestra
qué mandaría. Si no hubo tibios, no manda nada.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--enviar", action="store_true")
    args = parser.parse_args()

    from datetime import datetime, timedelta

    from app.db.database import SessionLocal
    from app.services import aviso_prospectos, prospectos_service

    db = SessionLocal()
    try:
        if args.enviar:
            n = aviso_prospectos.resumen_tibios(db)
            print(f"{n} tibio(s) · ENVIADO a {', '.join(aviso_prospectos.destinatarios(db)) or '(nadie)'}")
            return
        ahora = datetime.utcnow()
        tibios = [
            p for p in prospectos_service.listar(db, banda="warm", desde=ahora - timedelta(days=1), hasta=ahora)
            if p.estado == "nuevo"
        ]
        for p in tibios:
            print(f"  {p.creado_en:%Y-%m-%d %H:%M} · {p.nombre or 'sin nombre'} · {p.email or p.telefono or 'sin contacto'}")
        print(f"\n{len(tibios)} tibio(s) · simulación, usa --enviar")
        print(f"Iría a: {', '.join(aviso_prospectos.destinatarios(db)) or '(nadie)'}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
