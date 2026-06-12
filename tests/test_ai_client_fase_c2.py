"""Fase C2 · robustez transversal de call_claude (el path que usan las 8
funciones de IA fuera del chat).

Contratos nuevos:
1. stop_reason == "max_tokens" → None (JSON truncado NO se entrega al caller;
   sus fallbacks deterministas se activan igual que en cualquier fallo).
2. El texto se extrae del PRIMER bloque con .text, no de content[0] (puede
   haber bloques no-texto al inicio según modelo/configuración).
3. Sin ningún bloque de texto → None.
4. Errores 4xx deterministas (bad_request/auth) NO se reintentan: el mismo
   payload nunca va a funcionar.
5. Errores transitorios (timeout/rate_limit/server) SÍ agotan los reintentos.

Mismo patrón de fakes que tests/test_ai_client_legacy_timeout.py.
"""
from __future__ import annotations

import httpx
from types import SimpleNamespace

import anthropic

from app.core import ai_client


class _FakeMessages:
    def __init__(self, outcome):
        self._outcome = outcome
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeClient:
    def __init__(self, outcome):
        self.messages = _FakeMessages(outcome)

    def with_options(self, **kwargs):
        return self


def _patch(monkeypatch, outcome):
    client = _FakeClient(outcome)
    monkeypatch.setattr(ai_client, "get_client", lambda: client)
    return client


def _bad_request_error():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(400, request=request, json={"error": {"message": "bad"}})
    return anthropic.BadRequestError(
        "bad request", response=response, body=None
    )


def test_truncado_por_max_tokens_devuelve_none(monkeypatch):
    resp = SimpleNamespace(
        content=[SimpleNamespace(text='{"items": [{"name": "Progr')],
        stop_reason="max_tokens",
    )
    _patch(monkeypatch, resp)

    assert ai_client.call_claude("prompt", session_id="s1") is None


def test_extrae_texto_aunque_el_primer_bloque_no_sea_texto(monkeypatch):
    bloque_sin_texto = SimpleNamespace(type="thinking")  # sin atributo .text
    resp = SimpleNamespace(
        content=[bloque_sin_texto, SimpleNamespace(text="respuesta real")],
        stop_reason="end_turn",
    )
    _patch(monkeypatch, resp)

    assert ai_client.call_claude("prompt", session_id="s1") == "respuesta real"


def test_sin_bloques_de_texto_devuelve_none(monkeypatch):
    resp = SimpleNamespace(content=[SimpleNamespace(type="tool_use")], stop_reason="end_turn")
    _patch(monkeypatch, resp)

    assert ai_client.call_claude("prompt", session_id="s1") is None


def test_bad_request_no_se_reintenta(monkeypatch):
    client = _patch(monkeypatch, _bad_request_error())

    out = ai_client.call_claude("prompt", session_id="s1", max_retries=2)

    assert out is None
    assert client.messages.calls == 1  # corta de una: 4xx es determinista


def test_error_transitorio_si_agota_reintentos(monkeypatch):
    client = _patch(monkeypatch, RuntimeError("conexion caida"))

    out = ai_client.call_claude("prompt", session_id="s1", max_retries=2)

    assert out is None
    assert client.messages.calls == 3  # intento inicial + 2 reintentos


def test_modelo_por_defecto_es_sonnet_4_6():
    """Fase C2: upgrade de claude-sonnet-4-5 a claude-sonnet-4-6 (mismo
    precio, mejor calidad; sin prefills en el backend = sin bloqueantes).

    Se valida el DEFAULT del campo (no Settings(), que resuelve .env y en
    local/Heroku puede estar pineado a otro valor vía AI_MODEL).
    """
    from app.config import Settings

    assert Settings.model_fields["ai_model"].default == "claude-sonnet-4-6"
