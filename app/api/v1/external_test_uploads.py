"""External test uploads · Sprint 5 endpoints.

GH-S5-BE-01 · GH-S5-BE-05 · GH-S5-BE-06 · GH-S5-BE-07 · GH-S5-BE-08

Routes:
    POST   /external-test-uploads                · multipart upload
    GET    /external-test-uploads                · list current user's uploads
    GET    /external-test-uploads/{id}           · single upload + parsed_data
    POST   /external-test-uploads/{id}/parse     · trigger / re-trigger parsing (background)
    POST   /external-test-uploads/{id}/retry     · alias of /parse for FE clarity
    POST   /external-test-uploads/{id}/confirm   · promote parsed_data → VocationalTestResult
    POST   /external-test-uploads/{id}/discard   · soft-discard the upload
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.core.rate_limiter import limiter
from app.db.database import get_db, SessionLocal


def _rate_limit_external_upload(request: Request):
    """GH-S11-INFRA-04 · per-user rate limit for upload endpoint."""
    from app.core.rate_limiter import rate_limit
    s = get_settings()
    return rate_limit(s.rate_limit_external_test_upload)(request)
from app.db.models import ExternalTestUpload, User, VocationalTestResult
from app.schemas.external_tests import (
    ConfirmRequest,
    UploadDetail,
    UploadResponse,
)
from app.services import storage_service
from app.services.external_test_parser import parse_external_test

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/external-test-uploads", tags=["External Test Uploads"])

ALLOWED_TEST_TYPES = {"mbti", "istrong", "big5", "riasec"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/heic",
    "image/heif",
}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _serialize(upload: ExternalTestUpload) -> dict:
    return {
        "id": upload.id,
        "user_id": upload.user_id,
        "test_type": upload.test_type,
        "parsing_status": upload.parsing_status,
        "file_path": upload.file_path,
        "original_filename": upload.original_filename,
        "size_bytes": upload.size_bytes,
        "uploaded_at": upload.uploaded_at,
    }


def _serialize_detail(upload: ExternalTestUpload) -> dict:
    base = _serialize(upload)
    base.update(
        {
            "parsed_data": upload.parsed_data,
            "confidence_score": upload.confidence_score,
            "parser_version": upload.parser_version,
            "error_message": upload.error_message,
            "parsed_at": upload.parsed_at,
        }
    )
    return base


def _ensure_owner(upload: ExternalTestUpload, user: User) -> None:
    if upload.user_id != user.id and user.role != "super_admin":
        raise HTTPException(status_code=404, detail="Upload not found")


# -----------------------------------------------------------------------------
# Background task · isolated DB session
# -----------------------------------------------------------------------------

def _run_parse_task(upload_id: str) -> None:
    """Background runner · re-fetches the upload, calls parser, persists result.

    Uses its own SessionLocal because BackgroundTask runs after the request
    DB session is closed.
    """
    db = SessionLocal()
    try:
        upload = db.query(ExternalTestUpload).filter(
            ExternalTestUpload.id == upload_id
        ).first()
        if not upload:
            logger.warning("parse_task · upload not found id=%s", upload_id)
            return

        upload.parsing_status = "processing"
        db.commit()

        # Pull bytes from storage (signed URL → http GET)
        # In dev (stub backend) we fetch from the in-memory store via a custom
        # helper. To avoid the extra round trip we read directly from the
        # backend.
        backend = storage_service.get_backend()

        # Stub backend exposes ._store; for production backend we need to GET
        # the signed URL. Both supported.
        file_bytes: Optional[bytes] = None
        if hasattr(backend, "_store"):
            entry = backend._store.get(upload.file_path)  # type: ignore[attr-defined]
            if entry:
                file_bytes = entry[0]
        else:
            try:
                signed = storage_service.get_signed_url(upload.file_path, expires_in_seconds=300)
                import httpx
                with httpx.Client(timeout=30.0) as client:
                    r = client.get(signed)
                    r.raise_for_status()
                    file_bytes = r.content
            except Exception as exc:  # pragma: no cover - prod-only path
                upload.parsing_status = "failed"
                upload.error_message = f"could not fetch file from storage: {exc}"
                upload.parsed_at = datetime.utcnow()
                db.commit()
                return

        if not file_bytes:
            upload.parsing_status = "failed"
            upload.error_message = "file not found in storage"
            upload.parsed_at = datetime.utcnow()
            db.commit()
            return

        outcome = parse_external_test(
            test_type=upload.test_type,  # type: ignore[arg-type]
            file_bytes=file_bytes,
            content_type=upload.content_type,
            filename=upload.original_filename,
        )

        upload.raw_text = outcome.raw_text or None
        upload.parsing_status = outcome.parsing_status
        upload.error_message = outcome.error_message
        upload.parsed_at = datetime.utcnow()

        if outcome.result is not None:
            upload.parsed_data = outcome.result.model_dump(mode="json")
            upload.confidence_score = float(outcome.result.confidence)
            upload.parser_version = outcome.result.parser_version

        db.commit()
        logger.info(
            "parse_task complete id=%s status=%s",
            upload_id,
            upload.parsing_status,
        )
    except Exception as exc:
        logger.exception("parse_task crashed id=%s err=%s", upload_id, exc)
        try:
            db.rollback()
            upload = db.query(ExternalTestUpload).filter(
                ExternalTestUpload.id == upload_id
            ).first()
            if upload:
                upload.parsing_status = "failed"
                upload.error_message = f"parser crashed: {exc}"
                upload.parsed_at = datetime.utcnow()
                db.commit()
        except Exception:
            # No re-lanzamos (background task), pero sin log el upload
            # quedaba colgado en "processing" sin rastro.
            logger.exception(
                "parse_task: no se pudo marcar el upload como failed id=%s",
                upload_id,
            )
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_rate_limit_external_upload)],
)
async def upload_test_result(
    background_tasks: BackgroundTasks,
    test_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Multipart upload of a vocational test result PDF/image.

    Validates type, size, format · persists in storage · creates DB row ·
    schedules background parsing.

    GH-S11-INFRA-04 · rate-limited (default 10/hour per user).
    """
    test_type = test_type.lower().strip()
    if test_type not in ALLOWED_TEST_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"test_type must be one of {sorted(ALLOWED_TEST_TYPES)}",
        )

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported content_type {content_type!r}",
        )

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="empty file")
    if len(body) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {MAX_SIZE_BYTES // (1024*1024)}MB limit",
        )

    # Build storage path · {user_id}/test_uploads/{uuid}-{filename}
    upload_id = uuid.uuid4()
    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_")
    storage_filename = f"{upload_id}-{safe_name}"
    storage_path = storage_service.build_user_path(
        user_id=str(current_user.id),
        type_="test_uploads",
        filename=storage_filename,
    )

    try:
        storage_service.upload_file(
            path=storage_path,
            data=body,
            content_type=content_type,
            max_size_mb=MAX_SIZE_BYTES // (1024 * 1024),
        )
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=500, detail=f"storage failed: {exc}")

    record = ExternalTestUpload(
        id=upload_id,
        user_id=current_user.id,
        test_type=test_type,
        file_path=storage_path,
        original_filename=file.filename,
        content_type=content_type,
        size_bytes=len(body),
        parsing_status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Schedule parsing
    background_tasks.add_task(_run_parse_task, str(record.id))

    return _serialize(record)


@router.get("")
def list_uploads(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    rows = (
        db.query(ExternalTestUpload)
        .filter(ExternalTestUpload.user_id == current_user.id)
        .order_by(ExternalTestUpload.uploaded_at.desc())
        .all()
    )
    return [_serialize_detail(r) for r in rows]


@router.get("/{upload_id}")
def get_upload(
    upload_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    upload = db.query(ExternalTestUpload).filter(
        ExternalTestUpload.id == upload_id
    ).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    _ensure_owner(upload, current_user)
    return _serialize_detail(upload)


@router.post("/{upload_id}/parse")
def trigger_parse(
    upload_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    upload = db.query(ExternalTestUpload).filter(
        ExternalTestUpload.id == upload_id
    ).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    _ensure_owner(upload, current_user)

    if upload.parsing_status == "processing":
        raise HTTPException(status_code=409, detail="already processing")

    upload.parsing_status = "pending"
    upload.error_message = None
    db.commit()

    background_tasks.add_task(_run_parse_task, str(upload.id))
    return _serialize_detail(upload)


@router.post("/{upload_id}/retry")
def retry_parse(
    upload_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Alias of /parse · used by FE on user-triggered retry from needs_review state."""
    return trigger_parse(upload_id, background_tasks, current_user, db)


@router.post("/{upload_id}/confirm")
def confirm_upload(
    upload_id: uuid.UUID,
    request: ConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Promote a parsed (or user-edited) upload to a VocationalTestResult.

    If `request.payload` is present, it overrides the IA-generated parsed_data.
    Idempotent: if a VocationalTestResult already exists for this user+test it
    is updated (UniqueConstraint on user_id+test_id).
    """
    # M-006 · este endpoint también crea un VocationalTestResult → aplica el
    # mismo gate que /vocational-tests/submit (menor de 16 sin consentimiento).
    from app.services import parental_consent_service
    if parental_consent_service.needs_parental_consent(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="minor_parental_consent_required",
        )

    upload = db.query(ExternalTestUpload).filter(
        ExternalTestUpload.id == upload_id
    ).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    _ensure_owner(upload, current_user)

    if upload.parsing_status not in {"done", "needs_review"}:
        raise HTTPException(
            status_code=409,
            detail=f"upload not ready · status={upload.parsing_status}",
        )

    final_payload = request.payload or upload.parsed_data
    if not final_payload:
        raise HTTPException(status_code=400, detail="no parsed data to confirm")

    # If user edited, persist back into upload for traceability
    if request.payload is not None:
        upload.parsed_data = final_payload

    # Map upload.test_type → vocational test_id used in vocational_test_results
    # The platform uses canonical test_id strings consistent with app.data.vocational_tests
    # (see Sprint 4: 'mbti', 'istrong', 'big5_internal' / 'riasec'). For external
    # uploads we keep the same test_id namespace · the consolidated profile in
    # Sprint 6 will read from `vocational_test_results` regardless of source.
    test_id = upload.test_type  # 1:1 mapping by convention

    existing = (
        db.query(VocationalTestResult)
        .filter(
            VocationalTestResult.user_id == current_user.id,
            VocationalTestResult.test_id == test_id,
        )
        .first()
    )

    if existing:
        existing.scores = final_payload.get("payload", final_payload)
        existing.answers = {"_external_upload_id": str(upload.id)}
        existing.source = "external_upload"
        existing.external_upload_id = upload.id
    else:
        vtr = VocationalTestResult(
            user_id=current_user.id,
            test_id=test_id,
            answers={"_external_upload_id": str(upload.id)},
            scores=final_payload.get("payload", final_payload),
            source="external_upload",
            external_upload_id=upload.id,
        )
        db.add(vtr)

    upload.parsing_status = "done"  # confirmed by user
    db.commit()
    db.refresh(upload)

    # GH-S6 · invalidate consolidated profile cache so a new external
    # test result triggers regeneration on next /recommendations/me call.
    try:
        from app.services.consolidation_service import invalidate_cache
        invalidate_cache(db, current_user.id)
    except Exception:
        # La confirmación ya está persistida; si falla la invalidación el
        # perfil consolidado puede quedar stale → al menos dejamos señal.
        logger.warning(
            "confirm_upload: fallo invalidate_cache user_id=%s upload_id=%s",
            current_user.id,
            upload.id,
            exc_info=True,
        )

    return _serialize_detail(upload)


@router.post("/{upload_id}/discard")
def discard_upload(
    upload_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Discard an upload · removes file from storage and DB row.

    Returns 204 No Content on success.
    """
    upload = db.query(ExternalTestUpload).filter(
        ExternalTestUpload.id == upload_id
    ).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    _ensure_owner(upload, current_user)

    try:
        storage_service.delete_file(upload.file_path)
    except Exception as exc:
        logger.warning("storage delete failed during discard id=%s err=%s", upload_id, exc)

    db.delete(upload)
    db.commit()
    return {"deleted": True, "id": str(upload_id)}
