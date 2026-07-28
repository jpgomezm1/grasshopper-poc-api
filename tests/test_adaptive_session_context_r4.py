"""R4 · IA adaptativa con la sesión (feedback clienta 2026-07-08).

"El mismo set de preguntas una y otra vez… como que no estuviera inteligente":
los pasos IA del Journey ahora reciben lo que la persona YA contó en el
onboarding, y el chat de Hop recibe el estado del journey — para referenciar
lo ya dicho en vez de sonar genéricos.
"""
from __future__ import annotations

import pytest

from app.services import ai_service
from app.services.ai_service import format_onboarding_context


ONBOARDING = {
    "voice_passion": "Me apasiona la tecnología y ayudar a otros",
    "voice_hobbies": "Leer y programar",
    "voice_career": "Trabajando en software",
    "voice_strengths": "Lógica y comunicación",
    "voice_concerns": "No elegir bien mi camino",
    "main_goal": ["discover"],
    "international_interest": "intl_no",
}


# ── format_onboarding_context ───────────────────────────────────────────────

def test_contexto_completo_incluye_todo():
    txt = format_onboarding_context(ONBOARDING)
    assert "Me apasiona la tecnología" in txt
    assert "Leer y programar" in txt
    assert "Descubrir sobre mí" in txt  # label mapeado de main_goal
    assert "quiere enfocarse localmente" in txt  # intl_no mapeado


def test_contexto_vacio_es_tolerante():
    assert format_onboarding_context(None) == "(sin datos del onboarding)"
    assert format_onboarding_context({}) == "(sin datos del onboarding)"
    assert format_onboarding_context({"otra_cosa": "x"}) == "(sin datos del onboarding)"


def test_contexto_sanea_llaves_para_str_format():
    txt = format_onboarding_context({"voice_passion": "me gusta {python} y {js}"})
    assert "{" not in txt and "}" not in txt
    assert "(python)" in txt


# ── los pasos IA del journey inyectan el contexto en el prompt ─────────────

def _capture_prompt(monkeypatch):
    captured = {}

    def _fake_call(prompt, **kwargs):
        captured["prompt"] = prompt
        return None, {}  # sin respuesta → cae al fallback, no importa

    monkeypatch.setattr(ai_service, "call_claude_with_meta", _fake_call)
    return captured


def test_reflection_recibe_onboarding(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    ai_service.generate_empathy_reflection(
        "quiero claridad", "sess-1", onboarding=ONBOARDING
    )
    assert "Me apasiona la tecnología" in captured["prompt"]
    assert "CONTEXTO PREVIO DEL ONBOARDING" in captured["prompt"]


def test_synthesis_recibe_onboarding(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    ai_service.generate_synthesis({"lifeStage": "En la universidad"}, "sess-1", onboarding=ONBOARDING)
    assert "Me apasiona la tecnología" in captured["prompt"]


def test_routes_recibe_onboarding(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    ai_service.generate_routes({"lifeStage": "En la universidad"}, "sess-1", onboarding=ONBOARDING)
    assert "Me apasiona la tecnología" in captured["prompt"]


def test_sin_onboarding_no_rompe(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    out = ai_service.generate_empathy_reflection("hola", "sess-1")
    assert out.text  # fallback OK
    assert "(sin datos del onboarding)" in captured["prompt"]


# ── el chat de Hop conoce la sesión ─────────────────────────────────────────

def test_hop_chat_prompt_tiene_placeholder_journey():
    from app.core.ai_client import load_prompt

    text = load_prompt("hop_chat")
    assert "{journey_block}" in text
    assert "ADAPTACIÓN A LA SESIÓN" in text
    assert "NUNCA le vuelvas a preguntar algo que ya está en el contexto" in text


def test_build_journey_block_sin_sesion():
    """Usuario sin journey → bloque honesto, sin explotar."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.hop_chat_service import _build_journey_block

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    user = SimpleNamespace(id="u1", onboarding_answers=ONBOARDING)
    block = _build_journey_block(db, user)
    assert "aún no lo ha empezado" in block
    assert "Me apasiona la tecnología" in block


def test_build_journey_block_con_sesion():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.hop_chat_service import _build_journey_block

    session = SimpleNamespace(
        current_stage=SimpleNamespace(value="exploracion"),
        is_completed=False,
        answers={
            "lifeStage": "En la universidad",
            "interestType": ["Construir una carrera"],
            "dontWant": "algo muy teórico",
        },
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = session
    user = SimpleNamespace(id="u1", onboarding_answers=None)
    block = _build_journey_block(db, user)
    assert "en curso (etapa: exploracion)" in block
    assert "En la universidad" in block
    assert "intereses: Construir una carrera" in block


# ---------------------------------------------------------------------------
# P0-11b · Modalidad (R6-ON-5) — Sprint 3
#
# La pregunta de modalidad se agregó al onboarding en el mismo commit que la
# conecta al contexto de IA, a propósito: capturar una respuesta que después
# nadie lee es exactamente la queja de la clienta ("pareciera que nada de eso
# lo usara"). Este test amarra las dos puntas.
# ---------------------------------------------------------------------------


def test_modalidad_del_onboarding_llega_al_contexto_de_ia():
    from app.services.ai_service import format_onboarding_context

    for valor, esperado in [
        ("in_person", "Presencial"),
        ("hybrid", "Híbrido"),
        ("online", "Virtual"),
        ("no_preference", "Sin preferencia"),
    ]:
        bloque = format_onboarding_context({"modality": valor})
        assert "Modalidad de estudio que prefiere" in bloque
        assert esperado in bloque


def test_modalidad_desconocida_no_ensucia_el_contexto():
    """Un value que no esté en el mapa se ignora, no se filtra crudo al prompt."""
    from app.services.ai_service import format_onboarding_context

    assert format_onboarding_context({"modality": "valor_inventado"}) == "(sin datos del onboarding)"


def test_las_etiquetas_de_modalidad_cubren_las_opciones_del_front():
    """Contrato con OnboardingPage.tsx · step 'modality'.

    Si el front agrega una opción y no se mapea aquí, la respuesta se pierde en
    silencio: el usuario contesta y la IA nunca se entera.
    """
    from app.services.ai_service import _MODALITY_LABELS

    assert set(_MODALITY_LABELS) == {"in_person", "hybrid", "online", "no_preference"}
