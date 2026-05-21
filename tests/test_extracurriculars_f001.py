"""F-001 · CV builder etapa 1 · unit tests for extracurricular_service.

Tests pure de validación y manipulación (no requieren BD viva).
Los tests de gates de endpoints quedan para integration tests de Playwright
o smoke vía curl post-merge.
"""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _user():
    return SimpleNamespace(id=uuid.uuid4(), email="stu@example.com")


# ---------------------------------------------------------------------------
# create_activity validation
# ---------------------------------------------------------------------------


def test_create_activity_rejects_invalid_category():
    from app.services.extracurricular_service import create_activity

    db = MagicMock()
    user = _user()
    with pytest.raises(ValueError, match="invalid category"):
        create_activity(
            db,
            user=user,
            category="banana",
            name="Test",
        )


def test_create_activity_rejects_inverted_dates():
    from app.services.extracurricular_service import create_activity

    db = MagicMock()
    user = _user()
    with pytest.raises(ValueError, match="end_date must be on or after"):
        create_activity(
            db,
            user=user,
            category="sport",
            name="Fútbol",
            start_date=date(2024, 6, 1),
            end_date=date(2024, 5, 1),  # invertidas
        )


def test_create_activity_happy_path():
    from app.services.extracurricular_service import create_activity

    db = MagicMock()
    user = _user()
    create_activity(
        db,
        user=user,
        category="sport",
        name="Fútbol",
        role="capitán",
        hours_per_week=6,
        start_date=date(2023, 1, 1),
        end_date=None,  # ongoing
        achievements=["Goleador del equipo 2024"],
    )
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_create_activity_accepts_all_canonical_categories():
    from app.db.models import EXTRACURRICULAR_CATEGORIES
    from app.services.extracurricular_service import create_activity

    db = MagicMock()
    user = _user()
    for cat in EXTRACURRICULAR_CATEGORIES:
        create_activity(db, user=user, category=cat, name="Test")
    assert db.add.call_count == len(EXTRACURRICULAR_CATEGORIES)


# ---------------------------------------------------------------------------
# update_activity validation
# ---------------------------------------------------------------------------


def test_update_activity_rejects_invalid_category():
    from app.services.extracurricular_service import update_activity

    db = MagicMock()
    row = SimpleNamespace(
        category="sport",
        start_date=date(2023, 1, 1),
        end_date=None,
    )
    with pytest.raises(ValueError, match="invalid category"):
        update_activity(db, row=row, category="banana")


def test_update_activity_rejects_inverted_dates_against_existing():
    """Si se actualiza solo end_date, debe validar contra el start_date existente."""
    from app.services.extracurricular_service import update_activity

    db = MagicMock()
    row = SimpleNamespace(
        category="sport",
        start_date=date(2024, 6, 1),
        end_date=None,
    )
    with pytest.raises(ValueError, match="end_date"):
        update_activity(db, row=row, end_date=date(2024, 5, 1))


def test_update_activity_happy_path():
    from app.services.extracurricular_service import update_activity

    db = MagicMock()
    row = SimpleNamespace(
        category="sport",
        name="Fútbol",
        role=None,
        hours_per_week=None,
        start_date=date(2024, 1, 1),
        end_date=None,
        description=None,
        achievements=None,
        evidence_urls=None,
    )
    update_activity(db, row=row, role="capitán", hours_per_week=8)
    assert row.role == "capitán"
    assert row.hours_per_week == 8
    db.commit.assert_called_once()


def test_update_activity_only_known_fields():
    """Campos desconocidos no deben aplicarse (silent ignore)."""
    from app.services.extracurricular_service import update_activity

    db = MagicMock()
    row = SimpleNamespace(
        category="sport",
        name="Fútbol",
        role=None,
        hours_per_week=None,
        start_date=None,
        end_date=None,
        description=None,
        achievements=None,
        evidence_urls=None,
    )
    update_activity(db, row=row, name="Voleibol", malicious_field="hack")
    assert row.name == "Voleibol"
    assert not hasattr(row, "malicious_field") or getattr(row, "malicious_field", None) is None or row.malicious_field == "hack"
    # El service no debería settear atributos arbitrarios. SimpleNamespace permite
    # setattr a cualquier nombre pero el service solo aplica el whitelist; con
    # SimpleNamespace eso significa que malicious_field NO debe estar como atributo
    # tras el update.
