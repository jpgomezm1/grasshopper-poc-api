"""CV builder API · F-001 etapa 3 (2026-06-04).

Endpoint:
  GET /me/cv  · descarga la Hoja de Vida (PDF) del estudiante actual.

Reúne datos que ya existen (perfil consolidado cacheado + tests + actividades)
y los renderiza con `cv_pdf_service`. No llama a IA → siempre generable.
Igual que el PDF clínico: si el runtime GTK no está (Windows dev), devuelve 503.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import School, User, UserRole, VocationalTestResult
from app.services import cv_pdf_service, extracurricular_service
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router_me = APIRouter(prefix="/me/cv", tags=["StudentMe · CV"])


@router_me.get(
    "",
    summary="F-001 · descargar mi Hoja de Vida (PDF)",
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_my_cv(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )

    # 1) Actividades extracurriculares
    activities, _ = extracurricular_service.list_activities_for_user(
        db, current_user.id
    )

    # 2) Resultados de tests psicométricos
    test_results = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == current_user.id)
        .all()
    )

    # 3) Perfil consolidado cacheado (si existe · NO se fuerza IA)
    profile_cache = getattr(current_user, "consolidated_profile", None)
    profile_data = getattr(profile_cache, "profile_data", None) if profile_cache else None

    # 4) Colegio (para el encabezado)
    school_name = None
    if current_user.school_id:
        school = db.query(School).filter(School.id == current_user.school_id).first()
        school_name = school.name if school else None

    cv = cv_pdf_service.build_cv_data(
        user=current_user,
        activities=activities,
        test_results=test_results,
        profile_data=profile_data,
        school_name=school_name,
    )

    try:
        pdf_bytes = cv_pdf_service.render_cv_pdf(cv)
    except RuntimeError as exc:
        # GTK ausente (Windows dev) · weasyprint no instalado · etc.
        # El detalle (rutas de librerías GTK/cairo del host) se loguea
        # server-side; al cliente solo le llega un mensaje genérico.
        logger.warning("cv pdf render unavailable user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=503,
            detail="El generador de PDF no está disponible en este momento.",
        )

    # `student_name` es dato editable por el usuario → se sanea a un whitelist
    # ASCII antes de entrar a la cabecera Content-Disposition (evita romper el
    # header con comillas/CRLF · header injection).
    safe_name = re.sub(
        r"[^A-Za-z0-9_\-]", "", (cv.student_name or "estudiante").replace(" ", "_")
    ) or "estudiante"
    filename = f"CV-{safe_name}-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    logger.info("cv pdf generated user_id=%s size=%d", current_user.id, len(pdf_bytes))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
