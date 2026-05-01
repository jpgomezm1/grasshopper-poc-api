"""Bitrix sync orchestration · GH-S10-BE-03/04/05.

Glue between the DB, bitrix_mapper, bitrix_client and bitrix_sync_log table.

Public entry points:

    sync_user_lead(db, user_id)          -> BitrixSyncLog
        Creates or updates a Bitrix Lead from the student's consolidated profile.

    sync_user_deal(db, user_id)          -> BitrixSyncLog
        Creates or updates a Deal from the recommended programs.

    sync_advisor_lead(db, advisor_lead)  -> BitrixSyncLog
        Posts an AdvisorLead → Bitrix lead/comment when student requests asesor.

    sync_inbound_status(db, payload)     -> Optional[User]
        Applies an inbound webhook payload (status update from Bitrix).

    enqueue_journey_completed(background_tasks, db, user_id)
        Helper for endpoints that finish the journey and want to fire-and-forget
        the sync via FastAPI BackgroundTasks (BE-04).

    notify_failure_email(db, log_row)
        Sends the BITRIX_NOTIFY_EMAIL alert when a sync fails after N retries
        (BE-05). Honors the same stub-fallback pattern as email_service.

All sync_* functions are idempotent: the entity_type/entity_id pair is used
to locate prior log rows so we re-use the bitrix_id (update instead of create).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.db.models import (
    AdvisorLead,
    BitrixSyncLog,
    BitrixSyncStatus,
    ConsolidatedProfileCache,
    EnglishTestResult,
    User,
    VocationalTestResult,
)
from app.services.bitrix_client import (
    BitrixCallResult,
    BitrixClient,
    get_client,
    safe_summary,
)
from app.services.bitrix_mapper import (
    MAPPER_VERSION,
    StudentSyncBundle,
    map_advisor_lead_comment,
    map_recommendations_to_deal_fields,
    map_user_to_contact_fields,
    map_user_to_lead_fields,
    normalize_inbound_status,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Bundle assembly (DB → StudentSyncBundle)
# -----------------------------------------------------------------------------


def _summary_for_test(test_id: str, scores: Dict[str, Any]) -> Dict[str, Any]:
    """Pick a one-liner highlight per test for the comments brief."""
    if not isinstance(scores, dict):
        return {"test_id": test_id, "top": str(scores)[:60]}
    if test_id == "mbti":
        personality = scores.get("personality") or scores.get("type")
        return {"test_id": test_id, "personality": personality}
    if test_id == "values":
        ranking = scores.get("ranking") or scores.get("top")
        if isinstance(ranking, list) and ranking:
            return {"test_id": test_id, "top": ranking[:3]}
    if test_id in {"big5", "ocean"}:
        order = ["O", "C", "E", "A", "N"]
        ordered = [
            (k, scores.get(k))
            for k in order
            if isinstance(scores.get(k), (int, float))
        ]
        return {"test_id": test_id, "top": ordered[:3]}
    if test_id in {"holland", "riasec", "istrong"}:
        ranked = sorted(
            (
                (k, v)
                for k, v in scores.items()
                if isinstance(v, (int, float)) and not k.startswith("_")
            ),
            key=lambda kv: kv[1],
            reverse=True,
        )
        return {"test_id": test_id, "top": [k for k, _ in ranked[:3]]}
    # generic fallback
    if "top" in scores:
        return {"test_id": test_id, "top": scores["top"]}
    return {"test_id": test_id, "top": "n/a"}


def build_student_bundle(db: DBSession, user_id: UUID) -> Optional[StudentSyncBundle]:
    """Assemble the StudentSyncBundle from the DB.

    Returns None if the user does not exist.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    school_name = None
    school_id = None
    if user.school:
        school_name = user.school.name
        school_id = str(user.school.id)

    bundle = StudentSyncBundle(
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        phone=user.phone,
        school_name=school_name,
        school_id=school_id,
        role=user.role.value if user.role else None,
        budget_band=user.budget_band,
        budget_max_usd=user.budget_max_usd,
        preferred_countries=list(user.preferred_countries or []),
        bitrix_lead_id=user.bitrix_lead_id,
    )

    cache = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == user.id)
        .first()
    )
    if cache:
        prof = cache.profile_data or {}
        bundle.profile_summary = (
            prof.get("narrative") or prof.get("summary") or prof.get("description")
        )
        bundle.profile_strengths = prof.get("strengths") or prof.get("top_strengths")
        bundle.profile_career_paths = prof.get("career_paths") or prof.get("paths")
        bundle.profile_hash = cache.profile_hash
        bundle.recommended_programs = list(cache.recommendations_data or [])

    voc = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        .all()
    )
    if voc:
        bundle.vocational_summary = [
            _summary_for_test(v.test_id, v.scores or {}) for v in voc
        ]

    eng = (
        db.query(EnglishTestResult)
        .filter(EnglishTestResult.user_id == user.id)
        .first()
    )
    if eng:
        bundle.english_cefr = eng.cefr_level

    return bundle


# -----------------------------------------------------------------------------
# Log helpers
# -----------------------------------------------------------------------------


def _start_log(
    db: DBSession,
    *,
    entity_type: str,
    entity_id: str,
    user_id: Optional[UUID],
    action: str,
    payload: Dict[str, Any],
) -> BitrixSyncLog:
    row = BitrixSyncLog(
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        payload=safe_summary(payload),
        status=BitrixSyncStatus.PENDING.value,
        provider="stub",  # overwritten on finish
        attempts=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _finish_log(
    db: DBSession,
    row: BitrixSyncLog,
    result: BitrixCallResult,
) -> BitrixSyncLog:
    row.attempts = result.attempts
    row.bitrix_response = (
        {"id": result.bitrix_id, "status_code": result.status_code}
        if result.success
        else {"error": (result.error or "")[:500]}
    )
    row.provider = result.provider
    if result.success:
        if result.provider == "stub":
            row.status = BitrixSyncStatus.STUB.value
        else:
            row.status = BitrixSyncStatus.SUCCESS.value
        row.synced_at = datetime.utcnow()
        row.error_message = None
    else:
        row.status = BitrixSyncStatus.FAILED.value
        row.error_message = (result.error or "unknown_error")[:500]
    db.commit()
    db.refresh(row)
    return row


def _last_successful_log(
    db: DBSession,
    *,
    entity_type: str,
    entity_id: str,
) -> Optional[BitrixSyncLog]:
    return (
        db.query(BitrixSyncLog)
        .filter(
            BitrixSyncLog.entity_type == entity_type,
            BitrixSyncLog.entity_id == entity_id,
            BitrixSyncLog.status.in_(
                [BitrixSyncStatus.SUCCESS.value, BitrixSyncStatus.STUB.value]
            ),
        )
        .order_by(BitrixSyncLog.created_at.desc())
        .first()
    )


def _payload_hash(fields: Dict[str, Any]) -> str:
    """Stable hash of normalized fields for outbound dedup (GH-S11 hardening)."""
    import hashlib
    import json

    canonical = json.dumps(fields, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _is_duplicate_of_last(
    prior: Optional[BitrixSyncLog], fields: Dict[str, Any]
) -> bool:
    """True if the previous successful sync had the exact same payload hash.

    GH-S11 · prevents redundant Bitrix calls when journey status / scores
    haven't changed between consecutive triggers. Both sides are compared
    after ``safe_summary`` so PII masking doesn't introduce false negatives.
    """
    if not prior or not prior.payload:
        return False
    try:
        return _payload_hash(prior.payload) == _payload_hash(safe_summary(fields))
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Public sync functions
# -----------------------------------------------------------------------------


def sync_user_lead(
    db: DBSession,
    user_id: UUID,
    *,
    client: Optional[BitrixClient] = None,
) -> BitrixSyncLog:
    """Create or update a Bitrix Lead for the given user.

    Idempotent: if a previous successful sync exists, we update the same
    Bitrix lead id. Otherwise we create.
    """
    bundle = build_student_bundle(db, user_id)
    if bundle is None:
        raise ValueError(f"user {user_id} not found")

    fields = map_user_to_lead_fields(bundle)
    client = client or get_client()

    # Resolve previous lead id (User column wins · log row is fallback)
    prior = _last_successful_log(db, entity_type="user", entity_id=str(user_id))
    prior_lead_id = bundle.bitrix_lead_id or (
        (prior.bitrix_response or {}).get("id") if prior else None
    )

    action = "update" if prior_lead_id else "create"

    # GH-S11 dedup pre-check (S10 hardening) · skip if payload unchanged
    if prior and prior_lead_id and _is_duplicate_of_last(prior, fields):
        log_row = _start_log(
            db,
            entity_type="user",
            entity_id=str(user_id),
            user_id=user_id,
            action="skip_dedup",
            payload={"reason": "payload_unchanged", "prior_log_id": str(prior.id)},
        )
        from app.services.bitrix_client import BitrixCallResult
        result = BitrixCallResult(
            provider="dedup",
            success=True,
            bitrix_id=prior_lead_id,
            response={"id": prior_lead_id, "deduped": True},
            attempts=0,
        )
        return _finish_log(db, log_row, result)

    log_row = _start_log(
        db,
        entity_type="user",
        entity_id=str(user_id),
        user_id=user_id,
        action=action,
        payload=fields,
    )

    if prior_lead_id:
        result = client.update_lead(prior_lead_id, fields)
    else:
        result = client.create_lead(fields)

    log_row = _finish_log(db, log_row, result)

    # Persist the bitrix_lead_id back to User on success
    if result.success and result.bitrix_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.bitrix_lead_id != result.bitrix_id:
            user.bitrix_lead_id = result.bitrix_id
            db.commit()

    if not result.success:
        notify_failure_email(db, log_row)

    return log_row


def sync_user_deal(
    db: DBSession,
    user_id: UUID,
    *,
    client: Optional[BitrixClient] = None,
) -> BitrixSyncLog:
    """Create or update a Bitrix Deal from the recommended programs."""
    bundle = build_student_bundle(db, user_id)
    if bundle is None:
        raise ValueError(f"user {user_id} not found")
    if not bundle.recommended_programs:
        raise ValueError(f"user {user_id} has no recommended programs yet")

    fields = map_recommendations_to_deal_fields(
        bundle,
        lead_id=bundle.bitrix_lead_id,
    )
    client = client or get_client()

    prior = _last_successful_log(db, entity_type="deal", entity_id=str(user_id))
    prior_deal_id = (
        (prior.bitrix_response or {}).get("id") if prior else None
    )
    action = "update" if prior_deal_id else "create"

    # GH-S11 dedup pre-check (S10 hardening) · skip if payload unchanged
    if prior and prior_deal_id and _is_duplicate_of_last(prior, fields):
        log_row = _start_log(
            db,
            entity_type="deal",
            entity_id=str(user_id),
            user_id=user_id,
            action="skip_dedup",
            payload={"reason": "payload_unchanged", "prior_log_id": str(prior.id)},
        )
        result = BitrixCallResult(
            provider="dedup",
            success=True,
            bitrix_id=prior_deal_id,
            response={"id": prior_deal_id, "deduped": True},
            attempts=0,
        )
        return _finish_log(db, log_row, result)

    log_row = _start_log(
        db,
        entity_type="deal",
        entity_id=str(user_id),
        user_id=user_id,
        action=action,
        payload=fields,
    )

    if prior_deal_id:
        result = client.update_deal(prior_deal_id, fields)
    else:
        result = client.create_deal(fields)

    log_row = _finish_log(db, log_row, result)
    if not result.success:
        notify_failure_email(db, log_row)
    return log_row


def sync_advisor_lead(
    db: DBSession,
    advisor_lead: AdvisorLead,
    *,
    client: Optional[BitrixClient] = None,
) -> BitrixSyncLog:
    """Sync an AdvisorLead · creates a Lead with the brief as comment."""
    user_id: Optional[UUID] = None
    if advisor_lead.session and advisor_lead.session.user_id:
        user_id = advisor_lead.session.user_id

    if user_id is None:
        # Anonymous flow: no User row · build a minimal bundle just from contact data.
        bundle = StudentSyncBundle(
            user_id=str(advisor_lead.id),
            email=advisor_lead.email,
            name=advisor_lead.name,
            phone=advisor_lead.phone,
            advisor_brief=advisor_lead.advisor_brief,
            advisor_requested=True,
        )
    else:
        bundle = build_student_bundle(db, user_id)
        if bundle is None:
            raise ValueError(f"user {user_id} not found")
        bundle.advisor_brief = advisor_lead.advisor_brief
        bundle.advisor_requested = True

    fields = map_user_to_lead_fields(bundle)
    client = client or get_client()

    log_row = _start_log(
        db,
        entity_type="advisor_lead",
        entity_id=str(advisor_lead.id),
        user_id=user_id,
        action="create",
        payload=fields,
    )

    result = client.create_lead(fields)
    log_row = _finish_log(db, log_row, result)

    # Best-effort timeline comment with the auto-brief (non-blocking)
    if result.success and result.bitrix_id:
        try:
            comment = map_advisor_lead_comment(bundle)
            client.add_lead_comment(result.bitrix_id, comment)
        except Exception as exc:  # pragma: no cover · defensive
            logger.warning("bitrix add_lead_comment failed · %s", exc)

    if not result.success:
        notify_failure_email(db, log_row)

    return log_row


def sync_inbound_status(
    db: DBSession,
    payload: Dict[str, Any],
) -> Optional[User]:
    """Apply an inbound webhook payload (Bitrix → Hopper).

    Expected fields (best-effort, Bitrix sends a variety of shapes):

        {
            "event": "ONCRMLEADUPDATE",
            "data": {
                "FIELDS": {
                    "ID": "<bitrix_lead_id>",
                    "STATUS_ID": "PROCESSED" | "JUNK" | ...,
                    "UF_CRM_GH_USER_ID": "<our user_id>"  (preferred match)
                }
            }
        }

    Returns the updated User or None when no matching user exists.
    """
    fields = (
        payload.get("data", {}).get("FIELDS")
        or payload.get("FIELDS")
        or payload
    )
    if not isinstance(fields, dict):
        return None

    raw_user_id = fields.get("UF_CRM_GH_USER_ID")
    bitrix_lead_id = fields.get("ID") or fields.get("LEAD_ID")
    raw_status = fields.get("STATUS_ID") or fields.get("STATUS")

    user: Optional[User] = None
    if raw_user_id:
        try:
            user = (
                db.query(User)
                .filter(User.id == UUID(str(raw_user_id)))
                .first()
            )
        except (ValueError, TypeError):
            user = None
    if user is None and bitrix_lead_id:
        user = (
            db.query(User)
            .filter(User.bitrix_lead_id == str(bitrix_lead_id))
            .first()
        )

    if user is None:
        # Log the inbound anyway · resource_id is the bitrix lead id
        row = BitrixSyncLog(
            entity_type="inbound",
            entity_id=str(bitrix_lead_id or "unknown"),
            user_id=None,
            action="inbound_status",
            payload={"FIELDS_keys": sorted(fields.keys()), "STATUS": raw_status},
            status=BitrixSyncStatus.SUCCESS.value,
            provider="bitrix",
            attempts=1,
            synced_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        return None

    new_status = normalize_inbound_status(raw_status)
    user.bitrix_lead_status = new_status
    user.bitrix_lead_status_at = datetime.utcnow()
    if bitrix_lead_id and not user.bitrix_lead_id:
        user.bitrix_lead_id = str(bitrix_lead_id)

    log_row = BitrixSyncLog(
        entity_type="inbound",
        entity_id=str(user.id),
        user_id=user.id,
        action="inbound_status",
        payload={
            "FIELDS_keys": sorted(fields.keys()),
            "STATUS": raw_status,
            "normalized": new_status,
        },
        status=BitrixSyncStatus.SUCCESS.value,
        provider="bitrix",
        attempts=1,
        synced_at=datetime.utcnow(),
    )
    db.add(log_row)
    db.commit()
    return user


# -----------------------------------------------------------------------------
# BackgroundTasks helper (BE-04 · journey_completed)
# -----------------------------------------------------------------------------


def enqueue_journey_completed(
    background_tasks: BackgroundTasks,
    user_id: UUID,
) -> None:
    """Schedule sync_user_lead + sync_user_deal as background tasks.

    Mirrors the S5 parsing pattern: enqueue and return 202 to the caller.
    """
    from app.db.database import SessionLocal

    def _runner_lead(uid: UUID) -> None:
        db = SessionLocal()
        try:
            sync_user_lead(db, uid)
        except Exception as exc:  # pragma: no cover · defensive
            logger.warning("bitrix bg sync_user_lead failed · %s", exc)
        finally:
            db.close()

    def _runner_deal(uid: UUID) -> None:
        db = SessionLocal()
        try:
            sync_user_deal(db, uid)
        except ValueError:
            # No recommendations yet · skip silently
            pass
        except Exception as exc:  # pragma: no cover · defensive
            logger.warning("bitrix bg sync_user_deal failed · %s", exc)
        finally:
            db.close()

    background_tasks.add_task(_runner_lead, user_id)
    background_tasks.add_task(_runner_deal, user_id)


# -----------------------------------------------------------------------------
# Failure notification (BE-05)
# -----------------------------------------------------------------------------


def notify_failure_email(db: DBSession, log_row: BitrixSyncLog) -> None:
    """Email the Grasshopper team when a sync fails after retries.

    Uses the same email backend as reports (Resend default · stub fallback).
    No-op if BITRIX_NOTIFY_EMAIL is empty.
    """
    settings = get_settings()
    to = (settings.bitrix_notify_email or "").strip()
    if not to:
        logger.info(
            "bitrix failure not notified · BITRIX_NOTIFY_EMAIL empty · log=%s",
            log_row.id,
        )
        return

    try:
        from app.services.email_service import get_backend as get_email_backend
    except Exception as exc:  # pragma: no cover
        logger.warning("email backend unavailable · %s", exc)
        return

    body = (
        f"Una sincronización con Bitrix falló tras {log_row.attempts} intentos.\n\n"
        f"entity_type: {log_row.entity_type}\n"
        f"entity_id: {log_row.entity_id}\n"
        f"action: {log_row.action}\n"
        f"error: {log_row.error_message or 'unknown'}\n\n"
        f"Revisa /admin/bitrix/sync-log para reintentar manualmente.\n"
    )
    html = f"<pre style='font-family:monospace;font-size:13px;'>{body}</pre>"

    try:
        backend = get_email_backend()
        backend.send_with_attachment(
            to=to,
            subject="[Grasshopper] Bitrix sync failed",
            html=html,
            attachment_bytes=b"",
            attachment_filename="bitrix-failure.txt",
            attachment_mime="text/plain",
        )
    except Exception as exc:  # pragma: no cover · defensive
        logger.warning("bitrix failure email failed · %s", exc)


# -----------------------------------------------------------------------------
# Manual trigger / read helpers used by the admin router
# -----------------------------------------------------------------------------


def manual_sync(
    db: DBSession,
    *,
    entity_type: str,
    entity_id: str,
) -> BitrixSyncLog:
    """Manual sync from the super_admin panel (BE-07 · POST manual trigger)."""
    if entity_type == "user":
        return sync_user_lead(db, UUID(entity_id))
    if entity_type == "deal":
        return sync_user_deal(db, UUID(entity_id))
    if entity_type == "advisor_lead":
        adv = (
            db.query(AdvisorLead)
            .filter(AdvisorLead.id == UUID(entity_id))
            .first()
        )
        if not adv:
            raise ValueError(f"advisor_lead {entity_id} not found")
        return sync_advisor_lead(db, adv)
    raise ValueError(f"unsupported entity_type · {entity_type}")


def list_sync_logs(
    db: DBSession,
    *,
    page: int = 1,
    page_size: int = 50,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> tuple[List[BitrixSyncLog], int]:
    q = db.query(BitrixSyncLog)
    if entity_type:
        q = q.filter(BitrixSyncLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(BitrixSyncLog.entity_id == entity_id)
    if status:
        q = q.filter(BitrixSyncLog.status == status)
    if user_id:
        q = q.filter(BitrixSyncLog.user_id == user_id)
    total = q.count()
    rows = (
        q.order_by(BitrixSyncLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def status_overview(db: DBSession) -> Dict[str, Any]:
    """Compact overview for /admin/integrations/bitrix/status."""
    settings = get_settings()
    client = get_client()

    by_status_rows = (
        db.query(BitrixSyncLog.status)
        .all()
    )
    counts: Dict[str, int] = {}
    for (status_value,) in by_status_rows:
        counts[status_value] = counts.get(status_value, 0) + 1

    last = (
        db.query(BitrixSyncLog)
        .order_by(BitrixSyncLog.created_at.desc())
        .first()
    )
    last_payload = None
    if last:
        last_payload = {
            "id": str(last.id),
            "entity_type": last.entity_type,
            "entity_id": last.entity_id,
            "status": last.status,
            "provider": last.provider,
            "attempts": last.attempts,
            "synced_at": last.synced_at.isoformat() if last.synced_at else None,
            "created_at": last.created_at.isoformat(),
        }

    return {
        "provider": client.provider,
        "is_stub": client.is_stub,
        "webhook_configured": bool((settings.bitrix_webhook_url or "").strip()),
        "inbound_enabled": bool(settings.bitrix_inbound_enabled),
        "rate_limit_rps": settings.bitrix_rate_limit_rps,
        "max_attempts": settings.bitrix_max_attempts,
        "mapper_version": MAPPER_VERSION,
        "counts_by_status": counts,
        "last_event": last_payload,
        "notify_email_configured": bool((settings.bitrix_notify_email or "").strip()),
    }
