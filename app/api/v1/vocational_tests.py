from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, VocationalTestResult
from app.data.disclaimer import DISCLAIMER_TEXT, DISCLAIMER_VERSION
from app.data.vocational_tests import (
    get_all_tests_summary,
    get_test_by_id,
    calculate_vocational_scores,
    disponible_para_grado,
    VOCATIONAL_TESTS,
)
from app.services.scoring_service import derive_test_extras
from app.services import (
    parental_consent_service,
    test_interpretation_service,
    vocational_bank_selector,
)

router = APIRouter(prefix="/vocational-tests", tags=["Vocational Tests"])


class SubmitVocationalRequest(BaseModel):
    answers: dict


def _disclaimer_accepted(user: User, test_id: str) -> bool:
    """F-005 · ¿el estudiante aceptó la versión VIGENTE del aviso para este test?

    Compara la versión aceptada con `DISCLAIMER_VERSION`: si el texto legal
    cambió (bump de versión), la aceptación vieja deja de contar y se re-pide.
    """
    entry = (user.test_disclaimers or {}).get(test_id)
    return bool(entry) and entry.get("version") == DISCLAIMER_VERSION


@router.get("")
def list_tests(current_user: User = Depends(get_current_user)):
    # La descripción de Holland cambia según el grado (9°/10° ven la versión
    # con lenguaje de su edad). El resto de tests sale igual que siempre.
    return vocational_bank_selector.resumen_tests_para_usuario(current_user)


# Static routes MUST come before /{test_id} to avoid path conflicts
@router.get("/results/all")
def get_all_results(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    results = db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == current_user.id
    ).all()

    output = []
    for r in results:
        raw_scores = dict(r.scores or {})
        extras = raw_scores.pop("_extras", None)
        item = {
            "test_id": r.test_id,
            "scores": raw_scores,
            "completed_at": r.created_at.isoformat(),
        }
        if extras is not None:
            item["extras"] = extras
        output.append(item)
    return output


# F-005 · disclaimer pre-test. Static route ANTES de /{test_id}.
@router.get("/disclaimer/status")
def get_disclaimer_status(current_user: User = Depends(get_current_user)):
    """Texto vigente del aviso legal + qué tests ya aceptó el estudiante."""
    accepted = current_user.test_disclaimers or {}
    return {
        "version": DISCLAIMER_VERSION,
        "text": DISCLAIMER_TEXT,
        # Solo cuenta como aceptado si coincide con la versión vigente (si el
        # texto cambió, el front lo verá como NO aceptado y re-pedirá la firma).
        "accepted": {
            tid: meta.get("accepted_at")
            for tid, meta in accepted.items()
            if isinstance(meta, dict) and meta.get("version") == DISCLAIMER_VERSION
        },
    }


@router.post("/{test_id}/accept-disclaimer")
def accept_disclaimer(
    test_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Registra la aceptación del aviso legal para un tipo de test."""
    if not get_test_by_id(test_id):
        raise HTTPException(status_code=404, detail="Test not found")

    # Reasignar un dict nuevo para que SQLAlchemy detecte el cambio del JSON.
    data = dict(current_user.test_disclaimers or {})
    data[test_id] = {
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "version": DISCLAIMER_VERSION,
    }
    current_user.test_disclaimers = data
    db.commit()
    return {
        "test_id": test_id,
        "accepted_at": data[test_id]["accepted_at"],
        "version": DISCLAIMER_VERSION,
    }


@router.get("/{test_id}")
def get_test(test_id: str, current_user: User = Depends(get_current_user)):
    # Único punto donde se elige el banco de preguntas. Para Holland, grados
    # 9° y 10° reciben la redacción adaptada a 13-14 años; el instrumento es el
    # mismo (mismos ids de ítem, misma dimensión, mismo puntaje), sólo cambia
    # cómo está escrito cada enunciado.
    test = vocational_bank_selector.test_para_usuario(test_id, current_user)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return test


@router.post("/{test_id}/submit")
def submit_test(
    test_id: str,
    request: SubmitVocationalRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    test = get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Malla completa · un instrumento que pertenece a una sola ruta (hoy el Mapeo
    # de Habilidades Blandas, grado 10) no se contesta desde otra ruta: si sólo se
    # filtrara el listado, bastaría con entrar por la URL directa.
    #
    # Excepción deliberada, alineada con "MEMORIA SÍ, LLAVE NO": quien YA tiene un
    # resultado puede repetirlo aunque haya pasado de grado. Bloquearle rehacer algo
    # que ya hizo sería una llave, y no se construyeron llaves. Nótese que leer el
    # resultado viejo (`GET /{id}` y `/{id}/result`) nunca se bloquea, por lo mismo.
    if not disponible_para_grado(
        test, vocational_bank_selector.grado_del_estudiante(current_user)
    ):
        ya_lo_habia_hecho = (
            db.query(VocationalTestResult)
            .filter(
                VocationalTestResult.user_id == current_user.id,
                VocationalTestResult.test_id == test_id,
            )
            .first()
        )
        if not ya_lo_habia_hecho:
            # 404 y no 403: para este estudiante el test no existe en su ruta, y
            # el front ya trata el 403 como "falta aceptar el aviso legal".
            raise HTTPException(status_code=404, detail="Test not found")

    # M-006 · gate: menor de 16 (edad conocida) sin consentimiento parental.
    # Va ANTES del disclaimer: un menor no debe avanzar a ningún paso del test
    # (ni al aviso) hasta tener el consentimiento del acudiente.
    if parental_consent_service.needs_parental_consent(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="minor_parental_consent_required",
        )

    # F-005 · gate legal: exige aceptación del aviso antes de registrar el test.
    if not _disclaimer_accepted(current_user, test_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes aceptar el aviso legal antes de enviar este test.",
        )

    scores = calculate_vocational_scores(test_id, request.answers)
    extras = derive_test_extras(test_id, request.answers)

    # Persist extras inside the JSON ``scores`` column so we don't need a
    # migration. Shape stays backward compatible: legacy tests keep the
    # category->percentage map; MBTI/iStrong add an ``_extras`` key.
    persisted_scores = dict(scores)
    if extras is not None:
        persisted_scores["_extras"] = extras

    existing = db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == current_user.id,
        VocationalTestResult.test_id == test_id,
    ).first()

    if existing:
        existing.answers = request.answers
        existing.scores = persisted_scores
    else:
        result = VocationalTestResult(
            user_id=current_user.id,
            test_id=test_id,
            answers=request.answers,
            scores=persisted_scores,
        )
        db.add(result)

    db.commit()

    # GH-S6 · invalidate the consolidated profile cache so the next
    # `GET /recommendations/me` regenerates with the new test data.
    try:
        from app.services.consolidation_service import invalidate_cache
        invalidate_cache(db, current_user.id)
    except Exception:
        # Never block the test submission for a cache invalidation failure
        pass

    response = {"test_id": test_id, "scores": scores}
    if extras is not None:
        response["extras"] = extras
    return response


@router.get("/{test_id}/result")
def get_test_result(
    test_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    result = db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == current_user.id,
        VocationalTestResult.test_id == test_id,
    ).first()

    if not result:
        return None

    raw_scores = dict(result.scores or {})
    extras = raw_scores.pop("_extras", None)

    payload = {
        "test_id": result.test_id,
        "scores": raw_scores,
        "answers": result.answers,
        "completed_at": result.created_at.isoformat(),
    }
    if extras is not None:
        payload["extras"] = extras
    return payload


# ---------------------------------------------------------------------------
# P1-1 · Lectura narrativa del resultado (feedback A1)
# ---------------------------------------------------------------------------


@router.get("/{test_id}/interpretation")
def get_test_interpretation(
    test_id: str,
    force: bool = False,
    only_cached: bool = False,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Explicación en prosa del resultado de este test para ESTE estudiante.

    Feedback A1: "cada test tiene que darle más información al estudiante y su
    familia". Se genera bajo demanda la primera vez y se cachea contra el hash de
    los scores: si el estudiante repite el test, se regenera sola.

    Si la IA falla, responde 200 con `available: false` en vez de romper: el
    resultado del test (los puntajes, las barras) tiene que seguir viéndose.
    """
    result = (
        db.query(VocationalTestResult)
        .filter(
            VocationalTestResult.user_id == current_user.id,
            VocationalTestResult.test_id == test_id,
        )
        .first()
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todavía no has completado este test.",
        )

    test = get_test_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Test no encontrado."
        )

    # P1-2 · El snapshot y los PDFs piden `only_cached=true`: nunca deben disparar
    # una generación. Si se dejara generar, descargar un reporte con 4 tests tardaría
    # minutos y costaría IA en cada clic.
    if only_cached:
        cacheada = test_interpretation_service.get_cached(result)
        if cacheada is None:
            return {"available": False, "interpretation": None}
        return {"available": True, "interpretation": cacheada}

    try:
        data = test_interpretation_service.generate(
            db,
            result,
            test_name=test.get("name") or test_id,
            test_description=test.get("description") or "",
            user=current_user,
            force=force,
        )
    except test_interpretation_service.TestInterpretationUnavailable:
        return {"available": False, "interpretation": None}

    return {
        "available": True,
        "interpretation": data,
        "generated_at": (
            result.interpretation_generated_at.isoformat()
            if result.interpretation_generated_at
            else None
        ),
    }


# ---------------------------------------------------------------------------
# A6 · Autoanálisis del estudiante después de ver su resultado
#
# Feedback literal de la clienta (el único punto que escribió EN MAYÚSCULAS):
#   "ESTO NO ESTÁ FUNCIONANDO: una vez realizo un test de orientación, no me
#    pregunta: según el conocimiento que adquieres de ti mismo con el último
#    test realizado, ¿qué carreras profesionales piensas que se acomodan a tus
#    valores, habilidades e intereses? Escribe 3 opciones, siendo 1 la que más
#    se acomoda. Porque con ese autoanálisis el sistema debería ofrecerle
#    opciones según su top-3 y/o según lo que la IA considera del test."
# ---------------------------------------------------------------------------


class SelfAssessmentRequest(BaseModel):
    """Las 3 carreras que el estudiante cree que le encajan, EN ORDEN."""

    careers: list[str]


def _find_result(db: DBSession, user_id, test_id: str) -> VocationalTestResult:
    result = (
        db.query(VocationalTestResult)
        .filter(
            VocationalTestResult.user_id == user_id,
            VocationalTestResult.test_id == test_id,
        )
        .first()
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todavía no has completado este test.",
        )
    return result


@router.get("/{test_id}/self-assessment")
def get_self_assessment(
    test_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Lo que el estudiante respondió para ESTE test, más lo último que dijo en otro.

    `previous_careers` existe para pre-llenar el formulario. Ella también criticó
    la fatiga de cuestionarios, así que después del segundo test no se le pide
    escribir tres carreras desde cero: se le muestra lo que dijo antes y ajusta.
    """
    result = _find_result(db, current_user.id, test_id)

    ultima_en_otro_test = None
    previas = (
        db.query(VocationalTestResult)
        .filter(
            VocationalTestResult.user_id == current_user.id,
            VocationalTestResult.test_id != test_id,
            VocationalTestResult.self_assessment.isnot(None),
        )
        .all()
    )
    # Orden en Python y no en SQL: self_assessment_at puede ser NULL en filas
    # viejas y el orden de los NULL difiere entre SQLite y Postgres.
    previas.sort(key=lambda r: r.self_assessment_at or datetime.min, reverse=True)
    for r in previas:
        if isinstance(r.self_assessment, dict) and r.self_assessment.get("careers"):
            ultima_en_otro_test = r.self_assessment["careers"]
            break

    propia = result.self_assessment if isinstance(result.self_assessment, dict) else {}
    return {
        "careers": propia.get("careers") or [],
        "answered_at": (
            result.self_assessment_at.isoformat() if result.self_assessment_at else None
        ),
        "previous_careers": ultima_en_otro_test or [],
    }


@router.put("/{test_id}/self-assessment")
def save_self_assessment(
    test_id: str,
    request: SelfAssessmentRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Guarda el top-3 declarado. El ORDEN importa: "siendo 1 la que más se acomoda"."""
    result = _find_result(db, current_user.id, test_id)

    limpias = [c.strip() for c in (request.careers or []) if c and c.strip()][:3]
    if not limpias:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Escribe al menos una opción.",
        )

    result.self_assessment = {"careers": limpias}
    result.self_assessment_at = datetime.utcnow()
    db.commit()

    # El autoanálisis alimenta el perfil consolidado y las recomendaciones. Si no
    # se invalida la caché, el perfil seguiría sin conocerlo hasta que expire el
    # TTL — y el estudiante vería recomendaciones que ignoran lo que acaba de
    # escribir, que es exactamente lo que ella está reclamando.
    try:
        from app.services import consolidation_service

        invalidar = getattr(consolidation_service, "invalidate_cache", None)
        if callable(invalidar):
            invalidar(db, current_user.id)
    except Exception:  # pragma: no cover - la caché expira sola
        pass

    return {
        "careers": limpias,
        "answered_at": result.self_assessment_at.isoformat(),
    }
