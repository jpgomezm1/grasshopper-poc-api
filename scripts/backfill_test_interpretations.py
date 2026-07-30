"""Genera la lectura narrativa de los resultados de test que se quedaron sin ella.

A1/A2 · La lectura por test (P1-1) se genera **solo cuando alguien abre la pantalla
de resultados**. El PDF y el snapshot la leen de caché y nunca la generan, a
propósito: generar 8 lecturas dentro de una descarga tardaría minutos.

El efecto secundario es que **todo resultado anterior a P1-1 no tiene lectura y no
la va a tener nunca**, salvo que su dueño vuelva a abrir la pantalla de ese test.
Eso incluye los resultados de la clienta y los de Sandra, que son justo los que se
van a mirar en la revisión: descargarían el reporte y verían las tarjetas sin el
párrafo explicativo que pidieron.

Este script rellena esa caché.

    # ver qué haría, sin gastar un peso ni escribir nada
    python scripts/backfill_test_interpretations.py --dry-run

    # solo una persona (lo normal antes de una demo)
    python scripts/backfill_test_interpretations.py --email veronica@stayirrelevant.com

    # todo lo que falte, con tope de seguridad
    python scripts/backfill_test_interpretations.py --limit 50

⚠️ CUESTA DINERO: es una llamada a Claude por resultado. Por eso el tope por defecto
es bajo y `--all` hay que pedirlo explícitamente. Cada llamada queda registrada en
`ai_usage_logs` (M-001), así que el gasto es auditable después.

Es idempotente: salta los resultados que ya tienen una lectura válida para sus
puntajes actuales (`get_cached` valida el hash), así que se puede volver a correr.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # Windows · evita UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.data.vocational_tests import get_test_by_id
from app.db.database import SessionLocal
from app.db.models import User, VocationalTestResult
from app.services import test_interpretation_service as svc

TOPE_POR_DEFECTO = 25


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="solo los resultados de esta persona")
    parser.add_argument("--test-id", help="solo este test (ej. holland)")
    parser.add_argument(
        "--limit",
        type=int,
        default=TOPE_POR_DEFECTO,
        help=f"máximo de lecturas a generar (por defecto {TOPE_POR_DEFECTO})",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="sin tope · cada resultado es una llamada de IA facturable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="lista lo que haría, sin llamar a la IA ni escribir",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = db.query(VocationalTestResult)

        if args.email:
            user = db.query(User).filter(User.email == args.email).first()
            if not user:
                print(f"[!] no existe ningún usuario con el correo {args.email}")
                return 1
            q = q.filter(VocationalTestResult.user_id == user.id)

        if args.test_id:
            q = q.filter(VocationalTestResult.test_id == args.test_id)

        resultados = q.order_by(VocationalTestResult.created_at.asc()).all()

        # `get_cached` valida el hash, así que un resultado cuya lectura quedó vieja
        # (porque cambió el prompt o los puntajes) también entra al backfill.
        faltantes = [r for r in resultados if svc.get_cached(r) is None]

        print(f"resultados revisados : {len(resultados)}")
        print(f"ya tienen lectura    : {len(resultados) - len(faltantes)}")
        print(f"les falta            : {len(faltantes)}")

        if not faltantes:
            print("\nNo hay nada que hacer.")
            return 0

        if not args.all and len(faltantes) > args.limit:
            print(
                f"\n[!] Hay {len(faltantes)} sin lectura y el tope es {args.limit}."
                f"\n    Se procesarán los {args.limit} más antiguos."
                f"\n    Usa --limit N o --all si de verdad quieres todos."
            )
            faltantes = faltantes[: args.limit]

        if args.dry_run:
            print("\n--dry-run · no se llama a la IA ni se escribe nada:\n")
            for r in faltantes:
                print(f"  - {r.test_id:<16} user={r.user_id}")
            return 0

        print(f"\nGenerando {len(faltantes)} lecturas…\n")
        ok = 0
        fallidas = 0
        for r in faltantes:
            test = get_test_by_id(r.test_id) or {}
            user = db.query(User).filter(User.id == r.user_id).first()
            try:
                svc.generate(
                    db,
                    r,
                    test_name=test.get("name") or r.test_id,
                    test_description=test.get("description") or "",
                    user=user,
                )
                ok += 1
                print(f"  OK   {r.test_id:<16} user={r.user_id}")
            except Exception as exc:
                # Una falla no debe abortar el resto: lo normal es un rate limit o
                # un JSON mal formado, y el siguiente resultado suele salir bien.
                fallidas += 1
                print(f"  FALLA {r.test_id:<16} user={r.user_id} · {exc}")

        print(f"\nGeneradas: {ok} · fallidas: {fallidas}")
        if fallidas:
            print("Vuelve a correr el script: es idempotente y reintenta solo las que faltan.")
        return 0 if not fallidas else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
