"""Bitrix integration endpoints · GH-S10-BE-06/07.

Surfaces:

    GET  /admin/integrations/bitrix/status                 (super_admin)
    GET  /admin/integrations/bitrix/sync-log               (super_admin · paginated)
    POST /admin/integrations/bitrix/sync/{entity}/{id}     (super_admin · manual trigger)
    POST /webhooks/bitrix/inbound                          (HMAC validated · feature-flagged)

Hardening (F3 · GH-S11.5):
    BE-08 · ack inmediato: webhook arriva → valida → encola BackgroundTask → 200 OK <500ms
    BE-09 · PII sanitization: logs usan sanitize_for_log antes de emitir el body
    BE-10 · content-length cap: payloads > BITRIX_MAX_PAYLOAD_KB → 413

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
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.core.log_sanitization import sanitize_for_log
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
# Hardening (F3): BE-08 ack inmediato · BE-09 PII logs · BE-10 content-length cap
# -----------------------------------------------------------------------------


def _check_content_length(request: Request, max_bytes: int) -> None:
    """BE-10 · Reject oversized payloads early via Content-Length header check.

    Checks the ``Content-Length`` header before reading the body so we can
    return 413/411 without consuming memory.

    Raises:
        HTTPException 411 when Content-Length header is absent.
        HTTPException 413 when declared size exceeds *max_bytes*.
    """
    if max_bytes <= 0:
        # Cap disabled via BITRIX_MAX_PAYLOAD_KB=0
        return

    cl_header = request.headers.get("content-length")
    if cl_header is None:
        # Content-Length is required so we can enforce the cap safely.
        raise HTTPException(
            status_code=status.HTTP_411_LENGTH_REQUIRED,
            detail="Content-Length header is required for this endpoint.",
        )

    try:
        declared = int(cl_header)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Length header must be an integer.",
        )

    if declared > max_bytes:
        logger.warning(
            "bitrix inbound rejected · payload too large · declared=%d max=%d",
            declared,
            max_bytes,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Payload too large · declared {declared} bytes exceeds "
                f"limit of {max_bytes} bytes."
            ),
        )


def _run_sync_inbound(payload: Dict[str, Any], db_factory: Any) -> None:
    """BE-08 · Background worker that executes sync_inbound_status.

    Runs in a FastAPI BackgroundTask after the HTTP ack is sent.
    Opens and closes its own DB session to avoid using the request-scoped one.
    """
    from app.db.database import SessionLocal as _SessionLocal

    db_factory = db_factory or _SessionLocal
    db = db_factory()
    try:
        bitrix_sync_service.sync_inbound_status(db, payload)
    except Exception as exc:  # pragma: no cover · defensive
        logger.error("bitrix inbound background sync failed · %s", exc)
    finally:
        db.close()


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


def _parse_bitrix_form_payload(form: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct the nested dict Bitrix sends as flat form keys.

    Bitrix posts events as `application/x-www-form-urlencoded` with bracket
    keys like `data[FIELDS][ID]=42`. We collapse those back to a nested dict
    so `sync_inbound_status` can consume them with the same shape it does
    for JSON. We strip the `auth` envelope before returning (auth is checked
    separately in the route handler).
    """
    nested: Dict[str, Any] = {}
    for key, value in form.items():
        # Convert "data[FIELDS][ID]" → ["data", "FIELDS", "ID"]
        parts: list = []
        head, *rest = key.replace("]", "").split("[")
        parts.append(head)
        parts.extend(rest)
        cursor = nested
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
            if not isinstance(cursor, dict):
                # Conflicting shape · skip silently
                cursor = {}
        cursor[parts[-1]] = value
    return nested


@webhook_router.post(
    "/inbound",
    response_model=BitrixInboundAck,
    summary="GH-S10-BE-06 · Bitrix → Hopper status updates",
)
async def bitrix_inbound(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
):
    """Inbound webhook from Bitrix.

    GH-S11.5 hardening:
    - BE-08: validates synchronously, enqueues processing as a BackgroundTask,
      returns 200 OK immediately so Bitrix does not retry on slow DB writes.
    - BE-09: any log statement that touches the inbound body goes through
      ``sanitize_for_log`` to strip PII before reaching the log sink.
    - BE-10: enforces Content-Length cap (BITRIX_MAX_PAYLOAD_KB) before
      reading the body; returns 411/413 on violation.
    """
    settings = get_settings()
    if not settings.bitrix_inbound_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Bitrix inbound webhook is not enabled · set BITRIX_INBOUND_ENABLED=true",
        )

    # BE-10 · content-length cap (before reading body)
    max_bytes = (settings.bitrix_max_payload_kb or 0) * 1024
    _check_content_length(request, max_bytes)

    # Two supported auth modes:
    #
    # 1. Bitrix24 official events (event.bind handler) → posts as
    #    application/x-www-form-urlencoded with `auth[application_token]`
    #    matching `BITRIX_APPLICATION_TOKEN` env var.
    # 2. Legacy/proxy flow → posts JSON signed with HMAC sha256 in
    #    `X-Hopper-Signature` header against `BITRIX_INBOUND_SECRET`.
    #
    # If BITRIX_APPLICATION_TOKEN is set we ALWAYS try mode 1 first; HMAC
    # is the fallback. At least one of the two must be configured.
    application_token_cfg = (settings.bitrix_application_token or "").strip()
    secret = (settings.bitrix_inbound_secret or "").strip()
    if not application_token_cfg and not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Inbound auth not configured · set BITRIX_APPLICATION_TOKEN "
                "(official Bitrix events) and/or BITRIX_INBOUND_SECRET (legacy HMAC)."
            ),
        )

    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    body = await request.body()

    # Secondary size guard: body was already read — confirm it's within limit.
    # This catches cases where Content-Length was absent or mis-declared.
    if max_bytes > 0 and len(body) > max_bytes:
        logger.warning(
            "bitrix inbound rejected post-read · body=%d max=%d",
            len(body),
            max_bytes,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Payload too large · {len(body)} bytes exceeds limit of {max_bytes} bytes.",
        )

    # Mode 1 · Bitrix24 official webhook (form-urlencoded + application_token)
    if content_type == "application/x-www-form-urlencoded" and application_token_cfg:
        form = await request.form()
        form_dict: Dict[str, Any] = {k: v for k, v in form.items()}
        received_token = form_dict.get("auth[application_token]") or form_dict.get(
            "application_token"
        )
        if not received_token or not hmac.compare_digest(
            str(received_token), application_token_cfg
        ):
            try:
                from app.services.audit_service import log_action
                log_action(
                    db,
                    user=None,
                    action="webhook.application_token_invalid",
                    resource_type="bitrix.inbound",
                    resource_id=None,
                    payload={"len": len(body)},
                    request=request,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid application_token.",
            )
        payload = _parse_bitrix_form_payload(form_dict)
        # BE-09: sanitize before logging
        logger.debug(
            "bitrix inbound form-urlencoded received · keys=%s",
            sanitize_for_log(list(payload.keys())),
        )
        # BE-08: enqueue and ack immediately
        background_tasks.add_task(_run_sync_inbound, payload, None)
        return BitrixInboundAck(ok=True, matched_user_id=None, normalized_status=None)

    # Mode 2 · Legacy HMAC (proxy/test flow)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Got JSON payload but BITRIX_INBOUND_SECRET not set · "
                "use form-urlencoded with application_token for official events."
            ),
        )
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

    # GH-S11.5-BE-11: replay protection cross-dyno (Postgres)
    # El productor debe incluir X-Hopper-Timestamp (epoch seconds) y
    # X-Hopper-Nonce (unico por intento). Ambos forman parte del contrato
    # HMAC desde S11. Si estan ausentes se acepta con warning (compat stub).
    #
    # check_and_mark es atomico: INSERT ON CONFLICT DO NOTHING RETURNING
    # garantiza que solo un dyno "gana" cuando 2 procesan el mismo nonce
    # simultaneamente. El segundo ve RETURNING vacio = replay detectado.
    from app.core.webhook_replay import bitrix_replay_guard
    ts_header = request.headers.get("x-hopper-timestamp")
    nonce_header = request.headers.get("x-hopper-nonce")
    if ts_header and nonce_header:
        try:
            ts_value = float(ts_header)
        except ValueError:
            ts_value = 0
        ts_ok, ts_reason = bitrix_replay_guard.check_timestamp(ts_value)
        # check_and_mark atomico cross-dyno: True = nonce nuevo, False = replay
        nonce_ok = bitrix_replay_guard.check_and_mark(
            nonce=nonce_header, source="bitrix", db=db
        )
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

    # BE-09: safe log before enqueuing
    logger.debug(
        "bitrix inbound HMAC validated · payload_safe=%s",
        sanitize_for_log(payload),
    )

    # BE-08: enqueue processing and ack immediately so Bitrix receives 200 OK
    # before the DB write completes. The background task opens its own session.
    background_tasks.add_task(_run_sync_inbound, payload, None)
    return BitrixInboundAck(ok=True, matched_user_id=None, normalized_status=None)
