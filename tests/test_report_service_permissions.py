"""Unit tests · report_service permission rules (GH-S7-BE-05).

Pure logic tests · no DB needed.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.db.models import UserRole
from app.services.report_service import (
    user_can_access_report,
    user_can_generate_for,
    user_can_send_email,
)


def _user(role, school_id=None, uid=None):
    return SimpleNamespace(
        id=uid or uuid4(),
        role=role,
        school_id=school_id,
    )


def _report(user_id):
    return SimpleNamespace(id=uuid4(), user_id=user_id)


# ---------------------------------------------------------------------------
# user_can_access_report
# ---------------------------------------------------------------------------


def test_student_can_access_own_report():
    s = _user(UserRole.STUDENT, school_id="school-A")
    rep = _report(s.id)
    assert user_can_access_report(s, rep, s) is True


def test_student_cannot_access_other_report():
    s1 = _user(UserRole.STUDENT, school_id="school-A")
    s2 = _user(UserRole.STUDENT, school_id="school-A")
    rep = _report(s2.id)
    assert user_can_access_report(s1, rep, s2) is False


def test_psychologist_can_access_same_school_report():
    psy = _user(UserRole.PSYCHOLOGIST, school_id="school-A")
    s = _user(UserRole.STUDENT, school_id="school-A")
    rep = _report(s.id)
    assert user_can_access_report(psy, rep, s) is True


def test_psychologist_cannot_access_different_school():
    psy = _user(UserRole.PSYCHOLOGIST, school_id="school-A")
    s = _user(UserRole.STUDENT, school_id="school-B")
    rep = _report(s.id)
    assert user_can_access_report(psy, rep, s) is False


def test_school_admin_can_access_same_school_report():
    adm = _user(UserRole.SCHOOL_ADMIN, school_id="school-A")
    s = _user(UserRole.STUDENT, school_id="school-A")
    rep = _report(s.id)
    assert user_can_access_report(adm, rep, s) is True


def test_super_admin_can_access_anything():
    su = _user(UserRole.SUPER_ADMIN)
    s = _user(UserRole.STUDENT, school_id="school-X")
    rep = _report(s.id)
    assert user_can_access_report(su, rep, s) is True


def test_psychologist_without_school_blocked():
    psy = _user(UserRole.PSYCHOLOGIST, school_id=None)
    s = _user(UserRole.STUDENT, school_id="school-A")
    rep = _report(s.id)
    assert user_can_access_report(psy, rep, s) is False


# ---------------------------------------------------------------------------
# user_can_generate_for
# ---------------------------------------------------------------------------


def test_student_can_generate_for_self():
    s = _user(UserRole.STUDENT)
    assert user_can_generate_for(s, s) is True


def test_student_cannot_generate_for_other():
    s1 = _user(UserRole.STUDENT)
    s2 = _user(UserRole.STUDENT)
    assert user_can_generate_for(s1, s2) is False


def test_psychologist_generates_for_school_student():
    psy = _user(UserRole.PSYCHOLOGIST, school_id="A")
    s = _user(UserRole.STUDENT, school_id="A")
    assert user_can_generate_for(psy, s) is True


def test_psychologist_blocked_other_school():
    psy = _user(UserRole.PSYCHOLOGIST, school_id="A")
    s = _user(UserRole.STUDENT, school_id="B")
    assert user_can_generate_for(psy, s) is False


# ---------------------------------------------------------------------------
# user_can_send_email · same rules as access
# ---------------------------------------------------------------------------


def test_send_email_follows_access_rules():
    s1 = _user(UserRole.STUDENT)
    s2 = _user(UserRole.STUDENT)
    rep = _report(s2.id)
    assert user_can_send_email(s1, rep, s2) is False
    assert user_can_send_email(s2, rep, s2) is True
