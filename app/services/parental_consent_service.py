"""Consentimiento parental para menores · M-006 (2026-06-04).

E-sign nativo: un estudiante menor de 16 indica el email de su acudiente; se
genera un token de un solo uso (con expiración) que se envía por email como
enlace de firma. El acudiente abre el enlace, lee el texto legal y firma →
se otorga `parental` vía `consent_service.grant_consent` (+ audit).

Decisiones:
- Umbral = 16 (constante `MINOR_AGE_THRESHOLD`). Distinto de `consent_service.
  is_minor` (que es <18 y default-deny para el gate de CRM).
- **Solo se bloquea si la fecha de nacimiento es CONOCIDA y la edad < 16.** Si
  `birthdate` es NULL no se bloquea (no romper a usuarios sin fecha cargada).
"""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.data.parental_consent import (
    CONSENT_TEXT,
    CONSENT_TOKEN_TTL_HOURS,
    CONSENT_VERSION,
    MINOR_AGE_THRESHOLD,
)
from app.db.models import User
from app.services import consent_service, email_service

logger = logging.getLogger(__name__)


class ParentalConsentError(RuntimeError):
    """Errores de validación del flujo de consentimiento (token inválido, etc.)."""


# ---------------------------------------------------------------------------
# Predicados de edad / requerimiento
# ---------------------------------------------------------------------------


def age_of(user: User) -> Optional[int]:
    bd = getattr(user, "birthdate", None)
    if not bd:
        return None
    today = date.today()
    return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))


def is_minor_under_threshold(user: User) -> bool:
    """True solo si la edad es CONOCIDA y < umbral. NULL → False (no bloquea)."""
    age = age_of(user)
    return age is not None and age < MINOR_AGE_THRESHOLD


def needs_parental_consent(user: User) -> bool:
    """¿Debe bloquearse a este usuario hasta tener consentimiento parental?"""
    if user is None:
        return False
    return is_minor_under_threshold(user) and user.consent_parental_at is None


def _mask_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    head = local[0] if local else ""
    return f"{head}***@{domain}"


def consent_status(user: User) -> Dict[str, Any]:
    """Estado para el estudiante (FE): si requiere, si ya tiene, si está pendiente."""
    pending = bool(
        user.parental_consent_token
        and user.parental_consent_token_expires
        and user.parental_consent_token_expires > datetime.utcnow()
    )
    return {
        "required": is_minor_under_threshold(user),
        "granted": user.consent_parental_at is not None,
        "pending": pending and user.consent_parental_at is None,
        "parent_email_masked": _mask_email(user.parental_consent_parent_email),
        "expires_at": (
            user.parental_consent_token_expires.isoformat()
            if pending
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Flujo de firma
# ---------------------------------------------------------------------------


def request_consent(
    db: DBSession,
    student: User,
    parent_email: str,
    *,
    request: Optional[Request] = None,
) -> Dict[str, Any]:
    """Genera token de un solo uso y envía el enlace de firma al acudiente."""
    parent_email = (parent_email or "").strip().lower()
    if "@" not in parent_email or "." not in parent_email:
        raise ParentalConsentError("Email del acudiente inválido.")

    token = secrets.token_urlsafe(32)
    student.parental_consent_token = token
    student.parental_consent_token_expires = datetime.utcnow() + timedelta(
        hours=CONSENT_TOKEN_TTL_HOURS
    )
    student.parental_consent_parent_email = parent_email
    db.commit()

    base = get_settings().frontend_base_url.rstrip("/")
    link = f"{base}/consentimiento-parental/{token}"
    student_name = student.name or "tu hijo/a"
    subject = "Grasshopper · Autorización para un menor"
    html_body = (
        f"<p>Hola,</p>"
        f"<p>{student_name} te pidió autorizar su uso de la plataforma "
        f"Grasshopper (tests de orientación vocacional y acompañamiento).</p>"
        f"<p>Para revisar y firmar el consentimiento, abre este enlace "
        f"(válido por {CONSENT_TOKEN_TTL_HOURS} horas):</p>"
        f'<p><a href="{link}">{link}</a></p>'
        f"<p>Si no reconoces esta solicitud, puedes ignorar este correo.</p>"
    )
    result = email_service.send_email(
        to=parent_email,
        subject=subject,
        html_body=html_body,
        text_body=f"{student_name} te pidió autorizar Grasshopper. Firma aquí: {link}",
    )
    logger.info(
        "parental consent requested student=%s provider=%s delivered=%s",
        student.id,
        result.provider,
        result.delivered,
    )
    return {
        "sent": result.delivered,
        "provider": result.provider,
        "parent_email_masked": _mask_email(parent_email),
        "expires_at": student.parental_consent_token_expires.isoformat(),
    }


def _student_by_token(db: DBSession, token: str) -> Optional[User]:
    if not token:
        return None
    return (
        db.query(User)
        .filter(User.parental_consent_token == token)
        .first()
    )


def lookup(db: DBSession, token: str) -> Dict[str, Any]:
    """Datos para la pantalla del acudiente (sin auth). Lanza si token inválido."""
    student = _student_by_token(db, token)
    if not student:
        raise ParentalConsentError("Enlace inválido o ya utilizado.")
    expired = (
        not student.parental_consent_token_expires
        or student.parental_consent_token_expires <= datetime.utcnow()
    )
    return {
        "student_name": student.name or "el/la estudiante",
        "parent_email_masked": _mask_email(student.parental_consent_parent_email),
        "consent_text": CONSENT_TEXT,
        "version": CONSENT_VERSION,
        "expired": expired,
        "already_signed": student.consent_parental_at is not None,
    }


def sign(db: DBSession, token: str, *, request: Optional[Request] = None) -> Dict[str, Any]:
    """El acudiente firma → otorga consentimiento parental + audit. Token de un solo uso."""
    student = _student_by_token(db, token)
    if not student:
        raise ParentalConsentError("Enlace inválido o ya utilizado.")
    if (
        not student.parental_consent_token_expires
        or student.parental_consent_token_expires <= datetime.utcnow()
    ):
        raise ParentalConsentError("El enlace expiró. Pide uno nuevo.")

    consent_service.grant_consent(
        db, student, "parental", request=request, policy_version=CONSENT_VERSION
    )
    # Consumir el token (un solo uso).
    student.parental_consent_token = None
    student.parental_consent_token_expires = None
    db.commit()
    logger.info("parental consent signed student=%s", student.id)
    return {"signed": True, "student_name": student.name or "el/la estudiante"}
