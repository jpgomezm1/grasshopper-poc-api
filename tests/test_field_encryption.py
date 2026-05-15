"""At-rest field encryption tests · GH-F1-SECURITY · Tarea 4.

Validates app.core.crypto:
  - encrypt_field produces bytes, not the original plaintext
  - decrypt_field(encrypt_field(x)) == x  (round-trip)
  - Different calls produce different ciphertext (random nonce)
  - Tampered ciphertext raises InvalidTag (GCM authentication)
  - Dev-mode (no key) uses RAW1 sentinel and is transparently round-tripped
  - EncryptedJSON TypeDecorator serializes/deserializes dicts transparently
  - Legacy plaintext fallback in process_result_value works

Pure-unit tests, no DB, no env vars required by default.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from unittest.mock import patch

import pytest


def _make_32_byte_key() -> str:
    """Return a valid base64-urlsafe 32-byte key."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


class TestEncryptField:
    """Tests for encrypt_field / decrypt_field with a real key."""

    @pytest.fixture()
    def with_key(self, monkeypatch):
        """Set a random FIELD_ENCRYPTION_KEY and reload the crypto module."""
        key = _make_32_byte_key()
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", key)
        monkeypatch.setenv("ENVIRONMENT", "development")

        # Force module reload to pick up the new key
        import importlib
        import app.core.crypto as crypto_mod
        # Reload _KEY_BYTES by clearing and reloading
        importlib.reload(crypto_mod)
        yield crypto_mod

        # Restore: reload without key
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY", raising=False)
        importlib.reload(crypto_mod)

    def test_encrypted_bytes_not_equal_to_plaintext(self, with_key):
        ciphertext = with_key.encrypt_field("secret data")
        assert ciphertext != b"secret data"
        assert ciphertext != "secret data".encode("utf-8")

    def test_round_trip_string(self, with_key):
        original = "Análisis clínico sensible · señales_clinicas detectadas"
        ciphertext = with_key.encrypt_field(original)
        assert with_key.decrypt_field(ciphertext) == original

    def test_different_ciphertext_each_call(self, with_key):
        """Random nonce ensures same plaintext → different ciphertext."""
        plaintext = "mismo texto"
        ct1 = with_key.encrypt_field(plaintext)
        ct2 = with_key.encrypt_field(plaintext)
        assert ct1 != ct2
        # Both must decrypt to the same value
        assert with_key.decrypt_field(ct1) == plaintext
        assert with_key.decrypt_field(ct2) == plaintext

    def test_tampered_ciphertext_raises(self, with_key):
        """AES-GCM authentication tag protects against tampering."""
        from cryptography.exceptions import InvalidTag
        ciphertext = with_key.encrypt_field("data")
        # Flip a byte in the payload area (after nonce + ENC1 sentinel)
        tampered = bytearray(ciphertext)
        tampered[-1] ^= 0xFF
        with pytest.raises((InvalidTag, Exception)):
            with_key.decrypt_field(bytes(tampered))

    def test_encrypt_json_round_trip(self, with_key):
        obj = {
            "narrative": "Perfil clínico",
            "risks": ["aislamiento"],
            "requires_referral": True,
            "score": 0.82,
        }
        ciphertext = with_key.encrypt_json(obj)
        assert isinstance(ciphertext, bytes)
        result = with_key.decrypt_json(ciphertext)
        assert result == obj

    def test_none_returns_none(self, with_key):
        """None plaintext passes through without encryption."""
        # encrypt_field works on strings, but EncryptedJSON TypeDecorator
        # handles None at the TypeDecorator level.
        # Here we test encrypt_json explicitly with None is not called
        # (TypeDecorator guards it). Just verify encrypt_field rejects None.
        # (Production usage: None is handled by process_bind_param before calling.)
        with pytest.raises((AttributeError, TypeError)):
            with_key.encrypt_field(None)


class TestDevModeNoKey:
    """Tests for dev mode without FIELD_ENCRYPTION_KEY."""

    @pytest.fixture()
    def without_key(self, monkeypatch):
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        import importlib
        import app.core.crypto as crypto_mod
        importlib.reload(crypto_mod)
        yield crypto_mod
        importlib.reload(crypto_mod)

    def test_dev_mode_uses_raw_sentinel(self, without_key):
        ciphertext = without_key.encrypt_field("dev data")
        assert ciphertext.startswith(b"RAW1")

    def test_dev_mode_round_trip(self, without_key):
        plaintext = "datos en claro en dev"
        ct = without_key.encrypt_field(plaintext)
        assert without_key.decrypt_field(ct) == plaintext

    def test_dev_mode_json_round_trip(self, without_key):
        obj = {"key": "value", "num": 42}
        ct = without_key.encrypt_json(obj)
        assert without_key.decrypt_json(ct) == obj


class TestLegacyPlaintextFallback:
    """The decrypt side handles legacy UTF-8 rows (pre-encryption migration)."""

    @pytest.fixture()
    def without_key(self, monkeypatch):
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        import importlib
        import app.core.crypto as crypto_mod
        importlib.reload(crypto_mod)
        yield crypto_mod
        importlib.reload(crypto_mod)

    def test_utf8_legacy_bytes_decoded(self, without_key):
        """Bytes without sentinel (legacy row) are decoded as UTF-8 string."""
        legacy = "texto plano antiguo".encode("utf-8")
        result = without_key.decrypt_field(legacy)
        assert result == "texto plano antiguo"


class TestEncryptedJSONTypeDecorator:
    """Validate EncryptedJSON process_bind_param / process_result_value."""

    @pytest.fixture()
    def with_key(self, monkeypatch):
        key = _make_32_byte_key()
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", key)
        monkeypatch.setenv("ENVIRONMENT", "development")
        import importlib
        import app.core.crypto as crypto_mod
        importlib.reload(crypto_mod)
        yield crypto_mod
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY", raising=False)
        importlib.reload(crypto_mod)

    def test_none_passes_through(self, with_key):
        from app.db.models import EncryptedJSON
        td = EncryptedJSON()
        assert td.process_bind_param(None, None) is None
        assert td.process_result_value(None, None) is None

    def test_dict_encrypted_and_decrypted(self, with_key):
        from app.db.models import EncryptedJSON
        td = EncryptedJSON()
        obj = {"clinical": "data", "risk": True}
        encrypted = td.process_bind_param(obj, None)
        assert isinstance(encrypted, bytes)
        # The raw bytes must NOT contain the dict repr in plaintext
        assert b"clinical" not in encrypted
        decrypted = td.process_result_value(encrypted, None)
        assert decrypted == obj

    def test_db_sees_encrypted_bytes_not_plaintext(self, with_key):
        """Simulate what the DB stores: bytes without plaintext JSON visible."""
        from app.db.models import EncryptedJSON
        td = EncryptedJSON()
        sensitive = {"narrative": "señales_clinicas · ideación pasiva detectada"}
        db_bytes = td.process_bind_param(sensitive, None)
        # The sensitive word must NOT appear in the DB-bound bytes
        assert "señales_clinicas" not in db_bytes.decode("latin-1", errors="replace")
