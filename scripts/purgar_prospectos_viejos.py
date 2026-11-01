"""Retención de prospectos · borra los fríos o descartados de más de 12 meses (X-5).

Ley 1581/2012: los datos se guardan mientras sirvan a la finalidad para la que
se pidieron. Un prospecto frío o descartado que en un año no creó cuenta ya no
sirve para orientarlo. Antes se guardaban para siempre.

Qué borra (`prospectos_service.purgar_viejos`):
- del bot gratuito y del perfilador: los de más de 12 meses que nunca crearon
  cuenta y quedaron fríos o descartados;
- del quiz anterior: los de más de 12 meses que nunca crearon cuenta (el quiz no
  puntuaba, así que el criterio es solo la edad).

Los que crearon cuenta NO se borran: sus respuestas ya son parte de su perfil.

Para Heroku Scheduler, una vez al día. **No está activado**: activarlo es
decisión de JP (y conviene avisarle a la clienta del plazo).

    python scripts/purgar_prospectos_viejos.py            # muestra cuántos borraría
    python scripts/purgar_prospectos_viejos.py --aplicar  # los borra
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args()

    from app.db.database import SessionLocal
    from app.services import prospectos_service
    from app.services.audit_service import log_action

    db = SessionLocal()
    try:
        cuenta = prospectos_service.purgar_viejos(db, aplicar=args.aplicar)
        print(f"De más de {prospectos_service.RETENCION_MESES} meses: {cuenta}")
        if args.aplicar and any(cuenta.values()):
            log_action(
                db, user=None, action="prospectos.purgados", resource_type="prospecto",
                payload={"filas": cuenta, "meses": prospectos_service.RETENCION_MESES},
            )
            print("BORRADOS y registrados en la auditoría.")
        elif not args.aplicar:
            print("Simulación: nada se borró. Usa --aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
