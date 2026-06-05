"""Consentimiento parental para menores · M-006 (2026-06-04).

Routers:
  - router_me (auth · /me/parental-consent): el estudiante menor solicita el
    consentimiento (envía email al acudiente) y consulta su estado.
  - router_public (sin auth · /parental-consent/{token}): el acudiente abre el
    enlace recibido por email, lo revisa y firma (e-sign nativo).

Además expone la dependencia `require_parental_consent_if_minor` que protege
endpoints sensibles (tests vocacionales + journey) bloqueando a menores de 16
que aún no tienen consentimiento parental firmado.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services import parental_consent_service
from app.services.parental_consent_service import ParentalConsentError

router_me = APIRouter(prefix="/me/parental-consent", tags=["StudentMe · Parental consent"])
router_public = APIRouter(prefix="/parental-consent", tags=["Parental consent (público)"])


def _rate_limit_consent(request: Request) -> None:
    """M-006 · limita abuso: spam de email (request) y fuerza bruta del token."""
    from app.core.rate_limiter import rate_limit
    return rate_limit(get_settings().rate_limit_parental_consent)(request)


# ---------------------------------------------------------------------------
# Dependencia de gate (reutilizable)
# ---------------------------------------------------------------------------


def require_parental_consent_if_minor(
    current_user: User = Depends(get_current_user),
) -> User:
    """403 si el usuario es menor de 16 (edad conocida) sin consentimiento."""
    if parental_consent_service.needs_parental_consent(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="minor_parental_consent_required",
        )
    return current_user


# ---------------------------------------------------------------------------
# Estudiante (auth)
# ---------------------------------------------------------------------------


class RequestConsentBody(BaseModel):
    parent_email: str


@router_me.get("/status", summary="M-006 · estado del consentimiento parental")
def get_status(current_user: User = Depends(get_current_user)):
    return parental_consent_service.consent_status(current_user)


@router_me.post(
    "/request",
    summary="M-006 · enviar enlace de firma al acudiente",
    dependencies=[Depends(_rate_limit_consent)],
)
def request_consent(
    body: RequestConsentBody,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="student-only endpoint")
    if current_user.consent_parental_at is not None:
        raise HTTPException(status_code=400, detail="El consentimiento ya fue otorgado.")
    try:
        return parental_consent_service.request_consent(
            db, current_user, body.parent_email, request=request
        )
    except ParentalConsentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Acudiente (público · token)
# ---------------------------------------------------------------------------


@router_public.get(
    "/{token}",
    summary="M-006 · datos del consentimiento (acudiente)",
    dependencies=[Depends(_rate_limit_consent)],
)
def public_lookup(token: str, db: DBSession = Depends(get_db)):
    try:
        return parental_consent_service.lookup(db, token)
    except ParentalConsentError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router_public.post(
    "/{token}/sign",
    summary="M-006 · firmar consentimiento (acudiente)",
    dependencies=[Depends(_rate_limit_consent)],
)
def public_sign(token: str, request: Request, db: DBSession = Depends(get_db)):
    try:
        return parental_consent_service.sign(db, token, request=request)
    except ParentalConsentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
