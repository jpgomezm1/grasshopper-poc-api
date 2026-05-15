"""Origin header validation tests · GH-F1-SECURITY · Tarea 3.

Validates that _build_accept_url in school_panel.py:
  - Uses the Origin header only when it is in the allowed whitelist
  - Falls back to frontend_base_url for unknown / malicious origins
  - Falls back to localhost for missing origin

Pure-unit tests: mock Settings + mock Request objects. No DB needed.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_request(origin: str | None) -> MagicMock:
    req = MagicMock()
    if origin is None:
        req.headers.get.return_value = None
    else:
        req.headers.get.return_value = origin
    return req


def _make_settings(allowed_origins_str: str, frontend_base_url: str = "https://grasshopper-app.netlify.app"):
    """Build a minimal settings stub with allowed_origins_set populated."""
    settings = MagicMock()
    origins_set = {o.strip().rstrip("/") for o in allowed_origins_str.split(",") if o.strip()}
    settings.allowed_origins_set = origins_set
    settings.frontend_base_url = frontend_base_url
    return settings


class TestBuildAcceptUrl:

    def _call(self, token: str, origin: str | None, allowed: str, frontend_url: str = "https://grasshopper-app.netlify.app") -> str:
        from app.api.v1.school_panel import _build_accept_url

        fake_settings = _make_settings(allowed, frontend_url)
        with patch("app.api.v1.school_panel.get_settings", return_value=fake_settings):
            req = _make_request(origin) if origin is not None else None
            return _build_accept_url(token, req)

    def test_valid_origin_used_in_url(self):
        """An origin in the whitelist is used to build the URL."""
        url = self._call(
            token="abc123",
            origin="https://grasshopper-app.netlify.app",
            allowed="https://grasshopper-app.netlify.app,http://localhost:5173",
        )
        assert url == "https://grasshopper-app.netlify.app/invite/abc123"

    def test_localhost_origin_used_in_dev(self):
        """localhost origins in the whitelist are accepted."""
        url = self._call(
            token="dev-token",
            origin="http://localhost:5173",
            allowed="https://grasshopper-app.netlify.app,http://localhost:5173",
        )
        assert url == "http://localhost:5173/invite/dev-token"

    def test_malicious_origin_falls_back_to_frontend_base(self):
        """An attacker-controlled Origin falls back to the canonical frontend URL."""
        url = self._call(
            token="safe-token",
            origin="https://evil.attacker.com",
            allowed="https://grasshopper-app.netlify.app,http://localhost:5173",
            frontend_url="https://grasshopper-app.netlify.app",
        )
        # Must NOT contain the malicious origin
        assert "evil.attacker.com" not in url
        assert url == "https://grasshopper-app.netlify.app/invite/safe-token"

    def test_empty_origin_falls_back_to_frontend_base(self):
        """Empty Origin header uses the canonical frontend URL."""
        url = self._call(
            token="tok",
            origin="",
            allowed="https://grasshopper-app.netlify.app",
            frontend_url="https://grasshopper-app.netlify.app",
        )
        assert url == "https://grasshopper-app.netlify.app/invite/tok"

    def test_no_request_object_falls_back(self):
        """When request=None falls back to frontend_base_url."""
        url = self._call(
            token="no-req",
            origin=None,  # triggers req=None path
            allowed="https://grasshopper-app.netlify.app",
            frontend_url="https://grasshopper-app.netlify.app",
        )
        assert url == "https://grasshopper-app.netlify.app/invite/no-req"

    def test_trailing_slash_in_origin_still_matches(self):
        """Origin with trailing slash still matches the whitelist entry."""
        url = self._call(
            token="slash-tok",
            origin="https://grasshopper-app.netlify.app/",  # trailing slash
            allowed="https://grasshopper-app.netlify.app",
        )
        assert url == "https://grasshopper-app.netlify.app/invite/slash-tok"

    def test_subdomain_not_in_whitelist_rejected(self):
        """A subdomain not in the whitelist is rejected even if base domain is there."""
        url = self._call(
            token="sub-tok",
            origin="https://app.grasshopper-app.netlify.app",
            allowed="https://grasshopper-app.netlify.app",
            frontend_url="https://grasshopper-app.netlify.app",
        )
        assert "app.grasshopper-app" not in url
        assert url == "https://grasshopper-app.netlify.app/invite/sub-tok"
