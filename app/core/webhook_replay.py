"""Replay protection para webhooks inbound.

GH-S11.5-BE-11 · migra el guard de in-memory a Postgres para que multiples
dynos de Heroku compartan el mismo registro de nonces vistos.

Dos implementaciones:

  - ``PostgresWebhookReplayGuard``  PRODUCCION: usa la tabla webhook_nonces.
  - ``InMemoryWebhookReplayGuard``  DEPRECATED: solo para tests unitarios que
                                    no pueden tocar una DB real.

API publica compartida:
    guard.check_timestamp(ts: float, now: float | None) -> tuple[bool, str]
    guard.is_replay(nonce: str, source: str, db) -> bool
    guard.mark_seen(nonce: str, source: str, db, ttl_seconds: int) -> None
    guard.check_and_mark(nonce: str, source: str, db, ttl_seconds: int) -> bool
    guard.remember_nonce(nonce: str, now: float | None) -> bool  # compat S11

El modulo expone ``bitrix_replay_guard`` como singleton Postgres; el router
de Bitrix lo usa sin cambiar su signatura de llamada.

Cleanup de filas expiradas:
    ``delete_expired_nonces(db)`` puede llamarse desde un job de Heroku
    Scheduler o desde el handler de startup de FastAPI como asyncio background
    task. Ver ``app/main.py``.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    """Retorna datetime UTC sin timezone (compatible Postgres y SQLite)."""
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


# ===========================================================================
# PostgresWebhookReplayGuard - PRODUCCION
# ===========================================================================


class PostgresWebhookReplayGuard:
    """Guard persistente que usa la tabla ``webhook_nonces`` (Postgres/Neon).

    Diseno de la query atomica
    --------------------------
    La operacion check_and_mark se implementa en una sola sentencia:

        INSERT INTO webhook_nonces (nonce, source, seen_at, expires_at)
        VALUES (:nonce, :source, :seen_at, :expires_at)
        ON CONFLICT (nonce) DO NOTHING
        RETURNING nonce

    Si RETURNING devuelve una fila el nonce era nuevo (no replay).
    Si RETURNING devuelve vacio hubo conflicto (nonce ya existia) = replay.

    Esto elimina la race condition entre un SELECT y un INSERT separados.
    Postgres garantiza que solo uno de los dos INSERT "gana" gracias al
    constraint de PK.
    """

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
        self.nonce_ttl_s = (
            nonce_ttl_s if nonce_ttl_s is not None else s.webhook_nonce_ttl_s
        )

    def check_timestamp(
        self, ts: float, now: Optional[float] = None
    ) -> tuple[bool, str]:
        """Devuelve ``(ok, reason)``. ``reason`` vacio cuando ok."""
        now_val = now if now is not None else time.time()
        if ts <= 0:
            return False, "missing_timestamp"
        delta = abs(now_val - ts)
        if delta > self.timestamp_tolerance_s:
            return False, f"timestamp_skew={int(delta)}s"
        return True, ""

    def is_replay(
        self,
        nonce: str,
        source: str,
        db,
    ) -> bool:
        """Devuelve True si el nonce ya fue visto y no ha expirado."""
        if not nonce:
            return False
        from sqlalchemy import text

        now = _utcnow_naive()
        row = db.execute(
            text(
                "SELECT 1 FROM webhook_nonces "
                "WHERE nonce = :nonce AND source = :source AND expires_at > :now"
            ),
            {"nonce": nonce, "source": source, "now": now},
        ).first()
        return row is not None

    def mark_seen(
        self,
        nonce: str,
        source: str,
        db,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Registra el nonce. No lanza si ya existe (idempotente)."""
        if not nonce:
            return
        ttl = ttl_seconds if ttl_seconds is not None else self.nonce_ttl_s
        now = _utcnow_naive()
        expires_at = now + timedelta(seconds=ttl)
        from sqlalchemy import text

        db.execute(
            text(
                "INSERT INTO webhook_nonces (nonce, source, seen_at, expires_at) "
                "VALUES (:nonce, :source, :seen_at, :expires_at) "
                "ON CONFLICT (nonce) DO NOTHING"
            ),
            {"nonce": nonce, "source": source, "seen_at": now, "expires_at": expires_at},
        )
        db.commit()

    def check_and_mark(
        self,
        nonce: str,
        source: str,
        db,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Atomico: intenta insertar el nonce y devuelve True si es la primera vez.

        Usa INSERT ON CONFLICT DO NOTHING RETURNING para eliminar la race
        condition entre check e insert. El dyno que "gana" recibe el RETURNING;
        el que llega segundo ve vacio y sabe que es replay.

        Returns:
            True  nonce era nuevo (no replay), ya registrado.
            False nonce ya existia (replay), operacion abortada.
        """
        if not nonce:
            return False
        ttl = ttl_seconds if ttl_seconds is not None else self.nonce_ttl_s
        now = _utcnow_naive()
        expires_at = now + timedelta(seconds=ttl)
        from sqlalchemy import text

        result = db.execute(
            text(
                "INSERT INTO webhook_nonces (nonce, source, seen_at, expires_at) "
                "VALUES (:nonce, :source, :seen_at, :expires_at) "
                "ON CONFLICT (nonce) DO NOTHING "
                "RETURNING nonce"
            ),
            {"nonce": nonce, "source": source, "seen_at": now, "expires_at": expires_at},
        )
        inserted = result.fetchone()
        db.commit()
        return inserted is not None

    def remember_nonce(self, nonce: str, now: Optional[float] = None) -> bool:
        """DEPRECATED: solo para compatibilidad con tests S11 que no tocan DB.

        En produccion usar ``check_and_mark(nonce, source, db)`` que es atomico
        y cross-dyno safe.
        """
        logger.warning(
            "remember_nonce() usada sin DB (modo in-memory solo test). "
            "En produccion llamar check_and_mark(nonce, source, db)."
        )
        return self._mem_guard.remember_nonce(nonce, now)

    def reset(self) -> None:
        """Test helper: limpia el fallback in-memory."""
        self._mem_guard.reset()

    @property
    def _mem_guard(self) -> "InMemoryWebhookReplayGuard":
        if not hasattr(self, "_mem_guard_instance"):
            object.__setattr__(
                self,
                "_mem_guard_instance",
                InMemoryWebhookReplayGuard(
                    timestamp_tolerance_s=self.timestamp_tolerance_s,
                    nonce_ttl_s=self.nonce_ttl_s,
                ),
            )
        return self._mem_guard_instance  # type: ignore[return-value]


# ===========================================================================
# InMemoryWebhookReplayGuard - DEPRECATED - solo para tests sin DB
# ===========================================================================


@dataclass
class _NonceEntry:
    expires_at: float


class InMemoryWebhookReplayGuard:
    """Guard in-memory. DEPRECATED: usado solo en tests unitarios donde no
    se puede tocar una DB real. En produccion el guard es PostgresWebhookReplayGuard.

    Mantiene la misma API que el guard original de S11 para que los tests
    existentes de ``test_sprint11_hardening.py`` sigan pasando sin cambios.
    """

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
        self.nonce_ttl_s = (
            nonce_ttl_s if nonce_ttl_s is not None else s.webhook_nonce_ttl_s
        )
        self._nonces: dict[str, _NonceEntry] = {}
        self._lock = threading.Lock()

    def _purge_expired(self, now: float) -> None:
        expired = [n for n, entry in self._nonces.items() if entry.expires_at <= now]
        for n in expired:
            self._nonces.pop(n, None)

    def check_timestamp(
        self, ts: float, now: Optional[float] = None
    ) -> tuple[bool, str]:
        """Devuelve ``(ok, reason)``. ``reason`` vacio cuando ok."""
        now_val = now if now is not None else time.time()
        if ts <= 0:
            return False, "missing_timestamp"
        delta = abs(now_val - ts)
        if delta > self.timestamp_tolerance_s:
            return False, f"timestamp_skew={int(delta)}s"
        return True, ""

    def remember_nonce(self, nonce: str, now: Optional[float] = None) -> bool:
        """Registra un nonce. Devuelve False si ya fue visto dentro del TTL (replay)."""
        if not nonce:
            return False
        now_val = now if now is not None else time.time()
        with self._lock:
            self._purge_expired(now_val)
            entry = self._nonces.get(nonce)
            if entry is not None and entry.expires_at > now_val:
                return False  # replay
            self._nonces[nonce] = _NonceEntry(expires_at=now_val + self.nonce_ttl_s)
            return True

    def reset(self) -> None:
        """Test helper: elimina todos los nonces recordados."""
        with self._lock:
            self._nonces.clear()

    def check_and_mark(
        self,
        nonce: str,
        source: str,
        db=None,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Alias para remember_nonce (sin DB, solo tests)."""
        return self.remember_nonce(nonce)


# ===========================================================================
# Cleanup de filas expiradas (scheduler o startup)
# ===========================================================================


def delete_expired_nonces(db) -> int:
    """Borra filas de webhook_nonces cuyo expires_at < ahora.

    Retorna la cantidad de filas eliminadas.

    Puede ser invocado:
      - Desde un job de Heroku Scheduler.
      - Desde un background asyncio task en FastAPI startup (ver main.py).

    La query es barata: filtra por el indice ``ix_webhook_nonces_expires_at``.
    Usa datetime parametrizado (no NOW() del SQL) para maxima compatibilidad
    entre Postgres y SQLite (tests).
    """
    from sqlalchemy import text

    now = _utcnow_naive()
    result = db.execute(
        text("DELETE FROM webhook_nonces WHERE expires_at < :now"),
        {"now": now},
    )
    db.commit()
    deleted = result.rowcount
    if deleted:
        logger.info("webhook_nonces: %d filas expiradas eliminadas", deleted)
    return deleted


# ===========================================================================
# Singleton de modulo usado por el router de Bitrix
# ===========================================================================

bitrix_replay_guard = PostgresWebhookReplayGuard()

# Alias para compatibilidad con tests S11 que importan WebhookReplayGuard
WebhookReplayGuard = InMemoryWebhookReplayGuard  # type: ignore[misc]
# DEPRECATED: los nuevos tests deben usar PostgresWebhookReplayGuard directamente.


__all__ = [
    "PostgresWebhookReplayGuard",
    "InMemoryWebhookReplayGuard",
    "WebhookReplayGuard",
    "bitrix_replay_guard",
    "delete_expired_nonces",
]
