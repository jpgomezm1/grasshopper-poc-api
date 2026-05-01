"""Structured logging with PII masking.

GH-S11-INFRA-05 · structlog JSON output · masks sensitive fields before
they hit any log sink (stdout, Sentry, Heroku log drain).

Masking rules (centralized so prompts/services don't reinvent):
- emails  → first char + ``***@domain``
- phones  → fully redacted (``[redacted-phone]``)
- tokens  → fully redacted (``[redacted-token]``)
- bearer  → ``Bearer [redacted]`` in any string
- query strings with ``token=`` / ``access_token=`` are stripped

Use ``get_logger(__name__)`` to obtain a structlog logger anywhere in
the app. Stdlib ``logging.getLogger`` keeps working; we attach the same
processors via root handler so legacy ``logger.info(...)`` calls still
route through the masker.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any, Iterable, Mapping

import structlog

from app.config import get_settings

# ---------------------------------------------------------------------------
# Masking helpers (also exported for unit tests · pure functions)
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]*)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
# Phone heuristic · Colombian + intl mobile formats. Tightened to require
# either a leading + or a (\d{2,3}) prefix so ISO timestamps don't match.
PHONE_RE = re.compile(r"(?:\+\d[\d\s\-]{7,}\d|\b3\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b)")
BEARER_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]{6,})", re.IGNORECASE)
QS_TOKEN_RE = re.compile(r"((?:access_token|token|api_key|signature|sig)=)([A-Za-z0-9._\-%]{6,})", re.IGNORECASE)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
# ISO 8601 timestamps that EMAIL_RE could mangle? No — regex requires '@'.
# Timestamps embedded in keys ("timestamp") are emitted by structlog and
# already pass through mask_value(key=...) which won't trigger on them.

# Keys whose values are always considered secrets (full redaction)
SECRET_KEYS = {
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "jwt",
    "api_key",
    "anthropic_api_key",
    "openai_api_key",
    "supabase_service_key",
    "resend_api_key",
    "bitrix_user_token",
    "bitrix_inbound_secret",
    "jwt_secret_key",
    "secret",
    "authorization",
    "x-bitrix-signature",
}

# Keys whose values are PII (partial mask: email-style)
EMAIL_KEYS = {"email", "user_email", "to", "from", "recipient"}
PHONE_KEYS = {"phone", "phone_number", "telephone", "mobile"}


def mask_email(value: str) -> str:
    """``user@domain.com`` → ``u***@domain.com`` · empty string returned untouched."""
    if not value or "@" not in value:
        return value
    return EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(3)}", value)


def mask_phone(_value: str) -> str:
    """Phones are fully redacted (Habeas Data · highest sensitivity)."""
    return "[redacted-phone]"


def mask_string(value: str) -> str:
    """Apply all string-level masks (bearer, JWT, query token, phone, email).

    Order matters: tokens first so we don't mistakenly leave fragments visible.
    """
    if not isinstance(value, str) or not value:
        return value
    out = BEARER_RE.sub(r"\1[redacted]", value)
    out = JWT_RE.sub("[redacted-jwt]", out)
    out = QS_TOKEN_RE.sub(r"\1[redacted]", out)
    out = PHONE_RE.sub("[redacted-phone]", out)
    out = mask_email(out)
    return out


def mask_value(key: str, value: Any) -> Any:
    """Mask a single key/value pair according to ``SECRET_KEYS`` / ``EMAIL_KEYS``."""
    lowered = key.lower() if isinstance(key, str) else key
    if isinstance(lowered, str) and lowered in SECRET_KEYS:
        return "[redacted]"
    if isinstance(lowered, str) and lowered in EMAIL_KEYS and isinstance(value, str):
        return mask_email(value)
    if isinstance(lowered, str) and lowered in PHONE_KEYS:
        return mask_phone(str(value)) if value else value
    if isinstance(value, str):
        return mask_string(value)
    if isinstance(value, dict):
        return {k: mask_value(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        masked = [mask_value(key, v) for v in value]
        return type(value)(masked) if isinstance(value, tuple) else masked
    return value


# ---------------------------------------------------------------------------
# structlog processors
# ---------------------------------------------------------------------------


def _pii_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor · masks every value in the event dict."""
    return {k: mask_value(k, v) for k, v in event_dict.items()}


def configure_logging() -> None:
    """Configure stdlib logging + structlog processors.

    Idempotent: safe to call multiple times (FastAPI startup, tests).
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        _pii_processor,
    ]

    if settings.log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Reset root handlers so re-configuration replaces the previous formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy libraries in JSON mode
    for name in ("uvicorn.access", "httpx", "httpcore", "anthropic", "openai"):
        logging.getLogger(name).setLevel(max(level, logging.WARNING))


def get_logger(name: str | None = None) -> Any:
    """Return a structlog bound logger (preferred entry point)."""
    return structlog.get_logger(name) if name else structlog.get_logger()


# Convenience for unit tests
def _all_masking_helpers() -> Iterable[Mapping[str, Any]]:  # pragma: no cover
    return [
        {"name": "email", "fn": mask_email},
        {"name": "phone", "fn": mask_phone},
        {"name": "string", "fn": mask_string},
    ]
