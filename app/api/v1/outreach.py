"""RM-1 · El disparador del acompañamiento periódico.

Verónica, 21-07: *"periódicamente él debe escribirte: hola, ¿cómo vas con tu
proyecto? ¿tomaste el curso de inglés?… él se vuelve tu amigo"*.

## Por qué un endpoint y no un worker

Heroku Scheduler le pega a una URL. Un proceso `worker` o `clock` en el
`Procfile` seria otro dyno pagado 24/7 para trabajar un minuto al día, y este
proyecto tiene un solo dyno Basic.

## Las tres capas de seguridad

1. `outreach_enabled` **apagado por defecto** · se puede desplegar y agendar el
   cron sin que salga un solo correo.
2. `outreach_cron_secret` · sin secreto configurado el endpoint responde 503.
   Es preferible que el cron falle a que quede una URL pública capaz de
   dispararle correos a toda la base.
3. `outreach_max_por_corrida` · tope por ejecución.

El preview (`/preview`) es para super_admin y **no manda nada**: sirve para
mostrarle a la clienta a quién se le escribiría y con qué texto antes de que
autorice prender el interruptor.
"""
from __future__ import annotations

import hmac
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import outreach_sender
from app.services.outreach_service import candidatos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outreach", tags=["outreach"])


class ResumenCorrida(BaseModel):
    revisados: int
    enviados: int
    sin_consentimiento: int
    fallidos: int
    apagado: bool


class LineaPreview(BaseModel):
    user_id: str
    email: str
    nombre: Optional[str] = None
    motivo: str
    asunto: str
    cuerpo: str
    es_plantilla: bool
    puede_recibir: bool
    motivo_bloqueo: Optional[str] = None


def _rate_limit_outreach(request: Request) -> None:
    """Tope por IP en los dos endpoints.

    En `/run` no reemplaza al secreto: lo complementa. Sin tope, un atacante
    puede probar secretos tan rápido como aguante el servidor; con él, el
    ataque por fuerza bruta deja de ser viable. `/preview` lo necesita por otra
    razón — llama al modelo por cada persona de la lista, así que un admin
    dándole a recargar cuesta tokens de verdad.
    """
    from app.core.rate_limiter import rate_limit

    return rate_limit(get_settings().rate_limit_outreach, scope="outreach")(request)


def _verificar_secreto(recibido: Optional[str]) -> None:
    settings = get_settings()
    if not settings.outreach_cron_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="outreach_cron_secret sin configurar · el disparador está cerrado.",
        )
    # `compare_digest` y no `==` · esto es un secreto compartido y la
    # comparación byte a byte con salida temprana es filtrable.
    if not recibido or not hmac.compare_digest(recibido, settings.outreach_cron_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secreto inválido.",
        )


@router.post(
    "/run",
    response_model=ResumenCorrida,
    summary="RM-1 · corrida del acompañamiento (Heroku Scheduler)",
    dependencies=[Depends(_rate_limit_outreach)],
)
def correr(
    db: DBSession = Depends(get_db),
    x_outreach_secret: Optional[str] = Header(default=None),
):
    """La corrida diaria. Idempotente por el tope de frecuencia de 14 días:
    llamarla dos veces el mismo día no manda nada dos veces."""
    _verificar_secreto(x_outreach_secret)
    settings = get_settings()

    lista = candidatos(db, limite=settings.outreach_max_por_corrida)
    conteo = {"enviados": 0, "sin_consentimiento": 0, "fallidos": 0}

    for usuario, motivo in lista:
        r = outreach_sender.enviar(db, usuario, motivo)
        if r.resultado == outreach_sender.ENVIADO:
            conteo["enviados"] += 1
        elif r.resultado == outreach_sender.SIN_CONSENTIMIENTO:
            conteo["sin_consentimiento"] += 1
        elif r.resultado == outreach_sender.FALLO_ENVIO:
            conteo["fallidos"] += 1

    logger.info(
        "RM-1 · corrida · revisados=%d enviados=%d sin_consentimiento=%d fallidos=%d apagado=%s",
        len(lista), conteo["enviados"], conteo["sin_consentimiento"],
        conteo["fallidos"], not settings.outreach_enabled,
    )

    return ResumenCorrida(
        revisados=len(lista),
        enviados=conteo["enviados"],
        sin_consentimiento=conteo["sin_consentimiento"],
        fallidos=conteo["fallidos"],
        apagado=not settings.outreach_enabled,
    )


@router.get(
    "/preview",
    response_model=List[LineaPreview],
    summary="RM-1 · a quién se le escribiría y qué · NO envía",
    dependencies=[Depends(_rate_limit_outreach)],
)
def preview(
    limite: int = 20,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Para mostrarle a la clienta qué saldría, antes de autorizar el envío.

    Redacta de verdad (llama al modelo) para que lo que se ve sea lo que se
    mandaría. Lo único que no hace es enviar.
    """
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · sólo super_admin.",
        )

    from app.services.consent_service import can_send_communications

    salida: List[LineaPreview] = []
    for usuario, motivo in candidatos(db, limite=min(limite, 50)):
        puede, bloqueo = can_send_communications(usuario)
        r = outreach_sender.enviar(db, usuario, motivo, simulacro=True)
        # Sin consentimiento el simulacro no redacta · se muestra la plantilla
        # para que igual se vea QUÉ se le diría si diera permiso.
        if r.mensaje is None:
            from app.services.outreach_writer import plantilla_de_respaldo

            mensaje = plantilla_de_respaldo(motivo)
        else:
            mensaje = r.mensaje
        salida.append(
            LineaPreview(
                user_id=str(usuario.id),
                email=usuario.email,
                nombre=usuario.name,
                motivo=motivo.clave,
                asunto=motivo.asunto,
                cuerpo=mensaje.cuerpo,
                es_plantilla=mensaje.es_plantilla,
                puede_recibir=puede,
                motivo_bloqueo=bloqueo,
            )
        )
    return salida
