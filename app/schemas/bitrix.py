"""Pydantic schemas · GH-S10 (Bitrix CRM Sync)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BitrixSyncLogRow(BaseModel):
    id: UUID
    entity_type: str
    entity_id: str
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    action: str
    payload: Optional[Dict[str, Any]] = None
    bitrix_response: Optional[Dict[str, Any]] = None
    status: str
    provider: str
    attempts: int
    error_message: Optional[str] = None
    synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BitrixSyncLogList(BaseModel):
    items: List[BitrixSyncLogRow]
    total: int
    page: int
    page_size: int
    total_pages: int


class BitrixStatusResponse(BaseModel):
    provider: str
    is_stub: bool
    webhook_configured: bool
    inbound_enabled: bool
    rate_limit_rps: float
    max_attempts: int
    mapper_version: str
    counts_by_status: Dict[str, int]
    last_event: Optional[Dict[str, Any]] = None
    notify_email_configured: bool


class BitrixManualSyncResponse(BaseModel):
    log: BitrixSyncLogRow
    status: str = Field(
        ..., description="success | stub | failed · short summary of the call"
    )
    bitrix_id: Optional[str] = None


class BitrixInboundAck(BaseModel):
    ok: bool = True
    matched_user_id: Optional[UUID] = None
    normalized_status: Optional[str] = None
