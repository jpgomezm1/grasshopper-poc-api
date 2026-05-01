"""In-memory replay protection for inbound webhooks.

GH-S11 hardening over S10 · enforces:
  1. Timestamp tolerance (default 5 min) so a stolen payload cannot be
     re-submitted hours later.
  2. Nonce uniqueness within a TTL window (default 10 min) so the exact
     same payload cannot be replayed twice in the tolerance window.

Storage is process-local (a dict). For Heroku web dynos that means each
worker keeps its own cache · acceptable trade-off because:
  - HMAC + timestamp already block targeted replays per-dyno.
  - The TTL window is short (10 min) and Bitrix retries are rare.
  - Moving to Redis is queued for S12 if cross-dyno dedup becomes a need.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import get_settings


@dataclass
class _NonceEntry:
    expires_at: float


class WebhookReplayGuard:
    """Thread-safe replay guard."""

    def __init__(
        self,
        timestamp_tolerance_s: Optional[int] = None,
        nonce_ttl_s: Optional[int] = None,
    ) -> None:
        s = get_settings()
        self.timestamp_tolerance_s = (
            timestamp_tolerance_s
            if timestamp_tolerance_s is not None
            else s.webhook_timestamp_tolerance_s
        )
        self.nonce_ttl_s = nonce_ttl_s if nonce_ttl_s is not None else s.webhook_nonce_ttl_s
        self._nonces: dict[str, _NonceEntry] = {}
        self._lock = threading.Lock()

    def _purge_expired(self, now: float) -> None:
        expired = [n for n, entry in self._nonces.items() if entry.expires_at <= now]
        for n in expired:
            self._nonces.pop(n, None)

    def check_timestamp(self, ts: float, now: Optional[float] = None) -> tuple[bool, str]:
        """Return ``(ok, reason)``. ``reason`` empty when ok."""
        now = now if now is not None else time.time()
        if ts <= 0:
            return False, "missing_timestamp"
        delta = abs(now - ts)
        if delta > self.timestamp_tolerance_s:
            return False, f"timestamp_skew={int(delta)}s"
        return True, ""

    def remember_nonce(self, nonce: str, now: Optional[float] = None) -> bool:
        """Register a nonce. Returns False if already seen within TTL (replay)."""
        if not nonce:
            return False
        now = now if now is not None else time.time()
        with self._lock:
            self._purge_expired(now)
            entry = self._nonces.get(nonce)
            if entry is not None and entry.expires_at > now:
                return False  # replay
            self._nonces[nonce] = _NonceEntry(expires_at=now + self.nonce_ttl_s)
            return True

    def reset(self) -> None:
        """Test helper · drop all remembered nonces."""
        with self._lock:
            self._nonces.clear()


# Module-level singleton used by the Bitrix inbound webhook
bitrix_replay_guard = WebhookReplayGuard()


__all__ = ["WebhookReplayGuard", "bitrix_replay_guard"]
