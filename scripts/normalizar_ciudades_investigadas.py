"""Rellena la ciudad de los programas cuya institución tiene un campus único.

    python scripts/normalizar_ciudades_investigadas.py            # simulacro
    python scripts/normalizar_ciudades_investigadas.py --commit

## El problema, medido

7.816 de los 33.552 programas activos (23%) no tienen ciudad, y en la pantalla
de búsqueda salen agrupados en un "Sin ciudad registrada" que es el bucket más
grande de su faceta.

Lo revelador es cómo se reparten: **salen de sólo 82 instituciones**, y cada una
de esas 82 tiene **cero** programas con ciudad. No es que falte el dato en filas
sueltas — es que la extracción de esas instituciones nunca lo capturó. Por eso
esto se arregla con una tabla revisada y no con heurística.

## Por qué NO se hereda de la ficha del catálogo

Era lo primero que uno intenta: `programas_investigados.program_id` enlaza con
`programs`, que sí tiene `city`. Medido, no sirve:

    sin ciudad y con ficha que SÍ tiene ciudad ...........    65 de 7.816
    con ciudad en ambos y DISCREPAN .....................  3.400 de 23.375

O sea que cubriría el 0,8% de los casos y, donde se puede comparar, la ficha
dice otra cosa el 15% de las veces: las instituciones tienen varios campus y la
ficha guarda la sede principal. Heredar de ahí habría metido error donde hoy hay
un hueco honesto.

## La regla de esta tabla

**Sólo entra la institución cuyo campus principal es inequívoco.** Las redes de
escuelas de idiomas y las universidades multi-campus se quedan fuera a propósito
y siguen en "Sin ciudad registrada": ponerle Londres a St Giles —que tiene sedes
en Brighton, Eastbourne, Londres, Nueva York, Vancouver…— no es completar un
dato, es inventarlo. Un hueco visible es mejor que un dato falso, y el estudiante
puede ver la página oficial desde el detalle.

Las excluidas están listadas abajo **con su razón**, para que el siguiente que
lea esto no crea que se olvidaron.
"""
from __future__ import annotations

import argparse
import io
import os
import sys

# La consola de Windows es cp1252 y no encodea ni acentos ni símbolos · sin
# esto el script muere al imprimir un nombre con tilde, que es la mitad de ellos.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402

#: Institución → ciudad de su campus principal. **Revisada una por una.**
#:
#: El nombre va exactamente como está en `programas_investigados.institucion`,
#: erratas incluidas ("The university of Manchester"), porque el cruce es por
#: igualdad: normalizarlo aquí escondería que el catálogo lo tiene así.
CIUDAD_POR_INSTITUCION = {
    # ── Reino Unido ────────────────────────────────────────────────────────
    "Northumbria University": "Newcastle upon Tyne",
    "University of Liverpool": "Liverpool",
    "University of Glasgow": "Glasgow",
    "The university of Manchester": "Manchester",
    "University of York": "York",
    "University of Stirling": "Stirling",
    "Nottingham Trent University": "Nottingham",
    "QUB - The Queen´s University Of Belfast": "Belfast",
    "University of Birmingham": "Birmingham",
    "Cranfield University": "Cranfield",
    "Bournemouth University": "Bournemouth",
    "University of Strathclyde": "Glasgow",
    # Bayswater es un barrio de Londres · el propio nombre trae la sede.
    "Stafford House - Bayswater": "Londres",

    # ── Estados Unidos ─────────────────────────────────────────────────────
    "Stony Brook University": "Stony Brook",
    "Saint Louis University": "San Luis",
    "University of Kansas": "Lawrence",
    "University of South Carolina": "Columbia",
    "Tulane University": "Nueva Orleans",
    "Louisiana State University": "Baton Rouge",
    "American University": "Washington D. C.",
    "University of Dayton": "Dayton",
    "Belmont University": "Nashville",
    "University at Buffalo": "Buffalo",
    "University of Central Florida": "Orlando",
    "Auburn University": "Auburn",
    "Hofstra University": "Hempstead",
    "Montclair State University": "Montclair",
    "Adelphi University": "Garden City",
    "Cleveland State University": "Cleveland",
    "The University of Texas at San Antonio": "San Antonio",
    "University of Utah": "Salt Lake City",
    "University of Wyoming": "Laramie",
    "Gonzaga University": "Spokane",
    "University of the Pacific": "Stockton",
    "Johns Hopkins University": "Baltimore",
    "Robert Morris University": "Moon Township",
    "University of Connecticut": "Storrs",
    "Pace University": "Nueva York",

    # ── Canadá ─────────────────────────────────────────────────────────────
    "University of Victoria": "Victoria",
    "Thompson River University TRU": "Kamloops",
    "Vancouver Island University VIU": "Nanaimo",
    "VGC": "Vancouver",

    # ── Resto ──────────────────────────────────────────────────────────────
    "Universidad Pontificia de Salamanca": "Salamanca",
    "Wintec": "Hamilton",
    "Monash College": "Melbourne",
    "Taylors College": "Sídney",          # el dominio es taylorssydney.edu.au
    "Orewa College": "Orewa",
    "Study in Valencia": "Valencia",
    "Azurlingua": "Niza",
    "College de Paris": "París",
    "Hamelin-Laie International School": "Barcelona",
    "Montgomery International School": "Bruselas",
    "Ermitage International School": "Maisons-Laffitte",
}

#: Las que se dejan SIN ciudad a propósito, con su razón.
#:
#: Existe para que esto no parezca un olvido. Si algún día la agencia confirma
#: la sede de alguna, se mueve arriba — pero con el dato confirmado, no con una
#: suposición.
SIN_CIUDAD_A_PROPOSITO = {
    "St Giles": "red con sedes en Brighton, Londres, Nueva York, Vancouver…",
    "Sprachcaffe": "red internacional de escuelas de idiomas",
    "Oxford House - OHC": "red con varias sedes en Reino Unido e Irlanda",
    "ELS": "red de centros dentro de campus universitarios de EE. UU.",
    "Amerigo": "red de colegios en varias ciudades de EE. UU.",
    "Nacel France": "red · sedes por toda Francia",
    "Nacel España": "red · sedes en varias ciudades españolas",
    "Summer Discovery": "programas de verano alojados en campus distintos cada año",
    "Academies Australasia": "grupo con varios colegios en Sídney y Melbourne",
    "ALG - Australian Learning Group": "sedes en Sídney, Melbourne y Brisbane",
    "Acknowledge Education Pty Ltd": "sedes en Melbourne, Sídney y Perth",
    "ELSIS": "sedes en Sídney, Melbourne y Brisbane",
    "Kaplan Business School - KBS": "sedes en cinco ciudades australianas",
    "EQUALS International": "opera en varias ciudades",
    "English Studio": "sedes en Londres y Dublín",
    "Sheridan College": "campus en Oakville, Brampton y Mississauga",
    "ESIC Universidad": "campus en Madrid, Valencia, Barcelona, Sevilla…",
    "Ifalpes": "sedes en Annecy y Chambéry",
    "Superior Training Centre": "sede no confirmada",
    "IEM Digital Business School": "sede no confirmada",
    "EIE Institute of Education": "sede en Malta no confirmada",
    "ACE English": "sede en Malta no confirmada",
    "RCIIS": "sede no confirmada",
    "ACLA - Atlantic Canada Language Academy": "sede no confirmada",
    "Study Abroad Canada Language Institute": "sede no confirmada",
    "SRH INTERNATIONAL COLLEGE (SRHIC)": "SRH tiene varios campus en Alemania",
    "Sainte Victoire International School": "sede no confirmada",
    "Australian College of Technology and Business-ACBT": (
        "sede no confirmada · y además su país está mal: la fila dice Estados "
        "Unidos con dominio acbt.net, que no es estadounidense"
    ),
    "ESSCA": "además su país está mal (dice España y es Francia · Angers)",
}


#: Institución → ciudad real, cuando el campo `ciudad` trae un ESTADO o una
#: PROVINCIA en vez de una ciudad.
#:
#: Es un problema distinto del hueco, y peor: "Illinois" no es un dato que
#: falte, es un dato **equivocado mostrado como si fuera cierto**. Un estudiante
#: que filtra por ciudad y ve "Illinois" con 633 programas no está viendo una
#: ciudad, y no tiene cómo saberlo. Medido: 5.383 filas en 70 instituciones,
#: con estados de EE. UU., provincias canadienses y hasta "Gales".
#:
#: Se corrige por institución y no traduciendo el estado, porque el estado no
#: determina la ciudad: en Illinois hay tres instituciones distintas y cada una
#: está en una ciudad diferente (Chicago, Normal, Springfield).
#:
#: Misma regla que la tabla de arriba: **sólo campus inequívoco**. Las que
#: tienen varias sedes se quedan con su estado — feo, pero no falso — y están
#: listadas en `REGION_SIN_RESOLVER` con su razón.
CIUDAD_REAL_POR_INSTITUCION = {
    # ── Estados Unidos ─────────────────────────────────────────────────────
    "University of Illinois Chicago (UIC)": "Chicago",
    "Illinois State University": "Normal",
    "University of Illinois Springfield (UIS)": "Springfield",
    "FIU - Florida International University": "Miami",
    "FIU English Language Institute": "Miami",
    "Nova Southeastern University": "Fort Lauderdale",
    "IMG Academy": "Bradenton",
    "Colorado State University": "Fort Collins",
    "Colorado Mesa University": "Grand Junction",
    "William Paterson University": "Wayne",
    "New Jersey Institute of Technology": "Newark",
    "Drew University": "Madison",
    "Texas State University": "San Marcos",
    "Texas A&M University-Corpus Christi": "Corpus Christi",
    "California State University San Marcos": "San Marcos",
    "Virginia Tech (Advantage VT)": "Blacksburg",
    "George Mason University": "Fairfax",
    "James Madison University": "Harrisonburg",
    "Fairfax Christian School": "Fairfax",
    "Oregon State University": "Corvallis",
    "Saginaw Valley State University": "University Center",
    "Webster University": "Webster Groves",
    "Missouri State University - MSU": "Springfield",
    "Montana State University": "Bozeman",
    "University of Nebraska at Omaha": "Omaha",
    "Mercer University": "Macon",
    "Towson University": "Towson",
    "Western Washington University": "Bellingham",
    "Inlingua Washington": "Washington D. C.",
    "University of Wisconsin- Stout": "Menomonie",
    "Wesli": "Madison",
    "University of Science and Arts of Oklahoma": "Chickasha",
    "The University of Utah - English Language Institute": "Salt Lake City",
    "Bridgeport International Academy (BIA)": "Bridgeport",
    # "Nueva York" es estado Y ciudad · sólo se corrigen las que NO están en la
    # ciudad. Manhattan College, Pace, Manhattan Language y NYLC se quedan como
    # están, porque ahí "Nueva York" es correcto.
    "RPI ensselaer Polytechnic Institute": "Troy",
    "Hartwick College": "Oneonta",
    "Mercy University": "Dobbs Ferry",

    # ── Canadá ─────────────────────────────────────────────────────────────
    "NAIT": "Edmonton",
    "BCIT": "Burnaby",
    "Red River College": "Winnipeg",
    "University of Windsor": "Windsor",
    "Lakehead University": "Thunder Bay",
    "Pickering College": "Newmarket",
    "Edu Inter": "Quebec",
    "College international Mont-Tremblant": "Mont-Tremblant",

    # ── Resto ──────────────────────────────────────────────────────────────
    "Cardiff University": "Cardiff",
    "The University of Queensland": "Brisbane",
    "Cairns College of English & Business - CCEB": "Cairns",
    "Gold Coast International College": "Gold Coast",
    "Gold Coast Learning Centre": "Gold Coast",
}

#: Las que se quedan con el estado/provincia, y por qué.
REGION_SIN_RESOLVER = {
    "Niagara College": "campus en Welland y Niagara-on-the-Lake",
    "St. Lawrence College - SLC": "campus en Kingston, Brockville y Cornwall",
    "Southern Cross University": "campus en Lismore, Gold Coast y Coffs Harbour",
    "Lester B. Pearson School Board": "distrito escolar · varias sedes",
    "High School Central Quebec SD": "distrito escolar · varias sedes",
    "Avon Maitland Schools": "distrito escolar · varias sedes",
    "Pepperdine University (Graziadio Business School)": "sedes en Malibú y West LA",
    "EQI": "Education Queensland International · red de colegios públicos",
    "Sarina Russo": "sedes en varias ciudades australianas",
    "CCI-LEX": "sede no confirmada",
    "English Language Centre ELC": "sede no confirmada",
    "Encompass": "sede no confirmada",
    "LCI Language Consultants Intenational": "sede no confirmada",
    "Excel English Institute": "sede no confirmada",
    "Pacific International Academy": "sede no confirmada",
    # Ésta no es un problema de ciudad sino de país, y hay que mirarla aparte.
    "Saint George´s University": (
        "su ciudad dice Nueva York pero la universidad está en Granada · "
        "revisar también el país antes de tocar la ciudad"
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true",
                    help="sin esto sólo se reporta, no se escribe")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        sin_ciudad = db.execute(text(
            "SELECT institucion, count(*) FROM programas_investigados "
            " WHERE activo AND (ciudad IS NULL OR ciudad = '') "
            " GROUP BY institucion"
        )).fetchall()
        pendientes = {i: n for i, n in sin_ciudad}

        print("=" * 72)
        print("CIUDADES ·", "APLICA" if args.commit else "SIMULACRO")
        print("=" * 72)
        print(f"instituciones sin ciudad : {len(pendientes)}")
        print(f"programas sin ciudad     : {sum(pendientes.values())}")

        # ── Lo que la tabla no cubre · se dice, no se esconde ──────────────
        desconocidas = sorted(
            i for i in pendientes
            if i not in CIUDAD_POR_INSTITUCION and i not in SIN_CIUDAD_A_PROPOSITO
        )
        if desconocidas:
            print(f"\n!! {len(desconocidas)} institución(es) que la tabla no conoce "
                  f"—ni para rellenar ni para excluir—:")
            for i in desconocidas:
                print(f"    {pendientes[i]:>5}  {i}")
            print("  Revísalas y decide: campus único (arriba) o red (abajo).")

        # ── Filas de la tabla que ya no corresponden a nada ────────────────
        fantasma = sorted(set(CIUDAD_POR_INSTITUCION) - set(pendientes))
        if fantasma:
            print(f"\n!! {len(fantasma)} fila(s) de la tabla sin efecto "
                  f"(ya tienen ciudad, o el nombre cambió):")
            for i in fantasma:
                print(f"    {i}")

        # ── Segunda parte · la ciudad que es un estado o una provincia ─────
        con_region = dict(db.execute(text(
            "SELECT institucion, count(*) FROM programas_investigados "
            " WHERE activo AND institucion = ANY(:i) "
            " GROUP BY institucion"
        ), {"i": list(CIUDAD_REAL_POR_INSTITUCION)}).fetchall())

        aplicables = {i: c for i, c in CIUDAD_POR_INSTITUCION.items() if i in pendientes}
        total = sum(pendientes[i] for i in aplicables)
        excluidos = sum(pendientes.get(i, 0) for i in SIN_CIUDAD_A_PROPOSITO)

        print(f"\nse rellenan  : {total} programas · {len(aplicables)} instituciones")
        print(f"se dejan     : {excluidos} programas · "
              f"{len([i for i in SIN_CIUDAD_A_PROPOSITO if i in pendientes])} redes o multi-campus")
        print(f"quedarán sin ciudad: {sum(pendientes.values()) - total}")
        print(f"\nse corrigen  : {sum(con_region.values())} programas cuya "
              f"\"ciudad\" era un estado o provincia · "
              f"{len(con_region)} instituciones")
        print(f"se dejan     : {len(REGION_SIN_RESOLVER)} con varias sedes o sin confirmar")

        if not args.commit:
            print("\nSIMULACRO · no se escribió nada. Repetir con --commit.")
            return 0

        for institucion, ciudad in aplicables.items():
            n = db.execute(text(
                "UPDATE programas_investigados SET ciudad = :c "
                " WHERE activo AND institucion = :i AND (ciudad IS NULL OR ciudad = '')"
            ), {"c": ciudad, "i": institucion}).rowcount
            print(f"  {n:>5}  {institucion[:44]:<46} -> {ciudad}")
        for institucion, ciudad in CIUDAD_REAL_POR_INSTITUCION.items():
            # Se pisa la región cualquiera que sea · la condición es la
            # institución, no el valor viejo: si mañana dice "IL" en vez de
            # "Illinois", el arreglo sigue aplicando.
            n = db.execute(text(
                "UPDATE programas_investigados SET ciudad = :c "
                " WHERE activo AND institucion = :i AND coalesce(ciudad,'') <> :c"
            ), {"c": ciudad, "i": institucion}).rowcount
            if n:
                print(f"  {n:>5}  {institucion[:44]:<46} -> {ciudad}")
        db.commit()

        restantes = db.execute(text(
            "SELECT count(*) FROM programas_investigados "
            " WHERE activo AND (ciudad IS NULL OR ciudad = '')"
        )).scalar()
        print(f"\nLISTO · quedan sin ciudad: {restantes}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
