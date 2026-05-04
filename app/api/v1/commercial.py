"""Commercial productivity router · GH-COMMPROD sprint.

Aggregates surfaces for:
    - Assign / unassign / handoff (B2 / F2)
    - Tags catalog + per-lead assignment (D1)
    - Saved searches (D3)
    - Comments + mentions (F1)
    - Pipeline stages CRUD + reorder (B6)
    - Auto-assign rules (E1)
    - Pipeline rules / IFTTT (E2)
    - Today dashboard (B1)
    - Activity timeline (B5)
    - Performance + funnel + benchmarks (D4 / I2 / D2)
    - GH user picker

Auth tier:
    super_admin → full access (CRUD on settings + everyone's data)
    gh_commercial / gh_advisor → personal scope
    others → 403
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    AutoAssignRule,
    LeadComment,
    LeadTag,
    PipelineRule,
    PipelineStage,
    SavedSearch,
    User,
    UserRole,
)
from app.schemas.commercial import (
    ActivityTimelineResponse,
    AssignBody,
    AssignmentResult,
    AutoAssignRuleCreate,
    AutoAssignRuleItem,
    AutoAssignRulePatch,
    BenchmarkResponse,
    CommentCreate,
    CommentItem,
    CommentPatch,
    FunnelResponse,
    GhUserPickerItem,
    HandoffBody,
    LeadTagsResponse,
    PerformanceResponse,
    PipelineRuleCreate,
    PipelineRuleItem,
    PipelineRulePatch,
    PipelineStageCreate,
    PipelineStageItem,
    PipelineStagePatch,
    PipelineStageReorder,
    SavedSearchCreate,
    SavedSearchItem,
    SavedSearchPatch,
    TagAssignBody,
    TagCreate,
    TagItem,
    TodayResponse,
)
from app.services import commercial_service

router = APIRouter(prefix="/admin/commercial", tags=["Commercial"])


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _require_team(user: User) -> None:
    if user.role not in (
        UserRole.GH_COMMERCIAL,
        UserRole.GH_ADVISOR,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · gh team only",
        )


def _require_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="super_admin only"
        )


def _resolve_lead(db: DBSession, lead_user_id: UUID) -> User:
    lead = db.query(User).filter(User.id == lead_user_id).first()
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


# ===========================================================================
# Today dashboard (B1)
# ===========================================================================


@router.get("/today", response_model=TodayResponse)
def today(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.build_today(db, user=current_user)


# ===========================================================================
# Assign / handoff (B2 / F2)
# ===========================================================================


@router.patch(
    "/leads/{lead_user_id}/assign", response_model=AssignmentResult
)
def assign_lead(
    lead_user_id: UUID,
    body: AssignBody,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Decisión JP 2026-05-04: solo super_admin asigna manualmente
    # · gh_commercial / gh_advisor reciben asignación pero no la cambian
    _require_super_admin(current_user)
    lead = _resolve_lead(db, lead_user_id)
    to_user: Optional[User] = None
    if body.to_user_id is not None:
        to_user = db.query(User).filter(User.id == body.to_user_id).first()
        if to_user is None:
            raise HTTPException(status_code=404, detail="assignee not found")
    try:
        lead = commercial_service.assign_lead(
            db,
            lead=lead,
            to_user=to_user,
            actor=current_user,
            note=body.note,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "lead_user_id": lead.id,
        "assigned_to_user_id": lead.assigned_to_user_id,
        "assigned_to_name": (to_user.name if to_user else None),
        "assigned_at": lead.assigned_at,
    }


@router.patch(
    "/leads/{lead_user_id}/handoff", response_model=AssignmentResult
)
def handoff_lead(
    lead_user_id: UUID,
    body: HandoffBody,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Decisión JP 2026-05-04: solo super_admin transfiere leads
    _require_super_admin(current_user)
    lead = _resolve_lead(db, lead_user_id)
    to_user = db.query(User).filter(User.id == body.to_user_id).first()
    if to_user is None:
        raise HTTPException(status_code=404, detail="assignee not found")
    try:
        lead = commercial_service.handoff_lead(
            db,
            lead=lead,
            to_user=to_user,
            actor=current_user,
            note=body.note,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "lead_user_id": lead.id,
        "assigned_to_user_id": lead.assigned_to_user_id,
        "assigned_to_name": to_user.name,
        "assigned_at": lead.assigned_at,
    }


@router.get("/gh-users", response_model=List[GhUserPickerItem])
def gh_users(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.list_gh_users(db)


# ===========================================================================
# Tags (D1)
# ===========================================================================


@router.get("/tags", response_model=List[TagItem])
def list_tags(
    db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    _require_team(current_user)
    return commercial_service.list_tags(db)


@router.post("/tags", response_model=TagItem, status_code=status.HTTP_201_CREATED)
def create_tag(
    body: TagCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    return commercial_service.create_tag(
        db,
        actor=current_user,
        key=body.key,
        label=body.label,
        color=body.color,
        request=request,
    )


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    tag = db.query(LeadTag).filter(LeadTag.id == tag_id).first()
    if tag is None:
        raise HTTPException(status_code=404, detail="tag not found")
    commercial_service.delete_tag(db, actor=current_user, tag=tag, request=request)


@router.get("/leads/{lead_user_id}/tags", response_model=LeadTagsResponse)
def get_lead_tags(
    lead_user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    _resolve_lead(db, lead_user_id)
    tags = commercial_service.get_lead_tags(db, lead_user_id=lead_user_id)
    return {"lead_user_id": lead_user_id, "tags": tags}


@router.put("/leads/{lead_user_id}/tags", response_model=LeadTagsResponse)
def set_lead_tags(
    lead_user_id: UUID,
    body: TagAssignBody,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    _resolve_lead(db, lead_user_id)
    tags = commercial_service.set_lead_tags(
        db,
        actor=current_user,
        lead_user_id=lead_user_id,
        tag_ids=body.tag_ids,
        request=request,
    )
    return {"lead_user_id": lead_user_id, "tags": tags}


# ===========================================================================
# Saved searches (D3)
# ===========================================================================


@router.get("/saved-searches", response_model=List[SavedSearchItem])
def list_saved_searches(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.list_saved_searches(db, user=current_user)


@router.post(
    "/saved-searches",
    response_model=SavedSearchItem,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_search(
    body: SavedSearchCreate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.create_saved_search(
        db,
        user=current_user,
        name=body.name,
        filters=body.filters,
        pinned=body.pinned,
    )


@router.patch("/saved-searches/{search_id}", response_model=SavedSearchItem)
def patch_saved_search(
    search_id: UUID,
    body: SavedSearchPatch,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    s = db.query(SavedSearch).filter(SavedSearch.id == search_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    try:
        return commercial_service.patch_saved_search(
            db,
            user=current_user,
            search=s,
            fields=body.model_dump(exclude_unset=True),
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="not your saved search")


@router.delete(
    "/saved-searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_saved_search(
    search_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    s = db.query(SavedSearch).filter(SavedSearch.id == search_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    try:
        commercial_service.delete_saved_search(db, user=current_user, search=s)
    except PermissionError:
        raise HTTPException(status_code=403, detail="not your saved search")


# ===========================================================================
# Comments (F1)
# ===========================================================================


@router.get(
    "/leads/{lead_user_id}/comments", response_model=List[CommentItem]
)
def list_comments(
    lead_user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    _resolve_lead(db, lead_user_id)
    return commercial_service.list_comments(db, lead_user_id=lead_user_id)


@router.post(
    "/leads/{lead_user_id}/comments",
    response_model=CommentItem,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    lead_user_id: UUID,
    body: CommentCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    _resolve_lead(db, lead_user_id)
    row = commercial_service.create_comment(
        db,
        actor=current_user,
        lead_user_id=lead_user_id,
        body=body.body,
        parent_id=body.parent_id,
        mentions=body.mentions,
        request=request,
    )
    # Hydrate response
    items = commercial_service.list_comments(db, lead_user_id=lead_user_id)
    for it in items:
        if it["id"] == row.id:
            return it
    return {
        "id": row.id,
        "lead_user_id": row.lead_user_id,
        "author_user_id": row.author_user_id,
        "author_name": current_user.name,
        "author_email": current_user.email,
        "body": row.body,
        "mentions": row.mentions or [],
        "parent_id": row.parent_id,
        "created_at": row.created_at,
        "edited_at": row.edited_at,
    }


@router.patch("/comments/{comment_id}", response_model=CommentItem)
def patch_comment(
    comment_id: UUID,
    body: CommentPatch,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    c = db.query(LeadComment).filter(LeadComment.id == comment_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="comment not found")
    try:
        c = commercial_service.patch_comment(
            db, actor=current_user, comment=c, body=body.body
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="cannot edit this comment")
    return {
        "id": c.id,
        "lead_user_id": c.lead_user_id,
        "author_user_id": c.author_user_id,
        "author_name": current_user.name,
        "author_email": current_user.email,
        "body": c.body,
        "mentions": c.mentions or [],
        "parent_id": c.parent_id,
        "created_at": c.created_at,
        "edited_at": c.edited_at,
    }


@router.delete(
    "/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_comment(
    comment_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    c = db.query(LeadComment).filter(LeadComment.id == comment_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="comment not found")
    try:
        commercial_service.delete_comment(db, actor=current_user, comment=c)
    except PermissionError:
        raise HTTPException(status_code=403, detail="cannot delete this comment")


# ===========================================================================
# Activity timeline (B5)
# ===========================================================================


@router.get(
    "/leads/{lead_user_id}/activity",
    response_model=ActivityTimelineResponse,
)
def lead_activity(
    lead_user_id: UUID,
    limit: int = Query(200, ge=10, le=500),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    _resolve_lead(db, lead_user_id)
    return commercial_service.build_activity_timeline(
        db, lead_user_id=lead_user_id, limit=limit
    )


# ===========================================================================
# Performance / funnel / benchmarks
# ===========================================================================


@router.get("/me/performance", response_model=PerformanceResponse)
def me_performance(
    period: str = Query("30d", regex="^(30d|90d|year)$"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.build_performance(
        db, user=current_user, period=period
    )


@router.get("/me/funnel", response_model=FunnelResponse)
def me_funnel(
    period: str = Query("30d", regex="^(30d|90d|year)$"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.build_funnel(db, user=current_user, period=period)


@router.get(
    "/leads/{lead_user_id}/benchmarks", response_model=BenchmarkResponse
)
def lead_benchmarks(
    lead_user_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    lead = _resolve_lead(db, lead_user_id)
    return commercial_service.build_benchmarks(db, lead=lead)


# ===========================================================================
# Pipeline stages CRUD (B6)
# ===========================================================================


@router.get("/pipeline-stages", response_model=List[PipelineStageItem])
def list_pipeline_stages(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_team(current_user)
    return commercial_service.list_pipeline_stages(db)


@router.post(
    "/pipeline-stages",
    response_model=PipelineStageItem,
    status_code=status.HTTP_201_CREATED,
)
def create_pipeline_stage(
    body: PipelineStageCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    try:
        return commercial_service.create_pipeline_stage(
            db,
            actor=current_user,
            key=body.key,
            label=body.label,
            color=body.color,
            order_index=body.order_index,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/pipeline-stages/{stage_id}", response_model=PipelineStageItem
)
def patch_pipeline_stage(
    stage_id: UUID,
    body: PipelineStagePatch,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    stage = db.query(PipelineStage).filter(PipelineStage.id == stage_id).first()
    if stage is None:
        raise HTTPException(status_code=404, detail="stage not found")
    return commercial_service.patch_pipeline_stage(
        db,
        actor=current_user,
        stage=stage,
        fields=body.model_dump(exclude_unset=True),
        request=request,
    )


@router.delete(
    "/pipeline-stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_pipeline_stage(
    stage_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    stage = db.query(PipelineStage).filter(PipelineStage.id == stage_id).first()
    if stage is None:
        raise HTTPException(status_code=404, detail="stage not found")
    try:
        commercial_service.delete_pipeline_stage(
            db, actor=current_user, stage=stage, request=request
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/pipeline-stages/reorder", response_model=List[PipelineStageItem]
)
def reorder_pipeline_stages(
    body: PipelineStageReorder,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    return commercial_service.reorder_pipeline_stages(
        db, actor=current_user, order=body.order, request=request
    )


# ===========================================================================
# Auto-assign rules (E1)
# ===========================================================================


@router.get("/auto-assign-rules", response_model=List[AutoAssignRuleItem])
def list_auto_assign_rules(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    return commercial_service.list_auto_assign_rules(db)


@router.post(
    "/auto-assign-rules",
    response_model=AutoAssignRuleItem,
    status_code=status.HTTP_201_CREATED,
)
def create_auto_assign_rule(
    body: AutoAssignRuleCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    return commercial_service.create_auto_assign_rule(
        db,
        actor=current_user,
        strategy=body.strategy,
        config=body.config,
        is_active=body.is_active,
        priority=body.priority,
        request=request,
    )


@router.patch(
    "/auto-assign-rules/{rule_id}", response_model=AutoAssignRuleItem
)
def patch_auto_assign_rule(
    rule_id: UUID,
    body: AutoAssignRulePatch,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    rule = db.query(AutoAssignRule).filter(AutoAssignRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    return commercial_service.patch_auto_assign_rule(
        db,
        actor=current_user,
        rule=rule,
        fields=body.model_dump(exclude_unset=True),
        request=request,
    )


@router.delete(
    "/auto-assign-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_auto_assign_rule(
    rule_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    rule = db.query(AutoAssignRule).filter(AutoAssignRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    commercial_service.delete_auto_assign_rule(
        db, actor=current_user, rule=rule, request=request
    )


# ===========================================================================
# Pipeline rules / IFTTT (E2)
# ===========================================================================


@router.get("/pipeline-rules", response_model=List[PipelineRuleItem])
def list_pipeline_rules(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    return commercial_service.list_pipeline_rules(db)


@router.post(
    "/pipeline-rules",
    response_model=PipelineRuleItem,
    status_code=status.HTTP_201_CREATED,
)
def create_pipeline_rule(
    body: PipelineRuleCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    return commercial_service.create_pipeline_rule(
        db,
        actor=current_user,
        name=body.name,
        condition=body.condition,
        action=body.action,
        is_active=body.is_active,
        request=request,
    )


@router.patch("/pipeline-rules/{rule_id}", response_model=PipelineRuleItem)
def patch_pipeline_rule(
    rule_id: UUID,
    body: PipelineRulePatch,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    rule = db.query(PipelineRule).filter(PipelineRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    return commercial_service.patch_pipeline_rule(
        db,
        actor=current_user,
        rule=rule,
        fields=body.model_dump(exclude_unset=True),
        request=request,
    )


@router.delete(
    "/pipeline-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_pipeline_rule(
    rule_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_super_admin(current_user)
    rule = db.query(PipelineRule).filter(PipelineRule.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    commercial_service.delete_pipeline_rule(
        db, actor=current_user, rule=rule, request=request
    )
