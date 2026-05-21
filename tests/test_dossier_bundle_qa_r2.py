"""GH-LOCAL-QA-RONDA2 · 2026-05-21.

Unit tests for the dossier bundle fixes:

- B-015 · `_build_demographics` falls back to `user.onboarding_answers`
  when there's no Session (covers seeded users + real users who completed
  onboarding but not yet journey).
- B-017 · `_build_aspirations` reads from `declaredAspirations` (the new
  journey question) and combines onboarding + journey answers.
- B-016 · documented as wontfix-seed (`journey_answers={}` is correct when
  there's no session; not a code bug).

We test `_get_combined_answers` (new helper) and the two callers via
pure-unit assertions, without spinning up the full FastAPI app.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock


def _mock_db_no_session():
    """Return a db stub where `.query().filter().order_by().first()` returns None."""
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.first.return_value = None
    return db


def _mock_db_with_session(answers):
    """Return a db stub where the latest Session has the given answers."""
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.first.return_value = SimpleNamespace(answers=answers)
    return db


def _user(onboarding_answers=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Test Student",
        email="test@grasshopper.dev",
        birthdate=None,
        english_cefr_level=None,
        english_test_completed=False,
        onboarding_status="completed",
        budget_band=None,
        budget_max_usd=None,
        preferred_countries=[],
        onboarding_answers=onboarding_answers,
    )


# ---------------------------------------------------------------------------
# B-015 · _get_combined_answers fallback to onboarding_answers
# ---------------------------------------------------------------------------


def test_combined_answers_uses_session_when_present():
    from app.services.dossier_service import _get_combined_answers

    student = _user(onboarding_answers={"grade": "B2", "city": "Bogotá"})
    db = _mock_db_with_session({"grade": "C1", "country": "Colombia"})
    out = _get_combined_answers(db, student)
    # Session wins over onboarding for overlapping keys (grade); union for non-overlapping
    assert out["grade"] == "C1"
    assert out["city"] == "Bogotá"  # from onboarding fallback
    assert out["country"] == "Colombia"  # from session


def test_combined_answers_falls_back_to_onboarding_when_no_session():
    from app.services.dossier_service import _get_combined_answers

    student = _user(onboarding_answers={"grade": "B2", "city": "Bogotá", "country": "Colombia"})
    db = _mock_db_no_session()
    out = _get_combined_answers(db, student)
    assert out == {"grade": "B2", "city": "Bogotá", "country": "Colombia"}


def test_combined_answers_empty_when_both_empty():
    from app.services.dossier_service import _get_combined_answers

    student = _user(onboarding_answers=None)
    db = _mock_db_no_session()
    out = _get_combined_answers(db, student)
    assert out == {}


def test_combined_answers_empty_session_uses_onboarding():
    """Even if Session exists with empty answers, we fall back to onboarding for missing keys."""
    from app.services.dossier_service import _get_combined_answers

    student = _user(onboarding_answers={"grade": "A2"})
    db = _mock_db_with_session({})  # session present but empty
    out = _get_combined_answers(db, student)
    assert out["grade"] == "A2"


# ---------------------------------------------------------------------------
# B-017 · _build_aspirations reads declaredAspirations
# ---------------------------------------------------------------------------


def _mock_db_aspirations(session_answers, profile_data=None):
    """db where Session.answers is provided AND ConsolidatedProfileCache exists."""
    db = MagicMock()
    # query for Session
    sess_chain = MagicMock()
    sess_chain.filter.return_value = sess_chain
    sess_chain.order_by.return_value = sess_chain
    sess_chain.first.return_value = SimpleNamespace(answers=session_answers)
    # query for ConsolidatedProfileCache
    cache_chain = MagicMock()
    cache_chain.filter.return_value = cache_chain
    cache_chain.first.return_value = (
        SimpleNamespace(invalidated_at=None, profile_data=profile_data)
        if profile_data is not None
        else None
    )
    db.query.side_effect = lambda model: sess_chain if model.__name__ == "Session" else cache_chain
    return db


def test_aspirations_includes_declared_aspirations_from_journey():
    """B-017 · the new journey question 'declaredAspirations' must populate aspirations.declared."""
    from app.services.dossier_service import _build_aspirations

    student = _user()
    db = _mock_db_aspirations(
        session_answers={
            "declaredAspirations": "Ser ingeniera ambiental trabajando en energía renovable",
            "interestType": ["Construir una carrera"],
        }
    )
    aspirations, has_profile, profile_dict = _build_aspirations(db, student)
    assert "Ser ingeniera ambiental trabajando en energía renovable" in aspirations.declared
    assert has_profile is False
    assert profile_dict is None


def test_aspirations_falls_back_to_onboarding_keys_when_no_journey():
    """B-017 · if the student only did onboarding (no journey), fall back to onboarding aspirations."""
    from app.services.dossier_service import _build_aspirations

    student = _user(onboarding_answers={"dreamCareer": "Doctor sin fronteras"})
    db = _mock_db_aspirations(session_answers={})  # no journey data
    aspirations, _, _ = _build_aspirations(db, student)
    assert "Doctor sin fronteras" in aspirations.declared


def test_aspirations_journey_overrides_onboarding():
    """B-017 · journey answer should be present even if onboarding had old aspiration data."""
    from app.services.dossier_service import _build_aspirations

    student = _user(onboarding_answers={"dreamCareer": "Old answer"})
    db = _mock_db_aspirations(
        session_answers={"declaredAspirations": "New journey answer"}
    )
    aspirations, _, _ = _build_aspirations(db, student)
    # Both should appear (declared is a list; we don't dedupe semantically)
    assert "New journey answer" in aspirations.declared
    assert "Old answer" in aspirations.declared


def test_aspirations_empty_when_both_empty():
    from app.services.dossier_service import _build_aspirations

    student = _user(onboarding_answers=None)
    db = _mock_db_aspirations(session_answers={})
    aspirations, has_profile, _ = _build_aspirations(db, student)
    assert aspirations.declared == []
    assert aspirations.inferred == []
    assert has_profile is False


# ---------------------------------------------------------------------------
# state_machine · declaredAspirations step
# ---------------------------------------------------------------------------


def test_state_machine_has_declared_aspirations_step():
    from app.core.state_machine import get_step, get_next_step

    step = get_step("declaredAspirations")
    assert step is not None
    assert step.id == "declaredAspirations"
    assert step.save_to == "declaredAspirations"
    assert step.view_type.value == "OPEN_TEXT"
    assert "5 años" in step.question
    # Flow: dontWant → declaredAspirations → partialSummary1
    assert get_next_step("dontWant") == "declaredAspirations"
    assert get_next_step("declaredAspirations") == "partialSummary1"
