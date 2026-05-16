"""Alembic schema-drift guard · F2-AUDIT-004.

Replaces the removed `Base.metadata.create_all()` call that previously ran on
every boot.  Alembic is the single source of truth for the schema; this module
validates that the live DB is at the Alembic head revision before the app
starts serving traffic.

Behaviour by environment
------------------------
production  → RuntimeError if current revision != head revision (fail-fast).
              Heroku/Render will restart the dyno; the alert surface is the
              crash log / Sentry.

development → logger.warning if out of date; boot continues so developers can
              work without running migrations constantly.

test        → this function is NOT called from lifespan in test mode.
              Tests use Base.metadata.create_all() directly on their
              in-memory SQLite engine (Alembic + SQLite + UUID types is
              fragile and was already excluded before this change).
"""

from __future__ import annotations

from sqlalchemy import Engine

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def verify_alembic_head(engine: Engine, environment: str) -> None:
    """Check that the DB is at the current Alembic head.

    Parameters
    ----------
    engine:
        Bound SQLAlchemy engine pointing at the live database.
    environment:
        Value of ``settings.environment`` (e.g. "production", "development").

    Raises
    ------
    RuntimeError
        Only when ``environment == "production"`` and the DB is not at head.
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext

        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()

    except Exception as exc:
        # Never crash the app because alembic.ini is missing or mis-configured
        # outside production.  In production this is still a hard failure.
        msg = f"alembic_guard: could not read migration state: {exc}"
        if environment == "production":
            raise RuntimeError(msg) from exc
        logger.warning("alembic_guard.check_failed", error=str(exc))
        return

    if current == head:
        logger.info(
            "alembic_guard.ok",
            current=current,
            head=head,
            environment=environment,
        )
        return

    # Drift detected.
    logger.warning(
        "alembic_guard.drift_detected",
        current=current,
        head=head,
        environment=environment,
    )

    if environment == "production":
        raise RuntimeError(
            f"DB schema is not at Alembic head. "
            f"current={current!r}  head={head!r}. "
            f"Run `alembic upgrade head` before starting the server."
        )
    # development / staging: warn and continue.
