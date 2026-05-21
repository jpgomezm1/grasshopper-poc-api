"""GH-LOCAL-CLIENT-MODULES · M-001 · 2026-05-21.

Unit tests for the AI audit panel:
- ai_audit_service.create_feedback validates rating
- aggregates() math is correct
- to_csv() produces UTF-8 BOM + correct columns

Pure-unit (no DB needed for service-level math), pero create_feedback usa
una DBSession mock.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _user(role_value="gh_advisor"):
    role = SimpleNamespace(value=role_value)
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Test Rater",
        email="rater@example.com",
        role=role,
    )


def _row(rating, type_="program_recommendation", days_ago=0, comment=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        recommendation_type=type_,
        recommendation_ref="ref-123",
        context={"k": "v"},
        rating=rating,
        comment=comment,
        rated_by_user_id=uuid.uuid4(),
        created_at=datetime.utcnow() - timedelta(days=days_ago),
        updated_at=datetime.utcnow() - timedelta(days=days_ago),
    )


# ---------------------------------------------------------------------------
# create_feedback validation
# ---------------------------------------------------------------------------


def test_create_feedback_rejects_invalid_rating():
    from app.services.ai_audit_service import create_feedback

    db = MagicMock()
    user = _user()
    with pytest.raises(ValueError, match="invalid rating"):
        create_feedback(
            db,
            rated_by=user,
            recommendation_type="clinical_analysis",
            rating="awesome",  # invalid
        )


def test_create_feedback_accepts_thumbs_up():
    from app.services.ai_audit_service import create_feedback

    db = MagicMock()
    user = _user()
    create_feedback(
        db,
        rated_by=user,
        recommendation_type="clinical_analysis",
        rating="thumbs_up",
        comment="great",
    )
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_create_feedback_accepts_thumbs_down():
    from app.services.ai_audit_service import create_feedback

    db = MagicMock()
    user = _user()
    create_feedback(
        db,
        rated_by=user,
        recommendation_type="program_recommendation",
        rating="thumbs_down",
    )
    db.add.assert_called_once()


# ---------------------------------------------------------------------------
# aggregates math
# ---------------------------------------------------------------------------


def _mock_db_with_rows(rows):
    """db.query(AiRecommendationFeedback).filter(...).all() returns rows."""
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.all.return_value = rows
    return db


def test_aggregates_empty_returns_zero():
    from app.services.ai_audit_service import aggregates

    db = _mock_db_with_rows([])
    out = aggregates(db, days=30)
    assert out.total_feedback == 0
    assert out.overall_thumbs_up == 0
    assert out.overall_thumbs_down == 0
    assert out.overall_positive_rate_pct == 0.0
    assert out.by_type == []


def test_aggregates_computes_positive_rate():
    from app.services.ai_audit_service import aggregates

    rows = [
        _row("thumbs_up"),
        _row("thumbs_up"),
        _row("thumbs_up"),
        _row("thumbs_down"),
    ]
    db = _mock_db_with_rows(rows)
    out = aggregates(db, days=30)
    assert out.total_feedback == 4
    assert out.overall_thumbs_up == 3
    assert out.overall_thumbs_down == 1
    assert out.overall_positive_rate_pct == 75.0  # 3/4


def test_aggregates_groups_by_type():
    from app.services.ai_audit_service import aggregates

    rows = [
        _row("thumbs_up", "program_recommendation"),
        _row("thumbs_down", "program_recommendation"),
        _row("thumbs_up", "clinical_analysis"),
        _row("thumbs_up", "clinical_analysis"),
    ]
    db = _mock_db_with_rows(rows)
    out = aggregates(db, days=30)
    assert out.total_feedback == 4
    by_type = {t.recommendation_type: t for t in out.by_type}
    assert "program_recommendation" in by_type
    assert by_type["program_recommendation"].total == 2
    assert by_type["program_recommendation"].positive_rate_pct == 50.0
    assert "clinical_analysis" in by_type
    assert by_type["clinical_analysis"].total == 2
    assert by_type["clinical_analysis"].positive_rate_pct == 100.0


# ---------------------------------------------------------------------------
# to_csv output
# ---------------------------------------------------------------------------


def test_to_csv_starts_with_bom_and_header():
    from app.services.ai_audit_service import to_csv

    rows = [_row("thumbs_up", comment="ok")]
    body = to_csv(rows, users={})
    text = body.decode("utf-8")
    # UTF-8 BOM character
    assert text.startswith("﻿")
    assert "created_at,recommendation_type" in text
    assert "thumbs_up" in text


def test_to_csv_escapes_newlines_in_comment():
    from app.services.ai_audit_service import to_csv

    rows = [_row("thumbs_down", comment="line1\nline2\rmore")]
    body = to_csv(rows, users={})
    text = body.decode("utf-8")
    # Newlines should be replaced with spaces so the CSV row stays on one line.
    # The library will quote commas/quotes but newlines need explicit handling.
    assert "line1 line2 more" in text or "line1 line2" in text


def test_to_csv_includes_rater_email_when_available():
    from app.services.ai_audit_service import to_csv

    rows = [_row("thumbs_up")]
    rater_id = rows[0].rated_by_user_id
    rater = SimpleNamespace(
        email="advisor@example.com",
        role=SimpleNamespace(value="gh_advisor"),
    )
    body = to_csv(rows, users={rater_id: rater})
    text = body.decode("utf-8")
    assert "advisor@example.com" in text
    assert "gh_advisor" in text
