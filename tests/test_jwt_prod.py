"""JWT secret production assertion tests · GH-F1-SECURITY · Tarea 2.

Validates that Settings raises RuntimeError at boot time when the JWT
secret key is the insecure POC placeholder in a production environment.

Pure-unit tests: instantiate Settings directly with monkeypatched env vars.
No DB, no FastAPI app needed.
"""
from __future__ import annotations

import pytest


def _make_settings(**overrides):
    """Instantiate Settings with given overrides, bypassing .env file."""
    import importlib
    import app.config as config_mod
    # Clear lru_cache so each call creates a fresh Settings instance
    config_mod.get_settings.cache_clear()

    from pydantic_settings import BaseSettings
    # Build a dict of kwargs that Settings accepts
    kwargs = {
        "database_url": "sqlite:///test.db",  # harmless default for tests
        **overrides,
    }
    return config_mod.Settings(**kwargs)


class TestJWTProductionAssertion:

    def test_development_allows_default_jwt_secret(self):
        """In development, the default POC secret must NOT raise."""
        settings = _make_settings(
            environment="development",
            jwt_secret_key="grasshopper-poc-secret-key-change-in-production",
        )
        assert settings.environment == "development"

    def test_production_with_default_secret_raises(self):
        """In production, the default POC placeholder must trigger RuntimeError."""
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
            _make_settings(
                environment="production",
                jwt_secret_key="grasshopper-poc-secret-key-change-in-production",
            )

    def test_production_with_empty_secret_raises(self):
        """In production, an empty JWT_SECRET_KEY must trigger RuntimeError."""
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
            _make_settings(
                environment="production",
                jwt_secret_key="",
            )

    def test_production_with_strong_secret_ok(self):
        """In production, a strong secret must NOT raise."""
        strong = "X" * 64  # 64-char random-looking value
        settings = _make_settings(
            environment="production",
            jwt_secret_key=strong,
        )
        assert settings.jwt_secret_key == strong

    def test_poc_prefix_check_is_exact_prefix(self):
        """Any key starting with the POC prefix must fail in production."""
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
            _make_settings(
                environment="production",
                jwt_secret_key="grasshopper-poc-secret-key-whatever-suffix",
            )
