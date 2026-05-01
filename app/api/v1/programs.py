"""Programs catalogue admin · GH-S8-BE-06/07/08.

Endpoints (super_admin only for mutations · public read for listing):

- POST   /programs                · create program
- GET    /programs                · list with pagination + filters
- GET    /programs/{id}           · detail
- PATCH  /programs/{id}           · partial update
- DELETE /programs/{id}           · soft (active=false) by default; hard with ?force=true
- POST   /programs/import         · upload Excel · validate + upsert (super_admin only)
- GET    /programs/export         · download canonical catalogue as Excel
"""
from __future__ import annotations

import io
import logging
import math
import unicodedata
import re
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.core.rate_limiter import limiter
from app.db.database import get_db


def _rate_limit_programs_import(request: Request):
    """GH-S11-INFRA-04 · per-IP/user rate limit for program import upload."""
    from app.core.rate_limiter import rate_limit
    s = get_settings()
    return rate_limit(s.rate_limit_programs_import)(request)
from app.db.models import Program, User, UserRole
from app.schemas.program import (
    ProgramCreate,
    ProgramImportReport,
    ProgramListResponse,
    ProgramResponse,
    ProgramUpdate,
)
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/programs", tags=["Programs"])


REQUIRED_FIELDS = [
    "program_id", "name", "slug", "country", "city", "institution",
    "type", "area", "subject", "duration_months", "cost_total",
    "currency", "budget_tier", "alliance_type", "active",
]


def _ensure_super_admin(user: User) -> None:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden · only super_admin can manage the program catalogue.",
        )


def _slugify(value: str) -> str:
    norm = unicodedata.normalize("NFKD", value or "")
    norm = norm.encode("ascii", "ignore").decode("ascii")
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return norm or "program"


# ----------------------------- list / create / detail -----------------------------

@router.get(
    "",
    response_model=ProgramListResponse,
    summary="GH-S8-BE-06 · paginated list with filters",
)
def list_programs(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    country: Optional[str] = Query(None),
    budget_tier: Optional[str] = Query(None),
    alliance_type: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
):
    q = db.query(Program)

    # school_admin / psychologist / student see only active programs
    if current_user.role != UserRole.SUPER_ADMIN:
        q = q.filter(Program.active.is_(True))
    elif active is not None:
        q = q.filter(Program.active.is_(active))

    if country:
        q = q.filter(Program.country == country)
    if budget_tier:
        q = q.filter(Program.budget_tier == budget_tier)
    if alliance_type:
        q = q.filter(Program.alliance_type == alliance_type)
    if type:
        q = q.filter(Program.type == type)
    if search:
        term = f"%{search.strip().lower()}%"
        q = q.filter(
            or_(
                Program.name.ilike(term),
                Program.institution.ilike(term),
                Program.subject.ilike(term),
                Program.program_id.ilike(term),
            )
        )

    total = q.count()
    rows = (
        q.order_by(Program.country.asc(), Program.institution.asc(), Program.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    total_pages = max(1, math.ceil(total / page_size)) if total else 0

    return ProgramListResponse(
        items=[ProgramResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=ProgramResponse,
    status_code=status.HTTP_201_CREATED,
    summary="GH-S8-BE-06 · create program (super_admin only)",
)
def create_program(
    payload: ProgramCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    program = Program(
        program_id=payload.program_id.strip(),
        name=payload.name.strip(),
        slug=payload.slug,
        country=payload.country.strip(),
        city=(payload.city or "").strip() or None,
        institution=payload.institution.strip(),
        type=payload.type.strip(),
        area=(payload.area or "").strip() or None,
        subject=(payload.subject or "").strip() or None,
        duration_months=payload.duration_months,
        cost_total=payload.cost_total,
        currency=payload.currency,
        budget_tier=payload.budget_tier,
        alliance_type=payload.alliance_type,
        language_requirement=payload.language_requirement,
        active=payload.active,
        raw=payload.raw,
    )
    db.add(program)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A program with the same program_id or slug already exists.",
        )
    db.refresh(program)

    log_action(
        db,
        user=current_user,
        action="program.create",
        resource_type="program",
        resource_id=str(program.id),
        payload={"program_id": program.program_id, "slug": program.slug},
        request=request,
    )

    return ProgramResponse.model_validate(program)


@router.get(
    "/{program_id}",
    response_model=ProgramResponse,
    summary="Read program by id",
)
def get_program(
    program_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    program = db.query(Program).filter(Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found.")
    if not program.active and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found.")
    return ProgramResponse.model_validate(program)


@router.patch(
    "/{program_id}",
    response_model=ProgramResponse,
    summary="GH-S8-BE-06 · update program (super_admin only)",
)
def update_program(
    program_id: UUID,
    payload: ProgramUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    program = db.query(Program).filter(Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found.")

    diff: dict = {}
    for fld, val in payload.model_dump(exclude_unset=True).items():
        cur = getattr(program, fld)
        if val != cur:
            diff[fld] = {"from": str(cur)[:80] if cur is not None else None, "to": str(val)[:80] if val is not None else None}
            setattr(program, fld, val)

    program.updated_at = datetime.utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slug or program_id collision.",
        )
    db.refresh(program)

    if diff:
        log_action(
            db,
            user=current_user,
            action="program.update",
            resource_type="program",
            resource_id=str(program.id),
            payload=diff,
            request=request,
        )

    return ProgramResponse.model_validate(program)


@router.delete(
    "/{program_id}",
    status_code=status.HTTP_200_OK,
    summary="GH-S8-BE-06 · soft delete program (active=false) · ?force=true for hard delete",
)
def delete_program(
    program_id: UUID,
    request: Request,
    force: bool = Query(False),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    program = db.query(Program).filter(Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found.")

    if force:
        db.delete(program)
        action = "program.delete"
    else:
        program.active = False
        program.updated_at = datetime.utcnow()
        action = "program.delete"
    db.commit()

    log_action(
        db,
        user=current_user,
        action=action,
        resource_type="program",
        resource_id=str(program_id),
        payload={"force": force, "program_biz_id": program.program_id},
        request=request,
    )

    return {"id": str(program_id), "deleted": force, "deactivated": not force}


# ----------------------------- import / export -----------------------------

@router.post(
    "/import",
    response_model=ProgramImportReport,
    summary="GH-S8-BE-07 · Excel upload · validate + upsert (super_admin only)",
    dependencies=[Depends(_rate_limit_programs_import)],
)
async def import_programs(
    request: Request,
    file: UploadFile = File(...),
    commit: bool = Query(False, description="false = dry-run (validate only)"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GH-S11-INFRA-04 · rate-limited (default 5/hour)."""
    _ensure_super_admin(current_user)

    try:
        from openpyxl import load_workbook
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="openpyxl missing on server.",
        )

    if file.content_type and "spreadsheetml" not in file.content_type and not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xlsx files are accepted.",
        )

    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(status_code=413, detail="Excel too large (>10MB).")

    try:
        wb = load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read Excel: {exc}")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Empty Excel.")

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    missing = [c for c in REQUIRED_FIELDS if c not in headers]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    errors: list = []
    warnings: list = []
    valid_records: list[dict] = []
    total_rows = 0
    for idx, raw_row in enumerate(rows[1:], start=2):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in raw_row):
            continue
        total_rows += 1
        record = dict(zip(headers, raw_row))
        # normalize a few fields
        for k in ("program_id", "name", "country", "city", "institution", "type", "area", "subject", "currency", "budget_tier", "alliance_type", "language_requirement", "slug"):
            if record.get(k) is not None:
                record[k] = str(record[k]).strip()
        # required presence
        row_ok = True
        for fld in REQUIRED_FIELDS:
            v = record.get(fld)
            if v is None or (isinstance(v, str) and not v.strip()):
                errors.append({"row": idx, "field": fld, "msg": "campo obligatorio vacío"})
                row_ok = False
        # numeric coercions
        try:
            record["duration_months"] = int(record.get("duration_months") or 0)
        except (TypeError, ValueError):
            errors.append({"row": idx, "field": "duration_months", "msg": "no es entero"})
            row_ok = False
        try:
            record["cost_total"] = int(record.get("cost_total") or 0)
        except (TypeError, ValueError):
            errors.append({"row": idx, "field": "cost_total", "msg": "no es entero"})
            row_ok = False
        # active boolean coercion
        active_val = record.get("active")
        if isinstance(active_val, str):
            record["active"] = active_val.strip().lower() in ("si", "sí", "yes", "true", "1", "y", "x")
        else:
            record["active"] = bool(active_val) if active_val is not None else True

        if row_ok:
            valid_records.append(record)

    inserted = 0
    updated = 0
    if commit and not errors:
        for r in valid_records:
            existing = db.query(Program).filter(Program.program_id == r["program_id"]).first()
            slug = r.get("slug") or _slugify(r["name"])
            if existing:
                # update fields
                existing.name = r["name"]
                existing.slug = slug
                existing.country = r["country"]
                existing.city = r.get("city") or None
                existing.institution = r["institution"]
                existing.type = r["type"]
                existing.area = r.get("area") or None
                existing.subject = r.get("subject") or None
                existing.duration_months = r["duration_months"]
                existing.cost_total = r["cost_total"]
                existing.currency = (r.get("currency") or "USD").upper()
                existing.budget_tier = (r.get("budget_tier") or "medium").lower()
                existing.alliance_type = (r.get("alliance_type") or "estandar").lower()
                existing.language_requirement = r.get("language_requirement") or None
                existing.active = bool(r.get("active", True))
                existing.raw = r
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                p = Program(
                    program_id=r["program_id"],
                    name=r["name"],
                    slug=slug,
                    country=r["country"],
                    city=r.get("city") or None,
                    institution=r["institution"],
                    type=r["type"],
                    area=r.get("area") or None,
                    subject=r.get("subject") or None,
                    duration_months=r["duration_months"],
                    cost_total=r["cost_total"],
                    currency=(r.get("currency") or "USD").upper(),
                    budget_tier=(r.get("budget_tier") or "medium").lower(),
                    alliance_type=(r.get("alliance_type") or "estandar").lower(),
                    language_requirement=r.get("language_requirement") or None,
                    active=bool(r.get("active", True)),
                    raw=r,
                )
                db.add(p)
                inserted += 1
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Integrity error: {exc.orig}")

        log_action(
            db,
            user=current_user,
            action="program.import",
            resource_type="program_catalog",
            resource_id=None,
            payload={
                "filename": file.filename,
                "inserted": inserted,
                "updated": updated,
                "total_rows": total_rows,
            },
            request=request,
        )

    return ProgramImportReport(
        total_rows=total_rows,
        valid_rows=len(valid_records),
        inserted=inserted,
        updated=updated,
        errors=errors,
        warnings=warnings,
        committed=bool(commit and not errors),
    )


@router.get(
    "/export.xlsx",
    summary="GH-S8-BE-08 · download canonical program catalogue as Excel",
)
def export_programs(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_super_admin(current_user)

    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl missing on server.")

    rows = db.query(Program).order_by(Program.country.asc(), Program.institution.asc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Programs"
    ws.append(REQUIRED_FIELDS + ["language_requirement"])
    for p in rows:
        ws.append([
            p.program_id,
            p.name,
            p.slug,
            p.country,
            p.city or "",
            p.institution,
            p.type,
            p.area or "",
            p.subject or "",
            p.duration_months,
            p.cost_total,
            p.currency,
            p.budget_tier,
            p.alliance_type,
            "si" if p.active else "no",
            p.language_requirement or "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"grasshopper_catalog_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
