"""Snapshot API endpoints."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import Snapshot, Route, User, VocationalTestResult
from app.schemas.journey import SnapshotResponse
from app.services.journey_service import get_session
from app.services.ai_service import derive_motivations, derive_constraints
from app.api.v1.auth import get_current_user
from app.core.access import assert_session_access

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/{session_id}", response_model=List[SnapshotResponse])
def get_snapshots(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all snapshots for a session.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

    snapshots = (
        db.query(Snapshot)
        .filter(Snapshot.session_id == session_id)
        .order_by(Snapshot.created_at.desc())
        .all()
    )

    return snapshots


@router.post("/{session_id}", response_model=SnapshotResponse)
def create_snapshot(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a new snapshot.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    session = assert_session_access(session_id, current_user, db)

    answers = session.answers or {}

    # Get active routes
    routes = (
        db.query(Route)
        .filter(Route.session_id == session_id)
        .all()
    )

    routes_data = [
        {
            "id": str(r.id),
            "key": r.key,
            "name": r.name,
            "why": r.why,
            "what_it_looks_like": r.what_it_looks_like,
            "next_step": r.next_step,
            "status": r.status.value,
            "is_primary": r.is_primary,
        }
        for r in routes
    ]

    # Derive tags
    motivations = derive_motivations(answers)
    constraints = derive_constraints(answers)
    derived_tags = motivations + constraints

    # Include English test and vocational test data in profile
    profile_data = dict(answers)
    if session.user_id:
        user = db.query(User).filter(User.id == session.user_id).first()
        if user:
            profile_data["english_cefr_level"] = user.english_cefr_level
            profile_data["english_test_completed"] = user.english_test_completed

            voc_results = (
                db.query(VocationalTestResult)
                .filter(VocationalTestResult.user_id == user.id)
                .all()
            )
            profile_data["vocational_results"] = [
                {"test_id": vr.test_id, "scores": vr.scores}
                for vr in voc_results
            ]

    # Create snapshot
    snapshot = Snapshot(
        session_id=session_id,
        profile=profile_data,
        routes=routes_data,
        derived_tags=derived_tags,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return snapshot


@router.get("/{session_id}/latest", response_model=SnapshotResponse)
def get_latest_snapshot(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the latest snapshot for a session.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

    snapshot = (
        db.query(Snapshot)
        .filter(Snapshot.session_id == session_id)
        .order_by(Snapshot.created_at.desc())
        .first()
    )

    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshots found")

    return snapshot
