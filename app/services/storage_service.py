"""Storage service · Supabase Storage abstraction.

GH-S3-INFRA-02/03/04 · D-010

Why this module exists:
- Several future flows need to persist binary files: school logos (S9),
  AI-generated PDF reports (S7), and user-uploaded test results (S5).
- We do NOT want each route to know about Supabase SDK details.
- The interface here is intentionally storage-agnostic so we can swap to
  AWS S3 (boto3) later by replacing this module — no caller changes.

Sprint 3 scope (per JP auto-mode constraint 2026-04-30):
- Do NOT create production buckets or use real service keys.
- Code path must be exercised in tests with a stub backend.
- Real provisioning happens in S12 alongside Heroku/Netlify cutover.

Path convention (enforces IDOR boundary by namespacing per user):
    {user_id}/{type}/{filename}

Examples:
    "42/test_uploads/mbti_2026-05-12.pdf"
    "school_7/logos/colegio-andino.png"           # for school assets we use school_<id>
    "42/snapshot_pdfs/snapshot_2026-05-12.pdf"

Public API:
    upload_file(path, file_bytes, content_type)  -> StorageObject
    get_signed_url(path, expires_in_seconds)     -> str
    delete_file(path)                            -> bool
    object_exists(path)                          -> bool

Configuration via env vars (loaded from app.config.Settings):
    SUPABASE_URL                e.g. https://xxx.supabase.co
    SUPABASE_SERVICE_KEY        service_role key (server-side ONLY · never expose to FE)
    SUPABASE_STORAGE_BUCKET     default "grasshopper-uploads"
    STORAGE_BACKEND             "supabase" | "stub"  · default "stub" if no creds
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Public types
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class StorageObject:
    """Result of a successful upload."""
    bucket: str
    path: str
    content_type: str
    size_bytes: int


class StorageError(RuntimeError):
    """Raised when a storage operation fails."""


# -----------------------------------------------------------------------------
# Backend protocol
# -----------------------------------------------------------------------------

class StorageBackend(Protocol):
    def upload(self, path: str, data: bytes, content_type: str) -> StorageObject: ...
    def signed_url(self, path: str, expires_in: int) -> str: ...
    def delete(self, path: str) -> bool: ...
    def exists(self, path: str) -> bool: ...


# -----------------------------------------------------------------------------
# Stub backend (used in S3 development · no real bucket required)
# -----------------------------------------------------------------------------

class _StubBackend:
    """In-memory backend for local development before S12 provisioning.

    Stores blobs in a process-local dict. Useful for:
    - Integration tests that don't want to hit Supabase
    - Local dev when Tomás runs without SUPABASE_SERVICE_KEY
    - CI

    NOT a substitute for the real backend in any production-like environment.
    """

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self._store: dict[str, tuple[bytes, str]] = {}

    def upload(self, path: str, data: bytes, content_type: str) -> StorageObject:
        self._store[path] = (data, content_type)
        return StorageObject(
            bucket=self.bucket,
            path=path,
            content_type=content_type,
            size_bytes=len(data),
        )

    def signed_url(self, path: str, expires_in: int) -> str:
        if path not in self._store:
            raise StorageError(f"object not found: {path}")
        # Predictable shape so route tests can assert against it.
        return f"https://stub.local/{self.bucket}/{path}?expires_in={expires_in}"

    def delete(self, path: str) -> bool:
        return self._store.pop(path, None) is not None

    def exists(self, path: str) -> bool:
        return path in self._store


# -----------------------------------------------------------------------------
# Supabase backend (lazy-imported · only loaded when configured)
# -----------------------------------------------------------------------------

class _SupabaseBackend:
    """Wrapper around supabase-py storage client.

    Lazy-imports `supabase` so the dependency is only required when actually
    using this backend. Keeps S3 dev light.
    """

    def __init__(self, url: str, service_key: str, bucket: str) -> None:
        try:
            from supabase import create_client  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in S12
            raise StorageError(
                "supabase-py not installed · add `supabase>=2.0` to requirements.txt"
            ) from exc

        self._client = create_client(url, service_key)
        self.bucket = bucket

    def upload(self, path: str, data: bytes, content_type: str) -> StorageObject:
        try:
            res = self._client.storage.from_(self.bucket).upload(
                path=path,
                file=data,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        except Exception as exc:  # pragma: no cover - exercised in S12
            raise StorageError(f"supabase upload failed: {exc}") from exc

        # supabase-py returns different shapes across versions; we don't depend
        # on the response payload — we trust no exception means success.
        logger.info("storage upload ok bucket=%s path=%s", self.bucket, path)
        return StorageObject(
            bucket=self.bucket,
            path=path,
            content_type=content_type,
            size_bytes=len(data),
        )

    def signed_url(self, path: str, expires_in: int) -> str:
        try:
            res = self._client.storage.from_(self.bucket).create_signed_url(
                path=path,
                expires_in=expires_in,
            )
        except Exception as exc:  # pragma: no cover - exercised in S12
            raise StorageError(f"signed url failed: {exc}") from exc

        # supabase-py returns {"signedURL": "..."} or {"signed_url": "..."}
        # depending on version · normalize.
        url = res.get("signedURL") or res.get("signed_url") if isinstance(res, dict) else None
        if not url:
            raise StorageError(f"signed url payload unexpected: {res!r}")
        return url

    def delete(self, path: str) -> bool:
        try:
            self._client.storage.from_(self.bucket).remove([path])
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("storage delete failed path=%s err=%s", path, exc)
            return False

    def exists(self, path: str) -> bool:  # pragma: no cover
        # supabase-py has no cheap exists check; we'd HEAD via signed_url.
        # For now, attempt list and look for the file.
        prefix = path.rsplit("/", 1)[0] if "/" in path else ""
        target = path.rsplit("/", 1)[-1]
        try:
            entries = self._client.storage.from_(self.bucket).list(path=prefix)
            return any(e.get("name") == target for e in entries)
        except Exception:
            return False


# -----------------------------------------------------------------------------
# Service singleton (per-process)
# -----------------------------------------------------------------------------

_backend: StorageBackend | None = None


def _build_backend() -> StorageBackend:
    """Resolve which backend to use based on settings.

    Defaults to the stub backend if no SUPABASE_SERVICE_KEY is set, so that
    local dev and tests work out of the box. The moment JP+Tomás drop a real
    service key in `.env`, the Supabase backend takes over with no code change.
    """
    from app.config import get_settings

    settings = get_settings()
    bucket = settings.supabase_storage_bucket

    backend_choice = (settings.storage_backend or "").strip().lower()
    if not backend_choice:
        backend_choice = "supabase" if settings.supabase_service_key else "stub"

    if backend_choice == "supabase":
        if not (settings.supabase_url and settings.supabase_service_key):
            logger.warning(
                "STORAGE_BACKEND=supabase but creds missing · falling back to stub"
            )
            return _StubBackend(bucket=bucket)
        return _SupabaseBackend(
            url=settings.supabase_url,
            service_key=settings.supabase_service_key,
            bucket=bucket,
        )

    return _StubBackend(bucket=bucket)


def get_backend() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = _build_backend()
    return _backend


def reset_backend_for_tests() -> None:
    """Hook for unit tests to force a fresh backend."""
    global _backend
    _backend = None


# -----------------------------------------------------------------------------
# Public functions (the surface every caller should use)
# -----------------------------------------------------------------------------

def build_user_path(user_id: int | str, type_: str, filename: str) -> str:
    """Compose the canonical path for a user-scoped upload.

    Enforces the {user_id}/{type}/{filename} convention so security audits
    in S11-QA-05 can rely on it. Raises if any segment looks unsafe.
    """
    safe_filename = filename.replace("\\", "/").split("/")[-1]
    if not safe_filename or safe_filename in {".", ".."}:
        raise ValueError(f"invalid filename: {filename!r}")
    if "/" in type_ or not type_:
        raise ValueError(f"invalid type: {type_!r}")
    return f"{user_id}/{type_}/{safe_filename}"


def build_school_path(school_id: int | str, type_: str, filename: str) -> str:
    """Compose the canonical path for a school-scoped upload (e.g. logos)."""
    return build_user_path(f"school_{school_id}", type_, filename)


def upload_file(
    path: str,
    data: bytes,
    content_type: str,
    *,
    max_size_mb: Optional[int] = 10,
) -> StorageObject:
    """Upload bytes to storage at the given path.

    Guards:
    - Optional max_size enforcement to avoid runaway uploads (S5 sets 10MB).
    """
    if max_size_mb is not None and len(data) > max_size_mb * 1024 * 1024:
        raise StorageError(
            f"file exceeds {max_size_mb}MB limit (got {len(data) / 1024 / 1024:.1f}MB)"
        )
    return get_backend().upload(path=path, data=data, content_type=content_type)


def get_signed_url(path: str, expires_in_seconds: int = 3600) -> str:
    """Return a time-limited URL for the FE/client to download the object.

    Default TTL is 1h so leaked links auto-expire fast. For PDFs that students
    share with parents, the FE should re-request before each share.
    """
    if expires_in_seconds < 60 or expires_in_seconds > 60 * 60 * 24 * 7:
        raise ValueError("expires_in_seconds must be between 60s and 7d")
    return get_backend().signed_url(path=path, expires_in=expires_in_seconds)


def delete_file(path: str) -> bool:
    return get_backend().delete(path=path)


def object_exists(path: str) -> bool:
    return get_backend().exists(path=path)
