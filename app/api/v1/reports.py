"""Reports API · Sprint 7.

Endpoints:
    POST /reports/generate          · genera (o re-genera) PDF para current_user
    POST /reports/generate/{user}   · staff/super_admin pueden generar para otro
    GET  /reports/me                · último reporte del current_user
    GET  /reports/{id}              · descarga (URL firmada · respeta permisos)
    POST /reports/{id}/send         · envía por email (provider real o stub · D-016)

GH-S7-BE-04/05/06.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import Report, User, UserRole
from app.schemas.report import (
    ReportGenerateResponse,
    ReportRead,
    ReportSendRequest,
    ReportSendResponse,
)
from app.services import report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_read(report: Report) -> ReportRead:
    return ReportRead.model_validate(report)


def _get_user_or_404(db: DBSession, user_id: UUID) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )
    return user


def _get_report_or_404(db: DBSession, report_id: UUID) -> Report:
    rep = db.query(Report).filter(Report.id == report_id).first()
    if rep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado"
        )
    return rep


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=ReportGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_generate(
    force_refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Genera (o re-genera) el reporte PDF del current_user.

    Estudiantes generan el suyo. Para generar el de otro estudiante usa
    `POST /reports/generate/{user_id}` (psicólogo/admin/super).
    """
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Este endpoint es para que los estudiantes generen su propio "
                "reporte. Usa /reports/generate/{user_id} para staff."
            ),
        )

    try:
        report, signed, is_stale = report_service.generate_and_store_report(
            db, current_user, force_refresh_recommendations=force_refresh
        )
    except report_service.ReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    return ReportGenerateResponse(
        report=_to_read(report), download_url=signed, is_stale=is_stale
    )


@router.post(
    "/generate/{user_id}",
    response_model=ReportGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_generate_for(
    user_id: UUID,
    force_refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Staff path · psicólogo/admin de la escuela generan para un estudiante."""
    target = _get_user_or_404(db, user_id)

    if not report_service.user_can_generate_for(current_user, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para generar el reporte de este estudiante.",
        )

    try:
        report, signed, is_stale = report_service.generate_and_store_report(
            db, target, force_refresh_recommendations=force_refresh
        )
    except report_service.ReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    return ReportGenerateResponse(
        report=_to_read(report), download_url=signed, is_stale=is_stale
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("/me", response_model=Optional[ReportGenerateResponse])
def get_my_latest(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Último reporte del current_user · None si nunca lo generó."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los estudiantes consultan su propio reporte aquí.",
        )

    rep = (
        db.query(Report)
        .filter(Report.user_id == current_user.id)
        .order_by(Report.created_at.desc())
        .first()
    )
    if rep is None:
        return None

    try:
        signed = report_service.get_signed_download_url(rep)
    except Exception:
        signed = ""

    is_stale = report_service.is_report_stale(db, rep, current_user)

    return ReportGenerateResponse(
        report=_to_read(rep), download_url=signed, is_stale=is_stale
    )


@router.get("/{report_id}", response_model=ReportGenerateResponse)
def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Devuelve el report + URL firmada · respeta permisos."""
    rep = _get_report_or_404(db, report_id)
    target = report_service.get_target_user(db, rep)

    if not report_service.user_can_access_report(current_user, rep, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver este reporte.",
        )

    try:
        signed = report_service.get_signed_download_url(rep)
    except Exception as exc:
        logger.warning("signed url failed report_id=%s err=%s", rep.id, exc)
        signed = ""

    is_stale = report_service.is_report_stale(db, rep, target) if target else False

    return ReportGenerateResponse(
        report=_to_read(rep), download_url=signed, is_stale=is_stale
    )


# ---------------------------------------------------------------------------
# Send by email
# ---------------------------------------------------------------------------


@router.post("/{report_id}/send", response_model=ReportSendResponse)
def post_send(
    report_id: UUID,
    body: Optional[ReportSendRequest] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Envía el reporte al estudiante (o al override si el role lo permite)."""
    rep = _get_report_or_404(db, report_id)
    target = report_service.get_target_user(db, rep)

    if not report_service.user_can_send_email(current_user, rep, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para enviar este reporte.",
        )

    override = body.to if body and body.to else None

    try:
        rep, result = report_service.send_report_via_email(
            db, rep, requester=current_user, recipient_override=override
        )
    except report_service.ReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    return ReportSendResponse(
        report=_to_read(rep),
        delivered=result.delivered,
        provider=result.provider,
        reason=result.reason,
        message_id=result.message_id,
    )
