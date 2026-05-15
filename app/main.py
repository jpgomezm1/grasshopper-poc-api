"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.logging_config import configure_logging, get_logger
from app.core.rate_limiter import (
    RateLimitExceeded,
    SlowAPIMiddleware,
    limiter,
    rate_limit_exceeded_handler,
)
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.error_logging_middleware import ErrorLoggingMiddleware
from app.core.sentry_init import init_sentry
from app.db.database import engine, Base
from app.core.alembic_guard import verify_alembic_head
from app.api.v1 import (
    sessions,
    profile,
    journal,
    routes,
    snapshots,
    advisor,
    auth,
    transcription,
    english_test,
    vocational_tests,
    ofertas,
    lead_profile,
    schools,
    external_test_uploads,
    recommendations,
    reports,
    licenses,
    programs,
    admin,
    admin_stats_advanced,
    school_panel,
    bitrix,
    privacy,
    gh_team,
    crm,
    notifications,
    tasks,
    commercial,
    clinical,
    school_admin,
    parent_panel,
    me as me_router,
    users_admin,
    admin_search,
    admin_observability,
    admin_settings,
)

# Configure logging early · structlog + PII masking (GH-S11)
configure_logging()
logger = get_logger(__name__)

# Sentry · no-op when SENTRY_DSN_BACKEND empty (GH-S11-INFRA-01)
sentry_active = init_sentry()
if sentry_active:
    logger.info("sentry.activated")
else:
    logger.info("sentry.no_op", reason="dsn_empty")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler · replaces deprecated @app.on_event (S11-BUG-04 · S12).

    F2-AUDIT-004: create_all() removed — Alembic is the single source of truth
    for schema. verify_alembic_head() runs at boot:
      - production  → RuntimeError if DB is not at head (fail-fast)
      - development/test → warning only (allows working without running migrations)
    """
    logger.info(
        "startup",
        environment=settings.environment,
        version=settings.app_version,
        sentry_active=sentry_active,
        rate_limit_enabled=settings.rate_limit_enabled,
    )
    # F2-AUDIT-004: test env uses Base.metadata.create_all() internally (SQLite
    # in-memory + Alembic UUID incompatibility); all other envs check Alembic head.
    if settings.environment == "test":
        Base.metadata.create_all(bind=engine)
        logger.info("db.tables_ready", mode="create_all_test")
    else:
        verify_alembic_head(engine, settings.environment)
        logger.info("db.alembic_verified")
    yield
    logger.info("shutdown")


# Create FastAPI app
app = FastAPI(
    title="Grasshopper API",
    description="Backend API for Grasshopper · vocational orientation platform",
    version=settings.app_version,
    lifespan=lifespan,
)

# Rate limiter (GH-S11-INFRA-04) registered before CORS
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security headers (GH-S11-INFRA-05)
app.add_middleware(SecurityHeadersMiddleware)

# Error logging middleware (GH-SUPERADMIN-EXPERIENCE · Bloque K · 2026-05-05)
# Captures all unhandled exceptions and 5xx responses into the error_log table.
app.add_middleware(ErrorLoggingMiddleware)

# CORS — last in stack so its headers wrap everything below
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    max_age=600,
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(journal.router, prefix="/api/v1")
app.include_router(routes.router, prefix="/api/v1")
app.include_router(snapshots.router, prefix="/api/v1")
app.include_router(advisor.router, prefix="/api/v1")
app.include_router(transcription.router, prefix="/api/v1")
app.include_router(english_test.router, prefix="/api/v1")
app.include_router(vocational_tests.router, prefix="/api/v1")
app.include_router(ofertas.router, prefix="/api/v1")
app.include_router(lead_profile.router, prefix="/api/v1")
app.include_router(schools.router, prefix="/api/v1")
app.include_router(external_test_uploads.router, prefix="/api/v1")
app.include_router(recommendations.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(licenses.router, prefix="/api/v1")
app.include_router(programs.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
# Bloque C · Sprint super_admin fixes 2026-05-03 · funnel/timeseries/cohorts/exports
app.include_router(admin_stats_advanced.router, prefix="/api/v1")
app.include_router(school_panel.router, prefix="/api/v1")
app.include_router(school_panel.public_router, prefix="/api/v1")
# Bitrix CRM Sync (GH-S10 · D-020 stub default · activation in S12)
app.include_router(bitrix.admin_router, prefix="/api/v1")
app.include_router(bitrix.webhook_router, prefix="/api/v1")
# Habeas Data privacy endpoints (GH-S11.5-BE-07 · D-026 · Ley 1581/2012)
app.include_router(privacy.router, prefix="/api/v1")
# GH internal team contact-request flow (GH-ROLES-001)
app.include_router(gh_team.students_router, prefix="/api/v1")
app.include_router(gh_team.gh_router, prefix="/api/v1")
# CRM enriched (GH-CRM-001 · 2026-05-03 · super_admin + gh_commercial)
app.include_router(crm.router, prefix="/api/v1")

# GH-COMMPROD · gh_commercial productivity sprint 2026-05-03
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(commercial.router, prefix="/api/v1")

# GH-ADVISOR-CLINICAL · gh_advisor clinical toolkit sprint 2026-05-04
app.include_router(clinical.router, prefix="/api/v1")

# GH-SCHOOL-ADMIN · school_admin extended sprint 2026-05-04
app.include_router(school_admin.router, prefix="/api/v1")
app.include_router(parent_panel.router, prefix="/api/v1")

# GH-STUDENT-EXPERIENCE · student-facing sprint 2026-05-05
app.include_router(me_router.router, prefix="/api/v1")

# GH-SUPERADMIN-EXPERIENCE · super_admin uplift sprint 2026-05-05
# Bloque A·B·E·F (users_admin) + C (search) + D·I·J·K·L (observability) +
# M·N·O·P (settings).
app.include_router(users_admin.router, prefix="/api/v1")
app.include_router(admin_search.router, prefix="/api/v1")
app.include_router(admin_observability.router, prefix="/api/v1")
app.include_router(admin_settings.router, prefix="/api/v1")


@app.get("/health", tags=["Infra"])
async def health_check():
    """Readiness probe (GH-S11-INFRA-02).

    Returns 200 when DB connectivity is OK, 503 otherwise. Anthropic +
    Storage are reported as booleans without short-circuiting so
    monitoring can distinguish soft degradation from hard outage.
    """
    from sqlalchemy import text

    db_ok = True
    db_error: str | None = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover · best effort
        db_ok = False
        db_error = str(e)[:200]

    anthropic_ok = bool(settings.anthropic_api_key)
    storage_ok = bool(settings.supabase_url and settings.supabase_service_key) or (
        settings.storage_backend == "stub"
    )

    payload = {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "checks": {
            "db_connected": db_ok,
            "anthropic_reachable": anthropic_ok,
            "storage_reachable": storage_ok,
            "sentry_active": sentry_active,
            "rate_limit_enabled": settings.rate_limit_enabled,
        },
    }
    if db_error:
        payload["db_error"] = db_error

    if not db_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload
        )
    return payload


@app.get("/health/live", tags=["Infra"])
async def liveness_probe():
    """Bare liveness · always 200 if process is up."""
    return {"status": "alive", "version": settings.app_version}


@app.get("/", tags=["Infra"])
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Grasshopper API",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
