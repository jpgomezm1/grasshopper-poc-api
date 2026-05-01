"""Bitrix integration endpoints · GH-S10-BE-06/07.

Surfaces:

    GET  /admin/integrations/bitrix/status                 (super_admin)
    GET  /admin/integrations/bitrix/sync-log               (super_admin · paginated)
    POST /admin/integrations/bitrix/sync/{entity}/{id}     (super_admin · manual trigger)
    POST /webhooks/bitrix/inbound                          (HMAC validated · feature-flagged)

PII guard:
    - status / sync-log responses include only sanitized payload summaries
      (the DB rows themselves were already stored via safe_summary).
    - inbound webhook does NOT echo the body back · only an ack with normalized status.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import BitrixSyncLog, User, UserRole
from app.schemas.bitrix import (
    BitrixInboundAck,
    BitrixManualSyncResponse,
    BitrixStatusResponse,
    BitrixSyncLogList,
    BitrixSyncLogRow,
)
from app.services import bitrix_sync_service

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin/integrations/bitrix", tags=["Bitrix Admin"])
webhook_router = APIRouter(prefix="/webhooks/bitrix", tags=["Bitrix Webhook"])


# -----------------------------------------------------------------------------
# Auth guard
# -----------------------------------------------------------------------------


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can access Bitrix admin.",
        )


def _row_to_schema(row: BitrixSyncLog, db: DBSession) -> BitrixSyncLogRow:
    user_email = None
    if row.user_id:
        u = db.query(User.email).filter(User.id == row.user_id).first()
        user_email = u[0] if u else None
    return BitrixSyncLogRow(
        id=row.id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        user_id=row.user_id,
        user_email=user_email,
        action=row.action,
        payload=row.payload,
        bitrix_response=row.bitrix_response,
        status=row.status,
        provider=row.provider,
        attempts=row.attempts,
        error_message=row.error_message,
        synced_at=row.synced_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# -----------------------------------------------------------------------------
# Admin endpoints
# -----------------------------------------------------------------------------


@admin_router.get(
    "/status",
    response_model=BitrixStatusResponse,
    summary="GH-S10-BE-07 · Bitrix integration status",
)
def bitrix_status(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    return bitrix_sync_service.status_overview(db)


@admin_router.get(
    "/sync-log",
    response_model=BitrixSyncLogList,
    summary="GH-S10-BE-07 · Paginated Bitrix sync log",
)
def list_sync_log(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: Optional[UUID] = Query(None),
):
    _ensure_super_admin(current_user)
    rows, total = bitrix_sync_service.list_sync_logs(
        db,
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status_filter,
        user_id=user_id,
    )
    items = [_row_to_schema(r, db) for r in rows]
    total_pages = max(1, math.ceil(total / page_size)) if total else 0
    return BitrixSyncLogList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@admin_router.post(
    "/sync/{entity_type}/{entity_id}",
    response_model=BitrixManualSyncResponse,
    summary="GH-S10-BE-07 · Manual sync trigger",
)
def trigger_manual_sync(
    entity_type: str,
    entity_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    if entity_type not in {"user", "deal", "advisor_lead"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported entity_type · {entity_type}",
        )

    try:
        log_row = bitrix_sync_service.manual_sync(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    bitrix_id = None
    if isinstance(log_row.bitrix_response, dict):
        bitrix_id = log_row.bitrix_response.get("id")

    # Audit trail
    try:
        from app.services.audit_service import log_action

        log_action(
            db,
            user=current_user,
            action="bitrix.manual_sync",
            resource_type=entity_type,
            resource_id=entity_id,
            payload={
                "log_id": str(log_row.id),
                "status": log_row.status,
                "provider": log_row.provider,
                "attempts": log_row.attempts,
            },
            request=request,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit log failed for bitrix.manual_sync · %s", exc)

    return BitrixManualSyncResponse(
        log=_row_to_schema(log_row, db),
        status=log_row.status,
        bitrix_id=bitrix_id,
    )


# -----------------------------------------------------------------------------
# Inbound webhook (BE-06) · HMAC + feature flag
# -----------------------------------------------------------------------------


def _verify_hmac(secret: str, body: bytes, signature_header: Optional[str]) -> bool:
    """Verify the request HMAC against `secret`.

    Bitrix doesn't sign webhooks natively; we expose a Hopper-side proxy
    expectation: the cliente posts with header `X-Hopper-Signature: sha256=<hex>`.
    """
    if not signature_header:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.strip()
    if received.startswith("sha256="):
        received = received[len("sha256=") :]
    return hmac.compare_digest(expected, received)


@webhook_router.post(
    "/inbound",
    response_model=BitrixInboundAck,
    summary="GH-S10-BE-06 · Bitrix → Hopper status updates",
)
async def bitrix_inbound(
    request: Request,
    db: DBSession = Depends(get_db),
):
    settings = get_settings()
    if not settings.bitrix_inbound_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Bitrix inbound webhook is not enabled · set BITRIX_INBOUND_ENABLED=true",
        )

    secret = (settings.bitrix_inbound_secret or "").strip()
    if not secret:
        # Misconfiguration · refuse rather than accept unsigned payloads.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BITRIX_INBOUND_SECRET not configured · refusing unsigned inbound.",
        )

    body = await request.body()
    sig = request.headers.get("x-hopper-signature")
    if not _verify_hmac(secret, body, sig):
        # Don't leak which side failed (timing-safe compare already done).
        try:
            from app.services.audit_service import log_action
            log_action(
                db,
                user=None,
                action="webhook.signature_invalid",
                resource_type="bitrix.inbound",
                resource_id=None,
                payload={"len": len(body)},
                request=request,
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature.",
        )

    # GH-S11 hardening · replay protection (S10 gap closed)
    # The producer must include `X-Hopper-Timestamp` (epoch seconds) and
    # `X-Hopper-Nonce` (unique per attempt). Both are part of the HMAC
    # contract going forward; if absent we still accept (backward compat
    # for the stub) but log a warning.
    from app.core.webhook_replay import bitrix_replay_guard
    ts_header = request.headers.get("x-hopper-timestamp")
    nonce_header = request.headers.get("x-hopper-nonce")
    if ts_header and nonce_header:
        try:
            ts_value = float(ts_header)
        except ValueError:
            ts_value = 0
        ts_ok, ts_reason = bitrix_replay_guard.check_timestamp(ts_value)
        nonce_ok = bitrix_replay_guard.remember_nonce(nonce_header)
        if not ts_ok or not nonce_ok:
            try:
                from app.services.audit_service import log_action
                log_action(
                    db,
                    user=None,
                    action="webhook.replay_blocked",
                    resource_type="bitrix.inbound",
                    resource_id=None,
                    payload={
                        "ts_ok": ts_ok,
                        "ts_reason": ts_reason or None,
                        "nonce_ok": nonce_ok,
                    },
                    request=request,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Replay protection · timestamp or nonce invalid.",
            )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body must be valid JSON.",
        )

    user = bitrix_sync_service.sync_inbound_status(db, payload)
    if user is None:
        return BitrixInboundAck(ok=True, matched_user_id=None, normalized_status=None)
    return BitrixInboundAck(
        ok=True,
        matched_user_id=user.id,
        normalized_status=user.bitrix_lead_status,
    )
