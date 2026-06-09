"""Rate limiting · GH-S11-INFRA-04.

Implementation note: slowapi's decorator-based API doesn't compose well
with FastAPI endpoints that use ``from __future__ import annotations``
+ Pydantic body parameters + ``UploadFile`` (it wraps the handler and
breaks ForwardRef resolution / response_model inference).

To keep ergonomics clean across all endpoint shapes we ship a tiny
in-memory token-bucket limiter exposed as a FastAPI dependency. It
provides:

  - per-key buckets (by IP, or `user:<id>` once authenticated)
  - declarative limits like ``"5/minute"`` / ``"10/hour"`` parsed once
  - structured 429 JSON via raised :class:`RateLimitExceeded`
  - global on/off via ``settings.rate_limit_enabled``

Cross-dyno coordination is out of scope · for the single-dyno Heroku
deployment of S12 this is sufficient. The slowapi package stays in
requirements.txt so a Redis-backed swap remains a one-liner if needed.
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Optional

from fastapi import Depends, HTTPException, Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings


_PERIOD_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 60 * 60,
    "day": 60 * 60 * 24,
}


@dataclass
class _ParsedLimit:
    count: int
    window_s: int

    @classmethod
    def parse(cls, raw: str) -> "_ParsedLimit":
        m = re.match(r"\s*(\d+)\s*/\s*(\w+)\s*$", raw)
        if not m:
            raise ValueError(f"Invalid rate-limit format: {raw!r}")
        count = int(m.group(1))
        unit = m.group(2).lower().rstrip("s")  # accept "minutes" too
        if unit not in _PERIOD_SECONDS:
            raise ValueError(f"Unknown rate-limit unit: {unit!r}")
        return cls(count=count, window_s=_PERIOD_SECONDS[unit])


class RateLimitExceeded(HTTPException):
    """HTTP 429 with a structured JSON body (matches slowapi's behavior)."""

    def __init__(self, retry_after: int, limit_str: str) -> None:
        super().__init__(
            status_code=429,
            detail=f"Rate limit exceeded · {limit_str}",
            headers={"Retry-After": str(max(retry_after, 1))},
        )
        self.retry_after = retry_after
        self.limit_str = limit_str


@dataclass
class _Bucket:
    timestamps: Deque[float] = field(default_factory=deque)


class InMemoryLimiter:
    """Per-key sliding-window counter."""

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self.enabled: bool = True

    @staticmethod
    def _client_key(request: Request) -> str:
        """Prefer authenticated user-id, fall back to remote IP."""
        user = getattr(request.state, "user_id", None)
        if user:
            return f"user:{user}"
        # X-Forwarded-For (Heroku/Cloudflare) → first IP
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return f"ip:{xff.split(',')[0].strip()}"
        if request.client:
            return f"ip:{request.client.host}"
        return "ip:unknown"

    def hit(self, key: str, limit: _ParsedLimit, *, now: Optional[float] = None) -> None:
        """Record a request; raise :class:`RateLimitExceeded` if over the limit."""
        now = now if now is not None else time.time()
        cutoff = now - limit.window_s
        with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket())
            # Drop expired timestamps
            while bucket.timestamps and bucket.timestamps[0] < cutoff:
                bucket.timestamps.popleft()
            if len(bucket.timestamps) >= limit.count:
                retry_after = int((bucket.timestamps[0] + limit.window_s) - now) + 1
                raise RateLimitExceeded(
                    retry_after=retry_after,
                    limit_str=f"{limit.count} per {limit.window_s}s",
                )
            bucket.timestamps.append(now)

    def reset(self) -> None:
        """Test helper · drop all buckets."""
        with self._lock:
            self._buckets.clear()


# Module-level singleton
_global_limiter = InMemoryLimiter()


def get_limiter() -> InMemoryLimiter:
    return _global_limiter


def rate_limit(limit_str: str, *, scope: Optional[str] = None) -> Callable:
    """Build a FastAPI dependency that enforces ``limit_str`` (e.g. ``"5/minute"``).

    Usage:

        @router.post("/login", dependencies=[Depends(rate_limit("5/minute"))])
        def login(...): ...

    ``scope`` (Fase C · B-049): namespacea el bucket. Los buckets se indexan
    solo por client-key, así que SIN scope dos límites distintos sobre el
    mismo endpoint (ej. 20/minute + 200/day) compartirían deque y se
    double-countearían. Con ``scope`` cada límite cuenta aparte.
    """
    parsed = _ParsedLimit.parse(limit_str)

    def _dependency(request: Request) -> None:
        s = get_settings()
        if not s.rate_limit_enabled or not _global_limiter.enabled:
            return
        key = InMemoryLimiter._client_key(request)
        if scope:
            key = f"{scope}:{key}"
        _global_limiter.hit(key, parsed)

    return _dependency


# Backwards-compat shims so older code that imports ``limiter`` keeps working.
class _LimiterShim:
    """Tiny adapter to keep the old ``limiter`` symbol working."""

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.rate_limit_enabled

    def reset(self) -> None:
        _global_limiter.reset()


limiter = _LimiterShim()


def _cors_headers_for(request: Optional[Request]) -> Dict[str, str]:
    """Build CORS response headers manually for the 429 JSON response.

    B-005 (QA round 2): Starlette's ``CORSMiddleware`` does NOT decorate
    responses produced by ``add_exception_handler``-registered handlers
    when the exception is raised *inside* a route dependency (it bypasses
    the middleware chain entirely on the inbound side and the response
    short-circuits out of ``ExceptionMiddleware`` before reaching CORS).

    Without these headers the browser sees a 429 with no
    ``Access-Control-Allow-Origin`` and reports it as a CORS failure,
    masking the real rate-limit error in the FE (parent dashboard ·
    ``/parent/events`` was the canonical symptom).

    The origin is *validated* against ``settings.cors_origins`` so we
    never echo back ``*`` or an attacker-controlled value.
    """
    if request is None:
        return {}
    origin = request.headers.get("origin")
    if not origin:
        return {}
    allowed = set(get_settings().cors_origins or [])
    if origin not in allowed:
        # Silently drop · the browser will still surface the 429 but
        # without CORS unblock. Better than echoing back a forged origin.
        return {"Vary": "Origin"}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 handler · returns a structured JSON error.

    GH-LOCAL-QA-RONDA2 · B-005 · merges CORS headers onto the response so
    the browser doesn't mask the 429 behind a CORS error (the canonical
    repro is the parent dashboard polling ``/parent/events``).
    """
    headers: Dict[str, str] = dict(exc.headers or {})
    headers.update(_cors_headers_for(request))
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": exc.detail,
            "retry_after": exc.retry_after,
        },
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Optional ASGI middleware (kept for parity with slowapi pattern, but a no-op
# when all routes already declare their own ``Depends(rate_limit(...))``).
# ---------------------------------------------------------------------------


class SlowAPIMiddleware:
    """Catches :class:`RateLimitExceeded` raised from any nested code path
    (e.g. background helpers) and converts it into a 429 JSON response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except RateLimitExceeded as exc:
            # Build a lightweight Request so the handler can read the Origin
            # header and emit CORS headers on the 429 (B-005 QA round 2).
            request = Request(scope, receive=receive)
            response = rate_limit_exceeded_handler(request, exc)
            await response(scope, receive, send)


__all__ = [
    "RateLimitExceeded",
    "SlowAPIMiddleware",
    "limiter",
    "rate_limit",
    "rate_limit_exceeded_handler",
    "get_limiter",
]
