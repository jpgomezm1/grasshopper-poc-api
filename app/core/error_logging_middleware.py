"""Error logging middleware · captures unhandled exceptions into `error_log`.

Bloque K · GH-SUPERADMIN-EXPERIENCE.

PII guard:
  - request body is NEVER captured
  - message is the exception's first 500 chars only
  - trace is truncated to 4kb
  - path is captured raw (it can contain UUIDs but not free-form PII)
"""
from __future__ import annotations

import logging
import traceback
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger(__name__)


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            # Capture 5xx as well (handled gracefully somewhere upstream)
            if response.status_code >= 500:
                self._log(
                    request,
                    status_code=response.status_code,
                    exception_type="HTTP5xx",
                    message=f"Response status {response.status_code}",
                    trace=None,
                )
            return response
        except Exception as e:  # noqa: BLE001 · we want to capture EVERYTHING
            self._log(
                request,
                status_code=500,
                exception_type=type(e).__name__,
                message=str(e)[:500],
                trace=traceback.format_exc()[:4000],
            )
            raise

    @staticmethod
    def _log(
        request: Request,
        *,
        status_code: int,
        exception_type: str,
        message: str,
        trace: Optional[str],
    ) -> None:
        try:
            from app.db.database import SessionLocal
            from app.db.models import ErrorLog

            db = SessionLocal()
            try:
                row = ErrorLog(
                    level="error",
                    path=str(request.url.path)[:255],
                    method=request.method,
                    status_code=status_code,
                    exception_type=exception_type,
                    message=message,
                    trace=trace,
                )
                db.add(row)
                db.commit()
            finally:
                db.close()
        except Exception as e:  # never break the response cycle
            logger.warning("error_log middleware persist failed: %s", e)
