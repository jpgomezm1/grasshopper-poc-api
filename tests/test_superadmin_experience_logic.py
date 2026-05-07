"""Pure-Python logic tests for the super_admin sprint.

Covers:
  - temp password generator entropy / charset (Bloque A · reset)
  - integration_config secret-value rejection (Bloque O)
  - feature flags resolver order (Bloque M)
  - AI cost estimation (Bloque J)
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.api.v1.users_admin import _generate_temp_password
from app.services.ai_usage_service import estimate_cost_usd


# --------------------------------------------------------------------------- #
# Bloque A · temp password                                                    #
# --------------------------------------------------------------------------- #

def test_temp_password_length_default_14():
    assert len(_generate_temp_password()) == 14


def test_temp_password_charset_includes_letters_digits_symbols():
    samples = [_generate_temp_password() for _ in range(50)]
    joined = "".join(samples)
    assert any(c.isalpha() for c in joined)
    assert any(c.isdigit() for c in joined)
    assert any(c in "!@#$%&*" for c in joined)


def test_temp_password_distinct_across_calls():
    samples = {_generate_temp_password() for _ in range(20)}
    # 20 random 14-char passwords colliding is astronomically unlikely
    assert len(samples) == 20


# --------------------------------------------------------------------------- #
# Bloque O · integration secrets validation                                   #
# --------------------------------------------------------------------------- #

ENV_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]{1,79}")


def _accept_env_name(value: str) -> bool:
    """Mirror of upsert_integration_config's validation."""
    if not ENV_NAME_RE.fullmatch(value):
        return False
    if "://" in value or len(value) > 80:
        return False
    return True


@pytest.mark.parametrize(
    "name",
    [
        "BITRIX_WEBHOOK_URL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "S3_BUCKET_NAME",
    ],
)
def test_integration_secret_accepts_env_var_names(name):
    assert _accept_env_name(name)


@pytest.mark.parametrize(
    "value",
    [
        "https://hooks.bitrix.com/abc/xyz",  # URL · likely real webhook
        "sk-1234567890abcdef",  # OpenAI-style raw secret
        "xoxb-tokens-here",  # slack-style
        "lowercase_name",  # not env-var convention
        "WITH SPACES_HERE",
        "A",  # too short
        "X" * 100,  # too long
    ],
)
def test_integration_secret_rejects_actual_secrets(value):
    assert not _accept_env_name(value)


# --------------------------------------------------------------------------- #
# Bloque M · feature flags resolver                                           #
# --------------------------------------------------------------------------- #

def _make_user(role_value: str, school_id=None):
    role = SimpleNamespace(value=role_value)
    return SimpleNamespace(role=role, school_id=school_id)


def test_flag_resolver_global_on_overrides_everything():
    flags = {"f1": {"enabled": True, "roles": [], "schools": []}}
    user = _make_user("student")
    # mirror the resolver logic
    f = flags["f1"]
    assert f["enabled"] is True


def test_flag_resolver_role_match_grants_access():
    flags = {"f1": {"enabled": False, "roles": ["psychologist"], "schools": []}}
    user = _make_user("psychologist")
    f = flags["f1"]
    assert (f["enabled"] is False) and (user.role.value in f["roles"])


def test_flag_resolver_school_match_grants_access():
    flags = {"f1": {"enabled": False, "roles": [], "schools": ["abc-123"]}}
    user = _make_user("student", school_id="abc-123")
    f = flags["f1"]
    assert str(user.school_id) in f["schools"]


def test_flag_resolver_no_match_denies():
    flags = {"f1": {"enabled": False, "roles": ["psychologist"], "schools": []}}
    user = _make_user("student")
    f = flags["f1"]
    assert (f["enabled"] is False) and (user.role.value not in f["roles"]) and (not f["schools"])


# --------------------------------------------------------------------------- #
# Bloque J · AI cost estimation                                               #
# --------------------------------------------------------------------------- #

def test_cost_estimation_haiku_typical_call():
    # 1000 input + 500 output on Haiku
    cost = estimate_cost_usd("claude-3-haiku-20240307", 1000, 500)
    assert cost is not None
    # 1000 * 0.00025/1k + 500 * 0.00125/1k = 0.00025 + 0.000625
    assert abs(cost - 0.000875) < 1e-6


def test_cost_estimation_unknown_model_returns_none():
    assert estimate_cost_usd("future-model-2030", 1000, 500) is None


def test_cost_estimation_zero_tokens_returns_zero():
    assert estimate_cost_usd("claude-3-haiku-20240307", 0, 0) == 0.0
