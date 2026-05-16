"""IDOR protection tests · GH-F1-SECURITY · S11.5-BE-05.

Validates that `app.core.access.assert_session_access` enforces ownership.

Matrix tested:
  - student A cannot access session owned by student B          → 403
  - psychologist of school_A cannot access session of school_B  → 403
  - psychologist of same school CAN access session              → session returned
  - super_admin can access any session                          → session returned
  - gh_advisor can access any session                           → session returned
  - session does not exist                                      → 404

These are pure-unit tests: they mock the DB query via MagicMock and do not
require a running database.  Integration-level 401 coverage for "no token"
is verified via the helper function comment — HTTPBearer(auto_error=True)
returns 401 before our code runs, guaranteed by FastAPI's dependency system.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Minimal stub classes (avoids importing full model tree with PostgreSQL types)
# ---------------------------------------------------------------------------

class _FakeUser:
    def __init__(self, user_id, role: str, school_id=None):
        self.id = user_id
        self.role = _FakeRole(role)
        self.school_id = school_id


class _FakeRole(str):
    """Thin wrapper so comparisons to UserRole enum work."""
    pass


class _FakeSession:
    def __init__(self, session_id, user_id=None):
        self.id = session_id
        self.user_id = user_id


# ---------------------------------------------------------------------------
# Fixture: patch UserRole constants used inside access.py
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_roles(monkeypatch):
    """Patch UserRole values inside access.py so the helper compares strings."""
    import app.core.access as access_mod
    import app.db.models as models_mod

    # Patch the sets inside access.py to use plain strings
    monkeypatch.setattr(
        access_mod,
        "_BROAD_ACCESS_ROLES",
        {"super_admin", "gh_advisor", "gh_commercial"},
    )
    monkeypatch.setattr(
        access_mod,
        "_SCHOOL_STAFF_ROLES",
        {"school_admin", "psychologist"},
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestAssertSessionAccess:

    def _make_db(self, session=None, owner=None):
        """Build a mock DB session that returns `session` for JourneySession query
        and `owner` for User query.
        """
        db = MagicMock()

        def _query_side_effect(model):
            mock_q = MagicMock()
            model_name = getattr(model, "__name__", str(model))
            if "Session" in model_name:
                mock_q.filter.return_value.first.return_value = session
            elif "User" in model_name:
                mock_q.filter.return_value.first.return_value = owner
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect
        return db

    # ------------------------------------------------------------------
    # 404 — session not found
    # ------------------------------------------------------------------
    def test_404_when_session_not_found(self):
        from app.core.access import assert_session_access

        db = self._make_db(session=None)
        user = _FakeUser(uuid4(), "student")

        with pytest.raises(HTTPException) as exc_info:
            assert_session_access(uuid4(), user, db)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 404

    # ------------------------------------------------------------------
    # Super-admin unrestricted
    # ------------------------------------------------------------------
    def test_super_admin_can_access_any_session(self):
        from app.core.access import assert_session_access

        session_id = uuid4()
        session = _FakeSession(session_id, user_id=uuid4())
        db = self._make_db(session=session)
        user = _FakeUser(uuid4(), "super_admin")

        result = assert_session_access(session_id, user, db)  # type: ignore[arg-type]
        assert result is session

    # ------------------------------------------------------------------
    # gh_advisor unrestricted
    # ------------------------------------------------------------------
    def test_gh_advisor_can_access_any_session(self):
        from app.core.access import assert_session_access

        session_id = uuid4()
        session = _FakeSession(session_id, user_id=uuid4())
        db = self._make_db(session=session)
        user = _FakeUser(uuid4(), "gh_advisor")

        result = assert_session_access(session_id, user, db)  # type: ignore[arg-type]
        assert result is session

    # ------------------------------------------------------------------
    # Student owns the session → allowed
    # ------------------------------------------------------------------
    def test_student_can_access_own_session(self):
        from app.core.access import assert_session_access

        student_id = uuid4()
        session_id = uuid4()
        session = _FakeSession(session_id, user_id=student_id)
        db = self._make_db(session=session)
        user = _FakeUser(student_id, "student")

        result = assert_session_access(session_id, user, db)  # type: ignore[arg-type]
        assert result is session

    # ------------------------------------------------------------------
    # Student A vs Session of Student B → 403
    # ------------------------------------------------------------------
    def test_student_a_forbidden_from_session_of_student_b(self):
        from app.core.access import assert_session_access

        student_a_id = uuid4()
        student_b_id = uuid4()
        session_id = uuid4()
        session = _FakeSession(session_id, user_id=student_b_id)
        db = self._make_db(session=session)
        user_a = _FakeUser(student_a_id, "student")

        with pytest.raises(HTTPException) as exc_info:
            assert_session_access(session_id, user_a, db)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 403

    # ------------------------------------------------------------------
    # Anonymous session (user_id=None) → 403 for non-broad-access
    # ------------------------------------------------------------------
    def test_student_forbidden_from_anonymous_session(self):
        from app.core.access import assert_session_access

        session_id = uuid4()
        session = _FakeSession(session_id, user_id=None)
        db = self._make_db(session=session)
        user = _FakeUser(uuid4(), "student")

        with pytest.raises(HTTPException) as exc_info:
            assert_session_access(session_id, user, db)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 403

    def test_super_admin_can_access_anonymous_session(self):
        from app.core.access import assert_session_access

        session_id = uuid4()
        session = _FakeSession(session_id, user_id=None)
        db = self._make_db(session=session)
        user = _FakeUser(uuid4(), "super_admin")

        result = assert_session_access(session_id, user, db)  # type: ignore[arg-type]
        assert result is session

    # ------------------------------------------------------------------
    # Psychologist cross-school → 403
    # ------------------------------------------------------------------
    def test_psychologist_school_a_forbidden_from_session_in_school_b(self):
        from app.core.access import assert_session_access

        school_a_id = uuid4()
        school_b_id = uuid4()
        psy_id = uuid4()
        student_id = uuid4()

        session_id = uuid4()
        session = _FakeSession(session_id, user_id=student_id)
        # Owner is in school B
        owner = _FakeUser(student_id, "student", school_id=school_b_id)
        db = self._make_db(session=session, owner=owner)
        # Psychologist is in school A
        psy = _FakeUser(psy_id, "psychologist", school_id=school_a_id)

        with pytest.raises(HTTPException) as exc_info:
            assert_session_access(session_id, psy, db)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 403

    # ------------------------------------------------------------------
    # Psychologist same school → allowed
    # ------------------------------------------------------------------
    def test_psychologist_same_school_can_access_session(self):
        from app.core.access import assert_session_access

        shared_school_id = uuid4()
        psy_id = uuid4()
        student_id = uuid4()

        session_id = uuid4()
        session = _FakeSession(session_id, user_id=student_id)
        owner = _FakeUser(student_id, "student", school_id=shared_school_id)
        db = self._make_db(session=session, owner=owner)
        psy = _FakeUser(psy_id, "psychologist", school_id=shared_school_id)

        result = assert_session_access(session_id, psy, db)  # type: ignore[arg-type]
        assert result is session

    # ------------------------------------------------------------------
    # Dangling session (owner deleted) → 403
    # ------------------------------------------------------------------
    def test_psychologist_dangling_session_forbidden(self):
        from app.core.access import assert_session_access

        session_id = uuid4()
        orphan_user_id = uuid4()
        session = _FakeSession(session_id, user_id=orphan_user_id)
        # Owner query returns None (deleted user)
        owner = None
        db = self._make_db(session=session, owner=owner)
        psy = _FakeUser(uuid4(), "psychologist", school_id=uuid4())

        with pytest.raises(HTTPException) as exc_info:
            assert_session_access(session_id, psy, db)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 403
