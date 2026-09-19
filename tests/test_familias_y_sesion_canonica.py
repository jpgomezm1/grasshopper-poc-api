"""La consejería llega al motor · y una sola sesión manda · 2026-09-18.

Dos huecos de la misma auditoría, distintos entre sí:

1. **`career_families` no llegaba a ningún motor.** Se genera desde
   `consolidate_v2`, se le muestra a la persona en `TuLecturaCard` y en el PDF,
   y ni el recomendador (`recommendation_service`) ni la búsqueda
   (`busqueda_programas`) la miraban: los dos leían `suggested_career_paths`,
   que son sólo los nombres. El consejo más elaborado del sistema no influía en
   lo que se le recomienda.

2. **Dos definiciones de "la sesión del estudiante".** `POST /sessions` y el
   chat de Mento usaban la más antigua; el perfil consolidado, el CRM y el
   dossier la última actualizada. Con sesiones duplicadas —que los races
   produjeron, según el propio código— el perfil se armaba sobre una sesión y
   Mento leía otra.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.busqueda_programas import _rutas_del_perfil
from app.services.recommendation_service import _format_families_block
from app.services.sesion_canonica import respuestas_canonicas, sesion_canonica


def _familia(nombre, careers=(), fit="alto", why="Porque te gusta el detalle."):
    return {
        "name": nombre,
        "fit_level": fit,
        "why_it_fits": why,
        "what_its_like": "Se trabaja en equipo.",
        "careers": list(careers),
        "watch_out": None,
    }


# ---------------------------------------------------------------------------
# Los oficios de cada familia entran al vector de búsqueda
# ---------------------------------------------------------------------------


def test_los_oficios_de_la_familia_entran_a_las_rutas():
    """"Salud y cuidado animal" no se parece a ningún programa del catálogo;
    "Veterinaria" sí. Ese es todo el punto."""
    rutas = _rutas_del_perfil(
        {
            "career_families": [
                _familia("Salud y cuidado animal", ["Veterinaria", "Zootecnia"])
            ],
            "suggested_career_paths": ["Salud y cuidado animal"],
        }
    )
    assert "Veterinaria" in rutas
    assert "Zootecnia" in rutas
    assert "Salud y cuidado animal" in rutas


def test_el_orden_lo_pone_el_modelo():
    """La primera familia es la de mayor calce · si el orden se pierde, el
    vector pesa igual algo que el consejero puso de tercero."""
    rutas = _rutas_del_perfil(
        {
            "career_families": [
                _familia("Primera", ["Oficio A"]),
                _familia("Segunda", ["Oficio B"]),
            ]
        }
    )
    assert rutas.index("Primera") < rutas.index("Segunda")
    assert rutas.index("Oficio A") < rutas.index("Segunda")


def test_no_se_repite_lo_que_ya_esta():
    """El nombre de la familia suele repetirse dentro de sus propios oficios, y
    `suggested_career_paths` es su espejo: sin dedupe, el vector se sesga hacia
    lo que el modelo escribió dos veces."""
    rutas = _rutas_del_perfil(
        {
            "career_families": [_familia("Enfermería", ["Enfermería", "enfermería"])],
            "suggested_career_paths": ["ENFERMERÍA"],
        }
    )
    assert len(rutas) == 1


def test_un_perfil_viejo_sin_familias_sigue_funcionando():
    """Los perfiles anteriores a `consolidate_v2` no traen familias. Perder sus
    rutas sería quitarle orden semántico a quien ya lo tenía."""
    rutas = _rutas_del_perfil(
        {"suggested_career_paths": ["Producto digital", "Ingeniería ambiental"]}
    )
    assert rutas == ["Producto digital", "Ingeniería ambiental"]


def test_un_perfil_vacio_no_revienta():
    assert _rutas_del_perfil({}) == []
    assert _rutas_del_perfil({"career_families": None}) == []
    # Una familia mal formada (no-dict) se ignora en vez de tumbar la búsqueda.
    assert _rutas_del_perfil({"career_families": ["texto suelto"]}) == []


def test_las_rutas_cambian_la_firma_del_vector():
    """Si la firma no cambia, el vector cacheado se sigue usando y los oficios
    nuevos nunca llegan a ordenar nada."""
    from app.services.busqueda_programas import PerfilBusqueda

    sin = PerfilBusqueda(rutas=["Salud y cuidado animal"])
    con = PerfilBusqueda(rutas=["Salud y cuidado animal", "Veterinaria"])
    assert sin.firma != con.firma


# ---------------------------------------------------------------------------
# Las familias llegan al prompt del recomendador
# ---------------------------------------------------------------------------


def _perfil(familias):
    """El recomendador recibe el `ConsolidatedProfile` ya validado (atributos);
    la búsqueda lee el JSON crudo de `profile_data` (dicts). Son dos caminos
    distintos a propósito, y por eso se prueban con la forma de cada uno: un
    doble que se equivoque de forma aquí no probaría nada."""
    from app.schemas.consolidated_profile import CareerFamily

    if familias is None:
        return SimpleNamespace(career_families=None)
    return SimpleNamespace(
        career_families=[CareerFamily(**f) for f in familias]
    )


def test_el_bloque_de_familias_trae_oficios_y_porque():
    bloque = _format_families_block(
        _perfil([_familia("Producto digital", ["UX", "Product manager"],
                          why="Porque disfrutas entender cómo piensa la gente.")])
    )
    assert "Producto digital" in bloque
    assert "Product manager" in bloque
    assert "cómo piensa la gente" in bloque


def test_el_bloque_dice_el_nivel_de_calce():
    """"alto" y "a explorar" no se recomiendan igual; sin el nivel el modelo los
    trata como equivalentes."""
    bloque = _format_families_block(
        _perfil([_familia("Docencia", ["Licenciatura"], fit="a explorar")])
    )
    assert "a explorar" in bloque


def test_sin_familias_el_bloque_es_vacio():
    """Perfil viejo · el prompt no debe ganar un encabezado sin contenido
    debajo, que el modelo leería como "no tiene familias"."""
    assert _format_families_block(_perfil([])) == ""
    assert _format_families_block(_perfil(None)) == ""


def test_el_bloque_llega_al_prompt_completo():
    """La prueba de que están conectadas, no sólo formateadas."""
    from app.services.recommendation_service import _format_profile_block

    perfil = SimpleNamespace(
        summary_narrative="Resumen.", strengths=["a"], interests=["b"],
        values=[], learning_style=None, work_style=None, holland_codes=[],
        personality_dimensions=[], suggested_career_paths=["Salud animal"],
        constraints=[],
        career_families=_perfil(
            [_familia("Salud animal", ["Veterinaria"])]
        ).career_families,
    )
    assert "Veterinaria" in _format_profile_block(perfil)


# ---------------------------------------------------------------------------
# Una sola sesión canónica
# ---------------------------------------------------------------------------


def _db(sesiones):
    db = MagicMock()
    cadena = db.query.return_value
    cadena.filter.return_value = cadena
    cadena.order_by.return_value = cadena
    cadena.all.return_value = sesiones
    return db


def _sesion(answers):
    return SimpleNamespace(id=uuid4(), answers=answers)


def test_manda_la_mas_antigua_cuando_tiene_respuestas():
    """La regla canónica de `sessions.py`: es donde escribe el producto."""
    vieja, nueva = _sesion({"lifeStage": "11°"}), _sesion({"lifeStage": "otra"})
    assert sesion_canonica(_db([vieja, nueva]), uuid4()) is vieja


def test_una_duplicada_vacia_no_borra_el_journey():
    """La salvaguarda. Aplicar "la más antigua" a secas le habría dejado el
    perfil en blanco a quien llenó el journey en la segunda sesión — peor que
    la inconsistencia que esto viene a arreglar."""
    cascaron, llena = _sesion({}), _sesion({"lifeStage": "11°"})
    assert sesion_canonica(_db([cascaron, llena]), uuid4()) is llena


def test_si_ninguna_tiene_respuestas_devuelve_la_primera():
    a, b = _sesion({}), _sesion(None)
    assert sesion_canonica(_db([a, b]), uuid4()) is a


def test_sin_sesiones_devuelve_none():
    assert sesion_canonica(_db([]), uuid4()) is None


@pytest.mark.parametrize("sesiones", [[], [_sesion({})], [_sesion(None)]])
def test_las_respuestas_siempre_son_un_dict(sesiones):
    """Quien llama mete esto en prompts · un None se colaría como "None"."""
    assert respuestas_canonicas(_db(sesiones), uuid4()) == {}


def test_el_perfil_consolidado_usa_la_misma_sesion_que_el_chat():
    """El punto entero del cambio: `consolidation_service` leía la última
    actualizada y `hop_chat_service` la más antigua."""
    from app.services.consolidation_service import _latest_session_answers

    cascaron, llena = _sesion({}), _sesion({"lifeStage": "11°"})
    db = _db([cascaron, llena])
    assert _latest_session_answers(db, uuid4()) == {"lifeStage": "11°"}
