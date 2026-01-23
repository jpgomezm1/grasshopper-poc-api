from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class JournalEntryCreate(BaseModel):
    """Schema for creating a journal entry."""
    content: str
    tags: Optional[List[str]] = []


class JournalEntryUpdate(BaseModel):
    """Schema for updating a journal entry."""
    content: Optional[str] = None
    tags: Optional[List[str]] = None


class JournalEntryResponse(BaseModel):
    """Journal entry response."""
    id: UUID
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    content: str
    entry_type: str
    tags: List[str]
    auto_generated: bool

    class Config:
        from_attributes = True


class RouteResponse(BaseModel):
    """Route response."""
    id: UUID
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    key: str
    name: str
    why: str
    what_it_looks_like: str
    next_step: str
    status: str
    is_primary: bool

    class Config:
        from_attributes = True


class RouteStatusUpdate(BaseModel):
    """Schema for updating route status."""
    status: Optional[str] = None  # "active" or "paused"
    is_primary: Optional[bool] = None


class SnapshotCreate(BaseModel):
    """Schema for creating a snapshot."""
    pass  # Generated automatically from session data


class SnapshotResponse(BaseModel):
    """Snapshot response."""
    id: UUID
    session_id: UUID
    created_at: datetime
    profile: dict
    routes: List[dict]
    derived_tags: List[str]

    class Config:
        from_attributes = True


class AdvisorLeadCreate(BaseModel):
    """Schema for creating an advisor lead."""
    name: str
    email: str
    phone: Optional[str] = None


class AdvisorLeadResponse(BaseModel):
    """Advisor lead response."""
    id: UUID
    session_id: UUID
    created_at: datetime
    name: str
    email: str
    phone: Optional[str]
    advisor_brief: Optional[str]

    class Config:
        from_attributes = True
