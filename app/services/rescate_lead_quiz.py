"""El quiz de la landing deja de caer en un pozo.

`lead_profiles` se escribe desde `api/v1/lead_profile.py:70` y **ningún otro
sitio del backend la consulta**. El propio `models.py` lo confiesa, en el
docstring de la tabla de al lado:

    "la diferencia con esa tabla es que aquí SÍ hay quien lea —
     `lead_profiles` se escribe […] y ningún otro sitio del backend la
     consulta, así que los leads del quiz llevan meses cayendo en un pozo."

Y lo que se pierde no es poco. El quiz hace seis preguntas de verdad —qué te
emociona, qué haces en tu tiempo libre, cómo trabajas— y calcula un arquetipo
vocacional ("El Analista Metódico", "El Conector Social"). Es la **primera**
señal vocacional que la persona da, muchas veces semanas antes de registrarse.

## Qué hace este módulo

Cuando alguien se registra con el mismo correo con el que hizo el quiz, sus
respuestas se recuperan y entran a `onboarding_answers`, que es el bolsillo que
ya leen el perfil consolidado, el chat de Mento y las rutas del journey. Y
`converted` por fin significa algo.

## Los dos extremos, en el mismo commit

Escribir el campo sin conectarlo al consumidor es el defecto #1 de este repo, y
es precisamente cómo el quiz llegó a este estado. Por eso la clave que se
escribe aquí —`quiz_arquetipo`— se renderiza en
`ai_service.format_onboarding_context` en este mismo cambio, y hay un test que
falla si alguien desconecta cualquiera de las dos puntas.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DBSession

logger = logging.getLogger(__name__)

#: Dónde queda lo rescatado dentro de `onboarding_answers`.
CLAVE_ARQUETIPO = "quiz_arquetipo"
CLAVE_RASGOS = "quiz_rasgos"


def _texto_del_resultado(resultado: Dict[str, Any]) -> Optional[str]:
    """El arquetipo en una frase · None si la fila no trae nada aprovechable."""
    nombre = str(resultado.get("profile_name") or "").strip()
    descripcion = str(resultado.get("description") or "").strip()
    if not nombre:
        return None
    return f"{nombre} — {descripcion}" if descripcion else nombre


def rescatar(db: DBSession, user) -> bool:
    """Trae el quiz que esta persona hizo antes de tener cuenta.

    Devuelve True si se rescató algo. **Nunca lanza**: alguien que se acaba de
    registrar no puede quedarse sin cuenta porque su quiz viejo estuviera raro.

    No pisa nada: si la persona ya respondió el onboarding, lo suyo manda. El
    quiz es una señal anterior y más pobre —seis preguntas de opción múltiple—
    que sólo sirve para llenar huecos, no para sobrescribir lo que contó después
    con sus palabras.
    """
    from app.db.models import LeadProfile

    try:
        correo = (getattr(user, "email", "") or "").strip().lower()
        if not correo:
            return False

        lead = (
            db.query(LeadProfile)
            .filter(LeadProfile.email.ilike(correo))
            .order_by(LeadProfile.created_at.desc())
            .first()
        )
        if lead is None:
            return False

        resultado = lead.profile_result if isinstance(lead.profile_result, dict) else {}
        texto = _texto_del_resultado(resultado)
        rasgos = [str(t).strip() for t in (resultado.get("traits") or []) if str(t).strip()]

        actuales = dict(user.onboarding_answers or {})
        cambio = False
        if texto and not actuales.get(CLAVE_ARQUETIPO):
            actuales[CLAVE_ARQUETIPO] = texto
            cambio = True
        if rasgos and not actuales.get(CLAVE_RASGOS):
            actuales[CLAVE_RASGOS] = rasgos
            cambio = True

        # `converted` existía desde el principio y nadie lo ponía en True, igual
        # que nadie leía la tabla. Se marca aunque no haya nada que copiar: la
        # persona SÍ se convirtió, y eso es lo que el campo dice.
        if not lead.converted:
            lead.converted = True
            cambio = True

        if cambio:
            user.onboarding_answers = actuales
            db.commit()
            logger.info(
                "Quiz de la landing rescatado al registrarse",
                extra={"user_id": str(user.id), "tenia_arquetipo": bool(texto)},
            )
        return cambio
    except Exception:  # pragma: no cover · defensivo
        logger.warning("no se pudo rescatar el quiz de la landing", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return False
