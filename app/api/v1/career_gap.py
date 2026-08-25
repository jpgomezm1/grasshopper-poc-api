"""La ruta del adulto profesional · auditoría de trayectoria + análisis de brecha.

Endpoints:
  PUT  /me/career-gap/linkedin  · pega su perfil de LinkedIn, se estructura y se
                                   guarda (reusa `linkedin_import_service`).
  PUT  /me/career-gap/audit     · cargo actual, satisfacción (1-5 + texto) y
                                   "puesto ideal". Todo opcional, se puede
                                   responder a medias — mismo criterio que
                                   `study_preferences.py`.
  POST /me/career-gap/analyze   · corre el análisis de brecha con lo guardado.
  GET  /me/career-gap           · lo que ya hay guardado + el último análisis.

## Dónde vive el dato

Igual que `study_preferences.py`: todo va dentro de `user.onboarding_answers`
(columna JSON que ya existe), no en columnas nuevas — no hay migración para
esto y con la política de este repo ("migraciones sólo si la tarea lo pide
explícitamente") no correspondía crear una. Las claves usadas son EXACTAMENTE
las `onboarding_key` de `app/data/adult_track_hechos.py`: si el chat de
onboarding (de otro agente) llega a escribir ahí, este análisis funciona sin
tocar una línea de este archivo.

## Por qué esto es sólo para el perfil profesional

Se lee (no se edita) `onboarding_hechos.perfil()` para saber si la persona es
`colegio` o `profesional`. A quien es claramente colegio se le bloquea: un
análisis de brecha de carrera no tiene sentido para alguien de 15 años, y
mostrárselo sería la misma clase de ruido que la clienta ya reclamó del
onboarding largo. A quien el sistema todavía no sabe clasificar (perfil
`None` — no ha respondido `life_stage` aún) SÍ se le deja pasar: es la postura
conservadora consistente con cómo `onboarding_hechos.aplica()` trata lo
desconocido en sus propias ramas.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.core.rate_limiter import rate_limit
from app.db.database import get_db
from app.db.models import User
from app.services import career_gap_service, linkedin_import_service
from app.services.ai_usage_service import record_ai_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/career-gap", tags=["StudentMe · Career Gap"])

MAX_CURRENT_ROLE = 160
MAX_SATISFACTION_TEXT = 2000
MAX_TARGET_ROLE = 200


def _solo_profesionales(user: User) -> None:
    """Bloquea sólo a quien es claramente `colegio` · ver docstring del módulo."""
    from app.data.onboarding_hechos import perfil, PERFIL_COLEGIO

    if perfil(user.onboarding_answers or {}) == PERFIL_COLEGIO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "career_gap_not_for_school",
                "message": "Esta herramienta es para quien ya trabaja o está "
                           "definiendo su carrera profesional.",
            },
        )


def _answers(user: User) -> Dict[str, Any]:
    return dict(user.onboarding_answers or {})


def _guardar(db: DBSession, user: User, cambios: Dict[str, Any]) -> Dict[str, Any]:
    """Nuevo dict siempre · `onboarding_answers` es Column(JSON) sin MutableDict,
    así que mutar el mismo objeto no dispara el UPDATE (mismo motivo documentado
    en `study_preferences.py` y `auth.update_onboarding`)."""
    answers = {**_answers(user), **cambios}
    user.onboarding_answers = answers
    db.commit()
    db.refresh(user)
    return answers


def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# PUT /me/career-gap/linkedin
# ---------------------------------------------------------------------------


class LinkedInCareerRequest(BaseModel):
    profile_text: str = Field(..., min_length=1, max_length=20000)


@router.put(
    "/linkedin",
    summary="Pegar y estructurar el perfil de LinkedIn para el análisis de brecha",
    dependencies=[Depends(rate_limit("6/minute", scope="career_gap_linkedin"))],
)
def guardar_linkedin(
    request: LinkedInCareerRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reutiliza `linkedin_import_service` (ya existente) · no lo reescribe.

    A diferencia de `POST /me/cv/import-linkedin` (CV-2), esto SÍ se persiste:
    el análisis de brecha necesita releer el perfil sin repetirle a la persona
    que lo pegue en cada paso. Sigue siendo su dato — no se aplica a ningún
    otro documento (el CV sigue teniendo su propio flujo de importación).
    """
    _solo_profesionales(current_user)

    try:
        propuesta, meta = linkedin_import_service.importar_desde_texto(
            request.profile_text
        )
    except linkedin_import_service.LinkedInImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "linkedin_import_failed", "message": str(exc)},
        )

    texto_guardado = request.profile_text.strip()[: linkedin_import_service.MAX_CHARS]
    _guardar(
        db,
        current_user,
        {
            "career_linkedin_profile_text": texto_guardado,
            "career_linkedin_profile": propuesta,
            "career_linkedin_profile_hash": _hash_texto(texto_guardado),
        },
    )

    try:
        record_ai_usage(
            db,
            provider="anthropic",
            user_id=current_user.id,
            feature="career_gap_linkedin_import",
            model=meta.get("model"),
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
        )
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo registrar el uso de IA de career-gap/linkedin")

    return {"proposal": propuesta}


# ---------------------------------------------------------------------------
# PUT /me/career-gap/audit
# ---------------------------------------------------------------------------


class CareerAuditRequest(BaseModel):
    """Todo opcional · se puede responder una parte y volver después.

    Mismo criterio que `study_preferences.py`: la clienta se quejó de la
    fatiga de formularios, y esto no es una excepción.
    """

    current_role: Optional[str] = Field(default=None, max_length=MAX_CURRENT_ROLE)
    job_satisfaction_score: Optional[int] = Field(default=None, ge=1, le=5)
    job_satisfaction_text: Optional[str] = Field(
        default=None, max_length=MAX_SATISFACTION_TEXT
    )
    target_role: Optional[str] = Field(default=None, max_length=MAX_TARGET_ROLE)


class CareerAuditResponse(BaseModel):
    current_role: Optional[str] = None
    job_satisfaction_score: Optional[int] = None
    job_satisfaction_text: Optional[str] = None
    target_role: Optional[str] = None
    has_linkedin_profile: bool = False
    answered: bool = False


def _leer_audit(answers: Dict[str, Any]) -> CareerAuditResponse:
    return CareerAuditResponse(
        current_role=answers.get("career_current_role"),
        job_satisfaction_score=answers.get("career_job_satisfaction_score"),
        job_satisfaction_text=answers.get("career_job_satisfaction_text"),
        target_role=answers.get("career_target_role"),
        has_linkedin_profile=bool(answers.get("career_linkedin_profile")),
        answered=bool(
            answers.get("career_current_role")
            or answers.get("career_job_satisfaction_score")
            or answers.get("career_target_role")
        ),
    )


@router.put("/audit", response_model=CareerAuditResponse)
def guardar_audit(
    request: CareerAuditRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Guarda cargo actual, satisfacción y puesto ideal · nunca borra LinkedIn."""
    _solo_profesionales(current_user)

    # Cada campo presente en el request se guarda tal cual, o se BORRA si
    # llega vacío/None — borrar es una acción válida ("quité lo que había
    # puesto"), mismo criterio que `study_preferences.update_study_preferences`.
    # Lo que no viene en el request no se toca.
    base = _answers(current_user)

    def _set_o_borrar(clave: str, valor: Any) -> None:
        if valor:
            base[clave] = valor
        else:
            base.pop(clave, None)

    if request.current_role is not None:
        _set_o_borrar("career_current_role", request.current_role.strip())
    if request.job_satisfaction_score is not None:
        _set_o_borrar("career_job_satisfaction_score", request.job_satisfaction_score)
    if request.job_satisfaction_text is not None:
        _set_o_borrar("career_job_satisfaction_text", request.job_satisfaction_text.strip())
    if request.target_role is not None:
        _set_o_borrar("career_target_role", request.target_role.strip())

    current_user.onboarding_answers = base
    db.commit()
    db.refresh(current_user)

    return _leer_audit(base)


# ---------------------------------------------------------------------------
# GET /me/career-gap
# ---------------------------------------------------------------------------


class CareerGapStateResponse(BaseModel):
    audit: CareerAuditResponse
    linkedin_profile: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    analysis_generated_at: Optional[str] = None
    ready_for_analysis: bool = False


def _missing_for_analysis(answers: Dict[str, Any]) -> List[str]:
    faltan = []
    if not answers.get("career_linkedin_profile"):
        faltan.append("linkedin_profile")
    target_role = answers.get("career_target_role")
    if not (target_role.strip() if isinstance(target_role, str) else target_role):
        faltan.append("target_role")
    return faltan


@router.get("", response_model=CareerGapStateResponse)
def get_career_gap_state(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_profesionales(current_user)
    answers = _answers(current_user)
    return CareerGapStateResponse(
        audit=_leer_audit(answers),
        linkedin_profile=answers.get("career_linkedin_profile"),
        analysis=answers.get("career_gap_analysis"),
        analysis_generated_at=answers.get("career_gap_analysis_generated_at"),
        ready_for_analysis=not _missing_for_analysis(answers),
    )


# ---------------------------------------------------------------------------
# POST /me/career-gap/analyze
# ---------------------------------------------------------------------------


@router.post(
    "/analyze",
    summary="Comparar el perfil actual contra el puesto ideal declarado",
    dependencies=[Depends(rate_limit("6/minute", scope="career_gap_analyze"))],
)
def analizar(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Corre con lo que ya está guardado — no recibe body.

    Se pide primero pegar LinkedIn (`PUT .../linkedin`) y declarar el puesto
    ideal (`PUT .../audit`); sin esos dos no hay nada que comparar. 409 y no
    400 por el mismo motivo que `GET /me/cv`: no es una petición mal formada,
    es un paso previo que falta.
    """
    _solo_profesionales(current_user)
    answers = _answers(current_user)

    faltan = _missing_for_analysis(answers)
    if faltan:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "career_gap_incomplete",
                "message": "Antes de tu análisis de brecha necesitamos tu "
                           "perfil de LinkedIn y tu puesto ideal.",
                "missing": faltan,
            },
        )

    try:
        analisis, meta = career_gap_service.analizar(
            perfil_linkedin=answers.get("career_linkedin_profile"),
            target_role=answers.get("career_target_role") or "",
            current_role=answers.get("career_current_role"),
            job_satisfaction_score=answers.get("career_job_satisfaction_score"),
            job_satisfaction_text=answers.get("career_job_satisfaction_text"),
            session_id=str(current_user.id),
        )
    except career_gap_service.CareerGapError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "career_gap_analysis_failed", "message": str(exc)},
        )

    generado_en = datetime.now(timezone.utc).isoformat()
    _guardar(
        db,
        current_user,
        {
            "career_gap_analysis": analisis,
            "career_gap_analysis_generated_at": generado_en,
        },
    )

    try:
        record_ai_usage(
            db,
            provider="anthropic",
            user_id=current_user.id,
            feature="career_gap_analysis",
            model=meta.get("model"),
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
        )
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo registrar el uso de IA de career-gap/analyze")

    return {"analysis": analisis, "generated_at": generado_en}


# ---------------------------------------------------------------------------
# GET /me/professional/gap-analysis · GET /me/professional/upskilling-plan
# ---------------------------------------------------------------------------
# Contrato pedido por el frontend (`journey-compass/src/lib/professionalApi.ts`,
# construido por otro agente en paralelo, sin backend detrás todavía). Son
# rutas de sólo LECTURA sobre lo que YA calculó `POST /me/career-gap/analyze`
# arriba — no llaman IA, no agregan lógica nueva, sólo traducen el análisis
# guardado (`career_gap_analysis` en `onboarding_answers`) al shape que la
# pantalla espera.
#
# Fidelidad deliberada, NO se inventa lo que no existe: el análisis real habla
# de ÁREAS con un `impacto` (alto/medio/bajo) — no de una escala de 5 niveles
# "básico → experto" por habilidad, que fue la PROPUESTA original del
# frontend (`src/lib/types/upskilling.ts` lo decía explícito: "quien
# construya el backend puede ajustarlos, pero debe avisar si cambia"). Aquí
# se avisa: inventar `current_level`/`target_level` sería la misma clase de
# dato fabricado que este módulo existe para evitar (ver `_redactar_cifras`
# en `career_gap_service.py`), así que el tipo del frontend se ajustó para
# reflejar el shape real (`area`/`descripcion`/`impacto`,
# `brecha`/`como_cerrarla`/`tipo`/`prioridad`) en vez de forzar el backend a
# mentir para calzar con la propuesta.
router_professional = APIRouter(prefix="/me/professional", tags=["StudentMe · Professional"])


@router_professional.get("/gap-analysis")
def get_gap_analysis_view(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lo mismo que `GET /me/career-gap`, pero sólo la parte de la brecha y en
    la forma que espera `ProfessionalHomePanel.tsx`. 404 (no 200 vacío) si
    todavía no hay análisis · el frontend ya trata ese código como "todavía
    no hay datos", no como error (ver `useProfessionalResource` en el panel).
    """
    _solo_profesionales(current_user)
    answers = _answers(current_user)
    analisis = answers.get("career_gap_analysis")
    if not analisis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "career_gap_not_analyzed",
                "message": "Todavía no hay un análisis de brecha para esta persona.",
            },
        )
    return {
        "generated_at": answers.get("career_gap_analysis_generated_at"),
        "current_role": answers.get("career_current_role"),
        "target_role": answers.get("career_target_role"),
        "summary": analisis.get("resumen"),
        "fortalezas_alineadas": analisis.get("fortalezas_alineadas") or [],
        "gaps": analisis.get("brechas") or [],
        "disclaimer": analisis.get("disclaimer"),
    }


@router_professional.get("/upskilling-plan")
def get_upskilling_plan_view(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """El plan de upskilling del último análisis · mismo criterio de 404 que
    arriba. `headline` reutiliza el `resumen` del análisis: no hay un campo
    separado para "una frase que resuma el plan" en lo que calcula
    `career_gap_service`, y no vale la pena una segunda llamada a IA sólo
    para producir una frase — el resumen ya cumple ese rol.
    """
    _solo_profesionales(current_user)
    answers = _answers(current_user)
    analisis = answers.get("career_gap_analysis")
    plan = (analisis or {}).get("plan_upskilling") or []
    if not analisis or not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "career_gap_not_analyzed",
                "message": "Todavía no hay un plan de upskilling para esta persona.",
            },
        )
    return {
        "generated_at": answers.get("career_gap_analysis_generated_at"),
        "headline": analisis.get("resumen"),
        "steps": plan,
    }
