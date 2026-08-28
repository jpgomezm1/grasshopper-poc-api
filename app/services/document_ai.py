"""Leer un documento subido con Claude · texto o visión.

Estos tres helpers vivían privados dentro de `external_test_parser.py`, que
fue quien los necesitó primero (parsear el PDF de un test externo). Cuando el
lector de diplomas necesitó exactamente lo mismo —un PDF o una foto, sacar
texto, mandárselo al modelo— la alternativa era copiarlos.

Copiarlos es cómo se desincronizan: el arreglo de robustez que ya lleva este
código (timeout explícito de 120s y 2 reintentos, porque antes el SDK pelado
esperaba hasta 10 minutos sin reintentar; y leer el primer bloque con `.text`
en vez de `content[0]`, que puede no ser texto) se habría aplicado en una copia
y no en la otra.

Así que viven aquí y los importan los dos. No hay nada específico de tests ni
de diplomas en este módulo: recibe mensajes, devuelve texto y metadata.

## La metadata no es opcional

`(texto, meta)` con `model`/`tokens_input`/`tokens_output`/`latency_ms`
alimenta el tracking M-001. Quien llame tiene que registrarlo con
`record_ai_usage(..., provider=...)` — ojo que `provider` es obligatorio y
keyword-only, y olvidarlo lanza un `TypeError` que un `except` puede tragarse
dejando la auditoría vacía en silencio (ya pasó una vez).
"""
from __future__ import annotations

import base64
import time
from typing import Optional

from app.config import get_settings
from app.core.ai_client import get_client


class DocumentAIError(RuntimeError):
    """El modelo no devolvió nada utilizable."""


def call_claude_messages(messages: list) -> tuple[str, dict]:
    """Llama a Claude (texto o visión) y devuelve ``(texto, metadata)``.

    `temperature=0` a propósito: esto es extracción, no redacción. Con
    temperatura alta el mismo diploma daría dos lecturas distintas.
    """
    settings = get_settings()
    client = get_client().with_options(timeout=120.0, max_retries=2)
    start = time.time()
    response = client.messages.create(
        model=settings.ai_model,
        max_tokens=settings.ai_max_tokens or 1500,
        temperature=0,
        messages=messages,
    )
    meta: dict = {
        "model": settings.ai_model,
        "latency_ms": int((time.time() - start) * 1000),
    }
    usage = getattr(response, "usage", None)
    meta["tokens_input"] = getattr(usage, "input_tokens", None)
    meta["tokens_output"] = getattr(usage, "output_tokens", None)

    text: Optional[str] = None
    for block in getattr(response, "content", []) or []:
        t = getattr(block, "text", None)
        if t is not None:
            text = t
            break
    if text is None:
        raise DocumentAIError("la respuesta de Claude no trae ningún bloque de texto")
    return text, meta


def call_claude_vision(
    prompt_text: str, image_bytes: bytes, image_mime: str
) -> tuple[str, dict]:
    """Claude con una imagen adjunta · para lo que no tiene capa de texto."""
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return call_claude_messages(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_mime,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
    )


def call_claude_text(prompt_text: str) -> tuple[str, dict]:
    """Sólo texto · el camino barato, cuando el PDF sí tiene capa de texto."""
    return call_claude_messages([{"role": "user", "content": prompt_text}])
