"""Routes API endpoints."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import Route, RouteStatus
from app.schemas.journey import RouteResponse, RouteStatusUpdate
from app.services.journey_service import get_session

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("/{session_id}", response_model=List[RouteResponse])
def get_routes(
    session_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Get all routes for a session."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    routes = (
        db.query(Route)
        .filter(Route.session_id == session_id)
        .order_by(Route.is_primary.desc(), Route.created_at.desc())
        .all()
    )

    return routes


@router.post("/{session_id}/{route_id}/status", response_model=RouteResponse)
def update_route_status(
    session_id: UUID,
    route_id: UUID,
    status_update: RouteStatusUpdate,
    db: DBSession = Depends(get_db),
):
    """Update route status (active/paused/primary)."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    route = (
        db.query(Route)
        .filter(Route.id == route_id, Route.session_id == session_id)
        .first()
    )
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    if status_update.status is not None:
        route.status = RouteStatus(status_update.status)
        # If pausing, can't be primary
        if status_update.status == "paused":
            route.is_primary = False

    if status_update.is_primary is not None:
        if status_update.is_primary:
            # Unset other primaries
            db.query(Route).filter(
                Route.session_id == session_id,
                Route.id != route_id,
            ).update({"is_primary": False})
        route.is_primary = status_update.is_primary

    db.commit()
    db.refresh(route)

    return route


@router.post("/{session_id}/{route_id}/primary", response_model=RouteResponse)
def set_route_primary(
    session_id: UUID,
    route_id: UUID,
    db: DBSession = Depends(get_db),
):
    """Set a route as the primary route."""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    route = (
        db.query(Route)
        .filter(Route.id == route_id, Route.session_id == session_id)
        .first()
    )
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    # Unset all other primaries
    db.query(Route).filter(
        Route.session_id == session_id,
        Route.id != route_id,
    ).update({"is_primary": False})

    route.is_primary = True
    route.status = RouteStatus.ACTIVE

    db.commit()
    db.refresh(route)

    return route
