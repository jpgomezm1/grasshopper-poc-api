"""Tests de validación de Origin en /forgot-password · GH-F1-SECURITY.

Valida que:
  - build_safe_url (helper compartido) acepta origins válidos
  - Rechaza origins maliciosos y usa frontend_base_url como fallback
  - Sin origin usa el fallback
  - Subdomain spoofing es rechazado
  - El log de forgot_password NO contiene token ni email completo

Tests separados en dos clases:
  TestBuildSafeUrl       · unit tests del helper app/core/url_safety.py
  TestForgotPasswordLog  · verifica que el log neutro no expone PII/token
"""
from __future__ import annotations

import logging
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(origin: str | None) -> MagicMock:
    """Crea un mock de fastapi.Request con el header Origin dado."""
    req = MagicMock()
    if origin is None:
        req.headers.get.return_value = None
    else:
        req.headers.get.return_value = origin
    return req


def _make_settings(
    allowed_origins_str: str,
    frontend_base_url: str = "https://grasshopper-app.netlify.app",
) -> MagicMock:
    """Stub de Settings con allowed_origins_set y frontend_base_url."""
    s = MagicMock()
    s.allowed_origins_set = {
        o.strip().rstrip("/") for o in allowed_origins_str.split(",") if o.strip()
    }
    s.frontend_base_url = frontend_base_url
    return s


ALLOWED = "https://grasshopper-app.netlify.app,http://localhost:5173"
FRONTEND = "https://grasshopper-app.netlify.app"


# ---------------------------------------------------------------------------
# Tests del helper build_safe_url
# ---------------------------------------------------------------------------

class TestBuildSafeUrl:
    """Unit tests de app.core.url_safety.build_safe_url."""

    def _call(
        self,
        origin: str | None,
        path: str = "/reset-password/TOKEN",
        allowed: str = ALLOWED,
        frontend_url: str = FRONTEND,
        fallback: str | None = None,
    ) -> str:
        from app.core.url_safety import build_safe_url

        fake_settings = _make_settings(allowed, frontend_url)
        with patch("app.core.url_safety.get_settings", return_value=fake_settings):
            return build_safe_url(
                origin_header=origin,
                path=path,
                fallback=fallback,
            )

    def test_valid_origin_netlify_used(self):
        """Origin de la whitelist se usa directamente."""
        url = self._call(origin="https://grasshopper-app.netlify.app")
        assert url == "https://grasshopper-app.netlify.app/reset-password/TOKEN"

    def test_valid_origin_localhost_used(self):
        """localhost en whitelist se acepta (útil en dev)."""
        url = self._call(origin="http://localhost:5173")
        assert url == "http://localhost:5173/reset-password/TOKEN"

    def test_malicious_origin_falls_back_to_frontend(self):
        """Origin atacante produce fallback · nunca evil.com en la URL."""
        url = self._call(origin="https://evil.attacker.com")
        assert "evil.attacker.com" not in url
        assert url == "https://grasshopper-app.netlify.app/reset-password/TOKEN"

    def test_none_origin_falls_back_to_frontend(self):
        """Origin=None usa frontend_base_url."""
        url = self._call(origin=None)
        assert url == "https://grasshopper-app.netlify.app/reset-password/TOKEN"

    def test_empty_origin_falls_back_to_frontend(self):
        """Origin='' usa frontend_base_url."""
        url = self._call(origin="")
        assert url == "https://grasshopper-app.netlify.app/reset-password/TOKEN"

    def test_trailing_slash_origin_still_matches(self):
        """Origin con trailing slash se normaliza y coincide con la whitelist."""
        url = self._call(origin="https://grasshopper-app.netlify.app/")
        assert url == "https://grasshopper-app.netlify.app/reset-password/TOKEN"

    def test_subdomain_not_in_whitelist_rejected(self):
        """Subdominio no registrado es rechazado aunque el dominio base esté en la whitelist."""
        url = self._call(origin="https://evil.grasshopper-app.netlify.app")
        assert "evil.grasshopper-app" not in url
        assert url == "https://grasshopper-app.netlify.app/reset-password/TOKEN"

    def test_explicit_fallback_used_when_origin_rejected(self):
        """Cuando se pasa `fallback` explícito, se usa en lugar de frontend_base_url."""
        url = self._call(
            origin="https://evil.com",
            fallback="https://override.grasshopper.co",
        )
        assert url == "https://override.grasshopper.co/reset-password/TOKEN"

    def test_path_leading_slash_not_doubled(self):
        """La concatenación base + path nunca produce doble barra."""
        url = self._call(
            origin="https://grasshopper-app.netlify.app",
            path="/reset-password/abc",
        )
        assert "//" not in url.replace("https://", "").replace("http://", "")

    def test_rejected_origin_triggers_warning_log(self, caplog):
        """Un origin rechazado debe producir un WARNING de forensics."""
        with caplog.at_level(logging.WARNING, logger="app.core.url_safety"):
            self._call(origin="https://evil.com")

        assert any("origin_rejected" in r.message for r in caplog.records)
        # El WARNING debe incluir el origin recibido para forensics
        assert any("evil.com" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests de que el log de forgot_password no expone PII ni token
# ---------------------------------------------------------------------------

class TestForgotPasswordLog:
    """Verifica que el log en /forgot-password es neutro (sin email ni token)."""

    def _invoke_forgot_password(
        self,
        origin: str | None,
        user_email: str = "victim@example.com",
    ) -> list[logging.LogRecord]:
        """Invoca la función forgot_password con un user mock y captura logs."""
        import uuid
        from app.api.v1 import auth as auth_module

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.email = user_email
        fake_user.phone = None

        fake_db = MagicMock()
        fake_db.query.return_value.filter.return_value.first.return_value = fake_user

        fake_req = MagicMock()
        fake_req.headers.get.return_value = origin
        fake_body = MagicMock()
        fake_body.email = user_email
        fake_body.method = "email"

        fake_settings = _make_settings(ALLOWED, FRONTEND)

        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        handler = _Capture()
        logger = logging.getLogger("app.api.v1.auth")
        logger.addHandler(handler)
        try:
            with (
                patch("app.api.v1.auth.get_settings", return_value=fake_settings),
                patch("app.core.url_safety.get_settings", return_value=fake_settings),
                patch.object(fake_db, "commit"),
            ):
                # Patch settings dentro del módulo auth (ya importado como módulo-level)
                import app.api.v1.auth as auth_mod
                original_settings = auth_mod.settings
                auth_mod.settings = fake_settings
                try:
                    auth_module.forgot_password(fake_body, fake_req, fake_db)
                finally:
                    auth_mod.settings = original_settings
        finally:
            logger.removeHandler(handler)

        return captured

    def test_log_does_not_contain_reset_token(self):
        """El log de forgot_password NO debe contener el token de reset."""
        import secrets as _secrets

        # Parchamos secrets.token_urlsafe para que devuelva un token conocido
        known_token = "KNOWN_SECRET_TOKEN_ABC123"
        with patch("app.api.v1.auth.secrets.token_urlsafe", return_value=known_token):
            records = self._invoke_forgot_password(origin="https://grasshopper-app.netlify.app")

        # Ningún log debe contener el token
        for record in records:
            assert known_token not in record.getMessage(), (
                f"El log contiene el token de reset: {record.getMessage()}"
            )

    def test_log_does_not_contain_full_email(self):
        """El log de forgot_password NO debe contener el email completo del usuario."""
        user_email = "victim@example.com"
        records = self._invoke_forgot_password(
            origin="https://grasshopper-app.netlify.app",
            user_email=user_email,
        )
        for record in records:
            assert user_email not in record.getMessage(), (
                f"El log contiene el email del usuario: {record.getMessage()}"
            )

    def test_log_does_not_contain_reset_link(self):
        """El log de forgot_password NO debe contener el reset_link completo."""
        with patch("app.api.v1.auth.secrets.token_urlsafe", return_value="TKNXYZ"):
            records = self._invoke_forgot_password(
                origin="https://grasshopper-app.netlify.app",
            )
        for record in records:
            msg = record.getMessage()
            # El link completo nunca debe aparecer
            assert "/reset-password/TKNXYZ" not in msg, (
                f"El log contiene el reset link: {msg}"
            )

    def test_log_contains_user_id(self, caplog):
        """El log de forgot_password SÍ debe contener user_id (para trazabilidad)."""
        import uuid
        known_id = uuid.uuid4()

        import app.api.v1.auth as auth_module
        fake_user = MagicMock()
        fake_user.id = known_id
        fake_user.email = "victim@example.com"
        fake_user.phone = None

        fake_db = MagicMock()
        fake_db.query.return_value.filter.return_value.first.return_value = fake_user
        fake_req = MagicMock()
        fake_req.headers.get.return_value = "https://grasshopper-app.netlify.app"
        fake_body = MagicMock()
        fake_body.email = "victim@example.com"
        fake_body.method = "email"
        fake_settings = _make_settings(ALLOWED, FRONTEND)

        with caplog.at_level(logging.INFO, logger="app.api.v1.auth"):
            with (
                patch("app.api.v1.auth.get_settings", return_value=fake_settings),
                patch("app.core.url_safety.get_settings", return_value=fake_settings),
                patch.object(fake_db, "commit"),
            ):
                import app.api.v1.auth as auth_mod
                original_settings = auth_mod.settings
                auth_mod.settings = fake_settings
                try:
                    auth_module.forgot_password(fake_body, fake_req, fake_db)
                finally:
                    auth_mod.settings = original_settings

        user_id_str = str(known_id)
        assert any(user_id_str in r.getMessage() for r in caplog.records), (
            "El log de forgot_password debe contener user_id para trazabilidad"
        )
