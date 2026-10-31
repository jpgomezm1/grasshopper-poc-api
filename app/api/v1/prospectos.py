"""Panel de prospectos · G-1 / G-2, Sprint 4 (decisión D4 de JP).

Las tres fuentes (bot gratuito, perfilador, quiz viejo) en un solo listado, con
el estado que pone el equipo comercial y exportación a CSV. La lógica vive en
`prospectos_service`; aquí solo están los permisos y la forma HTTP.

Mismos roles que la bandeja del bot (`bot._require_equipo`): comercial, asesor
y super admin. Es la misma gente la que trabaja los prospectos.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.api.v1.bot import _require_equipo
from app.db.models import User
from app.db.database import get_db
from app.services import prospectos_service as svc
from app.services.audit_service import log_action

router = APIRouter(prefix="/prospectos", tags=["prospectos"])

Fuente = Literal["bot_gratuito", "perfilador", "quiz"]
Estado = Literal["nuevo", "contactado", "convertido", "descartado"]


class ProspectoItem(BaseModel):
    fuente: str
    id: str
    creado_en: datetime
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    quien: Optional[str] = None
    etapa: Optional[str] = None
    destino: Optional[str] = None
    presupuesto: Optional[str] = None
    cuando: Optional[str] = None
    puntaje: Optional[int] = None
    banda: Optional[str] = None
    ruta: Optional[str] = None
    porque: List[str] = []
    acciones: List[str] = []
    resumen: Optional[str] = None
    creo_cuenta: bool = False
    pidio_activar_plan: bool = False
    estado: str
    estado_manual: bool = False
    hechos: Dict[str, Any] = {}


class CambiarEstado(BaseModel):
    estado: Estado


def _filtros(
    fuente: Optional[Fuente] = Query(None),
    banda: Optional[str] = Query(None, description="hot · warm · cold"),
    ruta: Optional[str] = Query(None),
    estado: Optional[Estado] = Query(None),
    desde: Optional[datetime] = Query(None),
    hasta: Optional[datetime] = Query(None),
    limite: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    return dict(fuente=fuente, banda=banda, ruta=ruta, estado=estado, desde=desde, hasta=hasta, limite=limite)


@router.get("", response_model=List[ProspectoItem])
def listar(
    filtros: Dict[str, Any] = Depends(_filtros),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ProspectoItem]:
    _require_equipo(current_user)
    return [ProspectoItem(**p.a_dict()) for p in svc.listar(db, **filtros)]


@router.get("/csv")
def exportar_csv(
    filtros: Dict[str, Any] = Depends(_filtros),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Lo mismo que el listado, con los mismos filtros, en CSV.

    Va con BOM de UTF-8 para que Excel abra bien las tildes al hacer doble clic,
    que es como lo va a abrir el equipo comercial.
    """
    _require_equipo(current_user)
    salida = io.StringIO()
    csv.writer(salida).writerows(svc.a_filas_csv(svc.listar(db, **filtros)))
    log_action(
        db, user=current_user, action="prospectos.exportados", resource_type="prospecto",
        payload={k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in filtros.items()},
    )
    nombre = f"prospectos_{datetime.utcnow():%Y-%m-%d}.csv"
    return Response(
        content="﻿" + salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.patch("/{fuente}/{prospecto_id}/estado", response_model=ProspectoItem)
def cambiar_estado(
    fuente: Fuente,
    prospecto_id: UUID,
    request: CambiarEstado,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProspectoItem:
    _require_equipo(current_user)
    try:
        anterior = svc.cambiar_estado(db, fuente=fuente, prospecto_id=prospecto_id, estado=request.estado)
    except svc.ProspectoNoEncontrado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospecto_no_encontrado")
    log_action(
        db, user=current_user, action="prospecto.estado", resource_type="prospecto",
        resource_id=f"{fuente}:{prospecto_id}",
        payload={"de": anterior, "a": request.estado},
    )
    actualizado = next(
        (p for p in svc.listar(db, fuente=fuente, limite=1000) if p.id == str(prospecto_id)),
        None,
    )
    if actualizado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prospecto_no_encontrado")
    return ProspectoItem(**actualizado.a_dict())
