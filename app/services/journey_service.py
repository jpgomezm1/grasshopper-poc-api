"""Journey business logic service."""

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


def create_session(db: DBSession) -> Session:
    """Create a new journey session."""
    session = Session()
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

    if step.view_type == ViewType.REFLECTION:
        if step.id == "empathy":
            why_here = answers.get("whyHere", "")
            if why_here:
                reflection = generate_empathy_reflection(why_here, str(session.id))
                response.reflection_content = reflection.text
        elif step.id == "synthesis":
            synthesis = generate_synthesis(answers, str(session.id))
            response.synthesis_text = synthesis.text
            response.synthesis_chips = [
                {"label": chip.label, "value": chip.value}
                for chip in synthesis.chips
            ]

    elif step.view_type == ViewType.PARTIAL_SUMMARY:
        summary = generate_partial_summary(answers, str(session.id))
        response.partial_summary_bullets = summary.bullets
        response.partial_summary_motivation = summary.motivation

    elif step.view_type == ViewType.ROUTES_PICKER:
        routes_output = generate_routes(answers, str(session.id))
        response.suggested_routes = [
            {
                "key": route.key,
                "name": route.name,
                "why": route.why,
                "whatItLooksLike": route.what_it_looks_like,
                "nextStep": route.next_step,
            }
            for route in routes_output.routes
        ]

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

            # Advance to next step
            next_step_id = get_next_step(step_id)
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
                _handle_route_selection(db, session, route_key, answers)

                # Advance to next step
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


def _create_journal_entry_for_reflection(
    db: DBSession,
    session: Session,
    step_id: str,
    answers: Dict[str, Any],
) -> None:
    """Create a journal entry for a reflection step."""
    if step_id == "empathy":
        content = f"Reflexion inicial: {answers.get('whyHere', 'No especificado')}"
        tags = ["inicio", "motivacion"]
    elif step_id == "partialSummary1":
        summary = generate_partial_summary(answers, str(session.id))
        content = f"Intereses identificados: {'. '.join(summary.bullets)}. Motivacion principal: {summary.motivation}."
        tags = ["intereses", summary.motivation.lower()]
    elif step_id == "synthesis":
        synthesis = generate_synthesis(answers, str(session.id))
        content = synthesis.text
        tags = ["sintesis", "perfil"]
    else:
        content = "Nueva reflexion registrada."
        tags = ["reflexion"]

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
) -> None:
    """Handle route selection."""
    # Get the suggested routes to find the selected one
    routes_output = generate_routes(answers, str(session.id))
    selected_route = next(
        (r for r in routes_output.routes if r.key == route_key),
        None
    )

    if selected_route:
        # Create route record
        route = Route(
            session_id=session.id,
            key=selected_route.key,
            name=selected_route.name,
            why=selected_route.why,
            what_it_looks_like=selected_route.what_it_looks_like,
            next_step=selected_route.next_step,
            status=RouteStatus.ACTIVE,
            is_primary=True,
        )
        db.add(route)

        # Update session selected routes
        selected = list(session.selected_routes) if session.selected_routes else []
        if route_key not in selected:
            selected.append(route_key)
            session.selected_routes = selected

        # Create journal entry
        entry = JournalEntry(
            session_id=session.id,
            content=f"Ruta seleccionada: {selected_route.name}. {selected_route.why}",
            entry_type=JournalEntryType.DECISION,
            tags=["ruta", selected_route.key.lower()],
            auto_generated=True,
        )
        db.add(entry)


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
