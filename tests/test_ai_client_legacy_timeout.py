"""call_claude (path legado) debe llevar timeout explícito.

Fix hardening: call_claude_chat ya configuraba with_options(timeout=45,
max_retries=2), pero el call_claude legado (reflection/synthesis/routes/
advisor_brief vía ai_service.py) llamaba al SDK con el default de 10 min
por intento. Estos tests fijan el contrato nuevo: with_options(timeout=120.0)
sin alterar el loop de reintentos propio ni el retorno None en fallo
(que dispara los fallbacks deterministas de ai_service.py).

Mismo patrón de fakes que tests/test_clinical_llm_hardening.py.
"""
from __future__ import annotations

from types import SimpleNamespace

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
    """Imita Anthropic: with_options(...) devuelve el cliente configurado."""

    def __init__(self, outcome):
        self.messages = _FakeMessages(outcome)
        self.with_options_kwargs = None

    def with_options(self, **kwargs):
        self.with_options_kwargs = kwargs
        return self


def _response(text="respuesta"):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_call_claude_configura_timeout_explicito(monkeypatch):
    client = _FakeClient(_response("hola"))
    monkeypatch.setattr(ai_client, "get_client", lambda: client)

    out = ai_client.call_claude("prompt", session_id="s1")

    assert out == "hola"
    assert client.with_options_kwargs == {"timeout": 120.0}
    assert client.messages.calls == 1


def test_call_claude_sigue_devolviendo_none_tras_agotar_reintentos(monkeypatch):
    """El contrato de fallo no cambia: None → fallbacks deterministas."""
    client = _FakeClient(RuntimeError("api caida"))
    monkeypatch.setattr(ai_client, "get_client", lambda: client)

    out = ai_client.call_claude("prompt", session_id="s1", max_retries=1)

    assert out is None
    # max_retries=1 → 2 intentos del loop propio
    assert client.messages.calls == 2
