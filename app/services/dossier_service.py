"""Dossier service · gh_advisor clinical toolkit · GH-ADVISOR-CLINICAL Bloque A.

Responsibilities:
- Build the structured dossier payload for a student combining:
    * computed demographics (from User row + journey answers)
    * advisor-authored notes per section (`student_dossier_notes`)
    * declared aspirations (from onboarding answers · journey)
    * inferred aspirations (from cached consolidated_profile)
    * raw journey answers (so UI can surface family/hobbies/academic when present)
- Audit every CRUD action via the existing audit_service.

Privacy: dossier is never visible to the student. PII guard: never log
`content` body in stdout.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    DOSSIER_SECTIONS,
    ConsolidatedProfileCache,
    School,
    Session,
    StudentDossierNote,
    User,
    VocationalTestResult,
)
from app.schemas.clinical import (
    DossierAspirations,
    DossierDemographics,
    DossierNoteOut,
    DossierResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calc_age(birthdate: Optional[date]) -> Optional[int]:
    if not birthdate:
        return None
    today = date.today()
    years = today.year - birthdate.year
    if (today.month, today.day) < (birthdate.month, birthdate.day):
        years -= 1
    return max(0, years)


def _is_minor(birthdate: Optional[date]) -> Optional[bool]:
    age = _calc_age(birthdate)
    if age is None:
        return None
    return age < 18


def _latest_session_answers(db: DBSession, user_id: UUID) -> Dict[str, Any]:
    sess = (
        db.query(Session)
        .filter(Session.user_id == user_id)
        .order_by(Session.updated_at.desc())
        .first()
    )
    return (sess.answers if sess and sess.answers else {}) or {}


def _get_combined_answers(db: DBSession, student: User) -> Dict[str, Any]:
    """Merge `session.answers` (primary) with `user.onboarding_answers` (fallback).

    GH-LOCAL-QA-RONDA2 · B-015 · 2026-05-21 · cuando un estudiante terminó el
    onboarding pero no inició la sesión del journey (caso común en test data
    + usuarios reales que aún no avanzaron al journey), `session.answers` es
    `{}`. Para que el dossier muestre datos demográficos en lugar de campos
    null, combinamos ambas fuentes. `session.answers` tiene prioridad sobre
    `user.onboarding_answers` para keys overlapping — el journey gana cuando
    el usuario actualiza durante la sesión.
    """
    session_answers = _latest_session_answers(db, student.id)
    onboarding = dict(getattr(student, "onboarding_answers", None) or {})
    return {**onboarding, **session_answers}


def _build_demographics(
    db: DBSession, student: User, school: Optional[School]
) -> DossierDemographics:
    answers = _get_combined_answers(db, student)
    return DossierDemographics(
        name=student.name,
        email=student.email,
        age=_calc_age(getattr(student, "birthdate", None)),
        grade=str(answers.get("grade") or answers.get("currentGrade") or "") or None,
        city=str(answers.get("city") or "") or None,
        country=str(answers.get("country") or "") or None,
        school_name=school.name if school else None,
        english_cefr_level=student.english_cefr_level,
        english_test_completed=bool(student.english_test_completed),
        onboarding_status=(
            student.onboarding_status.value
            if student.onboarding_status is not None
            and hasattr(student.onboarding_status, "value")
            else str(student.onboarding_status or "not_started")
        ),
        budget_band=student.budget_band,
        budget_max_usd=student.budget_max_usd,
        preferred_countries=list(student.preferred_countries or []),
        is_minor=_is_minor(getattr(student, "birthdate", None)),
    )


def _build_aspirations(
    db: DBSession, student: User
) -> Tuple[DossierAspirations, bool, Optional[Dict[str, Any]]]:
    """Returns (aspirations, has_consolidated_profile, profile_dict).

    GH-LOCAL-QA-RONDA2 · B-017 · 2026-05-21 · agregamos `declaredAspirations`
    a las keys que recolectamos (proveniente del nuevo step del journey
    "¿qué te ves haciendo en 5 años?"). También combinamos session.answers
    con user.onboarding_answers para usuarios que aún no completaron journey
    pero ya completaron onboarding.
    """
    answers = _get_combined_answers(db, student)
    declared: List[str] = []
    # Capture any free-form aspiration fields from onboarding or journey
    for key in (
        "declaredAspirations",  # B-017 · nueva pregunta del journey
        "aspirations",
        "dreamCareer",
        "dream_career",
        "topInterests",
        "interests",
        "favoriteSubjects",
    ):
        val = answers.get(key)
        if isinstance(val, str) and val.strip():
            declared.append(val.strip())
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v.strip():
                    declared.append(v.strip())

    inferred: List[str] = []
    profile_dict: Optional[Dict[str, Any]] = None
    cache = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == student.id)
        .first()
    )
    has_profile = False
    if cache and cache.invalidated_at is None and cache.profile_data:
        has_profile = True
        try:
            profile_dict = dict(cache.profile_data)
            paths = profile_dict.get("suggested_career_paths") or []
            for p in paths:
                if isinstance(p, str) and p.strip():
                    inferred.append(p.strip())
        except Exception:
            pass

    return (
        DossierAspirations(declared=declared, inferred=inferred),
        has_profile,
        profile_dict,
    )


def _note_to_out(
    note: StudentDossierNote, advisor_name: Optional[str] = None
) -> DossierNoteOut:
    return DossierNoteOut(
        id=note.id,
        section=note.section,  # type: ignore[arg-type]
        content=note.content,
        advisor_user_id=note.advisor_user_id,
        advisor_name=advisor_name,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_dossier(db: DBSession, student: User) -> DossierResponse:
    """Compose full dossier payload."""
    school: Optional[School] = None
    if student.school_id:
        school = db.query(School).filter(School.id == student.school_id).first()

    demographics = _build_demographics(db, student, school)
    aspirations, has_profile, _profile = _build_aspirations(db, student)
    answers = _latest_session_answers(db, student.id)

    notes = (
        db.query(StudentDossierNote)
        .filter(StudentDossierNote.student_user_id == student.id)
        .order_by(StudentDossierNote.section.asc(), StudentDossierNote.created_at.desc())
        .all()
    )
    advisor_ids = {n.advisor_user_id for n in notes if n.advisor_user_id is not None}
    advisors_by_id: Dict[UUID, str] = {}
    if advisor_ids:
        for u in db.query(User).filter(User.id.in_(advisor_ids)).all():
            advisors_by_id[u.id] = u.name or u.email

    notes_by_section: Dict[str, List[DossierNoteOut]] = {s: [] for s in DOSSIER_SECTIONS}
    for n in notes:
        sect = n.section
        if sect not in notes_by_section:
            # Tolerate unknown sections (shouldn't happen but be defensive).
            notes_by_section[sect] = []
        notes_by_section[sect].append(
            _note_to_out(n, advisors_by_id.get(n.advisor_user_id))
        )

    tests_count = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == student.id)
        .count()
    )

    return DossierResponse(
        student_user_id=student.id,
        demographics=demographics,
        notes_by_section=notes_by_section,
        aspirations=aspirations,
        journey_answers=answers,
        has_consolidated_profile=has_profile,
        tests_completed_count=tests_count,
    )


def create_note(
    db: DBSession,
    student: User,
    advisor: User,
    section: str,
    content: str,
) -> StudentDossierNote:
    if section not in DOSSIER_SECTIONS:
        raise ValueError(f"Invalid section: {section}")
    note = StudentDossierNote(
        student_user_id=student.id,
        advisor_user_id=advisor.id,
        section=section,
        content=content,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def update_note(
    db: DBSession,
    note: StudentDossierNote,
    content: str,
) -> StudentDossierNote:
    note.content = content
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return note


def delete_note(db: DBSession, note: StudentDossierNote) -> None:
    db.delete(note)
    db.commit()
