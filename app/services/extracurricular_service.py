"""Service layer for extracurricular activities · F-001 (2026-05-21)."""
from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    EXTRACURRICULAR_CATEGORIES,
    ExtracurricularActivity,
    User,
)


def _validate_category(category: str) -> None:
    if category not in EXTRACURRICULAR_CATEGORIES:
        raise ValueError(
            f"invalid category: {category!r}; must be one of {EXTRACURRICULAR_CATEGORIES}"
        )


def _validate_dates(
    start_date: Optional[date], end_date: Optional[date]
) -> None:
    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date must be on or after start_date")


def create_activity(
    db: DBSession,
    *,
    user: User,
    category: str,
    name: str,
    role: Optional[str] = None,
    hours_per_week: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    description: Optional[str] = None,
    achievements: Optional[List[str]] = None,
    evidence_urls: Optional[List[str]] = None,
) -> ExtracurricularActivity:
    _validate_category(category)
    _validate_dates(start_date, end_date)
    row = ExtracurricularActivity(
        user_id=user.id,
        category=category,
        name=name,
        role=role,
        hours_per_week=hours_per_week,
        start_date=start_date,
        end_date=end_date,
        description=description,
        achievements=achievements,
        evidence_urls=evidence_urls,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_activities_for_user(
    db: DBSession, user_id: UUID
) -> Tuple[List[ExtracurricularActivity], int]:
    rows = (
        db.query(ExtracurricularActivity)
        .filter(ExtracurricularActivity.user_id == user_id)
        .order_by(
            ExtracurricularActivity.end_date.is_(None).desc(),
            ExtracurricularActivity.start_date.desc().nullslast(),
            ExtracurricularActivity.created_at.desc(),
        )
        .all()
    )
    return rows, len(rows)


def get_activity(
    db: DBSession, activity_id: UUID
) -> Optional[ExtracurricularActivity]:
    return (
        db.query(ExtracurricularActivity)
        .filter(ExtracurricularActivity.id == activity_id)
        .first()
    )


def update_activity(
    db: DBSession,
    *,
    row: ExtracurricularActivity,
    **fields,
) -> ExtracurricularActivity:
    # Validate category change if provided.
    if "category" in fields and fields["category"] is not None:
        _validate_category(fields["category"])
    # Validate dates considering the merge of new + existing values.
    sd = fields.get("start_date", row.start_date) if "start_date" in fields else row.start_date
    ed = fields.get("end_date", row.end_date) if "end_date" in fields else row.end_date
    _validate_dates(sd, ed)

    for k, v in fields.items():
        if k in {
            "category",
            "name",
            "role",
            "hours_per_week",
            "start_date",
            "end_date",
            "description",
            "achievements",
            "evidence_urls",
        }:
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


def delete_activity(db: DBSession, row: ExtracurricularActivity) -> None:
    db.delete(row)
    db.commit()
