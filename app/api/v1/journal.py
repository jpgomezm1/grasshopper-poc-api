"""Journal API endpoints."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import JournalEntry, JournalEntryType
from app.schemas.journey import (
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalEntryResponse,
)
from app.services.journey_service import get_session

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("/{session_id}", response_model=List[JournalEntryResponse])
def get_journal_entries(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Get all journal entries for a session."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
):
    """Add a manual journal entry."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
):
    """Update a journal entry."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
):
    """Delete a journal entry."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
