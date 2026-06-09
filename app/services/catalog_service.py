"""Catálogo real (tabla `programs`) para el recomendador IA · Fase C/C1.

Hasta C1, el recomendador (`recommendation_service.filter_catalog`) leía el
catálogo DEMO estático `app/data/ofertas.py` (~17 ofertas falsas) mientras la
tabla `Program` ya tiene el catálogo real importado (2.511 programas, con
`cost_total`/`duration_months`/`budget_tier` NULL = "a confirmar").

Este servicio expone `get_catalog_for_recommender(db)`: lee SOLO columnas
slim de los programas activos (sin los JSON pesados: description_long,
testimonials, syllabus, raw, ...) y mapea cada fila al MISMO shape dict que
consume `filter_catalog` (el shape de una oferta demo). Así el recomendador
no cambia de contrato — solo de fuente.

Nota de acoplamiento: `_TYPE_TO_CATEGORY`, `_BUDGET_TIER_DB_TO_OFERTA` y
`_language_level` son COPIAS deliberadas de `app/api/v1/ofertas.py` — un
servicio no debe importar desde `app/api` (acoplaría servicio→api). Si esos
mapeos cambian allá, hay que actualizarlos acá (son chicos y estables).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession, load_only

from app.db.models import Program

logger = logging.getLogger(__name__)


# COPIA de app/api/v1/ofertas.py::_TYPE_TO_CATEGORY (ver docstring del módulo).
# Program.type viene del Excel import; category es el enum legacy del POC que
# el front (y el scoring del recomendador) ya entienden.
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

# COPIA de app/api/v1/ofertas.py::_BUDGET_TIER_DB_TO_OFERTA.
# budget_tier NULL = "a confirmar" → se deja None (dato honesto, no inventar).
_BUDGET_TIER_DB_TO_OFERTA = {
    "low": "bajo",
    "medium": "medio",
    "high": "alto",
    "premium": "alto",
}


def _language_level(req: Optional[str]) -> str:
    """Heurística para mapear language_requirement (texto libre) a nivel.

    COPIA de app/api/v1/ofertas.py::_language_level.
    """
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


# Columnas slim que sí cargamos (2.511 filas → evitar los JSON pesados).
# area/subject se incluyen además de la lista mínima del diseño: son strings
# cortos y alimentan el match por intereses (vía short_description).
_SLIM_COLUMNS = [
    Program.id,
    Program.program_id,
    Program.slug,
    Program.name,
    Program.country,
    Program.city,
    Program.institution,
    Program.type,
    Program.area,
    Program.subject,
    Program.duration_months,
    Program.cost_total,
    Program.currency,
    Program.budget_tier,
    Program.language_requirement,
    Program.tags,
    Program.scholarships_for_latam,
]

# Cache módulo-level con TTL · evita re-mapear 2.511 filas en cada request.
# Los tests lo bypassean con use_cache=False (o invalidate_catalog_cache()).
_CACHE_TTL_SECONDS = 300  # 5 min
_cache: Dict[str, Any] = {"ts": 0.0, "data": None}


def invalidate_catalog_cache() -> None:
    """Resetea el cache (tests · o tras un import masivo de catálogo)."""
    _cache["ts"] = 0.0
    _cache["data"] = None


def _row_to_oferta_dict(p: Program) -> Dict[str, Any]:
    """Mapea una fila Program (slim) al shape de oferta demo que consume
    `recommendation_service.filter_catalog`.

    None-safety: cost/duration/budget_tier pueden ser NULL ("a confirmar") —
    se propagan como None honestos; el recomendador los maneja (hint
    'unknown' + render 'a confirmar' en el prompt).
    """
    tags = p.tags if isinstance(p.tags, list) else []
    extras = " · ".join(x for x in (p.area, p.subject) if x)
    short_desc = f"{p.name} · {p.institution}, {p.country}"
    if extras:
        short_desc = f"{short_desc} · {extras}"

    return {
        # `id` es lo que filter_catalog usa como program_id recomendable —
        # el UUID de Program, consistente con el `id` que /v1/ofertas expone.
        "id": str(p.id),
        "program_id": p.program_id,
        "slug": p.slug,
        "name": p.name,
        "shortDescription": short_desc,
        "category": _TYPE_TO_CATEGORY.get(p.type, "carrera_completa"),
        "tags": tags,
        "countries": [p.country],
        "cities": [p.city] if p.city else [],
        "duration": {
            "min": p.duration_months,
            "max": p.duration_months,
            "type": "meses",
        },
        "cost": {
            "min": p.cost_total,
            "max": p.cost_total,
            "currency": p.currency or "USD",
        },
        "budgetTier": _BUDGET_TIER_DB_TO_OFERTA.get(p.budget_tier) if p.budget_tier else None,
        "eligibility": {
            "languageRequirement": _language_level(p.language_requirement),
        },
        # F-003 · solo el flag curado (columna). El derivado del JSON
        # `scholarships` (ofertas.py::_has_latam_scholarship) NO aplica aquí
        # porque ese JSON es pesado y no se carga en el query slim.
        "scholarshipsForLatam": bool(p.scholarships_for_latam),
        "active": True,
    }


def get_catalog_for_recommender(
    db: DBSession,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """Catálogo real (programs activos) en shape de oferta demo.

    Devuelve [] si la tabla está vacía (dev sin seed) — el caller decide el
    fallback (recommendation_service cae al catálogo demo con warning).
    """
    now = time.time()
    if (
        use_cache
        and _cache["data"] is not None
        and (now - _cache["ts"]) < _CACHE_TTL_SECONDS
    ):
        return _cache["data"]

    rows = (
        db.query(Program)
        .options(load_only(*_SLIM_COLUMNS))
        .filter(Program.active.is_(True))
        .all()
    )
    data = [_row_to_oferta_dict(p) for p in rows]

    if use_cache and data:
        _cache["ts"] = now
        _cache["data"] = data

    return data
