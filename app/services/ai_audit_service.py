"""AI feedback audit service · M-001 (2026-05-21).

CRUD + aggregates para `ai_recommendation_feedback`. Sin logic de prompt
engineering aquí — solo el almacenamiento y la consulta de feedback. El
loop de mejora del prompt vive aguas arriba (en el equipo del cliente +
nuestro ciclo de iteración).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    AI_FEEDBACK_RATINGS,
    AiRecommendationFeedback,
    User,
)
from app.schemas.ai_audit import (
    AiFeedbackAggregates,
    AiFeedbackOut,
    AiFeedbackTypeAggregate,
)


def create_feedback(
    db: DBSession,
    *,
    rated_by: User,
    recommendation_type: str,
    rating: str,
    recommendation_ref: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    comment: Optional[str] = None,
) -> AiRecommendationFeedback:
    if rating not in AI_FEEDBACK_RATINGS:
        raise ValueError(f"invalid rating: {rating}")
    row = AiRecommendationFeedback(
        recommendation_type=recommendation_type,
        recommendation_ref=recommendation_ref,
        context=context,
        rating=rating,
        comment=comment,
        rated_by_user_id=rated_by.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_feedback(
    db: DBSession,
    *,
    page: int = 1,
    page_size: int = 50,
    recommendation_type: Optional[str] = None,
    rating: Optional[str] = None,
    rated_by_user_id: Optional[UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Tuple[List[AiRecommendationFeedback], int]:
    q = db.query(AiRecommendationFeedback)
    if recommendation_type:
        q = q.filter(AiRecommendationFeedback.recommendation_type == recommendation_type)
    if rating:
        q = q.filter(AiRecommendationFeedback.rating == rating)
    if rated_by_user_id:
        q = q.filter(AiRecommendationFeedback.rated_by_user_id == rated_by_user_id)
    if date_from:
        q = q.filter(AiRecommendationFeedback.created_at >= date_from)
    if date_to:
        q = q.filter(AiRecommendationFeedback.created_at <= date_to)
    total = q.count()
    rows = (
        q.order_by(AiRecommendationFeedback.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def to_out(
    row: AiRecommendationFeedback,
    *,
    rater_name: Optional[str] = None,
    rater_role: Optional[str] = None,
) -> AiFeedbackOut:
    return AiFeedbackOut(
        id=row.id,
        recommendation_type=row.recommendation_type,
        recommendation_ref=row.recommendation_ref,
        context=row.context,
        rating=row.rating,  # type: ignore[arg-type]
        comment=row.comment,
        rated_by_user_id=row.rated_by_user_id,
        rated_by_name=rater_name,
        rated_by_role=rater_role,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def aggregates(
    db: DBSession,
    *,
    days: int = 30,
) -> AiFeedbackAggregates:
    """Compute thumbs_up/down aggregates for the last `days` days."""
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    rows = (
        db.query(AiRecommendationFeedback)
        .filter(AiRecommendationFeedback.created_at >= since)
        .all()
    )
    overall_up = sum(1 for r in rows if r.rating == "thumbs_up")
    overall_down = sum(1 for r in rows if r.rating == "thumbs_down")
    overall_total = overall_up + overall_down
    overall_rate = (overall_up / overall_total * 100.0) if overall_total else 0.0

    # By type
    type_buckets: Dict[str, Dict[str, int]] = {}
    for r in rows:
        b = type_buckets.setdefault(r.recommendation_type, {"up": 0, "down": 0})
        if r.rating == "thumbs_up":
            b["up"] += 1
        elif r.rating == "thumbs_down":
            b["down"] += 1

    by_type: List[AiFeedbackTypeAggregate] = []
    for t, counts in sorted(type_buckets.items()):
        total = counts["up"] + counts["down"]
        rate = (counts["up"] / total * 100.0) if total else 0.0
        by_type.append(
            AiFeedbackTypeAggregate(
                recommendation_type=t,
                thumbs_up=counts["up"],
                thumbs_down=counts["down"],
                total=total,
                positive_rate_pct=round(rate, 1),
            )
        )

    return AiFeedbackAggregates(
        range_from=since,
        range_to=now,
        total_feedback=overall_total,
        overall_thumbs_up=overall_up,
        overall_thumbs_down=overall_down,
        overall_positive_rate_pct=round(overall_rate, 1),
        by_type=by_type,
    )


def to_csv(rows: List[AiRecommendationFeedback], users: Dict[UUID, User]) -> bytes:
    """Render a CSV ready for download. UTF-8 with BOM for Excel."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "created_at",
            "recommendation_type",
            "recommendation_ref",
            "rating",
            "comment",
            "rated_by_email",
            "rated_by_role",
        ]
    )
    for r in rows:
        rater = users.get(r.rated_by_user_id) if r.rated_by_user_id else None
        writer.writerow(
            [
                r.created_at.isoformat(),
                r.recommendation_type,
                r.recommendation_ref or "",
                r.rating,
                (r.comment or "").replace("\n", " ").replace("\r", " "),
                rater.email if rater else "",
                rater.role.value if rater and hasattr(rater.role, "value") else "",
            ]
        )
    # BOM helps Excel detect UTF-8 automatically.
    return ("﻿" + buf.getvalue()).encode("utf-8")
