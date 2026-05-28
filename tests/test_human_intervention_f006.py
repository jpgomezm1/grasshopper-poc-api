"""F-006 · Human Intervention notes · unit tests for gate logic + validation."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.db.models import UserRole


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_closeness_level_rejects_unknown():
    from app.schemas.human_intervention import HumanInterventionNoteUpdate

    with pytest.raises(Exception):
        HumanInterventionNoteUpdate(closeness_level="banana")


def test_closeness_level_accepts_known():
    from app.schemas.human_intervention import HumanInterventionNoteUpdate

    for v in ("cold", "warm", "hot", "closing", "closed_won", "closed_lost"):
        m = HumanInterventionNoteUpdate(closeness_level=v)
        assert m.closeness_level == v


def test_closeness_level_empty_string_becomes_none():
    from app.schemas.human_intervention import HumanInterventionNoteUpdate

    m = HumanInterventionNoteUpdate(closeness_level="")
    assert m.closeness_level is None


def test_notes_max_length_enforced():
    from app.schemas.human_intervention import HumanInterventionNoteUpdate

    with pytest.raises(Exception):
        HumanInterventionNoteUpdate(notes="x" * 4001)


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------


def _user(role, **kw):
    base = dict(id=uuid.uuid4(), role=role, assigned_to_user_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_gate_allows_assigned_advisor():
    from app.api.v1.human_intervention import _require_owner_advisor_or_super_admin

    advisor = _user(UserRole.GH_ADVISOR)
    student = _user(UserRole.STUDENT, assigned_to_user_id=advisor.id)

    _require_owner_advisor_or_super_admin(student, advisor)  # no raise


def test_gate_allows_super_admin_regardless_of_assignment():
    from app.api.v1.human_intervention import _require_owner_advisor_or_super_admin

    sa = _user(UserRole.SUPER_ADMIN)
    student = _user(UserRole.STUDENT, assigned_to_user_id=uuid.uuid4())  # someone else's lead

    _require_owner_advisor_or_super_admin(student, sa)  # no raise


def test_gate_blocks_non_assigned_advisor():
    from app.api.v1.human_intervention import _require_owner_advisor_or_super_admin

    other_advisor = _user(UserRole.GH_ADVISOR)
    student = _user(UserRole.STUDENT, assigned_to_user_id=uuid.uuid4())  # assigned to someone else

    with pytest.raises(HTTPException) as exc:
        _require_owner_advisor_or_super_admin(student, other_advisor)
    assert exc.value.status_code == 403


def test_gate_blocks_unassigned_student_even_for_advisor():
    from app.api.v1.human_intervention import _require_owner_advisor_or_super_admin

    advisor = _user(UserRole.GH_ADVISOR)
    student = _user(UserRole.STUDENT, assigned_to_user_id=None)  # unassigned

    with pytest.raises(HTTPException) as exc:
        _require_owner_advisor_or_super_admin(student, advisor)
    assert exc.value.status_code == 403


def test_gate_blocks_psychologist():
    from app.api.v1.human_intervention import _require_owner_advisor_or_super_admin

    psy = _user(UserRole.PSYCHOLOGIST)
    advisor = _user(UserRole.GH_ADVISOR)
    student = _user(UserRole.STUDENT, assigned_to_user_id=advisor.id)

    with pytest.raises(HTTPException) as exc:
        _require_owner_advisor_or_super_admin(student, psy)
    assert exc.value.status_code == 403


def test_gate_blocks_student_owning_their_own_record():
    from app.api.v1.human_intervention import _require_owner_advisor_or_super_admin

    student = _user(UserRole.STUDENT)
    student.assigned_to_user_id = uuid.uuid4()  # has an advisor

    with pytest.raises(HTTPException) as exc:
        _require_owner_advisor_or_super_admin(student, student)
    assert exc.value.status_code == 403


def test_gate_blocks_gh_commercial():
    """Commercial role is NOT entitled to advisor-private notes."""
    from app.api.v1.human_intervention import _require_owner_advisor_or_super_admin

    commercial = _user(UserRole.GH_COMMERCIAL)
    student = _user(UserRole.STUDENT, assigned_to_user_id=commercial.id)

    with pytest.raises(HTTPException) as exc:
        _require_owner_advisor_or_super_admin(student, commercial)
    assert exc.value.status_code == 403
