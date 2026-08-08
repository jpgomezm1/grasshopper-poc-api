"""Arregla los resultados de test de los alumnos DEMO en producción.

**Por qué existe.** `seed_test_data.py` sembró estas filas con dos datos malos —
arreglados en el script el 2026-08-07, pero las filas ya escritas siguen ahí:

  1. `scores = {"sample": "scores"}` · un placeholder, no un resultado. Al
     generar las lecturas (backfill A2), la IA no tenía nada que leer y escribió
     sobre QUÉ ES cada test en vez de sobre la persona. Tres alumnos distintos
     compartían titular y resumen: la queja de la clienta ("le salen unas siglas
     y ya"), reproducida por nosotros en las cuentas que ella abre.
  2. `test_id` "riasec" / "big5" · el producto no los reconoce.
     `test_interpretation_service._label_map` sólo entiende holland · bigfive ·
     values · career-anchors · mbti · istrong · vark · motivadores, y devuelve
     `{}` para cualquier otro → "Dimensiones sin etiqueta legible".

**Qué hace.** Sobre las filas de cuentas `@grasshopper.dev` con placeholder:
corrige el `test_id`, escribe puntajes variados por alumno (mismo generador que
la siembra, así que son reproducibles) y **borra la lectura** para que el
backfill la regenere con datos de verdad.

**Qué NO hace.** No toca ninguna fila de una cuenta real. El filtro es explícito
y hay un chequeo que aborta si alguna candidata no es `@grasshopper.dev`.

    python scripts/arreglar_scores_demo.py              # dry-run
    python scripts/arreglar_scores_demo.py --confirmar  # escribe

Después hay que correr `backfill_test_interpretations.py --all` para regenerar
las lecturas.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

# Ids que el producto NO reconoce → el que sí.
_RENOMBRAR = {"riasec": "holland", "big5": "bigfive"}

_DOMINIO_DEMO = "@grasshopper.dev"


def _generador():
    """El mismo `_puntajes_demo` de la siembra · una sola fuente de verdad.

    Se importa por ruta porque `seed_test_data.py` es un script, no un módulo
    del paquete. Si algún día se mueve la lógica, este import falla ruidosamente
    en vez de duplicar la fórmula y dejar que las dos diverjan.
    """
    ruta = _RAIZ / "scripts" / "seed_test_data.py"
    spec = importlib.util.spec_from_file_location("seed_test_data", ruta)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:  # el script parsea argumentos al importarse
        pass
    return mod._puntajes_demo


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--confirmar", action="store_true",
                   help="escribe · sin esto sólo muestra")
    args = p.parse_args()

    from sqlalchemy import create_engine, text

    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("[ERROR] falta DATABASE_URL", file=sys.stderr)
        return 1

    puntajes_de = _generador()
    engine = create_engine(url.replace("postgres://", "postgresql://"))

    with engine.begin() as c:
        filas = c.execute(text("""
            SELECT v.id, v.test_id, v.scores, u.email
            FROM vocational_test_results v JOIN users u ON u.id = v.user_id
            ORDER BY u.email, v.test_id
        """)).fetchall()

        candidatas = []
        for vid, tid, scores, email in filas:
            d = scores if isinstance(scores, dict) else (json.loads(scores) if scores else {})
            if d and d != {"sample": "scores"}:
                continue  # ya tiene puntajes reales · no se toca
            candidatas.append((vid, tid, email))

        if not candidatas:
            print("No hay filas con placeholder · nada que hacer.")
            return 0

        # Guardarraíl · si alguna candidata no es demo, se aborta entero.
        intrusas = [e for _, _, e in candidatas if not e.endswith(_DOMINIO_DEMO)]
        if intrusas:
            print(f"[ABORTA] {len(intrusas)} fila(s) de cuentas NO demo entre las "
                  f"candidatas · este script sólo toca {_DOMINIO_DEMO}",
                  file=sys.stderr)
            for e in sorted(set(intrusas)):
                print(f"    {e}", file=sys.stderr)
            return 1

        # El "alumno" para el generador es su correo, así cada uno recibe un
        # perfil propio y estable aunque el orden de las filas cambie.
        correos = sorted({e for _, _, e in candidatas})
        semilla_de = {e: i for i, e in enumerate(correos)}

        print(f"Filas con placeholder: {len(candidatas)} · "
              f"alumnos demo: {len(correos)}\n")
        renombres = {}
        for vid, tid, email in candidatas:
            nuevo = _RENOMBRAR.get(tid, tid)
            if nuevo != tid:
                renombres[tid] = renombres.get(tid, 0) + 1
            sc = puntajes_de(nuevo, semilla_de[email])
            if args.confirmar:
                c.execute(text("""
                    UPDATE vocational_test_results
                    SET test_id = :tid, scores = CAST(:sc AS JSON),
                        interpretation = NULL, interpretation_hash = NULL,
                        interpretation_generated_at = NULL
                    WHERE id = :vid
                """), {"tid": nuevo, "sc": json.dumps(sc), "vid": vid})

        for viejo, n in sorted(renombres.items()):
            print(f"  test_id {viejo} → {_RENOMBRAR[viejo]}: {n} filas")
        print(f"  puntajes escritos en {len(candidatas)} filas")
        print(f"  lecturas borradas para que el backfill las regenere")

        muestra = candidatas[0]
        print(f"\n  ejemplo · {muestra[2]}:")
        t = _RENOMBRAR.get(muestra[1], muestra[1])
        print(f"    {t}: {puntajes_de(t, semilla_de[muestra[2]])}")

        if not args.confirmar:
            print("\n--- dry-run · no se escribió nada ---"
                  "\nVuelve a correrlo con --confirmar.")
            return 0

    print("\n✓ Listo. Ahora corre:"
          "\n  python scripts/backfill_test_interpretations.py --all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
