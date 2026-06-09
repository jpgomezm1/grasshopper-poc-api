"""F-005 · disclaimer pre-test · unit tests.

Siguiendo la convención del repo: pruebas unitarias con fakes (los gates de
endpoint end-to-end quedan para Playwright/curl post-merge).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.vocational_tests import (
    SubmitVocationalRequest,
    _disclaimer_accepted,
    accept_disclaimer,
    get_disclaimer_status,
    submit_test,
)
from app.data.disclaimer import DISCLAIMER_VERSION


def _user(disclaimers=None):
    return SimpleNamespace(id="u1", test_disclaimers=disclaimers)


def test_disclaimer_accepted_helper():
    cur = {"accepted_at": "x", "version": DISCLAIMER_VERSION}
    assert _disclaimer_accepted(_user(None), "holland") is False
    assert _disclaimer_accepted(_user({}), "holland") is False
    assert _disclaimer_accepted(_user({"holland": cur}), "holland") is True
    # aceptar un test no habilita otro
    assert _disclaimer_accepted(_user({"holland": cur}), "mbti") is False
    # aceptación sin versión (legacy) no cuenta
    assert _disclaimer_accepted(_user({"holland": {"accepted_at": "x"}}), "holland") is False


def test_accept_disclaimer_stamps_user():
    user = _user(None)
    db = MagicMock()
    out = accept_disclaimer("holland", current_user=user, db=db)
    assert out["test_id"] == "holland"
    assert out["version"] == DISCLAIMER_VERSION
    assert user.test_disclaimers["holland"]["version"] == DISCLAIMER_VERSION
    assert user.test_disclaimers["holland"]["accepted_at"]
    db.commit.assert_called_once()


def test_accept_disclaimer_unknown_test_404():
    with pytest.raises(HTTPException) as ei:
        accept_disclaimer("no-existe", current_user=_user(None), db=MagicMock())
    assert ei.value.status_code == 404


def test_accept_disclaimer_preserves_other_tests():
    user = _user({"mbti": {"accepted_at": "ayer", "version": "v0"}})
    accept_disclaimer("holland", current_user=user, db=MagicMock())
    # No pisa la aceptación previa de otro test
    assert "mbti" in user.test_disclaimers
    assert "holland" in user.test_disclaimers


def test_submit_blocked_without_disclaimer():
    req = SubmitVocationalRequest(answers={})
    with pytest.raises(HTTPException) as ei:
        submit_test("holland", req, current_user=_user(None), db=MagicMock())
    assert ei.value.status_code == 403
    assert "aviso legal" in ei.value.detail.lower()


def test_get_disclaimer_status_returns_text_and_accepted():
    user = _user({"holland": {"accepted_at": "2026-06-04T00:00:00", "version": DISCLAIMER_VERSION}})
    out = get_disclaimer_status(current_user=user)
    assert out["version"] == DISCLAIMER_VERSION
    assert out["text"]
    assert out["accepted"]["holland"] == "2026-06-04T00:00:00"


# --- hardening · enforcement de versión (revisión adversarial) ---

def test_outdated_version_requires_reacceptance():
    user = _user({"holland": {"accepted_at": "x", "version": "version-vieja"}})
    # El gate ya no la cuenta como aceptada
    assert _disclaimer_accepted(user, "holland") is False
    # Y el status no la lista como aceptada (el front re-pedirá la firma)
    assert "holland" not in get_disclaimer_status(current_user=user)["accepted"]


def test_submit_blocked_when_version_outdated():
    req = SubmitVocationalRequest(answers={})
    user = _user({"holland": {"accepted_at": "x", "version": "version-vieja"}})
    with pytest.raises(HTTPException) as ei:
        submit_test("holland", req, current_user=user, db=MagicMock())
    assert ei.value.status_code == 403
