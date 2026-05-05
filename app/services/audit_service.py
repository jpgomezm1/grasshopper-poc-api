"""Audit log service · GH-S8-BE-10.

Centralizes audit logging of sensitive admin actions. Every super_admin and
school_admin mutation should call `log_action` with the relevant context.

Usage:

    from app.services.audit_service import log_action

    log_action(
        db,
        user=current_user,
        action="school.archive",
        resource_type="school",
        resource_id=str(school.id),
        payload={"reason": "..."},
        request=request,
    )

PII guard: payload may contain sensitive identifiers. Caller is responsible
for masking PII before passing it (e.g. don't dump plaintext passwords).
The service never logs to stdout.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from app.db.models import AuditLog, User

logger = logging.getLogger(__name__)


# Whitelist of actions to keep this typed-ish (free-form strings rejected
# would be too rigid for a starter audit log, so we just document them).
KNOWN_ACTIONS = frozenset({
    # schools
    "school.create",
    "school.update",
    "school.archive",
    "school.restore",
    # licenses
    "license.create",
    "license.update",
    "license.cancel",
    # programs / catalog
    "program.create",
    "program.update",
    "program.delete",
    "program.import",
    # users (school staff)
    "user.create_school_user",
    "user.deactivate",
    # auth
    "auth.login_super_admin",
    "auth.login_failed",
    "auth.login_failed_archived_school",
    # webhook security · GH-S11
    "webhook.replay_blocked",
    "webhook.signature_invalid",
    # invitations · GH-S9
    "invitation.create",
    "invitation.revoke",
    "invitation.accept",
    "invitation.resend",
    # school self-service · GH-S9
    "school.upload_logo",
    # bitrix integration · GH-S10
    "bitrix.manual_sync",
    "bitrix.inbound_received",
    # GH internal team contact-request · GH-ROLES-001
    "gh_contact.requested",
    "gh_contact.status_changed",
    # GH-SUPERADMIN-EXPERIENCE · 2026-05-05
    # Bloque A · global user CRUD
    "user.admin_create",
    "user.admin_update",
    "user.admin_delete",
    "user.suspend",
    "user.reactivate",
    "user.password_reset",
    # Bloque E · impersonation (CRITICAL · always logged)
    "impersonation.start",
    "impersonation.stop",
    "impersonation.action",
    # Bloque F · bulk operations on students
    "user.bulk_move_school",
    "user.bulk_reset_journey",
    "user.bulk_merge",
    "user.bulk_delete",
    # Bloque M · feature flags
    "feature_flag.create",
    "feature_flag.update",
    "feature_flag.toggle",
    "feature_flag.delete",
    # Bloque N · AI prompts
    "ai_prompt.create",
    "ai_prompt.activate",
    # Bloque O · integration configs (NO secret values)
    "integration_config.update",
    # Bloque P · backup
    "backup.export_created",
    "backup.export_downloaded",
})


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    # X-Forwarded-For first if behind reverse proxy
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _user_agent(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    if ua and len(ua) > 250:
        ua = ua[:250]
    return ua


def log_action(
    db: DBSession,
    *,
    user: Optional[User],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    commit: bool = True,
) -> AuditLog:
    """Persist an audit log entry.

    Returns the created row. Caller may set commit=False to fold the audit
    write into an outer transaction (we still flush so the row gets an id).
    """
    if action not in KNOWN_ACTIONS:
        logger.warning("audit · unknown action `%s` (still logged)", action)

    row = AuditLog(
        user_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload or {},
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row
