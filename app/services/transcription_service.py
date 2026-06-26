"""Audio transcription service using OpenAI Whisper."""

import logging
import time
from typing import Union, BinaryIO, Tuple, Optional

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# whisper-1 se factura por minuto de audio (no por tokens). Lo usamos para el
# costo M-001; la duración sale de response_format="verbose_json".
WHISPER_COST_PER_MINUTE = 0.006

# Type for audio file: can be BinaryIO or tuple (filename, content, content_type)
AudioFileType = Union[BinaryIO, Tuple[str, bytes, str]]

# Timeout explícito para la llamada a Whisper. Los uploads pueden llegar a
# 25MB (límite del endpoint /transcription/transcribe), así que damos margen
# amplio; el default del SDK (10 min) bloqueaba el worker demasiado tiempo.
TRANSCRIPTION_TIMEOUT_S = 120.0

# Context prompt to improve transcription accuracy for Spanish speakers
# This helps Whisper understand the context and improves accuracy
TRANSCRIPTION_PROMPT = """
Esta es una respuesta hablada en español de un joven latinoamericano
sobre sus metas educativas, pasiones, intereses, fortalezas y planes
de estudiar o trabajar en el extranjero. La persona habla sobre:
- Sus pasiones y lo que le gustaría lograr en la vida
- Sus hobbies e intereses en el tiempo libre
- El área en la que se imagina trabajando
- Sus habilidades y fortalezas
- Sus preocupaciones o dudas sobre dar un paso internacional
"""


async def transcribe_audio(
    audio_file: AudioFileType,
    language: str = "es",
    prompt: Optional[str] = None
) -> dict:
    """
    Transcribe audio using OpenAI Whisper API.

    Args:
        audio_file: Audio file - can be BinaryIO or tuple (filename, bytes, content_type)
        language: Language code (default: "es" for Spanish)
        prompt: Optional context prompt to improve accuracy

    Returns:
        dict con "text" (la transcripción) y "usage" (metadata M-001:
        provider/model/latency_ms y, si Whisper reportó duración,
        cost_usd/duration_s).
    """
    settings = get_settings()

    if not settings.openai_api_key:
        logger.error("OpenAI API key not configured")
        raise ValueError("OpenAI API key not configured")

    # Cliente ASYNC: la versión síncrona bloqueaba el event loop completo
    # del dyno mientras Whisper transcribía (todas las requests congeladas).
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=TRANSCRIPTION_TIMEOUT_S,
    )

    # Use default prompt if none provided
    context_prompt = prompt or TRANSCRIPTION_PROMPT

    start = time.time()
    try:
        # verbose_json (en vez de text) para obtener `duration` y poder estimar
        # el costo M-001. El texto sigue saliendo de .text · el parseo es
        # defensivo para que un cambio de formato NUNCA rompa la transcripción.
        transcript = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language,
            prompt=context_prompt,
            response_format="verbose_json",
        )

        latency_ms = int((time.time() - start) * 1000)

        if isinstance(transcript, str):
            text = transcript.strip()
            duration_s = None
        else:
            text = (getattr(transcript, "text", "") or "").strip()
            duration_s = getattr(transcript, "duration", None)

        # Costo best-effort · cualquier problema aquí NO debe afectar al texto.
        usage = {"provider": "openai", "model": "whisper-1", "latency_ms": latency_ms}
        try:
            if duration_s is not None:
                usage["duration_s"] = float(duration_s)
                usage["cost_usd"] = round(
                    (float(duration_s) / 60.0) * WHISPER_COST_PER_MINUTE, 6
                )
        except (TypeError, ValueError):
            pass

        logger.info(f"Successfully transcribed audio: {len(text)} characters")
        return {"text": text, "usage": usage}

    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        raise
