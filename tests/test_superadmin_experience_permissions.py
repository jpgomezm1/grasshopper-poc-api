"""Permission matrix tests · GH-SUPERADMIN-EXPERIENCE · 2026-05-05.

Hard rule: every endpoint added in this sprint must reject every non
super_admin role with 403. We do NOT test the happy path here (covered in
DB-backed integration tests) — only the access matrix · pure-Python so it
runs without Postgres.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.v1 import users_admin, admin_search, admin_observability, admin_settings
from app.db.models import UserRole


def _user(role: UserRole):
    return SimpleNamespace(role=role, id="u1", email="x@example.com", school_id=None)


# Roles that MUST be rejected (everything that is not super_admin).
NON_SUPER = [
    UserRole.STUDENT,
    UserRole.PSYCHOLOGIST,
    UserRole.SCHOOL_ADMIN,
    UserRole.GH_ADVISOR,
    UserRole.GH_COMMERCIAL,
    UserRole.PARENT,
]


@pytest.mark.parametrize("role", NON_SUPER)
def test_users_admin_blocks_non_super_admin(role):
    with pytest.raises(Exception) as exc:
        users_admin._require_super_admin(_user(role))
    assert "403" in str(exc.value) or "Forbidden" in str(exc.value)


@pytest.mark.parametrize("role", NON_SUPER)
def test_admin_search_blocks_non_super_admin(role):
    with pytest.raises(Exception) as exc:
        admin_search._require_super_admin(_user(role))
    assert "403" in str(exc.value) or "super_admin" in str(exc.value)


@pytest.mark.parametrize("role", NON_SUPER)
def test_admin_observability_blocks_non_super_admin(role):
    with pytest.raises(Exception) as exc:
        admin_observability._ensure_super_admin(_user(role))
    assert "403" in str(exc.value) or "super_admin" in str(exc.value)


@pytest.mark.parametrize("role", NON_SUPER)
def test_admin_settings_blocks_non_super_admin(role):
    with pytest.raises(Exception) as exc:
        admin_settings._ensure_super_admin(_user(role))
    assert "403" in str(exc.value) or "super_admin" in str(exc.value)


def test_super_admin_passes_all_guards():
    """Smoke · super_admin must NOT trigger the guards."""
    su = _user(UserRole.SUPER_ADMIN)
    users_admin._require_super_admin(su)
    admin_search._require_super_admin(su)
    admin_observability._ensure_super_admin(su)
    admin_settings._ensure_super_admin(su)
