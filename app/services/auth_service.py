"""Auth helpers · multi-role enforcement.

GH-S2-BE-02 · centralizes the logic that decides whether the current user
can access a given endpoint based on their role.

Usage:

    from fastapi import APIRouter, Depends
    from app.services.auth_service import require_role
    from app.db.models import UserRole, User

    router = APIRouter()

    @router.get("/admin/something")
    def something(current_user: User = Depends(require_role(UserRole.SUPER_ADMIN))):
        ...

    # Multiple roles allowed:
    @router.get("/school/me")
    def school_me(
        current_user: User = Depends(require_role(UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST))
    ):
        ...

Security notes:
- The dependency raises 403 if the role does not match. It does NOT leak
  whether the resource exists.
- Combine with row-level filtering (e.g. school_id ownership) for IDOR safety.
"""
from __future__ import annotations

from typing import Callable, Iterable

from fastapi import Depends, HTTPException, status

from app.api.v1.auth import get_current_user
from app.db.models import User, UserRole


def require_role(*allowed_roles: UserRole) -> Callable[[User], User]:
    """FastAPI dependency factory that enforces role membership.

    Returns a dependency that resolves to the current `User` if their role is
    in `allowed_roles`, raises HTTP 403 otherwise.
    """
    if not allowed_roles:
        raise ValueError("require_role() needs at least one role")

    allowed_set = set(allowed_roles)

    def _enforcer(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden · your role does not allow this action.",
            )
        return current_user

    # Useful for debugging in /docs
    _enforcer.__name__ = f"require_role[{','.join(r.value for r in allowed_roles)}]"
    return _enforcer


def require_super_admin() -> Callable[[User], User]:
    """Shorthand · only super_admin can pass."""
    return require_role(UserRole.SUPER_ADMIN)


def require_school_staff() -> Callable[[User], User]:
    """Shorthand · school_admin or psychologist · staff of a B2B colegio."""
    return require_role(UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST)


def is_role(user: User, *roles: UserRole) -> bool:
    """Plain boolean helper for in-handler logic (avoid duplicating logic)."""
    return user.role in set(roles)


def assert_same_school_or_super_admin(actor: User, target_school_id) -> None:
    """Authorization guard for school-scoped resources.

    - super_admin can act on any school
    - school_admin and psychologist can act ONLY on their own school
    - student / unauthenticated callers should never reach this helper

    Raises 403 if the actor is not allowed to act on `target_school_id`.
    """
    if actor.role == UserRole.SUPER_ADMIN:
        return
    if actor.role in (UserRole.SCHOOL_ADMIN, UserRole.PSYCHOLOGIST):
        if actor.school_id is not None and str(actor.school_id) == str(target_school_id):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden · you cannot access resources of a different school.",
    )


def list_roles(roles: Iterable[UserRole]) -> list[str]:
    """Stable serialization of role lists for logs / OpenAPI metadata."""
    return sorted(r.value for r in roles)
