"""Unit tests · email_service (GH-S7 · D-016).

Stub backend is the default · we exercise it directly without mocks.
The Resend backend path is mocked because we do not hit the network.
"""
from __future__ import annotations

import pytest

from app.services import email_service as svc


@pytest.fixture(autouse=True)
def _reset_backend():
    svc.reset_backend_for_tests()
    yield
    svc.reset_backend_for_tests()


def test_mask_email_basic():
    assert svc.mask_email("ana.lopez@colegioandino.edu.co") == "a***@colegioandino.edu.co"


def test_mask_email_short_local():
    assert svc.mask_email("a@x.com") == "a***@x.com"


def test_mask_email_invalid():
    assert svc.mask_email("not-an-email") == "***"


def test_send_report_with_stub_returns_not_delivered(monkeypatch):
    # Force stub backend by clearing the API key
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "", raising=False)
    svc.reset_backend_for_tests()

    result = svc.send_report_email(
        to="valeria@example.com",
        student_name="Valeria",
        report_pdf_bytes=b"%PDF-1.4\nfakebytes\n",
        school_name="Colegio Andino",
    )
    assert result.provider == "stub"
    assert result.delivered is False
    assert result.reason == "no_provider_configured"


def test_send_report_invalid_recipient():
    result = svc.send_report_email(
        to="",
        student_name="X",
        report_pdf_bytes=b"%PDF",
    )
    assert result.delivered is False
    assert result.reason == "invalid_recipient"


def test_send_report_empty_pdf():
    result = svc.send_report_email(
        to="x@y.com",
        student_name="X",
        report_pdf_bytes=b"",
    )
    assert result.delivered is False
    assert result.reason == "empty_pdf"


def test_html_body_includes_school_when_present():
    html = svc._build_html_body("Valeria", "Colegio Andino")
    assert "Colegio Andino" in html
    assert "Valeria" in html


def test_html_body_skips_school_when_absent():
    html = svc._build_html_body("Valeria", None)
    assert "Colegio" not in html
    assert "Valeria" in html


# -----------------------------------------------------------------------------
# QA-AUD-001 · `send_email` helper (GH-S11.5-BE-01)
#
# The Sprint 9 invitation flow tries `from app.services.email_service import send_email`.
# Before this fix the symbol did not exist · the import raised ImportError,
# which was swallowed by a try/except, so invitations were created but emails
# never went out. These tests pin the helper down to prevent regression.
# -----------------------------------------------------------------------------


def test_send_email_helper_exists():
    """QA-AUD-001 · the symbol must be importable from email_service."""
    from app.services.email_service import send_email  # noqa: F401
    assert callable(send_email)


def test_send_email_with_stub_returns_not_delivered(monkeypatch):
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "", raising=False)
    svc.reset_backend_for_tests()

    result = svc.send_email(
        to="valeria@colegioandino.edu.co",
        subject="Invitación a Colegio Andino · Grasshopper",
        html_body="<p>Hola</p>",
        text_body="Hola",
    )
    assert result.provider == "stub"
    assert result.delivered is False
    assert result.reason == "no_provider_configured"


def test_send_email_invalid_recipient():
    result = svc.send_email(
        to="",
        subject="x",
        html_body="<p>x</p>",
    )
    assert result.delivered is False
    assert result.reason == "invalid_recipient"


def test_send_email_invalid_recipient_no_at():
    result = svc.send_email(
        to="not-an-email",
        subject="x",
        html_body="<p>x</p>",
    )
    assert result.delivered is False
    assert result.reason == "invalid_recipient"


def test_send_email_empty_subject():
    result = svc.send_email(
        to="x@y.com",
        subject="",
        html_body="<p>x</p>",
    )
    assert result.delivered is False
    assert result.reason == "empty_subject_or_body"


def test_send_email_empty_html_body():
    result = svc.send_email(
        to="x@y.com",
        subject="hi",
        html_body="",
    )
    assert result.delivered is False
    assert result.reason == "empty_subject_or_body"


def test_send_email_text_body_optional(monkeypatch):
    """text_body is optional · should not blow up if omitted."""
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "", raising=False)
    svc.reset_backend_for_tests()

    result = svc.send_email(
        to="x@y.com",
        subject="hi",
        html_body="<p>hi</p>",
    )
    assert result.provider == "stub"
    assert result.delivered is False


def test_send_email_invokes_backend_send_html(monkeypatch):
    """Verifies the backend protocol method is wired correctly."""
    calls: list[dict] = []

    class _MockBackend:
        name = "mock"

        def send_with_attachment(self, **kwargs):  # pragma: no cover · not used here
            raise AssertionError("send_with_attachment should not be called")

        def send_html(self, *, to, subject, html, text=None):
            calls.append({"to": to, "subject": subject, "html": html, "text": text})
            return svc.EmailSendResult(provider="mock", delivered=True, message_id="m-1")

    svc.reset_backend_for_tests()
    monkeypatch.setattr(svc, "_backend", _MockBackend())

    result = svc.send_email(
        to="invitee@school.com",
        subject="Invitación a Colegio · Grasshopper",
        html_body="<p>link</p>",
        text_body="link",
    )

    assert result.delivered is True
    assert result.provider == "mock"
    assert result.message_id == "m-1"
    assert len(calls) == 1
    assert calls[0]["to"] == "invitee@school.com"
    assert calls[0]["subject"].startswith("Invitación")
    assert calls[0]["text"] == "link"
