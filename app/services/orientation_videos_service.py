"""La galería de videos de orientación · qué se le muestra a cada estudiante.

Reunión con Verónica del 2026-08-24: *"hay unas partes donde me gustaria irles
poniendo como videos que yo tengo"*.

## Qué decide este módulo

Sólo cómo se AGRUPA lo que ya está en la tabla. No inventa relevancia, no
rellena huecos y no ordena por criterios que no podamos explicar.

Dos reglas que parecen detalles y no lo son:

**1. "Para ti" sólo existe si se puede sostener.**
Necesita que el estudiante tenga resultados RIASEC *y* que haya videos
etiquetados con sus códigos. Si falta cualquiera de las dos, la fila no
aparece — en vez de aparecer vacía o, peor, llena de videos cualesquiera
bajo un rótulo que promete personalización. Hoy casi ningún estudiante tiene
tests hechos, así que el caso normal es que no salga.

**2. Con poco contenido, filas no.**
El formato de filas por tema (estilo Netflix) escala bien con muchos videos y
se ve roto con pocos: una fila con un solo elemento y un "Ver todos" al lado
parece un error. La galería arranca en CERO videos y se va llenando, así que
el servicio dice explícitamente al front qué formato usar (`layout`) en vez
de dejar que lo adivine. Ver `LAYOUT_MINIMO_PARA_FILAS`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.db.models import OrientationVideo, User, VocationalTestResult
from app.services.psychometrics_service import holland_top_codes

logger = logging.getLogger(__name__)

# Menos de esto en una fila y la fila no se pinta como fila.
MINIMO_POR_FILA = 3
# Y si en total no hay ni para dos filas decentes, la galería entera cae a
# rejilla simple: ver el docstring, regla 2.
LAYOUT_MINIMO_PARA_FILAS = 6

TITULO_PARA_TI = "Para ti"

# La frase exacta de la opción del onboarding · si cambia allá, cambia aquí.
# Se mantiene el literal (y no una constante importada) porque así venía de
# `journey_videos.py`; moverlo a un enum es un cambio aparte.
_CLARIDAD_ALTA = "Tengo algo claro y quiero validarlo"


@dataclass
class VideoOut:
    id: str
    url: str
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    duration_seconds: Optional[int]
    topic: str
    riasec_codes: List[str] = field(default_factory=list)


@dataclass
class FilaOut:
    """Una fila de la galería · `clave` es estable para el front y las métricas."""

    clave: str
    titulo: str
    videos: List[VideoOut]


@dataclass
class GaleriaOut:
    # "filas" | "rejilla" · lo decide el backend, no el front (ver regla 2).
    layout: str
    filas: List[FilaOut]
    total: int


def _a_out(v: OrientationVideo) -> VideoOut:
    codes = v.riasec_codes if isinstance(v.riasec_codes, list) else []
    return VideoOut(
        id=str(v.id),
        url=v.url,
        title=v.title,
        description=v.description,
        thumbnail_url=v.thumbnail_url,
        duration_seconds=v.duration_seconds,
        topic=v.topic,
        riasec_codes=[str(c) for c in codes],
    )


def codigos_riasec_del_estudiante(db: DBSession, user: User) -> List[str]:
    """Las dos letras RIASEC dominantes del estudiante · vacío si no tiene test.

    Se lee del resultado más reciente. La tolerancia a las formas heterogéneas
    de `scores` vive en `psychometrics_service.holland_top_codes`, no aquí.
    """
    fila = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        # Los ids reales de `app/data/vocational_tests.py`. No existe ningun
        # test con id "riasec": el modelo RIASEC lo implementan `holland` y
        # `istrong` (este ultimo "inspirado en Holland", ver su academicBasis).
        .filter(VocationalTestResult.test_id.in_(("holland", "istrong")))
        .order_by(VocationalTestResult.created_at.desc())
        .first()
    )
    if not fila:
        return []
    try:
        return holland_top_codes(fila.scores or {}, n=2)
    except Exception:  # pragma: no cover · defensivo
        logger.exception("videos · no se pudieron leer los codigos RIASEC")
        return []


def _publicados(db: DBSession) -> List[OrientationVideo]:
    return (
        db.query(OrientationVideo)
        .filter(OrientationVideo.is_published.is_(True))
        .order_by(
            OrientationVideo.topic.asc(),
            OrientationVideo.sort_order.asc(),
            OrientationVideo.created_at.asc(),
        )
        .all()
    )


def construir_galeria(db: DBSession, user: User) -> GaleriaOut:
    """La galería completa para este estudiante."""
    videos = _publicados(db)
    if not videos:
        return GaleriaOut(layout="rejilla", filas=[], total=0)

    codigos = codigos_riasec_del_estudiante(db, user)

    # --- "Para ti" ---------------------------------------------------------
    # Se arma sólo si hay códigos Y hay videos etiquetados con ellos. Sin las
    # dos cosas, el rótulo prometería una personalización que no existe.
    para_ti: List[OrientationVideo] = []
    if codigos:
        conjunto = set(codigos)
        para_ti = [
            v
            for v in videos
            if isinstance(v.riasec_codes, list) and conjunto & {str(c) for c in v.riasec_codes}
        ]

    filas: List[FilaOut] = []
    if len(para_ti) >= MINIMO_POR_FILA:
        filas.append(
            FilaOut(clave="para-ti", titulo=TITULO_PARA_TI, videos=[_a_out(v) for v in para_ti])
        )

    # --- las filas por tema ------------------------------------------------
    por_tema: Dict[str, List[OrientationVideo]] = {}
    for v in videos:
        por_tema.setdefault(v.topic, []).append(v)

    # Un tema con menos de `MINIMO_POR_FILA` no merece fila propia: se junta
    # en "Otros temas" para que no queden filas de un solo elemento.
    sueltos: List[OrientationVideo] = []
    for tema in sorted(por_tema):
        grupo = por_tema[tema]
        if len(grupo) >= MINIMO_POR_FILA:
            filas.append(
                FilaOut(clave=f"tema:{tema}", titulo=tema, videos=[_a_out(v) for v in grupo])
            )
        else:
            sueltos.extend(grupo)

    if sueltos:
        filas.append(
            FilaOut(clave="otros", titulo="Otros temas", videos=[_a_out(v) for v in sueltos])
        )

    # --- el formato --------------------------------------------------------
    # Con poco contenido las filas se ven rotas · ver regla 2 del docstring.
    layout = "filas" if len(videos) >= LAYOUT_MINIMO_PARA_FILAS else "rejilla"
    if layout == "rejilla":
        # En rejilla no hay filas que mostrar: va todo junto, en una sola.
        filas = [
            FilaOut(clave="todos", titulo="Videos", videos=[_a_out(v) for v in videos])
        ]

    return GaleriaOut(layout=layout, filas=filas, total=len(videos))


def elegir_para_momento(
    db: DBSession,
    momento: str,
    recolectados: Dict[str, Any],
    ruta: Optional[str] = None,
) -> Optional[OrientationVideo]:
    """El video que se ofrece dentro del chat del Journey tras recoger `momento`.

    La regla de cuándo NO ofrecer es de JP (reunión del 24-08, 20:03): *"si ya
    tienes mucha claridad saltate los videos"*. Vive aquí, junto a la consulta,
    porque el criterio y la selección son la misma decisión.

    Antes esto leía una lista de Python vacía en `app/data/journey_videos.py`;
    ahora lee la tabla, que es lo que permite que la clienta cargue contenido
    sin un despliegue.
    """
    if recolectados.get("clarityLevel") == _CLARIDAD_ALTA:
        return None

    candidatos = (
        db.query(OrientationVideo)
        .filter(OrientationVideo.is_published.is_(True))
        .filter(OrientationVideo.journey_moment == momento)
        .order_by(OrientationVideo.sort_order.asc(), OrientationVideo.created_at.asc())
        .all()
    )
    if not candidatos:
        return None

    # El específico de la ruta gana sobre el genérico si ambos existen.
    if ruta is not None:
        especificos = [v for v in candidatos if v.journey_route == ruta]
        if especificos:
            return especificos[0]
    genericos = [v for v in candidatos if v.journey_route is None]
    return genericos[0] if genericos else None

