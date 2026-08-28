# -*- coding: utf-8 -*-
"""Los helpers que leen un documento con Claude · texto y visión.

Vivían privados dentro de `external_test_parser` y se movieron a
`app/services/document_ai.py` el 2026-08-28, cuando el lector de diplomas
necesitó exactamente lo mismo. Este archivo es el test que se mudó con ellos.

## Por qué esto importa más de lo que parece

Al mover el helper, el test que lo probaba seguía parcheando
`external_test_parser.get_client` — y como la función ya leía
`document_ai.get_client`, el parche dejó de aplicar y **la llamada salió a la
API de verdad**. El test no falló por "no se llamó a nada": falló porque
Anthropic contestó un saludo real.

O sea: un mock que apunta al módulo equivocado no se nota como un mock roto,
se nota como una llamada de red silenciosa que gasta tokens. Por eso aquí se
parchea `document_ai.get_client`, que es donde de verdad se resuelve el
cliente, y por eso hay un test que comprueba que el doble se usó.
"""
from __future__ import annotations

import pytest

from app.services import document_ai


class _Usage:
    input_tokens = 640
    output_tokens = 210


class _Block:
    text = "respuesta del modelo"


class _Response:
    content = [_Block()]
    usage = _Usage()


class _Client:
    """Doble del SDK · registra con qué se le llamó."""

    def __init__(self):
        self.llamadas = []

    def with_options(self, **kw):
        return self

    @property
    def messages(self):
        padre = self

        class _Messages:
            @staticmethod
            def create(**kw):
                padre.llamadas.append(kw)
                return _Response()

        return _Messages()


@pytest.fixture()
def cliente(monkeypatch):
    c = _Client()
    monkeypatch.setattr(document_ai, "get_client", lambda: c)
    return c


def test_devuelve_texto_y_metadata(cliente):
    texto, meta = document_ai.call_claude_messages([{"role": "user", "content": "hola"}])

    assert texto == "respuesta del modelo"
    assert meta["tokens_input"] == 640
    assert meta["tokens_output"] == 210
    assert "latency_ms" in meta
    assert meta["model"]


def test_no_sale_a_la_red_si_el_doble_esta_puesto(cliente):
    """⭐ El que habría cazado el fallo del refactor.

    Si el parche apunta al módulo equivocado, `llamadas` se queda vacío y la
    petición se va a Anthropic de verdad — sin que ningún assert lo note.
    """
    document_ai.call_claude_messages([{"role": "user", "content": "hola"}])
    assert len(cliente.llamadas) == 1, "la llamada no pasó por el doble · salió a la red"


def test_la_extraccion_es_determinista(cliente):
    """`temperature=0` a propósito: esto lee documentos, no redacta. Con
    temperatura alta el mismo diploma daría dos lecturas distintas."""
    document_ai.call_claude_messages([{"role": "user", "content": "hola"}])
    assert cliente.llamadas[0]["temperature"] == 0


def test_vision_manda_la_imagen_antes_del_texto(cliente):
    """El orden importa: Claude lee mejor la imagen si va primero."""
    document_ai.call_claude_vision("¿qué dice?", b"\x89PNG-falso", "image/png")

    contenido = cliente.llamadas[0]["messages"][0]["content"]
    assert contenido[0]["type"] == "image"
    assert contenido[0]["source"]["media_type"] == "image/png"
    assert contenido[1]["type"] == "text"


def test_vision_codifica_la_imagen_en_base64(cliente):
    import base64

    crudo = b"\x89PNG-falso"
    document_ai.call_claude_vision("x", crudo, "image/png")

    enviado = cliente.llamadas[0]["messages"][0]["content"][0]["source"]["data"]
    assert base64.standard_b64decode(enviado) == crudo


def test_sin_bloque_de_texto_revienta_con_un_error_propio(monkeypatch):
    """Y no con un `IndexError` a 5 marcos de distancia."""

    class _Vacia:
        content = []
        usage = None

    class _C:
        def with_options(self, **kw):
            return self

        class messages:  # noqa: N801
            @staticmethod
            def create(**kw):
                return _Vacia()

    monkeypatch.setattr(document_ai, "get_client", lambda: _C())

    with pytest.raises(document_ai.DocumentAIError):
        document_ai.call_claude_messages([{"role": "user", "content": "x"}])
