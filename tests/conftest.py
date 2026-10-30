"""Shared pytest fixtures for the backend test suite.

GH-S11 · ensures the in-memory rate limiter buckets are wiped between
tests so cumulative HTTP requests across the suite don't accidentally
trigger 429s in unrelated test cases.

GH-S11.5-BE-04 · SQLite UUID compatibility patch:
SQLAlchemy 2.0+ with native UUID type is not supported by SQLite.
All DB-backed tests (sqlite:///:memory:) need the dialect to map UUID
columns to VARCHAR(36). This module-level patch applies once and affects
all test sessions that import conftest.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# SQLite UUID compatibility · module-level (runs once at import time)
# ---------------------------------------------------------------------------

def _patch_sqlite_uuid():
    """Monkey-patch SQLiteTypeCompiler to accept UUID columns as VARCHAR(36).

    SQLAlchemy 2.0 introduced a native UUID type that SQLite does not
    understand. Without this patch, `Base.metadata.create_all(engine)` fails
    with:
        UnsupportedCompilationError: Compiler can't render element of type UUID

    This is a test-only shim · production uses PostgreSQL which handles UUID
    natively. The patch is idempotent.
    """
    try:
        from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

        if not hasattr(SQLiteTypeCompiler, "visit_UUID"):
            def visit_UUID(self, type_, **kw):  # noqa: N802
                return "VARCHAR(36)"

            SQLiteTypeCompiler.visit_UUID = visit_UUID  # type: ignore[attr-defined]
    except Exception:
        pass  # non-critical for environments that don't run SQLite tests


_patch_sqlite_uuid()


# ---------------------------------------------------------------------------
# Rate limiter reset
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter_between_tests():
    """Drop all rate-limit buckets before and after every test."""
    try:
        from app.core.rate_limiter import limiter as gh_limiter

        gh_limiter.reset()
    except Exception:
        pass
    yield
    try:
        from app.core.rate_limiter import limiter as gh_limiter

        gh_limiter.reset()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# D-3 · Sprint 4 · los planes en los tests
# ---------------------------------------------------------------------------
#
# Desde D-3 las funciones pagas se niegan (402) a un estudiante sin plan, y casi
# todos los tests crean estudiantes sin plan. Esos tests prueban la FUNCIÓN
# (responder un test, el chat, la hoja de vida…), no el plan, así que por
# defecto todos corren como plan `pago`. Los tests de los planes y de la llave
# (D-1, D-2, D-3) se marcan con `@pytest.mark.planes_reales` y ven la regla de
# verdad. Así un test de la hoja de vida no se rompe por el plan, y el plan
# tiene sus propios tests que no dependen de este atajo.


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "planes_reales: el test usa la regla real de planes (sin el plan pago por defecto)",
    )


@pytest.fixture(autouse=True)
def _plan_pago_por_defecto(request, monkeypatch):
    if request.node.get_closest_marker("planes_reales"):
        yield
        return
    from app.services import plan_service

    original = plan_service.plan_vigente

    def _pago_si_no_tiene(db, user, ahora=None):
        real = original(db, user, ahora)
        if real.plan == plan_service.PLAN_GRATIS and real.origen == "ninguno":
            return plan_service.PlanVigente(plan_service.PLAN_PAGO, "tests")
        return real

    monkeypatch.setattr(plan_service, "plan_vigente", _pago_si_no_tiene)
    yield
