"""Anthropic Claude AI client wrapper."""

import time
import logging
from typing import Optional
from pathlib import Path

import anthropic
from anthropic import Anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize client
_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    """Get or create Anthropic client."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def classify_anthropic_error(e: Exception) -> str:
    """Clasifica una excepción del SDK de Anthropic en un `kind` estable.

    Fase C/B (B-050): permite que los servicios elijan un mensaje público
    por causa en lugar del genérico "no respondió". Devuelve uno de:

    - 'timeout'     · anthropic.APITimeoutError (se chequea antes que
                      connection porque es su subclase)
    - 'rate_limit'  · anthropic.RateLimitError (429)
    - 'connection'  · anthropic.APIConnectionError
    - 'server'      · APIStatusError con status_code >= 500
    - 'auth'        · APIStatusError 401/403
    - 'bad_request' · resto de 4xx
    - 'unknown'     · cualquier otra excepción
    """
    if isinstance(e, anthropic.APITimeoutError):
        return "timeout"
    if isinstance(e, anthropic.RateLimitError):
        return "rate_limit"
    if isinstance(e, anthropic.APIConnectionError):
        return "connection"
    if isinstance(e, anthropic.APIStatusError):
        status = getattr(e, "status_code", None)
        if status is None:
            return "unknown"
        if status >= 500:
            return "server"
        if status in (401, 403):
            return "auth"
        if 400 <= status < 500:
            return "bad_request"
        return "unknown"
    return "unknown"


def load_prompt(prompt_name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{prompt_name}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_name}")
    return prompt_path.read_text(encoding="utf-8")


def call_claude_chat(
    messages: list[dict],
    system: str,
    session_id: str,
    feature: str,
    max_tokens: int = 1000,
    temperature: float = 0.6,
) -> tuple[Optional[str], dict]:
    """Llamada conversacional a Claude (historial multi-turno + system prompt).

    Fase C pieza C (B-049) · chat real de Hop. A diferencia de
    :func:`call_claude` (un solo prompt user), acepta el historial completo
    como ``messages`` y un ``system`` separado, y devuelve también metadata
    (tokens/latencia) para el tracking M-001.

    Args:
        messages: lista de dicts {"role": "user"|"assistant", "content": str}.
        system: system prompt ya renderizado (va como ``system=`` del API).
        session_id: identificador para logging (usamos el user_id).
        feature: etiqueta de la feature para logging/tracking (ej. "hop_chat").
        max_tokens: tope de salida.
        temperature: temperatura de muestreo.

    Returns:
        (texto, metadata). ``texto`` es None si la llamada falló; metadata
        siempre incluye ``latency_ms`` y, en éxito, ``tokens_input``,
        ``tokens_output`` y ``stop_reason``. En error incluye ``error_kind``
        (vía :func:`classify_anthropic_error`). El detalle del error va SOLO
        a logs, nunca en metadata ni al usuario.
    """
    # max_retries=2 + timeout 45s: el SDK reintenta 429/5xx/conexión solo.
    client = get_client().with_options(max_retries=2, timeout=45.0)
    start_time = time.time()
    metadata: dict = {"model": settings.ai_model, "feature": feature}

    try:
        response = client.messages.create(
            model=settings.ai_model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        metadata["latency_ms"] = int((time.time() - start_time) * 1000)
        metadata["error_kind"] = classify_anthropic_error(e)
        logger.warning(
            "AI chat call failed",
            extra={
                "session_id": session_id,
                "feature": feature,
                "error_kind": metadata["error_kind"],
                "error": str(e),  # SOLO a logs
                "latency_ms": metadata["latency_ms"],
            },
        )
        return None, metadata

    metadata["latency_ms"] = int((time.time() - start_time) * 1000)
    usage = getattr(response, "usage", None)
    metadata["tokens_input"] = getattr(usage, "input_tokens", None)
    metadata["tokens_output"] = getattr(usage, "output_tokens", None)
    metadata["stop_reason"] = getattr(response, "stop_reason", None)

    if metadata["stop_reason"] == "max_tokens":
        logger.warning(
            "AI chat response truncated at max_tokens",
            extra={"session_id": session_id, "feature": feature, "max_tokens": max_tokens},
        )

    # Primer bloque con atributo .text (NO asumir content[0] · puede haber
    # bloques no-texto al inicio según el modelo/configuración).
    output_text: Optional[str] = None
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            output_text = text
            break

    if output_text is None:
        metadata["error_kind"] = "empty_response"
        logger.warning(
            "AI chat call returned no text block",
            extra={"session_id": session_id, "feature": feature},
        )
        return None, metadata

    logger.info(
        "AI chat call successful",
        extra={
            "session_id": session_id,
            "feature": feature,
            "tokens_input": metadata["tokens_input"],
            "tokens_output": metadata["tokens_output"],
            "latency_ms": metadata["latency_ms"],
        },
    )
    return output_text, metadata


def call_claude(
    prompt: str,
    session_id: str,
    prompt_version: str = "v1",
    max_retries: int = 1,
) -> Optional[str]:
    """
    Call Claude API with retry logic and logging.

    Args:
        prompt: The formatted prompt to send
        session_id: Session ID for logging
        prompt_version: Version identifier for logging
        max_retries: Number of retries on failure

    Returns:
        The response text or None if all retries fail
    """
    # Timeout explícito: sin él, el SDK espera hasta 10 min por intento y el
    # loop de reintentos propio multiplica esa espera. 120s cubre las llamadas
    # largas de journey (reflection/synthesis/routes/advisor_brief · una
    # recomendación fresca tarda ~48s) y es coherente con call_claude_chat
    # (45s para chat corto). Los fallbacks deterministas de ai_service.py
    # siguen activándose igual cuando esto devuelve None.
    client = get_client().with_options(timeout=120.0)
    input_size = len(prompt)
    start_time = time.time()

    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=settings.ai_model,
                max_tokens=settings.ai_max_tokens,
                temperature=settings.ai_temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            output_text = response.content[0].text
            latency_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "AI call successful",
                extra={
                    "session_id": session_id,
                    "prompt_version": prompt_version,
                    "input_size": input_size,
                    "output_size": len(output_text),
                    "latency_ms": latency_ms,
                    "attempt": attempt + 1,
                }
            )

            return output_text

        except Exception as e:
            logger.warning(
                f"AI call failed (attempt {attempt + 1}/{max_retries + 1}): {e}",
                extra={
                    "session_id": session_id,
                    "prompt_version": prompt_version,
                    "error": str(e),
                }
            )
            if attempt == max_retries:
                logger.error(
                    "AI call failed after all retries",
                    extra={
                        "session_id": session_id,
                        "prompt_version": prompt_version,
                    }
                )
                return None

    return None
