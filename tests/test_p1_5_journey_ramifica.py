"""P1-5 · El Journey salta los pasos que NO APLICAN a la persona · Sprint 3.

Reproducido y capturado en el QA del 28-07: un estudiante responde en el onboarding
"¿Dónde te gustaría vivir tu experiencia de estudio?" -> "En mi país", y minutos
después el Journey le pregunta "Cuando piensas en irte, ¿qué pesa más?".

La causa: `get_next_step` solo sabía saltar por UNA razón —"ya está respondido"—.
Faltaba la otra: "no aplica a esta persona".

Nota de diseño: se resolvió con una condición REAL y no sembrando una respuesta
inventada en `geoPreference`. Registrar que alguien contestó algo que nunca contestó
es el tipo de dato falso que este sprint viene quitando (ver P1-19).
"""
from __future__ import annotations

from app.core.state_machine import get_next_step, get_step

QUEDARSE = {"international_interest": "intl_no"}
IRSE = {"international_interest": "intl_yes"}
TAL_VEZ = {"international_interest": "intl_maybe"}


def test_a_quien_se_queda_no_se_le_pregunta_cuando_piensa_irse():
    """El bug exacto que vio la clienta."""
    assert get_next_step("languageLevel", {}, QUEDARSE) == "synthesis"


def test_a_quien_si_le_interesa_el_exterior_se_le_sigue_preguntando():
    """La condición no puede apagar el paso para todo el mundo."""
    assert get_next_step("languageLevel", {}, IRSE) == "geoPreference"


def test_quien_duda_tambien_ve_la_pregunta():
    """'Tal vez' no es 'no': ante la duda se muestra el paso."""
    assert get_next_step("languageLevel", {}, TAL_VEZ) == "geoPreference"


def test_sin_onboarding_se_comporta_como_antes():
    """Sesiones anónimas o sin onboarding: comportamiento original intacto."""
    assert get_next_step("languageLevel") == "geoPreference"
    assert get_next_step("languageLevel", {}) == "geoPreference"
    assert get_next_step("languageLevel", {}, None) == "geoPreference"


def test_el_paso_conserva_su_texto_y_su_destino():
    """Saltarlo no es borrarlo: sigue existiendo para quien sí le aplica."""
    paso = get_step("geoPreference")
    assert paso is not None
    assert paso.question == "Cuando piensas en irte, ¿qué pesa más?"
    assert paso.next_step == "synthesis"
    assert paso.skip_if is not None


def test_una_condicion_rota_no_deja_al_usuario_atascado():
    """Si `skip_if` lanza, se muestra el paso en vez de romper el journey."""
    paso = get_step("geoPreference")
    original = paso.skip_if
    paso.skip_if = lambda ctx: 1 / 0  # noqa: E731
    try:
        assert get_next_step("languageLevel", {}, QUEDARSE) == "geoPreference"
    finally:
        paso.skip_if = original


def test_se_combinan_las_dos_razones_de_salto():
    """Ya-respondido y no-aplica tienen que poder encadenarse."""
    # geoPreference no aplica Y synthesis no tiene save_to → cae en synthesis.
    assert get_next_step("languageLevel", {"geoPreference": "El país"}, QUEDARSE) == "synthesis"
