"""Shared pytest fixtures for the backend test suite.

GH-S11 · ensures the in-memory rate limiter buckets are wiped between
tests so cumulative HTTP requests across the suite don't accidentally
trigger 429s in unrelated test cases.
"""
from __future__ import annotations

import pytest


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
