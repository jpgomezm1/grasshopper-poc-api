"""Routes API endpoints.

Sprint 6 update (BE-09): authenticated students with cached recommendations
will see those programs surface as Routes in the legacy journey UI. The
underlying source of truth becomes `RecommendedProgram` (filtered against
the Mentoring catalog), instead of free-form AI-generated routes. The
free-form fallback is preserved for anonymous sessions / users without a
consolidated profile yet.
"""

from datetime import datetime
from uuid import UUID, uuid4
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import (
    ConsolidatedProfileCache,
    Route,
    RouteStatus,
    Session,
    User,
)
from app.schemas.journey import RouteResponse, RouteStatusUpdate
from app.services.journey_service import get_session
from app.api.v1.auth import get_current_user
from app.core.access import assert_session_access

router = APIRouter(prefix="/routes", tags=["routes"])


def _routes_from_cached_recommendations(
    cache: ConsolidatedProfileCache,
    session_id: UUID,
) -> List[Route]:
    """Map cached `recommendations_data` (JSONB) → list of Route-like objects
    for the legacy GET endpoint. These are NOT persisted unless the journey
    explicitly saves them. The shape matches `RouteResponse`.
    """
    out: List[Route] = []
    recs = cache.recommendations_data or []
    for idx, r in enumerate(recs):
        try:
            route = Route(
                id=uuid4(),
                session_id=session_id,
                key=str(r.get("program_id") or f"rec_{idx}"),
                name=r.get("program_name") or "Programa recomendado",
                why=r.get("why_match") or "",
                what_it_looks_like=(
                    f"Categoría: {(r.get('budget_tier') or '—')} · "
                    f"Países: {', '.join(r.get('countries') or []) or '—'}"
                ),
                next_step=(
                    f"Revisa el programa en el catálogo "
                    f"({(r.get('program_slug') or r.get('program_id') or '')})."
                ),
                status=RouteStatus.ACTIVE,
                is_primary=(idx == 0),
            )
            # Hack: SQLAlchemy needs created_at/updated_at on the unpersisted
            # instance for the response_model serializer. Set them in-memory.
            route.created_at = cache.generated_at or datetime.utcnow()
            route.updated_at = cache.updated_at or datetime.utcnow()
            out.append(route)
        except Exception:
            continue
    return out


@router.get("/{session_id}", response_model=List[RouteResponse])
def get_routes(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all routes for a session.

    GH-F1-IDOR: requires authentication + session ownership.

    Sprint 6: if the session has an authenticated user with a cached
    consolidated profile, surface RecommendedProgram[] as the canonical
    list of routes. Falls back to whatever has been persisted in the
    `routes` table for backwards compatibility.
    """
    session = assert_session_access(session_id, current_user, db)

    # Try cached recommendations first (new in S6 · BE-09)
    if session.user_id:
        cache: Optional[ConsolidatedProfileCache] = (
            db.query(ConsolidatedProfileCache)
            .filter(ConsolidatedProfileCache.user_id == session.user_id)
            .first()
        )
        if (
            cache
            and cache.invalidated_at is None
            and cache.recommendations_data
            and isinstance(cache.recommendations_data, list)
            and len(cache.recommendations_data) > 0
        ):
            return _routes_from_cached_recommendations(cache, session_id)

    # Fallback · legacy behavior (anonymous · or user without recs yet)
    routes = (
        db.query(Route)
        .filter(Route.session_id == session_id)
        .order_by(Route.is_primary.desc(), Route.created_at.desc())
        .all()
    )

    return routes


@router.post("/{session_id}/generate", response_model=List[RouteResponse])
def generate_routes_for_session(
    session_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera rutas a partir de los tests, **sin exigir terminar el journey**.

    Verónica hizo tests, abandonó el journey a mitad y vio "Rutas" vacía:
    *"¿por qué todavía no sale nada?"*. Hasta §1 las rutas sólo existían al
    llegar al paso 16 de 17, así que su pantalla estaba vacía por diseño.

    **Por qué un POST y no generar dentro del GET.** Meter una llamada de IA en
    un GET lo vuelve lento e impredecible; el proyecto ya resuelve esto al lado
    con las recomendaciones (`recommendations.py`), que generan aparte. El GET
    sigue siendo de sólo lectura.

    Requiere **al menos un test**: sin eso las rutas serían las mismas que ya
    salen del journey y no aportarían nada nuevo.
    """
    from app.services.ai_service import generate_routes
    from app.services.recommendation_service import user_has_tests
    from app.services.test_interpretation_service import format_tests_for_prompt

    session = assert_session_access(session_id, current_user, db)

    if not user_has_tests(db, current_user):
        raise HTTPException(
            status_code=409,
            detail="no_tests_yet",
        )

    tests_block = format_tests_for_prompt(db, current_user.id)
    salida = generate_routes(
        session.answers or {},
        str(session.id),
        db=db,
        user_id=current_user.id,
        onboarding=current_user.onboarding_answers or {},
        tests_block=tests_block,
    )

    # Se reemplazan las rutas previas de esta sesión: son la versión sin tests
    # de lo mismo, y dejarlas conviviendo le mostraría dos juegos de rutas
    # contradictorios sin forma de saber cuál manda.
    db.query(Route).filter(Route.session_id == session.id).delete()

    creadas: List[Route] = []
    for idx, r in enumerate(salida.routes):
        fila = Route(
            session_id=session.id,
            key=r.key,
            name=r.name,
            why=r.why,
            what_it_looks_like=r.what_it_looks_like,
            next_step=r.next_step,
            evidence=list(r.evidence or []),
            is_generic=bool(r.is_generic),
            status=RouteStatus.ACTIVE,
            is_primary=(idx == 0),
        )
        db.add(fila)
        creadas.append(fila)
    db.commit()
    for fila in creadas:
        db.refresh(fila)

    return creadas


@router.post("/{session_id}/{route_id}/status", response_model=RouteResponse)
def update_route_status(
    session_id: UUID,
    route_id: UUID,
    status_update: RouteStatusUpdate,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update route status (active/paused/primary).

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

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
    current_user: User = Depends(get_current_user),
):
    """Set a route as the primary route.

    GH-F1-IDOR: requires authentication + session ownership.
    """
    assert_session_access(session_id, current_user, db)

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
