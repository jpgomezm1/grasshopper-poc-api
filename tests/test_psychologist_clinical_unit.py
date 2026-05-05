"""GH-PSY-CLINICAL · 2026-05-05.

Pure-unit tests for the new clinical permission gates that allow the
school **psychologist** role to access the clinical surface, scoped to
students of their own school.

We test the predicate `_can_access_clinical_data` and the session
service's `can_view_session` / `can_view_note` / `can_edit_session` /
`can_edit_note` helpers — without spinning up the full FastAPI app
(SQLite + UUID rendering is broken in the existing test infra · pre-
existing problem and unrelated to this sprint).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from datetime import datetime

from app.db.models import UserRole


# ---------------------------------------------------------------------------
# Lightweight stand-ins for User / OrientationSession / SessionNote
# ---------------------------------------------------------------------------


def _user(role, school_id=None, gh_contact_requested_at=None, user_id=None):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        role=role,
        school_id=school_id,
        gh_contact_requested_at=gh_contact_requested_at,
    )


def _session(advisor_user_id, student_user_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        advisor_user_id=advisor_user_id,
        student_user_id=student_user_id or uuid.uuid4(),
    )


def _note(advisor_user_id, privacy="private"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        advisor_user_id=advisor_user_id,
        privacy=privacy,
    )


# ---------------------------------------------------------------------------
# clinical._can_access_clinical_data
# ---------------------------------------------------------------------------


def test_super_admin_always_can_access():
    from app.api.v1.clinical import _can_access_clinical_data

    student = _user(UserRole.STUDENT, school_id=uuid.uuid4())
    super_user = _user(UserRole.SUPER_ADMIN)
    assert _can_access_clinical_data(super_user, student) is True


def test_advisor_can_access_b2c_student():
    from app.api.v1.clinical import _can_access_clinical_data

    advisor = _user(UserRole.GH_ADVISOR)
    student = _user(UserRole.STUDENT, school_id=None)
    assert _can_access_clinical_data(advisor, student) is True


def test_advisor_blocked_for_silent_b2b_student():
    from app.api.v1.clinical import _can_access_clinical_data

    advisor = _user(UserRole.GH_ADVISOR)
    student = _user(UserRole.STUDENT, school_id=uuid.uuid4(), gh_contact_requested_at=None)
    assert _can_access_clinical_data(advisor, student) is False


def test_advisor_can_access_opted_in_b2b_student():
    from app.api.v1.clinical import _can_access_clinical_data

    advisor = _user(UserRole.GH_ADVISOR)
    student = _user(
        UserRole.STUDENT,
        school_id=uuid.uuid4(),
        gh_contact_requested_at=datetime.utcnow(),
    )
    assert _can_access_clinical_data(advisor, student) is True


def test_psy_can_access_same_school_student():
    from app.api.v1.clinical import _can_access_clinical_data

    school_id = uuid.uuid4()
    psy = _user(UserRole.PSYCHOLOGIST, school_id=school_id)
    student = _user(UserRole.STUDENT, school_id=school_id)
    assert _can_access_clinical_data(psy, student) is True


def test_psy_blocked_for_other_school_student():
    from app.api.v1.clinical import _can_access_clinical_data

    psy = _user(UserRole.PSYCHOLOGIST, school_id=uuid.uuid4())
    student = _user(UserRole.STUDENT, school_id=uuid.uuid4())  # different school
    assert _can_access_clinical_data(psy, student) is False


def test_psy_blocked_for_b2c_student():
    """A psychologist's clinical surface should not extend to B2C students."""
    from app.api.v1.clinical import _can_access_clinical_data

    psy = _user(UserRole.PSYCHOLOGIST, school_id=uuid.uuid4())
    student = _user(UserRole.STUDENT, school_id=None)
    assert _can_access_clinical_data(psy, student) is False


def test_psy_without_school_blocked():
    """A psy user without a school_id is misconfigured · should not bypass."""
    from app.api.v1.clinical import _can_access_clinical_data

    psy = _user(UserRole.PSYCHOLOGIST, school_id=None)
    student = _user(UserRole.STUDENT, school_id=uuid.uuid4())
    assert _can_access_clinical_data(psy, student) is False


def test_gh_commercial_blocked_from_clinical_surface():
    from app.api.v1.clinical import _can_access_clinical_data

    commercial = _user(UserRole.GH_COMMERCIAL)
    student = _user(UserRole.STUDENT, school_id=None)
    assert _can_access_clinical_data(commercial, student) is False


def test_school_admin_blocked_from_clinical_advisor_endpoints():
    from app.api.v1.clinical import _can_access_clinical_data

    school_id = uuid.uuid4()
    admin = _user(UserRole.SCHOOL_ADMIN, school_id=school_id)
    student = _user(UserRole.STUDENT, school_id=school_id)
    assert _can_access_clinical_data(admin, student) is False


def test_student_blocked():
    from app.api.v1.clinical import _can_access_clinical_data

    student_self = _user(UserRole.STUDENT)
    other_student = _user(UserRole.STUDENT, school_id=uuid.uuid4())
    assert _can_access_clinical_data(student_self, other_student) is False


# ---------------------------------------------------------------------------
# orientation_session_service · session/note visibility
# ---------------------------------------------------------------------------


def test_session_view_psy_owns():
    from app.services.orientation_session_service import can_view_session

    psy = _user(UserRole.PSYCHOLOGIST)
    sess = _session(advisor_user_id=psy.id)
    assert can_view_session(sess, psy) is True


def test_session_view_psy_other_psy_blocked():
    from app.services.orientation_session_service import can_view_session

    psy_owner = _user(UserRole.PSYCHOLOGIST)
    psy_other = _user(UserRole.PSYCHOLOGIST)
    sess = _session(advisor_user_id=psy_owner.id)
    assert can_view_session(sess, psy_other) is False


def test_session_view_advisor_other_advisor_blocked():
    from app.services.orientation_session_service import can_view_session

    advisor_owner = _user(UserRole.GH_ADVISOR)
    advisor_other = _user(UserRole.GH_ADVISOR)
    sess = _session(advisor_user_id=advisor_owner.id)
    assert can_view_session(sess, advisor_other) is False


def test_session_view_super_admin_sees_all():
    from app.services.orientation_session_service import can_view_session

    advisor = _user(UserRole.GH_ADVISOR)
    super_user = _user(UserRole.SUPER_ADMIN)
    sess = _session(advisor_user_id=advisor.id)
    assert can_view_session(sess, super_user) is True


def test_session_view_school_admin_blocked():
    from app.services.orientation_session_service import can_view_session

    advisor = _user(UserRole.GH_ADVISOR)
    school_admin = _user(UserRole.SCHOOL_ADMIN)
    sess = _session(advisor_user_id=advisor.id)
    assert can_view_session(sess, school_admin) is False


def test_session_view_gh_commercial_blocked():
    from app.services.orientation_session_service import can_view_session

    advisor = _user(UserRole.GH_ADVISOR)
    commercial = _user(UserRole.GH_COMMERCIAL)
    sess = _session(advisor_user_id=advisor.id)
    assert can_view_session(sess, commercial) is False


def test_note_view_other_psy_only_shared_team():
    from app.services.orientation_session_service import can_view_note

    owner = _user(UserRole.PSYCHOLOGIST)
    other = _user(UserRole.PSYCHOLOGIST)
    sess = _session(advisor_user_id=owner.id)
    private = _note(advisor_user_id=owner.id, privacy="private")
    shared = _note(advisor_user_id=owner.id, privacy="shared_team")
    supervisor = _note(advisor_user_id=owner.id, privacy="shared_supervisor")
    assert can_view_note(private, sess, other) is False
    assert can_view_note(shared, sess, other) is True
    assert can_view_note(supervisor, sess, other) is False


def test_note_view_session_owner_psy_sees_own_notes():
    from app.services.orientation_session_service import can_view_note

    psy = _user(UserRole.PSYCHOLOGIST)
    sess = _session(advisor_user_id=psy.id)
    note = _note(advisor_user_id=psy.id, privacy="private")
    assert can_view_note(note, sess, psy) is True


def test_session_edit_psy_owns():
    from app.services.orientation_session_service import can_edit_session

    psy = _user(UserRole.PSYCHOLOGIST)
    sess = _session(advisor_user_id=psy.id)
    assert can_edit_session(sess, psy) is True


def test_session_edit_other_psy_blocked():
    from app.services.orientation_session_service import can_edit_session

    psy_owner = _user(UserRole.PSYCHOLOGIST)
    psy_other = _user(UserRole.PSYCHOLOGIST)
    sess = _session(advisor_user_id=psy_owner.id)
    assert can_edit_session(sess, psy_other) is False


def test_note_edit_only_author():
    from app.services.orientation_session_service import can_edit_note

    psy = _user(UserRole.PSYCHOLOGIST)
    other = _user(UserRole.PSYCHOLOGIST)
    note = _note(advisor_user_id=psy.id, privacy="shared_team")
    assert can_edit_note(note, psy) is True
    assert can_edit_note(note, other) is False
