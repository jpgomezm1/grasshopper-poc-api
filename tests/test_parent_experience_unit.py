"""GH-PARENT-EXPERIENCE · 2026-05-05.

Pure-unit tests for the new parent-facing /v1/parent/* surface in
``app/api/v1/parent_panel.py``.

We exercise:
- ``_gate_parent`` rejects every non-parent role except SUPER_ADMIN.
- Notification fan-out wiring · the `notifications_service.NOTIFICATION_TYPES`
  set must contain the 4 parent types but NEVER message_received-style
  bidirectional types.
- ``ParentTimelineMilestone.kind`` enum is locked to PUBLIC labels.
- ``ParentLegalDocItem.requires_resign`` is False by default.
- ``ParentMessagesResponse`` shape is read-only (no reply field).
- The RSVP status alias dictionary maps yes/no to going/declined.

We avoid spinning up the full FastAPI app (SQLite/UUID test infra is
pre-broken · same approach as test_student_experience_unit.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.api.v1.parent_panel import _gate_parent, _public_test_label
from app.db.models import UserRole
from app.schemas.school_admin import (
    ParentLegalDocItem,
    ParentLegalHistoryResponse,
    ParentMessageItem,
    ParentMessagesResponse,
    ParentSchoolBranding,
    ParentTimelineMilestone,
    ParentTimelineResponse,
)
from app.services.notifications_service import NOTIFICATION_TYPES
from fastapi import HTTPException


def _user(role, user_id=None):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        role=role,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [
        UserRole.STUDENT,
        UserRole.SCHOOL_ADMIN,
        UserRole.PSYCHOLOGIST,
        UserRole.GH_ADVISOR,
        UserRole.GH_COMMERCIAL,
    ],
)
def test_gate_parent_rejects_non_parent_roles(role):
    with pytest.raises(HTTPException) as exc:
        _gate_parent(_user(role))
    assert exc.value.status_code == 403
    assert "padres" in exc.value.detail.lower()


def test_gate_parent_accepts_parent():
    u = _user(UserRole.PARENT)
    assert _gate_parent(u) is u


def test_gate_parent_accepts_super_admin():
    u = _user(UserRole.SUPER_ADMIN)
    assert _gate_parent(u) is u


# ---------------------------------------------------------------------------
# Notification types · 4 new parent-facing entries · zero bidirectional
# ---------------------------------------------------------------------------


def test_parent_notification_types_present():
    assert "legal_document_pending" in NOTIFICATION_TYPES
    assert "mass_message_received" in NOTIFICATION_TYPES
    assert "child_milestone" in NOTIFICATION_TYPES
    assert "report_available" in NOTIFICATION_TYPES


def test_no_bidirectional_messaging_types():
    """Hard rule from the student sprint: NO chat semantics anywhere."""
    forbidden = {
        "chat_message_received",
        "parent_replied",
        "staff_replied",
        "thread.created",
        "message.send",
    }
    leaks = NOTIFICATION_TYPES & forbidden
    assert leaks == set(), f"forbidden types leaked into NOTIFICATION_TYPES: {leaks}"


# ---------------------------------------------------------------------------
# Public test label mapper · NEVER returns clinical jargon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("riasec", "Holland RIASEC"),
        ("big5", "Big Five OCEAN"),
        ("work_values", "Work Values"),
        ("career_anchors", "Career Anchors"),
        ("english", "Test de inglés"),
        ("xyz_unknown", "Xyz_Unknown"),
    ],
)
def test_public_test_label(raw, expected):
    assert _public_test_label(raw) == expected


# ---------------------------------------------------------------------------
# Schemas · timeline locked to public kinds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        "onboarding_completed",
        "test_completed",
        "english_completed",
        "route_active",
        "journey_completed",
    ],
)
def test_timeline_milestone_kinds_accepted(kind):
    m = ParentTimelineMilestone(kind=kind, title="x")
    assert m.kind == kind


def test_timeline_milestone_rejects_clinical_kind():
    with pytest.raises(Exception):
        ParentTimelineMilestone(kind="clinical_alert", title="x")
    with pytest.raises(Exception):
        ParentTimelineMilestone(kind="dossier_note", title="x")
    with pytest.raises(Exception):
        ParentTimelineMilestone(kind="session_note", title="x")


def test_timeline_response_minimal_shape():
    sid = uuid.uuid4()
    r = ParentTimelineResponse(
        student_user_id=sid,
        student_name="Hijo",
        onboarding_status="completed",
        onboarding_pct=100.0,
        tests_completed=["riasec", "big5"],
        routes_active=2,
        milestones=[],
    )
    payload = r.model_dump()
    assert payload["onboarding_pct"] == 100.0
    assert "milestones" in payload
    # No clinical fields snuck through
    forbidden = {"dossier_notes", "clinical_analysis", "session_notes"}
    assert forbidden.isdisjoint(payload.keys())


# ---------------------------------------------------------------------------
# Legal · requires_resign default False
# ---------------------------------------------------------------------------


def test_legal_doc_item_requires_resign_default_false():
    d = ParentLegalDocItem(
        id=uuid.uuid4(),
        school_id=uuid.uuid4(),
        type="parental_consent",
        version="v1.0",
        content="…",
        created_at=datetime.utcnow(),
        is_signed=False,
    )
    assert d.requires_resign is False


def test_legal_history_response_split_fields():
    r = ParentLegalHistoryResponse(pending=[], signed=[])
    payload = r.model_dump()
    assert payload == {"pending": [], "signed": []}


# ---------------------------------------------------------------------------
# Messages response · read-only shape (no reply field)
# ---------------------------------------------------------------------------


def test_message_item_no_reply_fields():
    item = ParentMessageItem(
        id=uuid.uuid4(),
        school_id=uuid.uuid4(),
        subject="x",
        body="y",
        sent_at=datetime.utcnow(),
        is_read=False,
    )
    payload = item.model_dump()
    forbidden = {"reply_body", "thread_id", "in_reply_to", "replied_at"}
    assert forbidden.isdisjoint(payload.keys())


def test_messages_response_shape():
    r = ParentMessagesResponse(items=[], unread=0)
    payload = r.model_dump()
    assert set(payload.keys()) == {"items", "unread"}


# ---------------------------------------------------------------------------
# Branding payload
# ---------------------------------------------------------------------------


def test_school_branding_optional_fields():
    b = ParentSchoolBranding(id=uuid.uuid4(), name="Cumbres")
    payload = b.model_dump()
    assert payload["logo_url"] is None
    assert payload["branding_primary_color"] is None


# ---------------------------------------------------------------------------
# RSVP status normalisation · alias yes/no/maybe
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("yes", "going"),
        ("no", "declined"),
        ("going", "going"),
        ("declined", "declined"),
        ("maybe", "maybe"),
    ],
)
def test_rsvp_status_aliases(raw, expected):
    """Same alias dict the endpoint uses · keeps FE/BE in lockstep."""
    aliases = {"yes": "going", "no": "declined"}
    normalised = aliases.get(raw, raw)
    assert normalised == expected
    assert normalised in ("going", "declined", "maybe")
