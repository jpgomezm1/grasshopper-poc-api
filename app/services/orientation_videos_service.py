"""La ruta de videos de orientación · qué se le muestra a cada estudiante.

Reunión con Verónica del 2026-08-24: *"hay unas partes donde me gustaria irles
poniendo como videos que yo tengo"*. Y AH el 2026-08-29: *"quiero que esto se
vea como una ruta de aprendizaje, o sea como una visual de roadmap"*.

## Es una ruta, y no cierra puertas

Devuelve las etapas en orden, con lo que la persona ya abrió marcado y un
puntero al siguiente paso. Lo que NO hace es bloquear: todos los videos se
pueden abrir siempre.

Es "MEMORIA SÍ, LLAVE NO" (decisión de producto de la migración 067, aplicada
ya en seis sitios del backend), y en orientación vocacional el bloqueo tiene
además un costo concreto: alguien con curiosidad por enfermería no debería
tener que ver tres videos antes de llegar al que le importa.

El gris de un paso todavía no recorrido dice "todavía no", no "no puedes".

## Dos ejes, no uno

`stage` es la ETAPA del camino y tiene un antes y un después. `topic` son
ÁREAS (Salud, Ingeniería, Arte) y son paralelas. Se conservan los dos porque
sirven para cosas distintas; la ruta se arma por `stage`.

## Lo que este módulo no decide

No inventa relevancia ni rellena huecos. Si una etapa no tiene videos, no
aparece. Y `recomendado` sólo se marca cuando la persona TIENE códigos RIASEC
y el video está etiquetado con alguno: sin las dos cosas no hay marca, en vez
de una insignia que prometa una personalización que no existe. Hoy casi nadie
tiene tests hechos, así que el caso normal es que no aparezca.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.db.models import (
    OrientationVideo,
    OrientationVideoView,
    User,
    VocationalTestResult,
)
from app.services.psychometrics_service import holland_top_codes

logger = logging.getLogger(__name__)

# Los videos que la clienta todavía no clasificó en ninguna etapa caen aquí, al
# final. Es visible a propósito: un video sin etapa es contenido que alguien
# tiene que colocar, no un error que haya que esconder.
ETAPA_SIN_CLASIFICAR = "Otros videos"

# La frase exacta de la opción del onboarding · si cambia allá, cambia aquí.
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
    stage: Optional[str] = None
    riasec_codes: List[str] = field(default_factory=list)
    # Abierto por esta persona · ver `OrientationVideoView`: sabemos que abrió
    # el reproductor, no que lo vio entero.
    visto: bool = False
    # Es el que se le sugiere ahora · sólo uno en toda la ruta.
    siguiente: bool = False
    # Encaja con los códigos RIASEC de esta persona. NO reordena la ruta —el
    # orden lo pone la clienta— sólo lo señala donde está.
    recomendado: bool = False


@dataclass
class EtapaOut:
    clave: str
    titulo: str
    videos: List[VideoOut]
    vistos: int
    total: int


@dataclass
class RutaOut:
    etapas: List[EtapaOut]
    total: int
    vistos: int
    # Id del video sugerido · None si ya los abrió todos o no hay ninguno.
    siguiente_id: Optional[str]


def _publicados(db: DBSession) -> List[OrientationVideo]:
    """En orden de recorrido · etapa, luego orden dentro de la etapa.

    `stage` NULL ordena al final en Postgres con `nulls_last`, que es justo
    donde queremos los sin clasificar.
    """
    return (
        db.query(OrientationVideo)
        .filter(OrientationVideo.is_published.is_(True))
        .order_by(
            OrientationVideo.stage.asc().nullslast(),
            OrientationVideo.sort_order.asc(),
            OrientationVideo.created_at.asc(),
        )
        .all()
    )


def _ids_vistos(db: DBSession, user: User) -> set:
    filas = (
        db.query(OrientationVideoView.video_id)
        .filter(OrientationVideoView.user_id == user.id)
        .all()
    )
    return {str(f[0]) for f in filas}


def codigos_riasec_del_estudiante(db: DBSession, user: User) -> List[str]:
    """Las dos letras RIASEC dominantes · vacío si no tiene test.

    La tolerancia a las formas heterogéneas de `scores` vive en
    `psychometrics_service.holland_top_codes`, no aquí.
    """
    fila = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user.id)
        # Los ids reales de `app/data/vocational_tests.py`. No existe ningún
        # test con id "riasec": el modelo lo implementan `holland` e `istrong`.
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


def _a_out(v: OrientationVideo, visto: bool) -> VideoOut:
    codes = v.riasec_codes if isinstance(v.riasec_codes, list) else []
    return VideoOut(
        id=str(v.id),
        url=v.url,
        title=v.title,
        description=v.description,
        thumbnail_url=v.thumbnail_url,
        duration_seconds=v.duration_seconds,
        topic=v.topic,
        stage=v.stage,
        riasec_codes=[str(c) for c in codes],
        visto=visto,
    )


def construir_ruta(db: DBSession, user: User) -> RutaOut:
    """La ruta completa para este estudiante."""
    videos = _publicados(db)
    if not videos:
        return RutaOut(etapas=[], total=0, vistos=0, siguiente_id=None)

    vistos = _ids_vistos(db, user)
    codigos = set(codigos_riasec_del_estudiante(db, user))

    salidas = []
    for v in videos:
        out = _a_out(v, str(v.id) in vistos)
        # Sólo si hay códigos Y el video está etiquetado. Sin las dos cosas la
        # insignia prometería una personalización que no existe.
        if codigos and out.riasec_codes:
            out.recomendado = bool(codigos & set(out.riasec_codes))
        salidas.append(out)

    # El siguiente paso es el PRIMERO sin abrir en el orden del camino. Si ya
    # los abrió todos, no hay siguiente y la ruta se muestra completa — no se
    # inventa un "vuelve a ver el primero".
    siguiente = next((s for s in salidas if not s.visto), None)
    if siguiente is not None:
        siguiente.siguiente = True

    # --- agrupar por etapa, conservando el orden -----------------------------
    etapas: List[EtapaOut] = []
    for s in salidas:
        titulo = s.stage or ETAPA_SIN_CLASIFICAR
        clave = f"etapa:{titulo}"
        if not etapas or etapas[-1].clave != clave:
            etapas.append(EtapaOut(clave=clave, titulo=titulo, videos=[], vistos=0, total=0))
        etapas[-1].videos.append(s)

    for e in etapas:
        e.total = len(e.videos)
        e.vistos = sum(1 for v in e.videos if v.visto)

    return RutaOut(
        etapas=etapas,
        total=len(salidas),
        vistos=sum(1 for s in salidas if s.visto),
        siguiente_id=siguiente.id if siguiente else None,
    )


def marcar_abierto(db: DBSession, user: User, video_id) -> bool:
    """Registra que esta persona abrió este video · idempotente.

    Devuelve si se creó una fila nueva. Volver a abrirlo NO duplica ni
    actualiza la fecha: interesa "lo abrió alguna vez", que es lo que la ruta
    muestra, y reescribir la fecha en cada apertura perdería cuándo lo
    descubrió.
    """
    existe = (
        db.query(OrientationVideoView)
        .filter(OrientationVideoView.user_id == user.id)
        .filter(OrientationVideoView.video_id == video_id)
        .first()
    )
    if existe:
        return False

    db.add(OrientationVideoView(user_id=user.id, video_id=video_id))
    db.commit()
    return True


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
