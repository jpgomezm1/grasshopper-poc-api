"""Report orchestration service · Sprint 7.

GH-S7-BE-04/05/06 · ties together pdf_service + storage_service + email_service
and persists the Report row.

Public API:
    generate_and_store_report(db, user) -> (Report, signed_url, is_stale)
    get_report_for_user(db, report_id, requester) -> Report
    send_report_via_email(db, report, requester, recipient_override) -> EmailSendResult
    user_can_access_report(requester, report, target_user) -> bool

Permission model (S7-BE-05):
    student     · only their OWN reports (`report.user_id == requester.id`)
    psychologist · reports of users in the same school
    school_admin · reports of users in the same school
    super_admin  · all reports
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    Report,
    School,
    User,
    UserRole,
    VocationalTestResult,
)
from app.schemas.consolidated_profile import (
    ConsolidatedProfile,
    RecommendedProgram,
)
from app.services import storage_service
from app.services.email_service import (
    EmailSendResult,
    send_report_email,
)
from app.services.pdf_service import (
    GENERATOR_VERSION,
    PAGE_COUNT,
    ReportPayload,
    build_payload,
    render_report_pdf,
)
from app.services.recommendation_service import (
    RecommendationFailure,
    generate_recommendations,
)
from app.services.consolidation_service import ConsolidationFailure

logger = logging.getLogger(__name__)


class ReportError(RuntimeError):
    """Raised when report generation or persistence fails."""


# -----------------------------------------------------------------------------
# Permissions
# -----------------------------------------------------------------------------


def user_can_access_report(
    requester: User, report: Report, target_user: Optional[User]
) -> bool:
    """Decide whether `requester` may read/download `report`."""
    if requester is None:
        return False

    if requester.role == UserRole.SUPER_ADMIN:
        return True

    if report.user_id == requester.id:
        return True

    if requester.role in (UserRole.PSYCHOLOGIST, UserRole.SCHOOL_ADMIN):
        if requester.school_id is None:
            return False
        if target_user is None or target_user.school_id is None:
            return False
        return requester.school_id == target_user.school_id

    return False


def user_can_generate_for(requester: User, target_user: User) -> bool:
    """Decide whether `requester` may trigger a new report for `target_user`."""
    if requester.role == UserRole.SUPER_ADMIN:
        return True
    if target_user.id == requester.id:
        return True
    if requester.role in (UserRole.PSYCHOLOGIST, UserRole.SCHOOL_ADMIN):
        if requester.school_id and target_user.school_id == requester.school_id:
            return True
    return False


def user_can_send_email(
    requester: User, report: Report, target_user: Optional[User]
) -> bool:
    """Decide whether `requester` may trigger email send for `report`."""
    return user_can_access_report(requester, report, target_user)


# -----------------------------------------------------------------------------
# Generation
# -----------------------------------------------------------------------------


def _resolve_test_results(db: DBSession, user: User) -> List[VocationalTestResult]:
    return (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        .all()
    )


def _resolve_school(db: DBSession, user: User) -> Optional[School]:
    if not user.school_id:
        return None
    return db.query(School).filter(School.id == user.school_id).first()


def _resolve_school_logo_signed_url(school: Optional[School]) -> Optional[str]:
    """If `School.logo_url` is a Supabase storage path, sign it. If it's already
    a full URL, leave it alone."""
    if not school or not school.logo_url:
        return None
    url = school.logo_url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    try:
        return storage_service.get_signed_url(url, expires_in_seconds=3600)
    except Exception:
        # Logo missing / storage stub miss · fall back to raw value (template
        # will render a broken image but the rest of the PDF is fine).
        logger.warning("school logo signed url failed school_id=%s", school.id)
        return None


def _build_payload_for_user(
    db: DBSession,
    user: User,
    profile: ConsolidatedProfile,
    recommendations: List[RecommendedProgram],
) -> Tuple[ReportPayload, Optional[School]]:
    school = _resolve_school(db, user)
    school_logo_url = _resolve_school_logo_signed_url(school)
    test_results = _resolve_test_results(db, user)

    payload = build_payload(
        user=user,
        profile=profile,
        recommendations=recommendations,
        school=school,
        school_logo_url=school_logo_url,
        test_results=test_results,
    )
    return payload, school


def generate_and_store_report(
    db: DBSession,
    target_user: User,
    *,
    force_refresh_recommendations: bool = False,
) -> Tuple[Report, str, bool]:
    """End-to-end report generation.

    Returns:
        (report, signed_download_url, is_stale)

    Raises:
        ReportError on failure (wraps ConsolidationFailure / RecommendationFailure /
        rendering or storage errors).
    """
    # 1) Get profile + recommendations (uses cache by default · S6 service)
    try:
        profile, recommendations, cache_row, _cached = generate_recommendations(
            db,
            target_user,
            limit=5,
            force_refresh=force_refresh_recommendations,
        )
    except (ConsolidationFailure, RecommendationFailure) as exc:
        raise ReportError(str(exc)) from exc

    profile_hash = cache_row.profile_hash if cache_row else None

    # 2) Build payload
    payload, school = _build_payload_for_user(db, target_user, profile, recommendations)

    # 3) Render PDF
    try:
        pdf_bytes = render_report_pdf(payload)
    except Exception as exc:
        logger.exception("pdf render failed user_id=%s", target_user.id)
        raise ReportError(f"PDF render failed: {exc}") from exc

    # 4) Persist to storage · path {user_id}/reports/<uuid>.pdf
    file_uuid = uuid.uuid4()
    filename = f"{file_uuid}.pdf"
    path = storage_service.build_user_path(
        user_id=str(target_user.id), type_="reports", filename=filename
    )
    try:
        storage_obj = storage_service.upload_file(
            path=path, data=pdf_bytes, content_type="application/pdf"
        )
    except Exception as exc:
        logger.exception("storage upload failed path=%s", path)
        raise ReportError(f"Storage upload failed: {exc}") from exc

    # 5) Persist Report row
    report = Report(
        id=file_uuid,
        user_id=target_user.id,
        file_path=storage_obj.path,
        size_bytes=storage_obj.size_bytes,
        profile_hash=profile_hash,
        school_id_at_render=school.id if school else None,
        locale="es-CO",
        generator_version=GENERATOR_VERSION,
        page_count=PAGE_COUNT,
        created_at=datetime.utcnow(),
        email_sent=False,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 6) Signed URL for FE
    try:
        signed = storage_service.get_signed_url(report.file_path, expires_in_seconds=3600)
    except Exception as exc:
        logger.warning("signed url failed report_id=%s err=%s", report.id, exc)
        signed = ""

    is_stale = False  # Just generated · always fresh

    logger.info(
        "report generated report_id=%s user_id=%s size=%d profile_hash=%s",
        report.id,
        target_user.id,
        storage_obj.size_bytes,
        profile_hash,
    )
    return report, signed, is_stale


# -----------------------------------------------------------------------------
# Read
# -----------------------------------------------------------------------------


def get_signed_download_url(report: Report) -> str:
    return storage_service.get_signed_url(report.file_path, expires_in_seconds=3600)


def get_target_user(db: DBSession, report: Report) -> Optional[User]:
    return db.query(User).filter(User.id == report.user_id).first()


def is_report_stale(db: DBSession, report: Report, target_user: User) -> bool:
    """A report is stale when there is a fresher consolidated_profile cache."""
    cache = getattr(target_user, "consolidated_profile", None)
    if not cache or not cache.profile_hash:
        return False
    if not report.profile_hash:
        return True
    return cache.profile_hash != report.profile_hash


# -----------------------------------------------------------------------------
# Email
# -----------------------------------------------------------------------------


def send_report_via_email(
    db: DBSession,
    report: Report,
    requester: User,
    recipient_override: Optional[str] = None,
) -> Tuple[Report, EmailSendResult]:
    """Send the report to a recipient and persist the result on the Report row.

    Permission rules:
        - Student can only send to their own email (override is ignored if it
          differs from the user's email · log + raise).
        - Psychologist / school_admin / super_admin may pass any override.
    """
    target_user = get_target_user(db, report)
    if target_user is None:
        raise ReportError("Target user no longer exists")

    # Resolve recipient
    if recipient_override:
        if requester.role == UserRole.STUDENT and recipient_override.strip().lower() != (
            target_user.email or ""
        ).lower():
            raise ReportError(
                "Un estudiante solo puede enviar el reporte a su propio email."
            )
        recipient = recipient_override.strip()
    else:
        recipient = (target_user.email or "").strip()

    if not recipient:
        raise ReportError("Sin destinatario · el usuario no tiene email registrado.")

    # Read PDF bytes from storage
    try:
        signed = storage_service.get_signed_url(report.file_path, expires_in_seconds=3600)
    except Exception as exc:
        raise ReportError(f"Storage signed URL failed: {exc}") from exc

    pdf_bytes = _fetch_pdf_bytes(report, signed)

    school = _resolve_school(db, target_user)
    school_name = school.name if school else None

    result = send_report_email(
        to=recipient,
        student_name=target_user.name or "Estudiante",
        report_pdf_bytes=pdf_bytes,
        school_name=school_name,
    )

    # Persist · always update fields, even on failure (audit trail)
    report.email_provider = result.provider
    report.email_to = recipient
    report.email_message_id = result.message_id
    report.email_reason = result.reason
    if result.delivered:
        report.email_sent = True
        report.email_sent_at = datetime.utcnow()
    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info(
        "report email attempt report_id=%s provider=%s delivered=%s reason=%s",
        report.id,
        result.provider,
        result.delivered,
        result.reason,
    )
    return report, result


def _fetch_pdf_bytes(report: Report, signed_url: str) -> bytes:
    """Return the PDF bytes. Tries storage backend in-memory first (stub),
    falls back to HTTP fetch using the signed URL.
    """
    backend = storage_service.get_backend()
    inner = getattr(backend, "_store", None)
    if isinstance(inner, dict):  # stub backend (D-010)
        entry = inner.get(report.file_path)
        if entry:
            return entry[0]
    # Real backend · fetch via signed URL
    try:
        import httpx  # type: ignore

        with httpx.Client(timeout=10.0) as client:
            r = client.get(signed_url)
            r.raise_for_status()
            return r.content
    except Exception as exc:
        raise ReportError(f"Could not fetch PDF bytes: {exc}") from exc
