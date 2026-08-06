"""CV-2 · Traer el perfil de LinkedIn sin scraping.

Se pidió un *"scraper de LinkedIn"*. No se construyó como scraper: sus términos
de servicio lo prohíben y no funcionaría con perfiles privados. En su lugar la
persona pega su propio perfil y la IA lo estructura.

Lo que protegen estos tests, en orden de importancia:

 1. Que el endpoint **no escriba** la hoja de vida. Devuelve una propuesta. Es su
    CV, lleva su nombre, y A3 fue justamente "debe poder editarse".
 2. Que lo que devuelve el modelo se **limpie y acote** antes de tocar nada — un
    modelo puede devolver cualquier cosa y esto acaba en un documento real.
 3. Que un texto de dos palabras no dispare una llamada de IA.

No se llama al modelo de verdad en ningún test: se prueba el normalizado y la
traducción a overrides, que es donde están las decisiones.
"""
from __future__ import annotations

import pytest

from app.services import linkedin_import_service as li


# ---------------------------------------------------------------------------
# Normalizado · nunca confiar en lo que devuelve el modelo
# ---------------------------------------------------------------------------


def test_normaliza_un_perfil_tipico():
    salida = li.normalizar(
        {
            "headline": "  Ingeniera de datos  ",
            "summary": "Trabajo con datos hace 5 años.",
            "strengths": ["SQL", "  ", "Comunicación", None],
            "interests": ["Analítica"],
            "experience": [
                {"role": "Analista", "organization": "Bancolombia", "period": "2021-2024"}
            ],
            "education": [{"title": "Ingeniería", "institution": "EAFIT", "period": "2020"}],
        }
    )
    assert salida["headline"] == "Ingeniera de datos"
    # Los vacíos y los None se caen
    assert salida["strengths"] == ["SQL", "Comunicación"]
    assert salida["experience"][0]["organization"] == "Bancolombia"


def test_un_modelo_que_devuelve_basura_no_rompe_nada():
    salida = li.normalizar(
        {
            "headline": None,
            "strengths": "esto debería ser una lista",
            "experience": ["texto suelto", 42, {"role": "Válido"}],
            "education": None,
        }
    )
    assert salida["headline"] is None
    assert salida["strengths"] == []
    # Sólo sobrevive la entrada que era un dict con contenido
    assert salida["experience"] == [
        {"role": "Válido", "organization": None, "period": None}
    ]
    assert salida["education"] == []


def test_se_acotan_los_tamanos():
    salida = li.normalizar(
        {
            "headline": "x" * 500,
            "strengths": [f"fortaleza {i}" for i in range(50)],
            "experience": [{"role": f"puesto {i}"} for i in range(30)],
        }
    )
    assert len(salida["headline"]) <= 120
    assert len(salida["strengths"]) <= 6
    assert len(salida["experience"]) <= 8


# ---------------------------------------------------------------------------
# No gastar IA en vano
# ---------------------------------------------------------------------------


def test_texto_demasiado_corto_no_llama_al_modelo():
    with pytest.raises(li.LinkedInImportError) as exc:
        li.importar_desde_texto("Soy Ana")
    assert "más de tu perfil" in str(exc.value)


def test_texto_vacio_tampoco():
    with pytest.raises(li.LinkedInImportError):
        li.importar_desde_texto("   ")


# ---------------------------------------------------------------------------
# Extracción del JSON · el modelo a veces envuelve la respuesta
# ---------------------------------------------------------------------------


def test_tolera_code_fences():
    d = li._extraer_json('```json\n{"headline": "Diseñadora"}\n```')
    assert d["headline"] == "Diseñadora"


def test_tolera_texto_alrededor():
    d = li._extraer_json('Claro, aquí tienes:\n{"headline": "Docente"}\nEspero que sirva.')
    assert d["headline"] == "Docente"


def test_si_no_hay_json_lo_dice_claro():
    with pytest.raises(li.LinkedInImportError):
        li._extraer_json("No pude procesar el perfil.")


# ---------------------------------------------------------------------------
# Traducción a la hoja de vida
# ---------------------------------------------------------------------------


def test_la_experiencia_no_se_pierde_aunque_el_cv_no_tenga_campo_propio():
    overrides = li.a_overrides(
        li.normalizar(
            {
                "summary": "Llevo 5 años en analítica.",
                "experience": [
                    {"role": "Analista", "organization": "Bancolombia", "period": "2021-2024"},
                    {"role": "Practicante", "organization": "Sura", "period": "2020"},
                ],
            }
        )
    )
    assert "Llevo 5 años en analítica." in overrides["summary"]
    assert "Analista en Bancolombia (2021-2024)" in overrides["summary"]
    assert "Practicante en Sura" in overrides["summary"]


def test_solo_manda_los_campos_que_de_verdad_vienen():
    """Si el perfil no traía intereses, no se manda una lista vacía que pise
    lo que la persona ya hubiera escrito a mano."""
    overrides = li.a_overrides(li.normalizar({"headline": "Chef"}))
    assert overrides == {"headline": "Chef"}
    assert "interests" not in overrides
    assert "strengths" not in overrides


def test_los_overrides_encajan_con_los_campos_editables_del_cv():
    """Contrato con `cv_profile_service`: si alguien renombra un campo allá,
    este test lo detecta antes de que la importación deje de guardar nada."""
    from app.services import cv_profile_service as cvs

    overrides = li.a_overrides(
        li.normalizar(
            {
                "headline": "Chef",
                "summary": "Cocino hace años.",
                "strengths": ["Pastelería"],
                "interests": ["Gastronomía"],
            }
        )
    )
    permitidos = set(cvs._TEXT_FIELDS) | set(cvs._LIST_FIELDS)
    assert set(overrides).issubset(permitidos), set(overrides) - permitidos
