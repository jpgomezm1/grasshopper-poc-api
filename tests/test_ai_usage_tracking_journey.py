"""Tracking M-001 en el journey (ai_service.py).

Hasta ahora las 4 funciones IA del journey (reflection, synthesis, routes,
advisor_brief) llamaban a `call_claude()` —que solo devuelve texto— así que
NUNCA registraban en `ai_usage_log`: el panel de costos subestimaba el gasto
real del flujo de descubrimiento. Fase C: migradas a `call_claude_with_meta`
+ `record_ai_usage`.

Decisiones cubiertas:
  (a) cada función registra su feature ("journey_reflection", etc.) con los
      tokens/latencia reales y el user_id del dueño del journey.
  (b) sin `db` (función llamada suelta) NO registra — best-effort.
  (c) si la IA falla, se usa el fallback determinista y NO se registra
      (los costos solo cuentan llamadas exitosas; el fallo ya va a logs en
      call_claude_with_meta).

Spy de record_ai_usage al estilo de tests/test_ai_usage_tracking_recommender.py.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.services import ai_service as svc


_META_OK = {
    "model": "claude-sonnet-4-6",
    "tokens_input": 800,
    "tokens_output": 220,
    "latency_ms": 1300,
}


@pytest.fixture()
def spy(monkeypatch):
    """Captura las llamadas a record_ai_usage hechas desde ai_service."""
    calls: list[dict] = []
    monkeypatch.setattr(svc, "record_ai_usage", lambda db, **kw: calls.append(kw))
    return calls


def _mock_ai(monkeypatch, text):
    monkeypatch.setattr(
        svc, "call_claude_with_meta",
        lambda prompt, **kw: (text, dict(_META_OK)),
    )


def _synthesis_json() -> str:
    return json.dumps({
        "text": "Veo a alguien explorando con curiosidad.",
        "chips": [{"label": "Etapa", "value": "Explorando"}],
        "key_motivations": ["Crecimiento"],
        "constraints": [],
    })


def _routes_json() -> str:
    return json.dumps({
        "routes": [{
            "key": "LANGUAGE_PLUS_EXPERIENCE",
            "name": "Ruta Idioma + Experiencia",
            "why": "Mejora un idioma viviendo algo nuevo.",
            "what_it_looks_like": "Curso intensivo + cultura.",
            "next_step": "Definir duración.",
        }]
    })


def _advisor_json() -> str:
    return json.dumps({
        "profile_summary": "Estudiante en exploración con horizonte flexible.",
        "primary_route": "Ruta Idioma + Experiencia",
        "key_considerations": ["Etapa: explorando", "Horizonte: flexible"],
        "emotional_state": "Claridad media",
    })


# ---------------------------------------------------------------------------
# (a) cada función registra con su feature
# ---------------------------------------------------------------------------

def test_reflection_records_usage(monkeypatch, spy):
    _mock_ai(monkeypatch, "Tiene sentido, gracias por contarlo.")
    uid = uuid4()

    out = svc.generate_empathy_reflection("quiero claridad", "sess-1", db=object(), user_id=uid)

    assert out.text
    assert len(spy) == 1
    assert spy[0]["feature"] == "journey_reflection"
    assert spy[0]["provider"] == "anthropic"
    assert spy[0]["model"] == "claude-sonnet-4-6"
    assert spy[0]["tokens_input"] == 800
    assert spy[0]["tokens_output"] == 220
    assert spy[0]["latency_ms"] == 1300
    assert spy[0]["user_id"] == uid


def test_synthesis_records_usage(monkeypatch, spy):
    _mock_ai(monkeypatch, _synthesis_json())
    uid = uuid4()

    out = svc.generate_synthesis({"lifeStage": "En la universidad"}, "sess-2", db=object(), user_id=uid)

    assert out.text == "Veo a alguien explorando con curiosidad."
    assert len(spy) == 1
    assert spy[0]["feature"] == "journey_synthesis"
    assert spy[0]["user_id"] == uid


def test_routes_records_usage(monkeypatch, spy):
    _mock_ai(monkeypatch, _routes_json())
    uid = uuid4()

    out = svc.generate_routes({"lifeStage": "Ya trabajando"}, "sess-3", db=object(), user_id=uid)

    assert len(out.routes) == 1
    assert len(spy) == 1
    assert spy[0]["feature"] == "journey_routes"


def test_advisor_brief_records_usage(monkeypatch, spy):
    _mock_ai(monkeypatch, _advisor_json())
    uid = uuid4()

    out = svc.generate_advisor_brief(
        {"lifeStage": "En transición"}, [{"name": "Ruta X", "is_primary": True}],
        "sess-4", db=object(), user_id=uid,
    )

    assert out.profile_summary
    assert len(spy) == 1
    assert spy[0]["feature"] == "journey_advisor_brief"


# ---------------------------------------------------------------------------
# (b) sin db NO registra · (c) fallo de IA NO registra
# ---------------------------------------------------------------------------

def test_no_db_does_not_record(monkeypatch, spy):
    """Llamada suelta sin db (p.ej. tests legados): best-effort, cero filas."""
    _mock_ai(monkeypatch, _synthesis_json())

    out = svc.generate_synthesis({"lifeStage": "En la universidad"}, "sess-5")

    assert out.text == "Veo a alguien explorando con curiosidad."
    assert spy == []


def test_ai_failure_uses_fallback_and_does_not_record(monkeypatch, spy):
    """IA devuelve None → fallback determinista, sin fila de costo."""
    monkeypatch.setattr(
        svc, "call_claude_with_meta",
        lambda prompt, **kw: (None, {"model": "claude-sonnet-4-6", "error_kind": "timeout"}),
    )
    uid = uuid4()

    out = svc.generate_routes({"lifeStage": "Ya trabajando"}, "sess-6", db=object(), user_id=uid)

    # cae a FALLBACK_ROUTES (3 rutas estáticas)
    assert len(out.routes) == 3
    assert spy == []
