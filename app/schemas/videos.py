"""Esquemas de la galería de videos de orientación."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class VideoItem(BaseModel):
    id: str
    url: str
    title: str
    description: Optional[str] = None
    # NULL = el front la deriva del id de YouTube. No se pide una miniatura por
    # video para no ponerle una barrera a la clienta al cargar contenido.
    thumbnail_url: Optional[str] = None
    # NULL = no la sabemos · el front no pinta el badge en vez de poner "0:00".
    duration_seconds: Optional[int] = None
    topic: str
    riasec_codes: List[str] = []


class VideoRow(BaseModel):
    """Una fila de la galería · `clave` es estable para el front y las métricas."""

    clave: str
    titulo: str
    videos: List[VideoItem]


class VideoGalleryResponse(BaseModel):
    """`layout` lo decide el BACKEND, no el front.

    Con pocos videos las filas por tema se ven rotas (una fila de un elemento
    con su "Ver todos" al lado parece un error), así que el servicio dice
    explícitamente qué formato usar. La galería arranca en cero videos, así que
    el caso de "poco contenido" es el normal durante un buen rato.
    """

    layout: str  # "filas" | "rejilla"
    filas: List[VideoRow]
    total: int
