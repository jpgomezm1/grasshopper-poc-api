"""Aplica al catálogo las correcciones de fichas verificadas contra el sitio real.

    python scripts/aplicar_correcciones.py            # simulacro
    python scripts/aplicar_correcciones.py --confirm  # escribe

Lee `data/catalogo/CORRECCIONES.json`, que sale de `FICHAS_A_CORREGIR.md`: 34
agentes entraron al sitio oficial de cada institución y anotaron cada vez que la
ficha del catálogo no coincidía con la realidad.

**Esto escribe sobre el catálogo del cliente**, así que:

  · corre en seco por defecto;
  · deja en `correcciones_aplicadas.csv` el antes y el después de cada campo,
    para que la agencia pueda revisar qué tocamos y por qué;
  · **no aplica una corrección si el valor actual no coincide** con el que el
    informe decía encontrar. Si alguien ya lo arregló, o el Excel se recargó, el
    valor cambió y nuestra corrección puede estar pisando algo más nuevo.

## Dónde está la línea de lo que corregimos

Se corrige lo que es un **hecho comprobable** contra el sitio de la institución:
en qué país y ciudad está, cómo se llama de verdad, y si el producto que la
ficha describe existe.

**No se amplía `subject`.** Cuando una ficha *infra*vende —el campo está vacío en
una institución perfectamente vendible— llenarlo sería otorgarle a la agencia una
autorización comercial que nosotros no tenemos. Sólo se **quita** lo que
sobrevende: retirar una promesa que la institución no puede cumplir es seguro en
cualquier caso; agregarla no.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Program  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo")

# Los únicos campos que este script puede tocar. Cualquier otro en el JSON se
# rechaza en vez de aplicarse: la lista blanca es lo que impide que una entrada
# mal formada escriba sobre `cost_total` o `priority`.
CAMPOS = {"country", "city", "name", "subject", "active"}


def _normalizar(v):
    """Para comparar el valor actual con el que el informe decía encontrar."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    return str(v).strip().lower()


def _autorizados(fila) -> list:
    """Lo que la ficha autoriza vender · la lista COMPLETA.

    `subject` guarda **sólo el primer valor**; el resto vive en
    `raw["programs_offered"]`. Sin mirar la lista completa, una sobreventa como
    la de Holmesglen —que autoriza "Idiomas" en la segunda posición cuando la
    institución no dicta idiomas— es invisible.
    """
    crudo = fila.raw if isinstance(fila.raw, dict) else {}
    lista = crudo.get("programs_offered")
    if isinstance(lista, list) and lista:
        return [str(x) for x in lista]
    return [fila.subject] if fila.subject else []


def _aplicar_autorizacion(fila, valor_nuevo: str) -> None:
    """Escribe la lista de autorización en los DOS sitios donde vive.

    `subject` **se le muestra al estudiante** (lo compone
    `display_name_for_program`), así que meterle la lista unida con barras le
    pondría "Vocacionales | Todos los programas" en la pantalla. Va la lista a
    `raw["programs_offered"]` y el primer elemento a `subject`, que es
    exactamente como estaba antes.
    """
    from sqlalchemy.orm.attributes import flag_modified

    lista = [x.strip() for x in (valor_nuevo or "").split("|") if x.strip()]
    crudo = dict(fila.raw) if isinstance(fila.raw, dict) else {}
    crudo["programs_offered"] = lista
    # Se reasigna el dict entero en vez de mutarlo: SQLAlchemy no detecta los
    # cambios dentro de una columna JSON si se modifica en sitio.
    fila.raw = crudo
    flag_modified(fila, "raw")
    fila.subject = lista[0] if lista else None


# Cómo se llama cada ficha corregida dentro de `programas_investigados`.
#
# Las dos tablas no comparten el nombre: `programs` guarda el de la ficha del
# cliente y `programas_investigados` el que el agente verificó en el sitio real.
# Se resuelven a mano —son seis— en vez de con un emparejamiento aproximado:
# escribir el país equivocado sobre la institución equivocada es exactamente el
# error que estas correcciones vienen a arreglar.
# El valor es una LISTA porque una misma institución puede haber quedado bajo
# varios nombres: distintos lotes la extrajeron y cada agente escribió el nombre
# que vio en el sitio. UHE aparece tres veces, y sólo una de las tres arrastra el
# país equivocado — corregir sólo el nombre "principal" habría dejado el error
# vivo en las otras dos.
EQUIVALENCIAS = {
    "Montgomery International School": ["Montgomery International School"],
    "Cyprus West University": ["Cyprus West University"],
    "Istituto Marangoni": ["Istituto Marangoni"],
    "High Schools International": ["High Schools International (HSI)"],
    "The University of Business and International Studies UBIS S.A.": ["UBIS"],
    "Universal Higher Education International": [
        "Universal Higher Education",
        "Universal Higher Education (UHE)",
        "Universal Higher Education (UHE Australia)",
    ],
}


def _propagar_paises(correcciones, confirmar: bool) -> None:
    """Lleva las correcciones de país al catálogo investigado.

    Los 15.483 programas heredaron el país de la ficha de su institución, así
    que arrastran los mismos errores: 216 programas de Istituto Marangoni decían
    estar en Estados Unidos, donde esa escuela no tiene ni un campus.

    Es importante para la búsqueda y no sólo cosmético: el país es el **primer
    filtro** del recomendador. Con el país mal, esos programas le aparecen a
    quien pidió otro destino y no le aparecen a quien pidió el correcto.
    """
    from sqlalchemy import text as _text

    from app.db.database import SessionLocal as _S

    # El país se normaliza al vocabulario del catálogo investigado antes de
    # escribirlo. Las correcciones traen el valor tal como lo escribe la ficha
    # del cliente ("USA", "UK"), y esa tabla usa nombres en español: escribir
    # "USA" al lado de 1.975 "Estados Unidos" parte el filtro de país en dos
    # entradas para el mismo sitio, y el estudiante que elige una no ve la otra.
    from app.services import paises as _paises

    paises = {}
    for c in correcciones:
        if c["campo"] != "country":
            continue
        v = _paises.normalizar(c["valor_nuevo"]) or c["valor_nuevo"]
        paises[c["institucion_ficha"]] = v
    if not paises:
        return

    db = _S()
    total = 0
    try:
        for ficha, nuevo in paises.items():
            nombres = EQUIVALENCIAS.get(ficha)
            if not nombres:
                print(f"    (sin equivalencia en el catalogo investigado: {ficha})")
                continue
            for nombre in nombres:
                n = db.execute(_text(
                    "SELECT count(*) FROM programas_investigados "
                    "WHERE institucion = :i AND pais IS DISTINCT FROM :p"
                ), {"i": nombre, "p": nuevo}).scalar()
                if not n:
                    continue
                total += n
                print(f"    {n:>4} programas de {nombre[:38]} -> {nuevo}")
                if confirmar:
                    db.execute(_text(
                        "UPDATE programas_investigados SET pais = :p "
                        "WHERE institucion = :i"
                    ), {"i": nombre, "p": nuevo})
        if confirmar:
            db.commit()
    finally:
        db.close()
    print(f"  programas investigados con el pais corregido: {total}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true",
                    help="escribe en la base · sin esto sólo simula")
    ap.add_argument("--json", default=os.path.join(RAIZ, "CORRECCIONES.json"))
    ap.add_argument("--forzar", action="store_true",
                    help="aplica aunque el valor actual no coincida con el informe")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as fh:
        datos = json.load(fh)
    correcciones = datos.get("correcciones", [])

    db = SessionLocal()
    aplicadas, saltadas = [], Counter()
    try:
        for c in correcciones:
            campo = c.get("campo")
            if campo not in CAMPOS:
                saltadas[f"campo no permitido: {campo}"] += 1
                continue

            fila = (
                db.query(Program)
                .filter(Program.name == c["institucion_ficha"])
                .first()
            )
            if fila is None:
                saltadas["no existe esa ficha en programs"] += 1
                continue

            # `subject` no se compara contra la columna sino contra la lista
            # completa de autorización · ver `_autorizados`.
            if campo == "subject":
                actual = " | ".join(_autorizados(fila))
            else:
                actual = getattr(fila, campo, None)
            esperado = c.get("valor_actual")
            # El informe describe lo que había cuando se auditó. Si hoy dice otra
            # cosa, alguien lo tocó después y nuestra corrección está vieja.
            if not args.forzar and esperado is not None:
                if _normalizar(actual) != _normalizar(esperado):
                    saltadas["el valor actual ya no coincide con el informe"] += 1
                    continue

            nuevo = c["valor_nuevo"]
            if campo == "active" and isinstance(nuevo, str):
                nuevo = nuevo.strip().lower() not in ("false", "0", "no")
            if _normalizar(actual) == _normalizar(nuevo):
                saltadas["ya estaba corregido"] += 1
                continue

            aplicadas.append({
                "institucion": c["institucion_ficha"],
                "campo": campo,
                "antes": "" if actual is None else str(actual),
                "despues": "" if nuevo is None else str(nuevo),
                "categoria": c.get("categoria", ""),
                "evidencia": c.get("evidencia", ""),
            })
            if args.confirm:
                if campo == "subject":
                    _aplicar_autorizacion(fila, nuevo)
                else:
                    setattr(fila, campo, nuevo)

        if args.confirm:
            db.commit()
    finally:
        db.close()

    _propagar_paises(correcciones, args.confirm)

    salida = os.path.join(RAIZ, "correcciones_aplicadas.csv")
    with open(salida, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "institucion", "campo", "antes", "despues", "categoria", "evidencia"])
        w.writeheader()
        w.writerows(aplicadas)

    print(f"correcciones en el archivo : {len(correcciones)}")
    print(f"aplicables                 : {len(aplicadas)}")
    if saltadas:
        print("saltadas:")
        for m, n in saltadas.most_common():
            print(f"    {n:>4}  {m}")
    print("\npor categoria:")
    for k, n in Counter(a["categoria"] for a in aplicadas).most_common():
        print(f"    {n:>4}  {k}")
    print(f"\n  -> {salida}")

    for lista, titulo in (("requiere_autorizacion", "esperan autorizacion de la agencia"),
                          ("pendiente_confirmar", "hay que confirmar con la institucion"),
                          ("reclasificar", "necesitan reclasificarse"),
                          ("sin_ficha", "no se encontro la ficha")):
        n = len(datos.get(lista) or [])
        if n:
            print(f"  {n:>4} {titulo}")

    if not args.confirm:
        print(f"\n--- SIMULACRO ({datetime.now():%H:%M}) · nada se escribio. "
              f"Repite con --confirm ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
