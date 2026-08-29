"""Ruta de videos de orientación · reunión con Verónica del 2026-08-24.

    "hay unas partes donde me gustaria irles poniendo como videos que yo tengo"

Y AH el 2026-08-29: *"quiero que esto se vea como una ruta de aprendizaje, o
sea como una visual de roadmap e ir desbloqueando los videos"*.

## Lo del desbloqueo, y por qué no hay bloqueo

No hay ningún campo `bloqueado` ni endpoint que lo compruebe. La ruta muestra
por dónde va la persona y sugiere el siguiente paso, pero todos los videos se
pueden abrir. Es "MEMORIA SÍ, LLAVE NO" —decisión de producto de la migración
067, ya aplicada en seis sitios del backend— y AH la confirmó al verla
planteada.

Si algún día se decide bloquear de verdad, es un cambio de producto que hay
que hablar con la clienta, no un `if` que se añade aquí.

## Sólo el propio estudiante

Mismo patrón que `/me/electives` y `/me/activities`. El contenido lo carga el
equipo con `scripts/cargar_videos.py`; no hay endpoint de escritura de videos.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import OrientationVideo, User, UserRole
from app.schemas.videos import EtapaRuta, VideoItem, VideoRutaResponse
from app.services.orientation_videos_service import construir_ruta, marcar_abierto

router = APIRouter(prefix="/me/videos", tags=["StudentMe · Videos"])


def _solo_estudiante(user: User) -> None:
    if user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )


@router.get(
    "",
    response_model=VideoRutaResponse,
    summary="La ruta de videos de este estudiante · con lo que ya abrió",
)
def get_mi_ruta(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiante(current_user)

    ruta = construir_ruta(db, current_user)
    return VideoRutaResponse(
        total=ruta.total,
        vistos=ruta.vistos,
        siguiente_id=ruta.siguiente_id,
        etapas=[
            EtapaRuta(
                clave=e.clave,
                titulo=e.titulo,
                vistos=e.vistos,
                total=e.total,
                videos=[
                    VideoItem(
                        id=v.id,
                        url=v.url,
                        title=v.title,
                        description=v.description,
                        thumbnail_url=v.thumbnail_url,
                        duration_seconds=v.duration_seconds,
                        topic=v.topic,
                        stage=v.stage,
                        riasec_codes=v.riasec_codes,
                        visto=v.visto,
                        siguiente=v.siguiente,
                        recomendado=v.recomendado,
                    )
                    for v in e.videos
                ],
            )
            for e in ruta.etapas
        ],
    )


@router.post(
    "/{video_id}/visto",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marca que el estudiante abrió este video",
)
def marcar_visto(
    # Tipado como UUID y no `str`: la columna lo es, y sin la conversion
    # SQLAlchemy revienta con "'str' object has no attribute 'hex'". De paso,
    # un id con formato invalido se rechaza con 422 antes de tocar la base.
    video_id: UUID,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _solo_estudiante(current_user)

    # Se comprueba que el video exista y esté publicado antes de escribir: sin
    # esto, un id inventado dejaría filas apuntando a nada y el porcentaje de
    # avance podría pasar del 100%.
    existe = (
        db.query(OrientationVideo)
        .filter(OrientationVideo.id == video_id)
        .filter(OrientationVideo.is_published.is_(True))
        .first()
    )
    if not existe:
        raise HTTPException(status_code=404, detail="video no encontrado")

    marcar_abierto(db, current_user, video_id)
    return None
