"""P1-4 / S9 · No volver a preguntar lo que el onboarding ya preguntó.

Es la queja que más veces repitieron las DOS personas que probaron el producto:

    Sandra   · "esas preguntas siento que me está volviendo a preguntar"
    Verónica · "me hizo 13 preguntas y me va a volver a decir que comencemos"

Hasta ahora el seed cubría **2 de ~11 campos** (`lifeStage`, `timeHorizon`), así que
el journey seguía repreguntando objetivo y presupuesto, arrancaba con una pantalla de
bienvenida a alguien que acababa de responder 13 preguntas, y su primer paso
—"¿Qué te hizo llegar hasta aquí hoy?"— es el mismo "¿Qué quieres resolver con esta
orientación?" del onboarding con otras palabras.

La otra mitad de estos tests es igual de importante: **qué NO se siembra**. Dar por
respondido algo que la persona no respondió es peor que repreguntar — registra una
respuesta falsa y encima se la muestra de vuelta en la síntesis.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.state_machine import get_next_step, get_step
from app.services.journey_service import (
    seed_answers_from_onboarding,
    seed_session_from_onboarding,
)


# ---------------------------------------------------------------------------
# Lo que SÍ se siembra
# ---------------------------------------------------------------------------


def test_el_objetivo_no_se_vuelve_a_preguntar():
    seeded = seed_answers_from_onboarding(
        {"main_goal": ["learn_language", "emigrate"]}
    )
    assert seeded["interestType"] == ["Mejorar un idioma", "Vivir en otro país"]


def test_se_conserva_el_orden_en_que_las_eligio():
    seeded = seed_answers_from_onboarding({"main_goal": ["emigrate", "work"]})
    assert seeded["interestType"] == ["Vivir en otro país", "Construir una carrera"]


def test_no_se_repiten_intereses():
    """Dos metas distintas pueden mapear al mismo interés."""
    seeded = seed_answers_from_onboarding({"main_goal": ["explore", "explore"]})
    assert seeded["interestType"] == ["No estoy seguro aún"]


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("under_5k", "Bajo"),
        ("5k_15k", "Medio"),
        ("15k_30k", "Flexible"),
        ("over_30k", "Flexible"),
        ("unknown", "Prefiero no definirlo ahora"),
    ],
)
def test_el_presupuesto_no_se_vuelve_a_preguntar(valor, esperado):
    assert seed_answers_from_onboarding({"budget": valor})["budgetBand"] == esperado


def test_los_valores_sembrados_son_opciones_REALES_del_journey():
    """Si se siembra un texto que no está entre las opciones del paso, la pantalla
    muestra una selección que no existe. Este test ata el mapeo al state machine."""
    seeded = seed_answers_from_onboarding(
        {
            "life_stage": "high_school",
            "timeline": "1_year",
            "main_goal": ["learn_language", "work", "emigrate", "explore"],
            "budget": "5k_15k",
        }
    )
    for clave, valor in seeded.items():
        paso = next(
            (s for s in __import__(
                "app.core.state_machine", fromlist=["JOURNEY_STEPS"]
            ).JOURNEY_STEPS if s.save_to == clave),
            None,
        )
        assert paso is not None, f"no existe un paso que guarde en '{clave}'"
        opciones = [
            o.get("value") if isinstance(o, dict) else o for o in (paso.options or [])
        ]
        if not opciones:
            continue
        valores = valor if isinstance(valor, list) else [valor]
        for v in valores:
            assert v in opciones, f"'{v}' no es una opción de '{clave}': {opciones}"


# ---------------------------------------------------------------------------
# Lo que NO se siembra · registrar una respuesta falsa es peor que repreguntar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("meta", ["discover", "study"])
def test_las_metas_sin_equivalente_limpio_no_se_siembran(meta):
    """"Entenderme mejor" y "definir qué estudiar" no tienen equivalente entre las
    opciones del journey. Forzarlas a "Construir una carrera" sería registrar que la
    persona eligió algo que no eligió."""
    assert "interestType" not in seed_answers_from_onboarding({"main_goal": [meta]})


def test_si_una_meta_no_mapea_no_se_siembra_ninguna():
    """Sembrar solo la mitad dejaría el paso por respondido con parte de lo que dijo,
    que es peor: pierde información sin avisar."""
    seeded = seed_answers_from_onboarding(
        {"main_goal": ["study", "learn_language"]}
    )
    assert "interestType" not in seeded


def test_un_presupuesto_desconocido_no_inventa_banda():
    assert "budgetBand" not in seed_answers_from_onboarding({"budget": "???"})


def test_sin_onboarding_no_se_siembra_nada():
    assert seed_answers_from_onboarding(None) == {}
    assert seed_answers_from_onboarding({}) == {}


def test_no_se_siembra_whyHere():
    """`whyHere` es texto libre y `main_goal` son opciones: inventar la frase sería
    falsear lo que dijo. Se salta la pregunta, no se rellena."""
    seeded = seed_answers_from_onboarding({"main_goal": ["work"]})
    assert "whyHere" not in seeded


# ---------------------------------------------------------------------------
# El paso que duplica `main_goal` se salta, no se rellena
# ---------------------------------------------------------------------------


def test_whyHere_se_salta_si_el_onboarding_pregunto_el_objetivo():
    assert (
        get_next_step("welcome", {}, {"main_goal": ["work"]}) != "whyHere"
    )


def test_whyHere_se_pregunta_si_no_hubo_onboarding():
    """Quien entra sin onboarding no perdió nada: se le pregunta."""
    assert get_next_step("welcome", {}, {}) == "whyHere"
    assert get_next_step("welcome") == "whyHere"


def test_una_condicion_rota_muestra_el_paso_en_vez_de_atascar():
    """El `skip_if` corre sobre datos de usuario; si revienta, el journey no puede
    quedarse mudo."""
    paso = get_step("whyHere")
    assert paso.skip_if is not None
    # `onboarding` no es un dict → la condición falla por dentro.
    assert get_next_step("welcome", {}, {"main_goal": None}) == "whyHere"


# ---------------------------------------------------------------------------
# La sesión no arranca dándole la bienvenida a quien ya respondió 13 preguntas
# ---------------------------------------------------------------------------


def _sesion(current_step="welcome", answers=None, completed=None):
    return SimpleNamespace(
        current_step=current_step,
        current_stage=None,
        answers=answers or {},
        completed_steps=completed or [],
    )


def test_no_se_le_da_la_bienvenida_a_quien_viene_del_onboarding():
    s = _sesion()
    onboarding = {"life_stage": "high_school", "main_goal": ["work"]}
    assert seed_session_from_onboarding(s, onboarding) is True
    assert s.current_step != "welcome"
    # Y tampoco cae en la pregunta que duplica `main_goal`.
    assert s.current_step != "whyHere"


def test_la_sesion_anonima_conserva_su_bienvenida():
    """Sin onboarding no hay nada que saltarse: la persona no ha respondido nada."""
    s = _sesion()
    assert seed_session_from_onboarding(s, None) is False
    assert s.current_step == "welcome"


def test_no_pisa_lo_que_el_journey_ya_respondio():
    """Re-hacer el onboarding con el journey a medio camino no puede borrar lo que
    la persona ya contestó ahí."""
    s = _sesion(
        current_step="clarityLevel",
        answers={"interestType": ["Construir una carrera"]},
        completed=["interestType"],
    )
    seed_session_from_onboarding(s, {"main_goal": ["emigrate"], "budget": "under_5k"})
    assert s.answers["interestType"] == ["Construir una carrera"]
    # y lo que faltaba sí entra
    assert s.answers["budgetBand"] == "Bajo"


def test_avanza_si_estaba_parada_justo_en_un_paso_recien_sembrado():
    s = _sesion(current_step="budgetBand")
    seed_session_from_onboarding(s, {"budget": "5k_15k"})
    assert s.answers["budgetBand"] == "Medio"
    assert s.current_step != "budgetBand"


def test_los_pasos_sembrados_quedan_como_completados():
    s = _sesion()
    seed_session_from_onboarding(
        s, {"life_stage": "working", "budget": "unknown", "main_goal": ["explore"]}
    )
    for clave in ("lifeStage", "budgetBand", "interestType"):
        assert clave in s.completed_steps
