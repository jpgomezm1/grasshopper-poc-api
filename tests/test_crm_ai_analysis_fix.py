"""Fase C · el análisis IA del CRM nunca corría (validación 2026-06-05).

`crm_lead_analysis.txt` contiene llaves literales (el JSON de ejemplo del
output y `{"high","medium","low"}`) y `_invoke_ai_analysis` renderizaba con
`.format()` → KeyError → el except devolvía SIEMPRE la plantilla
(`is_fallback=True`), silenciosamente. Ningún lead recibió análisis real.

Cubre:
  (a) El prompt REAL del repo se construye sin excepción, los placeholders
      quedan sustituidos y las llaves literales del ejemplo sobreviven.
  (b) Con respuesta válida del modelo, el resultado es is_fallback=False
      (el bug hacía imposible llegar aquí).
  (c) Respuesta con fences ```json → se parsea igual (parse_ai_json).
  (d) Respuesta no parseable → fallback de plantilla, sin reventar.

Sin DB: User/Program como objetos no persistidos · call_claude monkeypatched.
"""
from __future__ import annotations

import json

import pytest


def _user():
    from app.db.models import User

    return User(
        email="lead.crm@grasshopper.dev",
        hashed_password="x",
        name="Lead CRM",
        english_cefr_level="B2",
        budget_band="medio",
        budget_max_usd=15000,
        preferred_countries=["Canadá"],
    )


def _snapshot():
    from app.schemas.crm import CrmJourneySnapshot

    return CrmJourneySnapshot(
        onboarding_status="completed",
        journey_progress=0.8,
        onboarding_answers={"city": "Medellín", "country": "Colombia"},
    )


def _program():
    from app.db.models import Program

    return Program(
        program_id="P-CRM-1", name="Ingenieria de Datos", slug="p-crm-1",
        country="Canadá", city="Toronto", institution="Uni Toronto",
        type="pregrado", cost_total=12000, currency="USD",
        budget_tier="medium", active=True,
    )


_VALID_RESPONSE = json.dumps({
    "rationale": "El lead muestra un journey avanzado y presupuesto definido.",
    "program_matches": [
        {"program_id": "P-CRM-1", "name": "Ingenieria de Datos",
         "match_reason": "Presupuesto medio + Canadá + perfil analítico"}
    ],
    "next_actions": [
        {"priority": "high", "action": "Llamar al lead esta semana",
         "why": "Score alto sin contacto abierto"}
    ],
})


def _invoke(monkeypatch, ai_response):
    from app.services import crm_service

    prompts = []

    # Fase C2: el CRM ahora usa call_claude_with_meta → (texto, metadata).
    def _fake_call_claude(prompt, **kw):
        prompts.append(prompt)
        return ai_response, {"model": "claude-sonnet-4-6", "latency_ms": 10}

    monkeypatch.setattr(crm_service, "call_claude_with_meta", _fake_call_claude)

    result = crm_service._invoke_ai_analysis(
        user=_user(), score=75, signals=[], snapshot=_snapshot(),
        catalog=[_program()],
    )
    return result, prompts


def test_prompt_builds_with_real_template_and_ai_runs(monkeypatch):
    result, prompts = _invoke(monkeypatch, _VALID_RESPONSE)

    # (a) la IA SÍ fue llamada (con .format() nunca se llegaba acá)
    assert len(prompts) == 1
    prompt = prompts[0]
    # placeholders sustituidos
    assert "lead.crm@grasshopper.dev" in prompt
    assert "{email}" not in prompt
    assert "{catalog_block}" not in prompt
    assert "{narrative_block}" not in prompt
    # las llaves literales del template sobreviven intactas
    assert '"rationale": "string' in prompt
    assert '{"high","medium","low"}' in prompt

    # (b) resultado real, no plantilla
    assert result.is_fallback is False
    assert result.rationale.startswith("El lead muestra")
    assert result.program_matches[0].program_id == "P-CRM-1"
    assert result.program_matches[0].institution == "Uni Toronto"
    assert result.next_actions[0].priority == "high"


def test_fenced_json_response_still_parses(monkeypatch):
    fenced = f"```json\n{_VALID_RESPONSE}\n```"
    result, _ = _invoke(monkeypatch, fenced)
    assert result.is_fallback is False
    assert result.program_matches[0].program_id == "P-CRM-1"


def test_unparseable_response_falls_back(monkeypatch):
    result, prompts = _invoke(monkeypatch, "lo siento, no puedo generar JSON")
    assert len(prompts) == 1
    assert result.is_fallback is True
    assert result.next_actions  # la plantilla trae acciones mínimas


def test_non_object_json_falls_back(monkeypatch):
    result, _ = _invoke(monkeypatch, json.dumps(["una", "lista"]))
    assert result.is_fallback is True


def test_tracking_m001_se_registra_cuando_hay_db(monkeypatch):
    """Fase C2: con db, el análisis CRM registra la llamada en M-001
    (mismo criterio que el recomendador: también los intentos fallidos)."""
    from app.services import crm_service

    registros = []
    monkeypatch.setattr(
        crm_service, "record_ai_usage", lambda db, **kw: registros.append(kw)
    )
    monkeypatch.setattr(
        crm_service,
        "call_claude_with_meta",
        lambda prompt, **kw: (
            _VALID_RESPONSE,
            {"model": "claude-sonnet-4-6", "tokens_input": 100, "tokens_output": 50, "latency_ms": 9},
        ),
    )

    result = crm_service._invoke_ai_analysis(
        user=_user(), score=75, signals=[], snapshot=_snapshot(),
        catalog=[_program()], db=object(),
    )

    assert result.is_fallback is False
    assert len(registros) == 1
    assert registros[0]["feature"] == "crm_lead_analysis"
    assert registros[0]["model"] == "claude-sonnet-4-6"
    assert registros[0]["tokens_input"] == 100
    assert registros[0]["tokens_output"] == 50
