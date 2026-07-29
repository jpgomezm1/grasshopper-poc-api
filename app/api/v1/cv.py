"""CV builder API · F-001 etapa 3 (2026-06-04) · A3 (2026-07-29).

Endpoints:
  GET  /me/cv          · descarga la Hoja de Vida (PDF) del estudiante actual.
  GET  /me/cv/profile  · A3 · las preguntas previas + el contenido editable.
  PUT  /me/cv/profile  · A3 · responder las preguntas y editar el contenido.

Reúne datos que ya existen (perfil consolidado cacheado + tests + actividades)
y los renderiza con `cv_pdf_service`. No llama a IA → siempre generable.
Igual que el PDF clínico: si el runtime GTK no está (Windows dev), devuelve 503.

A3 · feedback literal de la clienta:

    "Hoja de vida: antes de generarla debe preguntar QUÉ HAGO ACTUALMENTE y EN QUÉ
     COLEGIO ESTUDIO (si estoy en colegio). El resto (integrar perfiles + tests +
     lo subido) está muy chévere. Además DEBE PODER EDITARSE."

Por eso `GET /me/cv` ahora responde **409** mientras falten esas respuestas: ella
dijo "antes de generarla", así que no es un aviso saltable. El resto del CV no se
tocó — sobre eso dijo "está muy chévere".
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as DBSession

from pydantic import BaseModel

from app.db.database import get_db
from app.db.models import School, User, UserRole, VocationalTestResult
from app.services import cv_pdf_service, cv_profile_service, extracurricular_service
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router_me = APIRouter(prefix="/me/cv", tags=["StudentMe · CV"])


def _solo_estudiantes(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )


def _armar_cv(db: DBSession, user: User):
    """Junta todo lo que va en la hoja de vida y aplica lo que el estudiante editó.

    Se comparte entre la vista previa y la descarga a propósito: si fueran dos
    caminos distintos, lo que la persona ve editando podría no ser lo que sale en
    el PDF, que es justo la confianza que A3 intenta dar.
    """
    activities, _ = extracurricular_service.list_activities_for_user(db, user.id)

    test_results = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        .all()
    )

    profile_cache = getattr(user, "consolidated_profile", None)
    profile_data = getattr(profile_cache, "profile_data", None) if profile_cache else None

    school_name = None
    if user.school_id:
        school = db.query(School).filter(School.id == user.school_id).first()
        school_name = school.name if school else None

    cv = cv_pdf_service.build_cv_data(
        user=user,
        activities=activities,
        test_results=test_results,
        profile_data=profile_data,
        school_name=school_name,
    )
    perfil = cv_profile_service.get_profile(db, user.id)
    return cv_profile_service.apply_overrides(cv, perfil), perfil


@router_me.get(
    "",
    summary="F-001 · descargar mi Hoja de Vida (PDF)",
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_my_cv(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)

    cv, perfil = _armar_cv(db, current_user)

    # A3 · "ANTES de generarla debe preguntar qué hago actualmente y en qué
    # colegio estudio". Ella dijo "antes", así que no es un aviso que se pueda
    # saltar: sin las respuestas no se genera el PDF. 409 y no 400 porque no es
    # una petición mal formada, es un paso que falta.
    if not cv_profile_service.is_ready(perfil):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "cv_profile_incomplete",
                "message": "Antes de generar tu hoja de vida necesitamos un par de datos.",
                "missing": cv_profile_service.missing_answers(perfil),
            },
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


# ---------------------------------------------------------------------------
# A3 · Las preguntas previas y la edición de la hoja de vida
# ---------------------------------------------------------------------------


class CVProfileRequest(BaseModel):
    current_occupation: str | None = None
    occupation_detail: str | None = None
    school_name: str | None = None
    overrides: dict | None = None


def _serializar(cv, perfil) -> dict:
    """Lo que necesita la pantalla: las preguntas, el contenido y qué falta."""
    return {
        # --- Las dos preguntas de A3 ---------------------------------
        "occupation_choices": cv_profile_service.OCCUPATION_CHOICES,
        "current_occupation": getattr(perfil, "current_occupation", None),
        "occupation_detail": getattr(perfil, "occupation_detail", None),
        "school_name": getattr(perfil, "school_name", None),
        "requires_school": cv_profile_service.requires_school(
            getattr(perfil, "current_occupation", None)
        ),
        "ready": cv_profile_service.is_ready(perfil),
        "missing": cv_profile_service.missing_answers(perfil),
        # --- El contenido, ya con lo que él editó aplicado -----------
        "content": {
            "student_name": cv.student_name,
            "current_occupation_line": cv.current_occupation,
            "headline": cv.headline,
            "summary": cv.summary,
            "strengths": cv.strengths,
            "interests": cv.interests,
            "values": cv.values,
            "career_paths": cv.career_paths,
            "school_name": cv.school_name,
            "english_level": cv.english_level,
        },
        # --- Lo que puede quitar -------------------------------------
        "activities": [
            {
                "id": a.activity_id,
                "name": a.name,
                "category_label": a.category_label,
                "period": a.period,
            }
            for a in cv.activities
        ],
        "tests": [
            {
                "id": fila[3] if len(fila) > 3 else None,
                "label": fila[0],
                "highlight": fila[1],
            }
            for fila in cv.test_highlights
        ],
    }


@router_me.get("/profile", summary="A3 · datos y contenido editable de mi hoja de vida")
def get_cv_profile(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    cv, perfil = _armar_cv(db, current_user)
    return _serializar(cv, perfil)


@router_me.put("/profile", summary="A3 · responder las preguntas y editar mi hoja de vida")
def save_cv_profile(
    request: CVProfileRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    try:
        cv_profile_service.save_answers(
            db,
            current_user.id,
            current_occupation=request.current_occupation,
            occupation_detail=request.occupation_detail,
            school_name=request.school_name,
            overrides=request.overrides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    cv, perfil = _armar_cv(db, current_user)
    return _serializar(cv, perfil)
