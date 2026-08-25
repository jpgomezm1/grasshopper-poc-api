"""El estante de videos del Journey · Verónica, reunión 24-08 (19:52 y 20:03).

    "hay unas partes donde me gustaria irles poniendo como videos que yo tengo"
    "no se donde se montaria en el journey"

Y JP propuso el criterio de cuándo mostrarlos (20:03): "que haga parte del
journey, si ya tienes mucha claridad saltate los videos, si todavia
necesitas que te oriente...".

## Este módulo es el ESTANTE, no el contenido

`VIDEOS` empieza **vacío a propósito**. El contenido —URL, duración, de qué
trata cada video— lo produce y sube la clienta, no nosotros: inventar una
URL o una duración sería el mismo tipo de dato inventado por el que ya hubo
un reclamo (ver `CLAUDE.md` del repo, "la IA NUNCA inventa datos duros").

Falta, deliberadamente, CÓMO se cargan: quién los sube (¿la clienta por un
panel? ¿un script de datos?) es una decisión de producto que no se tomó en
la reunión del 24-08 — sólo se pidió el mecanismo. Cuando se decida, la
forma más natural dado el resto del repo es un endpoint de escritura en
`school_admin.py` o un panel interno, pero eso es de otro agente/otra
corrida: aquí sólo se deja la estructura y el selector listos para usarse.

## Dónde se monta

Cada video se ancla a un `momento` = el id de un hecho de
`app.data.journey_chat_hechos.HECHOS` — se ofrece justo DESPUÉS de que la
conversación recoge ese hecho, que es cuando tiene sentido en el hilo (por
ejemplo, un video sobre "cómo elegir entre programa y país" después de
`geoPreference`). `ruta` (opcional) lo dirige a una de las 5 rutas de la
malla completa (Cimientos, migración 067) o lo deja genérico si es `None`.

## Cómo se salta

`elegir_video` nunca ofrece un video a quien ya respondió `clarityLevel`
con "Tengo algo claro y quiero validarlo" — es la regla textual de JP. Fuera
de ese caso, el video NUNCA es obligatorio: el front lo puede mostrar con un
botón de saltar, esto sólo decide si se OFRECE.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
    # None = aplica a cualquiera de las 5 rutas de la malla completa.
    ruta: Optional[str] = None


# Vacío a propósito · ver docstring del módulo. NO agregar entradas de
# ejemplo ni URLs de prueba: `elegir_video` se comporta igual con la lista
# vacía (nunca ofrece nada) que con contenido real sin cargar todavía, así
# que no hace falta un placeholder para que el mecanismo quede probado.
VIDEOS: List[JourneyVideo] = []

_CLARIDAD_ALTA = "Tengo algo claro y quiero validarlo"

_POR_MOMENTO: Dict[str, List[JourneyVideo]] = {}


def _index() -> Dict[str, List[JourneyVideo]]:
    """Se reconstruye en cada llamada · `VIDEOS` es una lista módulo-level que
    en el futuro puede recargarse (p.ej. si termina viniendo de una fuente
    editable) y este selector no puede quedarse con un índice viejo."""
    indice: Dict[str, List[JourneyVideo]] = {}
    for v in VIDEOS:
        indice.setdefault(v.momento, []).append(v)
    return indice


def elegir_video(
    momento: str,
    recolectados: Dict[str, Any],
    ruta: Optional[str] = None,
) -> Optional[JourneyVideo]:
    """El video para este momento, o `None` si no hay uno cargado o si la
    persona ya tiene claridad alta (regla de JP).

    Nunca bloquea el avance de la conversación: es un complemento opcional
    que el front puede mostrar mientras Hop sigue con la pregunta siguiente.
    """
    if recolectados.get("clarityLevel") == _CLARIDAD_ALTA:
        return None

    candidatos = _index().get(momento, [])
    if not candidatos:
        return None

    # El específico de la ruta gana sobre el genérico si ambos existen.
    especificos = [v for v in candidatos if ruta is not None and v.ruta == ruta]
    if especificos:
        return especificos[0]
    genericos = [v for v in candidatos if v.ruta is None]
    return genericos[0] if genericos else None
