"""Super-admin settings: feature flags · prompts · integration configs · backup.

Bloques covered:
  M · /admin/feature-flags          (CRUD)
  N · /admin/prompts                (versioning + activate)
  O · /admin/integrations/configs   (Bitrix etc · NO secrets in DB)
  P · /admin/backup                 (export critical tables to CSV ZIP)
"""
from __future__ import annotations

import csv
import io
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import (
    AIPrompt,
    AuditLog,
    FeatureFlag,
    IntegrationConfig,
    Program,
    School,
    User,
    UserRole,
)
from app.services.audit_service import log_action
from app.services.feature_flags_service import invalidate_cache as _ff_invalidate
from app.services.ai_prompts_service import invalidate_cache as _ap_invalidate


router = APIRouter(prefix="/admin", tags=["Admin · Settings"])


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "super_admin only")


# --------------------------------------------------------------------------- #
# Bloque M · feature flags                                                    #
# --------------------------------------------------------------------------- #

class FeatureFlagOut(BaseModel):
    id: UUID
    key: str
    name: str
    description: Optional[str] = None
    enabled: bool
    enabled_for_roles: List[str] = Field(default_factory=list)
    enabled_for_school_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeatureFlagIn(BaseModel):
    key: str = Field(..., min_length=2, max_length=80)
    name: str
    description: Optional[str] = None
    enabled: bool = False
    enabled_for_roles: List[str] = Field(default_factory=list)
    enabled_for_school_ids: List[UUID] = Field(default_factory=list)


class FeatureFlagPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    enabled_for_roles: Optional[List[str]] = None
    enabled_for_school_ids: Optional[List[UUID]] = None


@router.get("/feature-flags", response_model=List[FeatureFlagOut])
def list_flags(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    rows = db.query(FeatureFlag).order_by(FeatureFlag.key).all()
    return [FeatureFlagOut.model_validate(r) for r in rows]


@router.post("/feature-flags", response_model=FeatureFlagOut, status_code=201)
def create_flag(
    payload: FeatureFlagIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    if db.query(FeatureFlag).filter(FeatureFlag.key == payload.key).first():
        raise HTTPException(409, "Flag key already exists")
    row = FeatureFlag(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        enabled_for_roles=payload.enabled_for_roles,
        enabled_for_school_ids=[str(s) for s in payload.enabled_for_school_ids],
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _ff_invalidate()
    log_action(
        db,
        user=current_user,
        action="feature_flag.create",
        resource_type="feature_flag",
        resource_id=str(row.id),
        payload={"key": row.key},
        request=request,
    )
    return FeatureFlagOut.model_validate(row)


@router.patch("/feature-flags/{flag_id}", response_model=FeatureFlagOut)
def update_flag(
    flag_id: UUID,
    payload: FeatureFlagPatch,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    row = db.query(FeatureFlag).filter(FeatureFlag.id == flag_id).first()
    if not row:
        raise HTTPException(404, "Flag not found")
    changes = {}
    if payload.name is not None and payload.name != row.name:
        changes["name"] = payload.name
        row.name = payload.name
    if payload.description is not None:
        changes["description"] = payload.description
        row.description = payload.description
    if payload.enabled is not None and payload.enabled != row.enabled:
        changes["enabled"] = payload.enabled
        row.enabled = payload.enabled
    if payload.enabled_for_roles is not None:
        changes["enabled_for_roles"] = payload.enabled_for_roles
        row.enabled_for_roles = payload.enabled_for_roles
    if payload.enabled_for_school_ids is not None:
        changes["enabled_for_school_ids"] = [str(s) for s in payload.enabled_for_school_ids]
        row.enabled_for_school_ids = changes["enabled_for_school_ids"]
    if changes:
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        _ff_invalidate()
        log_action(
            db,
            user=current_user,
            action="feature_flag.update",
            resource_type="feature_flag",
            resource_id=str(row.id),
            payload={"changes": changes},
            request=request,
        )
    return FeatureFlagOut.model_validate(row)


@router.post("/feature-flags/{flag_id}/toggle", response_model=FeatureFlagOut)
def toggle_flag(
    flag_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    row = db.query(FeatureFlag).filter(FeatureFlag.id == flag_id).first()
    if not row:
        raise HTTPException(404, "Flag not found")
    row.enabled = not row.enabled
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    _ff_invalidate()
    log_action(
        db,
        user=current_user,
        action="feature_flag.toggle",
        resource_type="feature_flag",
        resource_id=str(row.id),
        payload={"enabled": row.enabled},
        request=request,
    )
    return FeatureFlagOut.model_validate(row)


@router.delete("/feature-flags/{flag_id}", status_code=204)
def delete_flag(
    flag_id: UUID,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    row = db.query(FeatureFlag).filter(FeatureFlag.id == flag_id).first()
    if not row:
        raise HTTPException(404, "Flag not found")
    db.delete(row)
    db.commit()
    _ff_invalidate()
    log_action(
        db,
        user=current_user,
        action="feature_flag.delete",
        resource_type="feature_flag",
        resource_id=str(flag_id),
        request=request,
    )


# --------------------------------------------------------------------------- #
# Bloque N · AI prompts versioning                                            #
# --------------------------------------------------------------------------- #

class AIPromptOut(BaseModel):
    id: UUID
    key: str
    version: int
    content: str
    is_active: bool
    created_at: datetime
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class AIPromptVersionsResponse(BaseModel):
    key: str
    versions: List[AIPromptOut]


class AIPromptCreateIn(BaseModel):
    key: str = Field(..., min_length=2, max_length=80)
    content: str = Field(..., min_length=10)
    notes: Optional[str] = None
    activate: bool = False


@router.get("/prompts", response_model=List[Dict])
def list_prompt_keys(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all prompt keys with their currently active version."""
    _ensure_super_admin(current_user)
    rows = (
        db.query(
            AIPrompt.key,
            func.max(AIPrompt.version).label("latest_version"),
            func.count(AIPrompt.id).label("versions_count"),
        )
        .group_by(AIPrompt.key)
        .order_by(AIPrompt.key)
        .all()
    )
    out = []
    for r in rows:
        active = (
            db.query(AIPrompt)
            .filter(AIPrompt.key == r.key, AIPrompt.is_active == True)  # noqa: E712
            .first()
        )
        out.append(
            {
                "key": r.key,
                "latest_version": int(r.latest_version),
                "versions_count": int(r.versions_count),
                "active_version": active.version if active else None,
            }
        )
    return out


@router.get("/prompts/{key}", response_model=AIPromptVersionsResponse)
def list_prompt_versions(
    key: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    rows = db.query(AIPrompt).filter(AIPrompt.key == key).order_by(AIPrompt.version.desc()).all()
    if not rows:
        raise HTTPException(404, f"No prompts under key={key}")
    return AIPromptVersionsResponse(key=key, versions=[AIPromptOut.model_validate(r) for r in rows])


@router.post("/prompts", response_model=AIPromptOut, status_code=201)
def create_prompt_version(
    payload: AIPromptCreateIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    next_version = (
        db.query(func.coalesce(func.max(AIPrompt.version), 0))
        .filter(AIPrompt.key == payload.key)
        .scalar()
        or 0
    ) + 1
    row = AIPrompt(
        key=payload.key,
        version=next_version,
        content=payload.content,
        is_active=False,
        created_by_user_id=current_user.id,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db,
        user=current_user,
        action="ai_prompt.create",
        resource_type="ai_prompt",
        resource_id=str(row.id),
        payload={"key": payload.key, "version": next_version},
        request=request,
    )
    if payload.activate:
        return _activate_prompt_internal(db, row, current_user, request)
    return AIPromptOut.model_validate(row)


def _activate_prompt_internal(
    db: DBSession, target: AIPrompt, actor: User, request: Request
) -> AIPromptOut:
    db.query(AIPrompt).filter(
        AIPrompt.key == target.key, AIPrompt.is_active == True  # noqa: E712
    ).update({"is_active": False}, synchronize_session=False)
    target.is_active = True
    db.commit()
    db.refresh(target)
    _ap_invalidate()
    log_action(
        db,
        user=actor,
        action="ai_prompt.activate",
        resource_type="ai_prompt",
        resource_id=str(target.id),
        payload={"key": target.key, "version": target.version},
        request=request,
    )
    return AIPromptOut.model_validate(target)


@router.post("/prompts/{key}/activate/{version}", response_model=AIPromptOut)
def activate_prompt(
    key: str,
    version: int,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    target = (
        db.query(AIPrompt).filter(AIPrompt.key == key, AIPrompt.version == version).first()
    )
    if not target:
        raise HTTPException(404, "Prompt version not found")
    return _activate_prompt_internal(db, target, current_user, request)


# --------------------------------------------------------------------------- #
# Bloque O · integration configs (NO secrets in DB)                           #
# --------------------------------------------------------------------------- #

class IntegrationConfigOut(BaseModel):
    id: UUID
    integration_key: str
    setting_key: str
    setting_value: Optional[str] = None
    is_secret: bool
    description: Optional[str] = None
    updated_at: datetime
    # When is_secret=True, setting_value is the env var NAME (already returned),
    # the real value lives in os.environ. We expose a `configured_in_env` flag
    # so the UI can show "***configurado en env***" without leaking the value.
    configured_in_env: Optional[bool] = None

    model_config = {"from_attributes": True}


class IntegrationConfigUpsertIn(BaseModel):
    setting_key: str = Field(..., min_length=1, max_length=80)
    setting_value: Optional[str] = None
    is_secret: bool = False
    description: Optional[str] = None


def _serialize_config(row: IntegrationConfig) -> IntegrationConfigOut:
    out = IntegrationConfigOut.model_validate(row)
    if row.is_secret and row.setting_value:
        # setting_value is the env var NAME. Verify presence (do not return value).
        out.configured_in_env = bool(os.environ.get(row.setting_value))
    return out


@router.get("/integrations/{integration_key}/configs", response_model=List[IntegrationConfigOut])
def list_integration_configs(
    integration_key: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    rows = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.integration_key == integration_key)
        .order_by(IntegrationConfig.setting_key)
        .all()
    )
    return [_serialize_config(r) for r in rows]


@router.put("/integrations/{integration_key}/configs", response_model=IntegrationConfigOut)
def upsert_integration_config(
    integration_key: str,
    payload: IntegrationConfigUpsertIn,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upsert config row.

    SECURITY (Bloque O · gh-security-reviewer):
      - is_secret=True → setting_value MUST be an env var name (no spaces, no
        URL-like content); we additionally REJECT values that look like real
        secrets (contain '://', long random strings, or do not match an env
        var naming convention).
    """
    _ensure_super_admin(current_user)

    if payload.is_secret and payload.setting_value:
        sv = payload.setting_value.strip()
        # env var name convention: uppercase letters, digits, underscores
        import re

        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", sv):
            raise HTTPException(
                400,
                "is_secret requires setting_value to be an env var NAME (UPPER_SNAKE_CASE) · NEVER the real secret",
            )
        # extra paranoia · reject things that look like URLs or tokens
        if "://" in sv or len(sv) > 80:
            raise HTTPException(400, "is_secret value rejected · looks like an actual secret")

    row = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.integration_key == integration_key,
            IntegrationConfig.setting_key == payload.setting_key,
        )
        .first()
    )
    created = False
    if row is None:
        row = IntegrationConfig(
            integration_key=integration_key,
            setting_key=payload.setting_key,
            setting_value=payload.setting_value,
            is_secret=payload.is_secret,
            description=payload.description,
            updated_by_user_id=current_user.id,
        )
        db.add(row)
        created = True
    else:
        row.setting_value = payload.setting_value
        row.is_secret = payload.is_secret
        if payload.description is not None:
            row.description = payload.description
        row.updated_by_user_id = current_user.id
        row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    log_action(
        db,
        user=current_user,
        action="integration_config.update",
        resource_type="integration_config",
        resource_id=str(row.id),
        payload={
            "integration_key": integration_key,
            "setting_key": payload.setting_key,
            "is_secret": payload.is_secret,
            "created": created,
            # NEVER include setting_value when is_secret=True; even when
            # is_secret=False we keep the payload thin.
        },
        request=request,
    )
    return _serialize_config(row)


# --------------------------------------------------------------------------- #
# Bloque P · backup / export                                                  #
# --------------------------------------------------------------------------- #

class BackupExportOut(BaseModel):
    id: str
    created_at: datetime
    rows_users: int
    rows_schools: int
    rows_programs: int
    rows_audit_log: int
    size_bytes: int


_EXPORT_DIR = Path(os.getenv("BACKUP_EXPORT_DIR", "/tmp/gh_backups"))
_EXPORTS: Dict[str, dict] = {}


def _ensure_export_dir() -> None:
    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _csv_for(rows, columns) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for r in rows:
        writer.writerow([getattr(r, c) for c in columns])
    return buf.getvalue().encode("utf-8")


@router.post("/backup/export", response_model=BackupExportOut, status_code=201)
def create_backup_export(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    _ensure_export_dir()

    users = db.query(User).all()
    schools = db.query(School).all()
    programs = db.query(Program).all()
    audit_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(50000).all()

    export_id = uuid4().hex
    path = _EXPORT_DIR / f"{export_id}.zip"

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "users.csv",
            _csv_for(
                users,
                [
                    "id",
                    "email",
                    "name",
                    "role",
                    "school_id",
                    "is_active",
                    "suspended_at",
                    "last_login_at",
                    "created_at",
                ],
            ),
        )
        zf.writestr(
            "schools.csv",
            _csv_for(schools, ["id", "name", "created_at", "archived_at"]),
        )
        zf.writestr(
            "programs.csv",
            _csv_for(programs, ["id", "name", "country", "institution", "created_at"]),
        )
        zf.writestr(
            "audit_log.csv",
            _csv_for(
                audit_logs,
                [
                    "id",
                    "user_id",
                    "action",
                    "resource_type",
                    "resource_id",
                    "ip_address",
                    "created_at",
                ],
            ),
        )

    size_bytes = path.stat().st_size
    info = BackupExportOut(
        id=export_id,
        created_at=datetime.utcnow(),
        rows_users=len(users),
        rows_schools=len(schools),
        rows_programs=len(programs),
        rows_audit_log=len(audit_logs),
        size_bytes=size_bytes,
    )
    _EXPORTS[export_id] = {"path": str(path), "meta": info.model_dump()}
    log_action(
        db,
        user=current_user,
        action="backup.export_created",
        resource_type="backup",
        resource_id=export_id,
        payload={"size_bytes": size_bytes},
        request=request,
    )
    return info


@router.get("/backup/exports", response_model=List[BackupExportOut])
def list_backup_exports(
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    return [BackupExportOut(**v["meta"]) for v in _EXPORTS.values()]


@router.get("/backup/exports/{export_id}/download")
def download_backup_export(
    export_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)
    entry = _EXPORTS.get(export_id)
    if not entry:
        raise HTTPException(404, "Export not found")
    path = Path(entry["path"])
    if not path.exists():
        raise HTTPException(410, "Export expired")
    log_action(
        db,
        user=current_user,
        action="backup.export_downloaded",
        resource_type="backup",
        resource_id=export_id,
        request=request,
    )

    def _iter():
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="gh_backup_{export_id}.zip"'},
    )
