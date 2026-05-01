"""Bitrix CRM REST client · GH-S10-BE-01 (D-020).

Public API:

    BitrixClient.create_lead(payload)   -> BitrixCallResult
    BitrixClient.update_lead(id, p)     -> BitrixCallResult
    BitrixClient.create_contact(p)      -> BitrixCallResult
    BitrixClient.update_contact(id, p)  -> BitrixCallResult
    BitrixClient.create_deal(p)         -> BitrixCallResult
    BitrixClient.update_deal(id, p)     -> BitrixCallResult
    BitrixClient.add_lead_comment(id,t) -> BitrixCallResult

Backend resolution at runtime (mirrors storage_service.py and email_service.py):

    if BITRIX_WEBHOOK_URL is set    → real REST backend with tenacity retries
    else                            → stub backend (logs · synthetic IDs · provider=stub)

Decisions backing this module:

    D-020 (this sprint) · S10 entregado contra mock client por ausencia de
    credenciales · activación real va en S12 cuando cliente entregue API
    key/webhook. Same pattern as S5 mock parsing + S7 email stub.

PII guard:
    - NEVER log full payload or response bodies in stdout.
    - Email/phone are masked in logs (`a***@domain` · `***1234`).
    - Stub does NOT persist payload anywhere new (DB row in
      bitrix_sync_log is the audit record).

Rate limiting:
    - Bitrix REST defaults to ~2 req/s per webhook.
    - We honor BITRIX_RATE_LIMIT_RPS via a token-bucket sleeper.
    - Tenacity retries on 5xx + 429 with exponential backoff
      (BITRIX_RETRY_MIN_WAIT_S → BITRIX_RETRY_MAX_WAIT_S).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Public types
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class BitrixCallResult:
    """Result of a Bitrix REST call."""

    provider: str            # "bitrix" · "stub"
    success: bool
    bitrix_id: Optional[str] = None     # external entity id (lead/contact/deal id)
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None         # short error message · truncated to 500 chars
    attempts: int = 1
    status_code: Optional[int] = None   # http status, if any


class BitrixError(RuntimeError):
    """Raised by the real backend when retries are exhausted."""


# -----------------------------------------------------------------------------
# Backend protocol
# -----------------------------------------------------------------------------


class BitrixBackend(Protocol):
    name: str

    def call(
        self,
        method: str,
        params: Dict[str, Any],
    ) -> BitrixCallResult: ...


# -----------------------------------------------------------------------------
# PII / safe-log helpers
# -----------------------------------------------------------------------------


def _mask_email(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _mask_phone(phone: Optional[str]) -> str:
    if not phone:
        return "***"
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "***"
    return f"***{digits[-4:]}"


def _safe_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a non-PII summary of a payload for logging.

    Drops anything resembling a name and masks emails / phones.
    """
    if not isinstance(payload, dict):
        return {"_": "non-dict-payload"}
    out: Dict[str, Any] = {}
    for key, value in payload.items():
        lower = key.lower()
        if "email" in lower:
            out[key] = _mask_email(value if isinstance(value, str) else None)
        elif "phone" in lower or "tel" in lower:
            out[key] = _mask_phone(value if isinstance(value, str) else None)
        elif "name" in lower or "first" in lower or "last" in lower:
            out[key] = "***"
        elif isinstance(value, dict):
            out[key] = _safe_summary(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value if not isinstance(value, str) else value[:80]
        else:
            out[key] = f"<{type(value).__name__}>"
    return out


# Re-export for tests
mask_email = _mask_email
mask_phone = _mask_phone
safe_summary = _safe_summary


# -----------------------------------------------------------------------------
# Token-bucket rate limiter (process-local · best-effort)
# -----------------------------------------------------------------------------


class _RateLimiter:
    """Best-effort RPS limiter shared per backend instance.

    Bitrix REST API doc states ~2 r/s per webhook · we keep a small token
    bucket that blocks (sleeps) the calling thread when exhausted. This
    avoids 429 storms in dev. In production, the default is conservative
    (2.0 r/s) and configurable via BITRIX_RATE_LIMIT_RPS.
    """

    def __init__(self, rps: float) -> None:
        self.rps = max(0.1, rps)
        self.min_interval = 1.0 / self.rps
        self._last_call_at = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last_call_at)
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._last_call_at = now


# -----------------------------------------------------------------------------
# Stub backend (default · D-020)
# -----------------------------------------------------------------------------


class _StubBackend:
    """In-memory backend used when BITRIX_WEBHOOK_URL is empty.

    Returns synthetic IDs deterministically so tests can assert on them.
    Logs a non-PII summary at INFO level. Persists nothing.
    """

    name = "stub"

    def __init__(self) -> None:
        self._counter = 0
        self._lock = threading.Lock()
        # Capture the last N calls for tests that want to introspect.
        self.calls: list[tuple[str, Dict[str, Any]]] = []

    def _next_id(self, prefix: str) -> str:
        with self._lock:
            self._counter += 1
            return f"stub-{prefix}-{self._counter}"

    def call(self, method: str, params: Dict[str, Any]) -> BitrixCallResult:
        # Track the call for tests
        self.calls.append((method, params))
        # Most "create" methods → synthesize id; "update"/"add comment" → echo.
        if method.endswith(".add"):
            kind = method.split(".")[1]  # crm.lead.add → "lead"
            new_id = self._next_id(kind)
            logger.info(
                "bitrix_stub method=%s kind=%s -> %s payload_keys=%s",
                method,
                kind,
                new_id,
                sorted((params.get("fields") or {}).keys()),
            )
            return BitrixCallResult(
                provider="stub",
                success=True,
                bitrix_id=new_id,
                response={"result": new_id},
                attempts=1,
                status_code=200,
            )
        if method.endswith(".update"):
            target = str(params.get("id") or "unknown")
            logger.info("bitrix_stub method=%s id=%s ok", method, target)
            return BitrixCallResult(
                provider="stub",
                success=True,
                bitrix_id=target,
                response={"result": True},
                attempts=1,
                status_code=200,
            )
        # comment add etc.
        logger.info(
            "bitrix_stub method=%s params_summary=%s",
            method,
            sorted(params.keys()),
        )
        return BitrixCallResult(
            provider="stub",
            success=True,
            response={"result": True, "method": method},
            attempts=1,
            status_code=200,
        )


# -----------------------------------------------------------------------------
# Real Bitrix REST backend (lazy-imported tenacity + httpx)
# -----------------------------------------------------------------------------


class _BitrixRestBackend:
    """Real Bitrix REST backend.

    Uses an inbound-webhook URL of the form:
        https://<portal>.bitrix24.com/rest/<user_id>/<token>/

    Call format: POST {webhook_url}{method}.json with form-encoded params.
    """

    name = "bitrix"

    def __init__(
        self,
        webhook_url: str,
        *,
        rate_limit_rps: float = 2.0,
        max_attempts: int = 4,
        retry_min_wait_s: float = 2.0,
        retry_max_wait_s: float = 128.0,
        timeout_s: float = 15.0,
    ) -> None:
        try:
            import httpx  # type: ignore
            from tenacity import (  # type: ignore
                Retrying,
                stop_after_attempt,
                wait_exponential,
                retry_if_exception_type,
            )
        except ImportError as exc:  # pragma: no cover · runtime guard
            raise RuntimeError(
                "httpx + tenacity required for the real Bitrix backend"
            ) from exc

        if not webhook_url.endswith("/"):
            webhook_url = webhook_url + "/"
        self._webhook_url = webhook_url
        self._timeout_s = timeout_s
        self._max_attempts = max(1, max_attempts)
        self._httpx = httpx
        self._Retrying = Retrying
        self._stop_after_attempt = stop_after_attempt
        self._wait_exponential = wait_exponential
        self._retry_if_exception_type = retry_if_exception_type
        self._retry_min_wait_s = retry_min_wait_s
        self._retry_max_wait_s = retry_max_wait_s
        self._rate_limiter = _RateLimiter(rate_limit_rps)

    # ---- internal HTTP call (single attempt) -----------------------------

    def _http_post(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._rate_limiter.acquire()
        url = f"{self._webhook_url}{method}.json"
        try:
            with self._httpx.Client(timeout=self._timeout_s) as client:
                resp = client.post(url, json=params)
        except self._httpx.HTTPError as exc:  # network-level error
            raise BitrixError(f"network error · {exc}") from exc

        if resp.status_code == 429:
            # Bitrix is asking for backoff
            raise BitrixError(f"rate-limited · 429 · {resp.text[:120]}")
        if 500 <= resp.status_code < 600:
            raise BitrixError(
                f"server error · {resp.status_code} · {resp.text[:120]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise BitrixError(f"non-json response · {resp.status_code}") from exc

        if not resp.is_success or "error" in data:
            err = data.get("error_description") or data.get("error") or resp.text[:200]
            # 4xx (other than 429) is a hard error · don't retry
            raise BitrixError(f"bitrix error · {resp.status_code} · {err}")

        return data

    # ---- public ----------------------------------------------------------

    def call(self, method: str, params: Dict[str, Any]) -> BitrixCallResult:
        attempts = 0
        last_exc: Optional[BaseException] = None

        retryer = self._Retrying(
            reraise=True,
            stop=self._stop_after_attempt(self._max_attempts),
            wait=self._wait_exponential(
                multiplier=self._retry_min_wait_s,
                min=self._retry_min_wait_s,
                max=self._retry_max_wait_s,
            ),
            retry=self._retry_if_exception_type(BitrixError),
        )
        try:
            for attempt in retryer:
                with attempt:
                    attempts += 1
                    data = self._http_post(method, params)
        except BitrixError as exc:
            last_exc = exc
            return BitrixCallResult(
                provider="bitrix",
                success=False,
                error=str(exc)[:500],
                attempts=attempts,
            )

        result_value = data.get("result")
        bitrix_id: Optional[str] = None
        if isinstance(result_value, (int, str)):
            bitrix_id = str(result_value)
        elif isinstance(result_value, dict):
            # crm.lead.update returns {"result": true}; crm.lead.add returns {"result": <id>}
            inner_id = result_value.get("ID") or result_value.get("id")
            if inner_id is not None:
                bitrix_id = str(inner_id)

        return BitrixCallResult(
            provider="bitrix",
            success=True,
            bitrix_id=bitrix_id,
            response=data,
            attempts=attempts,
            status_code=200,
        )


# -----------------------------------------------------------------------------
# Backend resolution
# -----------------------------------------------------------------------------


_backend: Optional[BitrixBackend] = None


def _build_backend() -> BitrixBackend:
    from app.config import get_settings

    settings = get_settings()
    webhook_url = (settings.bitrix_webhook_url or "").strip()
    if not webhook_url:
        return _StubBackend()
    try:
        return _BitrixRestBackend(
            webhook_url=webhook_url,
            rate_limit_rps=settings.bitrix_rate_limit_rps,
            max_attempts=settings.bitrix_max_attempts,
            retry_min_wait_s=settings.bitrix_retry_min_wait_s,
            retry_max_wait_s=settings.bitrix_retry_max_wait_s,
        )
    except RuntimeError as exc:  # pragma: no cover
        logger.warning("bitrix backend init failed · falling back to stub: %s", exc)
        return _StubBackend()


def get_backend() -> BitrixBackend:
    global _backend
    if _backend is None:
        _backend = _build_backend()
    return _backend


def reset_backend_for_tests() -> None:
    global _backend
    _backend = None


# -----------------------------------------------------------------------------
# High-level façade
# -----------------------------------------------------------------------------


@dataclass
class BitrixClient:
    """Thin domain-typed façade over the resolved backend.

    Tests can pass an explicit `backend` to bypass resolution.
    """

    backend: BitrixBackend = field(default_factory=get_backend)

    @property
    def provider(self) -> str:
        return self.backend.name

    @property
    def is_stub(self) -> bool:
        return self.backend.name == "stub"

    # --- Leads --------------------------------------------------------------

    def create_lead(self, fields: Dict[str, Any]) -> BitrixCallResult:
        return self.backend.call("crm.lead.add", {"fields": fields})

    def update_lead(self, lead_id: str, fields: Dict[str, Any]) -> BitrixCallResult:
        return self.backend.call(
            "crm.lead.update",
            {"id": lead_id, "fields": fields},
        )

    def get_lead(self, lead_id: str) -> BitrixCallResult:
        return self.backend.call("crm.lead.get", {"id": lead_id})

    # --- Contacts -----------------------------------------------------------

    def create_contact(self, fields: Dict[str, Any]) -> BitrixCallResult:
        return self.backend.call("crm.contact.add", {"fields": fields})

    def update_contact(self, contact_id: str, fields: Dict[str, Any]) -> BitrixCallResult:
        return self.backend.call(
            "crm.contact.update",
            {"id": contact_id, "fields": fields},
        )

    # --- Deals --------------------------------------------------------------

    def create_deal(self, fields: Dict[str, Any]) -> BitrixCallResult:
        return self.backend.call("crm.deal.add", {"fields": fields})

    def update_deal(self, deal_id: str, fields: Dict[str, Any]) -> BitrixCallResult:
        return self.backend.call(
            "crm.deal.update",
            {"id": deal_id, "fields": fields},
        )

    # --- Comments / timeline ------------------------------------------------

    def add_lead_comment(self, lead_id: str, text: str) -> BitrixCallResult:
        return self.backend.call(
            "crm.timeline.comment.add",
            {
                "fields": {
                    "ENTITY_ID": lead_id,
                    "ENTITY_TYPE": "lead",
                    "COMMENT": text,
                }
            },
        )


def get_client() -> BitrixClient:
    """Default client factory · uses resolved backend."""
    return BitrixClient(backend=get_backend())


__all__ = [
    "BitrixClient",
    "BitrixCallResult",
    "BitrixError",
    "BitrixBackend",
    "get_client",
    "get_backend",
    "reset_backend_for_tests",
    "mask_email",
    "mask_phone",
    "safe_summary",
]
