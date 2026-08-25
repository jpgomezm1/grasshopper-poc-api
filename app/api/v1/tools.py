"""La sección "Herramientas" · las tres mini apps (2026-08-25).

JP, en la reunión del 24-08 (13:48): *"ya salieron tres, hoja de vida,
postulación a trabajo, postulación a la universidad... armamos así como unas
mini apps"*.

  GET  /me/tools                      · el índice de la sección, con qué falta
                                        para poder usar cada una.
  POST /me/tools/statement-of-purpose · el ensayo para aplicar a una universidad.
  POST /me/tools/job-application      · el copy para postularse a un trabajo.

La tercera mini app —**la hoja de vida por país**— no tiene endpoints propios a
propósito: es la hoja de vida de siempre con otro destino, y ese selector ya
existe (`GET /me/cv/formatos`, `PUT /me/cv/formato`, `GET /me/cv?estandar=...`).
Lo único que hacía falta era que España y Colombia fueran opciones de verdad, y
eso vive en `cv_variants`. Aquí sólo se listan sus opciones en el índice, para
que la sección "Herramientas" pueda pintar las tres juntas sin que el frontend
tenga que saber que una de ellas vive en otro router.

## Por qué esto es síncrono y las convocatorias del CV no

`POST /me/cv/targets` responde 202 y analiza en background porque encadena DOS
llamadas al modelo y se acercaba al límite de 30s del router de Heroku (H12).
Cada una de estas dos herramientas hace **una sola** llamada, igual que
`POST /me/career-gap/analyze`, que lleva meses respondiendo en línea. Si algún
día una de las dos crece a dos llamadas, el patrón a copiar es el de
`cv.py::_analizar_target_bg`, no alargar el timeout.

## Nada se guarda

Ninguna de las dos persiste su resultado. Ver el docstring de `sop_service`:
no hay tabla, crear una migración estaba fuera del alcance, y meter un ensayo
de 600 palabras en `user.onboarding_answers` lo metería en prompts del journey
que no lo pidieron. Lo que sí se guarda es el **consumo de IA**
(`record_ai_usage`), como en todo el resto del repo.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.core.rate_limiter import rate_limit
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import cv_variants, job_pitch_service, sop_service
from app.services.ai_usage_service import record_ai_usage
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/tools", tags=["StudentMe · Herramientas"])


def _solo_estudiantes(user: User) -> None:
    """Estas herramientas trabajan sobre el perfil de la propia persona.

    Un asesor o un colegio no tienen nada que escribir aquí: el ensayo lleva el
    nombre del estudiante y se apoya en sus datos, incluidos los de un menor.
    """
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )


def _cv_del_usuario(db: DBSession, user: User):
    """La MISMA hoja de vida que la persona ve, edita y descarga.

    Se reutiliza el ensamblador de `cv.py` en vez de rearmar el `CVData` aquí.
    Es un símbolo privado de otro módulo y se importa a sabiendas: la clienta
    dijo *"ya tienes mi hoja de vida"*, y si esto armara su propia versión, el
    ensayo podría citar cosas que ella ya había quitado de su CV — que es
    exactamente la clase de incoherencia que el A3 vino a arreglar.

    Sin foto: aquí el CV va a un prompt, no a un PDF. Bajarla de storage y
    pasarla a base64 para no usarla es medio megabyte de trabajo por request, y
    es la foto de un menor.
    """
    from app.api.v1.cv import _armar_cv

    cv, _perfil = _armar_cv(db, user, con_foto=False)
    return cv


def _perfil_profesional(user: User) -> Dict[str, Any]:
    """Lo que la ruta del adulto ya dejó guardado en `onboarding_answers`.

    Las claves son las que escribe `app/api/v1/career_gap.py`; no se inventan
    aquí. Si un día ese módulo cambia dónde guarda, esto deja de encontrar el
    perfil y la herramienta cae al camino "sólo con la hoja de vida" — degrada,
    no revienta.
    """
    answers = user.onboarding_answers or {}
    if not isinstance(answers, dict):
        return {}
    return {
        "perfil_linkedin": answers.get("career_linkedin_profile"),
        "current_role": answers.get("career_current_role"),
        "gap_analysis": answers.get("career_gap_analysis"),
    }


# ---------------------------------------------------------------------------
# GET /me/tools · el índice de la sección
# ---------------------------------------------------------------------------


@router.get("", summary="Las tres mini apps de Herramientas y qué falta para usarlas")
def listar_herramientas(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """El índice que pinta la sección.

    `disponible` y `que_falta` se calculan con **los mismos predicados** que
    aplican los endpoints (`sop_service.hay_con_que_escribir`,
    `job_pitch_service.hay_con_que_postularse`). Si fueran dos comprobaciones
    parecidas en dos sitios, acabaríamos con un botón habilitado que devuelve
    409 — el clásico de este repo.
    """
    _solo_estudiantes(current_user)

    cv = _cv_del_usuario(db, current_user)
    prof = _perfil_profesional(current_user)

    hay_perfil = sop_service.hay_con_que_escribir(cv)
    hay_para_trabajo = job_pitch_service.hay_con_que_postularse(
        perfil_linkedin=prof["perfil_linkedin"], cv=cv
    )

    return {
        "herramientas": [
            {
                "clave": "statement_of_purpose",
                "nombre": "Carta de motivación para una universidad",
                "descripcion": (
                    "El Statement of Purpose con el que te postulas a un "
                    "programa: lo escribimos con tus tests, tus actividades y "
                    "tu hoja de vida."
                ),
                "endpoint": "/api/v1/me/tools/statement-of-purpose",
                "disponible": hay_perfil,
                "que_falta": (
                    []
                    if hay_perfil
                    else ["Haz al menos un test o registra tus actividades y logros."]
                ),
                "idiomas": list(sop_service.IDIOMAS),
            },
            {
                "clave": "postulacion_trabajo",
                "nombre": "Postularte a un trabajo",
                "descripcion": (
                    "Pega el aviso de la vacante y te devolvemos el texto con "
                    "el que te presentas, más lo que la vacante pide y hoy no "
                    "tienes."
                ),
                "endpoint": "/api/v1/me/tools/job-application",
                "disponible": hay_para_trabajo,
                "que_falta": (
                    []
                    if hay_para_trabajo
                    else [
                        "Importa tu perfil de LinkedIn o completa tu hoja de vida."
                    ]
                ),
                "formatos": job_pitch_service.catalogo_formatos(),
            },
            {
                "clave": "hoja_de_vida_por_pais",
                "nombre": "Hoja de vida según el país",
                "descripcion": (
                    "La misma hoja de vida, con el formato que se usa en el "
                    "país al que la mandas. Cada formato explica en qué cambia."
                ),
                # Vive en el router del CV · esto es sólo el acceso directo
                # desde la sección Herramientas.
                "endpoint": "/api/v1/me/cv/formatos",
                "disponible": True,
                "que_falta": [],
                "opciones": cv_variants.catalogo()["estandares"],
            },
        ]
    }


# ---------------------------------------------------------------------------
# POST /me/tools/statement-of-purpose
# ---------------------------------------------------------------------------


class StatementOfPurposeRequest(BaseModel):
    """A dónde se postula · lo demás sale de lo que ya sabemos de ella."""

    universidad: str = Field(..., min_length=2, max_length=sop_service.MAX_UNIVERSIDAD)
    programa: str = Field(..., min_length=2, max_length=sop_service.MAX_PROGRAMA)
    pais: Optional[str] = Field(None, max_length=sop_service.MAX_PAIS)
    idioma: str = Field(
        sop_service.IDIOMA_POR_DEFECTO,
        description="es · en · el ensayo va en el idioma de la universidad.",
    )
    motivacion: Optional[str] = Field(
        None,
        max_length=sop_service.MAX_MOTIVACION,
        description="Con sus palabras: por qué quiere ese programa.",
    )


@router.post(
    "/statement-of-purpose",
    summary="Escribir el borrador del Statement of Purpose",
    dependencies=[Depends(rate_limit("4/minute", scope="tools_sop"))],
)
def escribir_statement_of_purpose(
    request: StatementOfPurposeRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el borrador, su disclaimer y lo que ella tiene que completar.

    409 (y no 400) cuando todavía no hay perfil con qué escribir: no es una
    petición mal formada, es un paso previo que falta — mismo criterio que
    `GET /me/cv` y que `POST /me/career-gap/analyze`.
    """
    _solo_estudiantes(current_user)

    cv = _cv_del_usuario(db, current_user)
    if not sop_service.hay_con_que_escribir(cv):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "sop_sin_insumos",
                "message": (
                    "Todavía no tenemos con qué escribir tu carta. Haz al menos "
                    "un test o registra tus actividades y logros."
                ),
                "missing": ["tests_o_actividades_o_perfil"],
            },
        )

    try:
        sop, meta = sop_service.escribir(
            cv=cv,
            universidad=request.universidad,
            programa=request.programa,
            pais=request.pais,
            idioma=request.idioma,
            motivacion=request.motivacion,
            session_id=str(current_user.id),
        )
    except sop_service.SOPError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "sop_failed", "message": str(exc)},
        )

    _registrar_uso(db, current_user, feature="sop_universidad", meta=meta)
    logger.info(
        "sop generado user_id=%s palabras=%s", current_user.id, sop.get("palabras")
    )
    return sop


# ---------------------------------------------------------------------------
# POST /me/tools/job-application
# ---------------------------------------------------------------------------


class JobApplicationRequest(BaseModel):
    """El aviso de la vacante, pegado tal cual · igual que las convocatorias."""

    vacante: str = Field(..., min_length=1, max_length=20000)
    formato: str = Field(
        job_pitch_service.FORMATO_POR_DEFECTO,
        description="mensaje · correo · carta",
    )
    notas: Optional[str] = Field(
        None,
        max_length=job_pitch_service.MAX_NOTAS,
        description="Algo que quiera que se mencione sí o sí.",
    )


@router.post(
    "/job-application",
    summary="Escribir el copy para postularse a una vacante",
    dependencies=[Depends(rate_limit("4/minute", scope="tools_job"))],
)
def escribir_postulacion(
    request: JobApplicationRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pensado sobre todo para el perfil adulto, pero **abierto a todos**.

    JP dijo "es para el perfil adulto sobre todo" — sobre todo, no
    exclusivamente: alguien de once que busca su primer trabajo de medio tiempo
    también tiene derecho a la herramienta. Lo que cambia según quién sea es de
    dónde salen los insumos (LinkedIn + brecha para el adulto; hoja de vida para
    quien está en el colegio), no el permiso.
    """
    _solo_estudiantes(current_user)

    texto = (request.vacante or "").strip()
    # Se valida ANTES de llamar al modelo · decirle "muy corto" al instante es
    # mejor que cobrarle una llamada para responderle lo mismo (mismo criterio
    # que `crear_target` en cv.py).
    if len(texto) < job_pitch_service.MIN_VACANTE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "job_vacante_too_short",
                "message": (
                    "Pega un poco más del aviso de la vacante: con tan poco "
                    "texto no puedo saber qué están buscando."
                ),
            },
        )

    cv = _cv_del_usuario(db, current_user)
    prof = _perfil_profesional(current_user)

    if not job_pitch_service.hay_con_que_postularse(
        perfil_linkedin=prof["perfil_linkedin"], cv=cv
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "job_pitch_sin_insumos",
                "message": (
                    "Antes de escribir tu postulación necesitamos saber de ti: "
                    "importa tu perfil de LinkedIn o completa tu hoja de vida."
                ),
                "missing": ["linkedin_o_hoja_de_vida"],
            },
        )

    perfil = job_pitch_service.describir_perfil(
        perfil_linkedin=prof["perfil_linkedin"],
        current_role=prof["current_role"],
        gap_analysis=prof["gap_analysis"],
        cv=cv,
    )

    try:
        pitch, meta = job_pitch_service.redactar(
            vacante=texto,
            perfil=perfil,
            formato=request.formato,
            notas=request.notas,
            session_id=str(current_user.id),
        )
    except job_pitch_service.JobPitchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "job_pitch_failed", "message": str(exc)},
        )

    _registrar_uso(db, current_user, feature="job_pitch", meta=meta)
    logger.info(
        "job pitch generado user_id=%s formato=%s", current_user.id, pitch.get("formato")
    )
    return pitch


def _registrar_uso(
    db: DBSession, user: User, *, feature: str, meta: Dict[str, Any]
) -> None:
    """M-001 · el consumo queda auditado; si falla, no se pierde el trabajo.

    `provider` es obligatorio y keyword-only: olvidarlo lanza un `TypeError`
    que este `except` se tragaría, dejando la auditoría vacía en silencio (ya
    pasó en este repo).
    """
    try:
        record_ai_usage(
            db,
            provider="anthropic",
            user_id=user.id,
            feature=feature,
            model=meta.get("model"),
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
        )
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo registrar el uso de IA de %s", feature)
