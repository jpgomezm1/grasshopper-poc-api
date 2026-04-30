"""
GH-S1-BE-01 · Genera catalogo dummy sintetico para arrancar el delivery.

Output: samples/catalog_dummy.xlsx con 80 programas sinteticos cubriendo
        todos los campos del schema definido en CLIENTE_DELIVERABLES.md item #1.

Variabilidad cubierta:
- 12 paises (USA, Canada, UK, Australia, Espana, Alemania, Francia, Holanda, Irlanda, Italia, Suiza, Argentina)
- 4 tiers de presupuesto (bajo, medio, alto, premium)
- 3 tipos de alianza (preferencial, estandar, convenio)
- Duraciones de 6 meses a 4 anos
- 18 areas de conocimiento

Uso:
    cd backend
    source venv/bin/activate
    python scripts/generate_catalog_dummy.py
"""
from __future__ import annotations

import random
from pathlib import Path

try:
    from openpyxl import Workbook
except ImportError:
    raise SystemExit("openpyxl no instalado. Ejecutar: pip install openpyxl")


random.seed(42)  # reproducible

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT_ROOT / "samples" / "catalog_dummy.xlsx"


COUNTRIES = [
    ("USA", "USD", ["Boston", "New York", "San Francisco", "Chicago", "Los Angeles", "Miami"]),
    ("Canada", "CAD", ["Toronto", "Vancouver", "Montreal", "Ottawa"]),
    ("Reino Unido", "GBP", ["Londres", "Manchester", "Edinburgo", "Bristol"]),
    ("Australia", "AUD", ["Sydney", "Melbourne", "Brisbane", "Perth"]),
    ("Espana", "EUR", ["Madrid", "Barcelona", "Valencia", "Sevilla"]),
    ("Alemania", "EUR", ["Berlin", "Munich", "Hamburgo", "Frankfurt"]),
    ("Francia", "EUR", ["Paris", "Lyon", "Marsella", "Niza"]),
    ("Holanda", "EUR", ["Amsterdam", "Rotterdam", "La Haya", "Utrecht"]),
    ("Irlanda", "EUR", ["Dublin", "Cork", "Galway"]),
    ("Italia", "EUR", ["Roma", "Milan", "Florencia", "Bolonia"]),
    ("Suiza", "CHF", ["Zurich", "Ginebra", "Lausana"]),
    ("Argentina", "USD", ["Buenos Aires", "Cordoba", "Mendoza"]),
]

INSTITUTIONS = {
    "USA": ["Boston University", "New York University", "Stanford University", "University of Chicago", "UCLA", "University of Miami"],
    "Canada": ["University of Toronto", "UBC", "McGill University", "University of Ottawa"],
    "Reino Unido": ["University College London", "University of Manchester", "University of Edinburgh", "University of Bristol"],
    "Australia": ["University of Sydney", "University of Melbourne", "University of Queensland", "UWA"],
    "Espana": ["IE University", "ESADE", "Universidad de Valencia", "Universidad de Sevilla"],
    "Alemania": ["TU Berlin", "LMU Munich", "Universitat Hamburg", "Goethe University"],
    "Francia": ["Sciences Po Paris", "Universite de Lyon", "Aix-Marseille Universite", "Universite Cote d'Azur"],
    "Holanda": ["University of Amsterdam", "Erasmus University Rotterdam", "Leiden University", "Utrecht University"],
    "Irlanda": ["Trinity College Dublin", "University College Cork", "University of Galway"],
    "Italia": ["Sapienza Universita", "Politecnico di Milano", "Universita di Firenze", "Alma Mater Studiorum Bologna"],
    "Suiza": ["ETH Zurich", "Universite de Geneve", "EPFL"],
    "Argentina": ["Universidad de Buenos Aires", "Universidad Nacional de Cordoba", "Universidad Nacional de Cuyo"],
}

AREAS = [
    ("Negocios y Administracion", ["Business Administration", "International Business", "Marketing", "Finance", "Entrepreneurship"]),
    ("Ingenieria", ["Computer Engineering", "Mechanical Engineering", "Civil Engineering", "Industrial Engineering"]),
    ("Tecnologia", ["Computer Science", "Data Science", "AI & Machine Learning", "Cybersecurity", "Software Engineering"]),
    ("Salud", ["Public Health", "Nursing", "Biomedical Science", "Nutrition", "Psychology"]),
    ("Diseno y Arte", ["Graphic Design", "Industrial Design", "Fine Arts", "Animation", "Film Studies"]),
    ("Comunicacion", ["Journalism", "Media Studies", "Public Relations", "Digital Communication"]),
    ("Ciencias Sociales", ["International Relations", "Political Science", "Sociology", "Economics"]),
    ("Educacion", ["Education", "TESOL", "Educational Leadership"]),
    ("Hospitalidad", ["Hospitality Management", "Tourism", "Culinary Arts"]),
    ("Idiomas", ["English Language", "Spanish Language", "French Language", "German Language"]),
]

PROGRAM_TYPES = [
    ("Pregrado", 36, 48, "high"),     # 3-4 years
    ("Maestria", 12, 24, "high"),     # 1-2 years
    ("Especializacion", 6, 12, "medium"),
    ("Curso de Idioma", 3, 12, "low"),
    ("Diplomado", 6, 12, "medium"),
    ("Certificado Profesional", 4, 9, "low"),
    ("Doctorado", 36, 60, "premium"),
    ("Bootcamp", 3, 6, "medium"),
]

TIER_RANGES = {
    "low": (3000, 9000),
    "medium": (9000, 22000),
    "high": (22000, 45000),
    "premium": (45000, 95000),
}

ALLIANCES = ["preferencial", "estandar", "convenio"]
LANGUAGES_REQ = ["B1", "B2", "C1", "C2", "Sin requisito (espanol nativo)"]


def slugify(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace(".", "")
        .replace("&", "y")
    )


def generate_programs(n: int = 80) -> list[dict]:
    rows: list[dict] = []
    pid = 1
    for _ in range(n):
        country, currency, cities = random.choice(COUNTRIES)
        institutions = INSTITUTIONS[country]
        institution = random.choice(institutions)
        city = random.choice(cities)
        area_name, subjects = random.choice(AREAS)
        subject = random.choice(subjects)
        ptype, dur_min, dur_max, default_tier = random.choice(PROGRAM_TYPES)
        duration_months = random.randint(dur_min, dur_max)
        # tier varia ligeramente
        tier_choices = {"low": ["low", "medium"], "medium": ["low", "medium", "high"], "high": ["medium", "high", "premium"], "premium": ["high", "premium"]}
        tier = random.choice(tier_choices[default_tier])
        cost_min, cost_max = TIER_RANGES[tier]
        cost_total = random.randint(cost_min, cost_max)
        alliance = random.choices(ALLIANCES, weights=[3, 5, 2])[0]
        # programs en pais hispanoparlante no requieren ingles
        lang_req = "Sin requisito (espanol nativo)" if country in ("Espana", "Argentina") else random.choice(LANGUAGES_REQ[:4])

        program_name = f"{ptype} en {subject}"
        rows.append({
            "program_id": f"GHP-{pid:04d}",
            "name": program_name,
            "slug": slugify(f"{program_name}-{institution}-{city}"),
            "country": country,
            "city": city,
            "institution": institution,
            "type": ptype,
            "area": area_name,
            "subject": subject,
            "duration_months": duration_months,
            "duration_label": f"{duration_months} meses" if duration_months < 12 else f"{duration_months // 12} ano(s) {duration_months % 12 or ''} mes(es)".strip(),
            "cost_total": cost_total,
            "currency": currency,
            "cost_includes": "Matricula y materiales academicos",
            "cost_excludes": "Alojamiento, manutencion, seguro medico, vuelos",
            "budget_tier": tier,
            "alliance_type": alliance,
            "language_requirement": lang_req,
            "min_age": random.choice([16, 17, 18]),
            "academic_requirement": random.choice(["Bachillerato", "Pregrado completado", "Notas minimas 3.5/5.0", "Portafolio"]),
            "cohort_starts": random.choice(["Enero", "Marzo", "Mayo", "Agosto", "Septiembre", "Octubre"]),
            "next_intake": random.choice(["2026-08", "2027-01", "2027-03", "2027-09"]),
            "tags": ", ".join(random.sample(["internacional", "tecnologia", "innovacion", "investigacion", "practica", "becas-disponibles", "online", "presencial", "intercambio"], k=3)),
            "url": f"https://www.{slugify(institution)}.edu/programs/{slugify(program_name)}",
            "active": True,
        })
        pid += 1
    return rows


def main() -> None:
    rows = generate_programs(80)
    wb = Workbook()
    ws = wb.active
    ws.title = "Programas"
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row[h] for h in headers])

    # tab de schema/diccionario
    ws2 = wb.create_sheet("Diccionario")
    ws2.append(["Campo", "Tipo", "Obligatorio", "Descripcion"])
    diccionario = [
        ("program_id", "string", "si", "ID unico interno (Grasshopper)"),
        ("name", "string", "si", "Nombre del programa"),
        ("slug", "string", "si", "Slug url-safe"),
        ("country", "string", "si", "Pais del programa"),
        ("city", "string", "si", "Ciudad"),
        ("institution", "string", "si", "Universidad / institucion"),
        ("type", "string", "si", "Pregrado | Maestria | Especializacion | etc."),
        ("area", "string", "si", "Area de conocimiento"),
        ("subject", "string", "si", "Tema especifico"),
        ("duration_months", "int", "si", "Duracion total en meses"),
        ("duration_label", "string", "no", "Etiqueta legible"),
        ("cost_total", "int", "si", "Costo total estimado en moneda local"),
        ("currency", "string", "si", "USD | EUR | GBP | CAD | AUD | CHF"),
        ("cost_includes", "string", "no", "Que incluye el costo"),
        ("cost_excludes", "string", "no", "Que NO incluye"),
        ("budget_tier", "enum", "si", "low | medium | high | premium"),
        ("alliance_type", "enum", "si", "preferencial | estandar | convenio"),
        ("language_requirement", "string", "no", "Nivel CEFR minimo de idioma"),
        ("min_age", "int", "no", "Edad minima"),
        ("academic_requirement", "string", "no", "Requisito academico previo"),
        ("cohort_starts", "string", "no", "Mes(es) de inicio"),
        ("next_intake", "string", "no", "Proxima cohort YYYY-MM"),
        ("tags", "string", "no", "Tags separados por coma"),
        ("url", "string", "no", "Link a la pagina del programa"),
        ("active", "bool", "si", "Activo en catalogo"),
    ]
    for r in diccionario:
        ws2.append(r)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT)
    print(f"[OK] Catalogo dummy generado: {OUTPUT}")
    print(f"     {len(rows)} programas en {len(set(r['country'] for r in rows))} paises")
    print(f"     Tiers: {sorted(set(r['budget_tier'] for r in rows))}")


if __name__ == "__main__":
    main()
