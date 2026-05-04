"""Pydantic schemas for tasks · GH-COMMPROD-B3."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TaskPriorityLiteral = Literal["low", "normal", "high"]
TaskStatusLiteral = Literal["open", "done", "cancelled"]


class TaskBase(BaseModel):
    description: str = Field(min_length=2, max_length=2000)
    due_at: Optional[datetime] = None
    priority: TaskPriorityLiteral = "normal"
    lead_user_id: Optional[UUID] = None


class TaskCreate(TaskBase):
    assigned_to_user_id: Optional[UUID] = None  # default: current_user


class TaskPatch(BaseModel):
    description: Optional[str] = Field(default=None, min_length=2, max_length=2000)
    due_at: Optional[datetime] = None
    priority: Optional[TaskPriorityLiteral] = None
    status: Optional[TaskStatusLiteral] = None
    lead_user_id: Optional[UUID] = None


class TaskItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assigned_to_user_id: UUID
    assigned_to_name: Optional[str] = None
    lead_user_id: Optional[UUID] = None
    lead_name: Optional[str] = None
    lead_email: Optional[str] = None
    description: str
    due_at: Optional[datetime] = None
    priority: str
    status: str
    created_by_user_id: Optional[UUID] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    is_overdue: bool = False


class TaskListResponse(BaseModel):
    items: List[TaskItem]
    total: int
    page: int
    page_size: int
