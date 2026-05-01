"""Smoke tests · bitrix_client stub backend (GH-S10-BE-01 · D-020).

Validates the contract of the BitrixClient against the in-process stub
backend WITHOUT making any network calls. This is the test that runs in
CI while we wait for the cliente to provide real BITRIX_WEBHOOK_URL.
"""
from __future__ import annotations

import pytest

from app.services import bitrix_client as svc


@pytest.fixture(autouse=True)
def _reset_backend(monkeypatch):
    # Force stub by clearing the env-derived url
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "bitrix_webhook_url", "", raising=False)
    svc.reset_backend_for_tests()
    yield
    svc.reset_backend_for_tests()


def test_default_backend_is_stub_when_no_webhook():
    client = svc.get_client()
    assert client.is_stub is True
    assert client.provider == "stub"


def test_create_lead_returns_synthetic_id():
    client = svc.get_client()
    result = client.create_lead({"NAME": "Valeria"})
    assert result.success is True
    assert result.provider == "stub"
    assert result.bitrix_id is not None
    assert result.bitrix_id.startswith("stub-lead-")
    assert result.attempts == 1
    assert result.status_code == 200


def test_create_contact_returns_synthetic_id():
    client = svc.get_client()
    result = client.create_contact({"NAME": "X"})
    assert result.success is True
    assert result.bitrix_id.startswith("stub-contact-")


def test_create_deal_returns_synthetic_id():
    client = svc.get_client()
    result = client.create_deal({"TITLE": "Plan"})
    assert result.success is True
    assert result.bitrix_id.startswith("stub-deal-")


def test_update_lead_echoes_id():
    client = svc.get_client()
    result = client.update_lead("123", {"NAME": "Y"})
    assert result.success is True
    assert result.bitrix_id == "123"


def test_add_lead_comment_succeeds():
    client = svc.get_client()
    result = client.add_lead_comment("123", "hola")
    assert result.success is True


def test_pii_helpers_mask_email():
    assert svc.mask_email("ana.lopez@example.com") == "a***@example.com"
    assert svc.mask_email("a@x.com") == "a***@x.com"
    assert svc.mask_email("not-email") == "***"
    assert svc.mask_email(None) == "***"


def test_pii_helpers_mask_phone():
    assert svc.mask_phone("+57 300 1234567") == "***4567"
    assert svc.mask_phone("123") == "***"
    assert svc.mask_phone(None) == "***"


def test_safe_summary_drops_pii():
    payload = {
        "TITLE": "Lead",
        "NAME": "Ana",
        "EMAIL": "ana.lopez@x.com",
        "PHONE": "3001234567",
        "FIELDS": {"FIRST_NAME": "Ana", "EMAIL_FIELD": "x@y.com"},
    }
    summary = svc.safe_summary(payload)
    assert summary["NAME"] == "***"
    assert summary["EMAIL"].startswith("a***@")
    assert summary["PHONE"].startswith("***")
    assert summary["FIELDS"]["FIRST_NAME"] == "***"
    assert summary["FIELDS"]["EMAIL_FIELD"].startswith("x***@")


def test_each_call_is_recorded_on_stub():
    backend = svc._StubBackend()
    backend.call("crm.lead.add", {"fields": {"X": 1}})
    backend.call("crm.lead.update", {"id": "1", "fields": {}})
    assert len(backend.calls) == 2
    assert backend.calls[0][0] == "crm.lead.add"
    assert backend.calls[1][0] == "crm.lead.update"
