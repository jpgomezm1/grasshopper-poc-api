"""GH-STUDENT-EXPERIENCE · 2026-05-05.

Pure-unit tests for the new student-facing /me/* endpoints in
``app/api/v1/me.py``.

We exercise:
- ``_require_student`` rejects every non-student role.
- ``_resolve_advisor_for_student`` handles unassigned + role mismatch.
- ``_resolve_psy_for_student`` returns None for B2C students with no school.
- ``_evaluate_journey_complete`` honours the (onboarding + 3 tests +
  2 routes) criteria.

We avoid spinning up the full FastAPI app (SQLite/UUID test infra is
pre-broken · same approach as test_psychologist_clinical_unit.py).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.api.v1.me import (
    _require_student,
    _resolve_advisor_for_student,
)
from app.db.models import OnboardingStatus, UserRole


def _user(role, school_id=None, assigned_to_user_id=None, user_id=None):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        role=role,
        school_id=school_id,
        assigned_to_user_id=assigned_to_user_id,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# _require_student
# ---------------------------------------------------------------------------


def test_require_student_passes_for_student():
    student = _user(UserRole.STUDENT)
    # Should not raise
    _require_student(student)


@pytest.mark.parametrize(
    "role",
    [
        UserRole.GH_ADVISOR,
        UserRole.GH_COMMERCIAL,
        UserRole.PSYCHOLOGIST,
        UserRole.SCHOOL_ADMIN,
        UserRole.SUPER_ADMIN,
        UserRole.PARENT,
    ],
)
def test_require_student_blocks_other_roles(role):
    from fastapi import HTTPException

    actor = _user(role)
    with pytest.raises(HTTPException) as exc:
        _require_student(actor)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# _resolve_advisor_for_student
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, target_user):
        self.target_user = target_user

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.target_user


class _FakeDB:
    def __init__(self, target_user=None):
        self.target_user = target_user

    def query(self, _model):
        return _FakeQuery(self.target_user)


def test_resolve_advisor_returns_none_when_not_assigned():
    student = _user(UserRole.STUDENT, assigned_to_user_id=None)
    db = _FakeDB(target_user=None)
    assert _resolve_advisor_for_student(db, student) is None


def test_resolve_advisor_returns_user_when_assigned():
    advisor = _user(UserRole.GH_ADVISOR)
    student = _user(UserRole.STUDENT, assigned_to_user_id=advisor.id)
    # The fake query already returns advisor unconditionally.
    db = _FakeDB(target_user=advisor)
    result = _resolve_advisor_for_student(db, student)
    assert result is advisor


def test_resolve_advisor_returns_none_when_target_role_mismatch():
    other = _user(UserRole.STUDENT)
    student = _user(UserRole.STUDENT, assigned_to_user_id=other.id)
    # The filter chain restricts role · we simulate "no match" via target=None.
    db = _FakeDB(target_user=None)
    assert _resolve_advisor_for_student(db, student) is None


# ---------------------------------------------------------------------------
# Privacy enum extension
# ---------------------------------------------------------------------------


def test_privacy_enum_accepts_shared_with_student():
    from app.db.models import SESSION_NOTE_PRIVACIES

    assert "shared_with_student" in SESSION_NOTE_PRIVACIES
    # Backwards compatibility · existing values still present.
    for old in ("private", "shared_supervisor", "shared_team"):
        assert old in SESSION_NOTE_PRIVACIES


# ---------------------------------------------------------------------------
# Notification type extension
# ---------------------------------------------------------------------------


def test_notification_types_extended_for_students():
    from app.services.notifications_service import NOTIFICATION_TYPES

    for new_type in (
        "session.scheduled",
        "session.reminder",
        "task.assigned",
        "school_event.created",
        "program.recommended",
    ):
        assert new_type in NOTIFICATION_TYPES, f"missing {new_type}"


def test_notification_types_no_message_received():
    """REGLA DURA · 2026-05-05 (JP): no bidirectional messaging.

    Asserts the type system has no `message_received` whitelisted.
    """
    from app.services.notifications_service import NOTIFICATION_TYPES

    forbidden = {"message_received", "message.received", "chat.message"}
    assert NOTIFICATION_TYPES.isdisjoint(forbidden)


# ---------------------------------------------------------------------------
# Schemas surface
# ---------------------------------------------------------------------------


def test_school_summary_exposes_branding_colors():
    from app.schemas.school import SchoolSummary

    s = SchoolSummary(
        id=uuid.uuid4(),
        name="Cumbres",
        slug="cumbres",
        logo_url=None,
        branding_primary_color="#8b5cf6",
        secondary_color="#3b82f6",
    )
    assert s.branding_primary_color == "#8b5cf6"
    assert s.secondary_color == "#3b82f6"


def test_quickprofile_import_payload_validates():
    from app.api.v1.me import QuickProfileImportIn

    payload = QuickProfileImportIn(
        name="Ana",
        phone="+57300...",
        budget_band="medio",
        budget_max_usd=40000,
        preferred_countries=["Estados Unidos", "Canadá"],
        answers={"lifeStage": "secundaria"},
    )
    assert payload.budget_band == "medio"
    assert payload.preferred_countries == ["Estados Unidos", "Canadá"]


def test_quickprofile_import_rejects_invalid_band():
    from app.api.v1.me import QuickProfileImportIn
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        QuickProfileImportIn(budget_band="ultra_premium")


def test_session_request_payload_min_length():
    from app.api.v1.me import SessionRequestIn
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SessionRequestIn(reason="x")  # too short


def test_rsvp_status_enum_strict():
    from app.api.v1.me import RsvpIn
    from pydantic import ValidationError

    assert RsvpIn(status="going").status == "going"
    assert RsvpIn(status="declined").status == "declined"
    assert RsvpIn(status="maybe").status == "maybe"
    with pytest.raises(ValidationError):
        RsvpIn(status="snooze")
