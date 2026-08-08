"""Tercera pasada · limpieza del consolidado antes de que sea cargable.

`validar_programas.py` rechaza lo que está **mal formado**. Esto quita lo que está
bien formado y es **falso o invendible**: primaria registrada como bachillerato,
formación clínica del NHS que un colombiano no puede cursar, y la misma
institución contada dos veces bajo nombres distintos.

    python scripts/limpiar_programas.py

Lee  `programas_consolidados.csv`
Deja `programas_final.csv` + `programas_descartados.csv` (con el motivo)

**Cada regla es una lista explícita, no un patrón.** Un regex sobre "primary"
borraría *Bachelor of Primary Education*, que es una carrera docente perfectamente
vendible: el problema no es la palabra, son cinco filas concretas. Escribirlas a
mano cuesta cinco minutos y es revisable por un humano; un patrón que acierta el
90% deja un 10% de daño que nadie va a auditar.

Nada se borra en silencio: lo descartado sale contado y con su motivo, igual que
en el validador.
"""
from __future__ import annotations

import csv
import os
from collections import Counter

RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "catalogo")

# ---------------------------------------------------------------------------
# 1 · Primaria registrada como `secundaria`
# ---------------------------------------------------------------------------
# El prompt de extracción se corrigió a mitad de camino para EXCLUIR primaria (un
# JK-5 no es bachillerato y el estudiante que lo vea recomendado no es el que la
# agencia atiende). Estas cinco filas salieron de lotes anteriores al arreglo.
# Van por (institución, nombre) exacto para que, si mañana el sitio cambia el
# nombre, la regla deje de aplicar en vez de acertar de casualidad.
PRIMARIA = {
    ("ELTHAM College", "Primary Years P-6"),
    ("Ermitage International School Paris",
     "French Bilingual School - Pre-K & Primary (Maternelle to Primary)"),
    ("Ermitage International School Paris", "IB Primary Years Programme (IB PYP)"),
    ("Pickering College", "Junior School (JK-Grade 5)"),
    ("Pickering College", "The Sphere Program (Grades 4 & 5)"),
}

# ---------------------------------------------------------------------------
# 2 · Formación profesional británica que un colombiano no puede cursar
# ---------------------------------------------------------------------------
# UWE Bristol publica 612 programas y sólo ~320 son su catálogo académico. El
# resto se reparte en dos bolsas, ambas cerradas de hecho a un estudiante
# extranjero:
#
#   · 282 `curso_corto` · CPD para personal ya colegiado en UK ("Administering
#     Intravenous Injections", "Chest X-ray Image Interpretation"). Se verificó
#     que las 282 —sin una sola excepción— llevan el tipo marcado entre
#     paréntesis al final del título: (Professional course), (Study day),
#     (Continuing Professional Development), (Certificate)… Es dato del sitio,
#     no inferencia nuestra.
#   · 10 `bootcamp` · los *Skills Bootcamps* del gobierno británico, financiados
#     con fondos públicos para residentes en UK.
#
# Por eso la regla va por NIVEL y no por texto: enumerar las variantes de
# paréntesis dejaba 82 filas fuera por diferencias de mayúsculas, y el patrón
# que las cazara a todas también cazaría cursos legítimos de otra institución.
# Acotada a UWE, "curso_corto o bootcamp" describe exactamente las dos bolsas.
CPD_NIVELES = {"curso_corto", "bootcamp"}
CPD_INSTITUCIONES = {"university of the west of england, bristol"}

# ---------------------------------------------------------------------------
# 3 · La misma institución bajo dos nombres
# ---------------------------------------------------------------------------
# Adelaide University absorbió a UniSA y su centro de idiomas (ex-CELUSA) en la
# fusión de 2026. Tres fichas del catálogo del cliente, una entidad real. Se
# unifican ANTES de deduplicar, para que el mismo programa contado dos veces caiga
# como duplicado en vez de sobrevivir por venir de fichas distintas.
ALIAS = {
    "adelaide university elc (ex-celusa)": "Adelaide University",
    "celusa": "Adelaide University",
    "unisa · university of south australia": "Adelaide University",
}


def _motivo(f: dict) -> str | None:
    """El primer motivo por el que esta fila no debería cargarse, o None."""
    if (f["institucion"], f["nombre"]) in PRIMARIA:
        return "primaria · no es bachillerato"
    if f["institucion"].lower() in CPD_INSTITUCIONES:
        if f["nivel"] in CPD_NIVELES:
            return "CPD / Skills Bootcamp UK · cerrado a estudiantes extranjeros"
    return None


def main() -> int:
    entrada = os.path.join(RAIZ, "programas_consolidados.csv")
    if not os.path.exists(entrada):
        print("Falta programas_consolidados.csv · corre antes validar_programas.py")
        return 1

    with open(entrada, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))

    campos = list(filas[0].keys())
    buenas, fuera = [], []

    for f in filas:
        # Unificar el nombre de la institución antes de cualquier otra cosa.
        canon = ALIAS.get(f["institucion"].lower())
        if canon:
            f["institucion_original"] = f["institucion"]
            f["institucion"] = canon

        motivo = _motivo(f)
        if motivo:
            fuera.append({**f, "motivo": motivo})
        else:
            buenas.append(f)

    # Segunda deduplicación · ahora que los alias colapsaron, aparecen duplicados
    # que la primera pasada no podía ver.
    vistos, unicas = set(), []
    for f in buenas:
        clave = (f["institucion"].lower(), f["nombre"].lower())
        if clave in vistos:
            fuera.append({**f, "motivo": "duplicado tras unificar la institución"})
            continue
        vistos.add(clave)
        unicas.append(f)

    with open(os.path.join(RAIZ, "programas_final.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(unicas)
    with open(os.path.join(RAIZ, "programas_descartados.csv"), "w",
              encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos + ["motivo"], extrasaction="ignore")
        w.writeheader()
        w.writerows(fuera)

    print(f"entraron : {len(filas)}")
    print(f"quedaron : {len(unicas)}")
    print(f"fuera    : {len(fuera)}")
    for m, n in Counter(x["motivo"] for x in fuera).most_common():
        print(f"    {n:>5}  {m}")
    print(f"\ninstituciones: {len(set(f['institucion'] for f in unicas))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
