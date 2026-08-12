"""La foto de la hoja de vida · guardada en la propia base.

Todo el acceso a `user_photos` pasa por aquí. Es un módulo pequeño a propósito:
si algún día la foto se muda a un bucket, se reescriben estas cuatro funciones y
el resto del código no se entera.

**`obtener_bytes` es la única que trae la imagen.** Las demás preguntan por ella
sin descargarla — `tiene_foto` hace un `SELECT 1`, no un `SELECT data`. Esa
distinción es la que evita que la pantalla del CV, que sólo necesita saber si
hay foto para pintar un botón, se baje 2 MB para responder sí o no.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.db.models import UserPhoto

logger = logging.getLogger(__name__)

#: El tope también vive aquí y no sólo en el endpoint: este servicio es la
#: frontera con la tabla, y una fila de 40 MB no debería poder entrar por otro
#: camino (un script, un comando de mantenimiento) sin toparse con el límite.
MAX_BYTES = 2 * 1024 * 1024


class FotoDemasiadoGrande(ValueError):
    """La imagen supera el tope · el endpoint lo traduce a un 413."""


def tiene_foto(db: DBSession, user_id: UUID) -> bool:
    """¿Hay foto? · sin traerse la imagen.

    `select(1)` en vez de cargar la fila entera: quien pregunta esto está
    pintando un botón, no generando un PDF.
    """
    return db.execute(
        select(1).select_from(UserPhoto).where(UserPhoto.user_id == user_id)
    ).first() is not None


def obtener_bytes(db: DBSession, user_id: UUID) -> Optional[Tuple[bytes, str]]:
    """Los bytes de la foto y su content-type · None si no hay."""
    fila = db.query(UserPhoto).filter(UserPhoto.user_id == user_id).first()
    if fila is None or not fila.data:
        return None
    return bytes(fila.data), fila.content_type or "image/jpeg"


def obtener_data_uri(db: DBSession, user_id: UUID) -> Optional[str]:
    """La foto como `data:image/...;base64,...`, lista para incrustar.

    El PDF y el Word la meten dentro del documento en vez de referenciar una
    URL: así el archivo que descarga el estudiante es autocontenido y no depende
    de que un enlace siga vivo cuando lo abra quien lo reciba.

    Cualquier fallo devuelve None a propósito · una foto ilegible no puede
    dejar a nadie sin hoja de vida.
    """
    try:
        encontrado = obtener_bytes(db, user_id)
        if not encontrado:
            return None
        datos, content_type = encontrado
        return f"data:{content_type};base64,{base64.b64encode(datos).decode('ascii')}"
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo leer la foto del CV user_id=%s", user_id)
        return None


def guardar(db: DBSession, user_id: UUID, datos: bytes, content_type: str) -> None:
    """Guarda o reemplaza la foto · un UPDATE, no filas acumuladas.

    No hace `commit`: lo deja en manos de quien llama, para que subir la foto y
    lo que venga después sean una sola transacción.
    """
    if len(datos) > MAX_BYTES:
        raise FotoDemasiadoGrande(
            f"La foto pesa más de {MAX_BYTES // (1024 * 1024)} MB."
        )

    fila = db.query(UserPhoto).filter(UserPhoto.user_id == user_id).first()
    if fila is None:
        fila = UserPhoto(user_id=user_id)
        db.add(fila)

    fila.data = datos
    fila.content_type = content_type
    fila.size_bytes = len(datos)
    fila.updated_at = datetime.utcnow()


def borrar(db: DBSession, user_id: UUID) -> bool:
    """Quita la foto · devuelve si había alguna. Tampoco hace commit."""
    fila = db.query(UserPhoto).filter(UserPhoto.user_id == user_id).first()
    if fila is None:
        return False
    db.delete(fila)
    return True
