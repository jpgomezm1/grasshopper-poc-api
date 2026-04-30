"""Transactional email service · Sprint 7 · D-016.

Public API:
    send_report_email(to, student_name, report_pdf_bytes, school_name=None) -> EmailSendResult

Backend resolution at runtime (mirrors storage_service.py · D-010):
    if RESEND_API_KEY is set       → Resend backend
    else                           → Stub backend (logs · marks NOT delivered)

PII guard:
    - NEVER log the body or attachment bytes.
    - Email addresses are masked in logs (`a***@domain.tld`).
    - Stub does NOT persist the PDF anywhere new (it's already in storage).
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Public types
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class EmailSendResult:
    """Result of an email send attempt."""

    provider: str          # "resend" · "stub" · ...
    delivered: bool        # True only if provider accepted the message
    message_id: Optional[str] = None
    reason: Optional[str] = None  # error or "no_provider_configured"


# -----------------------------------------------------------------------------
# Backend protocol
# -----------------------------------------------------------------------------


class EmailBackend(Protocol):
    name: str

    def send_with_attachment(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachment_bytes: bytes,
        attachment_filename: str,
        attachment_mime: str = "application/pdf",
    ) -> EmailSendResult: ...


# -----------------------------------------------------------------------------
# PII helpers
# -----------------------------------------------------------------------------


def _mask_email(email: str) -> str:
    """Mask local part for logs · 'ana.lopez@x.com' → 'a***@x.com'."""
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


# -----------------------------------------------------------------------------
# Stub backend (default when RESEND_API_KEY is missing)
# -----------------------------------------------------------------------------


class _StubBackend:
    name = "stub"

    def send_with_attachment(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachment_bytes: bytes,
        attachment_filename: str,
        attachment_mime: str = "application/pdf",
    ) -> EmailSendResult:
        logger.info(
            "email_stub to=%s subject=%r bytes=%d filename=%s reason=no_provider_configured",
            _mask_email(to),
            subject,
            len(attachment_bytes or b""),
            attachment_filename,
        )
        return EmailSendResult(
            provider="stub",
            delivered=False,
            message_id=None,
            reason="no_provider_configured",
        )


# -----------------------------------------------------------------------------
# Resend backend (lazy-imported)
# -----------------------------------------------------------------------------


class _ResendBackend:
    name = "resend"

    def __init__(self, api_key: str, from_email: str) -> None:
        try:
            import resend  # type: ignore
        except ImportError as exc:  # pragma: no cover · S12
            raise RuntimeError(
                "resend SDK not installed · `pip install resend`"
            ) from exc

        resend.api_key = api_key
        self._resend = resend
        self._from = from_email

    def send_with_attachment(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachment_bytes: bytes,
        attachment_filename: str,
        attachment_mime: str = "application/pdf",
    ) -> EmailSendResult:
        try:
            params = {
                "from": self._from,
                "to": [to],
                "subject": subject,
                "html": html,
                "attachments": [
                    {
                        "filename": attachment_filename,
                        "content": base64.b64encode(attachment_bytes).decode("ascii"),
                        "content_type": attachment_mime,
                    }
                ],
            }
            res = self._resend.Emails.send(params)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover · S12 live
            logger.warning(
                "resend send failed to=%s err=%s",
                _mask_email(to),
                exc,
            )
            return EmailSendResult(
                provider="resend",
                delivered=False,
                message_id=None,
                reason=str(exc)[:120],
            )

        message_id = None
        if isinstance(res, dict):
            message_id = res.get("id")
        logger.info(
            "resend send ok to=%s message_id=%s",
            _mask_email(to),
            message_id,
        )
        return EmailSendResult(
            provider="resend",
            delivered=True,
            message_id=message_id,
            reason=None,
        )


# -----------------------------------------------------------------------------
# Backend resolution
# -----------------------------------------------------------------------------


_backend: EmailBackend | None = None


def _build_backend() -> EmailBackend:
    """Resolve which backend to use based on env."""
    from app.config import get_settings

    settings = get_settings()
    api_key = (settings.resend_api_key or "").strip()
    from_email = (settings.email_from or "Grasshopper <hola@grasshopper.co>").strip()

    if not api_key:
        return _StubBackend()
    try:
        return _ResendBackend(api_key=api_key, from_email=from_email)
    except RuntimeError as exc:  # SDK missing
        logger.warning("resend SDK missing · falling back to stub: %s", exc)
        return _StubBackend()


def get_backend() -> EmailBackend:
    global _backend
    if _backend is None:
        _backend = _build_backend()
    return _backend


def reset_backend_for_tests() -> None:
    global _backend
    _backend = None


# -----------------------------------------------------------------------------
# Email body template (inline · co-branded)
# -----------------------------------------------------------------------------


def _build_html_body(student_name: str, school_name: Optional[str]) -> str:
    co_brand = ""
    if school_name:
        co_brand = (
            f'<p style="color:#6b6276;font-size:12px;margin:0 0 8px 0;">'
            f"Reporte preparado para {school_name}</p>"
        )
    return f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/></head>
<body style="font-family:-apple-system,Segoe UI,Inter,sans-serif;background:#faf8ff;padding:32px;color:#2b2433;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e1ed;border-radius:12px;padding:32px;">
    {co_brand}
    <h1 style="font-family:Quicksand,Inter,sans-serif;font-size:22px;margin:0 0 12px 0;color:#2b2433;">
      Tu reporte de orientación vocacional
    </h1>
    <p style="font-size:15px;line-height:1.6;margin:0 0 16px 0;">
      Hola {student_name},
    </p>
    <p style="font-size:15px;line-height:1.6;margin:0 0 16px 0;">
      Te enviamos adjunto tu reporte personalizado de Grasshopper. Es un punto
      de partida para conversar con tu familia
      {"y con tu equipo de orientación en " + school_name if school_name else ""}
      sobre los siguientes pasos en tu camino académico.
    </p>
    <p style="font-size:15px;line-height:1.6;margin:0 0 16px 0;">
      Cuando tengas dudas o nueva información, vuelve a la plataforma y
      regenera tu análisis · siempre tendremos una versión actualizada para ti.
    </p>
    <p style="font-size:13px;color:#6b6276;margin:24px 0 0 0;">
      — El equipo de Grasshopper
    </p>
  </div>
  <p style="text-align:center;font-size:11px;color:#6b6276;margin:16px 0 0 0;font-style:italic;">
    Documento confidencial · uso personal y familiar
  </p>
</body>
</html>
""".strip()


# -----------------------------------------------------------------------------
# Public surface
# -----------------------------------------------------------------------------


def send_report_email(
    *,
    to: str,
    student_name: str,
    report_pdf_bytes: bytes,
    school_name: Optional[str] = None,
    filename: str = "reporte-grasshopper.pdf",
) -> EmailSendResult:
    """Send the PDF report to the recipient.

    Returns EmailSendResult with the provider used and outcome.
    """
    if not to or "@" not in to:
        return EmailSendResult(
            provider="stub",
            delivered=False,
            reason="invalid_recipient",
        )

    if not report_pdf_bytes:
        return EmailSendResult(
            provider="stub",
            delivered=False,
            reason="empty_pdf",
        )

    subject = "Tu reporte de orientación vocacional · Grasshopper"
    html = _build_html_body(student_name=student_name, school_name=school_name)

    return get_backend().send_with_attachment(
        to=to,
        subject=subject,
        html=html,
        attachment_bytes=report_pdf_bytes,
        attachment_filename=filename,
        attachment_mime="application/pdf",
    )


# Re-export for tests / introspection
mask_email = _mask_email
