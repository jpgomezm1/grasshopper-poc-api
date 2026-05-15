"""At-rest field encryption · AES-256-GCM · GH-F1-SECURITY · Tarea 4.

Protects sensitive JSONB columns (clinical_analysis_cache) that contain
psychological data governed by Ley 1090/2006 (Código Deontológico del
Psicólogo) and Ley 1581/2012 art. 5 (datos sensibles).

Design decisions:
  D-AES-01  · AES-256-GCM (authenticated encryption) over AES-CBC or
              pgcrypto. GCM provides both confidentiality and integrity with
              no extra HMAC step. 256-bit key from a 32-byte base64 env var.

  D-AES-02  · Random 96-bit (12-byte) nonce per encryption call. The
              ciphertext stored in the DB is: nonce (12 bytes) || tag (16
              bytes built-in to AEADCiphertext) || ciphertext payload.
              The tag is extracted by AESGCM automatically.

  D-AES-03  · App-level encryption, NOT pgcrypto. Avoids needing the
              pgcrypto extension in Neon (serverless limitations) and keeps
              key management entirely in app code + Heroku config vars.

  D-AES-04  · Key loaded once at module import. If FIELD_ENCRYPTION_KEY is
              absent in production the module raises RuntimeError immediately
              (fail-fast pattern matching JWT_SECRET_KEY assertion).

Key provisioning:
  Generate a 32-byte key:
    python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  Set in Heroku:
    heroku config:set FIELD_ENCRYPTION_KEY=<output> -a grasshopper-api

  TODO (JP · Heroku URGENTE antes de deploy):
    1. Generar clave con el comando arriba
    2. heroku config:set FIELD_ENCRYPTION_KEY=<clave> -a grasshopper-api
    3. Correr `alembic upgrade head` en prod para agregar columna _encrypted
    4. Correr script de migración de data si hay rows existentes en clinical_analysis_cache
       (ver migration 037_encrypt_clinical_analysis.py)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# Nonce size: 12 bytes (96 bits) — NIST recommended for AES-GCM
_NONCE_BYTES = 12


def _load_key() -> bytes | None:
    """Load and decode FIELD_ENCRYPTION_KEY from environment.

    Returns None if the var is absent (development/test mode).
    Raises RuntimeError if the var is present but malformed.
    """
    raw = os.environ.get("FIELD_ENCRYPTION_KEY", "")
    if not raw:
        environment = os.environ.get("ENVIRONMENT", "development")
        if environment == "production":
            raise RuntimeError(
                "FIELD_ENCRYPTION_KEY must be set in production. "
                "Generate with: python -c \"import secrets, base64; "
                "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\""
                " then set FIELD_ENCRYPTION_KEY in Heroku config vars."
            )
        # In development/test: log a warning and return None (encryption disabled)
        logger.warning(
            "crypto.field_encryption_disabled "
            "FIELD_ENCRYPTION_KEY not set · clinical_analysis_cache stored in plaintext · "
            "set FIELD_ENCRYPTION_KEY for at-rest encryption"
        )
        return None

    try:
        key_bytes = base64.urlsafe_b64decode(raw + "==")  # pad for base64 tolerance
    except Exception as exc:
        raise RuntimeError(
            f"FIELD_ENCRYPTION_KEY is not valid base64: {exc}"
        ) from exc

    if len(key_bytes) != 32:
        raise RuntimeError(
            f"FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes (got {len(key_bytes)}). "
            "Re-generate with: python -c \"import secrets, base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\""
        )

    return key_bytes


# Load key at module import time so any misconfiguration is caught at boot
_KEY_BYTES: bytes | None = _load_key()


def encrypt_field(plaintext: str) -> bytes:
    """Encrypt a plaintext string with AES-256-GCM.

    If FIELD_ENCRYPTION_KEY is not set (dev mode), returns the plaintext
    encoded as UTF-8 bytes with a sentinel prefix so the decrypt side
    knows it's unencrypted.

    Wire format (encrypted):  b"ENC1" + nonce(12) + aesgcm_ciphertext
    Wire format (plaintext):  b"RAW1" + plaintext.encode("utf-8")
    """
    if _KEY_BYTES is None:
        # Dev mode: store as raw bytes with sentinel
        return b"RAW1" + plaintext.encode("utf-8")

    nonce = secrets.token_bytes(_NONCE_BYTES)
    aesgcm = AESGCM(_KEY_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return b"ENC1" + nonce + ciphertext


def decrypt_field(ciphertext: bytes) -> str:
    """Decrypt bytes produced by encrypt_field back to plaintext string.

    Handles both the encrypted (ENC1) and dev-mode plaintext (RAW1) formats.
    If neither sentinel is present, attempts UTF-8 decode as a last resort
    (migration path for any legacy plaintext rows).
    """
    if ciphertext[:4] == b"RAW1":
        return ciphertext[4:].decode("utf-8")

    if ciphertext[:4] == b"ENC1":
        if _KEY_BYTES is None:
            raise RuntimeError(
                "Cannot decrypt ENC1 data without FIELD_ENCRYPTION_KEY. "
                "Set the env var to the same key used when encrypting."
            )
        nonce = ciphertext[4 : 4 + _NONCE_BYTES]
        payload = ciphertext[4 + _NONCE_BYTES :]
        aesgcm = AESGCM(_KEY_BYTES)
        return aesgcm.decrypt(nonce, payload, None).decode("utf-8")

    # Legacy plaintext row (pre-encryption migration) — decode as UTF-8 directly
    try:
        return ciphertext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Cannot decode field: unknown format (not ENC1, not RAW1, not UTF-8). "
            "The data may be corrupted or encrypted with a different key."
        ) from exc


def encrypt_json(obj: Any) -> bytes:
    """Serialize `obj` to JSON then encrypt."""
    return encrypt_field(json.dumps(obj, ensure_ascii=False))


def decrypt_json(ciphertext: bytes) -> Any:
    """Decrypt bytes and deserialize from JSON."""
    return json.loads(decrypt_field(ciphertext))
