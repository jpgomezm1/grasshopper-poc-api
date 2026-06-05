"""M-006 · consentimiento parental de menores · unit tests (fakes)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services import parental_consent_service as pcs
from app.api.v1.vocational_tests import submit_test, SubmitVocationalRequest
from app.api.v1.parental_consent import require_parental_consent_if_minor


def _bday_for_age(age: int) -> date:
    t = date.today()
    try:
        return date(t.year - age, t.month, t.day)
    except ValueError:  # 29-feb edge
        return date(t.year - age, t.month, t.day - 1)


def _student(age=None, consent=None, role="student", **kw):
    bd = _bday_for_age(age) if age is not None else None
    base = dict(
        id="s1",
        name="Mateo",
        role=SimpleNamespace(value=role) if False else role,
        birthdate=bd,
        consent_parental_at=consent,
        consent_data_processing_version=None,
        parental_consent_token=None,
        parental_consent_token_expires=None,
        parental_consent_parent_email=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- predicados ---

def test_age_and_threshold():
    assert pcs.age_of(_student(age=None)) is None
    assert pcs.is_minor_under_threshold(_student(age=14)) is True
    assert pcs.is_minor_under_threshold(_student(age=17)) is False
    # edad desconocida NO bloquea (no rompe usuarios sin fecha)
    assert pcs.is_minor_under_threshold(_student(age=None)) is False


def test_needs_parental_consent():
    assert pcs.needs_parental_consent(_student(age=14, consent=None)) is True
    assert pcs.needs_parental_consent(_student(age=14, consent=datetime.utcnow())) is False
    assert pcs.needs_parental_consent(_student(age=17, consent=None)) is False
    assert pcs.needs_parental_consent(_student(age=None, consent=None)) is False


def test_consent_status_shape():
    s = _student(age=14)
    st = pcs.consent_status(s)
    assert st["required"] is True and st["granted"] is False and st["pending"] is False


# --- request / lookup / sign ---

def test_request_consent_sends_email_and_sets_token(monkeypatch):
    sent = {}

    def fake_send_email(*, to, subject, html_body, text_body=None):
        sent["to"] = to
        return SimpleNamespace(provider="stub", delivered=True, message_id=None, reason=None)

    monkeypatch.setattr(pcs.email_service, "send_email", fake_send_email)
    s = _student(age=13)
    db = MagicMock()
    out = pcs.request_consent(db, s, "Madre@Correo.com", request=None)
    assert sent["to"] == "madre@correo.com"
    assert s.parental_consent_token  # token seteado
    assert s.parental_consent_token_expires > datetime.utcnow()
    assert out["parent_email_masked"].endswith("@correo.com")
    db.commit.assert_called()


def test_request_consent_rejects_bad_email():
    with pytest.raises(pcs.ParentalConsentError):
        pcs.request_consent(MagicMock(), _student(age=13), "no-es-email", request=None)


def test_sign_grants_consent_and_consumes_token():
    s = _student(age=13)
    s.parental_consent_token = "tok123"
    s.parental_consent_token_expires = datetime.utcnow() + timedelta(hours=1)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = s
    out = pcs.sign(db, "tok123", request=None)
    assert out["signed"] is True
    assert s.consent_parental_at is not None          # consentimiento otorgado
    assert s.parental_consent_token is None            # token consumido (un solo uso)


def test_sign_expired_token_raises():
    s = _student(age=13)
    s.parental_consent_token = "tok"
    s.parental_consent_token_expires = datetime.utcnow() - timedelta(hours=1)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = s
    with pytest.raises(pcs.ParentalConsentError):
        pcs.sign(db, "tok", request=None)


def test_lookup_unknown_token_raises():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(pcs.ParentalConsentError):
        pcs.lookup(db, "nope")


# --- gate ---

def test_submit_blocked_for_minor_without_consent():
    req = SubmitVocationalRequest(answers={})
    with pytest.raises(HTTPException) as ei:
        submit_test("holland", req, current_user=_student(age=14), db=MagicMock())
    assert ei.value.status_code == 403
    assert ei.value.detail == "minor_parental_consent_required"


def test_dependency_blocks_minor_allows_others():
    # menor sin consentimiento → 403
    with pytest.raises(HTTPException) as ei:
        require_parental_consent_if_minor(current_user=_student(age=14))
    assert ei.value.status_code == 403
    # adulto → pasa
    assert require_parental_consent_if_minor(current_user=_student(age=20)) is not None
    # edad desconocida → pasa (no bloquea)
    assert require_parental_consent_if_minor(current_user=_student(age=None)) is not None
