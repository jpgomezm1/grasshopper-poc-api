"""Avisos al equipo comercial · G-4, Sprint 4.

Un prospecto caliente que nadie ve en el día se enfría. Antes no había aviso:
el equipo se enteraba abriendo la bandeja (que además no estaba en el menú).

- **Caliente** (banda `hot`): aviso inmediato, dentro de la app a cada
  comercial activo y por correo. **Una sola vez** por prospecto: el perfilador
  recalcula el puntaje en cada turno y sin la marca `_aviso_caliente` mandaría
  un correo por mensaje.
- **Tibios**: un resumen diario (`scripts/resumen_prospectos_tibios.py`, para
  Heroku Scheduler; sin activar hasta que JP lo pida).

## A quién (decidido por JP el 2026-10-31)

Si `AVISO_PROSPECTOS_EMAIL` está configurada (una o varias direcciones separadas
por coma), el correo va ahí. Si no, a cada usuario con rol comercial activo. La
notificación dentro de la app va siempre a los comerciales.

Sin `RESEND_API_KEY` el correo no sale (`email_service` lo registra en stub) y la
notificación de la app sí: el aviso no depende del proveedor de correo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from html import escape
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.db.models import BotConversation, User, UserRole

logger = logging.getLogger(__name__)

MARCA_AVISADO = "_aviso_caliente"


def _comerciales(db: DBSession) -> List[User]:
    return (
        db.query(User)
        .filter(User.role == UserRole.GH_COMMERCIAL, User.is_active.is_(True))
        .all()
    )


def destinatarios(db: DBSession) -> List[str]:
    fijo = (get_settings().aviso_prospectos_email or "").strip()
    if fijo:
        return [c.strip() for c in fijo.split(",") if "@" in c]
    return [u.email for u in _comerciales(db) if u.email]


def _enlace() -> str:
    return f"{get_settings().frontend_base_url.rstrip('/')}/gh/prospectos"


def _correo_caliente(p) -> tuple[str, str, str]:
    """(asunto, html, texto) · con lo que el asesor necesita antes de llamar."""
    quien = " · ".join(x for x in (p.quien, p.etapa) if x)
    filas = [
        ("Contacto", " · ".join(x for x in (p.email, p.telefono) if x) or "sin datos"),
        ("Quién", quien or None),
        ("Destino", p.destino),
        ("Presupuesto", p.presupuesto),
        ("Cuándo empieza", p.cuando),
    ]
    filas = [(k, v) for k, v in filas if v]
    asunto = f"Prospecto caliente: {p.nombre or 'sin nombre'}"
    html = (
        f"<p><strong>{escape(p.nombre or 'Sin nombre')}</strong> acaba de entrar como "
        f"prospecto caliente (puntaje {p.puntaje}).</p><ul>"
        + "".join(f"<li><strong>{escape(k)}:</strong> {escape(str(v))}</li>" for k, v in filas)
        + "</ul>"
        + (
            "<p><strong>Por qué:</strong></p><ul>"
            + "".join(f"<li>{escape(m)}</li>" for m in p.porque)
            + "</ul>"
            if p.porque else ""
        )
        + f'<p><a href="{_enlace()}">Verlo en Prospectos</a></p>'
    )
    texto = "\n".join(
        [f"{p.nombre or 'Sin nombre'} acaba de entrar como prospecto caliente (puntaje {p.puntaje})."]
        + [f"{k}: {v}" for k, v in filas]
        + ([f"Por qué: {' · '.join(p.porque)}"] if p.porque else [])
        + [f"Verlo en Prospectos: {_enlace()}"]
    )
    return asunto, html, texto


def avisar_caliente(db: DBSession, lead: BotConversation) -> bool:
    """Avisa de un prospecto caliente, una sola vez. Devuelve True si avisó.

    **Nunca lanza**: un aviso que falla no puede romper el envío del bot.
    """
    from app.services import prospectos_service
    from app.services.email_service import send_email
    from app.services.notifications_service import create_notification

    try:
        hechos = dict(lead.hechos or {})
        if lead.band != "hot" or hechos.get(MARCA_AVISADO):
            return False
        # La marca va ANTES de enviar: si el correo tarda o falla, un segundo
        # turno del perfilador no debe mandar otro.
        hechos[MARCA_AVISADO] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        lead.hechos = hechos
        db.commit()

        p = prospectos_service._desde_bot(lead)
        for u in _comerciales(db):
            create_notification(
                db,
                user_id=u.id,
                type="prospecto.caliente",
                title=f"Prospecto caliente: {p.nombre or 'sin nombre'}",
                body=" · ".join(x for x in (p.quien, p.etapa, p.cuando) if x) or None,
                data={"fuente": p.fuente, "id": p.id, "ruta": "/gh/prospectos"},
                commit=False,
            )
        db.commit()

        asunto, html, texto = _correo_caliente(p)
        for correo in destinatarios(db):
            send_email(to=correo, subject=asunto, html_body=html, text_body=texto)
        return True
    except Exception:  # noqa: BLE001 · el aviso es best-effort
        logger.exception("No se pudo avisar del prospecto caliente %s", getattr(lead, "id", None))
        db.rollback()
        return False


def avisar_caliente_en_segundo_plano(lead_id: UUID) -> None:
    """Para `BackgroundTasks`: abre su propia sesión (la del request ya cerró).

    Se lee `SessionLocal` del módulo en el momento de llamar, no al importar,
    para que los tests que sustituyen la base la usen (ver `cv.py`).
    """
    from app.db import database as dbmod

    db = dbmod.SessionLocal()
    try:
        lead = db.query(BotConversation).filter(BotConversation.id == lead_id).first()
        if lead is not None:
            avisar_caliente(db, lead)
    finally:
        db.close()


def resumen_tibios(db: DBSession, *, ahora: Optional[datetime] = None) -> int:
    """El resumen diario de los tibios de las últimas 24 horas. Devuelve cuántos.

    No se manda nada si no hubo tibios: un correo diario que dice "nada" se
    aprende a ignorar, y entonces también se ignora el día que sí trae algo.
    """
    from app.services import prospectos_service
    from app.services.email_service import send_email

    ahora = ahora or datetime.utcnow()
    tibios = prospectos_service.listar(db, banda="warm", desde=ahora - timedelta(days=1), hasta=ahora)
    tibios = [p for p in tibios if p.estado == "nuevo"]
    if not tibios:
        return 0
    asunto = f"{len(tibios)} prospecto(s) tibio(s) en las últimas 24 horas"
    lineas = [
        f"{p.nombre or 'Sin nombre'} · {' · '.join(x for x in (p.quien, p.etapa) if x) or p.fuente} · "
        f"{' · '.join(x for x in (p.email, p.telefono) if x) or 'sin contacto'}"
        for p in tibios
    ]
    html = (
        f"<p>{escape(asunto)}. Ruta sugerida: ofrecerles el perfilamiento.</p><ul>"
        + "".join(f"<li>{escape(l)}</li>" for l in lineas)
        + f'</ul><p><a href="{_enlace()}">Verlos en Prospectos</a></p>'
    )
    texto = "\n".join([asunto + ".", *lineas, f"Verlos en Prospectos: {_enlace()}"])
    for correo in destinatarios(db):
        send_email(to=correo, subject=asunto, html_body=html, text_body=texto)
    return len(tibios)
