"""Journey business logic service."""

import hashlib
import json
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    Session,
    SessionEvent,
    JournalEntry,
    Route,
    ProfileVersion,
    JourneyStage as DBJourneyStage,
    JournalEntryType,
    RouteStatus,
    User,
)
from app.core.state_machine import (
    get_step,
    get_next_step,
    calculate_progress,
    get_actions_for_step,
    validate_answer,
    ViewType,
    JourneyStage,
    JOURNEY_STEPS,
)
from app.schemas.session import (
    JourneyResponse,
    ProgressInfo,
    ProfilePreview,
    JournalPreviewEntry,
    SidePanel,
    JourneyStage as SchemaJourneyStage,
    ViewType as SchemaViewType,
)
from app.services.ai_service import (
    generate_empathy_reflection,
    generate_partial_summary,
    generate_synthesis,
    generate_routes,
    derive_motivations,
    derive_constraints,
)


# B-02 · Mapeo de valores del onboarding (users.onboarding_answers, códigos)
# a los valores que espera el Journey (sessions.answers, textos de opción).
# Solo campos que se solapan, para no volver a preguntarlos en el Journey.
_ONBOARDING_LIFE_STAGE_MAP = {
    # R6-ON-1b · Antes solo existía `high_school` = "En el colegio" en la UI, pero aquí
    # se traducía a "Terminando el colegio": un estudiante de 9° le decía a la IA que
    # estaba a punto de graduarse. Verónica pidió separarlo dos veces en la reunión
    # ("estoy en el colegio o estoy en último año", "Susana de 11 grados").
    # `high_school` conserva su valor y su significado — ahora sí es cierto.
    "high_school_early": "En el colegio",
    "high_school": "Terminando el colegio",
    "university": "En la universidad",
    "recent_grad": "En transición / no seguro",
    "working": "Ya trabajando",
    "career_change": "En transición / no seguro",
}
_ONBOARDING_TIMELINE_MAP = {
    "asap": "En los próximos meses",
    "6_months": "En los próximos meses",
    "1_year": "En 1 año",
    "2_years": "Más adelante (solo explorando)",
    "exploring": "Más adelante (solo explorando)",
}


def seed_answers_from_onboarding(onboarding: Optional[dict]) -> dict:
    """Deriva answers del Journey a partir de las respuestas del onboarding.

    Evita que el Journey vuelva a preguntar etapa de vida y horizonte de
    tiempo que el onboarding ya capturó (B-02). Devuelve un dict con claves
    del Journey (camelCase) solo para los valores mapeables.
    """
    seeded: dict = {}
    if not onboarding:
        return seeded
    life_stage = onboarding.get("life_stage")
    if life_stage in _ONBOARDING_LIFE_STAGE_MAP:
        seeded["lifeStage"] = _ONBOARDING_LIFE_STAGE_MAP[life_stage]
    timeline = onboarding.get("timeline")
    if timeline in _ONBOARDING_TIMELINE_MAP:
        seeded["timeHorizon"] = _ONBOARDING_TIMELINE_MAP[timeline]
    return seeded


def seed_session_from_onboarding(session: Session, onboarding: Optional[dict]) -> bool:
    """Aplica el seed del onboarding a una sesión (B-02).

    Se usa sobre la sesión VINCULADA al usuario (la que el Journey realmente
    consume), no sobre una anónima. Rellena `answers`/`completed_steps` con los
    valores mapeados del onboarding SIN pisar respuestas del Journey ya dadas,
    para no romper una sesión en progreso si el onboarding se re-ejecuta.

    Construye dicts NUEVOS para que SQLAlchemy detecte el cambio (las columnas
    JSON sin MutableDict no rastrean mutaciones in-place). Devuelve True si
    modificó algo.
    """
    seeded = seed_answers_from_onboarding(onboarding)
    if not seeded:
        return False
    answers = dict(session.answers or {})
    completed = list(session.completed_steps or [])
    changed = False
    for key, value in seeded.items():
        if not answers.get(key):  # no pisar lo que el Journey ya respondió
            answers[key] = value
            if key not in completed:
                completed.append(key)
            changed = True
    if changed:
        session.answers = answers
        session.completed_steps = completed
        # Auditoría R5 · si la sesión estaba PARADA exactamente en un paso que
        # acabamos de sembrar (p.ej. re-onboarding con journey a medio camino),
        # avanzar al siguiente paso pendiente — si no, el paso se re-pregunta
        # aunque ya tenga respuesta.
        current = get_step(session.current_step)
        if current is not None and current.save_to and answers.get(current.save_to):
            nxt = get_next_step(session.current_step, answers)
            if nxt:
                session.current_step = nxt
                nxt_step = get_step(nxt)
                if nxt_step:
                    session.current_stage = DBJourneyStage(nxt_step.stage.value)
    return changed


# ── R5 (auditoría Journey) · cache del contenido IA por paso ────────────────
# Lo que la usuaria VIO es lo que se selecciona, se journalea y se re-renderiza.
# Sin esto, cada GET del paso regeneraba con otra llamada IA (contenido
# distinto en cada refresh, costo x N) y la selección de ruta comparaba el
# route_key clickeado contra un set recién generado → elección perdida.

MAX_OPEN_TEXT_LEN = 5000  # tope de respuestas libres (protege prompts y DB)


def _ai_inputs_hash(answers: Optional[dict], onboarding: Optional[dict]) -> str:
    """Hash estable de los inputs que alimentan la generación IA de un paso.

    Si la usuaria navega atrás y cambia una respuesta, el hash cambia y el
    contenido se regenera (no servimos una síntesis desactualizada).
    """
    payload = json.dumps(
        {"a": answers or {}, "o": onboarding or {}},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _ai_cache_get(session: Session, key: str, inputs_hash: str) -> Optional[dict]:
    cache = session.ai_content or {}
    entry = cache.get(key)
    if isinstance(entry, dict) and entry.get("hash") == inputs_hash:
        return entry.get("data")
    return None


def _ai_cache_get_any(session: Session, key: str) -> Optional[dict]:
    """Última versión guardada aunque el hash no coincida (fallback de
    selección: mejor la lista que la usuaria vio que ninguna)."""
    cache = session.ai_content or {}
    entry = cache.get(key)
    return entry.get("data") if isinstance(entry, dict) else None


def _ai_cache_put(
    db: DBSession, session: Session, key: str, inputs_hash: str, data: dict
) -> None:
    # dict NUEVO → SQLAlchemy detecta el cambio (Column(JSON) sin MutableDict)
    cache = dict(session.ai_content or {})
    cache[key] = {"hash": inputs_hash, "data": data}
    session.ai_content = cache
    db.commit()


def create_session(db: DBSession, seeded: Optional[dict] = None) -> Session:
    """Create a new journey session.

    `seeded` pre-llena `answers` (p.ej. lifeStage/timeHorizon derivados del
    onboarding) y marca esos pasos como completados, para que el Journey no
    vuelva a preguntarlos (B-02).
    """
    session = Session(
        answers=seeded or {},
        completed_steps=list(seeded.keys()) if seeded else [],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: DBSession, session_id: UUID) -> Optional[Session]:
    """Get a session by ID."""
    return db.query(Session).filter(Session.id == session_id).first()


def get_side_panel_data(db: DBSession, session: Session) -> SidePanel:
    """Build side panel data from session."""
    answers = session.answers or {}

    # Build profile preview · B-022 · emit 6 camelCase fields to match the
    # FE's JourneyAnswers interface. The FE counts these 6 for completion.
    profile_preview = ProfilePreview(
        lifeStage=answers.get("lifeStage"),
        timeHorizon=answers.get("timeHorizon"),
        interestType=answers.get("interestType"),
        clarityLevel=answers.get("clarityLevel"),
        languageLevel=answers.get("languageLevel"),
        budgetBand=answers.get("budgetBand"),
        motivations=derive_motivations(answers) if answers else [],
        constraints=derive_constraints(answers) if answers else [],
    )

    # Get recent journal entries
    journal_entries = (
        db.query(JournalEntry)
        .filter(JournalEntry.session_id == session.id)
        .order_by(JournalEntry.created_at.desc())
        .limit(5)
        .all()
    )

    journal_preview = [
        JournalPreviewEntry(
            id=str(entry.id),
            content=entry.content[:100] + "..." if len(entry.content) > 100 else entry.content,
            type=entry.entry_type.value,
            timestamp=entry.created_at,
        )
        for entry in journal_entries
    ]

    return SidePanel(
        profile_preview=profile_preview,
        journal_preview=journal_preview,
    )


def build_journey_response(
    db: DBSession,
    session: Session,
) -> JourneyResponse:
    """Build the complete journey response for the current step."""
    step = get_step(session.current_step)
    if not step:
        step = JOURNEY_STEPS[0]

    progress = calculate_progress(session.current_step)
    actions = get_actions_for_step(session.current_step)
    side_panel = get_side_panel_data(db, session)

    # Base response
    response = JourneyResponse(
        session_id=session.id,
        stage=SchemaJourneyStage(step.stage.value),
        step_id=step.id,
        view_type=SchemaViewType(step.view_type.value),
        title=step.title,
        question=step.question,
        text=step.text,
        placeholder=step.placeholder,
        options=step.options,
        max_select=step.max_select,
        helper=step.helper,
        progress=ProgressInfo(**progress),
        side_panel=side_panel,
        actions=actions,
    )

    # Add AI-generated content based on step type
    answers = session.answers or {}

    # R4 · contexto del onboarding para los pasos IA: lo que el usuario YA
    # contó al registrarse (pasiones, hobbies, metas) se refleja en las
    # respuestas de Hop ("ya me contaste que…") en vez de sonar genérico.
    # Solo se consulta en pasos con IA; None si la sesión es anónima.
    onboarding = None
    if session.user_id is not None and step.view_type in (
        ViewType.REFLECTION,
        ViewType.ROUTES_PICKER,
    ):
        owner = db.query(User).filter(User.id == session.user_id).first()
        onboarding = owner.onboarding_answers if owner else None

    if step.view_type == ViewType.REFLECTION:
        if step.id == "empathy":
            why_here = answers.get("whyHere", "")
            if why_here:
                h = _ai_inputs_hash({"whyHere": why_here}, onboarding)
                cached = _ai_cache_get(session, "empathy", h)
                if cached is None:
                    reflection = generate_empathy_reflection(
                        why_here,
                        str(session.id),
                        db=db,
                        user_id=session.user_id,
                        onboarding=onboarding,
                    )
                    cached = {"text": reflection.text}
                    _ai_cache_put(db, session, "empathy", h, cached)
                response.reflection_content = cached["text"]
        elif step.id == "synthesis":
            h = _ai_inputs_hash(answers, onboarding)
            cached = _ai_cache_get(session, "synthesis", h)
            if cached is None:
                synthesis = generate_synthesis(
                    answers,
                    str(session.id),
                    db=db,
                    user_id=session.user_id,
                    onboarding=onboarding,
                )
                cached = {
                    "text": synthesis.text,
                    "chips": [
                        {"label": c.label, "value": c.value} for c in synthesis.chips
                    ],
                    "key_motivations": synthesis.key_motivations,
                    "constraints": synthesis.constraints,
                }
                _ai_cache_put(db, session, "synthesis", h, cached)
            response.synthesis_text = cached["text"]
            response.synthesis_chips = cached["chips"]

    elif step.view_type == ViewType.PARTIAL_SUMMARY:
        summary = generate_partial_summary(answers, str(session.id))
        response.partial_summary_bullets = summary.bullets
        response.partial_summary_motivation = summary.motivation

    elif step.view_type == ViewType.ROUTES_PICKER:
        h = _ai_inputs_hash(answers, onboarding)
        cached = _ai_cache_get(session, "routes", h)
        if cached is None:
            routes_output = generate_routes(
                answers,
                str(session.id),
                db=db,
                user_id=session.user_id,
                onboarding=onboarding,
            )
            cached = {
                "routes": [
                    {
                        "key": r.key,
                        "name": r.name,
                        "why": r.why,
                        "what_it_looks_like": r.what_it_looks_like,
                        "next_step": r.next_step,
                    }
                    for r in routes_output.routes
                ]
            }
            _ai_cache_put(db, session, "routes", h, cached)
        response.suggested_routes = [
            {
                "key": r["key"],
                "name": r["name"],
                "why": r["why"],
                "whatItLooksLike": r["what_it_looks_like"],
                "nextStep": r["next_step"],
            }
            for r in cached["routes"]
        ]

    elif step.view_type == ViewType.NEXT_STEP:
        # Auditoría R5 · el cierre no debe afirmar "tu ruta está guardada" si
        # la sesión llegó aquí sin elegir ruta (pausa/edge): copy honesto.
        if not (session.selected_routes or []):
            response.text = (
                "Tu progreso quedó guardado. Cuando quieras, vuelve al paso de "
                "rutas para elegir la tuya."
            )

    return response


def process_event(
    db: DBSession,
    session: Session,
    event_type: str,
    step_id: str,
    payload: Optional[Dict[str, Any]],
) -> JourneyResponse:
    """
    Process a journey event and advance the flow.

    Args:
        db: Database session
        session: Current session
        event_type: Type of event (answer, navigation, selection)
        step_id: Step where the event occurred
        payload: Event data

    Returns:
        Updated journey response
    """
    step = get_step(step_id)
    if not step:
        return build_journey_response(db, session)

    # Auditoría R5 · answer/selection solo aplican sobre el paso ACTUAL de la
    # sesión. Antes, un step_id arbitrario (front desincronizado, reintento
    # con estado viejo, request manual) podía saltar pasos y hasta completar
    # el journey vacío → is_completed=True + sync a Bitrix con perfil vacío.
    # Un mismatch es un no-op idempotente: devolvemos el estado actual para
    # que el cliente se re-sincronice.
    if event_type in ("answer", "selection") and step_id != session.current_step:
        return build_journey_response(db, session)

    # Log the event
    event = SessionEvent(
        session_id=session.id,
        event_type=event_type,
        step_id=step_id,
        payload=payload,
    )
    db.add(event)

    answers = dict(session.answers) if session.answers else {}

    # Process based on event type
    if event_type == "answer":
        # Validate and save answer (None payload treated as empty dict for steps without input)
        effective_payload = payload if payload is not None else {}
        if validate_answer(step_id, effective_payload):
            if step.save_to:
                value = effective_payload.get("value")
                # Auditoría R5 · tope a texto libre: protege los prompts IA y
                # la DB de payloads sin límite (voz transcrita larga, abuso).
                if isinstance(value, str) and len(value) > MAX_OPEN_TEXT_LEN:
                    value = value[:MAX_OPEN_TEXT_LEN]
                answers[step.save_to] = value
                session.answers = answers

            # Add step to completed
            completed = list(session.completed_steps) if session.completed_steps else []
            if step_id not in completed:
                completed.append(step_id)
                session.completed_steps = completed

            # Generate journal entries for reflections
            if step.view_type in [ViewType.REFLECTION, ViewType.PARTIAL_SUMMARY]:
                _create_journal_entry_for_reflection(db, session, step_id, answers)

            # Advance to next step (salta pasos ya respondidos, p.ej. sembrados
            # desde el onboarding · B-02)
            next_step_id = get_next_step(step_id, answers)
            if next_step_id:
                session.current_step = next_step_id
                next_step = get_step(next_step_id)
                if next_step:
                    session.current_stage = DBJourneyStage(next_step.stage.value)

    elif event_type == "navigation":
        # Handle back navigation
        direction = payload.get("direction") if payload else None
        if direction == "back":
            # Find previous step
            completed = list(session.completed_steps) if session.completed_steps else []
            if completed:
                prev_step_id = completed[-1]
                session.current_step = prev_step_id
                prev_step = get_step(prev_step_id)
                if prev_step:
                    session.current_stage = DBJourneyStage(prev_step.stage.value)

    elif event_type == "selection":
        # Handle route selection
        if step_id == "routes" and payload:
            route_key = payload.get("route_key")
            if route_key:
                # Auditoría R5 · solo avanzar si la selección se registró de
                # verdad (la key existe en las rutas que la usuaria VIO).
                # Antes se avanzaba y completaba el journey aunque la ruta
                # no matcheara → sesión "completada" sin ruta, sin error.
                handled = _handle_route_selection(db, session, route_key, answers)
                if handled:
                    next_step_id = get_next_step(step_id)
                    if next_step_id:
                        session.current_step = next_step_id
                        next_step = get_step(next_step_id)
                        if next_step:
                            session.current_stage = DBJourneyStage(next_step.stage.value)

    # Check if journey is complete
    if session.current_step == "nextStep":
        session.is_completed = True

    db.commit()
    db.refresh(session)

    return build_journey_response(db, session)


def _journal_entry_exists(db: DBSession, session: Session, marker_tag: str) -> bool:
    """Auditoría R5 · evita journal entries duplicadas al re-visitar un paso
    (back + continuar, doble clic, retry de red). El marker es el primer tag
    del tipo de entrada (estable por paso)."""
    entries = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.session_id == session.id,
            JournalEntry.auto_generated.is_(True),
        )
        .all()
    )
    return any(marker_tag in (e.tags or []) for e in entries)


def _owner_onboarding(db: DBSession, session: Session) -> Optional[dict]:
    """Onboarding del dueño de la sesión (None si anónima)."""
    if session.user_id is None:
        return None
    owner = db.query(User).filter(User.id == session.user_id).first()
    return owner.onboarding_answers if owner else None


def _create_journal_entry_for_reflection(
    db: DBSession,
    session: Session,
    step_id: str,
    answers: Dict[str, Any],
) -> None:
    """Create a journal entry for a reflection step (idempotente por paso)."""
    if step_id == "empathy":
        content = f"Reflexion inicial: {answers.get('whyHere', 'No especificado')}"
        tags = ["inicio", "motivacion"]
    elif step_id == "partialSummary1":
        summary = generate_partial_summary(answers, str(session.id))
        content = f"Intereses identificados: {'. '.join(summary.bullets)}. Motivacion principal: {summary.motivation}."
        tags = ["intereses", summary.motivation.lower()]
    elif step_id == "synthesis":
        # Auditoría R5 · reusar la síntesis QUE LA USUARIA VIO (cache del
        # paso). Antes se generaba OTRA síntesis con una segunda llamada IA
        # (sin contexto de onboarding) → el diario guardaba un texto distinto.
        onboarding = _owner_onboarding(db, session)
        h = _ai_inputs_hash(answers, onboarding)
        cached = _ai_cache_get(session, "synthesis", h) or _ai_cache_get_any(
            session, "synthesis"
        )
        if cached is None:
            synthesis = generate_synthesis(
                answers,
                str(session.id),
                db=db,
                user_id=session.user_id,
                onboarding=onboarding,
            )
            cached = {"text": synthesis.text}
            # no _ai_cache_put: el render del paso lo cacheará con su shape completo
        content = cached["text"]
        tags = ["sintesis", "perfil"]
    else:
        content = "Nueva reflexion registrada."
        tags = ["reflexion"]

    if _journal_entry_exists(db, session, tags[0]):
        return

    entry = JournalEntry(
        session_id=session.id,
        content=content,
        entry_type=JournalEntryType.REFLECTION,
        tags=tags,
        auto_generated=True,
    )
    db.add(entry)


def _handle_route_selection(
    db: DBSession,
    session: Session,
    route_key: str,
    answers: Dict[str, Any],
) -> bool:
    """Registra la selección de ruta. Devuelve True solo si se registró.

    Auditoría R5 · la key se busca en las rutas PERSISTIDAS que la usuaria
    vio en pantalla (cache del paso 'routes'). Antes se regeneraban con otra
    llamada IA (prompt distinto, temperatura 0.7) → las keys casi nunca
    coincidían y la elección se perdía en silencio.
    """
    onboarding = _owner_onboarding(db, session)
    h = _ai_inputs_hash(answers, onboarding)
    cached = _ai_cache_get(session, "routes", h) or _ai_cache_get_any(session, "routes")
    routes = (cached or {}).get("routes") or []

    selected_route = next((r for r in routes if r.get("key") == route_key), None)
    if selected_route is None:
        # Red de seguridad: no avanzar ni completar sin ruta registrada.
        return False

    # Idempotencia: re-selección de la misma ruta no duplica filas ni journal.
    existing = (
        db.query(Route)
        .filter(Route.session_id == session.id, Route.key == selected_route["key"])
        .first()
    )
    if existing is None:
        # Solo una ruta primaria por sesión: demover las anteriores.
        db.query(Route).filter(
            Route.session_id == session.id, Route.is_primary.is_(True)
        ).update({"is_primary": False}, synchronize_session=False)

        route = Route(
            session_id=session.id,
            key=selected_route["key"],
            name=selected_route["name"],
            why=selected_route["why"],
            what_it_looks_like=selected_route["what_it_looks_like"],
            next_step=selected_route["next_step"],
            status=RouteStatus.ACTIVE,
            is_primary=True,
        )
        db.add(route)

        entry = JournalEntry(
            session_id=session.id,
            content=f"Ruta seleccionada: {selected_route['name']}. {selected_route['why']}",
            entry_type=JournalEntryType.DECISION,
            tags=["ruta", selected_route["key"].lower()],
            auto_generated=True,
        )
        db.add(entry)

    # Update session selected routes
    selected = list(session.selected_routes) if session.selected_routes else []
    if route_key not in selected:
        selected.append(route_key)
        session.selected_routes = selected

    return True


def save_profile_version(db: DBSession, session: Session) -> ProfileVersion:
    """Save a new profile version."""
    answers = session.answers or {}
    motivations = derive_motivations(answers)
    constraints = derive_constraints(answers)

    # Get current version count
    version_count = (
        db.query(ProfileVersion)
        .filter(ProfileVersion.session_id == session.id)
        .count()
    )

    version = ProfileVersion(
        session_id=session.id,
        version=version_count + 1,
        answers=answers,
        derived_tags=motivations + constraints,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
