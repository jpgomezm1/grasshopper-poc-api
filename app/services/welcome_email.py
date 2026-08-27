"""Correo de bienvenida · lo primero que recibe alguien que se registra.

Hasta ahora no se mandaba **ninguno**: una persona se registraba en una
plataforma de orientación con su correo y no recibía nada. Ni confirmación, ni
qué sigue, ni de dónde viene el mensaje si luego le llegaba otro.

## Por qué el HTML se escribe aquí y no en una plantilla

`app/templates/` existe para lo que imprime WeasyPrint (el PDF clínico y el
reporte). Un correo es otro medio: los clientes de correo no soportan CSS
moderno —nada de flex, grid ni variables— así que el estilo va en línea y las
reglas de composición son otras. Mezclarlo con las plantillas de PDF haría que
un cambio pensado para papel rompa la bandeja de entrada, o al revés.

Los colores salen de `brand.py`, que sigue siendo la fuente única.

## Lo que este correo NO hace

No promete nada, no mete oferta y no pide que respondas. Es un acuse de recibo
con el siguiente paso — el brandbook prohíbe prometer cupos, becas o fechas, y
un correo de bienvenida es justo donde más tienta hacerlo.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.db.models import User
from app.services import brand, email_service

logger = logging.getLogger(__name__)

ASUNTO = "Bienvenido a Mentoring"


def _primer_nombre(user: User) -> Optional[str]:
    """El primer nombre, o None si no lo dio.

    El nombre es opcional en el registro, así que el saludo tiene que
    funcionar sin él: "Hola" a secas antes que "Hola None".
    """
    nombre = (getattr(user, "name", None) or "").strip()
    if not nombre:
        return None
    return nombre.split()[0]


def construir_html(user: User) -> str:
    """El cuerpo del correo · estilo en línea, sin CSS moderno."""
    nombre = _primer_nombre(user)
    saludo = f"Hola, {nombre}." if nombre else "Hola."

    return f"""\
<div style="margin:0;padding:32px 16px;background:{brand.CREMA};
            font-family:Lato,Helvetica,Arial,sans-serif;color:{brand.TINTA};">
  <div style="max-width:520px;margin:0 auto;background:{brand.BLANCO};
              border:1px solid {brand.BORDE};border-radius:12px;padding:32px;">

    <p style="margin:0 0 4px;font-size:12px;letter-spacing:1.6px;
              text-transform:uppercase;color:{brand.NARANJA_HONDO};
              font-weight:700;">Mentoring</p>

    <h1 style="margin:0 0 16px;font-size:24px;line-height:1.25;
               color:{brand.TINTA};font-weight:700;">{saludo}</h1>

    <p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:{brand.TINTA};">
      Soy Mento, y voy a acompañarte en esto. Tu cuenta ya está creada.
    </p>

    <p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:{brand.TINTA};">
      Lo que sigue es una conversación para conocerte: qué te mueve, qué se te
      da bien y qué te preocupa. No hay respuestas correctas y no tienes que
      hacerlo de una sola vez — puedes salir y retomar cuando quieras.
    </p>

    <p style="margin:0 0 28px;font-size:16px;line-height:1.6;color:{brand.GRIS};">
      Con eso puedo mostrarte caminos que tengan sentido para ti, en vez de una
      lista igual para todo el mundo.
    </p>

    <a href="https://grasshopper-app.netlify.app/home"
       style="display:inline-block;background:{brand.NARANJA};
              color:{brand.SOBRE_NARANJA};text-decoration:none;font-weight:700;
              font-size:16px;padding:14px 26px;border-radius:999px;">
      Continuar donde quedaste
    </a>

    <p style="margin:28px 0 0;padding-top:20px;border-top:1px solid {brand.BORDE};
              font-size:13px;line-height:1.6;color:{brand.GRIS};">
      Recibes este correo porque creaste una cuenta en Mentoring. Puedes
      cambiar tus preferencias de comunicación desde tu perfil.
    </p>
  </div>
</div>"""


def construir_texto(user: User) -> str:
    """Versión en texto plano · algunos clientes no muestran HTML, y sin ella
    el correo puntúa peor en los filtros de spam."""
    nombre = _primer_nombre(user)
    saludo = f"Hola, {nombre}." if nombre else "Hola."
    return (
        f"{saludo}\n\n"
        "Soy Mento, y voy a acompañarte en esto. Tu cuenta ya está creada.\n\n"
        "Lo que sigue es una conversación para conocerte: qué te mueve, qué se "
        "te da bien y qué te preocupa. No hay respuestas correctas y no tienes "
        "que hacerlo de una sola vez.\n\n"
        "Continúa aquí: https://grasshopper-app.netlify.app/home\n\n"
        "Recibes este correo porque creaste una cuenta en Mentoring."
    )


def enviar_bienvenida(user: User) -> bool:
    """Manda el correo. Devuelve si salió, sin levantar nunca.

    Un fallo aquí NO puede tumbar el registro: la cuenta ya existe y la persona
    tiene que poder entrar aunque el proveedor de correo esté caído. Por eso
    devuelve un booleano y deja rastro en el log en vez de propagar.
    """
    correo = (getattr(user, "email", None) or "").strip()
    if not correo:
        return False
    try:
        r = email_service.get_backend().send_html(
            to=correo,
            subject=ASUNTO,
            html=construir_html(user),
            text=construir_texto(user),
        )
        # El resultado del servicio se llama `delivered`, no `ok`.
        ok = bool(getattr(r, "delivered", False))
        if not ok:
            logger.warning(
                "welcome_email · el proveedor rechazó el envío",
                extra={"user_id": str(user.id)},
            )
        return ok
    except Exception:
        logger.exception(
            "welcome_email · fallo enviando la bienvenida",
            extra={"user_id": str(user.id)},
        )
        return False
