from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, EnglishTestResult
from app.data.english_test_questions import (
    ENGLISH_TEST_QUESTIONS,
    calculate_score,
    get_questions_for_client,
    placement_for,
)

router = APIRouter(prefix="/english-test", tags=["English Test"])


class SubmitAnswersRequest(BaseModel):
    answers: dict


class SectionScoreResponse(BaseModel):
    correct: int
    total: int
    percentage: int


class TestResultResponse(BaseModel):
    score: int
    total_questions: int
    percentage: int
    cefr_level: str
    section_scores: dict
    # A5 · La ubicación que da el instrumento de la agencia. Sin estos campos la
    # tarjeta "Según el examen de ubicación de AMES" del front era código muerto:
    # `calculate_score` los producía y este modelo los descartaba en silencio.
    # Son opcionales porque los resultados guardados con el banco viejo de 20
    # preguntas no tienen puntaje comparable contra la tabla de 60.
    ielts_equivalent: str | None = None
    class_placement: str | None = None
    instrument: str | None = None


@router.get("/questions")
def get_questions(current_user: User = Depends(get_current_user)):
    return get_questions_for_client()


@router.post("/submit", response_model=TestResultResponse)
def submit_test(
    request: SubmitAnswersRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    existing = db.query(EnglishTestResult).filter(
        EnglishTestResult.user_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="English test already completed",
        )

    result = calculate_score(request.answers)

    test_result = EnglishTestResult(
        user_id=current_user.id,
        answers=request.answers,
        score=result["score"],
        total_questions=result["total_questions"],
        cefr_level=result["cefr_level"],
        section_scores=result["section_scores"],
    )
    db.add(test_result)

    current_user.english_test_completed = True
    current_user.english_cefr_level = result["cefr_level"]

    db.commit()

    return TestResultResponse(
        score=result["score"],
        total_questions=result["total_questions"],
        percentage=result["percentage"],
        cefr_level=result["cefr_level"],
        section_scores=result["section_scores"],
        ielts_equivalent=result.get("ielts_equivalent"),
        class_placement=result.get("class_placement"),
        instrument=result.get("instrument"),
    )


@router.get("/result")
def get_result(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    result = db.query(EnglishTestResult).filter(
        EnglishTestResult.user_id == current_user.id
    ).first()

    if not result:
        return None

    total = result.total_questions
    percentage = round((result.score / total) * 100) if total > 0 else 0

    respuesta = {
        "score": result.score,
        "total_questions": total,
        "percentage": percentage,
        "cefr_level": result.cefr_level,
        "section_scores": result.section_scores,
    }

    # A5 · La ubicación de AMES se recalcula desde el puntaje en vez de guardarse
    # (no hace falta migración: es una función pura de `score`).
    #
    # SOLO si el resultado es del examen de 60. Los guardados con el banco viejo
    # de 20 preguntas inventadas no son comparables contra esta tabla: un 15/20
    # leído como 15/60 diría "Pre intermedio" cuando fue un 75%. Ahí se omite y el
    # front simplemente no muestra la tarjeta.
    if total == len(ENGLISH_TEST_QUESTIONS):
        ubicacion = placement_for(result.score)
        # Solo los dos campos nuevos. NO se pisa `cefr_level` con el recalculado:
        # el guardado es el que quedó en `user.english_cefr_level` y el que filtra
        # programas, así que mostrar otro dejaría al estudiante viendo un nivel
        # distinto al que el sistema usa para recomendarle.
        respuesta["ielts_equivalent"] = ubicacion["ielts_equivalent"]
        respuesta["class_placement"] = ubicacion["class_placement"]
        respuesta["instrument"] = "AMES English Placement Test"

    return respuesta
