"""Un matiz del modelo no puede costarle el perfil entero al estudiante.

Visto en vivo el 2026-09-19, generando un perfil real contra Claude: el modelo
devolvió `"medio-alto"` como nivel de una dimensión de personalidad. El schema
aceptaba sólo `alto|medio|bajo`, así que Pydantic rechazó **el objeto completo**
y la generación termino en `ConsolidationFailure`:

    pydantic_core.ValidationError: 1 validation error for ConsolidatedProfile
    personality_dimensions.2.level
      Input should be 'alto', 'medio' or 'bajo' [input_value='medio-alto']

El estudiante veía "Análisis no disponible · reintenta en breve", sin perfil y
sin recomendaciones, por un guion en el decimoquinto campo de quince buenos. Y
es **no determinista**: con los mismos datos, unos estudiantes lo sufren y otros
no, lo que lo vuelve casi imposible de reproducir desde un reporte de soporte.
"""
from __future__ import annotations

import pytest

from app.schemas.consolidated_profile import PersonalityDimension


def _nivel(valor):
    return PersonalityDimension(name="Apertura", level=valor, insight="x").level


# ---------------------------------------------------------------------------
# El caso que se vio en produccion
# ---------------------------------------------------------------------------


def test_el_compuesto_que_tumbo_un_perfil_real():
    """"medio-alto" tira hacia alto · es la convención del compuesto en español."""
    assert _nivel("medio-alto") == "alto"


def test_el_compuesto_al_reves_tira_hacia_el_ultimo():
    assert _nivel("bajo-medio") == "medio"


@pytest.mark.parametrize("valor,esperado", [
    ("alto", "alto"), ("medio", "medio"), ("bajo", "bajo"),
    ("Alta", "alto"), ("MEDIA", "medio"), ("Baja", "bajo"),
    ("  alto  ", "alto"),
    ("moderadamente alto", "alto"),
    ("nivel bajo", "bajo"),
])
def test_variantes_que_el_modelo_produce(valor, esperado):
    assert _nivel(valor) == esperado


def test_lo_irreconocible_cae_al_neutro_y_no_revienta():
    """Antes que perder el perfil, el neutro · la dimensión conserva su
    `insight`, que es donde está el contenido de verdad."""
    assert _nivel("indeterminado") == "medio"
    assert _nivel("") == "medio"
    assert _nivel(None) == "medio"


def test_el_perfil_completo_sobrevive_al_matiz():
    """La prueba de que el arreglo sirve donde dolía: un `ConsolidatedProfile`
    entero con una dimensión rara ya no se pierde."""
    from app.schemas.consolidated_profile import ConsolidatedProfile

    perfil = ConsolidatedProfile(
        summary_narrative="x" * 250,
        strengths=["Empatía", "Constancia", "Observación"],
        interests=["Biología", "Diseño", "Servicio"],
        personality_dimensions=[
            {"name": "Apertura", "level": "medio-alto", "insight": "Disfruta explorar."},
            {"name": "Responsabilidad", "level": "alto", "insight": "Termina lo que empieza."},
        ],
    )
    assert [d.level for d in perfil.personality_dimensions] == ["alto", "alto"]
    # Y lo que importaba: los otros catorce campos siguen ahí.
    assert perfil.strengths == ["Empatía", "Constancia", "Observación"]
