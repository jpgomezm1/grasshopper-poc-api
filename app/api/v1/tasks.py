"""Tasks router · GH-COMMPROD-B3.

Surfaces:

    GET    /api/v1/tasks?status=&due=today|overdue|week&user_id=
    POST   /api/v1/tasks
    PATCH  /api/v1/tasks/{id}
    DELETE /api/v1/tasks/{id}

Auth: gh_commercial · gh_advisor · super_admin (others 403).
Non-super_admin can only see/edit their own tasks.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import Task, User, UserRole
from app.schemas.tasks import (
    TaskCreate,
    TaskItem,
    TaskListResponse,
    TaskPatch,
)
from app.services import commercial_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _require_team(user: User) -> None:
    """GH-PSY-CLINICAL · 2026-05-05 · psychologist also uses tasks (their own only)."""
    if user.role not in (
        UserRole.GH_COMMERCIAL,
        UserRole.GH_ADVISOR,
        UserRole.PSYCHOLOGIST,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · gh team or psychologist only",
        )


def _resolve_target_user(
    db: DBSession, actor: User, target_user_id: Optional[UUID]
) -> User:
    if target_user_id is None or target_user_id == actor.id:
        return actor
    if actor.role != UserRole.SUPER_ADMIN:
        # Non super_admin can't create tasks for others
        return actor
    target = db.query(User).filter(User.id == target_user_id).first()
    if target is None or target.role not in (
        UserRole.GH_COMMERCIAL,
        UserRole.GH_ADVISOR,
        UserRole.PSYCHOLOGIST,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task assignee must be a gh team member or psychologist",
        )
    return target


@router.get("", response_model=TaskListResponse)
def list_tasks(
    user_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, regex="^(open|done|cancelled)$", alias="status"),
    due: Optional[str] = Query(None, regex="^(today|overdue|week|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.list_tasks(
        db,
        actor=current_user,
        user_id=user_id,
        status=status_filter,
        due=due,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TaskItem, status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    target = _resolve_target_user(db, current_user, body.assigned_to_user_id)
    row = commercial_service.create_task(
        db,
        actor=current_user,
        description=body.description,
        assigned_to=target,
        lead_user_id=body.lead_user_id,
        due_at=body.due_at,
        priority=body.priority,
        request=request,
    )
    return _serialize(db, row)


@router.patch("/{task_id}", response_model=TaskItem)
def patch_task(
    task_id: UUID,
    body: TaskPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if (
        current_user.role != UserRole.SUPER_ADMIN
        and task.assigned_to_user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · not your task",
        )
    row = commercial_service.patch_task(
        db,
        actor=current_user,
        task=task,
        fields=body.model_dump(exclude_unset=True),
        request=request,
    )
    return _serialize(db, row)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if (
        current_user.role != UserRole.SUPER_ADMIN
        and task.assigned_to_user_id != current_user.id
        and task.created_by_user_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="forbidden")
    commercial_service.delete_task(db, actor=current_user, task=task, request=request)


def _serialize(db: DBSession, row: Task) -> dict:
    from datetime import datetime as _dt

    lead = (
        db.query(User).filter(User.id == row.lead_user_id).first()
        if row.lead_user_id
        else None
    )
    assignee = (
        db.query(User).filter(User.id == row.assigned_to_user_id).first()
    )
    now = _dt.utcnow()
    return {
        "id": row.id,
        "assigned_to_user_id": row.assigned_to_user_id,
        "assigned_to_name": assignee.name if assignee else None,
        "lead_user_id": row.lead_user_id,
        "lead_name": lead.name if lead else None,
        "lead_email": lead.email if lead else None,
        "description": row.description,
        "due_at": row.due_at,
        "priority": row.priority,
        "status": row.status,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
        "is_overdue": bool(
            row.due_at and row.status == "open" and row.due_at < now
        ),
    }
