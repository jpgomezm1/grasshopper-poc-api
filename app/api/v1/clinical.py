"""Clinical toolkit endpoints · GH-ADVISOR-CLINICAL · 2026-05-04.

All endpoints under `/api/v1/gh/students/{user_id}/...` and `/api/v1/gh/sessions/...`
are restricted to gh_advisor + super_admin (NEVER gh_commercial · NEVER student).

GH-PSY-CLINICAL · 2026-05-05 update: school **psychologist** also has access,
scoped to students of their own school (`student.school_id == user.school_id`).
This lets the same clinical UI power both the GH advisor (external orientation
team) and the school psychologist (internal staff member) without duplicating
backend code.

Visibility matrix:
- super_admin   · all students.
- gh_advisor    · B2C (school_id=NULL) OR contact_requested.
- psychologist  · student.school_id == user.school_id (same school).
- gh_commercial · 403 (NEVER · commercial role does not see clinical data).
- school_admin  · 403 here (uses school_admin/parent endpoints instead).
- student/parent· 403.

For sessions, psychologists see ONLY sessions where they are the advisor (i.e.
sessions they themselves created in the school context). This is implemented in
`orientation_session_service` via `can_view_session`.

Bloques:
  A · Dossier (CRUD notes + GET full dossier)
  B · Psychometrics (GET full cross view)
  C+D · Clinical analysis (POST generate · GET cached)
  E · Sessions (CRUD + notes CRUD)
  F · Recomendaciones con interpretación clínica
  G · Comparador de finalistas
  H · PDF clínico
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import (
    DOSSIER_SECTIONS,
    OrientationSession,
    SessionNote,
    StudentDossierNote,
    User,
    UserRole,
)
from app.schemas.clinical import (
    ClinicalAnalysisResponse,
    ClinicalPdfRequestIn,
    ClinicalRecommendationsResponse,
    DossierNoteCreateIn,
    DossierNoteOut,
    DossierNoteUpdateIn,
    DossierResponse,
    FinalistsRequestIn,
    FinalistsResponse,
    PsychometricsResponse,
    SessionCreateIn,
    SessionListResponse,
    SessionNoteCreateIn,
    SessionNoteOut,
    SessionNotePatchIn,
    SessionOut,
    SessionPatchIn,
)
from app.services import (
    clinical_analysis_service,
    clinical_pdf_service,
    clinical_recommendations_service,
    dossier_service,
    finalists_service,
    orientation_session_service,
    psychometrics_service,
)
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gh", tags=["GH Advisor · Clinical"])


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _require_clinical_role(user: User) -> None:
    """Allow gh_advisor · psychologist · super_admin.

    GH-PSY-CLINICAL · 2026-05-05 · psychologist joined the clinical surface,
    scoped to their own school (enforced by `_resolve_student_in_scope`).
    """
    if user.role not in (
        UserRole.GH_ADVISOR,
        UserRole.PSYCHOLOGIST,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · clinical surface only for gh_advisor, psychologist or super_admin.",
        )


# Backwards-compat alias used by existing call-sites in this module.
_require_advisor_or_super = _require_clinical_role


def _can_access_clinical_data(user: User, student: User) -> bool:
    """Centralized clinical access predicate.

    Used by endpoints that resolve a single student. Mirrors the visibility
    matrix declared at the top of this module.
    """
    if user.role == UserRole.SUPER_ADMIN:
        return True
    if user.role == UserRole.GH_ADVISOR:
        # B2C (no school) OR opted-in B2B
        return student.school_id is None or student.gh_contact_requested_at is not None
    if user.role == UserRole.PSYCHOLOGIST:
        # Same-school scope · psy must belong to a school AND match the student's
        return (
            user.school_id is not None
            and student.school_id is not None
            and student.school_id == user.school_id
        )
    return False


def _resolve_student_in_scope(
    db: DBSession, user_id: UUID, current_user: User
) -> User:
    """Fetch student + apply scope rules per role (advisor/psy/super_admin)."""
    student = (
        db.query(User)
        .filter(User.id == user_id, User.role == UserRole.STUDENT, User.is_active.is_(True))
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if not _can_access_clinical_data(current_user, student):
        raise HTTPException(
            status_code=403,
            detail="Forbidden · this student is not in your clinical scope.",
        )
    return student


# ---------------------------------------------------------------------------
# Bloque A · Dossier
# ---------------------------------------------------------------------------


@router.get(
    "/students/{user_id}/dossier",
    response_model=DossierResponse,
    summary="GH-ADVISOR-CLINICAL · A · structured dossier of a student",
)
def get_dossier(
    user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    return dossier_service.build_dossier(db, student)


@router.post(
    "/students/{user_id}/dossier/notes",
    response_model=DossierNoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="GH-ADVISOR-CLINICAL · A · create dossier note",
)
def create_dossier_note(
    user_id: UUID,
    body: DossierNoteCreateIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    if body.section not in DOSSIER_SECTIONS:
        raise HTTPException(status_code=400, detail="Invalid section.")
    note = dossier_service.create_note(
        db, student=student, advisor=current_user,
        section=body.section, content=body.content,
    )
    log_action(
        db,
        user=current_user,
        action="dossier.note_created",
        resource_type="student_dossier_note",
        resource_id=str(note.id),
        payload={"student_user_id": str(student.id), "section": body.section},
        commit=True,
    )
    return DossierNoteOut(
        id=note.id,
        section=note.section,  # type: ignore[arg-type]
        content=note.content,
        advisor_user_id=note.advisor_user_id,
        advisor_name=current_user.name or current_user.email,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _get_note_or_404(db: DBSession, note_id: UUID) -> StudentDossierNote:
    note = db.query(StudentDossierNote).filter(StudentDossierNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")
    return note


@router.patch(
    "/students/{user_id}/dossier/notes/{note_id}",
    response_model=DossierNoteOut,
    summary="GH-ADVISOR-CLINICAL · A · edit dossier note",
)
def patch_dossier_note(
    user_id: UUID,
    note_id: UUID,
    body: DossierNoteUpdateIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    note = _get_note_or_404(db, note_id)
    if note.student_user_id != student.id:
        raise HTTPException(status_code=404, detail="Note not found for this student.")
    # Only author or super_admin can edit
    if current_user.role != UserRole.SUPER_ADMIN and note.advisor_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can edit this note.")
    note = dossier_service.update_note(db, note=note, content=body.content)
    log_action(
        db,
        user=current_user,
        action="dossier.note_updated",
        resource_type="student_dossier_note",
        resource_id=str(note.id),
        payload={"student_user_id": str(student.id)},
        commit=True,
    )
    advisor_name = None
    if note.advisor_user_id:
        adv = db.query(User).filter(User.id == note.advisor_user_id).first()
        if adv:
            advisor_name = adv.name or adv.email
    return DossierNoteOut(
        id=note.id,
        section=note.section,  # type: ignore[arg-type]
        content=note.content,
        advisor_user_id=note.advisor_user_id,
        advisor_name=advisor_name,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.delete(
    "/students/{user_id}/dossier/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="GH-ADVISOR-CLINICAL · A · delete dossier note (author only)",
)
def delete_dossier_note(
    user_id: UUID,
    note_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    note = _get_note_or_404(db, note_id)
    if note.student_user_id != student.id:
        raise HTTPException(status_code=404, detail="Note not found for this student.")
    if current_user.role != UserRole.SUPER_ADMIN and note.advisor_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can delete this note.")
    dossier_service.delete_note(db, note=note)
    log_action(
        db,
        user=current_user,
        action="dossier.note_deleted",
        resource_type="student_dossier_note",
        resource_id=str(note_id),
        payload={"student_user_id": str(student.id)},
        commit=True,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Bloque B · Psychometrics
# ---------------------------------------------------------------------------


@router.get(
    "/students/{user_id}/psychometrics",
    response_model=PsychometricsResponse,
    summary="GH-ADVISOR-CLINICAL · B · cross-test psychometrics view",
)
def get_psychometrics(
    user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    return psychometrics_service.build_psychometrics(db, student)


# ---------------------------------------------------------------------------
# Bloque C+D · Clinical analysis
# ---------------------------------------------------------------------------


@router.get(
    "/students/{user_id}/clinical-analysis",
    response_model=ClinicalAnalysisResponse,
    summary="GH-ADVISOR-CLINICAL · C · cached clinical analysis (or empty)",
)
def get_clinical_analysis(
    user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    cached = clinical_analysis_service.get_cached(student)
    reason = clinical_analysis_service.insufficient_inputs_reason(db, student)
    return ClinicalAnalysisResponse(
        student_user_id=student.id,
        analysis=cached,
        cached=cached is not None,
        cached_at=student.clinical_analysis_cached_at,
        stale=clinical_analysis_service.is_stale(student),
        has_inputs=reason is None,
        insufficient_inputs_reason=reason,
    )


@router.post(
    "/students/{user_id}/clinical-analysis",
    response_model=ClinicalAnalysisResponse,
    summary="GH-ADVISOR-CLINICAL · C · generate / regenerate clinical analysis",
)
def generate_clinical_analysis(
    user_id: UUID,
    force: bool = Query(False, description="Force regeneration ignoring cache"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    try:
        analysis = clinical_analysis_service.generate(db, student, force=force)
    except clinical_analysis_service.ClinicalAnalysisFailure as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    log_action(
        db,
        user=current_user,
        action="clinical_analysis.generated",
        resource_type="user",
        resource_id=str(student.id),
        payload={"force": force, "patterns": [p.pattern for p in analysis.behavioral_patterns]},
        commit=True,
    )
    return ClinicalAnalysisResponse(
        student_user_id=student.id,
        analysis=analysis,
        cached=False,
        cached_at=student.clinical_analysis_cached_at,
        stale=False,
        has_inputs=True,
    )


# ---------------------------------------------------------------------------
# Bloque E · Sessions
# ---------------------------------------------------------------------------


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="GH-ADVISOR-CLINICAL · E · list orientation sessions",
)
def list_sessions(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    advisor_user_id: Optional[UUID] = Query(None),
    student_user_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    _require_advisor_or_super(current_user)
    try:
        rows, total = orientation_session_service.list_sessions(
            db,
            current_user=current_user,
            advisor_user_id=advisor_user_id,
            student_user_id=student_user_id,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    items = orientation_session_service.hydrate_sessions(db, rows)
    return SessionListResponse(items=items, total=total)


@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="GH-ADVISOR-CLINICAL · E · create orientation session",
)
def create_session(
    body: SessionCreateIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    # Validate student in scope (advisor can only schedule with their scope)
    student = _resolve_student_in_scope(db, body.student_user_id, current_user)
    try:
        sess = orientation_session_service.create_session(
            db,
            advisor=current_user,
            student_user_id=student.id,
            scheduled_at=body.scheduled_at,
            duration_min=body.duration_min,
            type=body.type,
            status=body.status,
            summary=body.summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_action(
        db,
        user=current_user,
        action="orientation_session.created",
        resource_type="orientation_session",
        resource_id=str(sess.id),
        payload={"student_user_id": str(student.id), "type": body.type},
        commit=True,
    )
    out = orientation_session_service.hydrate_sessions(db, [sess])
    return out[0]


def _get_session_or_404(
    db: DBSession, session_id: UUID, current_user: User
) -> OrientationSession:
    sess = orientation_session_service.get_session(db, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not orientation_session_service.can_view_session(sess, current_user):
        raise HTTPException(status_code=403, detail="Forbidden · session not in your scope.")
    return sess


@router.get(
    "/sessions/{session_id}",
    response_model=SessionOut,
    summary="GH-ADVISOR-CLINICAL · E · session detail",
)
def get_session_detail(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    sess = _get_session_or_404(db, session_id, current_user)
    out = orientation_session_service.hydrate_sessions(db, [sess])
    return out[0]


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionOut,
    summary="GH-ADVISOR-CLINICAL · E · patch session",
)
def patch_session(
    session_id: UUID,
    body: SessionPatchIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    sess = _get_session_or_404(db, session_id, current_user)
    if not orientation_session_service.can_edit_session(sess, current_user):
        raise HTTPException(status_code=403, detail="Forbidden · cannot edit this session.")
    try:
        sess = orientation_session_service.patch_session(
            db,
            sess,
            scheduled_at=body.scheduled_at,
            duration_min=body.duration_min,
            type=body.type,
            status=body.status,
            summary=body.summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    out = orientation_session_service.hydrate_sessions(db, [sess])
    return out[0]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="GH-ADVISOR-CLINICAL · E · delete session",
)
def delete_session(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    sess = _get_session_or_404(db, session_id, current_user)
    if not orientation_session_service.can_edit_session(sess, current_user):
        raise HTTPException(status_code=403, detail="Forbidden · cannot delete this session.")
    orientation_session_service.delete_session(db, sess)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Session notes ---------------------------------------------------------


@router.get(
    "/sessions/{session_id}/notes",
    response_model=List[SessionNoteOut],
    summary="GH-ADVISOR-CLINICAL · E · list notes for a session (privacy-gated)",
)
def list_session_notes(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    sess = _get_session_or_404(db, session_id, current_user)
    notes = orientation_session_service.list_notes(db, session_id, current_user)
    advisor_ids = {n.advisor_user_id for n in notes if n.advisor_user_id}
    advisors_by_id = {}
    if advisor_ids:
        for u in db.query(User).filter(User.id.in_(advisor_ids)).all():
            advisors_by_id[u.id] = u.name or u.email
    return [
        orientation_session_service.note_to_out(n, advisors_by_id.get(n.advisor_user_id))
        for n in notes
    ]


@router.post(
    "/sessions/{session_id}/notes",
    response_model=SessionNoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="GH-ADVISOR-CLINICAL · E · create note on session",
)
def create_session_note(
    session_id: UUID,
    body: SessionNoteCreateIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    sess = _get_session_or_404(db, session_id, current_user)
    # Only advisor of the session (or super_admin) can add notes
    if current_user.role != UserRole.SUPER_ADMIN and sess.advisor_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden · only the session advisor adds notes.")
    try:
        note = orientation_session_service.create_note(
            db, sess=sess, advisor=current_user,
            content=body.content, privacy=body.privacy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_action(
        db,
        user=current_user,
        action="session_note.created",
        resource_type="session_note",
        resource_id=str(note.id),
        payload={"session_id": str(sess.id), "privacy": body.privacy},
        commit=True,
    )
    return orientation_session_service.note_to_out(
        note, current_user.name or current_user.email
    )


def _get_note_or_404_session(
    db: DBSession, note_id: UUID, sess: OrientationSession
) -> SessionNote:
    note = db.query(SessionNote).filter(SessionNote.id == note_id).first()
    if not note or note.session_id != sess.id:
        raise HTTPException(status_code=404, detail="Note not found.")
    return note


@router.patch(
    "/sessions/{session_id}/notes/{note_id}",
    response_model=SessionNoteOut,
    summary="GH-ADVISOR-CLINICAL · E · edit note",
)
def patch_session_note(
    session_id: UUID,
    note_id: UUID,
    body: SessionNotePatchIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    sess = _get_session_or_404(db, session_id, current_user)
    note = _get_note_or_404_session(db, note_id, sess)
    if not orientation_session_service.can_edit_note(note, current_user):
        raise HTTPException(status_code=403, detail="Only the author can edit.")
    try:
        note = orientation_session_service.patch_note(
            db, note, content=body.content, privacy=body.privacy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    advisor_name = None
    if note.advisor_user_id:
        adv = db.query(User).filter(User.id == note.advisor_user_id).first()
        if adv:
            advisor_name = adv.name or adv.email
    return orientation_session_service.note_to_out(note, advisor_name)


@router.delete(
    "/sessions/{session_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="GH-ADVISOR-CLINICAL · E · delete note",
)
def delete_session_note(
    session_id: UUID,
    note_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    sess = _get_session_or_404(db, session_id, current_user)
    note = _get_note_or_404_session(db, note_id, sess)
    if not orientation_session_service.can_edit_note(note, current_user):
        raise HTTPException(status_code=403, detail="Only the author can delete.")
    orientation_session_service.delete_note(db, note)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Bloque F · Recomendaciones con interpretación clínica
# ---------------------------------------------------------------------------


@router.get(
    "/students/{user_id}/recommendations-clinical",
    response_model=ClinicalRecommendationsResponse,
    summary="GH-ADVISOR-CLINICAL · F · top 5 recomendaciones con interpretación clínica",
)
def get_clinical_recommendations(
    user_id: UUID,
    top_n: int = Query(5, ge=1, le=10),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    return clinical_recommendations_service.build_clinical_recommendations(db, student, top_n=top_n)


# ---------------------------------------------------------------------------
# Bloque G · Comparador finalistas
# ---------------------------------------------------------------------------


@router.post(
    "/students/{user_id}/finalists",
    response_model=FinalistsResponse,
    summary="GH-ADVISOR-CLINICAL · G · side-by-side comparator of 2-3 finalists",
)
def post_finalists(
    user_id: UUID,
    body: FinalistsRequestIn,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)
    student = _resolve_student_in_scope(db, user_id, current_user)
    return finalists_service.build_finalists(
        db,
        student=student,
        program_ids=body.program_ids,
        advisor_pros_cons=body.advisor_pros_cons,
    )


# ---------------------------------------------------------------------------
# Bloque H · PDF clínico
# ---------------------------------------------------------------------------


@router.post(
    "/students/{user_id}/clinical-pdf",
    summary="GH-ADVISOR-CLINICAL · H · generate clinical PDF (8-12 páginas · advisor-only)",
)
def post_clinical_pdf(
    user_id: UUID,
    body: ClinicalPdfRequestIn = ClinicalPdfRequestIn(),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_advisor_or_super(current_user)

    # GH-LOCAL-QA-RONDA2 · B-014 · feature flag guard.
    # WeasyPrint needs GTK runtime (libgobject/cairo/pango). On Windows dev
    # boxes those libs aren't installed by default and the original 500 stack
    # trace was leaking confusing internals. Now we short-circuit with a 503
    # when the deploy explicitly disables the feature.
    if not get_settings().clinical_pdf_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Clinical PDF generation disabled on this deploy "
                "(GTK runtime not available)"
            ),
        )

    student = _resolve_student_in_scope(db, user_id, current_user)

    dossier = dossier_service.build_dossier(db, student)
    psy = psychometrics_service.build_psychometrics(db, student)
    analysis = clinical_analysis_service.get_cached(student)
    recs = clinical_recommendations_service.build_clinical_recommendations(db, student)

    finalists = None
    # Need at least 2 program_ids to render a meaningful comparator
    if body and body.program_ids and len(body.program_ids) >= 2:
        finalists = finalists_service.build_finalists(
            db,
            student=student,
            program_ids=body.program_ids,
            advisor_pros_cons=body.advisor_pros_cons,
        )

    student_name = student.name or student.email
    advisor_name = current_user.name or current_user.email

    try:
        pdf_bytes = clinical_pdf_service.render_clinical_pdf(
            student_name=student_name,
            advisor_name=advisor_name,
            dossier=dossier,
            psy=psy,
            analysis=analysis,
            recs=recs,
            finalists=finalists,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    log_action(
        db,
        user=current_user,
        action="clinical_pdf.generated",
        resource_type="user",
        resource_id=str(student.id),
        payload={"size_bytes": len(pdf_bytes)},
        commit=True,
    )

    filename = f"clinical-{(student_name or 'estudiante').replace(' ', '_')}-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
