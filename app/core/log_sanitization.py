"""Webhook payload sanitizer for safe logging · GH-S11.5-BE-09.

Removes PII from webhook payloads before they are written to any log sink.
Delegates heavy masking to the existing ``logging_config`` primitives so
there is a single source of truth for REDACTED keys.

Usage::

    from app.core.log_sanitization import sanitize_for_log

    safe = sanitize_for_log(raw_payload)
    logger.info("bitrix inbound received · %s", safe)

``sanitize_for_log`` is:
  - Recursive: handles nested dicts and lists to any depth.
  - Non-mutating: always returns a new object; the original payload is
    never modified in-place.
  - Key-based: any key whose lowercase form matches ``PII_KEYS`` has its
    value replaced with ``"***REDACTED***"``.
  - Value-pattern: remaining string values are passed through
    ``logging_config.mask_string`` for bearer / JWT / email / phone
    patterns embedded inside longer strings.
"""
from __future__ import annotations

from typing import Any

# Keys whose values contain PII and must always be fully redacted.
# Extend this set here; no other file needs changing.
PII_KEYS: frozenset[str] = frozenset(
    {
        # Identity
        "email",
        "user_email",
        "phone",
        "phone_number",
        "telephone",
        "mobile",
        "document",
        "document_number",
        "cedula",
        "birthdate",
        "birth_date",
        "date_of_birth",
        # Auth / tokens
        "password",
        "hashed_password",
        "token",
        "access_token",
        "refresh_token",
        "jwt",
        "secret",
        "api_key",
        "application_token",
        # AI scores / analysis (sensitive per Habeas Data scope)
        "score",
        "scores",
        "analysis",
        "analysis_text",
        "profile_summary",
        "profile_strengths",
        "career_paths",
        # Bitrix-specific
        "bitrix_user_token",
        "bitrix_inbound_secret",
        "x-hopper-signature",
        "x_hopper_signature",
    }
)


def sanitize_for_log(payload: Any, *, _depth: int = 0) -> Any:
    """Return a copy of *payload* with PII values replaced by ``***REDACTED***``.

    Args:
        payload: Any JSON-like structure (dict, list, str, int, …).

    Returns:
        A new object of the same type with sensitive values redacted.
        Recursion is capped at depth 20 to prevent pathological inputs.

    Examples::

        >>> sanitize_for_log({"email": "a@b.com", "name": "Juan"})
        {"email": "***REDACTED***", "name": "Juan"}

        >>> sanitize_for_log({"nested": {"phone": "3001234567", "city": "Medellín"}})
        {"nested": {"phone": "***REDACTED***", "city": "Medellín"}}
    """
    if _depth > 20:
        # Hard stop to avoid stack overflow on adversarial payloads.
        return "***REDACTED_DEEP***"

    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for k, v in payload.items():
            k_low = k.lower() if isinstance(k, str) else k
            if k_low in PII_KEYS:
                result[k] = "***REDACTED***"
            else:
                result[k] = sanitize_for_log(v, _depth=_depth + 1)
        return result

    if isinstance(payload, list):
        return [sanitize_for_log(item, _depth=_depth + 1) for item in payload]

    if isinstance(payload, tuple):
        return tuple(sanitize_for_log(item, _depth=_depth + 1) for item in payload)

    if isinstance(payload, str):
        # Apply string-level masks (bearer, JWT, email patterns, phones)
        # for values that survived the key-based filter.
        from app.core.logging_config import mask_string
        return mask_string(payload)

    # int, float, bool, None — return as-is
    return payload


__all__ = ["sanitize_for_log", "PII_KEYS"]
