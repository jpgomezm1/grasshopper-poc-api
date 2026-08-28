"""Leer un logro para prellenar una actividad · AH, 2026-08-28.

    "quiero que se puedan como subir logros, es decir por ejemplo soy el
     capitán del equipo de fútbol, o sea que pueda ser en modo conversacional
     o subiendo el PDF o la imagen del diploma"

## Esto NO guarda nada

Devuelve una ficha para que el estudiante la revise. Guardar sigue siendo del
endpoint de siempre, `POST /me/activities`, después de que él confirme.

Son dos pasos y no uno a propósito: el modelo lee bien la mayoría de las veces,
pero "la mayoría" no es suficiente cuando lo que se guarda va al perfil
consolidado, al Statement of Purpose y a la hoja de vida. Un dato mal leído que
entra solo reaparece meses después en un documento que el estudiante manda a
una universidad.

## El archivo no se archiva

Se lee y se descarta · decisión de AH. `STORAGE_BACKEND` está en `stub` en
producción y el stub guarda los blobs en memoria del proceso: prometer que el
diploma queda guardado y perderlo en el siguiente reinicio sería peor que no
ofrecerlo. Ver `logros_reader`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import logros_reader
from app.services.ai_usage_service import record_ai_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/logros", tags=["StudentMe · Logros"])

# Mismos límites que la subida de tests externos · es el mismo tipo de archivo
# y no tiene sentido que uno acepte lo que el otro rechaza.
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


def _rate_limit_lectura(request: Request):
    """Cada lectura es una llamada al modelo · se limita como las demás."""
    from app.core.rate_limiter import rate_limit

    s = get_settings()
    return rate_limit(s.rate_limit_external_test_upload)(request)


class TextoIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=12000)


class LogroLeidoOut(BaseModel):
    """La ficha PROPUESTA · el front la muestra para confirmar, no la guarda."""

    encontrado: bool
    categoria: Optional[str] = None
    nombre: Optional[str] = None
    rol: Optional[str] = None
    horas_semana: Optional[int] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    descripcion: Optional[str] = None
    logros: list[str] = []
    # 0-1 · el front avisa cuando es baja en vez de esconderlo.
    confianza: float = 0.0
    # Lo que falta por preguntar, en español y dirigido al estudiante.
    falta: list[str] = []


def _solo_estudiante(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )


def _registrar_uso(db: DBSession, user: User, usage: Optional[dict]) -> None:
    """Tracking M-001 · en su propio try: un fallo de auditoría no puede
    tumbar una lectura que ya salió bien."""
    if not usage:
        return
    try:
        record_ai_usage(
            db,
            provider="anthropic",
            model=usage.get("model") or "",
            feature=logros_reader.FEATURE,
            tokens_input=usage.get("tokens_input"),
            tokens_output=usage.get("tokens_output"),
            latency_ms=usage.get("latency_ms"),
            user_id=user.id,
        )
    except Exception:  # pragma: no cover · defensivo
        logger.exception("logros · no se pudo registrar el consumo de IA")


def _a_salida(ficha: logros_reader.LogroLeido) -> LogroLeidoOut:
    return LogroLeidoOut(
        encontrado=ficha.encontrado,
        categoria=ficha.categoria,
        nombre=ficha.nombre,
        rol=ficha.rol,
        horas_semana=ficha.horas_semana,
        fecha_inicio=ficha.fecha_inicio,
        fecha_fin=ficha.fecha_fin,
        descripcion=ficha.descripcion,
        logros=ficha.logros,
        confianza=ficha.confianza,
        falta=ficha.falta,
    )


@router.post(
    "/leer",
    response_model=LogroLeidoOut,
    summary="Lee un logro de lo que el estudiante escribió · NO lo guarda",
    dependencies=[Depends(_rate_limit_lectura)],
)
def leer_texto(
    payload: TextoIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiante(current_user)
    try:
        ficha = logros_reader.leer_de_texto(payload.texto)
    except logros_reader.LectorError as exc:
        # El mensaje del lector está escrito para mostrárselo a la persona.
        raise HTTPException(status_code=422, detail=str(exc))

    _registrar_uso(db, current_user, ficha.usage)
    return _a_salida(ficha)


@router.post(
    "/leer-archivo",
    response_model=LogroLeidoOut,
    summary="Lee un diploma (PDF o imagen) · NO guarda el archivo",
    dependencies=[Depends(_rate_limit_lectura)],
)
async def leer_archivo(
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiante(current_user)

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="sube un PDF o una foto (PNG, JPG o WEBP)",
        )

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="el archivo llegó vacío")
    if len(body) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"el archivo pesa más de {MAX_SIZE_BYTES // (1024 * 1024)}MB",
        )

    try:
        ficha = logros_reader.leer_de_archivo(
            file_bytes=body,
            content_type=content_type,
            filename=file.filename,
        )
    except logros_reader.LectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # `body` sale de ámbito aquí y no se escribió en ningún lado · a propósito.
    _registrar_uso(db, current_user, ficha.usage)
    return _a_salida(ficha)
