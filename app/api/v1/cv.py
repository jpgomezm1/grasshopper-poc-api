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

import base64
import logging
import re
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session as DBSession

from pydantic import BaseModel, Field

from app.core.rate_limiter import rate_limit
from app.db.database import get_db
from app.db.models import CVTarget, School, User, UserRole, VocationalTestResult
from app.services import (
    cv_docx_service,
    cv_pdf_service,
    cv_photo_service,
    cv_profile_service,
    cv_tailor_service,
    cv_target_service,
    cv_variants,
    extracurricular_service,
    linkedin_import_service,
)
from app.services.ai_usage_service import record_ai_usage
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
    # La foto viaja incrustada en base64 dentro del propio documento · así el
    # archivo que descarga el estudiante es autocontenido.
    cv.photo_data_uri = cv_photo_service.obtener_data_uri(db, user.id)
    perfil = cv_profile_service.get_profile(db, user.id)
    return cv_profile_service.apply_overrides(cv, perfil), perfil


@router_me.get(
    "/formatos",
    summary="El catálogo de destinos y estilos + lo que el estudiante tiene elegido",
)
def get_formatos(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lo que necesita el selector de formato para pintarse.

    El catálogo sale de `cv_variants` y no de una lista en el frontend: dos
    listas de estándares que se desincronizan es el bug que este repo ya pagó
    dos veces (P0-8). Cada estándar viaja con su `nota`, que es el texto con el
    que la pantalla explica por qué Estados Unidos omite la foto.
    """
    _solo_estudiantes(current_user)
    perfil = cv_profile_service.get_profile(db, current_user.id)
    catalogo = cv_variants.catalogo()
    catalogo["seleccion"] = cv_profile_service.preferencias_formato(perfil)
    # `tiene_foto` pregunta sin descargar la imagen · es para pintar un botón.
    catalogo["tiene_foto"] = cv_photo_service.tiene_foto(db, current_user.id)
    return catalogo


class FormatoRequest(BaseModel):
    estandar: str | None = None
    estilo: str | None = None
    incluir_foto: bool | None = None


@router_me.put("/formato", summary="Guardar a qué destino va mi hoja de vida y cómo se ve")
def save_formato(
    request: FormatoRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    try:
        perfil = cv_profile_service.save_formato(
            db,
            current_user.id,
            estandar=request.estandar,
            estilo=request.estilo,
            incluir_foto=request.incluir_foto,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return cv_profile_service.preferencias_formato(perfil)


# Cada formato con su renderizador, su MIME y su extensión. El endpoint no sabe
# que uno lleva CSS y el otro no: sólo elige la fila.
_FORMATOS = {
    "pdf": ("application/pdf", "pdf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    "html": ("text/html; charset=utf-8", "html"),
}


@router_me.get(
    "",
    summary="F-001 · descargar mi Hoja de Vida (PDF · Word · HTML)",
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_my_cv(
    formato: str = Query("pdf", description="pdf · docx · html"),
    estandar: str | None = Query(None, description="us · europass · latam"),
    estilo: str | None = Query(None, description="clasico · moderno · compacto"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)

    formato = (formato or "pdf").lower()
    if formato not in _FORMATOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"formato desconocido: {formato}",
        )

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

    # El querystring manda sobre lo guardado (para previsualizar sin guardar),
    # y lo guardado sobre el valor por defecto.
    prefs = cv_profile_service.preferencias_formato(perfil)
    variante = {
        "estandar": estandar or prefs["estandar"],
        "estilo": estilo or prefs["estilo"],
        "incluir_foto": prefs["incluir_foto"],
    }

    media_type, extension = _FORMATOS[formato]

    try:
        if formato == "pdf":
            contenido = cv_pdf_service.render_cv_pdf(cv, **variante)
        elif formato == "docx":
            contenido = cv_docx_service.render_cv_docx(cv, **variante)
        else:
            contenido = cv_pdf_service.render_cv_html(cv, **variante).encode("utf-8")
    except RuntimeError as exc:
        # GTK ausente (Windows dev) · weasyprint no instalado · etc.
        # El detalle (rutas de librerías GTK/cairo del host) se loguea
        # server-side; al cliente solo le llega un mensaje genérico.
        logger.warning("cv render unavailable user_id=%s fmt=%s: %s", current_user.id, formato, exc)
        raise HTTPException(
            status_code=503,
            detail="El generador de documentos no está disponible en este momento.",
        )

    # `student_name` es dato editable por el usuario → se sanea a un whitelist
    # ASCII antes de entrar a la cabecera Content-Disposition (evita romper el
    # header con comillas/CRLF · header injection).
    safe_name = re.sub(
        r"[^A-Za-z0-9_\-]", "", (cv.student_name or "estudiante").replace(" ", "_")
    ) or "estudiante"
    filename = f"CV-{safe_name}-{datetime.utcnow().strftime('%Y%m%d')}.{extension}"
    logger.info(
        "cv generated user_id=%s fmt=%s size=%d", current_user.id, formato, len(contenido)
    )
    return Response(
        content=contenido,
        media_type=media_type,
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
        # Lo que decidió quitar. Iba implementado desde A3 pero no se devolvía,
        # así que la pantalla no tenía forma de mostrar qué estaba oculto ni de
        # revertirlo: sólo se podía usar armando un PUT a mano. Es el error nº1
        # del CLAUDE.md de este backend (un campo que nadie lee) y se cierra
        # aquí, en el mismo commit que su interfaz.
        "excluded": {
            "activity_ids": list(
                (getattr(perfil, "overrides", None) or {}).get("excluded_activity_ids")
                or []
            ),
            "test_ids": list(
                (getattr(perfil, "overrides", None) or {}).get("excluded_test_ids") or []
            ),
        },
        # Si el estudiante nunca pidió recomendaciones, `consolidated_profile`
        # no existe y la sección entera de Perfil sale vacía del PDF sin que
        # nada lo explique. Para un producto que promete armarte el CV con IA,
        # ese silencio es el peor síntoma posible: mejor decirlo.
        "perfil_generado": bool(cv.summary or cv.strengths or cv.interests or cv.values),
    }


@router_me.get("/profile", summary="A3 · datos y contenido editable de mi hoja de vida")
def get_cv_profile(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    cv, perfil = _armar_cv(db, current_user)
    return _serializar(cv, perfil)


class LinkedInImportRequest(BaseModel):
    """CV-2 · El texto que la persona copió de su propio perfil de LinkedIn."""

    profile_text: str = Field(..., min_length=1, max_length=20000)


@router_me.post(
    "/import-linkedin",
    summary="CV-2 · estructurar el perfil de LinkedIn que la persona pegó",
)
def import_linkedin(
    request: LinkedInImportRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve una PROPUESTA · no escribe la hoja de vida.

    Se pidió un scraper de LinkedIn. No se construyó como scraper: sus términos
    de servicio lo prohíben, y además no funcionaría con perfiles privados. En su
    lugar la persona pega su propio perfil y la IA lo estructura — mismo
    resultado, sin exponer a la agencia.

    **No aplica nada.** Devuelve un borrador para que lo revise y confirme con el
    `PUT /profile` de siempre. Es su hoja de vida y lleva su nombre; pisarla sin
    preguntar sería justo lo contrario de lo que pidió A3 ("debe poder editarse").
    """
    _solo_estudiantes(current_user)

    try:
        propuesta, meta = linkedin_import_service.importar_desde_texto(
            request.profile_text
        )
    except linkedin_import_service.LinkedInImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "linkedin_import_failed", "message": str(exc)},
        )

    # M-001 · todo consumo de IA queda auditado. Si falla el registro no se
    # pierde el trabajo que la persona ya esperó.
    try:
        record_ai_usage(
            db,
            provider="anthropic",
            user_id=current_user.id,
            feature="cv_linkedin_import",
            model=meta.get("model"),
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
        )
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo registrar el uso de IA de import-linkedin")

    return {
        "proposal": propuesta,
        # Listo para mandarlo tal cual al PUT /profile si la persona lo acepta.
        "suggested_overrides": linkedin_import_service.a_overrides(propuesta),
    }


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


# ===========================================================================
# La convocatoria · pegar una vacante/beca/programa y adaptar el CV a ella
# ===========================================================================
#
# Va encolado y no dentro del request porque son DOS llamadas al modelo
# (entender la convocatoria + adaptar la hoja de vida) y **Heroku corta a los
# 30 s**. Es el mismo mordisco que ya se llevó `recommendations.py` (fix
# 503/H12) y la misma solución: `BackgroundTasks` + polling.
#
# A diferencia de allá, aquí NO hace falta un diccionario `_GENERATING` como
# candado: el estado vive en la propia fila (`cv_targets.status`), que es
# durable y sobrevive a un reinicio del dyno. El lock en memoria de
# recommendations existía porque su resultado era un cache sin fila propia.

_MAX_TARGETS_POR_USUARIO = 20


def _serializar_target(t: CVTarget) -> dict:
    return {
        "id": str(t.id),
        "kind": t.kind,
        "title": t.title,
        "organization": t.organization,
        "status": t.status or "pending",
        "error": t.error,
        "parsed": t.parsed,
        "analysis": t.analysis,
        "proposal": t.proposal,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _analizar_target_bg(target_id: str, user_id: str) -> None:
    """Worker · sesión de DB propia porque la del request ya se cerró.

    `SessionLocal` se resuelve por el MÓDULO y no por el nombre importado
    arriba. No es un capricho de estilo: enlazarlo en el import deja el worker
    apuntando a la base real aunque los tests hayan sustituido la del módulo, y
    entonces esta función —la única que llama a la IA— es exactamente la que
    ningún test ejercita. Es el error nº2 del `CLAUDE.md` de este backend, y así
    se evita.
    """
    from app.db import database as dbmod

    db = dbmod.SessionLocal()
    target = None
    try:
        target = db.query(CVTarget).filter(CVTarget.id == UUID(target_id)).first()
        if target is None:
            return
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        if user is None:
            return

        target.status = "analyzing"
        db.commit()

        # --- 1. ¿Qué pide la convocatoria? --------------------------------
        parsed, meta_parse = cv_target_service.parsear(
            target.raw_text or "", session_id=target_id
        )
        target.parsed = parsed
        target.kind = parsed.get("kind")
        target.title = parsed.get("title")
        target.organization = parsed.get("organization")
        db.commit()

        # --- 2. ¿Cómo le va a ella con esto? ------------------------------
        cv, _perfil = _armar_cv(db, user)
        adaptacion, meta_tailor = cv_tailor_service.adaptar(
            cv=cv, parsed=parsed, session_id=target_id
        )

        target.analysis = {
            "ajuste": adaptacion.get("ajuste"),
            "resumen_ajuste": adaptacion.get("resumen_ajuste"),
            "faltantes": adaptacion.get("faltantes"),
            "sugerencias": adaptacion.get("sugerencias"),
            "destacar_actividades": adaptacion.get("destacar_actividades"),
        }
        # La propuesta viaja con forma de `overrides`: lista para el PUT
        # /profile de siempre si el estudiante la acepta. No se aplica sola.
        target.proposal = cv_tailor_service.a_overrides(adaptacion)
        target.status = "ready"
        target.error = None
        db.commit()

        # M-001 · las dos llamadas quedan auditadas. Si falla el registro no se
        # pierde el trabajo que la persona ya esperó.
        for feature, meta in (
            ("cv_target_parse", meta_parse),
            ("cv_tailor", meta_tailor),
        ):
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

    except Exception as exc:  # noqa: BLE001
        logger.warning("cv target analysis failed target_id=%s: %s", target_id, exc)
        if target is not None:
            try:
                target.status = "failed"
                # El mensaje llega a la pantalla del estudiante: los de
                # `CVTargetError`/`CVTailorError` están escritos para él.
                target.error = str(exc)[:500]
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
    finally:
        db.close()


class CVTargetRequest(BaseModel):
    """El texto de la convocatoria que la persona copió y pegó."""

    raw_text: str = Field(..., min_length=1, max_length=20000)


@router_me.post(
    "/targets",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Pegar una convocatoria y pedir que adaptemos el CV a ella",
    dependencies=[Depends(rate_limit("6/minute", scope="cv_target"))],
)
def crear_target(
    request: CVTargetRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Responde **202 de inmediato** y analiza en background.

    Devuelve la fila con `status="pending"`; la pantalla consulta
    `GET /targets/{id}` hasta que quede en `ready` o `failed`.
    """
    _solo_estudiantes(current_user)

    texto = (request.raw_text or "").strip()
    # Se valida ANTES de crear la fila y de encolar: decirle "muy corto" al
    # instante es mejor que crear un registro que va a fallar en 20 segundos.
    if len(texto) < cv_target_service.MIN_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "cv_target_too_short",
                "message": (
                    "Pega un poco más de la convocatoria: con tan poco texto no "
                    "puedo saber qué están pidiendo."
                ),
            },
        )

    cuantas = db.query(CVTarget).filter(CVTarget.user_id == current_user.id).count()
    if cuantas >= _MAX_TARGETS_POR_USUARIO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "cv_targets_limit",
                "message": (
                    f"Ya tienes {cuantas} convocatorias guardadas. Borra alguna "
                    "para analizar una nueva."
                ),
            },
        )

    target = CVTarget(
        user_id=current_user.id,
        raw_text=texto[: cv_target_service.MAX_CHARS],
        status="pending",
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    background_tasks.add_task(_analizar_target_bg, str(target.id), str(current_user.id))
    logger.info("cv target scheduled user_id=%s target_id=%s", current_user.id, target.id)

    return _serializar_target(target)


@router_me.get("/targets", summary="Mis convocatorias")
def listar_targets(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    filas = (
        db.query(CVTarget)
        .filter(CVTarget.user_id == current_user.id)
        .order_by(CVTarget.created_at.desc())
        .all()
    )
    return {"targets": [_serializar_target(t) for t in filas]}


def _mi_target(db: DBSession, user: User, target_id: str) -> CVTarget:
    """Busca la fila SIEMPRE filtrando por dueño · no por id a secas.

    Filtrar sólo por id dejaría leer la convocatoria de otro estudiante con
    adivinar un UUID. El 404 (y no 403) es deliberado: no confirma que el
    recurso exista.
    """
    try:
        uid = UUID(target_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no encontrada")

    target = (
        db.query(CVTarget)
        .filter(CVTarget.id == uid, CVTarget.user_id == user.id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no encontrada")
    return target


@router_me.get("/targets/{target_id}", summary="Estado y resultado de una convocatoria")
def ver_target(
    target_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    return _serializar_target(_mi_target(db, current_user, target_id))


@router_me.post(
    "/targets/{target_id}/apply",
    summary="Aplicar a mi hoja de vida la propuesta de esta convocatoria",
)
def aplicar_target(
    target_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Escribe la propuesta en los overrides · **sólo cuando el estudiante lo pide**.

    Hasta aquí nada se había guardado. Es el mismo principio de
    `linkedin_import_service`: es su hoja de vida y lleva su nombre, así que la
    IA propone y él decide.
    """
    _solo_estudiantes(current_user)
    target = _mi_target(db, current_user, target_id)

    if target.status != "ready" or not target.proposal:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "cv_target_not_ready",
                "message": "Esta convocatoria todavía no tiene una propuesta lista.",
            },
        )

    cv_profile_service.save_answers(db, current_user.id, overrides=target.proposal)
    cv, perfil = _armar_cv(db, current_user)
    return _serializar(cv, perfil)


@router_me.delete("/targets/{target_id}", summary="Borrar una convocatoria")
def borrar_target(
    target_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    target = _mi_target(db, current_user, target_id)
    db.delete(target)
    db.commit()
    return {"deleted": True}


# ===========================================================================
# La foto
# ===========================================================================

router_foto = APIRouter(prefix="/me", tags=["StudentMe · CV"])

_FOTO_MIMES = {"image/jpeg", "image/png", "image/webp"}
_FOTO_MAX_MB = 2


@router_foto.post(
    "/photo",
    summary="Subir mi foto para la hoja de vida",
    dependencies=[Depends(rate_limit("10/minute", scope="cv_photo"))],
)
async def subir_foto(
    request: Request,
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Copia el patrón de `school_panel.py::upload_logo`, con dos diferencias.

    **Sin SVG.** Allá se permite porque un logo institucional suele venir
    vectorial; una foto de una persona nunca lo es, y el SVG es el formato que
    puede traer script dentro.

    **Se guarda la RUTA, no la URL firmada.** Las URLs de Supabase caducan y
    persistirlas deja imágenes rotas — es el bug que arrastra `programs.py`.
    """
    _solo_estudiantes(current_user)

    if file.content_type not in _FOTO_MIMES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato no soportado: {file.content_type}. Usa JPG, PNG o WebP.",
        )

    datos = await file.read()
    if len(datos) > _FOTO_MAX_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"La foto pesa más de {_FOTO_MAX_MB} MB.",
        )

    # El content-type lo manda el cliente y se puede mentir: los magic bytes no.
    from app.core.file_validation import validate_image_bytes

    fv = validate_image_bytes(
        datos, allow_svg=False, max_bytes=_FOTO_MAX_MB * 1024 * 1024
    )
    if not fv.ok:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"El archivo no parece una imagen válida · {fv.reason}",
        )

    # Se guarda en la propia base (`user_photos`) y no en un bucket. El
    # `storage_service` de este proyecto corre contra un stub en memoria hasta
    # que alguien configure Supabase, así que la foto se perdía en cada
    # reinicio del dyno: la referencia sobrevivía y la imagen no.
    #
    # Guardar y reemplazar son la misma operación, así que no hay que borrar
    # nada antes ni queda basura si algo falla a medias.
    try:
        cv_photo_service.guardar(db, current_user.id, datos, file.content_type)
    except cv_photo_service.FotoDemasiadoGrande as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        )
    db.commit()

    logger.info("cv photo uploaded user_id=%s size=%d", current_user.id, len(datos))
    return {"tiene_foto": True}


@router_foto.delete("/photo", summary="Quitar mi foto")
def borrar_foto(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    cv_photo_service.borrar(db, current_user.id)
    db.commit()
    return {"tiene_foto": False}


# ===========================================================================
# El enlace público · nace apagado y así se queda
# ===========================================================================
#
# Los usuarios de esta plataforma son **menores de edad**. Una URL sin
# autenticación con su nombre y su colegio no es una decisión de ingeniería, así
# que se construye con cuatro candados:
#
#   1. `CV_PUBLIC_LINK_ENABLED` está en false y encenderlo lo decide la clienta.
#   2. Opt-in explícito del estudiante · `share_habilitado` arranca nulo.
#   3. La versión pública **no lleva foto ni correo**, aunque el CV sí los tenga.
#   4. Token de 32 bytes, revocable, y límite de tasa en la ruta abierta.

router_publico = APIRouter(prefix="/cv", tags=["CV público"])


def _link_publico_activo() -> bool:
    from app.config import get_settings

    return bool(get_settings().cv_public_link_enabled)


@router_me.post("/share", summary="Generar el enlace público de mi hoja de vida")
def crear_share(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    if not _link_publico_activo():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "cv_share_disabled",
                "message": "El enlace público no está habilitado en esta plataforma.",
            },
        )

    perfil = cv_profile_service.get_profile(db, current_user.id)
    if perfil is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Primero completa tu hoja de vida.",
        )

    # Se regenera en cada activación: si alguna vez lo revocó, el enlace viejo
    # no puede volver a funcionar por reactivar.
    perfil.share_token = secrets.token_urlsafe(32)
    perfil.share_habilitado = True
    perfil.share_creado_en = datetime.utcnow()
    db.commit()

    logger.info("cv share enabled user_id=%s", current_user.id)
    return {"share_token": perfil.share_token, "habilitado": True}


@router_me.delete("/share", summary="Revocar el enlace público")
def revocar_share(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiantes(current_user)
    perfil = cv_profile_service.get_profile(db, current_user.id)
    if perfil is not None:
        # Se borra el token además de apagar el flag: dejarlo guardado sería
        # dejar viva la llave de una puerta que se dijo cerrar.
        perfil.share_token = None
        perfil.share_habilitado = False
        db.commit()
    return {"habilitado": False}


@router_publico.get(
    "/p/{token}",
    summary="Ver una hoja de vida compartida · SIN autenticación",
    dependencies=[Depends(rate_limit("20/minute", scope="cv_publico"))],
)
def ver_cv_publico(token: str, db: DBSession = Depends(get_db)):
    """Sirve el HTML del CV · sin foto y sin correo.

    Devuelve 404 en todos los casos de fallo (apagado, token inexistente,
    revocado): distinguirlos permitiría enumerar tokens válidos.
    """
    from app.db.models import CVProfile

    generico = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no encontrada")

    if not _link_publico_activo() or not token or len(token) < 20:
        raise generico

    perfil = (
        db.query(CVProfile)
        .filter(CVProfile.share_token == token, CVProfile.share_habilitado.is_(True))
        .first()
    )
    if perfil is None:
        raise generico

    user = db.query(User).filter(User.id == perfil.user_id).first()
    if user is None:
        raise generico

    cv, _perfil = _armar_cv(db, user)

    # Lo que NO sale en la versión pública. Se apaga aquí, sobre el CVData ya
    # armado, y no confiando en un parámetro del renderizador: es un dato que se
    # borra, no una opción de formato.
    cv.email = None
    cv.photo_data_uri = None

    prefs = cv_profile_service.preferencias_formato(perfil)
    html = cv_pdf_service.render_cv_html(
        cv, estandar=prefs["estandar"], estilo=prefs["estilo"], incluir_foto=False
    )
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        # Que no lo indexen los buscadores es la mitad del punto de que sea "un
        # enlace que compartes", y no "una página pública".
        headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"},
    )
