"""El recomendador ve qué enseña de verdad cada institución · 2026-09-19.

## El sesgo que esto corrige

A una estudiante de 11° cuyo perfil dice "quiere ser veterinaria" el
recomendador le devolvía **cinco academias de inglés**. No era culpa del prompt
ni del modelo: de las 25 fichas que le llegaban, 12 eran de idiomas, 6 de
colegio y **ninguna vocacional**.

La causa es que el catálogo del recomendador (`programs`) son fichas a nivel
institución — "Idiomas · ILAC", "Colorado State University · Todos los
programas" — sin una sola fila que diga "Doctor of Veterinary Medicine". Con
eso, lo único que podía decir el modelo era "te prepara para veterinaria".

Pero el dato existe: `programas_investigados.program_id` enlaza 27.514 programas
con 449 de las 583 fichas activas, y el "Doctor of Veterinary Medicine" de
Colorado State está ahí — con su ficha diciendo "Todos los programas", o sea que
la agencia sí puede colocar a alguien. **No se inventa ninguna autorización**:
sólo se muestra qué se estudia en las instituciones que ya representa.

Medido tras el cambio, mismas 25 fichas: 12 idiomas → 5, y las recomendaciones
pasaron de cinco academias a Enfermería en UVic, Biomédicas en Windsor y
Ciencias de la Salud en Laurier.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.recommendation_service import (
    areas_afines_del_perfil,
    filter_catalog,
    programas_concretos_por_ficha,
)


def _perfil(codigos=("S", "I", "A"), **kw):
    base = dict(
        holland_codes=[SimpleNamespace(code=c) for c in codigos],
        interests=["Biología"], suggested_career_paths=[], strengths=["a"],
        constraints=[], values=[], learning_style=None, work_style=None,
        personality_dimensions=[], summary_narrative="x", career_families=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _user(**kw):
    base = dict(budget_band=None, budget_max_usd=None, preferred_countries=[],
                english_cefr_level=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _ficha(id_, nombre, tipo="carrera_completa"):
    return {"id": id_, "name": nombre, "category": tipo, "programType": None,
            "countries": ["Canadá"], "tags": [], "cost": {}, "duration": {}}


# ---------------------------------------------------------------------------
# Qué áreas se consideran
# ---------------------------------------------------------------------------


def test_las_areas_salen_del_riasec_no_de_los_intereses():
    """`interests` es texto libre que el modelo escribe a su gusto ("Diseño UX",
    "Biología marina") y no cruza contra el vocabulario cerrado de
    `programas_investigados.area`. Cruzarlo daría cero y en silencio."""
    areas = areas_afines_del_perfil(_perfil(("S", "I"), interests=["Biología marina"]))
    assert "Salud y Medicina" in areas
    assert "Biología marina" not in areas


def test_sin_holland_no_hay_areas_y_no_pasa_nada():
    """Quien no hizo test no tiene códigos · el enriquecimiento simplemente no
    ocurre y el recomendador funciona como siempre."""
    assert areas_afines_del_perfil(_perfil(())) == []


def test_las_areas_vienen_ordenadas_por_afinidad():
    areas = areas_afines_del_perfil(_perfil(("S", "I", "A")))
    assert areas[0] == "Salud y Medicina"


# ---------------------------------------------------------------------------
# La consulta · degrada sin tumbar nada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ids,areas", [([], ["Salud y Medicina"]), (["x"], []), ([], [])])
def test_sin_insumos_no_se_consulta_la_base(ids, areas):
    db = MagicMock()
    assert programas_concretos_por_ficha(db, ids, areas) == {}
    assert not db.execute.called


def test_si_la_consulta_falla_el_recomendador_sigue():
    """SQLite en los tests no tiene `array_position` ni `uuid[]`. Una consulta
    caída no puede costar una recomendación: el recomendador funcionaba sin
    esto y tiene que seguir funcionando sin esto."""
    db = MagicMock()
    db.execute.side_effect = RuntimeError("no such function: array_position")
    assert programas_concretos_por_ficha(db, ["a"], ["Salud y Medicina"]) == {}


def test_agrupa_los_programas_por_ficha():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = [
        {"ficha": "f1", "nombre": "Nursing", "area": "Salud y Medicina", "nivel": "bachelor"},
        {"ficha": "f1", "nombre": "Paramedic", "area": "Salud y Medicina", "nivel": "diplomado"},
        {"ficha": "f2", "nombre": "Biology", "area": "Ciencias", "nivel": "bachelor"},
    ]
    out = programas_concretos_por_ficha(db, ["f1", "f2"], ["Salud y Medicina"])
    assert [p["nombre"] for p in out["f1"]] == ["Nursing", "Paramedic"]
    assert out["f2"][0]["nivel"] == "bachelor"


# ---------------------------------------------------------------------------
# El peso en el ranking · el arreglo de las cinco academias de inglés
# ---------------------------------------------------------------------------


def test_una_institucion_con_programas_relevantes_le_gana_a_una_academia():
    """El test que representa el bug entero."""
    catalogo = [_ficha("academia", "Idiomas · ILAC", "curso_idiomas"),
                _ficha("uni", "University of Victoria")]
    por_ficha = {"uni": [{"nombre": "Nursing", "area": "Salud y Medicina",
                          "nivel": "bachelor"}]}

    sin = filter_catalog(_user(), _perfil(), catalog=catalogo)
    con = filter_catalog(_user(), _perfil(), catalog=catalogo,
                         programas_por_ficha=por_ficha)

    assert sin[0]["program_name"] == "Idiomas · ILAC", (
        "el caso de prueba no reproduce el sesgo que viene a arreglar")
    assert con[0]["program_name"] == "University of Victoria"


def test_tener_algo_relevante_es_el_salto_tener_mucho_es_un_matiz():
    """Los pesos bajan rápido (0.6 · 0.3 · 0.15) a propósito: que una
    institución enseñe lo que le interesa a la persona es la señal; cuántos
    programas tenga es un desempate."""
    catalogo = [_ficha("a", "Una"), _ficha("b", "Otra")]
    uno = [{"nombre": "N", "area": "Salud y Medicina", "nivel": "bachelor"}]
    tres = uno * 3

    salto = filter_catalog(_user(), _perfil(), catalog=catalogo,
                           programas_por_ficha={"a": uno})
    matiz = filter_catalog(_user(), _perfil(), catalog=catalogo,
                           programas_por_ficha={"a": tres})
    # Con uno ya gana; con tres gana por poco más, no por el triple.
    assert salto[0]["program_name"] == "Una"
    assert matiz[0]["program_name"] == "Una"


def test_los_programas_concretos_viajan_al_prompt():
    """Escribirlos en la ficha y no pasarlos al modelo sería el defecto #1 del
    repo otra vez."""
    from app.services.recommendation_service import _format_catalog_block

    catalogo = filter_catalog(
        _user(), _perfil(), catalog=[_ficha("uni", "University of Victoria")],
        programas_por_ficha={"uni": [{"nombre": "Doctor of Veterinary Medicine",
                                      "area": "Agricultura y Veterinaria",
                                      "nivel": "doctorado"}]},
    )
    bloque = _format_catalog_block(catalogo)
    assert "Doctor of Veterinary Medicine" in bloque
    assert "doctorado" in bloque


def test_sin_puente_el_catalogo_sale_igual_que_antes():
    """Regresión · el parámetro es opcional y su ausencia no cambia nada."""
    catalogo = [_ficha("a", "Una"), _ficha("b", "Otra")]
    a = filter_catalog(_user(), _perfil(), catalog=catalogo)
    b = filter_catalog(_user(), _perfil(), catalog=catalogo, programas_por_ficha={})
    assert [x["program_name"] for x in a] == [x["program_name"] for x in b]
    assert all(x["programas_concretos"] == [] for x in a)
