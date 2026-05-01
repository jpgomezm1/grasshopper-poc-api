"""Habeas Data consent service · GH-S11.5-BE-07 · D-026.

Centralizes the rules around Ley 1581/2012 (Colombia) consent state and the
audit trail. All callers (auth flows · Bitrix sync · /me endpoints) MUST go
through this module instead of poking `User.consent_*` columns directly.

Public API:

    has_crm_consent(user)            -> tuple[bool, str | None]
        Returns (allowed, reason). When `allowed` is False, `reason` is one
        of: 'no_data_processing_consent' | 'no_crm_sync_consent' |
        'no_parental_consent'. Use as a gate before any third-party data
        share.

    is_minor(user)                   -> bool
        True if birthdate < 18 OR birthdate is None (default-deny).

    grant_consent(db, user, kind, *, request, policy_version)
        Sets the corresponding *_at column to now() and writes an audit row.

    revoke_consent(db, user, kind, *, request)
        Clears the corresponding *_at column and writes an audit row.

    log_data_export(db, user, *, request)
    log_data_deletion(db, user, *, request)
        Audit-only helpers for the data-rights endpoints.

    consent_state(user) -> dict
        Snapshot for API responses · serializable.

    CONSENT_EVENTS · whitelist of valid event strings (mirrored on the
    DB column `consent_audit_log.event`).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.db.models import ConsentAuditLog, User

logger = logging.getLogger(__name__)


# Valid consent event names · used both by the audit_log writer and tests.
CONSENT_EVENTS = frozenset(
    {
        "data_processing.granted",
        "data_processing.revoked",
        "crm_sync.granted",
        "crm_sync.revoked",
        "parental.granted",
        "parental.revoked",
        "data_export",
        "data_deletion",
    }
)

# Three independent consent kinds.
CONSENT_KINDS = ("data_processing", "crm_sync", "parental")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _client_ip(request: Optional[Request]) -> Optional[str]:
    """Best-effort first-hop IP extraction · respects X-Forwarded-For."""
    if request is None:
        return None
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:50]
    if request.client and request.client.host:
        return request.client.host[:50]
    return None


def _client_ua(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    if not ua:
        return None
    return ua[:500]


def is_minor(user: User) -> bool:
    """Computes minor (<18). When birthdate is None, default-deny → minor."""
    if user is None or user.birthdate is None:
        return True
    today = date.today()
    bd = user.birthdate
    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    return age < 18


def has_crm_consent(user: User) -> Tuple[bool, Optional[str]]:
    """Gate for any third-party CRM data share.

    Order of checks (fail-fast):
      1. data_processing must be granted (covers all flows).
      2. crm_sync must be granted (explicit opt-in).
      3. If minor → parental must be granted.
    """
    if user is None:
        return False, "no_user"
    if user.consent_data_processing_at is None:
        return False, "no_data_processing_consent"
    if user.consent_crm_sync_at is None:
        return False, "no_crm_sync_consent"
    if is_minor(user) and user.consent_parental_at is None:
        return False, "no_parental_consent"
    return True, None


def consent_state(user: User) -> Dict[str, Any]:
    """Serializable snapshot · used by /me/consents and /me/data."""
    settings = get_settings()
    return {
        "data_processing": {
            "granted": user.consent_data_processing_at is not None,
            "granted_at": (
                user.consent_data_processing_at.isoformat()
                if user.consent_data_processing_at
                else None
            ),
            "version_accepted": user.consent_data_processing_version,
        },
        "crm_sync": {
            "granted": user.consent_crm_sync_at is not None,
            "granted_at": (
                user.consent_crm_sync_at.isoformat()
                if user.consent_crm_sync_at
                else None
            ),
        },
        "parental": {
            "granted": user.consent_parental_at is not None,
            "granted_at": (
                user.consent_parental_at.isoformat()
                if user.consent_parental_at
                else None
            ),
            "required": is_minor(user),
        },
        "policy_version_current": settings.privacy_policy_version,
        "needs_re_acceptance": (
            user.consent_data_processing_version is not None
            and user.consent_data_processing_version
            != settings.privacy_policy_version
        ),
    }


# -----------------------------------------------------------------------------
# Audit log writer
# -----------------------------------------------------------------------------


def _audit(
    db: DBSession,
    user: Optional[User],
    event: str,
    *,
    request: Optional[Request] = None,
    policy_version: Optional[str] = None,
) -> ConsentAuditLog:
    if event not in CONSENT_EVENTS:
        raise ValueError(f"unknown consent event: {event!r}")
    row = ConsentAuditLog(
        user_id=user.id if user is not None else None,
        event=event,
        ip=_client_ip(request),
        user_agent=_client_ua(request),
        policy_version=policy_version,
    )
    db.add(row)
    db.flush()
    return row


# -----------------------------------------------------------------------------
# State mutations
# -----------------------------------------------------------------------------


def grant_consent(
    db: DBSession,
    user: User,
    kind: str,
    *,
    request: Optional[Request] = None,
    policy_version: Optional[str] = None,
) -> ConsentAuditLog:
    """Grant a consent of the given kind. Writes column + audit row.

    For `data_processing`, also stamps the policy version that was
    accepted (caller passes `policy_version` or we read settings).
    """
    if kind not in CONSENT_KINDS:
        raise ValueError(f"unknown consent kind: {kind!r}")
    now = datetime.utcnow()
    settings = get_settings()
    if kind == "data_processing":
        user.consent_data_processing_at = now
        user.consent_data_processing_version = (
            policy_version or settings.privacy_policy_version
        )
    elif kind == "crm_sync":
        user.consent_crm_sync_at = now
    elif kind == "parental":
        user.consent_parental_at = now
    return _audit(
        db,
        user,
        event=f"{kind}.granted",
        request=request,
        policy_version=user.consent_data_processing_version
        or settings.privacy_policy_version,
    )


def revoke_consent(
    db: DBSession,
    user: User,
    kind: str,
    *,
    request: Optional[Request] = None,
) -> ConsentAuditLog:
    """Revoke a consent of the given kind. Clears column + audit row."""
    if kind not in CONSENT_KINDS:
        raise ValueError(f"unknown consent kind: {kind!r}")
    if kind == "data_processing":
        user.consent_data_processing_at = None
        # Keep version for record · so audit shows what was last accepted.
    elif kind == "crm_sync":
        user.consent_crm_sync_at = None
    elif kind == "parental":
        user.consent_parental_at = None
    return _audit(
        db,
        user,
        event=f"{kind}.revoked",
        request=request,
        policy_version=user.consent_data_processing_version,
    )


def log_data_export(
    db: DBSession,
    user: User,
    *,
    request: Optional[Request] = None,
) -> ConsentAuditLog:
    """Audit row when a titular invokes GET /me/data."""
    return _audit(
        db,
        user,
        event="data_export",
        request=request,
        policy_version=user.consent_data_processing_version,
    )


def log_data_deletion(
    db: DBSession,
    user: User,
    *,
    request: Optional[Request] = None,
) -> ConsentAuditLog:
    """Audit row when a titular invokes DELETE /me/data."""
    return _audit(
        db,
        user,
        event="data_deletion",
        request=request,
        policy_version=user.consent_data_processing_version,
    )
