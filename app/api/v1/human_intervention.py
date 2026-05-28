"""F-006 · Human intervention notes (advisor-only) · 2026-05-28.

Cliente docx §3: notas privadas que solo el advisor asignado al lead puede
ver para anotar qué tan cerca está de cerrar el contrato de Counselling
Premium. NUNCA visible para el student, el psy ni otros advisors.

Endpoints (todos /gh-prefixed):
    GET  /gh/students/{student_id}/intervention-notes
    PUT  /gh/students/{student_id}/intervention-notes
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import HumanInterventionNote, User, UserRole
from app.schemas.human_intervention import (
    HumanInterventionNoteOut,
    HumanInterventionNoteUpdate,
)
from app.services.auth_service import get_current_user


router = APIRouter(prefix="/gh/students", tags=["F-006 · Human Intervention"])


def _require_owner_advisor_or_super_admin(
    student: User, current_user: User
) -> None:
    """Solo el advisor asignado al student o super_admin pueden ver/editar."""
    if current_user.role == UserRole.SUPER_ADMIN:
        return
    if current_user.role != UserRole.GH_ADVISOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · intervention notes are advisor-only",
        )
    assigned = getattr(student, "assigned_to_user_id", None)
    if assigned is None or assigned != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · only the assigned advisor can access these notes",
        )


def _load_student(db: DBSession, student_id: UUID) -> User:
    student = db.query(User).filter(User.id == student_id).first()
    if student is None or student.role != UserRole.STUDENT:
        raise HTTPException(status_code=404, detail="student not found")
    return student


@router.get(
    "/{student_id}/intervention-notes",
    response_model=HumanInterventionNoteOut,
    summary="F-006 · read advisor-private intervention notes",
)
def get_notes(
    student_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _load_student(db, student_id)
    _require_owner_advisor_or_super_admin(student, current_user)

    obj = (
        db.query(HumanInterventionNote)
        .filter(HumanInterventionNote.user_id == student_id)
        .first()
    )
    if obj is None:
        # empty placeholder so FE can render the form
        return HumanInterventionNoteOut(
            user_id=student_id,
            notes=None,
            closeness_level=None,
            updated_by_user_id=None,
            updated_at=datetime.utcnow(),
        )
    return HumanInterventionNoteOut.model_validate(obj)


@router.put(
    "/{student_id}/intervention-notes",
    response_model=HumanInterventionNoteOut,
    summary="F-006 · upsert advisor-private intervention notes",
)
def upsert_notes(
    student_id: UUID,
    body: HumanInterventionNoteUpdate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = _load_student(db, student_id)
    _require_owner_advisor_or_super_admin(student, current_user)

    obj = (
        db.query(HumanInterventionNote)
        .filter(HumanInterventionNote.user_id == student_id)
        .first()
    )
    if obj is None:
        obj = HumanInterventionNote(
            user_id=student_id,
            notes=body.notes,
            closeness_level=body.closeness_level,
            updated_by_user_id=current_user.id,
        )
        db.add(obj)
    else:
        obj.notes = body.notes
        obj.closeness_level = body.closeness_level
        obj.updated_by_user_id = current_user.id
    db.commit()
    db.refresh(obj)
    return HumanInterventionNoteOut.model_validate(obj)
