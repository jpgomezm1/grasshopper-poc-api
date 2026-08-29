"""Esquemas de la ruta de videos de orientación."""
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
    stage: Optional[str] = None
    riasec_codes: List[str] = []
    # Abierto por esta persona. Ojo con la palabra: sabemos que abrió el
    # reproductor, no que lo vio entero (ver `OrientationVideoView`).
    visto: bool = False
    # El paso sugerido ahora · sólo uno en toda la ruta.
    siguiente: bool = False
    # Encaja con sus códigos RIASEC · no reordena nada, sólo lo señala.
    recomendado: bool = False


class EtapaRuta(BaseModel):
    """Un tramo del camino · `clave` es estable para el front y las métricas."""

    clave: str
    titulo: str
    videos: List[VideoItem]
    vistos: int
    total: int


class VideoRutaResponse(BaseModel):
    """La ruta completa.

    NO trae ningún campo de bloqueo, y es deliberado: "MEMORIA SÍ, LLAVE NO"
    (migración 067). El camino muestra por dónde va la persona y sugiere el
    siguiente paso; todos los videos se pueden abrir siempre.
    """

    etapas: List[EtapaRuta]
    total: int
    vistos: int
    siguiente_id: Optional[str] = None
