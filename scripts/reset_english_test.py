"""Resetea el intento del test de inglés de una o varias cuentas.

**Por qué existe.** El test es de **un solo intento** (`english_test_results`
tiene `user_id` UNIQUE). Verónica y Sandra lo hicieron con el banco viejo de 20
preguntas inventadas por nosotros; el 05-08 se reemplazó por el examen real de
AMES (60 preguntas, con su tabla de equivalencia). Si entran con su cuenta de
siempre **ven el resultado viejo** y concluyen, con razón, que A5 no se hizo.

**Qué hace.** Borra la fila de `english_test_results` de las cuentas indicadas,
para que puedan volver a presentarlo. No toca nada más: ni el usuario, ni sus
tests de orientación, ni el journey.

**Qué NO hace.** No guarda una copia del resultado viejo — no hay dónde, la
tabla tiene `user_id` único. El resultado borrado se pierde. Por eso el script
imprime lo que va a borrar y **no borra nada sin `--confirmar`**.

Uso (contra producción se corre en Heroku, que es donde viven las credenciales):

    heroku run python scripts/reset_english_test.py --email veronica@... -a <app>
    heroku run python scripts/reset_english_test.py --email veronica@... --confirmar -a <app>

Sin `--confirmar` es un dry-run: lista y sale.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import EnglishTestResult, User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--email",
        action="append",
        required=True,
        help="correo de la cuenta a resetear · repetible para varias",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="borra de verdad · sin esto solo lista lo que haría",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        a_borrar: list[tuple[User, EnglishTestResult]] = []

        for correo in args.email:
            user = db.query(User).filter(User.email == correo).first()
            if user is None:
                print(f"[!] no existe ninguna cuenta con el correo {correo}")
                return 1
            resultado = (
                db.query(EnglishTestResult)
                .filter(EnglishTestResult.user_id == user.id)
                .first()
            )
            if resultado is None:
                print(f"  · {correo}: no tiene intento · nada que resetear")
                continue
            a_borrar.append((user, resultado))

        if not a_borrar:
            print("\nNo hay nada que hacer.")
            return 0

        print("\nSe va a borrar el intento de:\n")
        for user, resultado in a_borrar:
            print(
                f"  - {user.email:<38} "
                f"puntaje {resultado.score}/{resultado.total_questions} · "
                f"nivel {resultado.cefr_level} · {resultado.created_at:%Y-%m-%d}"
            )

        if not args.confirmar:
            print(
                "\n--- dry-run · no se borró nada ---"
                "\nSi el puntaje de arriba es sobre 20 preguntas, es el banco viejo"
                "\ny resetearlo es justo lo que queremos. Si es sobre 60, ya hizo"
                "\nel examen nuevo de AMES y borrarlo le haría perder su resultado."
                "\n\nVuelve a correrlo con --confirmar para borrarlo."
            )
            return 0

        for _, resultado in a_borrar:
            db.delete(resultado)
        db.commit()
        print(f"\n✓ {len(a_borrar)} intento(s) borrado(s) · ya pueden volver a presentarlo.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
