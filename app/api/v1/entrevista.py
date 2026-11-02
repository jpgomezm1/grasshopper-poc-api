"""El simulador de entrevista de admisión · E-4, Sprint 4 · `/me/entrevista`.

Ver `entrevista_service` para el porqué. Las dos rutas llevan la llave del plan
(`entrevista_admision`: pago, 11° y 12°); la devolución, que es la que llama a
la IA, además lleva límite de uso como el resto de las mini apps.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
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


# ---------------------------------------------------------------------------
# La devolución en segundo plano · verificación en producción, 2026-11-02
# ---------------------------------------------------------------------------
# Con cinco respuestas de verdad, la devolución tarda más de 30 s (una sola
# llamada a la IA que escribe tres cosas por respuesta más el resumen) y el
# router de Heroku corta la petición a los 30 s (H12): la persona terminaba la
# entrevista y veía "Hopper no pudo revisar tu entrevista", aunque no había
# fallado nada más que la espera. Es el mismo problema que tuvo el análisis de
# brecha (`career_gap.analizar_en_segundo_plano`) y la misma solución: esta
# ruta responde de inmediato (202), el trabajo sigue después de responder y la
# pantalla consulta `GET /devolucion` hasta que el estado sea "listo".
#
# Se guarda la ÚLTIMA devolución en `onboarding_answers` (no hay tabla de
# entrevistas: la práctica no se archiva, decisión de E-4). `POST /devolucion`
# sigue igual para no romper a quien la llame.

CLAVE = "entrevista_devolucion"
ESTADO_EN_CURSO = "en_curso"
ESTADO_LISTO = "listo"
ESTADO_FALLIDO = "fallido"
# Si un trabajo quedó "en curso" más que esto (el dyno se reinició), se permite otro.
VENCE_EN_CURSO_S = 300
ERROR_GENERICO = "Hopper no pudo revisar tu entrevista en este momento. Intenta de nuevo en un rato."


def _guardar_estado(db: DBSession, user: User, estado: Dict[str, Any]) -> None:
    """Nuevo dict siempre: `onboarding_answers` es JSON sin MutableDict, y mutar
    el mismo objeto no dispara el UPDATE (ver `career_gap._guardar`)."""
    user.onboarding_answers = {**(user.onboarding_answers or {}), CLAVE: estado}
    db.commit()


def _perfil_de(db: DBSession, user: User) -> str:
    try:
        from app.api.v1.tools import _cv_del_usuario
        from app.services import cv_tailor_service

        return cv_tailor_service.describir_cv(_cv_del_usuario(db, user))
    except Exception:  # noqa: BLE001
        logger.warning("entrevista · no se pudo armar el perfil de %s", user.id)
        return "(no tenemos perfil todavía · no sugieras nada de él)"


def _trabajo_de_devolucion(user_id: Any, datos: Dict[str, Any]) -> None:
    """La devolución, fuera de la petición · con su propia sesión de base."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return
        try:
            resultado, meta = svc.devolucion(**datos, perfil=_perfil_de(db, user), session_id=str(user.id))
            _guardar_estado(db, user, {
                "estado": ESTADO_LISTO,
                "resultado": resultado,
                "generada_en": datetime.now(timezone.utc).isoformat(),
            })
            try:
                record_ai_usage(
                    db,
                    provider="anthropic",
                    user_id=user.id,
                    feature="entrevista_admision",
                    model=meta.get("model"),
                    tokens_input=meta.get("tokens_input"),
                    tokens_output=meta.get("tokens_output"),
                    latency_ms=meta.get("latency_ms"),
                )
            except Exception:  # noqa: BLE001
                logger.warning("No se pudo registrar el uso de IA de entrevista_admision")
        except Exception as exc:  # noqa: BLE001 · se reporta en el estado, no se pierde
            logger.warning("Devolución de entrevista en segundo plano falló", exc_info=True)
            db.rollback()
            _guardar_estado(db, user, {
                "estado": ESTADO_FALLIDO,
                "error": str(exc) if isinstance(exc, svc.EntrevistaError) else ERROR_GENERICO,
            })
    finally:
        db.close()


@router.post(
    "/devolucion-en-segundo-plano",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(rate_limit("4/minute", scope="entrevista")),
        Depends(requiere("entrevista_admision")),
    ],
)
def devolucion_en_segundo_plano(
    payload: DevolucionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _solo_estudiante(current_user)
    # Se valida ANTES de lanzar el trabajo: sin ninguna respuesta no hay qué
    # revisar, y es mejor decirlo ya que dejarla esperando un "fallido".
    if not any((r.respuesta or "").strip() for r in payload.respuestas):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Responde al menos una pregunta para que Hopper te dé su devolución.",
        )

    actual = (current_user.onboarding_answers or {}).get(CLAVE) or {}
    if actual.get("estado") == ESTADO_EN_CURSO:
        try:
            edad = (datetime.now(timezone.utc) - datetime.fromisoformat(actual.get("iniciada_en"))).total_seconds()
        except (TypeError, ValueError):
            edad = VENCE_EN_CURSO_S + 1
        if edad < VENCE_EN_CURSO_S:
            return {"estado": ESTADO_EN_CURSO}

    _guardar_estado(db, current_user, {
        "estado": ESTADO_EN_CURSO,
        "iniciada_en": datetime.now(timezone.utc).isoformat(),
    })
    background_tasks.add_task(_trabajo_de_devolucion, current_user.id, {
        "respuestas": [r.model_dump() for r in payload.respuestas],
        "idioma": payload.idioma,
        "universidad": payload.universidad,
        "programa": payload.programa,
    })
    return {"estado": ESTADO_EN_CURSO}


@router.get("/devolucion", dependencies=[Depends(requiere("entrevista_admision"))])
def estado_de_la_devolucion(current_user: User = Depends(get_current_user)):
    """El estado de la última devolución: `en_curso`, `listo` (con `resultado`) o `fallido` (con `error`)."""
    _solo_estudiante(current_user)
    return (current_user.onboarding_answers or {}).get(CLAVE) or {"estado": None}
