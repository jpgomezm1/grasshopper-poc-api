"""Magic-byte (file signature) validation for uploads.

GH-S11 hardening over S9 · prevents an attacker from renaming
``payload.exe`` to ``logo.png`` and bypassing client-side validation.

Pure stdlib implementation (no python-magic dependency). Validates the
first bytes against a small table of allowed image formats. SVG is
accepted but sanitized (no ``<script>``, no ``onerror=`` handlers, no
external entity declarations).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# (signature_bytes, mime, label)
_IMAGE_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpeg"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
    (b"RIFF", "image/webp", "webp"),  # WEBP starts RIFF....WEBP
]

# Tags / attributes that may run code or fetch external resources
_SVG_FORBIDDEN_TAG = re.compile(
    rb"<\s*(script|foreignObject|iframe|embed|object|use\s+[^>]*xlink:href\s*=\s*['\"]https?:)",
    re.IGNORECASE,
)
_SVG_EVENT_HANDLER = re.compile(rb"\son[a-z]+\s*=", re.IGNORECASE)
_SVG_EXTERNAL_ENTITY = re.compile(rb"<!ENTITY\s+[^>]*SYSTEM", re.IGNORECASE)
_SVG_JAVASCRIPT_URL = re.compile(rb"javascript\s*:", re.IGNORECASE)


@dataclass
class FileValidationResult:
    ok: bool
    detected_mime: Optional[str] = None
    detected_label: Optional[str] = None
    reason: Optional[str] = None


def validate_image_bytes(
    data: bytes,
    *,
    allow_svg: bool = True,
    max_bytes: int = 2 * 1024 * 1024,  # 2 MB
) -> FileValidationResult:
    """Validate uploaded image bytes.

    Returns ``FileValidationResult.ok=True`` when the file matches one of
    the allowed signatures and (for SVG) passes sanitization.
    """
    if not data:
        return FileValidationResult(ok=False, reason="empty")
    if len(data) > max_bytes:
        return FileValidationResult(ok=False, reason="too_large")

    # Binary signatures
    for sig, mime, label in _IMAGE_SIGNATURES:
        if data.startswith(sig):
            # WEBP requires "WEBP" at offset 8
            if label == "webp" and len(data) < 12 or (
                label == "webp" and data[8:12] != b"WEBP"
            ):
                continue
            return FileValidationResult(ok=True, detected_mime=mime, detected_label=label)

    # SVG (text-based) — allow only if requested
    head = data[:512].lstrip()
    if allow_svg and (head.startswith(b"<?xml") or head.startswith(b"<svg")):
        # First 32k is enough to spot any sane payload
        sample = data[: 32 * 1024]
        if _SVG_FORBIDDEN_TAG.search(sample):
            return FileValidationResult(ok=False, reason="svg_forbidden_tag")
        if _SVG_EVENT_HANDLER.search(sample):
            return FileValidationResult(ok=False, reason="svg_event_handler")
        if _SVG_EXTERNAL_ENTITY.search(sample):
            return FileValidationResult(ok=False, reason="svg_external_entity")
        if _SVG_JAVASCRIPT_URL.search(sample):
            return FileValidationResult(ok=False, reason="svg_javascript_url")
        return FileValidationResult(ok=True, detected_mime="image/svg+xml", detected_label="svg")

    return FileValidationResult(ok=False, reason="unknown_signature")


__all__ = ["validate_image_bytes", "FileValidationResult"]
