"""Galería de videos de orientación · reunión con Verónica del 2026-08-24.

    "hay unas partes donde me gustaria irles poniendo como videos que yo tengo"

Sólo lectura y sólo el propio estudiante, mismo patrón que `/me/electives` y
`/me/activities`. No hay endpoint de escritura a propósito: el contenido lo
carga el equipo con `scripts/cargar_videos.py` desde el archivo que produce la
clienta (decisión de AH, 2026-08-27). Cuando se quiera que ella cargue sola,
lo que falta es un panel — no otro modelo de datos.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User, UserRole
from app.schemas.videos import VideoGalleryResponse, VideoItem, VideoRow
from app.services.orientation_videos_service import construir_galeria

router = APIRouter(prefix="/me/videos", tags=["StudentMe · Videos"])


@router.get(
    "",
    response_model=VideoGalleryResponse,
    summary="Videos de orientación agrupados para este estudiante",
)
def get_my_videos(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden · student-only endpoint",
        )

    galeria = construir_galeria(db, current_user)
    return VideoGalleryResponse(
        layout=galeria.layout,
        total=galeria.total,
        filas=[
            VideoRow(
                clave=f.clave,
                titulo=f.titulo,
                videos=[
                    VideoItem(
                        id=v.id,
                        url=v.url,
                        title=v.title,
                        description=v.description,
                        thumbnail_url=v.thumbnail_url,
                        duration_seconds=v.duration_seconds,
                        topic=v.topic,
                        riasec_codes=v.riasec_codes,
                    )
                    for v in f.videos
                ],
            )
            for f in galeria.filas
        ],
    )
