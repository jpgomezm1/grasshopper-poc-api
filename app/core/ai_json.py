"""Utilidad central para parsear respuestas JSON de Claude · Fase C/A.

Claude a veces envuelve el JSON en fences de Markdown (```json ... ```)
o lo rodea de prosa explicativa. Antes, cada servicio tenía su propia
copia de los helpers de limpieza y `app/services/ai_service.py` hacía
`json.loads(response)` directo, lo que activaba el fallback genérico
en silencio cuando llegaban fences.

Este módulo centraliza la limpieza + el parseo robusto:

- `strip_code_fences`: quita fences ```json / ``` envolventes.
- `extract_first_json`: rescata el primer objeto JSON balanceado dentro
  de texto arbitrario (prosa antes/después del objeto).
- `parse_ai_json`: pipeline completo · fences → json.loads → fallback
  de extracción → `AIJsonError` si nada funciona.
"""
from __future__ import annotations

import json
from typing import Any, Optional


class AIJsonError(ValueError):
    """La respuesta del modelo no contiene JSON parseable.

    Hereda de ValueError (igual que json.JSONDecodeError) para que los
    call-sites existentes con `except (ValueError, KeyError)` la capturen
    sin cambiar su contrato.
    """


def strip_code_fences(text: str) -> str:
    """Quita fences de Markdown (```json ... ```) envolventes, si existen.

    Si el texto no empieza con ``` se devuelve tal cual (solo .strip()).
    """
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        # descarta la primera línea (``` o ```json)
        lines = lines[1:]
        # descarta el ``` de cierre si está presente
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def extract_first_json(text: str) -> Optional[str]:
    """Devuelve el primer objeto JSON balanceado dentro de `text`, o None.

    Defensivo: recorre el texto contando llaves `{`/`}` para encontrar el
    primer objeto completo, ignorando prosa antes y después. No valida
    que el contenido sea JSON válido · eso lo hace el caller con
    json.loads.
    """
    if not text:
        return None
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    return text[start : i + 1]
    return None


def parse_ai_json(text: str) -> Any:
    """Parsea de forma robusta una respuesta JSON de Claude.

    Estrategia en cascada:
      1. `strip_code_fences` + json.loads directo.
      2. Fallback: `extract_first_json` (primer objeto balanceado) + json.loads.
      3. Si nada funciona · `AIJsonError` con un preview de los primeros
         200 caracteres para facilitar el debug en logs.

    Raises:
        AIJsonError: si la respuesta no contiene JSON parseable.
    """
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    recovered = extract_first_json(cleaned)
    if recovered is not None:
        try:
            return json.loads(recovered)
        except json.JSONDecodeError:
            pass

    preview = (text or "")[:200]
    raise AIJsonError(f"La respuesta del modelo no contiene JSON parseable · preview: {preview!r}")
