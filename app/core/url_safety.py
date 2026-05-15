"""URL safety helpers · GH-F1-SECURITY.

Centraliza la validación del Origin header para construir URLs seguras que
se incluyen en emails transaccionales (invitaciones, password reset, etc.).

Sin validación, un atacante podría enviar `Origin: https://evil.com` y
el email generado apuntaría al sitio malicioso (phishing + token hijack).

Uso:
    from app.core.url_safety import build_safe_url

    reset_link = build_safe_url(
        origin_header=request.headers.get("origin"),
        path=f"/reset-password/{token}",
    )
"""
from __future__ import annotations

import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


def build_safe_url(
    origin_header: Optional[str],
    path: str,
    fallback: Optional[str] = None,
) -> str:
    """Construye una URL segura validando el Origin header contra la whitelist.

    Orden de prioridad:
      1. ``origin_header`` si está en ``settings.allowed_origins_set``
      2. ``fallback`` si se proporcionó
      3. ``settings.frontend_base_url`` (URL canónica de producción)

    Si el origin es rechazado, se logea un WARNING con el valor recibido
    para forensics (pero NO se expone al cliente ni se incluye en la URL).

    Args:
        origin_header: Valor crudo del header Origin de la request (puede ser
            None o cadena vacía).
        path: Ruta relativa a concatenar (ej. "/reset-password/abc123").
            Debe comenzar con "/".
        fallback: URL base alternativa. Si es None se usa
            ``settings.frontend_base_url``.

    Returns:
        URL absoluta segura.
    """
    settings_obj = get_settings()
    normalized = (origin_header or "").strip().rstrip("/")

    if normalized and normalized in settings_obj.allowed_origins_set:
        base = normalized
    else:
        if normalized:
            # Origen recibido pero rechazado: loggear para forensics
            logger.warning(
                "url_safety.origin_rejected "
                "origin=%r not in allowed_origins_set · using fallback",
                normalized,
            )
        base = (
            fallback
            or getattr(settings_obj, "frontend_base_url", None)
            or "http://localhost:5173"
        )

    # Garantizar un solo "/" entre base y path
    return base.rstrip("/") + "/" + path.lstrip("/")
