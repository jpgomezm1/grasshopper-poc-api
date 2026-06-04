"""Student-facing offers (`/v1/ofertas`) · GH-CATALOG-UNIFY 2026-05-05.

Hasta antes de este sprint, este router leía de `app.data.ofertas` (un módulo
con datos hardcoded del POC original). El catálogo real que el super_admin
gestiona está en la tabla `programs` (Program model · 50+ items con seed).
La inconsistencia hacía que el student viera un catálogo distinto del admin.

Este módulo ahora lee siempre de la tabla `programs` y mapea cada `Program`
al contrato `Oferta` que espera el frontend (src/lib/types/ofertas.ts).
El módulo `app.data.ofertas` queda como dead code · puede borrarse en sprint
de cleanup.
"""
from __future__ import annotations

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import Program, SavedOferta, User

router = APIRouter(prefix="/ofertas", tags=["Ofertas"])


# ---------------------------------------------------------------------------
# Mapping helpers · Program → Oferta contract
# ---------------------------------------------------------------------------

# Program.type uses values from Excel import (pregrado · maestria · mba · etc.)
# Oferta.category uses the legacy POC enum the frontend already understands.
_TYPE_TO_CATEGORY = {
    "pregrado": "carrera_completa",
    "maestria": "carrera_completa",
    "mba": "carrera_completa",
    "posgrado": "carrera_completa",
    "doctorado": "carrera_completa",
    "especializacion": "carrera_completa",
    "diplomado": "certificacion_corta",
    "curso_corto": "certificacion_corta",
    "bootcamp": "certificacion_corta",
    "vacacional": "curso_idiomas",
    "intercambio": "semestre_academico",
}

_CATEGORY_TO_TYPES = {
    "carrera_completa": [
        "pregrado",
        "maestria",
        "mba",
        "posgrado",
        "doctorado",
        "especializacion",
    ],
    "certificacion_corta": ["diplomado", "curso_corto", "bootcamp"],
    "curso_idiomas": ["vacacional"],
    "semestre_academico": ["intercambio"],
    "work_travel": [],  # No hay equivalente en programs
    "practicas": [],
    "voluntariado": [],
}

_BUDGET_TIER_DB_TO_OFERTA = {
    "low": "bajo",
    "medium": "medio",
    "high": "alto",
    "premium": "alto",
}

_BUDGET_TIER_OFERTA_TO_DB = {
    "bajo": ["low"],
    "medio": ["medium"],
    "alto": ["high", "premium"],
}


def _language_level(req: Optional[str]) -> str:
    """Heurística para mapear language_requirement (texto libre) a nivel."""
    if not req:
        return "ninguno"
    s = req.lower()
    if any(x in s for x in ["c1", "c2", "avanzado", "advanced", "native", "nativo"]):
        return "avanzado"
    if any(x in s for x in ["b1", "b2", "intermedio", "intermediate"]):
        return "intermedio"
    if any(x in s for x in ["a1", "a2", "básico", "basico", "basic"]):
        return "basico"
    return "ninguno"


_DEFAULT_FEATURED_IMAGE = (
    "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=1200&h=600&fit=crop"
)


def _has_latam_scholarship(p: Program) -> bool:
    """F-003 · ¿la oferta tiene beca curada para LatAm?

    Fuente primaria: el flag booleano `scholarships_for_latam` (curado por el
    admin en el catálogo). Como respaldo, se deriva del JSON `scholarships` si
    alguna entrada está marcada elegible para LatAm — así el flag se enciende
    solo cuando llegue ese dato (vía import/curación), sin tocar nada más.
    """
    if p.scholarships_for_latam is True:
        return True
    sch = p.scholarships if isinstance(p.scholarships, list) else []
    for s in sch:
        if isinstance(s, dict) and (s.get("latam_eligible") or s.get("for_latam")):
            return True
    return False


def _program_to_oferta(p: Program) -> dict:
    """Map a Program row to the Oferta schema (frontend contract)."""
    images = p.images if isinstance(p.images, list) else []
    image_urls = [img.get("url") for img in images if isinstance(img, dict) and img.get("url")]
    featured_image = image_urls[0] if image_urls else _DEFAULT_FEATURED_IMAGE

    short_desc = ""
    if p.description_long:
        short_desc = (
            p.description_long[:197] + "..."
            if len(p.description_long) > 200
            else p.description_long
        )
    else:
        short_desc = f"{p.name} · {p.institution}, {p.country}"

    deadlines: list = []
    if isinstance(p.admission_dates, list):
        for d in p.admission_dates:
            if isinstance(d, dict) and d.get("date"):
                deadlines.append(
                    {
                        "name": d.get("name") or "Convocatoria",
                        "date": d.get("date"),
                        "type": d.get("type") or "application",
                    }
                )

    return {
        "id": str(p.id),
        "slug": p.slug,
        "name": p.name,
        "shortDescription": short_desc,
        "fullDescription": p.description_long
        or f"Programa {p.name} ofrecido por {p.institution} en {p.country}.",
        "highlights": p.highlights if isinstance(p.highlights, list) else [],
        "category": _TYPE_TO_CATEGORY.get(p.type, "carrera_completa"),
        "tags": p.tags if isinstance(p.tags, list) else [],
        "provider": {
            "id": p.program_id,
            "name": p.institution,
            "logo": p.institution_logo_url or "",
            "verified": True,
        },
        "countries": [p.country],
        "cities": [p.city] if p.city else [],
        # cost/duration/budgetTier pueden ser NULL ("a confirmar") cuando la
        # oferta viene del catálogo real sin datos financieros (GH-CATALOG-REAL).
        "duration": {
            "min": p.duration_months,
            "max": p.duration_months,
            "type": "meses",
        },
        "cost": {
            "min": p.cost_total,
            "max": p.cost_total,
            "currency": p.currency,
            "includes": [],
            "excludes": [],
        },
        "budgetTier": _BUDGET_TIER_DB_TO_OFERTA.get(p.budget_tier) if p.budget_tier else None,
        "eligibility": {
            "requiredDocuments": [],
            "languageRequirement": _language_level(p.language_requirement),
            "languageTests": [p.language_requirement_detail]
            if p.language_requirement_detail
            else [],
        },
        "startDates": [],
        "deadlines": deadlines,
        "featuredImage": featured_image,
        "media": [{"type": "image", "url": u} for u in image_urls],
        "featured": False,
        "active": p.active,
        # F-003 · beca curada para LatAm (flag o derivado del JSON scholarships)
        "scholarshipsForLatam": _has_latam_scholarship(p),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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
    scholarshipsForLatam: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    q = db.query(Program).filter(Program.active == True)  # noqa: E712

    if category:
        types = _CATEGORY_TO_TYPES.get(category)
        if types:
            q = q.filter(Program.type.in_(types))
        else:
            # categoría sin equivalente en programs (work_travel, etc.) → vacío
            return []

    if countries:
        country_list = [c.strip() for c in countries.split(",") if c.strip()]
        if country_list:
            q = q.filter(Program.country.in_(country_list))

    if budgetTier:
        db_tiers = _BUDGET_TIER_OFERTA_TO_DB.get(budgetTier)
        if db_tiers:
            q = q.filter(Program.budget_tier.in_(db_tiers))

    # Duration filters · Program.duration_months es la unidad canónica
    if minDuration is not None:
        # Si el cliente pide minDuration en semanas, convertimos aproximado
        if durationType == "semanas":
            q = q.filter(Program.duration_months >= max(1, minDuration // 4))
        elif durationType == "semestres":
            q = q.filter(Program.duration_months >= minDuration * 6)
        else:
            q = q.filter(Program.duration_months >= minDuration)

    if maxDuration is not None:
        if durationType == "semanas":
            q = q.filter(Program.duration_months <= max(1, maxDuration // 4))
        elif durationType == "semestres":
            q = q.filter(Program.duration_months <= maxDuration * 6)
        else:
            q = q.filter(Program.duration_months <= maxDuration)

    if searchQuery:
        like = f"%{searchQuery}%"
        q = q.filter(
            or_(
                Program.name.ilike(like),
                Program.institution.ilike(like),
                Program.country.ilike(like),
                Program.city.ilike(like),
                Program.subject.ilike(like),
                Program.area.ilike(like),
            )
        )

    programs = q.order_by(Program.name.asc()).all()
    ofertas = [_program_to_oferta(p) for p in programs]

    # languageRequirement filter post-mapping (porque la columna es texto libre)
    if languageRequirement:
        ofertas = [
            o
            for o in ofertas
            if o["eligibility"]["languageRequirement"] == languageRequirement
        ]

    # F-003 · filtro de becas LatAm post-mapping (el flag se deriva, no es columna pura)
    if scholarshipsForLatam is not None:
        ofertas = [o for o in ofertas if o["scholarshipsForLatam"] == scholarshipsForLatam]

    return ofertas


@router.get("/featured")
def list_featured(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Top 6 programs activos · ordenados por institution + name (placeholder
    hasta que existe campo `featured` en Program)."""
    programs = (
        db.query(Program)
        .filter(Program.active == True)  # noqa: E712
        .order_by(Program.institution.asc(), Program.name.asc())
        .limit(6)
        .all()
    )
    return [_program_to_oferta(p) for p in programs]


# --- Saved Ofertas ---


class SaveOfertaRequest(BaseModel):
    oferta_id: str


@router.get("/saved")
def list_saved_ofertas(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
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

    saved = SavedOferta(user_id=current_user.id, oferta_id=body.oferta_id)
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


# --- Detail · slug-based ---


@router.get("/{slug}")
def get_oferta(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    p = db.query(Program).filter(Program.slug == slug).first()
    if not p:
        return None
    return _program_to_oferta(p)


# --- Compare · accepts UUIDs (Program.id) or slugs ---


@router.get("/compare/{ids}")
def compare_ofertas(
    ids: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    if not id_list:
        return []

    # Soporta UUIDs y slugs en el mismo path
    uuid_ids: List[UUID] = []
    slug_ids: List[str] = []
    for raw in id_list:
        try:
            uuid_ids.append(UUID(raw))
        except ValueError:
            slug_ids.append(raw)

    q = db.query(Program)
    conds = []
    if uuid_ids:
        conds.append(Program.id.in_(uuid_ids))
    if slug_ids:
        conds.append(Program.slug.in_(slug_ids))
    if not conds:
        return []
    q = q.filter(or_(*conds))
    return [_program_to_oferta(p) for p in q.all()]
