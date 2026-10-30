"""El panel de planes de la agencia · activar, renovar o bajar el plan de un estudiante (D-5).

Sin pasarela de pago (decisión D2): la agencia cobra por fuera y activa aquí.
Cada activación agrega una fila a `user_plans` (nunca edita), con quién lo hizo
y cómo pagó, y queda en la auditoría (`audit_logs`).

## Quién puede

- **Ver** (lista, detalle, solicitudes): equipo comercial, orientadores y super admin.
- **Activar**: solo equipo comercial y super admin. Un orientador ve el plan
  para saber qué tiene el estudiante, pero cobrar no es su trabajo.
- Un estudiante nunca entra aquí (no puede activarse a sí mismo).

## Las solicitudes de "Quiero activarlo"

El muro de pago (D-4) las crea con la solicitud de contacto que ya existía
(`users.gh_contact_*`), con un mensaje que empieza por "Quiero activar el
plan". Este panel las lista arriba y, al activar el plan, la marca `converted`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserPlan, UserRole
from app.services import plan_service
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/planes", tags=["Admin · Planes"])

ROLES_QUE_VEN = (UserRole.GH_COMMERCIAL, UserRole.GH_ADVISOR, UserRole.SUPER_ADMIN)
ROLES_QUE_ACTIVAN = (UserRole.GH_COMMERCIAL, UserRole.SUPER_ADMIN)
PREFIJO_SOLICITUD = "Quiero activar el plan"
# Duración por defecto de un plan, del demo: 12 meses; 6 para profesional.
MESES_POR_DEFECTO = 12
MESES_PROFESIONAL = 6


def _ver(user: User) -> None:
    if user.role not in ROLES_QUE_VEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el equipo de Mentoring.")


def _activar(user: User) -> None:
    if user.role not in ROLES_QUE_ACTIVAN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Activar planes es del equipo comercial o de un administrador.",
        )


def _solicitud_pendiente(u: User) -> Optional[str]:
    mensaje = u.gh_contact_message or ""
    if u.gh_contact_status == "pending" and mensaje.startswith(PREFIJO_SOLICITUD):
        return mensaje
    return None


class PlanFila(BaseModel):
    id: UUID
    plan: str
    desde: datetime
    hasta: Optional[datetime]
    metodo: Optional[str]
    notas: Optional[str]
    activado_por: Optional[str]
    creado_en: datetime


class EstudiantePlan(BaseModel):
    user_id: UUID
    nombre: Optional[str]
    email: str
    plan: str
    origen: str
    hasta: Optional[datetime]
    # Días que le quedan al plan propio · None si no vence o no es propio.
    vence_en_dias: Optional[int]
    solicitud: Optional[str]
    solicitud_en: Optional[datetime]


class EstudianteDetalle(EstudiantePlan):
    historial: List[PlanFila]


class ActivarRequest(BaseModel):
    plan: str = Field(pattern=r"^(gratis|pago|vip)$")
    desde: Optional[datetime] = None
    # Si no se dice, 12 meses (6 para profesional). `sin_vencimiento` lo anula.
    hasta: Optional[datetime] = None
    sin_vencimiento: bool = False
    metodo: Optional[str] = Field(default=None, max_length=120)
    notas: Optional[str] = Field(default=None, max_length=2000)


def _fila(db: DBSession, u: User, ahora: datetime) -> EstudiantePlan:
    p = plan_service.plan_vigente(db, u, ahora)
    vence = None
    if p.origen == "propio" and p.hasta is not None:
        vence = max(0, (p.hasta - ahora).days)
    return EstudiantePlan(
        user_id=u.id,
        nombre=u.name,
        email=u.email,
        plan=p.plan,
        origen=p.origen,
        hasta=p.hasta,
        vence_en_dias=vence,
        solicitud=_solicitud_pendiente(u),
        solicitud_en=u.gh_contact_requested_at if _solicitud_pendiente(u) else None,
    )


def _estudiante_o_404(db: DBSession, user_id: UUID) -> User:
    u = db.query(User).filter(User.id == user_id, User.role == UserRole.STUDENT).first()
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estudiante no encontrado.")
    return u


@router.get("", response_model=List[EstudiantePlan])
def listar(
    q: Optional[str] = Query(None, max_length=120, description="correo o nombre"),
    solo_solicitudes: bool = Query(False),
    vencen_en_dias: Optional[int] = Query(None, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[EstudiantePlan]:
    """Estudiantes con su plan · las solicitudes de "Quiero activarlo" primero."""
    _ver(current_user)
    ahora = datetime.utcnow()
    consulta = db.query(User).filter(User.role == UserRole.STUDENT)
    if q:
        patron = f"%{q.strip().lower()}%"
        consulta = consulta.filter(or_(User.email.ilike(patron), User.name.ilike(patron)))
    if solo_solicitudes:
        consulta = consulta.filter(
            User.gh_contact_status == "pending",
            User.gh_contact_message.like(f"{PREFIJO_SOLICITUD}%"),
        )
    filas = [_fila(db, u, ahora) for u in consulta.order_by(User.created_at.desc()).limit(limit * 3).all()]
    if vencen_en_dias is not None:
        filas = [f for f in filas if f.vence_en_dias is not None and f.vence_en_dias <= vencen_en_dias]
    # Dos ordenamientos estables: la solicitud más reciente primero y, encima,
    # las que tienen solicitud antes que las que no. (`datetime.min.timestamp()`
    # revienta en Windows, por eso no se convierte a número.)
    filas.sort(key=lambda f: f.solicitud_en or datetime.min, reverse=True)
    filas.sort(key=lambda f: f.solicitud is None)
    return filas[:limit]


@router.get("/{user_id}", response_model=EstudianteDetalle)
def detalle(
    user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EstudianteDetalle:
    _ver(current_user)
    u = _estudiante_o_404(db, user_id)
    filas = (
        db.query(UserPlan)
        .filter(UserPlan.user_id == u.id)
        .order_by(UserPlan.creado_en.desc())
        .all()
    )
    quienes = {
        x.id: (x.name or x.email)
        for x in db.query(User).filter(User.id.in_({f.activado_por_id for f in filas if f.activado_por_id})).all()
    } if any(f.activado_por_id for f in filas) else {}
    base = _fila(db, u, datetime.utcnow())
    return EstudianteDetalle(
        **base.model_dump(),
        historial=[
            PlanFila(
                id=f.id, plan=f.plan, desde=f.desde, hasta=f.hasta, metodo=f.metodo, notas=f.notas,
                activado_por=quienes.get(f.activado_por_id) if f.activado_por_id else "el sistema",
                creado_en=f.creado_en,
            )
            for f in filas
        ],
    )


@router.post("/{user_id}", response_model=EstudianteDetalle)
def activar(
    user_id: UUID,
    request: ActivarRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EstudianteDetalle:
    """Activa, renueva o baja el plan · agrega una fila, nunca edita."""
    _activar(current_user)
    u = _estudiante_o_404(db, user_id)
    ahora = datetime.utcnow()
    desde = request.desde or ahora

    if request.sin_vencimiento or request.plan == "gratis":
        hasta = None
    elif request.hasta is not None:
        hasta = request.hasta
    else:
        from app.services.permisos_service import tramo_de
        from app.data.onboarding_hechos import RUTA_PROFESIONAL

        meses = MESES_PROFESIONAL if tramo_de(u) == RUTA_PROFESIONAL else MESES_POR_DEFECTO
        hasta = desde + timedelta(days=round(meses * 30.44))
    if hasta is not None and hasta <= desde:
        raise HTTPException(status_code=422, detail="El vencimiento tiene que ser después del inicio.")

    fila = UserPlan(
        user_id=u.id,
        plan=request.plan,
        desde=desde,
        hasta=hasta,
        activado_por_id=current_user.id,
        metodo=(request.metodo or "").strip() or None,
        notas=(request.notas or "").strip() or None,
        creado_en=ahora,
    )
    db.add(fila)

    # La solicitud de "Quiero activarlo" queda atendida.
    atendio_solicitud = bool(_solicitud_pendiente(u)) and request.plan != "gratis"
    if atendio_solicitud:
        u.gh_contact_status = "converted"

    log_action(
        db,
        user=current_user,
        action="plan.activado",
        resource_type="user",
        resource_id=str(u.id),
        payload={
            "plan": request.plan,
            "hasta": hasta.isoformat() if hasta else None,
            "metodo": fila.metodo,
            "atendio_solicitud": atendio_solicitud,
        },
        commit=False,
    )
    db.commit()

    if request.plan != "gratis":
        _avisar_al_estudiante(u, request.plan, hasta)
    return detalle(user_id, db, current_user)


def _avisar_al_estudiante(u: User, plan: str, hasta: Optional[datetime]) -> None:
    """Correo de "ya tienes acceso" · best-effort: si falla, el plan ya quedó activo."""
    from app.services.email_service import send_email

    nombre_plan = "VIP" if plan == "vip" else "pago"
    vence = f" hasta el {hasta:%d/%m/%Y}" if hasta else ""
    try:
        send_email(
            to=u.email,
            subject=f"Ya tienes tu plan {nombre_plan} en Mentoring",
            html_body=(
                f"<p>Hola{(' ' + u.name.split()[0]) if u.name else ''}:</p>"
                f"<p>Tu plan {nombre_plan} ya está activo{vence}. Entra a Mentoring y vas a ver "
                "abiertos los tests de tu etapa, sus lecturas completas y las herramientas.</p>"
                "<p>Hopper, de Mentoring</p>"
            ),
        )
    except Exception:  # noqa: BLE001 · el correo no puede tumbar la activación
        logger.warning("plan.activado · no se pudo enviar el correo", exc_info=True)
