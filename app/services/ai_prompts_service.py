"""AI prompts versioning · Bloque N.

`get_active_prompt(key)` returns the currently active prompt content. Cache
TTL 60 s. Service layer reads prompts via this helper instead of from
filesystem so super_admin can roll prompts forward without redeploys.

If no prompt exists in DB, returns the optional fallback. Existing services
should pass their current hardcoded prompt as the fallback — that way the
migration to DB-backed prompts is non-breaking (DB is empty initially → all
services keep working with their current prompts).
"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.db.models import AIPrompt


_CACHE: dict = {"ts": 0.0, "data": {}}
_TTL = 60


def _load(db: DBSession) -> dict:
    now = time.time()
    if _CACHE["data"] and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["data"]
    rows = db.query(AIPrompt).filter(AIPrompt.is_active == True).all()  # noqa: E712
    data = {r.key: {"content": r.content, "version": r.version} for r in rows}
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data


def invalidate_cache() -> None:
    _CACHE["ts"] = 0.0
    _CACHE["data"] = {}


def get_active_prompt(db: DBSession, key: str, fallback: Optional[str] = None) -> Optional[str]:
    cache = _load(db)
    entry = cache.get(key)
    if entry:
        return entry["content"]
    return fallback
