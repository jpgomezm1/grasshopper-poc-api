"""Calcula el nivel de confianza de cada programa investigado.

    python scripts/calcular_confianza.py            # simulacro
    python scripts/calcular_confianza.py --confirm  # escribe

No inventa una métrica: lee señales que ya están en la fila y las traduce a un
nivel que un asesor pueda interpretar sin saber cómo se extrajo el dato.

**La señal fuerte es el código oficial.** Un CRICOS, un RTO o un código nacional
existe en un registro público del país: se puede confirmar en un minuto y no se
puede inventar. Es lo único de esta tabla que un tercero puede verificar sin
confiar en nosotros.

**La segunda es que la URL apunte a su propia ficha.** Cuando varios programas
comparten URL, esa URL es un listado: el nombre del programa pudo salir de esa
lista, o del slug de la dirección, y no de una página que lo describa. Varios
agentes lo dijeron en sus notas ("los títulos están reconstruidos desde el slug",
"fidelidad verificada abriendo 5 páginas de 68").

Se recalcula entero cada vez porque es barato y porque una reextracción puede
cambiar las señales de una institución completa.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

VERIFICABLE = "verificable"
PUBLICADO = "publicado"
INDICATIVO = "indicativo"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # Se calcula en SQL y no en Python porque son 15.483 filas y la señal de
        # "URL propia" exige agrupar toda la tabla: traerla entera para decidir
        # cada fila sería pedirle a la red lo que la base resuelve de una.
        sql = """
        UPDATE programas_investigados pi SET confianza = CASE
            WHEN pi.codigo_oficial IS NOT NULL THEN :verificable
            WHEN pi.url_fuente IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM programas_investigados o
                WHERE o.url_fuente = pi.url_fuente AND o.id <> pi.id
            ) THEN :publicado
            ELSE :indicativo
        END
        """
        if args.confirm:
            db.execute(text(sql), {"verificable": VERIFICABLE,
                                   "publicado": PUBLICADO,
                                   "indicativo": INDICATIVO})
            db.commit()

        filas = db.execute(text("""
            SELECT CASE
                WHEN pi.codigo_oficial IS NOT NULL THEN 'verificable'
                WHEN pi.url_fuente IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM programas_investigados o
                    WHERE o.url_fuente = pi.url_fuente AND o.id <> pi.id
                ) THEN 'publicado'
                ELSE 'indicativo'
            END AS nivel, count(*) AS n
            FROM programas_investigados pi GROUP BY 1
        """)).mappings().all()

        total = sum(r["n"] for r in filas)
        cuenta = {r["nivel"]: r["n"] for r in filas}
        print(f"programas: {total}")
        for nivel, que in (
            (VERIFICABLE, "publica un codigo oficial · confirmable en un registro publico"),
            (PUBLICADO, "sin codigo, pero el nombre viene de su propia pagina"),
            (INDICATIVO, "sin codigo y su URL es un listado · el nombre puede venir del slug"),
        ):
            n = cuenta.get(nivel, 0)
            print(f"  {nivel:<12} {n:>6}  ({round(100 * n / total)}%)  {que}")

        # Cuántas instituciones quedan enteras en el tramo más flojo · son las
        # que hay que reextraer o revisar primero.
        flojas = db.execute(text("""
            SELECT institucion, count(*) n FROM programas_investigados
            WHERE codigo_oficial IS NULL AND url_fuente IN (
                SELECT url_fuente FROM programas_investigados
                GROUP BY url_fuente HAVING count(*) > 1)
            GROUP BY institucion HAVING count(*) >= 20
            ORDER BY n DESC LIMIT 10
        """)).mappings().all()
        if flojas:
            print("\ninstituciones con mas filas indicativas (revisar primero):")
            for r in flojas:
                print(f"    {r['n']:>4}  {r['institucion'][:52]}")

        if not args.confirm:
            print("\n--- SIMULACRO · nada se escribio. Repite con --confirm ---")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
