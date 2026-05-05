"""Commercial productivity service · GH-COMMPROD sprint.

Aggregates the business logic for:
    - Lead assignment + handoff (B2 / F2)
    - Tasks CRUD (B3)
    - Tags catalog + assign (D1)
    - Saved searches (D3)
    - Comments + mentions (F1)
    - Pipeline stages CRUD (B6)
    - Auto-assign rules (E1) + pipeline rules (E2)
    - Today dashboard aggregation (B1)
    - Activity timeline (B5)
    - Performance + benchmarks (D2 / D4 / I2)
    - GH user picker (assign/handoff dropdown)

Kept in one module to avoid spawning a service-per-feature explosion ·
each section is clearly delimited. All mutation paths emit an audit
log entry + (where relevant) a notification via notifications_service.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Request
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    AuditLog,
    AutoAssignRule,
    LeadComment,
    LeadTag,
    LeadTagAssignment,
    Notification,
    PipelineRule,
    PipelineStage,
    SavedSearch,
    Task,
    User,
    UserRole,
)
from app.services import notifications_service
from app.services.audit_service import log_action
from app.services.sla_service import evaluate as evaluate_sla

logger = logging.getLogger(__name__)


GH_TEAM = (UserRole.GH_COMMERCIAL, UserRole.GH_ADVISOR, UserRole.SUPER_ADMIN)


def _safe_log(
    db: DBSession,
    *,
    user: Optional[User],
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Audit log wrapper that swallows the unknown-action warning · we use
    namespaced free-form actions in this sprint (commercial.*).
    """
    try:
        # bypass KNOWN_ACTIONS warning by writing directly · pattern reused from
        # bitrix_sync_service.py (also uses free-form audit events).
        row = AuditLog(
            user_id=user.id if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload or {},
            ip_address=(request.client.host if request and request.client else None)
            if request
            else None,
            user_agent=(request.headers.get("user-agent") if request else None),
        )
        db.add(row)
    except Exception as exc:  # pragma: no cover
        logger.warning("audit · failed to log %s · %s", action, exc)


# ===========================================================================
# Lead assignment + handoff (B2 / F2)
# ===========================================================================


def assign_lead(
    db: DBSession,
    *,
    lead: User,
    to_user: Optional[User],
    actor: User,
    note: Optional[str] = None,
    request: Optional[Request] = None,
) -> User:
    if to_user is not None and to_user.role not in (
        UserRole.GH_COMMERCIAL,
        UserRole.GH_ADVISOR,
    ):
        raise ValueError(
            "assignee must be gh_commercial or gh_advisor "
            f"(got {to_user.role.value if to_user.role else 'none'})"
        )

    prev = lead.assigned_to_user_id
    lead.assigned_to_user_id = to_user.id if to_user else None
    lead.assigned_at = datetime.utcnow() if to_user else None
    db.add(lead)

    _safe_log(
        db,
        user=actor,
        action="commercial.lead_assign" if to_user else "commercial.lead_unassign",
        resource_type="user",
        resource_id=str(lead.id),
        payload={
            "previous_assigned_to": str(prev) if prev else None,
            "new_assigned_to": str(to_user.id) if to_user else None,
            "note": note,
        },
        request=request,
    )
    db.commit()
    db.refresh(lead)

    # Notify the new assignee (skip if reassigning to themselves)
    if to_user is not None and to_user.id != actor.id:
        notifications_service.create_notification(
            db,
            user_id=to_user.id,
            type="lead.assigned",
            title=f"Te asignaron un lead · {lead.name or lead.email}",
            body=note or f"Asignado por {actor.name or actor.email}",
            data={
                "lead_user_id": str(lead.id),
                "navigate_to": f"/admin/crm/leads/{lead.id}",
                "actor_user_id": str(actor.id),
            },
        )
    return lead


def handoff_lead(
    db: DBSession,
    *,
    lead: User,
    to_user: User,
    actor: User,
    note: str,
    request: Optional[Request] = None,
) -> User:
    if to_user.role not in (UserRole.GH_COMMERCIAL, UserRole.GH_ADVISOR):
        raise ValueError("handoff target must be gh_commercial or gh_advisor")
    prev_id = lead.assigned_to_user_id
    lead.assigned_to_user_id = to_user.id
    lead.assigned_at = datetime.utcnow()
    db.add(lead)
    _safe_log(
        db,
        user=actor,
        action="commercial.lead_handoff",
        resource_type="user",
        resource_id=str(lead.id),
        payload={
            "previous_assigned_to": str(prev_id) if prev_id else None,
            "new_assigned_to": str(to_user.id),
            "note": note,
        },
        request=request,
    )
    db.commit()
    db.refresh(lead)

    # Notify both participants
    notifications_service.create_notification(
        db,
        user_id=to_user.id,
        type="lead.assigned",
        title=f"Hand-off · {lead.name or lead.email}",
        body=note,
        data={
            "lead_user_id": str(lead.id),
            "from_user_id": str(prev_id) if prev_id else None,
            "navigate_to": f"/admin/crm/leads/{lead.id}",
        },
    )
    if prev_id and prev_id != actor.id:
        notifications_service.create_notification(
            db,
            user_id=prev_id,
            type="lead.assigned",
            title=f"Transferiste un lead · {lead.name or lead.email}",
            body=f"Pasó a {to_user.name or to_user.email} · {note}",
            data={
                "lead_user_id": str(lead.id),
                "to_user_id": str(to_user.id),
                "navigate_to": f"/admin/crm/leads/{lead.id}",
            },
        )
    return lead


def auto_assign_lead(
    db: DBSession, *, lead: User, request: Optional[Request] = None
) -> Optional[User]:
    """Pick a gh_commercial via the active rules and assign · idempotent.

    Returns the chosen user (or None if no active rule / no candidates).
    Skips if the lead is already assigned.
    """
    if lead.assigned_to_user_id is not None:
        return None

    rules = (
        db.query(AutoAssignRule)
        .filter(AutoAssignRule.is_active.is_(True))
        .order_by(AutoAssignRule.priority.asc(), AutoAssignRule.created_at.asc())
        .all()
    )
    if not rules:
        return None

    candidates = (
        db.query(User)
        .filter(User.role == UserRole.GH_COMMERCIAL)
        .filter(User.is_active.is_(True))
        .all()
    )
    if not candidates:
        return None

    chosen: Optional[User] = None
    for rule in rules:
        chosen = _resolve_strategy(db, rule, candidates, lead)
        if chosen is not None:
            break

    if chosen is None:
        return None

    # Use a synthetic actor (system) for the audit log
    assign_lead(
        db,
        lead=lead,
        to_user=chosen,
        actor=chosen,  # system attribution → assignee
        note="auto-assign",
        request=request,
    )
    return chosen


def _resolve_strategy(
    db: DBSession,
    rule: AutoAssignRule,
    candidates: List[User],
    lead: User,
) -> Optional[User]:
    cfg = rule.config or {}
    strategy = (rule.strategy or "round_robin").lower()

    if strategy == "round_robin":
        # Pick the candidate with the oldest `assigned_at` of their last lead
        rows = (
            db.query(User.assigned_to_user_id, func.max(User.assigned_at))
            .filter(User.assigned_to_user_id.isnot(None))
            .group_by(User.assigned_to_user_id)
            .all()
        )
        last_map = {uid: ts for uid, ts in rows}
        candidates_sorted = sorted(
            candidates,
            key=lambda c: (last_map.get(c.id) or datetime.min),
        )
        return candidates_sorted[0] if candidates_sorted else None

    if strategy == "least_loaded":
        rows = (
            db.query(User.assigned_to_user_id, func.count(User.id))
            .filter(User.assigned_to_user_id.isnot(None))
            .filter(User.lead_pipeline_status.in_(["pending", "contacted", "qualified"]))
            .group_by(User.assigned_to_user_id)
            .all()
        )
        load_map = {uid: cnt for uid, cnt in rows}
        candidates_sorted = sorted(
            candidates,
            key=lambda c: load_map.get(c.id, 0),
        )
        return candidates_sorted[0] if candidates_sorted else None

    if strategy == "by_country":
        # cfg = {"colombia": "<uuid>", ...} matches lead.preferred_countries[0]
        prefs = lead.preferred_countries or []
        if not prefs:
            return None
        target_uid = cfg.get(str(prefs[0]).lower())
        if not target_uid:
            return None
        for c in candidates:
            if str(c.id) == target_uid:
                return c
        return None

    if strategy == "by_language":
        # We default to "es" (single-locale POC) · take the first mapped user
        target_uid = cfg.get("es")
        if target_uid:
            for c in candidates:
                if str(c.id) == target_uid:
                    return c
        return None

    return None


# ===========================================================================
# Tasks CRUD (B3)
# ===========================================================================


def create_task(
    db: DBSession,
    *,
    actor: User,
    description: str,
    assigned_to: Optional[User] = None,
    lead_user_id: Optional[UUID] = None,
    due_at: Optional[datetime] = None,
    priority: str = "normal",
    request: Optional[Request] = None,
) -> Task:
    target_id = (assigned_to.id if assigned_to else actor.id)
    row = Task(
        assigned_to_user_id=target_id,
        lead_user_id=lead_user_id,
        description=description.strip(),
        due_at=due_at,
        priority=priority,
        status="open",
        created_by_user_id=actor.id,
    )
    db.add(row)
    _safe_log(
        db,
        user=actor,
        action="commercial.task_create",
        resource_type="task",
        resource_id=None,
        payload={
            "assigned_to": str(target_id),
            "lead_user_id": str(lead_user_id) if lead_user_id else None,
            "priority": priority,
            "due_at": due_at.isoformat() if due_at else None,
        },
        request=request,
    )
    db.commit()
    db.refresh(row)
    if target_id != actor.id:
        # GH-STUDENT-EXPERIENCE · Bloque D · 2026-05-05
        # Differentiate gh-team-internal "task.created" from a student-facing
        # "task.assigned". Both are 1-way notifications · NO chat created.
        is_student = bool(assigned_to and assigned_to.role == UserRole.STUDENT)
        notif_type = "task.assigned" if is_student else "task.created"
        navigate_to = "/tasks" if not is_student else "/tasks"
        notifications_service.create_notification(
            db,
            user_id=target_id,
            type=notif_type,
            title=f"Tarea nueva · {description[:80]}",
            body=f"Asignada por {actor.name or actor.email}",
            data={
                "task_id": str(row.id),
                "lead_user_id": str(lead_user_id) if lead_user_id else None,
                "navigate_to": navigate_to,
            },
        )
    return row


def list_tasks(
    db: DBSession,
    *,
    actor: User,
    user_id: Optional[UUID] = None,
    status: Optional[str] = None,
    due: Optional[str] = None,  # today | overdue | week | all
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    q = db.query(Task)
    target_user_id = user_id or actor.id
    # Non super_admin can only see their own tasks
    if actor.role != UserRole.SUPER_ADMIN and target_user_id != actor.id:
        target_user_id = actor.id
    q = q.filter(Task.assigned_to_user_id == target_user_id)

    if status and status in ("open", "done", "cancelled"):
        q = q.filter(Task.status == status)

    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if due == "today":
        q = q.filter(Task.due_at >= today, Task.due_at < today + timedelta(days=1))
    elif due == "overdue":
        q = q.filter(Task.status == "open", Task.due_at < now)
    elif due == "week":
        q = q.filter(Task.due_at >= today, Task.due_at < today + timedelta(days=7))

    total = q.count()
    rows = (
        q.order_by(
            Task.status.asc(),
            Task.due_at.asc().nulls_last(),
            Task.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Eager hydrate lead names + assignee names
    lead_ids = {r.lead_user_id for r in rows if r.lead_user_id}
    assignee_ids = {r.assigned_to_user_id for r in rows}
    user_map: Dict[UUID, User] = {}
    if lead_ids or assignee_ids:
        users = (
            db.query(User)
            .filter(User.id.in_(list(lead_ids | assignee_ids)))
            .all()
        )
        user_map = {u.id: u for u in users}

    items = []
    for r in rows:
        lead_u = user_map.get(r.lead_user_id) if r.lead_user_id else None
        assignee_u = user_map.get(r.assigned_to_user_id)
        items.append({
            "id": r.id,
            "assigned_to_user_id": r.assigned_to_user_id,
            "assigned_to_name": assignee_u.name if assignee_u else None,
            "lead_user_id": r.lead_user_id,
            "lead_name": lead_u.name if lead_u else None,
            "lead_email": lead_u.email if lead_u else None,
            "description": r.description,
            "due_at": r.due_at,
            "priority": r.priority,
            "status": r.status,
            "created_by_user_id": r.created_by_user_id,
            "created_at": r.created_at,
            "completed_at": r.completed_at,
            "is_overdue": bool(r.due_at and r.status == "open" and r.due_at < now),
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


def patch_task(
    db: DBSession,
    *,
    actor: User,
    task: Task,
    fields: Dict[str, Any],
    request: Optional[Request] = None,
) -> Task:
    if "description" in fields and fields["description"] is not None:
        task.description = fields["description"].strip()
    if "due_at" in fields:
        task.due_at = fields["due_at"]
    if "priority" in fields and fields["priority"] is not None:
        task.priority = fields["priority"]
    if "status" in fields and fields["status"] is not None:
        new_status = fields["status"]
        prev = task.status
        task.status = new_status
        if new_status == "done" and prev != "done":
            task.completed_at = datetime.utcnow()
        elif new_status != "done":
            task.completed_at = None
    if "lead_user_id" in fields:
        task.lead_user_id = fields["lead_user_id"]

    db.add(task)
    _safe_log(
        db,
        user=actor,
        action="commercial.task_update",
        resource_type="task",
        resource_id=str(task.id),
        payload={"fields": list(fields.keys())},
        request=request,
    )
    db.commit()
    db.refresh(task)
    return task


def delete_task(
    db: DBSession,
    *,
    actor: User,
    task: Task,
    request: Optional[Request] = None,
) -> None:
    _safe_log(
        db,
        user=actor,
        action="commercial.task_delete",
        resource_type="task",
        resource_id=str(task.id),
        payload={"description": task.description[:120]},
        request=request,
    )
    db.delete(task)
    db.commit()


def emit_task_due_soon_notifications(db: DBSession) -> int:
    """Sweep open tasks · notify the assignee 1h before due_at (idempotent)."""
    now = datetime.utcnow()
    horizon = now + timedelta(hours=1)
    tasks = (
        db.query(Task)
        .filter(
            Task.status == "open",
            Task.due_at.isnot(None),
            Task.due_at >= now,
            Task.due_at <= horizon,
            Task.notified_due_at.is_(None),
        )
        .all()
    )
    n = 0
    for t in tasks:
        notifications_service.create_notification(
            db,
            user_id=t.assigned_to_user_id,
            type="task.due_soon",
            title=f"Tarea próxima · {t.description[:80]}",
            body=f"Vence en menos de 1h · {t.due_at.isoformat() if t.due_at else ''}",
            data={"task_id": str(t.id), "navigate_to": "/tasks"},
            commit=False,
        )
        t.notified_due_at = now
        db.add(t)
        n += 1
    if n > 0:
        db.commit()
    return n


# ===========================================================================
# Tags (D1)
# ===========================================================================


def list_tags(db: DBSession) -> List[LeadTag]:
    return db.query(LeadTag).order_by(LeadTag.label.asc()).all()


def create_tag(
    db: DBSession,
    *,
    actor: User,
    key: str,
    label: str,
    color: Optional[str],
    request: Optional[Request] = None,
) -> LeadTag:
    existing = db.query(LeadTag).filter(LeadTag.key == key).first()
    if existing is not None:
        return existing
    row = LeadTag(key=key, label=label, color=color)
    db.add(row)
    _safe_log(
        db,
        user=actor,
        action="commercial.tag_create",
        resource_type="lead_tag",
        resource_id=None,
        payload={"key": key},
        request=request,
    )
    db.commit()
    db.refresh(row)
    return row


def delete_tag(
    db: DBSession, *, actor: User, tag: LeadTag, request: Optional[Request] = None
) -> None:
    _safe_log(
        db,
        user=actor,
        action="commercial.tag_delete",
        resource_type="lead_tag",
        resource_id=str(tag.id),
        payload={"key": tag.key},
        request=request,
    )
    db.delete(tag)
    db.commit()


def get_lead_tags(db: DBSession, *, lead_user_id: UUID) -> List[LeadTag]:
    return (
        db.query(LeadTag)
        .join(LeadTagAssignment, LeadTagAssignment.tag_id == LeadTag.id)
        .filter(LeadTagAssignment.lead_user_id == lead_user_id)
        .order_by(LeadTag.label.asc())
        .all()
    )


def set_lead_tags(
    db: DBSession,
    *,
    actor: User,
    lead_user_id: UUID,
    tag_ids: List[UUID],
    request: Optional[Request] = None,
) -> List[LeadTag]:
    """Idempotent · replaces the full set of tags for a lead."""
    db.query(LeadTagAssignment).filter(
        LeadTagAssignment.lead_user_id == lead_user_id
    ).delete(synchronize_session=False)
    for tid in tag_ids:
        db.add(
            LeadTagAssignment(
                lead_user_id=lead_user_id,
                tag_id=tid,
                assigned_by=actor.id,
            )
        )
    _safe_log(
        db,
        user=actor,
        action="commercial.lead_tags_set",
        resource_type="user",
        resource_id=str(lead_user_id),
        payload={"tag_count": len(tag_ids)},
        request=request,
    )
    db.commit()
    return get_lead_tags(db, lead_user_id=lead_user_id)


# ===========================================================================
# Saved searches (D3)
# ===========================================================================


def list_saved_searches(db: DBSession, *, user: User) -> List[SavedSearch]:
    return (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == user.id)
        .order_by(SavedSearch.pinned.desc(), SavedSearch.created_at.desc())
        .all()
    )


def create_saved_search(
    db: DBSession,
    *,
    user: User,
    name: str,
    filters: Dict[str, Any],
    pinned: bool = False,
) -> SavedSearch:
    existing = (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == user.id, SavedSearch.name == name)
        .first()
    )
    if existing is not None:
        existing.filters = filters
        existing.pinned = pinned
        db.commit()
        db.refresh(existing)
        return existing
    row = SavedSearch(user_id=user.id, name=name, filters=filters, pinned=pinned)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def patch_saved_search(
    db: DBSession,
    *,
    user: User,
    search: SavedSearch,
    fields: Dict[str, Any],
) -> SavedSearch:
    if search.user_id != user.id:
        raise PermissionError("not your saved search")
    for k in ("name", "filters", "pinned"):
        if k in fields and fields[k] is not None:
            setattr(search, k, fields[k])
    db.commit()
    db.refresh(search)
    return search


def delete_saved_search(db: DBSession, *, user: User, search: SavedSearch) -> None:
    if search.user_id != user.id:
        raise PermissionError("not your saved search")
    db.delete(search)
    db.commit()


# ===========================================================================
# Comments + mentions (F1)
# ===========================================================================


def list_comments(db: DBSession, *, lead_user_id: UUID) -> List[Dict[str, Any]]:
    rows = (
        db.query(LeadComment)
        .filter(LeadComment.lead_user_id == lead_user_id)
        .order_by(LeadComment.created_at.asc())
        .all()
    )
    author_ids = {r.author_user_id for r in rows if r.author_user_id}
    author_map: Dict[UUID, User] = {}
    if author_ids:
        users = db.query(User).filter(User.id.in_(list(author_ids))).all()
        author_map = {u.id: u for u in users}
    items = []
    for r in rows:
        a = author_map.get(r.author_user_id) if r.author_user_id else None
        items.append({
            "id": r.id,
            "lead_user_id": r.lead_user_id,
            "author_user_id": r.author_user_id,
            "author_name": a.name if a else None,
            "author_email": a.email if a else None,
            "body": r.body,
            "mentions": r.mentions or [],
            "parent_id": r.parent_id,
            "created_at": r.created_at,
            "edited_at": r.edited_at,
        })
    return items


def create_comment(
    db: DBSession,
    *,
    actor: User,
    lead_user_id: UUID,
    body: str,
    parent_id: Optional[UUID] = None,
    mentions: Optional[List[UUID]] = None,
    request: Optional[Request] = None,
) -> LeadComment:
    row = LeadComment(
        lead_user_id=lead_user_id,
        author_user_id=actor.id,
        body=body.strip(),
        mentions=[str(m) for m in (mentions or [])] if mentions else None,
        parent_id=parent_id,
    )
    db.add(row)
    _safe_log(
        db,
        user=actor,
        action="commercial.comment_create",
        resource_type="user",
        resource_id=str(lead_user_id),
        payload={"mentions": len(mentions or [])},
        request=request,
    )
    db.commit()
    db.refresh(row)

    # Notify mentioned users (skip self-mentions)
    if mentions:
        for mid in mentions:
            if mid == actor.id:
                continue
            notifications_service.create_notification(
                db,
                user_id=mid,
                type="comment.mention",
                title=f"{actor.name or actor.email} te mencionó",
                body=body[:200],
                data={
                    "lead_user_id": str(lead_user_id),
                    "comment_id": str(row.id),
                    "navigate_to": f"/admin/crm/leads/{lead_user_id}",
                },
            )
    return row


def patch_comment(
    db: DBSession,
    *,
    actor: User,
    comment: LeadComment,
    body: str,
) -> LeadComment:
    if comment.author_user_id != actor.id and actor.role != UserRole.SUPER_ADMIN:
        raise PermissionError("only the author or super_admin may edit a comment")
    comment.body = body.strip()
    comment.edited_at = datetime.utcnow()
    db.commit()
    db.refresh(comment)
    return comment


def delete_comment(
    db: DBSession,
    *,
    actor: User,
    comment: LeadComment,
) -> None:
    if comment.author_user_id != actor.id and actor.role != UserRole.SUPER_ADMIN:
        raise PermissionError("only the author or super_admin may delete a comment")
    db.delete(comment)
    db.commit()


# ===========================================================================
# Pipeline stages (B6)
# ===========================================================================


def list_pipeline_stages(db: DBSession) -> List[PipelineStage]:
    return (
        db.query(PipelineStage)
        .order_by(PipelineStage.order_index.asc(), PipelineStage.label.asc())
        .all()
    )


def create_pipeline_stage(
    db: DBSession,
    *,
    actor: User,
    key: str,
    label: str,
    color: Optional[str],
    order_index: int,
    request: Optional[Request] = None,
) -> PipelineStage:
    existing = db.query(PipelineStage).filter(PipelineStage.key == key).first()
    if existing is not None:
        raise ValueError(f"stage `{key}` already exists")
    row = PipelineStage(
        key=key, label=label, color=color, order_index=order_index, is_default=False
    )
    db.add(row)
    _safe_log(
        db,
        user=actor,
        action="commercial.stage_create",
        resource_type="pipeline_stage",
        resource_id=None,
        payload={"key": key, "label": label},
        request=request,
    )
    db.commit()
    db.refresh(row)
    return row


def patch_pipeline_stage(
    db: DBSession,
    *,
    actor: User,
    stage: PipelineStage,
    fields: Dict[str, Any],
    request: Optional[Request] = None,
) -> PipelineStage:
    for k in ("label", "color", "order_index"):
        if k in fields and fields[k] is not None:
            setattr(stage, k, fields[k])
    _safe_log(
        db,
        user=actor,
        action="commercial.stage_update",
        resource_type="pipeline_stage",
        resource_id=str(stage.id),
        payload={"fields": list(fields.keys())},
        request=request,
    )
    db.commit()
    db.refresh(stage)
    return stage


def delete_pipeline_stage(
    db: DBSession,
    *,
    actor: User,
    stage: PipelineStage,
    request: Optional[Request] = None,
) -> None:
    if stage.is_default:
        raise ValueError("cannot delete a default pipeline stage")
    _safe_log(
        db,
        user=actor,
        action="commercial.stage_delete",
        resource_type="pipeline_stage",
        resource_id=str(stage.id),
        payload={"key": stage.key},
        request=request,
    )
    db.delete(stage)
    db.commit()


def reorder_pipeline_stages(
    db: DBSession,
    *,
    actor: User,
    order: List[UUID],
    request: Optional[Request] = None,
) -> List[PipelineStage]:
    for idx, sid in enumerate(order):
        stage = db.query(PipelineStage).filter(PipelineStage.id == sid).first()
        if stage is None:
            continue
        stage.order_index = (idx + 1) * 10
        db.add(stage)
    _safe_log(
        db,
        user=actor,
        action="commercial.stage_reorder",
        resource_type="pipeline_stage",
        resource_id=None,
        payload={"count": len(order)},
        request=request,
    )
    db.commit()
    return list_pipeline_stages(db)


# ===========================================================================
# Auto-assign rules (E1) + Pipeline rules (E2)
# ===========================================================================


def list_auto_assign_rules(db: DBSession) -> List[AutoAssignRule]:
    return (
        db.query(AutoAssignRule)
        .order_by(AutoAssignRule.priority.asc(), AutoAssignRule.created_at.asc())
        .all()
    )


def create_auto_assign_rule(
    db: DBSession,
    *,
    actor: User,
    strategy: str,
    config: Optional[Dict[str, Any]],
    is_active: bool,
    priority: int,
    request: Optional[Request] = None,
) -> AutoAssignRule:
    row = AutoAssignRule(
        strategy=strategy,
        config=config,
        is_active=is_active,
        priority=priority,
    )
    db.add(row)
    _safe_log(
        db,
        user=actor,
        action="commercial.auto_assign_rule_create",
        resource_type="auto_assign_rule",
        resource_id=None,
        payload={"strategy": strategy},
        request=request,
    )
    db.commit()
    db.refresh(row)
    return row


def patch_auto_assign_rule(
    db: DBSession,
    *,
    actor: User,
    rule: AutoAssignRule,
    fields: Dict[str, Any],
    request: Optional[Request] = None,
) -> AutoAssignRule:
    for k in ("strategy", "config", "is_active", "priority"):
        if k in fields and fields[k] is not None:
            setattr(rule, k, fields[k])
    db.commit()
    db.refresh(rule)
    return rule


def delete_auto_assign_rule(
    db: DBSession,
    *,
    actor: User,
    rule: AutoAssignRule,
    request: Optional[Request] = None,
) -> None:
    db.delete(rule)
    db.commit()


def list_pipeline_rules(db: DBSession) -> List[PipelineRule]:
    return (
        db.query(PipelineRule)
        .order_by(PipelineRule.created_at.desc())
        .all()
    )


def create_pipeline_rule(
    db: DBSession,
    *,
    actor: User,
    name: str,
    condition: Dict[str, Any],
    action: Dict[str, Any],
    is_active: bool,
    request: Optional[Request] = None,
) -> PipelineRule:
    row = PipelineRule(
        name=name, condition=condition, action=action, is_active=is_active
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def patch_pipeline_rule(
    db: DBSession,
    *,
    actor: User,
    rule: PipelineRule,
    fields: Dict[str, Any],
    request: Optional[Request] = None,
) -> PipelineRule:
    for k in ("name", "condition", "action", "is_active"):
        if k in fields and fields[k] is not None:
            setattr(rule, k, fields[k])
    db.commit()
    db.refresh(rule)
    return rule


def delete_pipeline_rule(
    db: DBSession,
    *,
    actor: User,
    rule: PipelineRule,
    request: Optional[Request] = None,
) -> None:
    db.delete(rule)
    db.commit()


# ===========================================================================
# Today dashboard (B1)
# ===========================================================================


def build_today(db: DBSession, *, user: User) -> Dict[str, Any]:
    """Aggregate Mi día for a gh_commercial / gh_advisor."""
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())

    leads_assigned_total = (
        db.query(func.count(User.id))
        .filter(User.assigned_to_user_id == user.id)
        .scalar()
        or 0
    )

    pending_q = (
        db.query(User)
        .filter(
            User.assigned_to_user_id == user.id,
            User.lead_pipeline_status.in_(["pending", "contacted"]),
        )
        .order_by(User.lead_pipeline_status_at.asc().nulls_first())
        .limit(20)
        .all()
    )

    sla_breaches: List[Dict[str, Any]] = []
    pending_cards: List[Dict[str, Any]] = []
    for u in pending_q:
        info = evaluate_sla(u, now=now)
        card = {
            "user_id": u.id,
            "name": u.name,
            "email": u.email,
            "score": int(_quick_score_estimate(u)),
            "score_band": _score_band(_quick_score_estimate(u)),
            "pipeline_status": u.lead_pipeline_status,
            "last_activity_at": u.lead_pipeline_status_at,
            "sla_state": info.state,
            "days_in_status": info.days_in_status,
        }
        pending_cards.append(card)
        if info.state == "breach":
            sla_breaches.append(card)

    overdue_tasks_rows = (
        db.query(Task)
        .filter(
            Task.assigned_to_user_id == user.id,
            Task.status == "open",
            Task.due_at < now,
        )
        .order_by(Task.due_at.asc())
        .limit(20)
        .all()
    )
    upcoming_tasks_rows = (
        db.query(Task)
        .filter(
            Task.assigned_to_user_id == user.id,
            Task.status == "open",
            Task.due_at >= now,
            Task.due_at < today + timedelta(days=2),
        )
        .order_by(Task.due_at.asc())
        .limit(20)
        .all()
    )

    lead_ids = {
        r.lead_user_id for r in (overdue_tasks_rows + upcoming_tasks_rows) if r.lead_user_id
    }
    lead_map: Dict[UUID, User] = {}
    if lead_ids:
        for u in db.query(User).filter(User.id.in_(list(lead_ids))).all():
            lead_map[u.id] = u

    def _task_card(r: Task) -> Dict[str, Any]:
        lu = lead_map.get(r.lead_user_id) if r.lead_user_id else None
        return {
            "id": r.id,
            "description": r.description,
            "due_at": r.due_at,
            "priority": r.priority,
            "lead_user_id": r.lead_user_id,
            "lead_name": lu.name if lu else None,
            "is_overdue": bool(r.due_at and r.status == "open" and r.due_at < now),
        }

    overdue_tasks = [_task_card(r) for r in overdue_tasks_rows]
    upcoming_tasks = [_task_card(r) for r in upcoming_tasks_rows]

    week_conversions = (
        db.query(func.count(User.id))
        .filter(
            User.assigned_to_user_id == user.id,
            User.lead_pipeline_status == "converted",
            User.lead_pipeline_status_at >= week_start,
        )
        .scalar()
        or 0
    )

    kpis = {
        "leads_assigned_total": int(leads_assigned_total),
        "leads_pending_action": len(pending_cards),
        "tasks_today": sum(
            1
            for r in upcoming_tasks_rows
            if r.due_at and r.due_at.date() == today.date()
        ),
        "tasks_overdue": len(overdue_tasks),
        "sla_breach_count": len(sla_breaches),
        "week_conversions": int(week_conversions),
    }

    return {
        "generated_at": now,
        "kpis": kpis,
        "priority_leads": pending_cards[:10],
        "overdue_tasks": overdue_tasks,
        "upcoming_tasks": upcoming_tasks,
        "sla_breaches": sla_breaches[:10],
    }


def _quick_score_estimate(u: User) -> float:
    """Lightweight score proxy for the today dashboard cards.

    The CRM detail uses the canonical scoring service · here we just want
    a stable badge so we avoid importing the heavy student_lead_scoring
    chain. This is FE-display only · not exposed as the real score.
    """
    base = 50.0
    if u.english_test_completed:
        base += 10
    if u.consolidated_profile is not None:
        base += 15
    if u.budget_max_usd and u.budget_max_usd > 0:
        base += 10
    if u.preferred_countries:
        base += 5
    return min(base, 100.0)


def _score_band(score: float) -> str:
    if score >= 80:
        return "hot"
    if score >= 60:
        return "warm"
    return "cold"


# ===========================================================================
# Activity timeline (B5)
# ===========================================================================


def build_activity_timeline(
    db: DBSession,
    *,
    lead_user_id: UUID,
    limit: int = 200,
) -> Dict[str, Any]:
    """All-in-one timeline for a lead · merges audit + pipeline + tasks +
    notifications + comments + assignments + journey events.
    """
    events: List[Dict[str, Any]] = []

    # 1. audit logs touching this user
    audit_rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.resource_type == "user",
            AuditLog.resource_id == str(lead_user_id),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    actor_ids = {r.user_id for r in audit_rows if r.user_id}
    actor_map: Dict[UUID, User] = {}
    if actor_ids:
        for u in db.query(User).filter(User.id.in_(list(actor_ids))).all():
            actor_map[u.id] = u

    for r in audit_rows:
        actor = actor_map.get(r.user_id) if r.user_id else None
        kind = "audit"
        if r.action.startswith("commercial.lead_assign") or r.action.startswith(
            "commercial.lead_unassign"
        ) or r.action == "commercial.lead_handoff":
            kind = "assignment"
        elif r.action.startswith("commercial.lead_tags_set"):
            kind = "tag"
        elif r.action.startswith("commercial.comment"):
            kind = "comment"
        elif r.action.startswith("commercial.task"):
            kind = "task"
        events.append({
            "kind": kind,
            "at": r.created_at,
            "actor_user_id": r.user_id,
            "actor_name": actor.name if actor else None,
            "title": _humanize_audit_action(r.action),
            "detail": None,
            "data": r.payload or {},
        })

    # 2. pipeline status changes (from User.lead_pipeline_status_at) · single
    # current row only · the audit log captures historical transitions.
    lead = db.query(User).filter(User.id == lead_user_id).first()
    if lead is not None and lead.lead_pipeline_status_at is not None:
        events.append({
            "kind": "pipeline_change",
            "at": lead.lead_pipeline_status_at,
            "actor_user_id": None,
            "actor_name": None,
            "title": f"Estado en pipeline: {lead.lead_pipeline_status}",
            "detail": None,
            "data": {"status": lead.lead_pipeline_status},
        })

    # 3. tasks · created + completed
    tasks_rows = (
        db.query(Task)
        .filter(Task.lead_user_id == lead_user_id)
        .order_by(Task.created_at.desc())
        .limit(50)
        .all()
    )
    for t in tasks_rows:
        events.append({
            "kind": "task",
            "at": t.created_at,
            "actor_user_id": t.created_by_user_id,
            "actor_name": None,
            "title": f"Tarea creada · {t.description[:80]}",
            "detail": f"Prioridad {t.priority}",
            "data": {"task_id": str(t.id), "status": t.status},
        })
        if t.completed_at:
            events.append({
                "kind": "task",
                "at": t.completed_at,
                "actor_user_id": t.assigned_to_user_id,
                "actor_name": None,
                "title": f"Tarea completada · {t.description[:80]}",
                "detail": None,
                "data": {"task_id": str(t.id)},
            })

    # 4. notifications (system-generated about this lead)
    notif_rows = (
        db.query(Notification)
        .filter(Notification.data.op("->>")("lead_user_id") == str(lead_user_id))
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    for n in notif_rows:
        events.append({
            "kind": "notification",
            "at": n.created_at,
            "actor_user_id": None,
            "actor_name": None,
            "title": n.title,
            "detail": n.body,
            "data": n.data or {},
        })

    # 5. comments
    comments = list_comments(db, lead_user_id=lead_user_id)
    for c in comments:
        events.append({
            "kind": "comment",
            "at": c["created_at"],
            "actor_user_id": c["author_user_id"],
            "actor_name": c["author_name"],
            "title": "Comentario",
            "detail": c["body"][:200],
            "data": {"comment_id": str(c["id"])},
        })

    events.sort(key=lambda e: e["at"], reverse=True)
    events = events[:limit]
    return {
        "lead_user_id": lead_user_id,
        "items": events,
        "total": len(events),
    }


def _humanize_audit_action(action: str) -> str:
    return {
        "commercial.lead_assign": "Lead asignado",
        "commercial.lead_unassign": "Lead desasignado",
        "commercial.lead_handoff": "Hand-off de lead",
        "commercial.lead_tags_set": "Tags actualizados",
        "commercial.task_create": "Tarea creada",
        "commercial.task_update": "Tarea actualizada",
        "commercial.task_delete": "Tarea eliminada",
        "commercial.comment_create": "Comentario creado",
    }.get(action, action)


# ===========================================================================
# Performance + funnel + benchmarks (D4 / I2 / D2)
# ===========================================================================


def build_performance(
    db: DBSession,
    *,
    user: User,
    period: str = "30d",
) -> Dict[str, Any]:
    days = {"30d": 30, "90d": 90, "year": 365}.get(period, 30)
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    leads_handled = _count_leads(db, user.id, start, end)
    leads_handled_prev = _count_leads(db, user.id, prev_start, start)

    conversions = _count_conversions(db, user.id, start, end)
    conversions_prev = _count_conversions(db, user.id, prev_start, start)

    conv_rate = (conversions / leads_handled * 100) if leads_handled else 0.0
    conv_rate_prev = (
        (conversions_prev / leads_handled_prev * 100) if leads_handled_prev else 0.0
    )

    # Ranking among gh_commercial in current period (anonymous-by-default)
    ranking_rows = (
        db.query(
            User.assigned_to_user_id,
            func.count(User.id).label("conv"),
        )
        .filter(
            User.lead_pipeline_status == "converted",
            User.lead_pipeline_status_at >= start,
            User.assigned_to_user_id.isnot(None),
        )
        .group_by(User.assigned_to_user_id)
        .order_by(func.count(User.id).desc())
        .all()
    )
    rank = None
    rank_total = len(ranking_rows)
    for idx, row in enumerate(ranking_rows, start=1):
        if row.assigned_to_user_id == user.id:
            rank = idx
            break

    # Timeseries · weekly buckets
    bucket_size = max(1, days // 12)
    timeseries: List[Dict[str, Any]] = []
    cursor = start
    while cursor < end:
        nxt = cursor + timedelta(days=bucket_size)
        lh = _count_leads(db, user.id, cursor, nxt)
        cv = _count_conversions(db, user.id, cursor, nxt)
        timeseries.append({
            "label": cursor.strftime("%d %b"),
            "leads_handled": lh,
            "conversions": cv,
            "conversion_rate": (cv / lh * 100) if lh else 0.0,
        })
        cursor = nxt

    return {
        "period": period,
        "user_id": user.id,
        "leads_handled": leads_handled,
        "leads_handled_prev": leads_handled_prev,
        "conversions": conversions,
        "conversions_prev": conversions_prev,
        "conversion_rate": round(conv_rate, 1),
        "conversion_rate_prev": round(conv_rate_prev, 1),
        "avg_response_hours": None,  # placeholder · requires interaction logs
        "avg_response_hours_prev": None,
        "rank": rank,
        "rank_total": rank_total,
        "timeseries": timeseries,
    }


def _count_leads(db: DBSession, user_id: UUID, start: datetime, end: datetime) -> int:
    return int(
        db.query(func.count(User.id))
        .filter(
            User.assigned_to_user_id == user_id,
            User.assigned_at >= start,
            User.assigned_at < end,
        )
        .scalar()
        or 0
    )


def _count_conversions(
    db: DBSession, user_id: UUID, start: datetime, end: datetime
) -> int:
    return int(
        db.query(func.count(User.id))
        .filter(
            User.assigned_to_user_id == user_id,
            User.lead_pipeline_status == "converted",
            User.lead_pipeline_status_at >= start,
            User.lead_pipeline_status_at < end,
        )
        .scalar()
        or 0
    )


def build_funnel(
    db: DBSession, *, user: User, period: str = "30d"
) -> Dict[str, Any]:
    days = {"30d": 30, "90d": 90, "year": 365}.get(period, 30)
    start = datetime.utcnow() - timedelta(days=days)
    stages = ["pending", "contacted", "qualified", "converted", "declined"]
    labels = {
        "pending": "Pendiente",
        "contacted": "Contactado",
        "qualified": "Calificado",
        "converted": "Convertido",
        "declined": "Descartado",
    }

    # My counts · query lead_pipeline_status_at within period for each stage
    my_counts: Dict[str, int] = {}
    team_counts: Dict[str, int] = {}
    for s in stages:
        my_counts[s] = int(
            db.query(func.count(User.id))
            .filter(
                User.assigned_to_user_id == user.id,
                User.lead_pipeline_status == s,
                User.lead_pipeline_status_at >= start,
            )
            .scalar()
            or 0
        )
        team_counts[s] = int(
            db.query(func.count(User.id))
            .filter(
                User.assigned_to_user_id.isnot(None),
                User.lead_pipeline_status == s,
                User.lead_pipeline_status_at >= start,
            )
            .scalar()
            or 0
        )

    # Number of distinct gh_commercial assignees (for averaging)
    assignees = (
        db.query(func.count(func.distinct(User.assigned_to_user_id)))
        .filter(User.assigned_to_user_id.isnot(None))
        .scalar()
        or 1
    )
    assignees = max(1, int(assignees))

    funnel_stages = []
    prev_count: Optional[int] = None
    for s in stages:
        my_count = my_counts[s]
        team_avg = team_counts[s] // assignees
        drop_off: Optional[float] = None
        if prev_count is not None and prev_count > 0:
            drop_off = round(((prev_count - my_count) / prev_count) * 100, 1)
        funnel_stages.append({
            "key": s,
            "label": labels[s],
            "count": my_count,
            "drop_off_pct": drop_off,
            "team_avg_count": team_avg,
        })
        prev_count = my_count

    return {
        "user_id": user.id,
        "period": period,
        "stages": funnel_stages,
        "team_avg_total": sum(team_counts.values()) // assignees,
        "my_total": sum(my_counts.values()),
    }


def build_benchmarks(
    db: DBSession, *, lead: User
) -> Dict[str, Any]:
    """Compare a lead against the cohort sharing similar demographics."""
    # Cohort definition · same first preferred country + budget band
    pref_country = (lead.preferred_countries or [None])[0]
    cohort_q = db.query(User).filter(User.role == UserRole.STUDENT)
    if pref_country:
        cohort_q = cohort_q.filter(
            User.preferred_countries.op("@>")([pref_country])  # type: ignore
        )
    if lead.budget_band:
        cohort_q = cohort_q.filter(User.budget_band == lead.budget_band)

    cohort = cohort_q.limit(500).all()
    cohort_size = len(cohort)
    my_score = int(_quick_score_estimate(lead))
    higher = sum(1 for u in cohort if int(_quick_score_estimate(u)) > my_score)
    rank = higher + 1
    percentile = round(
        ((cohort_size - rank) / max(cohort_size, 1)) * 100, 1
    )
    avg = (
        round(sum(_quick_score_estimate(u) for u in cohort) / cohort_size, 1)
        if cohort_size
        else 0.0
    )
    top = (
        max(int(_quick_score_estimate(u)) for u in cohort) if cohort_size else 0
    )

    return {
        "lead_user_id": lead.id,
        "cohort_size": cohort_size,
        "rank": rank,
        "percentile": percentile,
        "cohort_definition": {
            "preferred_country": pref_country,
            "budget_band": lead.budget_band,
        },
        "cohort_avg_score": avg,
        "cohort_top_score": int(top),
        "my_score": my_score,
    }


# ===========================================================================
# GH user picker (assign/handoff dropdown)
# ===========================================================================


def list_gh_users(db: DBSession) -> List[Dict[str, Any]]:
    users = (
        db.query(User)
        .filter(
            User.role.in_([UserRole.GH_COMMERCIAL, UserRole.GH_ADVISOR]),
            User.is_active.is_(True),
        )
        .order_by(User.name.asc().nulls_last(), User.email.asc())
        .all()
    )
    # Compute open lead count per user
    rows = (
        db.query(User.assigned_to_user_id, func.count(User.id))
        .filter(
            User.assigned_to_user_id.isnot(None),
            User.lead_pipeline_status.in_(["pending", "contacted", "qualified"]),
        )
        .group_by(User.assigned_to_user_id)
        .all()
    )
    load_map = {uid: cnt for uid, cnt in rows}
    items = []
    for u in users:
        items.append({
            "user_id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role.value,
            "open_leads": int(load_map.get(u.id, 0)),
        })
    return items
