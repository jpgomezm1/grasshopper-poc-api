"""Tests · hardening de _call_llm del análisis clínico (Fase C/B · B-050).

Cubre:
- classify_anthropic_error: mapeo de cada excepción tipada del SDK a un kind.
- _call_llm: with_options(max_retries=2, timeout=60.0), error_kind en
  metadata por cada tipo de fallo, kind 'empty' cuando no hay bloque de
  texto, y caso de éxito con usage poblado.
- _public_error_message: mensaje cara al usuario por kind.
"""
from __future__ import annotations

import anthropic
import httpx
import pytest

from app.core.ai_client import classify_anthropic_error
from app.services import clinical_analysis_service as svc


# ---------------------------------------------------------------------------
# Helpers · construcción de excepciones tipadas del SDK (anthropic==0.18.1)
# ---------------------------------------------------------------------------

_REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(status_code: int) -> anthropic.APIStatusError:
    resp = httpx.Response(status_code, request=_REQ)
    if status_code == 429:
        return anthropic.RateLimitError("rate limited", response=resp, body=None)
    return anthropic.APIStatusError(f"status {status_code}", response=resp, body=None)


def _timeout_error() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=_REQ)


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=_REQ)


# ---------------------------------------------------------------------------
# Stubs del cliente Anthropic
# ---------------------------------------------------------------------------


class _StubBlock:
    def __init__(self, text):
        self.text = text


class _StubUsage:
    def __init__(self, input_tokens=1200, output_tokens=900):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _StubResponse:
    def __init__(self, content, usage=None):
        self.content = content
        self.usage = usage


class _StubMessages:
    def __init__(self, exc=None, response=None):
        self._exc = exc
        self._response = response

    def create(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


class _StubClient:
    """Imita Anthropic: with_options(...) devuelve el cliente configurado."""

    def __init__(self, exc=None, response=None):
        self.messages = _StubMessages(exc=exc, response=response)
        self.with_options_kwargs = None

    def with_options(self, **kwargs):
        self.with_options_kwargs = kwargs
        return self


def _patch_client(monkeypatch, client: _StubClient) -> None:
    # _call_llm usa get_client importado en el namespace del servicio
    monkeypatch.setattr(svc, "get_client", lambda: client)


# ---------------------------------------------------------------------------
# classify_anthropic_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_factory,expected",
    [
        (_timeout_error, "timeout"),
        (lambda: _status_error(429), "rate_limit"),
        (_connection_error, "connection"),
        (lambda: _status_error(500), "server"),
        (lambda: _status_error(503), "server"),
        (lambda: _status_error(401), "auth"),
        (lambda: _status_error(403), "auth"),
        (lambda: _status_error(400), "bad_request"),
        (lambda: _status_error(422), "bad_request"),
        (lambda: ValueError("boom"), "unknown"),
    ],
)
def test_classify_anthropic_error(exc_factory, expected):
    assert classify_anthropic_error(exc_factory()) == expected


def test_timeout_classified_before_connection():
    # APITimeoutError es subclase de APIConnectionError · debe ganar 'timeout'
    assert isinstance(_timeout_error(), anthropic.APIConnectionError)
    assert classify_anthropic_error(_timeout_error()) == "timeout"


# ---------------------------------------------------------------------------
# _call_llm · clasificación en metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_factory,expected_kind",
    [
        (_timeout_error, "timeout"),
        (lambda: _status_error(429), "rate_limit"),
        (_connection_error, "connection"),
        (lambda: _status_error(503), "server"),
        (lambda: _status_error(401), "auth"),
        (lambda: _status_error(400), "bad_request"),
        (lambda: RuntimeError("???"), "unknown"),
    ],
)
def test_call_llm_sets_error_kind(monkeypatch, exc_factory, expected_kind):
    client = _StubClient(exc=exc_factory())
    _patch_client(monkeypatch, client)

    text, metadata = svc._call_llm("prompt", "user-1")

    assert text is None
    assert metadata["error_kind"] == expected_kind
    assert "error" in metadata


def test_call_llm_uses_sdk_retries(monkeypatch):
    client = _StubClient(response=_StubResponse([_StubBlock('{"ok": 1}')], _StubUsage()))
    _patch_client(monkeypatch, client)

    svc._call_llm("prompt", "user-1")

    assert client.with_options_kwargs == {"max_retries": 2, "timeout": 60.0}


def test_call_llm_empty_content_is_empty_kind(monkeypatch):
    client = _StubClient(response=_StubResponse([], _StubUsage()))
    _patch_client(monkeypatch, client)

    text, metadata = svc._call_llm("prompt", "user-1")

    assert text is None
    assert metadata["error_kind"] == "empty"


def test_call_llm_block_without_text_is_empty_kind(monkeypatch):
    class _ToolBlock:
        type = "tool_use"  # sin atributo .text

    client = _StubClient(response=_StubResponse([_ToolBlock()], _StubUsage()))
    _patch_client(monkeypatch, client)

    text, metadata = svc._call_llm("prompt", "user-1")

    assert text is None
    assert metadata["error_kind"] == "empty"


def test_call_llm_success_with_usage(monkeypatch):
    client = _StubClient(
        response=_StubResponse(
            [_StubBlock('{"narrative": "ok"}')],
            _StubUsage(input_tokens=1500, output_tokens=800),
        )
    )
    _patch_client(monkeypatch, client)

    text, metadata = svc._call_llm("prompt", "user-1")

    assert text == '{"narrative": "ok"}'
    assert metadata["tokens_input"] == 1500
    assert metadata["tokens_output"] == 800
    assert "error_kind" not in metadata
    assert metadata["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# Mensaje público por kind
# ---------------------------------------------------------------------------

MSG_SLOW = "El análisis IA está tardando más de lo normal. Inténtalo de nuevo en unos minutos."
MSG_RATE = "Hemos recibido muchas solicitudes seguidas. Espera un momento y vuelve a intentarlo."
MSG_INCOMPLETE = "El análisis IA devolvió un resultado incompleto. Reintenta; si persiste, avísanos."
MSG_UNAVAILABLE = "El motor de análisis IA no está disponible en este momento."


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("timeout", MSG_SLOW),
        ("connection", MSG_SLOW),
        ("server", MSG_SLOW),
        ("rate_limit", MSG_RATE),
        ("parse", MSG_INCOMPLETE),
        ("empty", MSG_INCOMPLETE),
        ("auth", MSG_UNAVAILABLE),
        ("bad_request", MSG_UNAVAILABLE),
        ("unknown", MSG_UNAVAILABLE),
        (None, MSG_UNAVAILABLE),
        ("algo_raro", MSG_UNAVAILABLE),
    ],
)
def test_public_error_message_by_kind(kind, expected):
    assert svc._public_error_message(kind) == expected


def test_generate_raises_public_message_for_rate_limit(monkeypatch):
    """Wiring end-to-end de generate(): el error_kind de _call_llm define
    el mensaje de la ClinicalAnalysisFailure (lo que ve el endpoint)."""
    student = type("S", (), {"id": "u-1", "clinical_analysis_cached_at": None})()

    monkeypatch.setattr(svc, "insufficient_inputs_reason", lambda db, s: None)
    monkeypatch.setattr(
        svc,
        "_gather_inputs",
        lambda db, s: {
            "demographic_block": "",
            "consolidated_block": "",
            "tests_block": "",
            "journey_answers_block": "",
            "journal_block": "",
        },
    )
    monkeypatch.setattr(svc, "load_prompt", lambda name: "{demographic_block}{consolidated_block}{tests_block}{journey_answers_block}{journal_block}")
    client = _StubClient(exc=_status_error(429))
    _patch_client(monkeypatch, client)

    with pytest.raises(svc.ClinicalAnalysisFailure) as exc_info:
        svc.generate(db=None, student=student, force=True)

    assert str(exc_info.value) == MSG_RATE
