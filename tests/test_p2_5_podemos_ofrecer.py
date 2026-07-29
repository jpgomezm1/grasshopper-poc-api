"""P2-5 · Decirle al modelo qué podemos vender de cada institución · Sprint 3.

Verónica (A8): "en el archivo de Excel yo solamente tengo instituciones... dice que
de la institución A puedo vender Foundations, pregrados y maestrías".

Ese dato YA venía en el Excel y quedaba enterrado en `Program.raw`, que el query
slim no cargaba. Sin él, el modelo podía recomendar una maestría en una institución
de la que solo podemos gestionar cursos de idiomas.

Esto NO resuelve A8 completo (buscar los programas concretos de cada institución es
P2-4, un proyecto). Resuelve la mitad barata: no proponer un nivel que no podemos
gestionar.
"""
from __future__ import annotations

from app.services.catalog_service import _normalize_programs_offered
from app.services.recommendation_service import _format_catalog_block


def _slim(**kw):
    base = dict(
        program_id="X", program_name="Test", category="carrera_completa",
        countries=[], duration={}, cost={}, budget_tier=None,
        language_requirement=None, scholarships_for_latam=None,
        programs_offered=None, tags=[], _budget_fit_hint="unknown",
    )
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Normalización · el Excel del cliente viene sucio
# ---------------------------------------------------------------------------


def test_deduplica_sin_distinguir_mayusculas():
    """El Excel real trae "High School" y "High school" como entradas separadas,
    y repite "Idiomas" dentro de la misma fila."""
    assert _normalize_programs_offered(["Idiomas", "Idiomas"]) == ["Idiomas"]
    assert _normalize_programs_offered(["High School", "High school"]) == ["High School"]


def test_conserva_el_orden_y_la_primera_grafia():
    assert _normalize_programs_offered(
        ["Pregrado", "Idiomas", "pregrado"]
    ) == ["Pregrado", "Idiomas"]


def test_ausencia_de_dato_es_None_no_lista_vacia():
    """None = "no lo tenemos cargado". [] diría "no vende nada". No es lo mismo."""
    for vacio in (None, [], ["", "  "], "no-es-lista", {}):
        assert _normalize_programs_offered(vacio) is None


# ---------------------------------------------------------------------------
# Lo que ve el modelo
# ---------------------------------------------------------------------------


def test_el_modelo_recibe_lo_que_podemos_ofrecer():
    bloque = _format_catalog_block([
        _slim(programs_offered=["Pregrado & Postgrado", "Idiomas"])
    ])
    assert "podemos_ofrecer=Pregrado & Postgrado, Idiomas" in bloque


def test_sin_dato_la_clave_se_OMITE_en_vez_de_decir_ninguno():
    """Si mandáramos "podemos_ofrecer=ninguno", el modelo no podría distinguir
    "no vendemos nada ahí" de "no lo tenemos cargado" — y con el 77% del catálogo
    sin curar, concluiría lo primero."""
    bloque = _format_catalog_block([_slim(programs_offered=None)])
    assert "podemos_ofrecer" not in bloque
    # pero el resto de la línea sigue intacto
    assert "id=X" in bloque and "tags=" in bloque


def test_el_bloque_sigue_bien_formado_con_y_sin_el_dato():
    bloque = _format_catalog_block([
        _slim(program_id="A", programs_offered=["Idiomas"]),
        _slim(program_id="B", programs_offered=None),
    ])
    lineas = [l for l in bloque.split("\n") if l.strip()]
    assert len(lineas) == 2
    assert all(l.startswith("- id=") for l in lineas)
    assert " ·  · " not in bloque  # sin separadores huérfanos
