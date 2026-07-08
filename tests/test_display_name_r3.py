"""R3-01 (feedback clienta 2026-07-08) · "la IA muestra universidades, no
programas".

Causa: el catálogo real (Excel de junio) viene a nivel INSTITUCIÓN —
2.511/2.562 filas con name == institution y area NULL. Mitigación honesta
hasta que llegue el Excel a nivel programa: componer el nombre visible con
subject/área/tipo reales de la fila (nunca inventar programas).
"""
from __future__ import annotations

from app.services.catalog_service import display_name_for_program


def test_fila_institucion_con_subject_compone_oferta():
    assert (
        display_name_for_program(
            "Brisbane School of Beauty",
            "Brisbane School of Beauty",
            subject="Vocacionales (Cert, Dip, Adv Dip)",
            area=None,
            program_type="curso_corto",
        )
        == "Vocacionales (Cert, Dip, Adv Dip) · Brisbane School of Beauty"
    )


def test_fila_institucion_sin_subject_usa_tipo():
    assert (
        display_name_for_program("YMCA", "YMCA", None, None, "vacacional")
        == "Programa vacacional · YMCA"
    )


def test_fila_institucion_prefiere_area_sobre_subject():
    assert (
        display_name_for_program("U X", "U X", "Cat gruesa", "Ingeniería", "pregrado")
        == "Ingeniería · U X"
    )


def test_programa_real_no_se_toca():
    assert (
        display_name_for_program(
            "Administración de Empresas", "CESA", "Negocios", None, "pregrado"
        )
        == "Administración de Empresas"
    )


def test_match_institucion_es_case_insensitive():
    assert display_name_for_program("ymca", "YMCA", None, None, "vacacional").startswith(
        "Programa vacacional"
    )


def test_tipo_desconocido_cae_a_programa():
    assert display_name_for_program("X", "X", None, None, "rarísimo") == "Programa · X"


def test_none_safety():
    # fila degenerada: sin nombre ni institución no explota
    assert display_name_for_program(None, None, None, None, None) == "Programa · Programa"
