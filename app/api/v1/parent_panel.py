"""Parent panel router · GH-SCHOOL-ADMIN-PARENT · 2026-05-04.

Read-only access for the new `parent` role. Parents see only:
- their own children (linked via parent_relationships)
- public progress KPIs (% advance, tests count, profile generated)
- public reports (PDF previously generated)
- school events for their children's school
- legal documents pending signature
- mass messages broadcast to parents (READ-ONLY · NEVER chat)

NEVER exposes clinical analysis, dossier notes, session notes,
admin notes, or any staff-only artifact.

REGLA DURA · GH-PARENT-EXPERIENCE 2026-05-05:
    NO mensajería bidireccional · NO chats · NO threads.
    `mass_messages` is consumed READ-ONLY (the parent can only mark as read).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    ConsolidatedProfileCache,
    EnglishTestResult,
    OnboardingStatus,
    ParentRelationship,
    Report,
    Route,
    RouteStatus,
    School,
    SchoolEvent,
    SchoolLegalDocument,
    SchoolLegalSignature,
    SchoolMassMessage,
    SchoolMassMessageRead,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.school_admin import (
    LegalDocumentResponse,
    LegalSignatureRequest,
    LegalSignatureResponse,
    ParentLegalDocItem,
    ParentLegalHistoryResponse,
    ParentMeResponse,
    ParentMessageItem,
    ParentMessagesResponse,
    ParentSchoolBranding,
    ParentTimelineMilestone,
    ParentTimelineResponse,
)
from app.services import school_admin_service

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/parent", tags=["Parent Panel"])


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


def _gate_parent(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.PARENT and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Solo padres autenticados.")
    return current_user


def _children_school_ids(db: DBSession, parent_id: UUID) -> List[UUID]:
    rows = (
        db.query(User.school_id)
        .join(ParentRelationship, ParentRelationship.student_user_id == User.id)
        .filter(
            ParentRelationship.parent_user_id == parent_id,
            ParentRelationship.is_active.is_(True),
            User.school_id.isnot(None),
        )
        .all()
    )
    seen: List[UUID] = []
    for (sid,) in rows:
        if sid is not None and sid not in seen:
            seen.append(sid)
    return seen


def _branding_payload(school: School) -> ParentSchoolBranding:
    return ParentSchoolBranding(
        id=school.id,
        name=school.name,
        logo_url=school.logo_url,
        branding_primary_color=school.branding_primary_color,
    )


# ---------------------------------------------------------------------------
# /me  ·  children + branding
# ---------------------------------------------------------------------------


@router.get("/me", response_model=ParentMeResponse)
def parent_me(
    user: User = Depends(_gate_parent), db: DBSession = Depends(get_db)
):
    children = school_admin_service.list_children_for_parent(db, user.id)
    school_ids = _children_school_ids(db, user.id)
    schools = (
        db.query(School).filter(School.id.in_(school_ids)).all()
        if school_ids
        else []
    )
    schools_payload = [_branding_payload(s) for s in schools]
    primary = None
    if schools_payload:
        # Pick the school of the first child returned (most-recent activity).
        first_school_id = None
        if children:
            child_user_ids = [c["student_user_id"] for c in children]
            row = (
                db.query(User.school_id)
                .filter(User.id.in_(child_user_ids), User.school_id.isnot(None))
                .order_by(User.updated_at.desc())
                .first()
            )
            first_school_id = row[0] if row else None
        if first_school_id:
            primary = next(
                (s for s in schools_payload if s.id == first_school_id),
                schools_payload[0],
            )
        else:
            primary = schools_payload[0]
    return ParentMeResponse(
        parent_user_id=user.id,
        parent_name=user.name,
        children=children,
        primary_school=primary,
        schools=schools_payload,
    )


# ---------------------------------------------------------------------------
# Child profile + reports + timeline
# ---------------------------------------------------------------------------


@router.get("/children/{student_id}/profile")
def child_public_profile(
    student_id: UUID,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    if not school_admin_service.parent_can_see_student(db, user.id, student_id):
        raise HTTPException(status_code=403, detail="Sin acceso a este estudiante.")
    profile = (
        db.query(ConsolidatedProfileCache)
        .filter(
            ConsolidatedProfileCache.user_id == student_id,
            ConsolidatedProfileCache.invalidated_at.is_(None),
        )
        .first()
    )
    if not profile:
        return {"available": False, "reason": "Tu hijo aún no tiene perfil consolidado."}
    payload = profile.payload or {}
    public_fields = {
        k: v
        for k, v in payload.items()
        if k
        in (
            "areas_of_interest",
            "values",
            "narrative_short",
            "summary",
            "strengths_public",
            "skills",
            "next_steps",
        )
    }
    return {
        "available": True,
        "generated_at": profile.updated_at,
        "public_profile": public_fields,
    }


def _public_test_label(test_id: str) -> str:
    return {
        "riasec": "Holland RIASEC",
        "big5": "Big Five OCEAN",
        "work_values": "Work Values",
        "career_anchors": "Career Anchors",
        "mbti": "MBTI",
        "istrong": "Strong Interest",
        "english": "Test de inglés",
    }.get(test_id, test_id.title())


@router.get(
    "/children/{student_id}/timeline",
    response_model=ParentTimelineResponse,
)
def child_timeline(
    student_id: UUID,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Public timeline of a child's journey · NEVER returns clinical info.

    Shows only:
        - onboarding completion + percentage
        - tests completed (id + label · NO scores breakdown)
        - active routes count
        - english test pass + level
        - journey_completed_at + onboarding_completed_at hits
    """
    if not school_admin_service.parent_can_see_student(db, user.id, student_id):
        raise HTTPException(status_code=403, detail="Sin acceso a este estudiante.")

    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")

    tests = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == student_id)
        .order_by(VocationalTestResult.created_at.asc())
        .all()
    )
    test_ids = sorted({t.test_id for t in tests if t.test_id})
    # Routes hang off Session (not directly off the user) · join via session.user_id
    from app.db.models import Session as JourneySession
    routes_active = (
        db.query(func.count(Route.id))
        .join(JourneySession, JourneySession.id == Route.session_id)
        .filter(
            JourneySession.user_id == student_id,
            Route.status == RouteStatus.ACTIVE,
        )
        .scalar()
        or 0
    )

    onboarding_pct = 0.0
    if student.onboarding_status == OnboardingStatus.COMPLETED:
        onboarding_pct = 100.0
    elif student.onboarding_status == OnboardingStatus.IN_PROGRESS:
        onboarding_pct = 50.0

    milestones: List[ParentTimelineMilestone] = []
    if student.onboarding_status == OnboardingStatus.COMPLETED:
        milestones.append(
            ParentTimelineMilestone(
                kind="onboarding_completed",
                title="Completó el onboarding",
                detail="Su hijo terminó las 12 etapas iniciales del programa.",
                occurred_at=student.updated_at,
                icon="check",
            )
        )
    for t in tests:
        milestones.append(
            ParentTimelineMilestone(
                kind="test_completed",
                title=f"Completó {_public_test_label(t.test_id)}",
                detail="Resultado disponible en el resumen público del perfil.",
                occurred_at=t.created_at,
                icon="brain",
            )
        )
    if student.english_test_completed:
        eng_row = (
            db.query(EnglishTestResult)
            .filter(EnglishTestResult.user_id == student_id)
            .order_by(EnglishTestResult.created_at.desc())
            .first()
        )
        milestones.append(
            ParentTimelineMilestone(
                kind="english_completed",
                title=f"Inglés · nivel {student.english_cefr_level or 'estimado'}",
                detail="Test de inglés finalizado.",
                occurred_at=eng_row.created_at if eng_row else None,
                icon="globe",
            )
        )
    if routes_active:
        milestones.append(
            ParentTimelineMilestone(
                kind="route_active",
                title=f"{routes_active} ruta{'s' if routes_active != 1 else ''} profesional"
                + ("es" if routes_active != 1 else "")
                + " activa"
                + ("s" if routes_active != 1 else ""),
                detail="Trayectorias visibles en su panel del estudiante.",
                occurred_at=None,
                icon="compass",
            )
        )
    if getattr(student, "journey_completed_at", None):
        milestones.append(
            ParentTimelineMilestone(
                kind="journey_completed",
                title="Cerró el journey vocacional",
                detail="Su hijo completó la fase guiada del programa.",
                occurred_at=student.journey_completed_at,
                icon="trophy",
            )
        )

    milestones.sort(key=lambda m: (m.occurred_at or datetime.min))

    return ParentTimelineResponse(
        student_user_id=student.id,
        student_name=student.name,
        onboarding_status=(
            student.onboarding_status.value
            if hasattr(student.onboarding_status, "value")
            else str(student.onboarding_status)
        ),
        onboarding_pct=onboarding_pct,
        tests_completed=test_ids,
        routes_active=int(routes_active),
        onboarding_completed_at=(
            student.updated_at
            if student.onboarding_status == OnboardingStatus.COMPLETED
            else None
        ),
        journey_completed_at=getattr(student, "journey_completed_at", None),
        milestones=milestones,
    )


@router.get("/children/{student_id}/reports")
def child_reports(
    student_id: UUID,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    if not school_admin_service.parent_can_see_student(db, user.id, student_id):
        raise HTTPException(status_code=403, detail="Sin acceso a este estudiante.")
    # Filter by audience: only parents/both. The Report model uses an `audience`
    # column when present (school_admin reports) · we are defensive about its
    # existence so older rows without it remain visible.
    q = db.query(Report).filter(Report.user_id == student_id)
    if hasattr(Report, "audience"):
        q = q.filter(
            (Report.audience.in_(("parents", "both"))) | (Report.audience.is_(None))
        )
    reports = q.order_by(Report.created_at.desc()).all()
    return {
        "items": [
            {
                "id": r.id,
                "title": getattr(r, "title", None) or "Reporte",
                "created_at": r.created_at,
                "url": getattr(r, "pdf_url", None),
                "downloadable": bool(
                    getattr(r, "pdf_url", None)
                    or getattr(r, "pdf_local_path", None)
                ),
            }
            for r in reports
        ]
    }


@router.get("/children/{student_id}/reports/{report_id}/download")
def download_child_report(
    student_id: UUID,
    report_id: UUID,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Proxy a parent-allowed report PDF.

    Resolution order:
      1. If `pdf_url` is set → 302 redirect (signed URL on S3).
      2. If `pdf_local_path` exists → stream FileResponse.
      3. Else 404.
    """
    if not school_admin_service.parent_can_see_student(db, user.id, student_id):
        raise HTTPException(status_code=403, detail="Sin acceso a este estudiante.")
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == student_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    if hasattr(Report, "audience"):
        aud = getattr(report, "audience", None)
        if aud not in (None, "parents", "both"):
            raise HTTPException(
                status_code=403,
                detail="Este reporte no está disponible para padres.",
            )
    pdf_url = getattr(report, "pdf_url", None)
    if pdf_url:
        return Response(status_code=307, headers={"Location": pdf_url})
    local = getattr(report, "pdf_local_path", None)
    if local and os.path.exists(local):
        return FileResponse(local, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="PDF del reporte no disponible.")


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@router.get("/events")
def parent_events(
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Events for any school where the parent has at least one active child."""
    school_ids = _children_school_ids(db, user.id)
    if not school_ids:
        return {"items": []}
    events = (
        db.query(SchoolEvent)
        .filter(
            SchoolEvent.school_id.in_(school_ids),
            SchoolEvent.audience.in_(["parents", "both"]),
            SchoolEvent.archived_at.is_(None),
        )
        .order_by(SchoolEvent.starts_at.asc())
        .all()
    )
    # Compute parent's RSVP per event (single-shot)
    from app.db.models import SchoolEventRSVP

    rsvps = {}
    if events:
        rows = (
            db.query(SchoolEventRSVP)
            .filter(
                SchoolEventRSVP.user_id == user.id,
                SchoolEventRSVP.event_id.in_([e.id for e in events]),
            )
            .all()
        )
        rsvps = {r.event_id: r.status for r in rows}

    return {
        "items": [
            {
                "id": e.id,
                "school_id": e.school_id,
                "title": e.title,
                "description": e.description,
                "starts_at": e.starts_at,
                "ends_at": e.ends_at,
                "location": e.location,
                "audience": e.audience,
                "rsvp_status": rsvps.get(e.id),
            }
            for e in events
        ]
    }


@router.post("/events/{event_id}/rsvp", status_code=201)
def parent_rsvp_event(
    event_id: UUID,
    payload: dict,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """RSVP to an event audience-targeting parents.

    Status values: 'going' | 'declined' | 'maybe' (aligned with school_admin).
    """
    from app.db.models import SchoolEventRSVP

    raw = (payload.get("status") or "").strip().lower()
    aliases = {"yes": "going", "no": "declined"}
    status_value = aliases.get(raw, raw)
    if status_value not in ("going", "declined", "maybe"):
        raise HTTPException(status_code=422, detail="status inválido (going|declined|maybe).")

    event = db.query(SchoolEvent).filter(SchoolEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Evento no encontrado.")
    school_ids = _children_school_ids(db, user.id)
    if event.school_id not in school_ids and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Sin acceso a este evento.")
    if event.audience not in ("parents", "both") and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Evento no es para padres.")

    existing = (
        db.query(SchoolEventRSVP)
        .filter(SchoolEventRSVP.event_id == event_id, SchoolEventRSVP.user_id == user.id)
        .first()
    )
    if existing:
        existing.status = status_value
        existing.responded_at = datetime.utcnow()
    else:
        db.add(
            SchoolEventRSVP(
                id=uuid4(),
                event_id=event_id,
                user_id=user.id,
                status=status_value,
            )
        )
    db.commit()
    return {"ok": True, "status": status_value}


# ---------------------------------------------------------------------------
# Mass messages · read-only inbox
# ---------------------------------------------------------------------------


@router.get("/messages", response_model=ParentMessagesResponse)
def parent_messages(
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    school_ids = _children_school_ids(db, user.id)
    if not school_ids:
        return ParentMessagesResponse(items=[], unread=0)
    rows = (
        db.query(SchoolMassMessage)
        .filter(
            SchoolMassMessage.school_id.in_(school_ids),
            SchoolMassMessage.audience.in_(("parents", "both")),
        )
        .order_by(desc(SchoolMassMessage.sent_at))
        .limit(200)
        .all()
    )
    if not rows:
        return ParentMessagesResponse(items=[], unread=0)

    msg_ids = [m.id for m in rows]
    read_rows = (
        db.query(SchoolMassMessageRead.message_id)
        .filter(
            SchoolMassMessageRead.user_id == user.id,
            SchoolMassMessageRead.message_id.in_(msg_ids),
        )
        .all()
    )
    read_set = {r[0] for r in read_rows}

    school_names = {
        s.id: s.name
        for s in db.query(School).filter(School.id.in_(school_ids)).all()
    }
    author_ids = [m.author_user_id for m in rows if m.author_user_id]
    authors = {
        u.id: u.name or u.email
        for u in db.query(User).filter(User.id.in_(author_ids)).all()
    } if author_ids else {}

    items = [
        ParentMessageItem(
            id=m.id,
            school_id=m.school_id,
            school_name=school_names.get(m.school_id),
            sender_name=authors.get(m.author_user_id) if m.author_user_id else None,
            subject=m.subject,
            body=m.body,
            sent_at=m.sent_at,
            is_read=(m.id in read_set),
        )
        for m in rows
    ]
    unread = sum(1 for it in items if not it.is_read)
    return ParentMessagesResponse(items=items, unread=unread)


@router.post("/messages/{message_id}/read", status_code=201)
def parent_mark_message_read(
    message_id: UUID,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Idempotent · marking the same message twice keeps the original read_at."""
    msg = (
        db.query(SchoolMassMessage)
        .filter(SchoolMassMessage.id == message_id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado.")
    school_ids = _children_school_ids(db, user.id)
    if msg.school_id not in school_ids and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Sin acceso a este mensaje.")
    if msg.audience not in ("parents", "both") and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Mensaje no audiencia parents.")
    existing = (
        db.query(SchoolMassMessageRead)
        .filter(
            SchoolMassMessageRead.message_id == message_id,
            SchoolMassMessageRead.user_id == user.id,
        )
        .first()
    )
    if existing:
        return {"ok": True, "read_at": existing.read_at, "idempotent": True}
    db.add(
        SchoolMassMessageRead(
            id=uuid4(),
            message_id=message_id,
            user_id=user.id,
        )
    )
    db.commit()
    return {"ok": True, "idempotent": False}


# ---------------------------------------------------------------------------
# Legal documents · pending + history
# ---------------------------------------------------------------------------


@router.get("/legal-documents", response_model=List[LegalDocumentResponse])
def parent_legal_docs(
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Legacy endpoint · returns docs (signed_count helps the FE show state)."""
    school_ids = _children_school_ids(db, user.id)
    if not school_ids:
        return []
    docs = (
        db.query(SchoolLegalDocument)
        .filter(SchoolLegalDocument.school_id.in_(school_ids))
        .order_by(SchoolLegalDocument.created_at.desc())
        .all()
    )
    signed_ids = {
        s.document_id
        for s in db.query(SchoolLegalSignature)
        .filter(SchoolLegalSignature.signer_user_id == user.id)
        .all()
    }
    return [
        {
            "id": d.id,
            "school_id": d.school_id,
            "type": d.type,
            "version": d.version,
            "content": d.content,
            "effective_at": d.effective_at,
            "created_at": d.created_at,
            "signatures_count": 1 if d.id in signed_ids else 0,
        }
        for d in docs
    ]


@router.get(
    "/legal-documents/history",
    response_model=ParentLegalHistoryResponse,
)
def parent_legal_history(
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Tabbed view · pending vs signed.

    A doc is `requires_resign=True` when the parent already signed an older
    version (same school + type) but there is a newer document version.
    """
    school_ids = _children_school_ids(db, user.id)
    if not school_ids:
        return ParentLegalHistoryResponse(pending=[], signed=[])
    docs = (
        db.query(SchoolLegalDocument)
        .filter(SchoolLegalDocument.school_id.in_(school_ids))
        .order_by(SchoolLegalDocument.created_at.desc())
        .all()
    )
    sigs = (
        db.query(SchoolLegalSignature)
        .filter(SchoolLegalSignature.signer_user_id == user.id)
        .all()
    )
    sig_by_doc = {s.document_id: s for s in sigs}

    # Index docs by (school_id, type) to detect newer versions
    docs_by_key = {}
    for d in docs:
        docs_by_key.setdefault((d.school_id, d.type), []).append(d)
    for key in docs_by_key:
        docs_by_key[key].sort(key=lambda x: x.created_at, reverse=True)

    pending: List[ParentLegalDocItem] = []
    signed: List[ParentLegalDocItem] = []

    # Track which doc ids belong to a signed group (so older signed versions are
    # NOT shown as pending again)
    signed_doc_ids = set(sig_by_doc.keys())

    for d in docs:
        sig = sig_by_doc.get(d.id)
        if sig:
            signed.append(
                ParentLegalDocItem(
                    id=d.id,
                    school_id=d.school_id,
                    type=d.type,
                    version=d.version,
                    content=d.content,
                    effective_at=d.effective_at,
                    created_at=d.created_at,
                    is_signed=True,
                    signed_at=sig.signed_at,
                    signed_version=d.version,
                    requires_resign=False,
                )
            )
            continue
        # not signed · check if a sibling (same school+type) IS signed AND this
        # one is newer → requires re-sign.
        siblings = docs_by_key.get((d.school_id, d.type), [])
        signed_sibling = next(
            (s for s in siblings if s.id in signed_doc_ids), None
        )
        if signed_sibling and d.created_at > signed_sibling.created_at:
            pending.append(
                ParentLegalDocItem(
                    id=d.id,
                    school_id=d.school_id,
                    type=d.type,
                    version=d.version,
                    content=d.content,
                    effective_at=d.effective_at,
                    created_at=d.created_at,
                    is_signed=False,
                    signed_at=None,
                    signed_version=signed_sibling.version,
                    requires_resign=True,
                )
            )
        else:
            pending.append(
                ParentLegalDocItem(
                    id=d.id,
                    school_id=d.school_id,
                    type=d.type,
                    version=d.version,
                    content=d.content,
                    effective_at=d.effective_at,
                    created_at=d.created_at,
                    is_signed=False,
                    requires_resign=False,
                )
            )

    return ParentLegalHistoryResponse(pending=pending, signed=signed)


@router.post("/legal-documents/sign", response_model=LegalSignatureResponse, status_code=201)
def parent_sign_document(
    payload: LegalSignatureRequest,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    doc = (
        db.query(SchoolLegalDocument)
        .filter(SchoolLegalDocument.id == payload.document_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    has_child = (
        db.query(ParentRelationship)
        .join(User, User.id == ParentRelationship.student_user_id)
        .filter(
            ParentRelationship.parent_user_id == user.id,
            ParentRelationship.is_active.is_(True),
            User.school_id == doc.school_id,
        )
        .first()
        is not None
    )
    if not has_child and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Sin hijos en este colegio.")
    existing = (
        db.query(SchoolLegalSignature)
        .filter(
            SchoolLegalSignature.document_id == doc.id,
            SchoolLegalSignature.signer_user_id == user.id,
        )
        .first()
    )
    if existing:
        return existing
    sig = SchoolLegalSignature(
        id=uuid4(),
        document_id=doc.id,
        signer_user_id=user.id,
        signer_name=user.name,
        signer_email=user.email,
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)
    return sig
