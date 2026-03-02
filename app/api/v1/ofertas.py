from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, SavedOferta
from app.data.ofertas import (
    get_all_ofertas,
    get_oferta_by_slug,
    get_featured_ofertas,
    filter_ofertas,
)

router = APIRouter(prefix="/ofertas", tags=["Ofertas"])


@router.get("")
def list_ofertas(
    category: Optional[str] = None,
    countries: Optional[str] = None,
    budgetTier: Optional[str] = None,
    durationType: Optional[str] = None,
    minDuration: Optional[int] = None,
    maxDuration: Optional[int] = None,
    languageRequirement: Optional[str] = None,
    searchQuery: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    filters = {}
    if category:
        filters["category"] = category
    if countries:
        filters["countries"] = countries.split(",")
    if budgetTier:
        filters["budgetTier"] = budgetTier
    if durationType:
        filters["durationType"] = durationType
    if minDuration is not None:
        filters["minDuration"] = minDuration
    if maxDuration is not None:
        filters["maxDuration"] = maxDuration
    if languageRequirement:
        filters["languageRequirement"] = languageRequirement
    if searchQuery:
        filters["searchQuery"] = searchQuery

    if filters:
        return filter_ofertas(filters)
    return get_all_ofertas()


@router.get("/featured")
def list_featured(current_user: User = Depends(get_current_user)):
    return get_featured_ofertas()


# --- Saved Ofertas ---

class SaveOfertaRequest(BaseModel):
    oferta_id: str


@router.get("/saved")
def list_saved_ofertas(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """List all saved ofertas for the current user."""
    saved = (
        db.query(SavedOferta)
        .filter(SavedOferta.user_id == current_user.id)
        .order_by(SavedOferta.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(s.id),
            "ofertaId": s.oferta_id,
            "savedAt": s.created_at.isoformat(),
            "status": s.status,
        }
        for s in saved
    ]


@router.post("/saved")
def save_oferta(
    body: SaveOfertaRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Save/bookmark an oferta."""
    existing = (
        db.query(SavedOferta)
        .filter(
            SavedOferta.user_id == current_user.id,
            SavedOferta.oferta_id == body.oferta_id,
        )
        .first()
    )
    if existing:
        return {
            "id": str(existing.id),
            "ofertaId": existing.oferta_id,
            "savedAt": existing.created_at.isoformat(),
            "status": existing.status,
        }

    saved = SavedOferta(
        user_id=current_user.id,
        oferta_id=body.oferta_id,
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return {
        "id": str(saved.id),
        "ofertaId": saved.oferta_id,
        "savedAt": saved.created_at.isoformat(),
        "status": saved.status,
    }


@router.delete("/saved/{oferta_id}")
def unsave_oferta(
    oferta_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Remove a saved oferta."""
    saved = (
        db.query(SavedOferta)
        .filter(
            SavedOferta.user_id == current_user.id,
            SavedOferta.oferta_id == oferta_id,
        )
        .first()
    )
    if saved:
        db.delete(saved)
        db.commit()
    return {"ok": True}


# --- Other endpoints ---

@router.get("/{slug}")
def get_oferta(slug: str, current_user: User = Depends(get_current_user)):
    oferta = get_oferta_by_slug(slug)
    if not oferta:
        return None
    return oferta


@router.get("/compare/{ids}")
def compare_ofertas(ids: str, current_user: User = Depends(get_current_user)):
    id_list = ids.split(",")
    all_ofertas = get_all_ofertas()
    return [o for o in all_ofertas if o["id"] in id_list]
