"""Audio transcription endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services.transcription_service import transcribe_audio
from app.services.ai_usage_service import record_ai_usage

router = APIRouter(prefix="/transcription", tags=["Transcription"])
logger = logging.getLogger(__name__)

# Supported audio formats by Whisper
SUPPORTED_FORMATS = {
    "audio/webm",
    "audio/mp3",
    "audio/mpeg",
    "audio/mp4",
    "audio/mpga",
    "audio/m4a",
    "audio/wav",
    "audio/ogg",
    "video/webm",  # Browser often sends webm as video/webm
}


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Transcribe audio file to text using OpenAI Whisper.

    Accepts audio files up to 25MB in formats: webm, mp3, mp4, mpeg, mpga, m4a, wav, ogg
    """
    # Validate file type
    content_type = audio.content_type or ""
    if content_type not in SUPPORTED_FORMATS and not content_type.startswith("audio/"):
        logger.warning(f"Unsupported audio format: {content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {content_type}. Supported formats: webm, mp3, mp4, wav, ogg"
        )

    # Check file size (Whisper limit is 25MB)
    MAX_SIZE = 25 * 1024 * 1024  # 25MB
    content = await audio.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file too large. Maximum size is 25MB."
        )

    # Get filename with extension for OpenAI
    filename = audio.filename or "audio.webm"

    try:
        # Pass as tuple (filename, content, content_type) for OpenAI
        result = await transcribe_audio(
            audio_file=(filename, content, content_type),
            language="es"
        )

        # Tracking M-001 · whisper se cobra por minuto; el costo ya viene
        # calculado en usage. Best-effort y NO se filtra al cliente.
        usage = result.get("usage") or {}
        if usage:
            record_ai_usage(
                db,
                provider=usage.get("provider", "openai"),
                model=usage.get("model", "whisper-1"),
                feature="audio_transcription",
                latency_ms=usage.get("latency_ms"),
                cost_usd=usage.get("cost_usd"),
                user_id=current_user.id,
            )

        return {"text": result.get("text", "")}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transcribe audio. Please try again."
        )
