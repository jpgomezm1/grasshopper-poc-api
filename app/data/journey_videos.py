"""El estante de videos del Journey · Verónica, reunión 24-08 (19:52 y 20:03).

    "hay unas partes donde me gustaria irles poniendo como videos que yo tengo"
    "no se donde se montaria en el journey"

Y JP propuso el criterio de cuándo mostrarlos (20:03): "que haga parte del
journey, si ya tienes mucha claridad saltate los videos, si todavia
necesitas que te oriente...".

## Qué cambió el 2026-08-27

Este módulo era el estante Y el contenido: una lista `VIDEOS` en código, vacía
a propósito, que sólo se podía llenar con un despliegue. Por eso la clienta
nunca pudo cargar un video: no había dónde ponerlo.

Ahora el contenido vive en la tabla `orientation_videos` y este módulo es
sólo el **adaptador** entre esa tabla y el chat del Journey. La selección y la
regla de JP viven en `app.services.orientation_videos_service`, que es también
quien alimenta la galería `/videos` — una decisión, una función.

`JourneyVideo` se conserva como la forma que el chat espera de vuelta, para no
propagar el modelo de SQLAlchemy hasta el router.

## Dónde se monta

Cada video se ancla a un `momento` = el id de un hecho de
`app.data.journey_chat_hechos.HECHOS` — se ofrece justo DESPUÉS de que la
conversación recoge ese hecho, que es cuando tiene sentido en el hilo (por
ejemplo, un video sobre "cómo elegir entre programa y país" después de
`geoPreference`). `ruta` (opcional) lo dirige a una de las 5 rutas de la
malla completa; sin ruta, aplica a todas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DBSession


@dataclass(frozen=True)
class JourneyVideo:
    """Un video de la clienta, listo para insertarse en el chat del Journey."""

    id: str
    # id de un Hecho de `journey_chat_hechos` · después de cuál pregunta se ofrece.
    momento: str
    url: str
    duracion_segundos: int
    # De qué trata, en una frase · lo que lee el estudiante antes de darle play.
    tema: str
    # El título real del video. Antes no viajaba y el front lo fabricaba
    # ("Un video que te puede ayudar", `journeyChatApi.ts`) porque el backend
    # sólo mandaba `tema` — un texto inventado en la capa equivocada.
    titulo: str = ""
    # None = aplica a cualquiera de las 5 rutas de la malla completa.
    ruta: Optional[str] = None


def elegir_video(
    momento: str,
    recolectados: Dict[str, Any],
    ruta: Optional[str] = None,
    *,
    db: Optional[DBSession] = None,
) -> Optional[JourneyVideo]:
    """El video para este momento, o `None`.

    Devuelve `None` si no hay sesión de base de datos, si no hay ninguno
    cargado para ese momento, o si la persona ya tiene claridad alta (regla de
    JP). Las tres son el mismo resultado a propósito: el video es un
    complemento opcional y **nunca** bloquea el avance de la conversación.

    Sin `db` no se inventa nada. El chat del Journey siempre tiene sesión; que
    el parámetro sea opcional es sólo para no romper a quien llame sin ella.
    """
    if db is None:
        return None

    from app.services.orientation_videos_service import elegir_para_momento

    fila = elegir_para_momento(db, momento, recolectados, ruta)
    if fila is None:
        return None

    return JourneyVideo(
        id=str(fila.id),
        momento=fila.journey_moment or momento,
        url=fila.url,
        # El chat pinta la duración; 0 es "no la sabemos", que el front ya
        # sabe no mostrar.
        duracion_segundos=fila.duration_seconds or 0,
        tema=fila.description or fila.title,
        titulo=fila.title,
        ruta=fila.journey_route,
    )
