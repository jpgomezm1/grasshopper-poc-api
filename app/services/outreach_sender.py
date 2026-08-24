"""RM-1 · Manda el mensaje, o registra por qué no salió.

Aquí es donde `consent_service.can_send_communications()` **por fin se llama
desde producción**: existía desde el 05-08 con sus tests, y ningún camino real
la consultaba. Ese era el trabajo a medias que RM-1 vino a cerrar.

## Todo se registra, incluido lo que no salió

Cada intento escribe una fila en `OutreachLog`, tanto si se entregó como si no.
Un log que sólo guarda los éxitos no sirve para auditar, y aquí hay menores de
edad: tiene que poder responderse "¿qué se le mandó a esta persona y con qué
permiso?" sin adivinar.

## El orden de las comprobaciones no es casual

1. Kill switch · si está apagado, no se toca ni el modelo (no se gastan tokens
   en mensajes que no van a salir).
2. Consentimiento · antes de redactar, por lo mismo.
3. Redacción.
4. Envío.

Un simulacro (`simulacro=True`) hace todo menos el paso 4.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.db.models import OutreachLog, User
from app.services.consent_service import can_send_communications
from app.services.outreach_service import Motivo
from app.services.outreach_writer import Mensaje, redactar

logger = logging.getLogger(__name__)

# Valores de OutreachLog.resultado
ENVIADO = "enviado"
SIN_CONSENTIMIENTO = "sin_consentimiento"
FALLO_ENVIO = "fallo_envio"
SIMULACRO = "simulacro"
APAGADO = "apagado"


@dataclass(frozen=True)
class Resultado:
    resultado: str
    detalle: Optional[str] = None
    mensaje: Optional[Mensaje] = None


def _html(nombre: Optional[str], mensaje: Mensaje, destino: str) -> str:
    """El correo · mismo lenguaje visual que `email_service._build_html_body`.

    Sin imágenes remotas ni tracking pixel: la mitad de los clientes de correo
    los bloquea y el otro medio los marca como promoción.
    """
    settings = get_settings()
    url = f"{settings.frontend_base_url.rstrip('/')}{destino}"
    saludo = f"Hola {nombre.split(' ')[0]}" if nombre else "Hola"
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/></head>
<body style="font-family:Lato,Segoe UI,Helvetica,Arial,sans-serif;background:#F9F5E9;padding:32px;color:#1D1D1B;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #E2DDD0;border-radius:12px;padding:32px;">
    <p style="margin:0 0 20px 0;font-size:20px;font-weight:700;letter-spacing:-0.02em;color:#EE7238;">Mentoring</p>
    <p style="margin:0 0 16px 0;font-size:16px;">{saludo},</p>
    <p style="margin:0 0 24px 0;font-size:15px;line-height:1.6;">{mensaje.cuerpo}</p>
    <p style="margin:0 0 28px 0;">
      <a href="{url}" style="background:#EE7238;color:#1D1D1B;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:600;font-size:14px;display:inline-block;">{mensaje.cta}</a>
    </p>
    <p style="margin:0;color:#6B675E;font-size:12px;line-height:1.5;">
      Recibes este mensaje porque aceptaste que te acompañemos en tu proceso.
      Puedes dejar de recibirlos cuando quieras desde
      <a href="{settings.frontend_base_url.rstrip('/')}/preferencias" style="color:#B24310;">tus preferencias</a>.
    </p>
  </div>
</body>
</html>"""


def _registrar(
    db: DBSession,
    user: User,
    motivo: Motivo,
    resultado: str,
    *,
    canal: str = "email",
    mensaje: Optional[Mensaje] = None,
    detalle: Optional[str] = None,
) -> OutreachLog:
    fila = OutreachLog(
        user_id=user.id,
        motivo=motivo.clave,
        canal=canal,
        resultado=resultado,
        asunto=motivo.asunto,
        cuerpo=mensaje.cuerpo if mensaje else None,
        es_plantilla=mensaje.es_plantilla if mensaje else None,
        detalle=detalle,
    )
    db.add(fila)
    db.commit()
    return fila


def enviar(
    db: DBSession,
    user: User,
    motivo: Motivo,
    *,
    simulacro: bool = False,
) -> Resultado:
    """Manda el acompañamiento a una persona · nunca lanza.

    Un fallo con un destinatario no puede tumbar la corrida entera: son cientos
    de personas y un correo rebotado es normal.
    """
    settings = get_settings()

    # 1 · Kill switch. Antes que nada, para no gastar tokens en algo que no sale.
    if not simulacro and not settings.outreach_enabled:
        _registrar(db, user, motivo, APAGADO, detalle="outreach_enabled=false")
        return Resultado(APAGADO, "El envío está apagado por configuración")

    # 2 · Consentimiento · el gate que llevaba desde el 05-08 sin que nadie lo
    # llamara. Cubre menores sin consentimiento parental (fail-closed: sin fecha
    # de nacimiento se asume menor).
    puede, motivo_no = can_send_communications(user)
    if not puede:
        _registrar(db, user, motivo, SIN_CONSENTIMIENTO, detalle=motivo_no)
        return Resultado(SIN_CONSENTIMIENTO, motivo_no)

    # 3 · Redacción · cae en plantilla determinista si el modelo falla.
    mensaje = redactar(motivo, nombre=user.name, user_id=str(user.id), db=db)

    if simulacro:
        _registrar(db, user, motivo, SIMULACRO, mensaje=mensaje)
        return Resultado(SIMULACRO, mensaje=mensaje)

    # 4 · Envío. El aviso en la app es best-effort: que falle no invalida el
    # correo, que es el canal que trae de vuelta a quien no ha entrado.
    try:
        from app.services.email_service import send_email

        envio = send_email(
            to=user.email,
            subject=motivo.asunto,
            html_body=_html(user.name, mensaje, motivo.destino),
            text_body=f"{mensaje.cuerpo}\n\n{mensaje.cta}: "
            f"{get_settings().frontend_base_url.rstrip('/')}{motivo.destino}",
        )
    except Exception as exc:  # pragma: no cover · defensivo
        _registrar(db, user, motivo, FALLO_ENVIO, mensaje=mensaje, detalle=str(exc)[:255])
        return Resultado(FALLO_ENVIO, str(exc))

    if not envio.delivered:
        _registrar(
            db, user, motivo, FALLO_ENVIO, mensaje=mensaje, detalle=envio.reason
        )
        return Resultado(FALLO_ENVIO, envio.reason)

    try:
        from app.services.notifications_service import create_notification

        create_notification(
            db,
            user_id=user.id,
            type="outreach.nudge",
            title=motivo.asunto,
            body=mensaje.cuerpo,
            data={"href": motivo.destino, "motivo": motivo.clave},
        )
    except Exception as exc:  # pragma: no cover · best-effort
        logger.warning("RM-1 · aviso in-app falló · %s", exc)

    _registrar(db, user, motivo, ENVIADO, mensaje=mensaje)
    return Resultado(ENVIADO, mensaje=mensaje)
