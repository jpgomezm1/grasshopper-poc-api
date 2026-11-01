"""Programas estatales y empresas: su personal solo ve datos agregados · F-2 / F-4, Sprint 4.

Un programa estatal (F-2) y una empresa (F-4) usan la misma maquinaria que un
colegio: licencia = plan pago, invitaciones, alta masiva por CSV, mensajes. Lo
que cambia es quién ve qué:

- En un **colegio**, la psicóloga y el administrador acompañan a cada
  estudiante, y por eso ven su detalle.
- En un **programa estatal**, la entidad pública recibe información de menores
  de edad a escala; en una **empresa**, RR. HH. recibe información de sus
  trabajadores. Ninguno de los dos necesita ver a una persona en particular
  para cumplir su función, y en ambos casos ver el detalle individual expone a
  la persona (Habeas Data, Ley 1581 de 2012). Ven el tablero agregado
  (`org_tablero`), con los grupos pequeños ocultos.

## Lista blanca, no lista negra

Para el personal de un programa o una empresa, todo lo que cuelga de estos
routers responde 403, salvo lo que está en `PERMITIDAS`. Así un endpoint
individual nuevo queda cerrado por defecto: olvidarse de bloquear algo sería
exponer datos; olvidarse de permitir algo es solo una pantalla que no carga.

No toca al super admin ni al equipo de Mentoring, ni a nada de un colegio.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import School, User, UserRole

TIPOS_SOLO_AGREGADO = ("programa", "empresa")

# (método, ruta) · la ruta es la plantilla de FastAPI, con el prefijo /api/v1.
PERMITIDAS = {
    ("GET", "/api/v1/school/me"),
    ("GET", "/api/v1/school/me/tablero"),
    ("POST", "/api/v1/school/me/logo"),
    ("PATCH", "/api/v1/school/me/branding"),
    ("GET", "/api/v1/school/me/invitations"),
    ("POST", "/api/v1/school/me/invitations"),
    ("DELETE", "/api/v1/school/me/invitations/{invitation_id}"),
    ("POST", "/api/v1/school/me/students/bulk-invite"),
    ("POST", "/api/v1/school/me/students/bulk-invite-csv"),
    ("GET", "/api/v1/school/me/mass-messages"),
    ("POST", "/api/v1/school/me/mass-messages"),
    ("GET", "/api/v1/school/me/events"),
    ("POST", "/api/v1/school/me/events"),
    ("PATCH", "/api/v1/school/me/events/{event_id}"),
    ("DELETE", "/api/v1/school/me/events/{event_id}"),
    ("GET", "/api/v1/school/me/legal-documents"),
    ("POST", "/api/v1/school/me/legal-documents"),
    ("POST", "/api/v1/school/me/license/upgrade-request"),
}

MENSAJE = (
    "En un programa o una empresa el panel muestra solo datos agregados, para "
    "proteger a cada participante. Mira el tablero."
)


def tipo_de(school: School | None) -> str:
    return (getattr(school, "tipo", None) or "colegio") if school else "colegio"


def solo_agregado(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Dependencia de router · 403 a lo individual si la organización no es un colegio."""
    if current_user.role not in (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST):
        return
    if not current_user.school_id:
        return
    school = db.query(School).filter(School.id == current_user.school_id).first()
    if tipo_de(school) not in TIPOS_SOLO_AGREGADO:
        return
    ruta = getattr(request.scope.get("route"), "path", request.url.path)
    if (request.method.upper(), ruta) in PERMITIDAS:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "solo_agregado", "message": MENSAJE},
    )
