"""Feature flags helper · Bloque M.

`is_feature_enabled(key, user)` is the canonical resolver. Resolution order:
  1. flag missing → False (fail-closed)
  2. flag.enabled is True → True (global on)
  3. user.role.value in flag.enabled_for_roles → True
  4. user.school_id in flag.enabled_for_school_ids → True
  5. otherwise False

Cached in-process for 60 s · `invalidate_cache()` after writes.
"""
from __future__ import annotations

import time
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import FeatureFlag, User


_CACHE: dict = {"ts": 0.0, "data": {}}
_TTL = 60


def _load(db: DBSession) -> dict:
    now = time.time()
    if _CACHE["data"] and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["data"]
    rows = db.query(FeatureFlag).all()
    data = {
        r.key: {
            "enabled": bool(r.enabled),
            "roles": list(r.enabled_for_roles or []),
            "schools": [str(s) for s in (r.enabled_for_school_ids or [])],
        }
        for r in rows
    }
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data


def invalidate_cache() -> None:
    _CACHE["ts"] = 0.0
    _CACHE["data"] = {}


def is_feature_enabled(db: DBSession, key: str, user: Optional[User]) -> bool:
    flags = _load(db)
    f = flags.get(key)
    if not f:
        return False
    if f["enabled"]:
        return True
    if user is None:
        return False
    if user.role.value in f["roles"]:
        return True
    if user.school_id and str(user.school_id) in f["schools"]:
        return True
    return False
