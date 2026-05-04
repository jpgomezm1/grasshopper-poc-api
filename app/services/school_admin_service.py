"""School-admin extended service · GH-SCHOOL-ADMIN · 2026-05-04.

Pure business logic for the 23 features of the school_admin sprint.
Endpoints in `app/api/v1/school_admin.py` orchestrate these helpers.

Conventions:
    - All helpers expect (db, school_id) · NEVER trust caller-supplied school_id.
    - Helpers are dumb · permission gates live in the router via dependencies.
    - Cohort, custom-field and parent-relationship lookups always filter by
      `school_id` to prevent cross-tenant leaks.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    AuditLog,
    CaseIntervention,
    ClinicalAlert,
    Cohort,
    CohortPsychologistAssignment,
    ConsolidatedProfileCache,
    Invitation,
    InvitationStatus,
    OnboardingStatus,
    OrientationSession,
    ParentRelationship,
    Report,
    SchoolCustomField,
    SchoolEvent,
    SchoolEventRSVP,
    SchoolLegalDocument,
    SchoolLegalSignature,
    SchoolMassMessage,
    StudentAdminNote,
    StudentCaseFollowup,
    StudentCohortAssignment,
    StudentCustomFieldValue,
    User,
    UserRole,
    VocationalTestResult,
)
from app.services.invitation_service import role_can_invite

logger = logging.getLogger(__name__)


# ============================================================================
# Cohorts
# ============================================================================


def list_cohorts(
    db: DBSession, school_id: UUID, *, include_archived: bool = False
) -> List[Dict[str, Any]]:
    q = db.query(Cohort).filter(Cohort.school_id == school_id)
    if not include_archived:
        q = q.filter(Cohort.archived_at.is_(None))
    cohorts = q.order_by(desc(Cohort.is_active), Cohort.label.asc()).all()

    if not cohorts:
        return []

    cohort_ids = [c.id for c in cohorts]
    students_rows = (
        db.query(StudentCohortAssignment.cohort_id, func.count(StudentCohortAssignment.id))
        .filter(StudentCohortAssignment.cohort_id.in_(cohort_ids))
        .group_by(StudentCohortAssignment.cohort_id)
        .all()
    )
    s_map = {r[0]: int(r[1]) for r in students_rows}
    psy_rows = (
        db.query(
            CohortPsychologistAssignment.cohort_id,
            func.count(CohortPsychologistAssignment.id),
        )
        .filter(CohortPsychologistAssignment.cohort_id.in_(cohort_ids))
        .group_by(CohortPsychologistAssignment.cohort_id)
        .all()
    )
    p_map = {r[0]: int(r[1]) for r in psy_rows}

    result = []
    for c in cohorts:
        result.append(
            {
                "id": c.id,
                "school_id": c.school_id,
                "key": c.key,
                "label": c.label,
                "grade": c.grade,
                "academic_year": c.academic_year,
                "color": c.color,
                "is_active": c.is_active,
                "created_at": c.created_at,
                "archived_at": c.archived_at,
                "students_count": s_map.get(c.id, 0),
                "psychologists_count": p_map.get(c.id, 0),
            }
        )
    return result


def create_cohort(
    db: DBSession,
    school_id: UUID,
    *,
    key: str,
    label: str,
    grade: Optional[str] = None,
    academic_year: Optional[int] = None,
    color: Optional[str] = None,
) -> Cohort:
    existing = (
        db.query(Cohort)
        .filter(Cohort.school_id == school_id, Cohort.key == key)
        .first()
    )
    if existing:
        raise ValueError(f"Ya existe un cohorte con key '{key}' en este colegio.")
    cohort = Cohort(
        id=uuid4(),
        school_id=school_id,
        key=key,
        label=label,
        grade=grade,
        academic_year=academic_year,
        color=color,
    )
    db.add(cohort)
    db.commit()
    db.refresh(cohort)
    return cohort


def update_cohort(
    db: DBSession, school_id: UUID, cohort_id: UUID, **fields
) -> Cohort:
    cohort = (
        db.query(Cohort)
        .filter(Cohort.id == cohort_id, Cohort.school_id == school_id)
        .first()
    )
    if not cohort:
        raise LookupError("Cohorte no encontrada.")
    for k, v in fields.items():
        if v is not None and hasattr(cohort, k):
            setattr(cohort, k, v)
    db.commit()
    db.refresh(cohort)
    return cohort


def archive_cohort(db: DBSession, school_id: UUID, cohort_id: UUID) -> Cohort:
    cohort = (
        db.query(Cohort)
        .filter(Cohort.id == cohort_id, Cohort.school_id == school_id)
        .first()
    )
    if not cohort:
        raise LookupError("Cohorte no encontrada.")
    cohort.archived_at = datetime.utcnow()
    cohort.is_active = False
    db.commit()
    return cohort


def assign_students_to_cohort(
    db: DBSession,
    school_id: UUID,
    cohort_id: UUID,
    student_user_ids: List[UUID],
    actor_user_id: UUID,
) -> int:
    cohort = (
        db.query(Cohort)
        .filter(Cohort.id == cohort_id, Cohort.school_id == school_id)
        .first()
    )
    if not cohort:
        raise LookupError("Cohorte no encontrada.")
    # Validate students belong to this school
    valid_ids = [
        u.id
        for u in db.query(User)
        .filter(
            User.id.in_(student_user_ids),
            User.school_id == school_id,
            User.role == UserRole.STUDENT,
        )
        .all()
    ]
    inserted = 0
    for sid in valid_ids:
        existing = (
            db.query(StudentCohortAssignment)
            .filter(
                StudentCohortAssignment.student_user_id == sid,
                StudentCohortAssignment.cohort_id == cohort_id,
            )
            .first()
        )
        if existing:
            continue
        db.add(
            StudentCohortAssignment(
                id=uuid4(),
                student_user_id=sid,
                cohort_id=cohort_id,
                assigned_by=actor_user_id,
            )
        )
        inserted += 1
    db.commit()
    return inserted


def unassign_students_from_cohort(
    db: DBSession, school_id: UUID, cohort_id: UUID, student_user_ids: List[UUID]
) -> int:
    cohort = (
        db.query(Cohort)
        .filter(Cohort.id == cohort_id, Cohort.school_id == school_id)
        .first()
    )
    if not cohort:
        raise LookupError("Cohorte no encontrada.")
    n = (
        db.query(StudentCohortAssignment)
        .filter(
            StudentCohortAssignment.cohort_id == cohort_id,
            StudentCohortAssignment.student_user_id.in_(student_user_ids),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(n)


def assign_psychologists_to_cohort(
    db: DBSession,
    school_id: UUID,
    cohort_id: UUID,
    psy_user_ids: List[UUID],
    actor_user_id: UUID,
) -> int:
    cohort = (
        db.query(Cohort)
        .filter(Cohort.id == cohort_id, Cohort.school_id == school_id)
        .first()
    )
    if not cohort:
        raise LookupError("Cohorte no encontrada.")
    valid_ids = [
        u.id
        for u in db.query(User)
        .filter(
            User.id.in_(psy_user_ids),
            User.school_id == school_id,
            User.role == UserRole.PSYCHOLOGIST,
        )
        .all()
    ]
    inserted = 0
    for pid in valid_ids:
        existing = (
            db.query(CohortPsychologistAssignment)
            .filter(
                CohortPsychologistAssignment.psychologist_user_id == pid,
                CohortPsychologistAssignment.cohort_id == cohort_id,
            )
            .first()
        )
        if existing:
            continue
        db.add(
            CohortPsychologistAssignment(
                id=uuid4(),
                psychologist_user_id=pid,
                cohort_id=cohort_id,
                assigned_by=actor_user_id,
            )
        )
        inserted += 1
    db.commit()
    return inserted


def students_for_cohort(
    db: DBSession, school_id: UUID, cohort_id: UUID
) -> List[User]:
    return (
        db.query(User)
        .join(StudentCohortAssignment, StudentCohortAssignment.student_user_id == User.id)
        .filter(
            StudentCohortAssignment.cohort_id == cohort_id,
            User.school_id == school_id,
        )
        .all()
    )


def compute_cohort_kpis(
    db: DBSession, school_id: UUID, cohort_id: UUID, label: str
) -> Dict[str, Any]:
    students = students_for_cohort(db, school_id, cohort_id)
    total = len(students)
    if total == 0:
        return {
            "cohort_id": cohort_id,
            "cohort_label": label,
            "students_total": 0,
            "completed_pct": 0.0,
            "in_progress_pct": 0.0,
            "inactive_pct": 0.0,
            "decided_pct": 0.0,
            "health_score": 0.0,
            "avg_journey_days": None,
        }
    completed = sum(1 for u in students if u.onboarding_status == OnboardingStatus.COMPLETED)
    in_progress = sum(
        1
        for u in students
        if u.onboarding_status == OnboardingStatus.IN_PROGRESS
    )
    now = datetime.utcnow()
    inactive = sum(1 for u in students if (now - u.updated_at) > timedelta(days=30))
    user_ids = [u.id for u in students]
    decided = (
        db.query(func.count(Report.id))
        .filter(Report.user_id.in_(user_ids))
        .scalar()
        or 0
    )
    days = [
        (u.updated_at - u.created_at).days
        for u in students
        if u.onboarding_status == OnboardingStatus.COMPLETED
    ]
    avg_days = sum(days) / len(days) if days else None

    activity = max(0.0, 100.0 - (inactive / total) * 100.0)
    completeness = (completed / total) * 100.0
    satisfaction = (decided / total) * 100.0 if total else 0.0
    timeliness = max(0.0, 100.0 - (avg_days or 0)) if avg_days else 80.0
    health = round(
        (activity * 0.25 + completeness * 0.35 + satisfaction * 0.25 + timeliness * 0.15),
        1,
    )

    return {
        "cohort_id": cohort_id,
        "cohort_label": label,
        "students_total": total,
        "completed_pct": round((completed / total) * 100.0, 1),
        "in_progress_pct": round((in_progress / total) * 100.0, 1),
        "inactive_pct": round((inactive / total) * 100.0, 1),
        "decided_pct": round((decided / total) * 100.0, 1),
        "health_score": health,
        "avg_journey_days": round(avg_days, 1) if avg_days else None,
    }


# ============================================================================
# Admin notes
# ============================================================================


def list_admin_notes(
    db: DBSession, school_id: UUID, student_user_id: UUID
) -> List[Dict[str, Any]]:
    notes = (
        db.query(StudentAdminNote)
        .filter(
            StudentAdminNote.school_id == school_id,
            StudentAdminNote.student_user_id == student_user_id,
        )
        .order_by(desc(StudentAdminNote.created_at))
        .all()
    )
    if not notes:
        return []
    author_ids = [n.author_user_id for n in notes if n.author_user_id]
    authors = {
        u.id: u.name or u.email
        for u in db.query(User).filter(User.id.in_(author_ids)).all()
    } if author_ids else {}
    out = []
    for n in notes:
        out.append(
            {
                "id": n.id,
                "student_user_id": n.student_user_id,
                "school_id": n.school_id,
                "author_user_id": n.author_user_id,
                "author_name": authors.get(n.author_user_id),
                "content": n.content,
                "created_at": n.created_at,
                "updated_at": n.updated_at,
            }
        )
    return out


def create_admin_note(
    db: DBSession,
    school_id: UUID,
    student_user_id: UUID,
    author_user_id: UUID,
    content: str,
) -> StudentAdminNote:
    student = (
        db.query(User)
        .filter(User.id == student_user_id, User.school_id == school_id)
        .first()
    )
    if not student:
        raise LookupError("Estudiante no encontrado en este colegio.")
    note = StudentAdminNote(
        id=uuid4(),
        student_user_id=student_user_id,
        school_id=school_id,
        author_user_id=author_user_id,
        content=content,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def update_admin_note(
    db: DBSession, school_id: UUID, note_id: UUID, content: str
) -> StudentAdminNote:
    note = (
        db.query(StudentAdminNote)
        .filter(
            StudentAdminNote.id == note_id,
            StudentAdminNote.school_id == school_id,
        )
        .first()
    )
    if not note:
        raise LookupError("Nota no encontrada.")
    note.content = content
    db.commit()
    db.refresh(note)
    return note


def delete_admin_note(db: DBSession, school_id: UUID, note_id: UUID) -> None:
    note = (
        db.query(StudentAdminNote)
        .filter(
            StudentAdminNote.id == note_id,
            StudentAdminNote.school_id == school_id,
        )
        .first()
    )
    if not note:
        raise LookupError("Nota no encontrada.")
    db.delete(note)
    db.commit()


# ============================================================================
# Custom fields
# ============================================================================


def list_custom_fields(
    db: DBSession, school_id: UUID, *, include_inactive: bool = False
) -> List[SchoolCustomField]:
    q = db.query(SchoolCustomField).filter(SchoolCustomField.school_id == school_id)
    if not include_inactive:
        q = q.filter(SchoolCustomField.is_active.is_(True))
    return q.order_by(SchoolCustomField.label.asc()).all()


def create_custom_field(
    db: DBSession,
    school_id: UUID,
    *,
    key: str,
    label: str,
    type: str,
    options: Optional[List[str]] = None,
) -> SchoolCustomField:
    existing = (
        db.query(SchoolCustomField)
        .filter(
            SchoolCustomField.school_id == school_id,
            SchoolCustomField.key == key,
        )
        .first()
    )
    if existing:
        raise ValueError(f"Ya existe un custom field con key '{key}'.")
    if type == "enum" and not options:
        raise ValueError("Los custom fields tipo 'enum' requieren al menos una opción.")
    field = SchoolCustomField(
        id=uuid4(),
        school_id=school_id,
        key=key,
        label=label,
        type=type,
        options=options,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


def update_custom_field(
    db: DBSession, school_id: UUID, field_id: UUID, **fields
) -> SchoolCustomField:
    f = (
        db.query(SchoolCustomField)
        .filter(
            SchoolCustomField.id == field_id,
            SchoolCustomField.school_id == school_id,
        )
        .first()
    )
    if not f:
        raise LookupError("Custom field no encontrado.")
    for k, v in fields.items():
        if v is not None and hasattr(f, k):
            setattr(f, k, v)
    db.commit()
    db.refresh(f)
    return f


def upsert_student_custom_value(
    db: DBSession,
    school_id: UUID,
    student_user_id: UUID,
    field_id: UUID,
    value: Any,
) -> StudentCustomFieldValue:
    field = (
        db.query(SchoolCustomField)
        .filter(
            SchoolCustomField.id == field_id,
            SchoolCustomField.school_id == school_id,
        )
        .first()
    )
    if not field:
        raise LookupError("Custom field no encontrado.")
    student = (
        db.query(User)
        .filter(User.id == student_user_id, User.school_id == school_id)
        .first()
    )
    if not student:
        raise LookupError("Estudiante no encontrado en este colegio.")
    existing = (
        db.query(StudentCustomFieldValue)
        .filter(
            StudentCustomFieldValue.student_user_id == student_user_id,
            StudentCustomFieldValue.field_id == field_id,
        )
        .first()
    )
    if existing:
        existing.value = value
    else:
        existing = StudentCustomFieldValue(
            id=uuid4(),
            student_user_id=student_user_id,
            field_id=field_id,
            value=value,
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def get_student_custom_values(
    db: DBSession, school_id: UUID, student_user_id: UUID
) -> List[Dict[str, Any]]:
    rows = (
        db.query(StudentCustomFieldValue, SchoolCustomField)
        .join(
            SchoolCustomField,
            SchoolCustomField.id == StudentCustomFieldValue.field_id,
        )
        .filter(
            SchoolCustomField.school_id == school_id,
            StudentCustomFieldValue.student_user_id == student_user_id,
        )
        .all()
    )
    return [
        {
            "field_id": f.id,
            "field_key": f.key,
            "field_label": f.label,
            "field_type": f.type,
            "value": v.value,
        }
        for v, f in rows
    ]


# ============================================================================
# Psychologist performance
# ============================================================================


def compute_psychologist_performance(
    db: DBSession, school_id: UUID
) -> Dict[str, Any]:
    psys = (
        db.query(User)
        .filter(User.school_id == school_id, User.role == UserRole.PSYCHOLOGIST)
        .all()
    )
    items: List[Dict[str, Any]] = []
    students_counts: List[int] = []
    for p in psys:
        sessions_q = db.query(OrientationSession).filter(
            OrientationSession.advisor_user_id == p.id
        )
        sessions_count = sessions_q.count()
        students_attended = (
            db.query(func.count(func.distinct(OrientationSession.student_user_id)))
            .filter(OrientationSession.advisor_user_id == p.id)
            .scalar()
            or 0
        )
        # avg response = avg(now - created_at) for unfinished sessions (proxy)
        # no_show_rate proxy via `outcome == 'no_show'` if column exists
        items.append(
            {
                "psychologist_user_id": p.id,
                "name": p.name,
                "email": p.email,
                "sessions_count": int(sessions_count),
                "students_attended": int(students_attended),
                "avg_response_hours": None,
                "no_show_rate": None,
                "workload_alert": False,
            }
        )
        students_counts.append(int(students_attended))

    avg_students = (
        round(sum(students_counts) / len(students_counts), 1)
        if students_counts
        else 0.0
    )
    # workload alert: 2x school avg
    for it in items:
        if avg_students > 0 and it["students_attended"] >= 2 * avg_students:
            it["workload_alert"] = True

    return {"items": items, "school_avg_students": avg_students}


# ============================================================================
# Parent helpers
# ============================================================================


def list_children_for_parent(
    db: DBSession, parent_user_id: UUID
) -> List[Dict[str, Any]]:
    rels = (
        db.query(ParentRelationship)
        .filter(
            ParentRelationship.parent_user_id == parent_user_id,
            ParentRelationship.is_active.is_(True),
        )
        .all()
    )
    if not rels:
        return []
    student_ids = [r.student_user_id for r in rels]
    students = db.query(User).filter(User.id.in_(student_ids)).all()
    children: List[Dict[str, Any]] = []
    for s in students:
        tests_count = (
            db.query(func.count(VocationalTestResult.id))
            .filter(VocationalTestResult.user_id == s.id)
            .scalar()
            or 0
        )
        has_profile = (
            db.query(ConsolidatedProfileCache.id)
            .filter(
                ConsolidatedProfileCache.user_id == s.id,
                ConsolidatedProfileCache.invalidated_at.is_(None),
            )
            .first()
            is not None
        )
        # Progress proxy: tests + onboarding
        pct = 0.0
        if s.onboarding_status == OnboardingStatus.COMPLETED:
            pct += 30.0
        elif s.onboarding_status == OnboardingStatus.IN_PROGRESS:
            pct += 15.0
        pct += min(50.0, tests_count * 12.5)
        if has_profile:
            pct += 20.0
        pct = round(min(100.0, pct), 1)
        children.append(
            {
                "student_user_id": s.id,
                "student_name": s.name,
                "onboarding_status": s.onboarding_status.value
                if hasattr(s.onboarding_status, "value")
                else str(s.onboarding_status),
                "progress_pct": pct,
                "tests_completed": int(tests_count),
                "has_consolidated_profile": has_profile,
                "last_activity_at": s.updated_at,
            }
        )
    return children


def parent_can_see_student(
    db: DBSession, parent_user_id: UUID, student_user_id: UUID
) -> bool:
    rel = (
        db.query(ParentRelationship)
        .filter(
            ParentRelationship.parent_user_id == parent_user_id,
            ParentRelationship.student_user_id == student_user_id,
            ParentRelationship.is_active.is_(True),
        )
        .first()
    )
    return rel is not None


# ============================================================================
# Cases + clinical alerts
# ============================================================================


def list_cases(
    db: DBSession, school_id: UUID, *, status: Optional[str] = None
) -> List[Dict[str, Any]]:
    q = db.query(StudentCaseFollowup).filter(StudentCaseFollowup.school_id == school_id)
    if status:
        q = q.filter(StudentCaseFollowup.status == status)
    cases = q.order_by(desc(StudentCaseFollowup.created_at)).all()
    if not cases:
        return []
    user_ids = {c.student_user_id for c in cases} | {
        c.opened_by_user_id for c in cases if c.opened_by_user_id
    }
    users = {
        u.id: u for u in db.query(User).filter(User.id.in_(list(user_ids))).all()
    }
    case_ids = [c.id for c in cases]
    int_counts = dict(
        db.query(CaseIntervention.case_id, func.count(CaseIntervention.id))
        .filter(CaseIntervention.case_id.in_(case_ids))
        .group_by(CaseIntervention.case_id)
        .all()
    )
    out = []
    for c in cases:
        s = users.get(c.student_user_id)
        o = users.get(c.opened_by_user_id) if c.opened_by_user_id else None
        out.append(
            {
                "id": c.id,
                "student_user_id": c.student_user_id,
                "student_name": s.name if s else None,
                "school_id": c.school_id,
                "opened_by_user_id": c.opened_by_user_id,
                "opened_by_name": (o.name or o.email) if o else None,
                "case_type": c.case_type,
                "status": c.status,
                "title": c.title,
                "description": c.description,
                "resolution_notes": c.resolution_notes,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "resolved_at": c.resolved_at,
                "interventions_count": int(int_counts.get(c.id, 0)),
            }
        )
    return out


def create_case(
    db: DBSession,
    school_id: UUID,
    opened_by_user_id: UUID,
    *,
    student_user_id: UUID,
    case_type: str,
    title: str,
    description: Optional[str] = None,
) -> StudentCaseFollowup:
    student = (
        db.query(User)
        .filter(User.id == student_user_id, User.school_id == school_id)
        .first()
    )
    if not student:
        raise LookupError("Estudiante no encontrado en este colegio.")
    case = StudentCaseFollowup(
        id=uuid4(),
        student_user_id=student_user_id,
        school_id=school_id,
        opened_by_user_id=opened_by_user_id,
        case_type=case_type,
        title=title,
        description=description,
        status="open",
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def update_case(
    db: DBSession, school_id: UUID, case_id: UUID, **fields
) -> StudentCaseFollowup:
    case = (
        db.query(StudentCaseFollowup)
        .filter(
            StudentCaseFollowup.id == case_id,
            StudentCaseFollowup.school_id == school_id,
        )
        .first()
    )
    if not case:
        raise LookupError("Caso no encontrado.")
    for k, v in fields.items():
        if v is not None and hasattr(case, k):
            setattr(case, k, v)
    if fields.get("status") in ("resolved", "escalated"):
        case.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(case)
    return case


def add_intervention(
    db: DBSession,
    school_id: UUID,
    case_id: UUID,
    author_user_id: UUID,
    *,
    action: str,
    content: str,
) -> CaseIntervention:
    case = (
        db.query(StudentCaseFollowup)
        .filter(
            StudentCaseFollowup.id == case_id,
            StudentCaseFollowup.school_id == school_id,
        )
        .first()
    )
    if not case:
        raise LookupError("Caso no encontrado.")
    inter = CaseIntervention(
        id=uuid4(),
        case_id=case_id,
        author_user_id=author_user_id,
        action=action,
        content=content,
    )
    db.add(inter)
    case.updated_at = datetime.utcnow()
    if action == "closure":
        case.status = "resolved"
        case.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(inter)
    return inter


def list_interventions(
    db: DBSession, school_id: UUID, case_id: UUID
) -> List[Dict[str, Any]]:
    case = (
        db.query(StudentCaseFollowup)
        .filter(
            StudentCaseFollowup.id == case_id,
            StudentCaseFollowup.school_id == school_id,
        )
        .first()
    )
    if not case:
        raise LookupError("Caso no encontrado.")
    rows = (
        db.query(CaseIntervention)
        .filter(CaseIntervention.case_id == case_id)
        .order_by(asc(CaseIntervention.created_at))
        .all()
    )
    if not rows:
        return []
    author_ids = [r.author_user_id for r in rows if r.author_user_id]
    authors = {
        u.id: u.name or u.email
        for u in db.query(User).filter(User.id.in_(author_ids)).all()
    } if author_ids else {}
    return [
        {
            "id": r.id,
            "case_id": r.case_id,
            "author_user_id": r.author_user_id,
            "author_name": authors.get(r.author_user_id),
            "action": r.action,
            "content": r.content,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def list_clinical_alerts(
    db: DBSession, school_id: UUID, *, only_pending: bool = False
) -> List[Dict[str, Any]]:
    q = db.query(ClinicalAlert).filter(ClinicalAlert.school_id == school_id)
    if only_pending:
        q = q.filter(ClinicalAlert.acknowledged_at.is_(None))
    rows = q.order_by(desc(ClinicalAlert.created_at)).limit(200).all()
    if not rows:
        return []
    student_ids = list({r.student_user_id for r in rows})
    students = {
        u.id: u for u in db.query(User).filter(User.id.in_(student_ids)).all()
    }
    return [
        {
            "id": r.id,
            "student_user_id": r.student_user_id,
            "student_name": students[r.student_user_id].name
            if r.student_user_id in students
            else None,
            "severity": r.severity,
            "pattern_type": r.pattern_type,
            "summary": r.summary,
            "source": r.source,
            "acknowledged_at": r.acknowledged_at,
            "case_id": r.case_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def materialize_alert_from_clinical_analysis(
    db: DBSession,
    school_id: UUID,
    student_user_id: UUID,
    pattern: Dict[str, Any],
) -> ClinicalAlert:
    """Idempotent: looks up by (student, pattern_type, severity) before insert."""
    existing = (
        db.query(ClinicalAlert)
        .filter(
            ClinicalAlert.student_user_id == student_user_id,
            ClinicalAlert.school_id == school_id,
            ClinicalAlert.pattern_type == pattern.get("label", "unknown"),
            ClinicalAlert.severity == pattern.get("severity", "medium"),
            ClinicalAlert.acknowledged_at.is_(None),
        )
        .first()
    )
    if existing:
        return existing
    alert = ClinicalAlert(
        id=uuid4(),
        student_user_id=student_user_id,
        school_id=school_id,
        severity=pattern.get("severity", "medium"),
        pattern_type=pattern.get("label", "unknown"),
        summary=pattern.get("summary") or pattern.get("description"),
        source="ai_analysis",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def acknowledge_alert(
    db: DBSession,
    school_id: UUID,
    alert_id: UUID,
    actor_user_id: UUID,
    *,
    case_id: Optional[UUID] = None,
) -> ClinicalAlert:
    alert = (
        db.query(ClinicalAlert)
        .filter(
            ClinicalAlert.id == alert_id,
            ClinicalAlert.school_id == school_id,
        )
        .first()
    )
    if not alert:
        raise LookupError("Alerta no encontrada.")
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = actor_user_id
    if case_id:
        alert.case_id = case_id
    db.commit()
    db.refresh(alert)
    return alert


# ============================================================================
# Risk alerts (Categoría A · 3) · computed live, not stored
# ============================================================================


def compute_risk_alerts(db: DBSession, school_id: UUID) -> List[Dict[str, Any]]:
    students = (
        db.query(User)
        .filter(User.school_id == school_id, User.role == UserRole.STUDENT)
        .all()
    )
    now = datetime.utcnow()
    alerts: List[Dict[str, Any]] = []
    for s in students:
        if (now - s.updated_at) > timedelta(days=30):
            alerts.append(
                {
                    "student_user_id": s.id,
                    "student_name": s.name,
                    "reason": "inactive_30d",
                    "detail": f"Sin actividad en {(now - s.updated_at).days} días.",
                    "triggered_at": now,
                }
            )
        if (
            s.onboarding_status == OnboardingStatus.IN_PROGRESS
            and (now - s.updated_at) > timedelta(days=14)
        ):
            alerts.append(
                {
                    "student_user_id": s.id,
                    "student_name": s.name,
                    "reason": "stuck_14d",
                    "detail": "Atascado en mismo paso del onboarding por más de 14 días.",
                    "triggered_at": now,
                }
            )
    # Tests abandonados: VocationalTestResult con status incomplete (proxy)
    return alerts[:200]


# ============================================================================
# Timeline + funnel + heatmap
# ============================================================================


def compute_timeline(
    db: DBSession, school_id: UUID, *, granularity: str = "weekly", weeks: int = 12
) -> List[Dict[str, Any]]:
    """Activity timeline · students_active + tests + profiles + decisions per period."""
    now = datetime.utcnow()
    # Build periods
    periods: List[Tuple[datetime, datetime, str]] = []
    if granularity == "weekly":
        for i in range(weeks - 1, -1, -1):
            start = now - timedelta(days=now.weekday() + 7 * i)
            start = datetime(start.year, start.month, start.day)
            end = start + timedelta(days=7)
            label = f"{start.year}-W{start.isocalendar()[1]:02d}"
            periods.append((start, end, label))
    else:
        for i in range(weeks - 1, -1, -1):
            ref = now.replace(day=1)
            month = ref.month - i
            year = ref.year
            while month <= 0:
                month += 12
                year -= 1
            start = datetime(year, month, 1)
            end = (
                datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
            )
            label = f"{year}-{month:02d}"
            periods.append((start, end, label))

    out: List[Dict[str, Any]] = []
    for start, end, label in periods:
        active = (
            db.query(func.count(User.id))
            .filter(
                User.school_id == school_id,
                User.role == UserRole.STUDENT,
                User.updated_at >= start,
                User.updated_at < end,
            )
            .scalar()
            or 0
        )
        tests = (
            db.query(func.count(VocationalTestResult.id))
            .join(User, User.id == VocationalTestResult.user_id)
            .filter(
                User.school_id == school_id,
                VocationalTestResult.created_at >= start,
                VocationalTestResult.created_at < end,
            )
            .scalar()
            or 0
        )
        profiles = (
            db.query(func.count(ConsolidatedProfileCache.id))
            .join(User, User.id == ConsolidatedProfileCache.user_id)
            .filter(
                User.school_id == school_id,
                ConsolidatedProfileCache.updated_at >= start,
                ConsolidatedProfileCache.updated_at < end,
            )
            .scalar()
            or 0
        )
        decisions = (
            db.query(func.count(Report.id))
            .join(User, User.id == Report.user_id)
            .filter(
                User.school_id == school_id,
                Report.created_at >= start,
                Report.created_at < end,
            )
            .scalar()
            or 0
        )
        out.append(
            {
                "period_label": label,
                "period_start": start,
                "students_active": int(active),
                "tests_completed": int(tests),
                "profiles_consolidated": int(profiles),
                "decisions_taken": int(decisions),
            }
        )
    return out


def compute_funnel(db: DBSession, school_id: UUID) -> List[Dict[str, Any]]:
    total = (
        db.query(func.count(User.id))
        .filter(User.school_id == school_id, User.role == UserRole.STUDENT)
        .scalar()
        or 0
    )
    started = (
        db.query(func.count(User.id))
        .filter(
            User.school_id == school_id,
            User.role == UserRole.STUDENT,
            User.onboarding_status != OnboardingStatus.NOT_STARTED,
        )
        .scalar()
        or 0
    )
    student_ids = [
        u.id
        for u in db.query(User.id)
        .filter(User.school_id == school_id, User.role == UserRole.STUDENT)
        .all()
    ]
    with_tests = 0
    with_profile = 0
    with_report = 0
    if student_ids:
        with_tests = (
            db.query(func.count(func.distinct(VocationalTestResult.user_id)))
            .filter(VocationalTestResult.user_id.in_(student_ids))
            .scalar()
            or 0
        )
        with_profile = (
            db.query(func.count(func.distinct(ConsolidatedProfileCache.user_id)))
            .filter(
                ConsolidatedProfileCache.user_id.in_(student_ids),
                ConsolidatedProfileCache.invalidated_at.is_(None),
            )
            .scalar()
            or 0
        )
        with_report = (
            db.query(func.count(func.distinct(Report.user_id)))
            .filter(Report.user_id.in_(student_ids))
            .scalar()
            or 0
        )

    stages = [
        ("registered", "Registrados", int(total)),
        ("onboarding_started", "Onboarding iniciado", int(started)),
        ("tests_completed", "Tests completados", int(with_tests)),
        ("profile_built", "Perfil consolidado", int(with_profile)),
        ("decided", "Decididos (reporte)", int(with_report)),
    ]
    out: List[Dict[str, Any]] = []
    prev = total or 1
    for key, label, count in stages:
        drop = max(0.0, round((1 - count / prev) * 100.0, 1)) if prev > 0 else 0.0
        out.append(
            {
                "stage_key": key,
                "stage_label": label,
                "count": count,
                "drop_off_pct": drop,
            }
        )
        prev = count if count > 0 else prev
    return out


def compute_heatmap(db: DBSession, school_id: UUID) -> List[List[int]]:
    """7 rows (Mon..Sun) x 24 cols (hours) of student activity counts."""
    grid = [[0] * 24 for _ in range(7)]
    rows = (
        db.query(VocationalTestResult.created_at)
        .join(User, User.id == VocationalTestResult.user_id)
        .filter(User.school_id == school_id)
        .filter(VocationalTestResult.created_at >= datetime.utcnow() - timedelta(days=90))
        .all()
    )
    for (ts,) in rows:
        if ts is None:
            continue
        grid[ts.weekday()][ts.hour] += 1
    return grid


def compute_health_score(db: DBSession, school_id: UUID) -> Dict[str, float]:
    students = (
        db.query(User)
        .filter(User.school_id == school_id, User.role == UserRole.STUDENT)
        .all()
    )
    total = len(students) or 1
    now = datetime.utcnow()
    active = sum(1 for u in students if (now - u.updated_at) <= timedelta(days=30))
    completed = sum(
        1 for u in students if u.onboarding_status == OnboardingStatus.COMPLETED
    )
    user_ids = [u.id for u in students]
    decided = (
        db.query(func.count(func.distinct(Report.user_id)))
        .filter(Report.user_id.in_(user_ids))
        .scalar()
        or 0
    ) if user_ids else 0
    avg_days = []
    for u in students:
        if u.onboarding_status == OnboardingStatus.COMPLETED:
            avg_days.append((u.updated_at - u.created_at).days)
    timeliness_raw = sum(avg_days) / len(avg_days) if avg_days else 30
    timeliness = max(0.0, min(100.0, 100 - timeliness_raw * 1.5))
    activity = (active / total) * 100.0
    completeness = (completed / total) * 100.0
    satisfaction = (decided / total) * 100.0

    overall = round(
        activity * 0.25 + completeness * 0.35 + satisfaction * 0.25 + timeliness * 0.15,
        1,
    )
    return {
        "activity": round(activity, 1),
        "completeness": round(completeness, 1),
        "satisfaction": round(satisfaction, 1),
        "timeliness": round(timeliness, 1),
        "overall": overall,
    }


# ============================================================================
# CSV bulk invite parser (Categoría C · 6)
# ============================================================================


def parse_bulk_invite_csv(content: bytes) -> List[Dict[str, Any]]:
    """Returns list of dicts with keys: email, name, cohort_key.

    Accepts headers: email | name | cohort_key (case-insensitive · whitespace tolerant).
    """
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, Any]] = []
    for r in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        email = norm.get("email", "").strip()
        if not email:
            continue
        rows.append(
            {
                "email": email,
                "name": norm.get("name") or None,
                "cohort_key": norm.get("cohort_key") or None,
            }
        )
    return rows
