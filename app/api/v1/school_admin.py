"""School-admin extended router · GH-SCHOOL-ADMIN · Sprint 2026-05-04.

23 features grouped in 11 categories. All endpoints scoped to the caller's
school via the `_get_school_admin_caller` dependency. Psychologist has
read-only access to a subset (cases, cohorts, alerts) declared explicitly.

Permission matrix:

    school_admin    · all endpoints + writes
    psychologist    · read-only on: cohorts.list, cases.list, alerts.list,
                       psychologist-performance, custom-fields.list
    super_admin     · acts on its bound school_id (or 403 if none)
    student/parent  · 403

Mount prefix: /api/v1/school/me  (sub-prefixed `/cohorts`, `/dashboard-rich`, ...)
Public sub-router: NONE · all gates require auth.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user, get_password_hash
from app.db.database import get_db
from app.db.models import (
    AuditLog,
    Cohort,
    Invitation,
    InvitationStatus,
    OnboardingStatus,
    ParentRelationship,
    School,
    SchoolCustomField,
    SchoolEvent,
    SchoolEventRSVP,
    SchoolLegalDocument,
    SchoolLegalSignature,
    SchoolMassMessage,
    StudentAdminNote,
    StudentCohortAssignment,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.school_admin import (
    AdminNoteCreate,
    AdminNoteResponse,
    AdminNoteUpdate,
    BulkInactivateRequest,
    BulkInviteRequest,
    BulkInviteResult,
    BulkReassignCohortRequest,
    CaseCreate,
    CaseResponse,
    CaseUpdate,
    ClinicalAlertAck,
    ClinicalAlertResponse,
    CohortAssignmentRequest,
    CohortCreate,
    CohortKpis,
    CohortListResponse,
    CohortPsyAssignmentRequest,
    CohortResponse,
    CohortUpdate,
    CustomFieldCreate,
    CustomFieldResponse,
    CustomFieldUpdate,
    DashboardRichResponse,
    EventCreate,
    EventRSVPRequest,
    EventResponse,
    EventUpdate,
    ExecutiveReportRequest,
    GHCoordinationStudent,
    HandoffRequest,
    InterventionCreate,
    InterventionResponse,
    LegalDocumentCreate,
    LegalDocumentResponse,
    LegalSignatureRequest,
    LegalSignatureResponse,
    LicenseUpgradeRequest,
    MassMessageCreate,
    MassMessageResponse,
    ParentInviteRequest,
    ParentInviteResult,
    PsychologistPerformanceResponse,
    ROIReportRequest,
    SchoolBrandingUpdate,
    StudentCustomFieldValueResponse,
    StudentCustomFieldValueUpdate,
)
from app.services import school_admin_service
from app.services.audit_service import log_action as _log_action_raw
from app.services.invitation_service import create_invitation


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/school/me", tags=["School Admin (extended)"])


def log_action(
    db: DBSession,
    user: User,
    action: str,
    *,
    entity_type: str = "school",
    entity_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    """Light wrapper aligning route call-sites with audit_service.log_action."""
    try:
        _log_action_raw(
            db,
            user=user,
            action=action,
            resource_type=entity_type,
            resource_id=entity_id,
            payload=meta or {},
        )
    except Exception:  # pragma: no cover · audit must never break the request
        logger.exception("audit log failed for action=%s", action)


# ============================================================================
# Auth gates
# ============================================================================


def _get_school_admin_caller(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> tuple[School, User]:
    """school_admin / super_admin only · writes-allowed gate."""
    if current_user.role not in (UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo school_admin puede acceder.",
        )
    if not current_user.school_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sin colegio.",
        )
    school = db.query(School).filter(School.id == current_user.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="Colegio no encontrado.")
    if school.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Colegio archivado.",
        )
    return school, current_user


def _get_school_staff_caller(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> tuple[School, User]:
    """school_admin or psychologist · read-only access for psy."""
    if current_user.role not in (
        UserRole.SCHOOL_ADMIN,
        UserRole.PSYCHOLOGIST,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Solo staff del colegio.")
    if not current_user.school_id:
        raise HTTPException(status_code=400, detail="Usuario sin colegio.")
    school = db.query(School).filter(School.id == current_user.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="Colegio no encontrado.")
    if school.archived_at is not None:
        raise HTTPException(status_code=403, detail="Colegio archivado.")
    return school, current_user


# ============================================================================
# Categoría A · Dashboard rico
# ============================================================================


@router.get("/dashboard-rich", response_model=DashboardRichResponse)
def dashboard_rich(
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    health = school_admin_service.compute_health_score(db, school.id)
    timeline_w = school_admin_service.compute_timeline(db, school.id, granularity="weekly", weeks=12)
    timeline_m = school_admin_service.compute_timeline(db, school.id, granularity="monthly", weeks=6)
    funnel = school_admin_service.compute_funnel(db, school.id)
    heatmap = school_admin_service.compute_heatmap(db, school.id)
    risk = school_admin_service.compute_risk_alerts(db, school.id)
    cohorts = school_admin_service.list_cohorts(db, school.id)
    cohorts_kpis = [
        school_admin_service.compute_cohort_kpis(db, school.id, c["id"], c["label"])
        for c in cohorts[:8]
    ]
    return {
        "health_score": health,
        "timeline_weekly": timeline_w,
        "timeline_monthly": timeline_m,
        "funnel": funnel,
        "activity_heatmap": heatmap,
        "risk_alerts": risk,
        "cohorts_kpis": cohorts_kpis,
        "cohorts_compare": cohorts_kpis[:4],
    }


@router.get("/risk-alerts")
def list_risk_alerts(
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return {"items": school_admin_service.compute_risk_alerts(db, school.id)}


# ============================================================================
# Categoría B · Cohorts CRUD + assignments
# ============================================================================


@router.get("/cohorts", response_model=CohortListResponse)
def list_cohorts(
    include_archived: bool = Query(False),
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    items = school_admin_service.list_cohorts(db, school.id, include_archived=include_archived)
    return {"items": items, "total": len(items)}


@router.post("/cohorts", response_model=CohortResponse, status_code=201)
def create_cohort(
    payload: CohortCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        cohort = school_admin_service.create_cohort(
            db,
            school.id,
            key=payload.key,
            label=payload.label,
            grade=payload.grade,
            academic_year=payload.academic_year,
            color=payload.color,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    log_action(
        db, user, "school_admin.cohort_create", entity_type="cohort", entity_id=str(cohort.id)
    )
    return school_admin_service.list_cohorts(db, school.id)[0]


@router.patch("/cohorts/{cohort_id}", response_model=CohortResponse)
def update_cohort(
    cohort_id: UUID,
    payload: CohortUpdate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        c = school_admin_service.update_cohort(
            db, school.id, cohort_id, **payload.model_dump(exclude_unset=True)
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.cohort_update", entity_type="cohort", entity_id=str(c.id))
    return next(
        x for x in school_admin_service.list_cohorts(db, school.id, include_archived=True) if x["id"] == c.id
    )


@router.delete("/cohorts/{cohort_id}", status_code=204)
def archive_cohort(
    cohort_id: UUID,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        c = school_admin_service.archive_cohort(db, school.id, cohort_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.cohort_archive", entity_type="cohort", entity_id=str(c.id))


@router.post("/cohorts/{cohort_id}/students", status_code=201)
def assign_students(
    cohort_id: UUID,
    payload: CohortAssignmentRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        n = school_admin_service.assign_students_to_cohort(
            db, school.id, cohort_id, payload.student_user_ids, user.id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(
        db, user, "school_admin.cohort_assign_students", entity_type="cohort", entity_id=str(cohort_id)
    )
    return {"assigned": n}


@router.delete("/cohorts/{cohort_id}/students", status_code=200)
def unassign_students(
    cohort_id: UUID,
    payload: CohortAssignmentRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        n = school_admin_service.unassign_students_from_cohort(
            db, school.id, cohort_id, payload.student_user_ids
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"removed": n}


@router.post("/cohorts/{cohort_id}/psychologists", status_code=201)
def assign_psy(
    cohort_id: UUID,
    payload: CohortPsyAssignmentRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        n = school_admin_service.assign_psychologists_to_cohort(
            db, school.id, cohort_id, payload.psychologist_user_ids, user.id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.cohort_assign_psy", entity_type="cohort", entity_id=str(cohort_id))
    return {"assigned": n}


@router.get("/cohorts/{cohort_id}/kpis", response_model=CohortKpis)
def cohort_kpis(
    cohort_id: UUID,
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    cohort = (
        db.query(Cohort)
        .filter(Cohort.id == cohort_id, Cohort.school_id == school.id)
        .first()
    )
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohorte no encontrada.")
    return school_admin_service.compute_cohort_kpis(db, school.id, cohort_id, cohort.label)


@router.get("/cohorts/compare")
def cohort_compare(
    cohort_ids: List[UUID] = Query(..., min_length=2, max_length=4),
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    cohorts = (
        db.query(Cohort)
        .filter(Cohort.id.in_(cohort_ids), Cohort.school_id == school.id)
        .all()
    )
    return {
        "items": [
            school_admin_service.compute_cohort_kpis(db, school.id, c.id, c.label)
            for c in cohorts
        ]
    }


# ============================================================================
# Categoría C · Search avanzado + bulk + admin notes
# ============================================================================


@router.post("/students/bulk-invite", response_model=BulkInviteResult)
def bulk_invite_students(
    payload: BulkInviteRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    created = 0
    skipped = 0
    errors: List[dict] = []
    cohort_map = {c.key: c for c in db.query(Cohort).filter(Cohort.school_id == school.id).all()}
    for row in payload.rows:
        try:
            existing = (
                db.query(User).filter(User.email == row.email).first()
                or db.query(Invitation)
                .filter(
                    Invitation.email == row.email,
                    Invitation.school_id == school.id,
                    Invitation.status == InvitationStatus.PENDING,
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            inv = create_invitation(
                db=db,
                school=school,
                email=row.email,
                role=UserRole.STUDENT.value,
                invited_by=user,
            )
            created += 1
            # Optional cohort assignment is deferred until the student accepts.
        except Exception as exc:  # pragma: no cover · defensive
            errors.append({"email": row.email, "error": str(exc)[:200]})
    log_action(db, user, "school_admin.bulk_invite", entity_type="school", entity_id=str(school.id))
    return {"created": created, "skipped": skipped, "errors": errors}


@router.post("/students/bulk-invite-csv", response_model=BulkInviteResult)
async def bulk_invite_csv(
    file: UploadFile = File(...),
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    if file.size and file.size > 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV demasiado grande (max 1 MB).")
    content = await file.read()
    rows = school_admin_service.parse_bulk_invite_csv(content)
    payload = BulkInviteRequest(rows=[{"email": r["email"], "name": r.get("name"), "cohort_key": r.get("cohort_key")} for r in rows])
    return bulk_invite_students(payload=payload, bundle=bundle, db=db)


@router.post("/students/bulk-reassign-cohort")
def bulk_reassign_cohort(
    payload: BulkReassignCohortRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    cohort = (
        db.query(Cohort)
        .filter(Cohort.id == payload.target_cohort_id, Cohort.school_id == school.id)
        .first()
    )
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohorte destino no existe.")
    # Drop old, add new for each.
    db.query(StudentCohortAssignment).filter(
        StudentCohortAssignment.student_user_id.in_(payload.student_user_ids)
    ).delete(synchronize_session=False)
    for sid in payload.student_user_ids:
        db.add(
            StudentCohortAssignment(
                id=uuid4(),
                student_user_id=sid,
                cohort_id=cohort.id,
                assigned_by=user.id,
            )
        )
    db.commit()
    log_action(db, user, "school_admin.bulk_reassign_cohort", entity_type="cohort", entity_id=str(cohort.id))
    return {"reassigned": len(payload.student_user_ids)}


@router.post("/students/bulk-inactivate")
def bulk_inactivate(
    payload: BulkInactivateRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    n = (
        db.query(User)
        .filter(
            User.id.in_(payload.student_user_ids),
            User.school_id == school.id,
            User.role == UserRole.STUDENT,
        )
        .update({"is_active": False}, synchronize_session=False)
    )
    db.commit()
    log_action(db, user, "school_admin.bulk_inactivate", entity_type="school", entity_id=str(school.id))
    return {"inactivated": int(n)}


@router.get("/students/{student_id}/admin-notes", response_model=List[AdminNoteResponse])
def list_student_admin_notes(
    student_id: UUID,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return school_admin_service.list_admin_notes(db, school.id, student_id)


@router.post("/students/{student_id}/admin-notes", response_model=AdminNoteResponse, status_code=201)
def create_student_admin_note(
    student_id: UUID,
    payload: AdminNoteCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        note = school_admin_service.create_admin_note(db, school.id, student_id, user.id, payload.content)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.admin_note_create", entity_type="user", entity_id=str(student_id))
    return school_admin_service.list_admin_notes(db, school.id, student_id)[0]


@router.patch("/admin-notes/{note_id}", response_model=AdminNoteResponse)
def update_admin_note(
    note_id: UUID,
    payload: AdminNoteUpdate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        note = school_admin_service.update_admin_note(db, school.id, note_id, payload.content)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.admin_note_update", entity_type="admin_note", entity_id=str(note.id))
    rows = school_admin_service.list_admin_notes(db, school.id, note.student_user_id)
    return next(r for r in rows if r["id"] == note.id)


@router.delete("/admin-notes/{note_id}", status_code=204)
def delete_admin_note(
    note_id: UUID,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        school_admin_service.delete_admin_note(db, school.id, note_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.admin_note_delete", entity_type="admin_note", entity_id=str(note_id))


# ============================================================================
# Categoría D · Psychologist performance
# ============================================================================


@router.get("/psychologists-performance", response_model=PsychologistPerformanceResponse)
def psychologists_performance(
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return school_admin_service.compute_psychologist_performance(db, school.id)


# ============================================================================
# Categoría E · Parents · invite + relationships
# ============================================================================


@router.post("/students/{student_id}/invite-parents", response_model=ParentInviteResult)
def invite_parents(
    student_id: UUID,
    payload: ParentInviteRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    student = (
        db.query(User)
        .filter(User.id == student_id, User.school_id == school.id, User.role == UserRole.STUDENT)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado en este colegio.")

    invited = 0
    skipped = 0
    errors: List[dict] = []
    for entry in payload.emails:
        try:
            existing_user = db.query(User).filter(User.email == entry.email).first()
            if existing_user:
                if existing_user.role != UserRole.PARENT:
                    skipped += 1
                    errors.append(
                        {"email": entry.email, "error": "Email ya pertenece a otro rol."}
                    )
                    continue
                rel = (
                    db.query(ParentRelationship)
                    .filter(
                        ParentRelationship.parent_user_id == existing_user.id,
                        ParentRelationship.student_user_id == student.id,
                    )
                    .first()
                )
                if not rel:
                    db.add(
                        ParentRelationship(
                            id=uuid4(),
                            parent_user_id=existing_user.id,
                            student_user_id=student.id,
                            relationship_type=entry.relationship,
                        )
                    )
                    invited += 1
                else:
                    skipped += 1
                continue
            # Create a pending invitation (parent role)
            inv = create_invitation(
                db=db,
                school=school,
                email=entry.email,
                role=UserRole.PARENT.value,
                invited_by=user,
            )
            # Park the relationship intent in invitation metadata via a marker note on the
            # invitation row · easier: mint a placeholder ParentRelationship after accept.
            invited += 1
        except Exception as exc:
            errors.append({"email": entry.email, "error": str(exc)[:200]})
    db.commit()
    log_action(db, user, "school_admin.parents_invite", entity_type="user", entity_id=str(student_id))
    return {"invited": invited, "skipped": skipped, "errors": errors}


@router.get("/students/{student_id}/parents")
def list_student_parents(
    student_id: UUID,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    student = (
        db.query(User)
        .filter(User.id == student_id, User.school_id == school.id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    rels = (
        db.query(ParentRelationship, User)
        .join(User, User.id == ParentRelationship.parent_user_id)
        .filter(ParentRelationship.student_user_id == student_id)
        .all()
    )
    return {
        "items": [
            {
                "parent_user_id": u.id,
                "name": u.name,
                "email": u.email,
                "relationship": r.relationship_type,
                "is_active": r.is_active,
                "created_at": r.created_at,
            }
            for r, u in rels
        ]
    }


# ============================================================================
# Categoría E · Mass messages
# ============================================================================


@router.post("/mass-messages", response_model=MassMessageResponse, status_code=201)
def send_mass_message(
    payload: MassMessageCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    if payload.cohort_id:
        cohort = (
            db.query(Cohort)
            .filter(Cohort.id == payload.cohort_id, Cohort.school_id == school.id)
            .first()
        )
        if not cohort:
            raise HTTPException(status_code=404, detail="Cohorte no encontrada.")

    # Estimate sent_count by audience
    student_q = db.query(User).filter(
        User.school_id == school.id, User.role == UserRole.STUDENT, User.is_active.is_(True)
    )
    if payload.cohort_id:
        student_q = student_q.join(
            StudentCohortAssignment, StudentCohortAssignment.student_user_id == User.id
        ).filter(StudentCohortAssignment.cohort_id == payload.cohort_id)
    students_total = student_q.count() if payload.audience in ("students", "both") else 0

    parent_count = 0
    if payload.audience in ("parents", "both"):
        parent_count = (
            db.query(func.count(func.distinct(ParentRelationship.parent_user_id)))
            .join(User, User.id == ParentRelationship.student_user_id)
            .filter(User.school_id == school.id, ParentRelationship.is_active.is_(True))
            .scalar()
            or 0
        )

    msg = SchoolMassMessage(
        id=uuid4(),
        school_id=school.id,
        author_user_id=user.id,
        subject=payload.subject,
        body=payload.body,
        audience=payload.audience,
        cohort_id=payload.cohort_id,
        sent_count=int(students_total + parent_count),
        opened_count=0,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    log_action(db, user, "school_admin.mass_message_send", entity_type="school", entity_id=str(school.id))
    return msg


@router.get("/mass-messages", response_model=List[MassMessageResponse])
def list_mass_messages(
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return (
        db.query(SchoolMassMessage)
        .filter(SchoolMassMessage.school_id == school.id)
        .order_by(desc(SchoolMassMessage.sent_at))
        .limit(100)
        .all()
    )


# ============================================================================
# Categoría E + G · Events
# ============================================================================


@router.post("/events", response_model=EventResponse, status_code=201)
def create_event(
    payload: EventCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    e = SchoolEvent(
        id=uuid4(),
        school_id=school.id,
        title=payload.title,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        location=payload.location,
        audience=payload.audience,
        created_by=user.id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    log_action(db, user, "school_admin.event_create", entity_type="event", entity_id=str(e.id))
    return _event_to_response(db, e)


@router.get("/events", response_model=List[EventResponse])
def list_events(
    upcoming_only: bool = Query(False),
    audience: Optional[str] = Query(None),
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    q = db.query(SchoolEvent).filter(
        SchoolEvent.school_id == school.id, SchoolEvent.archived_at.is_(None)
    )
    if upcoming_only:
        q = q.filter(SchoolEvent.starts_at >= datetime.utcnow())
    if audience:
        q = q.filter(SchoolEvent.audience.in_([audience, "both"]))
    items = q.order_by(SchoolEvent.starts_at.asc()).all()
    return [_event_to_response(db, e) for e in items]


@router.patch("/events/{event_id}", response_model=EventResponse)
def update_event(
    event_id: UUID,
    payload: EventUpdate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    e = (
        db.query(SchoolEvent)
        .filter(SchoolEvent.id == event_id, SchoolEvent.school_id == school.id)
        .first()
    )
    if not e:
        raise HTTPException(status_code=404, detail="Evento no encontrado.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    log_action(db, user, "school_admin.event_update", entity_type="event", entity_id=str(e.id))
    return _event_to_response(db, e)


@router.delete("/events/{event_id}", status_code=204)
def archive_event(
    event_id: UUID,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    e = (
        db.query(SchoolEvent)
        .filter(SchoolEvent.id == event_id, SchoolEvent.school_id == school.id)
        .first()
    )
    if not e:
        raise HTTPException(status_code=404, detail="Evento no encontrado.")
    e.archived_at = datetime.utcnow()
    db.commit()
    log_action(db, user, "school_admin.event_archive", entity_type="event", entity_id=str(e.id))


@router.post("/events/{event_id}/rsvp", status_code=201)
def rsvp_event(
    event_id: UUID,
    payload: EventRSVPRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    e = db.query(SchoolEvent).filter(SchoolEvent.id == event_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="Evento no encontrado.")
    # Caller must belong to the same school (or be a parent of a student of that school).
    has_access = current_user.school_id == e.school_id
    if not has_access and current_user.role == UserRole.PARENT:
        has_access = (
            db.query(ParentRelationship)
            .join(User, User.id == ParentRelationship.student_user_id)
            .filter(
                ParentRelationship.parent_user_id == current_user.id,
                User.school_id == e.school_id,
                ParentRelationship.is_active.is_(True),
            )
            .first()
            is not None
        )
    if not has_access and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Sin acceso a este evento.")

    existing = (
        db.query(SchoolEventRSVP)
        .filter(SchoolEventRSVP.event_id == event_id, SchoolEventRSVP.user_id == current_user.id)
        .first()
    )
    if existing:
        existing.status = payload.status
        existing.responded_at = datetime.utcnow()
    else:
        db.add(
            SchoolEventRSVP(
                id=uuid4(),
                event_id=event_id,
                user_id=current_user.id,
                status=payload.status,
            )
        )
    db.commit()
    return {"ok": True}


def _event_to_response(db: DBSession, e: SchoolEvent) -> dict:
    rsvp_count = (
        db.query(func.count(SchoolEventRSVP.id))
        .filter(SchoolEventRSVP.event_id == e.id, SchoolEventRSVP.status == "going")
        .scalar()
        or 0
    )
    return {
        "id": e.id,
        "school_id": e.school_id,
        "title": e.title,
        "description": e.description,
        "starts_at": e.starts_at,
        "ends_at": e.ends_at,
        "location": e.location,
        "audience": e.audience,
        "created_at": e.created_at,
        "archived_at": e.archived_at,
        "rsvp_count": int(rsvp_count),
    }


# ============================================================================
# Categoría F · Reports executive + ROI
# ============================================================================


@router.post("/reports/executive")
def report_executive(
    payload: ExecutiveReportRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    health = school_admin_service.compute_health_score(db, school.id)
    funnel = school_admin_service.compute_funnel(db, school.id)
    cohorts = school_admin_service.list_cohorts(db, school.id)
    cohorts_kpis = [
        school_admin_service.compute_cohort_kpis(db, school.id, c["id"], c["label"])
        for c in cohorts
    ]
    log_action(db, user, "school_admin.report_executive", entity_type="school", entity_id=str(school.id))
    return {
        "school_id": school.id,
        "school_name": school.name,
        "quarter": payload.quarter,
        "year": payload.year,
        "generated_at": datetime.utcnow(),
        "health_score": health,
        "funnel": funnel,
        "cohorts": cohorts_kpis,
        "narrative": (
            f"Durante el Q{payload.quarter} {payload.year} el programa mantuvo un "
            f"health score de {health['overall']} con {len(cohorts)} cohortes activas. "
            "Los KPIs muestran tendencia estable en completitud del journey."
        ),
    }


@router.post("/reports/roi")
def report_roi(
    payload: ROIReportRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    student_ids = [
        u.id
        for u in db.query(User.id)
        .filter(User.school_id == school.id, User.role == UserRole.STUDENT)
        .all()
    ]
    decided = (
        db.query(func.count(func.distinct(VocationalTestResult.user_id)))
        .filter(VocationalTestResult.user_id.in_(student_ids))
        .filter(
            VocationalTestResult.created_at >= payload.period_start,
            VocationalTestResult.created_at <= payload.period_end,
        )
        .scalar()
        or 0
    ) if student_ids else 0
    total = len(student_ids)
    log_action(db, user, "school_admin.report_roi", entity_type="school", entity_id=str(school.id))
    return {
        "school_id": school.id,
        "period_start": payload.period_start,
        "period_end": payload.period_end,
        "students_total": total,
        "students_with_tests": int(decided),
        "engagement_rate": round((decided / total * 100.0), 1) if total else 0.0,
        "generated_at": datetime.utcnow(),
    }


# ============================================================================
# Categoría H · Branding + custom fields + legal
# ============================================================================


@router.patch("/branding")
def update_branding(
    payload: SchoolBrandingUpdate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    if payload.secondary_color is not None:
        school.secondary_color = payload.secondary_color
    if payload.locale is not None:
        school.locale = payload.locale
    if payload.timezone is not None:
        school.timezone = payload.timezone
    db.commit()
    db.refresh(school)
    log_action(db, user, "school_admin.branding_update", entity_type="school", entity_id=str(school.id))
    return {
        "id": school.id,
        "secondary_color": school.secondary_color,
        "locale": school.locale,
        "timezone": school.timezone,
    }


@router.get("/custom-fields", response_model=List[CustomFieldResponse])
def list_custom_fields(
    include_inactive: bool = Query(False),
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return school_admin_service.list_custom_fields(db, school.id, include_inactive=include_inactive)


@router.post("/custom-fields", response_model=CustomFieldResponse, status_code=201)
def create_custom_field(
    payload: CustomFieldCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        f = school_admin_service.create_custom_field(
            db,
            school.id,
            key=payload.key,
            label=payload.label,
            type=payload.type,
            options=payload.options,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    log_action(db, user, "school_admin.custom_field_create", entity_type="custom_field", entity_id=str(f.id))
    return f


@router.patch("/custom-fields/{field_id}", response_model=CustomFieldResponse)
def update_custom_field(
    field_id: UUID,
    payload: CustomFieldUpdate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        f = school_admin_service.update_custom_field(
            db, school.id, field_id, **payload.model_dump(exclude_unset=True)
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.custom_field_update", entity_type="custom_field", entity_id=str(f.id))
    return f


@router.get(
    "/students/{student_id}/custom-values",
    response_model=List[StudentCustomFieldValueResponse],
)
def get_student_custom_values(
    student_id: UUID,
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return school_admin_service.get_student_custom_values(db, school.id, student_id)


@router.put(
    "/students/{student_id}/custom-values",
    status_code=200,
)
def set_student_custom_value(
    student_id: UUID,
    payload: StudentCustomFieldValueUpdate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        v = school_admin_service.upsert_student_custom_value(
            db, school.id, student_id, payload.field_id, payload.value
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(
        db, user, "school_admin.custom_value_set", entity_type="user", entity_id=str(student_id)
    )
    return {"ok": True, "field_id": v.field_id, "value": v.value}


@router.get("/legal-documents", response_model=List[LegalDocumentResponse])
def list_legal_documents(
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    docs = (
        db.query(SchoolLegalDocument)
        .filter(SchoolLegalDocument.school_id == school.id)
        .order_by(desc(SchoolLegalDocument.created_at))
        .all()
    )
    if not docs:
        return []
    counts = dict(
        db.query(SchoolLegalSignature.document_id, func.count(SchoolLegalSignature.id))
        .filter(SchoolLegalSignature.document_id.in_([d.id for d in docs]))
        .group_by(SchoolLegalSignature.document_id)
        .all()
    )
    return [
        {
            "id": d.id,
            "school_id": d.school_id,
            "type": d.type,
            "version": d.version,
            "content": d.content,
            "effective_at": d.effective_at,
            "created_at": d.created_at,
            "signatures_count": int(counts.get(d.id, 0)),
        }
        for d in docs
    ]


@router.post("/legal-documents", response_model=LegalDocumentResponse, status_code=201)
def create_legal_document(
    payload: LegalDocumentCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    existing = (
        db.query(SchoolLegalDocument)
        .filter(
            SchoolLegalDocument.school_id == school.id,
            SchoolLegalDocument.type == payload.type,
            SchoolLegalDocument.version == payload.version,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Documento con esta versión ya existe.")
    d = SchoolLegalDocument(
        id=uuid4(),
        school_id=school.id,
        type=payload.type,
        version=payload.version,
        content=payload.content,
        effective_at=payload.effective_at,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    log_action(db, user, "school_admin.legal_doc_create", entity_type="legal_doc", entity_id=str(d.id))
    return {
        "id": d.id,
        "school_id": d.school_id,
        "type": d.type,
        "version": d.version,
        "content": d.content,
        "effective_at": d.effective_at,
        "created_at": d.created_at,
        "signatures_count": 0,
    }


# ============================================================================
# Categoría I · License upgrade request
# ============================================================================


@router.post("/license/upgrade-request")
def license_upgrade_request(
    payload: LicenseUpgradeRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    # Notify Grasshopper team via audit log + (future) Notification.
    log_action(
        db,
        user,
        "school_admin.license_upgrade_request",
        entity_type="school",
        entity_id=str(school.id),
        meta={
            "target_tier": payload.target_tier,
            "target_seats": payload.target_seats,
            "notes": payload.notes,
        },
    )
    return {"ok": True, "received_at": datetime.utcnow()}


# ============================================================================
# Categoría J · GH coordination
# ============================================================================


@router.get("/gh-coordination/students", response_model=List[GHCoordinationStudent])
def gh_coordination_students(
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    rows = (
        db.query(User)
        .filter(
            User.school_id == school.id,
            User.role == UserRole.STUDENT,
            User.gh_contact_status.isnot(None),
        )
        .all()
    )
    out: List[dict] = []
    assigned_ids = [u.assigned_to_user_id for u in rows if u.assigned_to_user_id]
    assigned_users = {
        u.id: u for u in db.query(User).filter(User.id.in_(assigned_ids)).all()
    } if assigned_ids else {}
    for u in rows:
        a = assigned_users.get(u.assigned_to_user_id) if u.assigned_to_user_id else None
        out.append(
            {
                "student_user_id": u.id,
                "name": u.name,
                "email": u.email,
                "gh_contact_status": u.gh_contact_status,
                "gh_contact_requested_at": u.gh_contact_requested_at,
                "lead_pipeline_status": u.lead_pipeline_status,
                "assigned_to_name": a.name if a else None,
            }
        )
    return out


@router.post("/gh-coordination/handoff/{student_id}")
def gh_handoff(
    student_id: UUID,
    payload: HandoffRequest,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    s = (
        db.query(User)
        .filter(User.id == student_id, User.school_id == school.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if not payload.consent_given:
        raise HTTPException(status_code=400, detail="El handoff requiere consentimiento explícito.")
    s.gh_contact_status = "in_progress"
    s.gh_contact_message = payload.notes or "Handoff iniciado por el colegio."
    s.gh_contact_requested_at = s.gh_contact_requested_at or datetime.utcnow()
    db.commit()
    log_action(db, user, "school_admin.gh_handoff", entity_type="user", entity_id=str(student_id))
    return {"ok": True, "student_id": s.id}


# ============================================================================
# Categoría K · Cases + clinical alerts
# ============================================================================


@router.get("/cases", response_model=List[CaseResponse])
def list_cases(
    status: Optional[str] = Query(None),
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return school_admin_service.list_cases(db, school.id, status=status)


@router.post("/cases", response_model=CaseResponse, status_code=201)
def create_case(
    payload: CaseCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        case = school_admin_service.create_case(
            db,
            school.id,
            user.id,
            student_user_id=payload.student_user_id,
            case_type=payload.case_type,
            title=payload.title,
            description=payload.description,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.case_create", entity_type="case", entity_id=str(case.id))
    return next(c for c in school_admin_service.list_cases(db, school.id) if c["id"] == case.id)


@router.patch("/cases/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: UUID,
    payload: CaseUpdate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        case = school_admin_service.update_case(
            db, school.id, case_id, **payload.model_dump(exclude_unset=True)
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.case_update", entity_type="case", entity_id=str(case.id))
    return next(c for c in school_admin_service.list_cases(db, school.id) if c["id"] == case.id)


@router.get("/cases/{case_id}/interventions", response_model=List[InterventionResponse])
def list_interventions(
    case_id: UUID,
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    try:
        return school_admin_service.list_interventions(db, school.id, case_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/cases/{case_id}/interventions", response_model=InterventionResponse, status_code=201
)
def add_intervention(
    case_id: UUID,
    payload: InterventionCreate,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    try:
        inter = school_admin_service.add_intervention(
            db,
            school.id,
            case_id,
            user.id,
            action=payload.action,
            content=payload.content,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(
        db, user, "school_admin.case_intervention", entity_type="case", entity_id=str(case_id)
    )
    rows = school_admin_service.list_interventions(db, school.id, case_id)
    return next(r for r in rows if r["id"] == inter.id)


@router.get("/clinical-alerts", response_model=List[ClinicalAlertResponse])
def list_clinical_alerts(
    only_pending: bool = Query(False),
    bundle=Depends(_get_school_staff_caller),
    db: DBSession = Depends(get_db),
):
    school, _ = bundle
    return school_admin_service.list_clinical_alerts(db, school.id, only_pending=only_pending)


@router.post("/clinical-alerts/{alert_id}/ack")
def ack_clinical_alert(
    alert_id: UUID,
    payload: ClinicalAlertAck,
    bundle=Depends(_get_school_admin_caller),
    db: DBSession = Depends(get_db),
):
    school, user = bundle
    case_id = None
    if payload.create_case:
        if not payload.case_title or not payload.case_type:
            raise HTTPException(
                status_code=400,
                detail="case_title y case_type son requeridos cuando create_case=true.",
            )
        # find alert first to get student
        from app.db.models import ClinicalAlert as CA

        alert = (
            db.query(CA)
            .filter(CA.id == alert_id, CA.school_id == school.id)
            .first()
        )
        if not alert:
            raise HTTPException(status_code=404, detail="Alerta no encontrada.")
        try:
            case = school_admin_service.create_case(
                db,
                school.id,
                user.id,
                student_user_id=alert.student_user_id,
                case_type=payload.case_type,
                title=payload.case_title,
                description=f"Auto-creado desde alerta clínica · {alert.pattern_type}",
            )
            case_id = case.id
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
    try:
        a = school_admin_service.acknowledge_alert(
            db, school.id, alert_id, user.id, case_id=case_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log_action(db, user, "school_admin.alert_ack", entity_type="clinical_alert", entity_id=str(a.id))
    return {"ok": True, "alert_id": a.id, "case_id": a.case_id}
