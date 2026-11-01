"""El simulador de entrevista de admisión · E-4, Sprint 4 · `/me/entrevista`.

Ver `entrevista_service` para el porqué. Las dos rutas llevan la llave del plan
(`entrevista_admision`: pago, 11° y 12°); la devolución, que es la que llama a
la IA, además lleva límite de uso como el resto de las mini apps.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.api.v1.llave_plan import requiere
from app.core.rate_limiter import rate_limit
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import entrevista_service as svc
from app.services.ai_usage_service import record_ai_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/entrevista", tags=["StudentMe"])


def _solo_estudiante(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para estudiantes.")


@router.get("/preguntas", dependencies=[Depends(requiere("entrevista_admision"))])
def preguntas(
    idioma: str = Query(svc.IDIOMA_POR_DEFECTO),
    universidad: Optional[str] = Query(None, max_length=svc.MAX_UNIVERSIDAD),
    programa: Optional[str] = Query(None, max_length=svc.MAX_PROGRAMA),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiante(current_user)
    return {
        "idioma": svc.normalizar_idioma(idioma),
        "preguntas": svc.preguntas(idioma=idioma, universidad=universidad, programa=programa),
        "aviso": svc.AVISO,
    }


class Respuesta(BaseModel):
    pregunta_id: str = Field(max_length=40)
    respuesta: str = Field("", max_length=svc.MAX_RESPUESTA)


class DevolucionRequest(BaseModel):
    idioma: str = svc.IDIOMA_POR_DEFECTO
    universidad: Optional[str] = Field(None, max_length=svc.MAX_UNIVERSIDAD)
    programa: Optional[str] = Field(None, max_length=svc.MAX_PROGRAMA)
    respuestas: List[Respuesta] = Field(..., min_length=1, max_length=svc.PREGUNTAS_POR_ENTREVISTA)


@router.post(
    "/devolucion",
    dependencies=[
        Depends(rate_limit("4/minute", scope="entrevista")),
        Depends(requiere("entrevista_admision")),
    ],
)
def devolucion(
    payload: DevolucionRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _solo_estudiante(current_user)

    # El perfil que ya tenemos: la MISMA hoja de vida que usan la carta de
    # motivación y la postulación (`tools._cv_del_usuario`). Si no se puede
    # armar, la devolución sale igual, solo que sin sugerir qué de su perfil
    # contar: degrada, no revienta.
    perfil = "(no tenemos perfil todavía · no sugieras nada de él)"
    try:
        from app.api.v1.tools import _cv_del_usuario
        from app.services import cv_tailor_service

        perfil = cv_tailor_service.describir_cv(_cv_del_usuario(db, current_user))
    except Exception:  # noqa: BLE001
        logger.warning("entrevista · no se pudo armar el perfil de %s", current_user.id)

    try:
        resultado, meta = svc.devolucion(
            respuestas=[r.model_dump() for r in payload.respuestas],
            idioma=payload.idioma,
            universidad=payload.universidad,
            programa=payload.programa,
            perfil=perfil,
            session_id=str(current_user.id),
        )
    except svc.EntrevistaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    # M-001 · el consumo queda auditado. `provider` es obligatorio y
    # keyword-only (ver el CLAUDE.md del backend).
    try:
        record_ai_usage(
            db,
            provider="anthropic",
            user_id=current_user.id,
            feature="entrevista_admision",
            model=meta.get("model"),
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
        )
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo registrar el uso de IA de entrevista_admision")
    return resultado
