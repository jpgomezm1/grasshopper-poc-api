"""Habeas Data privacy endpoints · GH-S11.5-BE-07 · D-026.

Implements the data-subject rights mandated by Ley 1581/2012 (Colombia)
Art. 8 · access · update · revoke · delete · proof of authorization.

Endpoints:

    GET    /me/data           · full export of user data + consent state
    POST   /me/consents       · grant/revoke consent toggles
    DELETE /me/data           · soft-delete (anonymize + deactivate)
    GET    /privacy-policy    · current Privacy Policy markdown + version

The first three require authentication and operate strictly on the
caller's own User row. The fourth is public.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import (
    BitrixSyncLog,
    ConsentAuditLog,
    ConsolidatedProfileCache,
    EnglishTestResult,
    JournalEntry,
    Report,
    SavedOferta,
    Session as JourneySession,
    User,
    VocationalTestResult,
)
from app.services import consent_service
from app.services.consent_service import (
    CONSENT_KINDS,
    consent_state,
    grant_consent,
    is_minor,
    log_data_deletion,
    log_data_export,
    revoke_consent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["privacy"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConsentToggleRequest(BaseModel):
    """Granular per-finalidad toggle.

    Each field is optional · None means "no change". True grants, False
    revokes. Backend writes one audit row per non-None field.
    """

    data_processing: Optional[bool] = None
    crm_sync: Optional[bool] = None
    parental: Optional[bool] = None


class ConsentStateResponse(BaseModel):
    data_processing: Dict[str, Any]
    crm_sync: Dict[str, Any]
    parental: Dict[str, Any]
    policy_version_current: str
    needs_re_acceptance: bool


class PrivacyPolicyResponse(BaseModel):
    version: str
    markdown: str
    dpo_email: str


class DataDeletionResponse(BaseModel):
    status: str = Field(default="scheduled")
    deleted_at: datetime
    note: str


class ExportPayload(BaseModel):
    """Loose schema · returns whatever the user has · serializable."""

    user_id: UUID
    email: str
    name: Optional[str]
    role: str
    school_id: Optional[UUID]
    birthdate: Optional[str]
    consent_state: Dict[str, Any]
    sessions: List[Dict[str, Any]] = []
    journal_entries: List[Dict[str, Any]] = []
    vocational_tests: List[Dict[str, Any]] = []
    english_test: Optional[Dict[str, Any]] = None
    consolidated_profile: Optional[Dict[str, Any]] = None
    reports: List[Dict[str, Any]] = []
    saved_offers: List[str] = []
    bitrix_sync_log: List[Dict[str, Any]] = []
    consent_audit_log: List[Dict[str, Any]] = []
    exported_at: datetime


# ---------------------------------------------------------------------------
# GET /me/data · full export
# ---------------------------------------------------------------------------


@router.get(
    "/me/data",
    response_model=ExportPayload,
    summary="GH-S11.5-BE-07 · Habeas Data right of access (Ley 1581 Art. 8.a)",
)
def export_my_data(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns ALL data the platform holds for the calling user.

    Includes consent state and the immutable audit trail · titular tiene
    derecho a "conocer los datos" y "solicitar prueba de la autorización".
    """
    # Sessions + journal entries (joined via session relationship)
    sessions = (
        db.query(JourneySession)
        .filter(JourneySession.user_id == current_user.id)
        .all()
    )
    sessions_payload = [
        {
            "id": str(s.id),
            "current_step": s.current_step,
            "current_stage": (
                s.current_stage.value
                if hasattr(s.current_stage, "value")
                else str(s.current_stage)
            ),
            "is_completed": s.is_completed,
            "is_paused": s.is_paused,
            "answers": s.answers or {},
            "completed_steps": s.completed_steps or [],
            "selected_routes": s.selected_routes or [],
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]

    journal_rows = (
        db.query(JournalEntry)
        .join(JourneySession, JourneySession.id == JournalEntry.session_id)
        .filter(JourneySession.user_id == current_user.id)
        .order_by(JournalEntry.created_at.desc())
        .all()
    )
    journal_payload = [
        {
            "id": str(j.id),
            "session_id": str(j.session_id),
            "entry_type": (
                j.entry_type.value
                if hasattr(j.entry_type, "value")
                else str(j.entry_type)
            ),
            "content": j.content,
            "tags": j.tags or [],
            "auto_generated": bool(j.auto_generated),
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in journal_rows
    ]

    voc_rows = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == current_user.id)
        .all()
    )
    voc_payload = [
        {
            "test_id": v.test_id,
            "scores": v.scores or {},
            "answers": v.answers or {},
            "source": getattr(v, "source", None) or "internal",
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in voc_rows
    ]

    english_row = (
        db.query(EnglishTestResult)
        .filter(EnglishTestResult.user_id == current_user.id)
        .first()
    )
    english_payload = None
    if english_row:
        english_payload = {
            "cefr_level": english_row.cefr_level,
            "score": getattr(english_row, "score", None),
            "answers": getattr(english_row, "answers", None) or {},
            "created_at": (
                english_row.created_at.isoformat() if english_row.created_at else None
            ),
        }

    profile = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == current_user.id)
        .first()
    )
    consolidated_payload = None
    if profile:
        consolidated_payload = {
            "profile_hash": profile.profile_hash,
            "profile_data": profile.profile_data,
            "recommendations_data": profile.recommendations_data,
            "created_at": (
                profile.created_at.isoformat() if profile.created_at else None
            ),
            "invalidated_at": (
                profile.invalidated_at.isoformat()
                if profile.invalidated_at
                else None
            ),
        }

    report_rows = (
        db.query(Report).filter(Report.user_id == current_user.id).all()
    )
    reports_payload = [
        {
            "id": str(r.id),
            "file_path": r.file_path,
            "profile_hash": getattr(r, "profile_hash", None),
            "email_sent": bool(getattr(r, "email_sent", False)),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in report_rows
    ]

    saved_rows = (
        db.query(SavedOferta.oferta_id)
        .filter(SavedOferta.user_id == current_user.id)
        .all()
    )
    saved_payload = [str(r[0]) for r in saved_rows]

    bitrix_rows = (
        db.query(BitrixSyncLog)
        .filter(BitrixSyncLog.user_id == current_user.id)
        .order_by(BitrixSyncLog.created_at.desc())
        .all()
    )
    bitrix_payload = [
        {
            "id": str(b.id),
            "entity_type": b.entity_type,
            "action": b.action,
            "status": b.status,
            "provider": b.provider,
            "attempts": b.attempts,
            "synced_at": b.synced_at.isoformat() if b.synced_at else None,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            # NOTE: payload stored is already `safe_summary`-masked.
            "payload_summary": b.payload,
        }
        for b in bitrix_rows
    ]

    audit_rows = (
        db.query(ConsentAuditLog)
        .filter(ConsentAuditLog.user_id == current_user.id)
        .order_by(ConsentAuditLog.created_at.desc())
        .all()
    )
    audit_payload = [
        {
            "id": str(a.id),
            "event": a.event,
            "policy_version": a.policy_version,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in audit_rows
    ]

    # Audit row for this export · proof of access invocation.
    log_data_export(db, current_user, request=request)
    db.commit()

    return ExportPayload(
        user_id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=(
            current_user.role.value
            if hasattr(current_user.role, "value")
            else str(current_user.role)
        ),
        school_id=current_user.school_id,
        birthdate=(
            current_user.birthdate.isoformat() if current_user.birthdate else None
        ),
        consent_state=consent_state(current_user),
        sessions=sessions_payload,
        journal_entries=journal_payload,
        vocational_tests=voc_payload,
        english_test=english_payload,
        consolidated_profile=consolidated_payload,
        reports=reports_payload,
        saved_offers=saved_payload,
        bitrix_sync_log=bitrix_payload,
        consent_audit_log=audit_payload,
        exported_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /me/consents · toggle on/off per finalidad
# ---------------------------------------------------------------------------


@router.post(
    "/me/consents",
    response_model=ConsentStateResponse,
    summary="GH-S11.5-BE-07 · grant/revoke consents (Ley 1581 Art. 8.e)",
)
def update_my_consents(
    request: Request,
    payload: ConsentToggleRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-finalidad toggle. Each non-None field flips one consent kind.

    When `crm_sync` is revoked, we enqueue a Bitrix de-sync (mark lead as
    JUNK with Habeas Data note) so the upstream CRM reflects the revocation.
    """
    settings = get_settings()
    changed: List[str] = []

    pairs = [
        ("data_processing", payload.data_processing),
        ("crm_sync", payload.crm_sync),
        ("parental", payload.parental),
    ]

    for kind, value in pairs:
        if value is None:
            continue
        if kind not in CONSENT_KINDS:  # pragma: no cover · defensive
            continue
        if value:
            grant_consent(
                db,
                current_user,
                kind,
                request=request,
                policy_version=settings.privacy_policy_version,
            )
        else:
            revoke_consent(db, current_user, kind, request=request)
        changed.append(kind)

    db.commit()
    db.refresh(current_user)

    # Side effect · de-sync Bitrix lead when crm_sync was revoked.
    if payload.crm_sync is False:
        from app.services.bitrix_sync_service import desync_user_on_revoke
        from app.db.database import SessionLocal

        def _runner_desync(uid: UUID) -> None:
            db2 = SessionLocal()
            try:
                desync_user_on_revoke(db2, uid)
            except Exception as exc:  # pragma: no cover · defensive
                logger.warning("desync on revoke failed · %s", exc)
            finally:
                db2.close()

        background_tasks.add_task(_runner_desync, current_user.id)

    state = consent_state(current_user)
    return ConsentStateResponse(**state)


# ---------------------------------------------------------------------------
# DELETE /me/data · soft-delete (anonymize + deactivate)
# ---------------------------------------------------------------------------


@router.delete(
    "/me/data",
    response_model=DataDeletionResponse,
    summary="GH-S11.5-BE-07 · soft-delete user data (Ley 1581 Art. 8.f)",
)
def delete_my_data(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: deactivate + anonymize PII + cascade-clear journey data.

    We do NOT hard-delete: Ley 1581 Art. 11 + Decreto 1377 Art. 23 require
    a 5-year retention of audit logs + minimal evidence that the data was
    held and properly removed. The User row stays in DB · all PII columns
    are redacted to placeholder values · is_active=False blocks login.

    Cascade child rows (sessions · journal_entries · tests · profile cache
    · saved_ofertas · reports) are deleted via SQLAlchemy `cascade="all,
    delete-orphan"` on the relationships. Audit log + consent log rows
    persist with `user_id=None` (FK SET NULL).
    """
    user_id = current_user.id
    # Capture the Bitrix lead id BEFORE we anonymize · the bg runner will
    # need it explicitly because by the time it runs, user.bitrix_lead_id
    # has been cleared in the DB (anonymization step below).
    former_bitrix_lead_id = current_user.bitrix_lead_id

    # Bitrix de-sync first (best-effort · before clearing the lead id).
    if former_bitrix_lead_id:
        from app.services.bitrix_client import get_client
        from app.db.database import SessionLocal
        from app.db.models import BitrixSyncLog, BitrixSyncStatus

        def _runner(uid: UUID, lead_id: str) -> None:
            db2 = SessionLocal()
            try:
                # Mark the lead as JUNK with Habeas Data note · we use the
                # captured lead_id directly because user_id row already has
                # bitrix_lead_id=None at this point.
                client = get_client()
                fields = {
                    "STATUS_ID": "JUNK",
                    "COMMENTS": (
                        "Account deleted by user · Habeas Data Ley 1581/2012 "
                        "(Colombia)."
                    ),
                }
                row = BitrixSyncLog(
                    entity_type="user",
                    entity_id=str(uid),
                    user_id=None,  # user already anonymized
                    action="data_deletion_desync",
                    payload={"former_lead_id": lead_id},
                    status=BitrixSyncStatus.PENDING.value,
                    provider="consent_gate",
                    attempts=0,
                )
                db2.add(row)
                db2.commit()
                db2.refresh(row)
                try:
                    result = client.update_lead(lead_id, fields)
                    row.status = (
                        BitrixSyncStatus.SUCCESS.value
                        if result.success
                        else BitrixSyncStatus.FAILED.value
                    )
                    row.provider = result.provider or "consent_gate"
                    row.attempts = result.attempts
                    row.synced_at = datetime.utcnow() if result.success else None
                    if not result.success:
                        row.error_message = (result.error or "")[:500]
                    db2.commit()
                except Exception as exc:  # pragma: no cover · defensive
                    logger.warning(
                        "data_deletion bitrix desync failed · %s",
                        exc,
                    )
                    row.status = BitrixSyncStatus.FAILED.value
                    row.error_message = str(exc)[:500]
                    db2.commit()
            except Exception as exc:  # pragma: no cover · defensive
                logger.warning("desync on deletion failed · %s", exc)
            finally:
                db2.close()

        background_tasks.add_task(_runner, user_id, former_bitrix_lead_id)

    # Audit BEFORE mutation so user_id is still on the row.
    log_data_deletion(db, current_user, request=request)
    db.flush()

    # Cascade-deletable rows go via relationships when supported, fallback
    # to explicit deletes for tables that don't cascade from User.
    db.query(VocationalTestResult).filter(
        VocationalTestResult.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(SavedOferta).filter(
        SavedOferta.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(ConsolidatedProfileCache).filter(
        ConsolidatedProfileCache.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(EnglishTestResult).filter(
        EnglishTestResult.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(Report).filter(
        Report.user_id == user_id
    ).delete(synchronize_session=False)
    # Sessions cascade journal_entries via the relationship.
    db.query(JourneySession).filter(
        JourneySession.user_id == user_id
    ).delete(synchronize_session=False)

    # Anonymize User row · keep schema integrity, drop PII.
    placeholder_email = f"deleted+{user_id}@privacy.grasshopper.local"
    current_user.email = placeholder_email
    current_user.name = None
    current_user.phone = None
    current_user.hashed_password = "!"  # invalid bcrypt → no login possible
    current_user.is_active = False
    current_user.password_reset_token = None
    current_user.password_reset_expires = None
    current_user.bitrix_lead_id = None
    current_user.bitrix_lead_status = None
    current_user.bitrix_lead_status_at = None
    current_user.budget_band = None
    current_user.budget_max_usd = None
    current_user.preferred_countries = []
    current_user.onboarding_answers = {}
    current_user.english_cefr_level = None
    current_user.birthdate = None
    current_user.consent_data_processing_at = None
    current_user.consent_crm_sync_at = None
    current_user.consent_parental_at = None
    # Keep `consent_data_processing_version` for retention proof.

    db.commit()

    return DataDeletionResponse(
        status="scheduled",
        deleted_at=datetime.utcnow(),
        note=(
            "Datos personales anonimizados. Logs de auditoría retenidos "
            "5 años por obligación legal (Ley 1581/2012 Art. 11)."
        ),
    )


# ---------------------------------------------------------------------------
# GET /privacy-policy · public · current text
# ---------------------------------------------------------------------------


_POLICY_CACHE: Dict[str, Any] = {"version": None, "markdown": None}


def _load_policy_markdown() -> str:
    """Loads docs/PRIVACY_POLICY_v1.md · cached after first load."""
    settings = get_settings()
    if (
        _POLICY_CACHE.get("version") == settings.privacy_policy_version
        and _POLICY_CACHE.get("markdown") is not None
    ):
        return _POLICY_CACHE["markdown"]

    import os
    candidate_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "docs", "PRIVACY_POLICY_v1.md"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "PRIVACY_POLICY_v1.md"),
        os.path.join("docs", "PRIVACY_POLICY_v1.md"),
    ]
    for p in candidate_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
                _POLICY_CACHE["version"] = settings.privacy_policy_version
                _POLICY_CACHE["markdown"] = content
                return content
        except FileNotFoundError:
            continue
    # Fallback skeleton if file not deployed yet.
    return (
        f"# Política de Tratamiento de Datos · Grasshopper · "
        f"v{settings.privacy_policy_version}\n\n"
        "Documento en preparación. Para consultas escribir a "
        f"{settings.privacy_dpo_email}."
    )


@router.get(
    "/privacy-policy",
    response_model=PrivacyPolicyResponse,
    summary="Public · current Privacy Policy markdown",
)
def get_privacy_policy():
    settings = get_settings()
    return PrivacyPolicyResponse(
        version=settings.privacy_policy_version,
        markdown=_load_policy_markdown(),
        dpo_email=settings.privacy_dpo_email,
    )
