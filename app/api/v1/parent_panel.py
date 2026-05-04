"""Parent panel router · GH-SCHOOL-ADMIN-PARENT · 2026-05-04.

Read-only access for the new `parent` role. Parents see only:
- their own children (linked via parent_relationships)
- public progress KPIs (% advance, tests count, profile generated)
- public reports (PDF previously generated)
- school events for their children's school
- legal documents pending signature

NEVER exposes clinical analysis, dossier notes, session notes,
admin notes, or any staff-only artifact.
"""
from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    ConsolidatedProfileCache,
    OnboardingStatus,
    ParentRelationship,
    Report,
    School,
    SchoolEvent,
    SchoolLegalDocument,
    SchoolLegalSignature,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.school_admin import (
    LegalDocumentResponse,
    LegalSignatureRequest,
    LegalSignatureResponse,
    ParentMeResponse,
)
from app.services import school_admin_service

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/parent", tags=["Parent Panel"])


def _gate_parent(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.PARENT and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Solo padres autenticados.")
    return current_user


@router.get("/me", response_model=ParentMeResponse)
def parent_me(
    user: User = Depends(_gate_parent), db: DBSession = Depends(get_db)
):
    children = school_admin_service.list_children_for_parent(db, user.id)
    return {
        "parent_user_id": user.id,
        "parent_name": user.name,
        "children": children,
    }


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
    # Return ONLY public-safe fields · stripped of clinical / private signals.
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
        "generated_at": profile.created_at,
        "public_profile": public_fields,
    }


@router.get("/children/{student_id}/reports")
def child_reports(
    student_id: UUID,
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    if not school_admin_service.parent_can_see_student(db, user.id, student_id):
        raise HTTPException(status_code=403, detail="Sin acceso a este estudiante.")
    reports = (
        db.query(Report)
        .filter(Report.user_id == student_id)
        .order_by(Report.created_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "title": getattr(r, "title", None) or "Reporte",
                "created_at": r.created_at,
                "url": getattr(r, "pdf_url", None),
            }
            for r in reports
        ]
    }


@router.get("/events")
def parent_events(
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Events for any school where the parent has at least one active child."""
    rels = (
        db.query(ParentRelationship, User)
        .join(User, User.id == ParentRelationship.student_user_id)
        .filter(
            ParentRelationship.parent_user_id == user.id,
            ParentRelationship.is_active.is_(True),
        )
        .all()
    )
    school_ids = list({u.school_id for _r, u in rels if u.school_id})
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
            }
            for e in events
        ]
    }


@router.get("/legal-documents", response_model=List[LegalDocumentResponse])
def parent_legal_docs(
    user: User = Depends(_gate_parent),
    db: DBSession = Depends(get_db),
):
    """Legal docs pending signature from any of the parent's children's schools."""
    rels = (
        db.query(User)
        .join(ParentRelationship, ParentRelationship.student_user_id == User.id)
        .filter(
            ParentRelationship.parent_user_id == user.id,
            ParentRelationship.is_active.is_(True),
        )
        .all()
    )
    school_ids = list({u.school_id for u in rels if u.school_id})
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
    # Caller must have a child in this school.
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
    from datetime import datetime
    from uuid import uuid4

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
