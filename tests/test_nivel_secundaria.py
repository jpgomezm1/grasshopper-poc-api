"""El catálogo no podía representar bachillerato · encontrado el 2026-08-08.

`VALID_PROGRAM_TYPES` tenía doce niveles, de `pregrado` a `bootcamp`, y **ninguno
para educación secundaria**. Lo destapó la primera pasada de extracción de
programas: de diez instituciones, tres quedaron mal representadas.

  - Un colegio de Pre-Prep a Year 12 aportó **2 filas**.
  - IMG Academy perdió su boarding school (grados 6-12) y el año Post-Graduate
    —justo el producto "Full Time" que la agencia vende— y quedaron sólo los
    campamentos.
  - Sir Wilfrid Laurier, cuyo `puede_vender` dice literalmente **"High School"**,
    se quedó sin su producto principal.

No es un caso de borde: **"High School" es la categoría más grande del catálogo
del cliente**, 647 de 2.511 fichas. El producto no podía representar la categoría
mayoritaria de la agencia.

`intercambio` no servía como sustituto: un semestre de intercambio y un
bachillerato completo de cinco años son productos distintos, con distinta
duración, precio y decisión familiar detrás.
"""
from __future__ import annotations

import pytest


def test_secundaria_es_un_nivel_valido():
    """El arreglo, en una línea."""
    from app.schemas.program import VALID_PROGRAM_TYPES

    assert "secundaria" in VALID_PROGRAM_TYPES


def test_el_schema_acepta_un_programa_de_secundaria():
    """Sin esto, cargar un colegio devolvía 422 y el dato se perdía."""
    from app.schemas.program import ProgramUpdate

    assert ProgramUpdate(type="secundaria").type == "secundaria"


def test_secundaria_tiene_categoria_en_las_DOS_copias_del_mapeo():
    """`_TYPE_TO_CATEGORY` está duplicado a propósito en `catalog_service` y en
    `ofertas.py` (un servicio no debe importar desde `app/api`), y el propio
    módulo advierte que hay que actualizar las dos. Este test es el que se da
    cuenta si alguien toca una sola."""
    from app.services.catalog_service import _TYPE_TO_CATEGORY as SERVICIO
    from app.api.v1.ofertas import _TYPE_TO_CATEGORY as API

    assert "secundaria" in SERVICIO
    assert "secundaria" in API
    assert SERVICIO["secundaria"] == API["secundaria"]


def test_el_mapeo_inverso_es_coherente():
    """`_CATEGORY_TO_TYPES` filtra el catálogo por categoría · si `secundaria`
    no está, filtrar por su categoría no devuelve los colegios."""
    from app.api.v1.ofertas import _TYPE_TO_CATEGORY, _CATEGORY_TO_TYPES

    categoria = _TYPE_TO_CATEGORY["secundaria"]
    assert "secundaria" in _CATEGORY_TO_TYPES[categoria]


def test_secundaria_tiene_etiqueta_legible():
    """`display_name_for_program` compone el nombre visible con esta etiqueta
    cuando la fila viene a nivel institución. Sin ella diría "Programa"."""
    from app.services.catalog_service import _TYPE_LABEL, display_name_for_program

    assert "secundaria" in _TYPE_LABEL
    compuesto = display_name_for_program(
        "Colegio X", "Colegio X", None, None, "secundaria"
    )
    assert _TYPE_LABEL["secundaria"] in compuesto


# ---------------------------------------------------------------------------
# El nivel académico · A8
# ---------------------------------------------------------------------------


def test_a_quien_esta_en_el_colegio_se_le_prefiere_secundaria():
    from app.services import academic_level as al

    assert al.evaluar("secundaria", "high_school_early") == al.PREFERIDO
    assert al.evaluar("secundaria", "En el colegio") == al.PREFERIDO


def test_a_quien_ya_paso_el_colegio_no_se_le_ofrece_bachillerato():
    """No es "imposible" —nadie se lo prohíbe— pero recomendarle un colegio a
    alguien que trabaja o está en la universidad es absurdo, así que no se
    pondera. Se deja NEUTRO y no IMPOSIBLE porque descartar sobre un `type`
    adivinado esconde oferta real (ver academic_level.py)."""
    from app.services import academic_level as al

    for etapa in ("university", "working", "recent_grad"):
        assert al.evaluar("secundaria", etapa) == al.NEUTRO


def test_secundaria_nunca_se_descarta_por_imposible():
    """Ninguna etapa lo bloquea · no requiere un título previo que falte."""
    from app.services import academic_level as al

    for etapa in ("high_school_early", "high_school", "university",
                  "working", "recent_grad", "career_change", None):
        assert al.evaluar("secundaria", etapa) != al.IMPOSIBLE


def test_terminando_el_colegio_sigue_prefiriendo_pregrado():
    """El arreglo no puede robarle la preferencia a quien está por graduarse:
    su siguiente paso es el pregrado, no otro bachillerato."""
    from app.services import academic_level as al

    assert al.evaluar("pregrado", "high_school") == al.PREFERIDO


# ---------------------------------------------------------------------------
# La normalización de la etapa tiene que ser idempotente · 2026-08-08
# ---------------------------------------------------------------------------


def test_normalizar_una_etapa_ya_normalizada_da_lo_mismo():
    """`normalizar_etapa` no reconocía los valores que ella misma devuelve.

    Y con etapa None, `academic_level` **no descarta nada**: a un estudiante de
    11° le volvían a salir maestrías y doctorados. Es el bug de A8 entrando por
    otra puerta, y no da ningún síntoma — sólo recomendaciones de más.
    """
    from app.services import academic_level as al

    for etapa in (al.EN_COLEGIO, al.TERMINANDO_COLEGIO, al.EN_UNIVERSIDAD,
                  al.EGRESADO, al.TRABAJANDO):
        assert al.normalizar_etapa(etapa) == etapa


def test_a_quien_termina_el_colegio_se_le_descarta_el_posgrado_por_las_dos_vias():
    """Da igual si la etapa llega en bruto o ya normalizada."""
    from app.services import academic_level as al

    for entrada in ("high_school", al.TERMINANDO_COLEGIO):
        fuera = al.niveles_fuera_de_alcance(entrada)
        assert "maestria" in fuera and "doctorado" in fuera, entrada
