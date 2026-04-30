"""Unit tests · storage_service (GH-S3-INFRA-02/03/04).

Exercises the stub backend so we can validate path conventions and basic
upload/sign/delete semantics without hitting Supabase.
"""
from __future__ import annotations

import pytest

from app.services import storage_service as svc


@pytest.fixture(autouse=True)
def _reset_backend():
    svc.reset_backend_for_tests()
    yield
    svc.reset_backend_for_tests()


def test_build_user_path_canonical():
    path = svc.build_user_path(42, "test_uploads", "mbti.pdf")
    assert path == "42/test_uploads/mbti.pdf"


def test_build_user_path_strips_dirs_in_filename():
    path = svc.build_user_path(7, "test_uploads", "../../etc/passwd")
    assert path == "7/test_uploads/passwd"


def test_build_user_path_rejects_dot_filename():
    with pytest.raises(ValueError):
        svc.build_user_path(7, "test_uploads", "..")


def test_build_user_path_rejects_bad_type():
    with pytest.raises(ValueError):
        svc.build_user_path(7, "bad/type", "x.pdf")


def test_build_school_path_namespaces():
    assert svc.build_school_path(3, "logos", "logo.png") == "school_3/logos/logo.png"


def test_upload_and_sign_roundtrip():
    path = svc.build_user_path(1, "snapshot_pdfs", "report.pdf")
    obj = svc.upload_file(path, b"hello-pdf-bytes", content_type="application/pdf")
    assert obj.path == path
    assert obj.size_bytes == len(b"hello-pdf-bytes")
    url = svc.get_signed_url(path, expires_in_seconds=120)
    assert path in url
    assert "expires_in=120" in url


def test_signed_url_rejects_bad_ttl():
    path = svc.build_user_path(1, "snapshot_pdfs", "report.pdf")
    svc.upload_file(path, b"x", content_type="application/pdf")
    with pytest.raises(ValueError):
        svc.get_signed_url(path, expires_in_seconds=10)
    with pytest.raises(ValueError):
        svc.get_signed_url(path, expires_in_seconds=60 * 60 * 24 * 30)


def test_max_size_enforced():
    payload = b"x" * (11 * 1024 * 1024)
    path = svc.build_user_path(1, "test_uploads", "huge.pdf")
    with pytest.raises(svc.StorageError):
        svc.upload_file(path, payload, content_type="application/pdf", max_size_mb=10)


def test_delete_returns_true_only_for_existing():
    path = svc.build_user_path(1, "test_uploads", "report.pdf")
    svc.upload_file(path, b"x", content_type="application/pdf")
    assert svc.delete_file(path) is True
    assert svc.delete_file(path) is False


def test_object_exists_reflects_state():
    path = svc.build_user_path(1, "test_uploads", "report.pdf")
    assert svc.object_exists(path) is False
    svc.upload_file(path, b"x", content_type="application/pdf")
    assert svc.object_exists(path) is True
