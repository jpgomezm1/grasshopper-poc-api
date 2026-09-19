"""Cuál de las sesiones de journey es LA sesión del estudiante.

El sistema tenía dos respuestas distintas para esta pregunta, y ninguna estaba
mal por sí sola — lo que estaba mal era que fueran dos:

    `app/api/v1/sessions.py:57`   la MÁS ANTIGUA · "si un race dejó sesiones
                                  duplicadas, TODOS los endpoints usan la más
                                  antigua (la canónica)". La cumplían ese
                                  endpoint y `hop_chat_service`.
    todos los demás               la ÚLTIMA ACTUALIZADA · `consolidation_service`,
                                  `busqueda_programas`, `crm_service`,
                                  `dossier_service`, `outreach_service`.

Con una sola sesión por persona da igual. Con duplicadas —y el propio código
dice que los races las produjeron— el perfil consolidado se construía sobre una
sesión y el chat de Mento leía otra, así que Mento podía no saber nada de lo que
la persona acababa de contar. Es la clase de desalineación que no rompe nada y
sólo se nota como "la IA no me está entendiendo".

## La regla

**La más antigua que tenga respuestas**, y si ninguna tiene, la más antigua.

La primera mitad es la regla canónica ya documentada, y es la correcta porque
`POST /sessions` hace get-or-create sobre la más antigua: es ahí donde escribe
el producto, así que es ahí donde está lo que la persona respondió.

La segunda mitad es la salvaguarda: si la más antigua quedó como cascarón vacío
—por ejemplo una sesión anónima vinculada al registrarse antes de que la persona
respondiera nada— aplicar la regla a secas le habría borrado el journey a quien
sí lo llenó en otra. Preferir la más antigua CON respuestas coincide con la
regla canónica siempre que ésta tenga datos, y coincide con el criterio viejo
(`updated_at desc`) justo cuando no los tiene. Por construcción no puede
devolver menos información que cualquiera de los dos criterios que reemplaza.

El orden es determinista en los empates (`created_at`, luego `id`) porque de
esto cuelga el hash de la caché del perfil: un desempate arbitrario regeneraría
perfiles sin que nada hubiera cambiado.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.db.models import Session as SesionJourney


def sesion_canonica(db: DBSession, user_id: UUID) -> Optional[SesionJourney]:
    """La sesión de journey que representa a este estudiante · None si no tiene."""
    sesiones = (
        db.query(SesionJourney)
        .filter(SesionJourney.user_id == user_id)
        .order_by(SesionJourney.created_at.asc(), SesionJourney.id.asc())
        .all()
    )
    if not sesiones:
        return None
    for s in sesiones:
        if s.answers:
            return s
    return sesiones[0]


def respuestas_canonicas(db: DBSession, user_id: UUID) -> Dict[str, Any]:
    """Las `answers` de la sesión canónica · `{}` si no hay sesión ni respuestas.

    Devuelve siempre un dict para que quien llama no tenga que distinguir "sin
    sesión" de "sesión vacía": para todos los consumidores de hoy es lo mismo, y
    la diferencia sólo produciría `None`s colándose en los prompts.
    """
    s = sesion_canonica(db, user_id)
    return (s.answers if s and s.answers else {}) or {}
