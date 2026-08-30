"""Onboarding conversacional (`/v1/onboarding-chat`).

Reemplaza los 14 pasos del formulario por una conversación. Lo que **no** cambia
es lo que queda guardado: cada turno persiste en `User.onboarding_answers` con
las mismas claves y los mismos códigos que producía el formulario, así que el
recomendador, el gate de menores y los prompts de IA no se enteran.

Dos decisiones de esta capa:

**Se guarda en cada turno, no al final.** Una conversación de ocho mensajes que
se pierde porque se cerró la pestaña es peor que un formulario: al menos el
formulario guardaba paso a paso. Si la persona vuelve, retoma donde iba.

**El historial vive en el cliente.** No hay tabla de conversación aquí — lo que
importa persistir son los hechos, no la charla. `bot_conversations` existe para
el perfilador comercial porque ahí la conversación **es** el lead y se audita;
aquí el valor está en el perfil resultante.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import _sync_onboarding_to_user_columns, get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services import onboarding_conversacional as conv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding-chat", tags=["Onboarding"])


class Turno(BaseModel):
    role: str
    content: str


class TurnoRequest(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=4000)
    historial: List[Turno] = Field(default_factory=list)


class TurnoResponse(BaseModel):
    respuesta: str
    # Lo que se sabe hasta ahora · el front lo muestra como un resumen vivo para
    # que la persona vea que la conversación va a algún lado y pueda corregir.
    recolectado: Dict[str, Any]
    faltan: int
    listo: bool


class InicioResponse(BaseModel):
    respuesta: str
    recolectado: Dict[str, Any]
    listo: bool


def _hechos_del_usuario(user: User) -> Dict[str, Any]:
    """Los hechos ya conocidos, leídos de `onboarding_answers`.

    Se reconstruyen desde ahí y no de una tabla propia para que la conversación
    pueda **retomar lo que dejó el formulario**: quien ya había avanzado por la
    pantalla vieja no vuelve a empezar.
    """
    from app.data import onboarding_hechos as cat

    guardado = user.onboarding_answers or {}
    fuera: Dict[str, Any] = {}
    for h in cat.HECHOS:
        if not h.onboarding_key:
            continue
        v = guardado.get(h.onboarding_key)
        if v in (None, "", [], {}):
            continue
        # `birthdate` se guarda como YYYY-12-31 y el catálogo lo maneja como año.
        if h.id == "birthdate" and isinstance(v, str) and len(v) >= 4:
            try:
                v = int(v[:4])
            except ValueError:
                continue
        fuera[h.id] = v
    return fuera


def _persistir(db: DBSession, user: User, recolectados: Dict[str, Any]) -> None:
    """Guarda con el mismo contrato que `PUT /me/onboarding`.

    Se reusa `_sync_onboarding_to_user_columns` en vez de reimplementarlo: es lo
    que copia presupuesto y países a las columnas que el recomendador realmente
    lee, y ese bug —preguntar y no usarlo— ya se cometió una vez (P1-3).
    """
    nuevas = conv.a_onboarding_answers(recolectados)
    if not nuevas:
        return
    # Dict NUEVO · mutar en sitio una columna JSON no lo detecta SQLAlchemy y
    # sólo persistiría el primer campo. Ya pasó en el formulario.
    user.onboarding_answers = {**(user.onboarding_answers or {}), **nuevas}

    # El gate de menores: sólo la PRIMERA vez. Permitir cambiarla después dejaría
    # a un menor bloqueado "volverse mayor" contando otra cosa en el chat.
    bd = nuevas.get("birthdate")
    if user.birthdate is None and isinstance(bd, str):
        from datetime import datetime
        try:
            user.birthdate = datetime.strptime(bd[:10], "%Y-%m-%d").date()
        except ValueError:
            pass

    # `db` para que el cambio de grado deje su foto del año saliente ·
    # ver `year_memory_service.guardar_snapshot_saliente`.
    _sync_onboarding_to_user_columns(user, user.onboarding_answers, db)
    db.commit()


@router.get("/inicio", response_model=InicioResponse)
def inicio(
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """El primer mensaje, y lo que ya sabemos de esta persona."""
    from app.data import onboarding_hechos as cat

    hechos = _hechos_del_usuario(user)
    return InicioResponse(
        respuesta=conv.primer_mensaje(),
        recolectado=hechos,
        listo=cat.listo_para_cerrar(hechos),
    )


@router.post("/turno", response_model=TurnoResponse)
def turno(
    req: TurnoRequest,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Un turno de la conversación · extrae, responde y guarda."""
    from app.data import onboarding_hechos as cat

    previos = _hechos_del_usuario(user)
    respuesta, actualizados, listo = conv.responder(
        req.mensaje,
        [t.model_dump() for t in req.historial],
        previos,
        session_id=str(user.id),
        db=db,
    )

    # Se guarda aunque la respuesta del modelo haya fallado: lo que la persona
    # dijo ya lo dijo, y perderlo la obliga a repetirse.
    try:
        _persistir(db, user, actualizados)
    except Exception:  # pragma: no cover · guardar no puede tumbar el turno
        logger.warning("no se pudo persistir el onboarding conversacional",
                       exc_info=True, extra={"user_id": str(user.id)})
        db.rollback()

    return TurnoResponse(
        respuesta=respuesta,
        recolectado=actualizados,
        faltan=len(cat.faltantes(actualizados)),
        listo=listo,
    )
