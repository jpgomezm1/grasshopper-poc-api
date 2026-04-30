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
