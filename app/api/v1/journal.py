"""Journal API endpoints."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import JournalEntry, JournalEntryType, User
from app.schemas.journey import (
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalEntryResponse,
)
from app.services.journey_service import get_session
from app.api.v1.auth import get_current_user
from app.core.access import assert_session_access

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("/{session_id}", response_model=List[JournalEntryResponse])
def get_journal_entries(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all journal entries for a session.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

    entries = (
        db.query(JournalEntry)
        .filter(JournalEntry.session_id == session_id)
        .order_by(JournalEntry.created_at.desc())
        .all()
    )

    return entries


@router.post("/{session_id}", response_model=JournalEntryResponse)
def add_journal_entry(
    session_id: UUID,
    entry_data: JournalEntryCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a manual journal entry.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

    entry = JournalEntry(
        session_id=session_id,
        content=entry_data.content,
        entry_type=JournalEntryType.MANUAL,
        tags=entry_data.tags or [],
        auto_generated=False,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry


@router.put("/{session_id}/{entry_id}", response_model=JournalEntryResponse)
def update_journal_entry(
    session_id: UUID,
    entry_id: UUID,
    entry_data: JournalEntryUpdate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a journal entry.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.id == entry_id, JournalEntry.session_id == session_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry_data.content is not None:
        entry.content = entry_data.content
    if entry_data.tags is not None:
        entry.tags = entry_data.tags

    db.commit()
    db.refresh(entry)

    return entry


@router.delete("/{session_id}/{entry_id}")
def delete_journal_entry(
    session_id: UUID,
    entry_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a journal entry.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.id == entry_id, JournalEntry.session_id == session_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    db.delete(entry)
    db.commit()

    return {"status": "deleted"}
