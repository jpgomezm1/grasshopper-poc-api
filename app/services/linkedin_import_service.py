"""CV-2 · Traer el perfil de LinkedIn a la hoja de vida, sin scraping.

## Qué se pidió y qué se hizo

En la reunión del 21-07 se pidió un *"scraper de LinkedIn para profesionales:
subes tu usuario y alimenta el perfil automáticamente"*.

**No se construye como scraper.** Los términos de servicio de LinkedIn prohíben
el scraping automatizado y hay litigio conocido sobre el tema; montarlo expondría
a la agencia a un riesgo legal que no pidió asumir y probablemente no sabe que
estaría asumiendo. Tampoco funcionaría con perfiles privados.

Lo que se hace en su lugar: **la persona pega su propio perfil** (lo copia de su
página de LinkedIn, o del PDF que LinkedIn deja descargar desde "Recursos →
Guardar como PDF") y la IA lo estructura. El resultado para el usuario es el
mismo —no volver a escribir a mano lo que ya escribió allá— sin el riesgo, y
funciona aunque su perfil sea privado.

## Por qué devuelve una PROPUESTA y no escribe el CV

Es la hoja de vida de la persona y lleva su nombre. El endpoint devuelve un
borrador para que lo revise y confirme; nunca pisa lo que ya tenga escrito. La
clienta elogió explícitamente el CV ("el resto está muy chévere"), así que lo
último que conviene es sobreescribirlo sin preguntar.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Un perfil de LinkedIn pegado entero rara vez pasa de unos pocos miles de
# caracteres. El tope evita que alguien pegue un libro y dispare el costo de IA.
MAX_CHARS = 12000
MIN_CHARS = 80


class LinkedInImportError(RuntimeError):
    """No se pudo interpretar lo que pegó la persona."""


_PROMPT = """Recibes el texto que una persona copió de su propio perfil de LinkedIn.
Tu trabajo es estructurarlo para prellenar su hoja de vida en español.

REGLAS DURAS:
- NO inventes NADA. Si un dato no está en el texto, omítelo. Es preferible un
  campo vacío que uno inventado: esto va a una hoja de vida real con su nombre.
- Traduce al español lo que esté en inglés, salvo nombres propios de empresas,
  instituciones, cargos oficiales y tecnologías.
- `headline`: una línea que resuma quién es profesionalmente. Máximo 120 caracteres.
- `summary`: 2-4 frases en primera persona, con lo que de verdad dice el texto.
- `strengths`: 3-6 fortalezas que se DEDUZCAN de su experiencia concreta, no
  genéricas. Cada una máximo 100 caracteres.
- `interests`: 3-6 áreas o temas visibles en su trayectoria.
- `experience`: hasta 8 puestos, del más reciente al más antiguo.
- Devuelve SOLO JSON parseable. Sin texto antes ni después. Sin code fences.

ESQUEMA:
{{
  "headline": "string o null",
  "summary": "string o null",
  "strengths": ["string"],
  "interests": ["string"],
  "experience": [
    {{"role": "string", "organization": "string o null", "period": "string o null"}}
  ],
  "education": [
    {{"title": "string", "institution": "string o null", "period": "string o null"}}
  ]
}}

TEXTO DEL PERFIL:
---
{perfil}
---

Ahora devuelve el JSON."""


def _extraer_json(texto: str) -> Dict[str, Any]:
    """Saca el objeto JSON de la respuesta, tolerando envoltorios."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-zA-Z]*\n?", "", texto)
        texto = re.sub(r"\n?```$", "", texto).strip()
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio == -1 or fin <= inicio:
        raise LinkedInImportError("La respuesta del modelo no trae JSON.")
    try:
        return json.loads(texto[inicio : fin + 1])
    except json.JSONDecodeError as exc:
        raise LinkedInImportError(f"JSON inválido: {exc}") from exc


def _texto(valor: Any, limite: int) -> Optional[str]:
    if valor is None:
        return None
    limpio = str(valor).strip()
    return limpio[:limite] if limpio else None


def _lista(valor: Any, max_items: int, limite: int) -> List[str]:
    if not isinstance(valor, list):
        return []
    salida: List[str] = []
    for item in valor:
        t = _texto(item, limite)
        if t:
            salida.append(t)
    return salida[:max_items]


def _entradas(valor: Any, claves: tuple, max_items: int) -> List[Dict[str, Optional[str]]]:
    if not isinstance(valor, list):
        return []
    salida = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        fila = {k: _texto(item.get(k), 160) for k in claves}
        if any(fila.values()):
            salida.append(fila)
    return salida[:max_items]


def normalizar(bruto: Dict[str, Any]) -> Dict[str, Any]:
    """Limpia y acota lo que devolvió el modelo · nunca confiar en crudo."""
    return {
        "headline": _texto(bruto.get("headline"), 120),
        "summary": _texto(bruto.get("summary"), 1200),
        "strengths": _lista(bruto.get("strengths"), 6, 100),
        "interests": _lista(bruto.get("interests"), 6, 100),
        "experience": _entradas(
            bruto.get("experience"), ("role", "organization", "period"), 8
        ),
        "education": _entradas(
            bruto.get("education"), ("title", "institution", "period"), 6
        ),
    }


def importar_desde_texto(perfil: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Estructura el texto pegado. Devuelve ``(propuesta, metadata_de_ia)``.

    La metadata alimenta el tracking de consumo (`ai_usage_logs`).
    """
    perfil = (perfil or "").strip()
    if len(perfil) < MIN_CHARS:
        raise LinkedInImportError(
            "Pega un poco más de tu perfil: con tan poco texto no puedo armar nada."
        )
    if len(perfil) > MAX_CHARS:
        perfil = perfil[:MAX_CHARS]

    from app.services.ai_client import get_client

    settings = get_settings()
    client = get_client().with_options(timeout=120.0, max_retries=2)
    inicio = time.time()
    respuesta = client.messages.create(
        model=settings.ai_model,
        max_tokens=settings.ai_max_tokens or 1500,
        temperature=0,  # estructurar no es escribir: determinista
        messages=[{"role": "user", "content": _PROMPT.format(perfil=perfil)}],
    )

    meta: Dict[str, Any] = {
        "model": settings.ai_model,
        "latency_ms": int((time.time() - inicio) * 1000),
    }
    usage = getattr(respuesta, "usage", None)
    meta["tokens_input"] = getattr(usage, "input_tokens", None)
    meta["tokens_output"] = getattr(usage, "output_tokens", None)

    texto = None
    for bloque in getattr(respuesta, "content", []) or []:
        t = getattr(bloque, "text", None)
        if t is not None:
            texto = t
            break
    if texto is None:
        raise LinkedInImportError("El modelo no devolvió texto.")

    return normalizar(_extraer_json(texto)), meta


def a_overrides(propuesta: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce la propuesta a los campos que entiende `cv_profile_service`.

    `experience` y `education` no tienen campo propio en el CV todavía: se
    resumen dentro del `summary` para no perderlos. Cuando exista el campo, esto
    se cambia aquí y en un solo sitio.
    """
    overrides: Dict[str, Any] = {}
    if propuesta.get("headline"):
        overrides["headline"] = propuesta["headline"]

    partes = []
    if propuesta.get("summary"):
        partes.append(propuesta["summary"])
    exp = propuesta.get("experience") or []
    if exp:
        lineas = []
        for e in exp[:4]:
            trozo = e.get("role") or ""
            if e.get("organization"):
                trozo += f" en {e['organization']}"
            if e.get("period"):
                trozo += f" ({e['period']})"
            if trozo.strip():
                lineas.append(trozo.strip())
        if lineas:
            partes.append("Experiencia: " + " · ".join(lineas) + ".")
    if partes:
        overrides["summary"] = "\n\n".join(partes)[:2000]

    if propuesta.get("strengths"):
        overrides["strengths"] = propuesta["strengths"]
    if propuesta.get("interests"):
        overrides["interests"] = propuesta["interests"]
    return overrides
