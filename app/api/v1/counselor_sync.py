"""Counselor Sync · el estudiante le manda su avance a su colegio.

Verónica, revisión Sprint 2 (Paso 5): *"al finalizar cada etapa, el sistema
genera un reporte ejecutivo de progreso que el estudiante envía a su consejera
antes de su reunión presencial"*.

  GET  /me/counselor-sync/preview   · qué diría el reporte (no guarda nada)
  POST /me/counselor-sync           · lo congela y lo manda al colegio
  GET  /me/counselor-sync           · lo que ya mandó, para que sepa qué compartió
  GET  /school/counselor-sync       · lo que le han mandado al colegio
  POST /school/counselor-sync/{id}/leido

## Quién puede qué

- **Enviar sólo el estudiante, y sólo lo suyo.** No hay parámetro de a quién
  se manda: va al colegio del que envía. Sin ese dato, un `student_id` en el
  cuerpo sería una invitación a mandar el avance de otro.
- **Leer el buzón, sólo el staff del colegio** (`school_admin`,
  `psychologist`), y sólo el de SU colegio — la misma regla que ya aplica
  `app.core.access` a las sesiones.
- **El estudiante ve lo que él mandó**, no lo de nadie más.

## Por qué la vista previa existe

Porque esto sale del estudiante hacia un adulto de su colegio. Mandar a ciegas
algo que habla de ti es lo contrario de darle control. La previa la arma el
MISMO constructor que el envío, así que no puede enseñarle una cosa y mandar
otra.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import CounselorSyncReport, User, UserRole
from app.services import counselor_sync_service as servicio

router = APIRouter(tags=["Counselor Sync"])

_STAFF_DEL_COLEGIO = {UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST}


class EnviarRequest(BaseModel):
    nota: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Lo que el estudiante quiera añadir de su puño.",
    )


class ReporteOut(BaseModel):
    id: UUID
    sent_at: str
    content: Dict[str, Any]
    student_note: Optional[str] = None
    read_at: Optional[str] = None
    # Sólo para el buzón del colegio · el estudiante ya sabe quién es.
    student_name: Optional[str] = None
    student_grade: Optional[int] = None


def _a_salida(r: CounselorSyncReport, *, con_estudiante: bool = False) -> ReporteOut:
    return ReporteOut(
        id=r.id,
        sent_at=r.sent_at.isoformat(),
        content=r.content or {},
        student_note=r.student_note,
        read_at=r.read_at.isoformat() if r.read_at else None,
        student_name=(r.student.name if con_estudiante and r.student else None),
        student_grade=(r.student.grade if con_estudiante and r.student else None),
    )


def _solo_estudiante(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sólo un estudiante puede enviar su avance.",
        )


def _staff_con_colegio(user: User) -> UUID:
    """El colegio del que consulta · 403 si no es staff o no tiene colegio."""
    if user.role not in _STAFF_DEL_COLEGIO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sólo el equipo del colegio puede ver estos reportes.",
        )
    if user.school_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu usuario no está asociado a ningún colegio.",
        )
    return user.school_id


# ---------------------------------------------------------------------------
# Estudiante
# ---------------------------------------------------------------------------

@router.get("/me/counselor-sync/preview")
def previsualizar(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Qué diría el reporte si lo mandara ahora · no guarda nada."""
    _solo_estudiante(current_user)
    return {
        "puede_enviar": current_user.school_id is not None,
        "reporte": servicio.construir_reporte(db, current_user),
    }


@router.post("/me/counselor-sync", status_code=status.HTTP_201_CREATED)
def enviar(
    request: EnviarRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Congela el reporte y lo deja en el panel del colegio."""
    _solo_estudiante(current_user)
    try:
        reporte = servicio.enviar(db, current_user, request.nota)
    except ValueError as e:
        # Un B2C sin colegio · 409 y no 500: no es un fallo, es que no aplica.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    db.commit()
    db.refresh(reporte)
    return _a_salida(reporte)


@router.get("/me/counselor-sync", response_model=List[ReporteOut])
def mis_envios(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lo que ya mandó · para que sepa qué compartió y cuándo."""
    _solo_estudiante(current_user)
    return [_a_salida(r) for r in servicio.listar_del_estudiante(db, current_user.id)]


# ---------------------------------------------------------------------------
# Colegio
# ---------------------------------------------------------------------------

@router.get("/school/counselor-sync", response_model=List[ReporteOut])
def buzon_del_colegio(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lo que le han mandado a este colegio · lo más reciente primero."""
    school_id = _staff_con_colegio(current_user)
    return [
        _a_salida(r, con_estudiante=True)
        for r in servicio.listar_del_colegio(db, school_id)
    ]


@router.post("/school/counselor-sync/{reporte_id}/leido")
def marcar_leido(
    reporte_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca que el colegio ya lo abrió · sirve para que el estudiante lo sepa."""
    school_id = _staff_con_colegio(current_user)

    reporte = (
        db.query(CounselorSyncReport)
        .filter(CounselorSyncReport.id == reporte_id)
        .first()
    )
    # 404 y no 403 cuando es de otro colegio: confirmar que existe pero es
    # ajeno ya filtra información. Mismo criterio que el resto del panel.
    if reporte is None or reporte.school_id != school_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    servicio.marcar_leido(db, reporte)
    db.commit()
    return {"ok": True, "read_at": reporte.read_at.isoformat() if reporte.read_at else None}
