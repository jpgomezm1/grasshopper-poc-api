"""Tests del servicio de transcripción (Whisper · cliente async).

Fix hardening: el servicio usaba el cliente OpenAI SÍNCRONO dentro de una
corrutina, bloqueando el event loop completo del dyno durante toda la
transcripción. Estos tests fijan el contrato nuevo:

  - se usa ``AsyncOpenAI`` y la llamada se await-ea (no bloquea el loop)
  - el cliente se construye con timeout explícito (120s · audios de hasta 25MB)
  - el manejo de errores existente se conserva (ValueError sin API key,
    excepciones del SDK se propagan al caller)

Sin red: ``AsyncOpenAI`` se reemplaza por un fake en el módulo del servicio.
"""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from app.services import transcription_service as ts


def _install_fake_client(monkeypatch, result, api_key="sk-test"):
    """Reemplaza AsyncOpenAI en el módulo del servicio y captura los kwargs."""
    captured: dict = {}

    class _FakeTranscriptions:
        async def create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            if isinstance(result, Exception):
                raise result
            return result

    class _FakeAsyncOpenAI:
        def __init__(self, api_key=None, timeout=None):
            captured["api_key"] = api_key
            captured["timeout"] = timeout
            self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions())

    monkeypatch.setattr(ts, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(
        ts, "get_settings", lambda: SimpleNamespace(openai_api_key=api_key)
    )
    return captured


def test_transcribe_audio_es_corrutina():
    """El contrato async se mantiene (el endpoint la await-ea)."""
    assert inspect.iscoroutinefunction(ts.transcribe_audio)


def test_transcribe_usa_cliente_async_con_timeout(monkeypatch):
    captured = _install_fake_client(monkeypatch, "  hola mundo \n")

    out = asyncio.run(ts.transcribe_audio(("a.webm", b"bytes", "audio/webm")))

    assert out["text"] == "hola mundo"
    assert captured["api_key"] == "sk-test"
    assert captured["timeout"] == ts.TRANSCRIPTION_TIMEOUT_S == 120.0
    kwargs = captured["create_kwargs"]
    assert kwargs["model"] == "whisper-1"
    assert kwargs["language"] == "es"
    # verbose_json para obtener `duration` (costo M-001)
    assert kwargs["response_format"] == "verbose_json"
    # Sin prompt explícito usa el contexto por defecto
    assert kwargs["prompt"] == ts.TRANSCRIPTION_PROMPT


def test_transcribe_respuesta_objeto_con_text(monkeypatch):
    """Si el SDK devuelve objeto (no str), se usa .text y se hace strip."""
    _install_fake_client(monkeypatch, SimpleNamespace(text="  hola  "))

    out = asyncio.run(ts.transcribe_audio(("a.mp3", b"x", "audio/mp3")))

    assert out["text"] == "hola"


def test_transcribe_calcula_costo_por_duracion(monkeypatch):
    """verbose_json trae `duration` (s) → usage.cost_usd = min * $0.006."""
    _install_fake_client(monkeypatch, SimpleNamespace(text="hola", duration=120.0))

    out = asyncio.run(ts.transcribe_audio(("a.webm", b"x", "audio/webm")))

    usage = out["usage"]
    assert usage["provider"] == "openai"
    assert usage["model"] == "whisper-1"
    assert usage["duration_s"] == 120.0
    assert usage["cost_usd"] == round(2 * ts.WHISPER_COST_PER_MINUTE, 6)  # 2 min
    assert "latency_ms" in usage


def test_transcribe_sin_duracion_no_da_costo(monkeypatch):
    """Sin `duration` (p.ej. SDK devuelve str) → usage sin cost_usd, texto OK."""
    _install_fake_client(monkeypatch, "  hola  ")

    out = asyncio.run(ts.transcribe_audio(("a.webm", b"x", "audio/webm")))

    assert out["text"] == "hola"
    assert "cost_usd" not in out["usage"]


def test_transcribe_sin_api_key_levanta_valueerror(monkeypatch):
    _install_fake_client(monkeypatch, "no importa", api_key="")

    with pytest.raises(ValueError):
        asyncio.run(ts.transcribe_audio(("a.webm", b"x", "audio/webm")))


def test_transcribe_propaga_errores_del_sdk(monkeypatch):
    """El manejo de errores existente se conserva: loguea y re-lanza."""
    _install_fake_client(monkeypatch, RuntimeError("whisper exploto"))

    with pytest.raises(RuntimeError, match="whisper exploto"):
        asyncio.run(ts.transcribe_audio(("a.webm", b"x", "audio/webm")))
