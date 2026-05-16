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
