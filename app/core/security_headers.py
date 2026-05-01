"""HTTP security headers middleware.

GH-S11-INFRA-05 · sets HSTS, X-Content-Type-Options, X-Frame-Options,
Referrer-Policy, Permissions-Policy and a baseline CSP on every response.

CSP is intentionally minimal because the API is JSON-first; the only HTML
surface is FastAPI's ``/docs`` (Swagger UI) which loads its assets from
``cdn.jsdelivr.net`` and ``fastapi.tiangolo.com``. The frontend serves
its own CSP via Netlify headers; we don't try to govern it from here.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.config import get_settings


def _build_csp(extra_connect_src: str = "") -> str:
    """Compose the Content-Security-Policy header string."""
    extras = [s.strip() for s in extra_connect_src.split(",") if s.strip()]
    connect_src = " ".join(
        [
            "'self'",
            "https://api.anthropic.com",
            "https://api.openai.com",
            "https://*.supabase.co",
            "https://*.sentry.io",
            *extras,
        ]
    )
    parts = [
        "default-src 'self'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        # Swagger UI assets
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",
        "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net",
        "font-src 'self' data: https://cdn.jsdelivr.net",
        f"connect-src {connect_src}",
        "object-src 'none'",
        "upgrade-insecure-requests",
    ]
    return "; ".join(parts)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardened security headers to every response.

    Idempotent: never overrides headers already set by an inner handler.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        settings = get_settings()
        self._enabled = settings.security_headers_enabled
        self._csp = _build_csp(settings.csp_extra_connect_src)
        # HSTS: 1 year, include subdomains; preload omitted until prod cutover (S12)
        self._hsts = "max-age=31536000; includeSubDomains"

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        if not self._enabled:
            return response

        h = response.headers
        h.setdefault("Strict-Transport-Security", self._hsts)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        h.setdefault("Content-Security-Policy", self._csp)
        # Hide server signature
        if "server" in h:
            del h["server"]
        return response
