"""F-003 · becas LatAm en el catálogo real (/ofertas) · 2026-06-04.

Valida la derivación del flag + que `/ofertas` lo expone en el contrato FE.
No toca DB: usa un Program falso (SimpleNamespace) con los campos que lee
`_program_to_oferta`.
"""
from types import SimpleNamespace as NS

from app.api.v1.ofertas import _has_latam_scholarship, _program_to_oferta


def _fake_program(**over):
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        program_id="UNI-001",
        slug="uni-toronto",
        name="University of Toronto",
        institution="University of Toronto",
        institution_logo_url=None,
        country="Canadá",
        city="Toronto",
        type="carrera",
        description_long=None,
        highlights=[],
        tags=[],
        images=[],
        admission_dates=[],
        duration_months=None,
        cost_total=None,
        currency="USD",
        budget_tier=None,
        language_requirement=None,
        language_requirement_detail=None,
        active=True,
        scholarships=None,
        scholarships_for_latam=None,
    )
    base.update(over)
    return NS(**base)


def test_has_latam_scholarship_from_boolean_flag():
    assert _has_latam_scholarship(_fake_program(scholarships_for_latam=True)) is True
    assert _has_latam_scholarship(_fake_program(scholarships_for_latam=False)) is False
    assert _has_latam_scholarship(_fake_program(scholarships_for_latam=None)) is False


def test_has_latam_scholarship_derived_from_json():
    # Se enciende si una entrada del JSON está marcada elegible para LatAm
    p = _fake_program(scholarships=[{"name": "Beca X", "latam_eligible": True}])
    assert _has_latam_scholarship(p) is True
    p2 = _fake_program(scholarships=[{"name": "Beca Y", "for_latam": True}])
    assert _has_latam_scholarship(p2) is True
    # JSON sin marca LatAm → False
    p3 = _fake_program(scholarships=[{"name": "Beca Z"}])
    assert _has_latam_scholarship(p3) is False


def test_has_latam_scholarship_malformed_json_is_safe():
    """Hardening F-003: el JSON viene de import/curación externa → formas raras
    no deben encender la beca por error ni reventar."""
    # `scholarships` no es lista (string / dict / None) → False, sin crash
    assert _has_latam_scholarship(_fake_program(scholarships="texto")) is False
    assert _has_latam_scholarship(_fake_program(scholarships={"latam_eligible": True})) is False
    assert _has_latam_scholarship(_fake_program(scholarships=None)) is False
    # entradas no-dict dentro de la lista → ignoradas
    assert _has_latam_scholarship(_fake_program(scholarships=[123, "x", None])) is False
    # truthiness laxa: el string "false"/"no"/0 NO debe encender la beca
    assert _has_latam_scholarship(_fake_program(scholarships=[{"latam_eligible": "false"}])) is False
    assert _has_latam_scholarship(_fake_program(scholarships=[{"for_latam": "no"}])) is False
    assert _has_latam_scholarship(_fake_program(scholarships=[{"latam_eligible": 0}])) is False
    # strings/números que SÍ significan verdadero
    assert _has_latam_scholarship(_fake_program(scholarships=[{"latam_eligible": "true"}])) is True
    assert _has_latam_scholarship(_fake_program(scholarships=[{"for_latam": 1}])) is True
    assert _has_latam_scholarship(_fake_program(scholarships=[{"latam_eligible": "sí"}])) is True


def test_program_to_oferta_exposes_scholarships_for_latam():
    o_true = _program_to_oferta(_fake_program(scholarships_for_latam=True))
    assert o_true["scholarshipsForLatam"] is True
    o_false = _program_to_oferta(_fake_program())
    assert o_false["scholarshipsForLatam"] is False
    # el campo SIEMPRE está presente en el contrato (no opcional)
    assert "scholarshipsForLatam" in o_false
