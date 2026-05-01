"""Sentry SDK bootstrap · GH-S11-INFRA-01.

No-op when ``SENTRY_DSN_BACKEND`` is empty (default in dev/test). When a
DSN is provided the SDK is initialized once with a custom
``before_send`` that strips PII via ``logging_config.mask_value``.

Activation in S12 only requires:
    SENTRY_DSN_BACKEND=https://<key>@<org>.ingest.sentry.io/<project>
    SENTRY_ENVIRONMENT=production
    SENTRY_RELEASE=$HEROKU_SLUG_COMMIT (Heroku release phase)
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings


def _scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Sentry ``before_send`` · scrub PII from messages, breadcrumbs, request data."""
    try:
        from app.core.logging_config import mask_value  # local import to avoid cycle
    except Exception:  # pragma: no cover · should never fail
        return event

    def _walk(node: Any, key: str = "") -> Any:
        if isinstance(node, dict):
            return {k: _walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(item, key) for item in node]
        return mask_value(key, node)

    return _walk(event)  # type: ignore[return-value]


def init_sentry() -> bool:
    """Initialize Sentry. Returns True if SDK was activated, False otherwise."""
    settings = get_settings()
    dsn = (settings.sentry_dsn_backend or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:  # pragma: no cover · sentry-sdk pinned in requirements
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment,
        release=settings.sentry_release or settings.app_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,  # we mask manually via before_send
        before_send=_scrub_event,
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            SqlalchemyIntegration(),
        ],
    )
    return True


__all__ = ["init_sentry"]
