"""Traduce lo que escribe el estudiante a algo con lo que el buscador trabaje.

Por qué existe · los tres casos medidos que el vector no resuelve
----------------------------------------------------------------
El buscador ordena por parecido de texto contra 33.552 programas. Con el
catálogo completo y las glosas eso funciona bien cuando la persona nombra una
materia. Se rompe en tres casos, y los tres están medidos:

1. **Negación.** *"Quiero un trabajo donde no tenga que estar sentado en una
   oficina"* devuelve `Postgrado en Diseño del Espacio Interior` — o sea una
   oficina. Un embedding **no puede representar un "no"**: comprobado que
   `Outdoor Adventure Leadership` puntúa 0.217 contra 0.281 del programa de
   oficinas, así que la respuesta correcta puntúa *peor* que la absurda. Ningún
   ajuste de pesos ni de índice lo arregla.

2. **Varios intereses.** *"Me gustan los animales pero también dibujar"* devuelve
   diez programas de dibujo y pierde los animales. El vector promediado cae
   entre los dos conceptos y no se parece bien a ninguno: similitud 0.347,
   contra 0.45–0.48 cuando se busca cada concepto por separado.

3. **Datos que son filtro, no parecido.** "Maestría en Londres" son un nivel y
   una ciudad; resolverlos por similitud es desperdiciar la señal.

Cómo encaja con el filtro duro
------------------------------
**La IA no decide qué es elegible.** Sigue mandando SQL: `activo`, país, nivel
viable para la etapa de vida, lo que la agencia tiene autorizado. Lo que hace
este módulo es proponer **conceptos para ordenar** y **filtros que el estudiante
ve y puede quitar**. Un filtro que el modelo inventa y nadie ve escondería
33.000 programas de un golpe, y por eso viajan marcados con su origen.

Si el modelo falla, se devuelve la consulta tal cual y la búsqueda funciona como
antes. Es el mismo criterio que rige el resto del producto: la IA mejora, no
sostiene.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config import get_settings
from app.services import areas as areas_mod, lugares

logger = logging.getLogger(__name__)

#: El mismo modelo que escribe las glosas. Se probó contra `gpt-4o-mini` para
#: esa tarea y ganó; aquí la tarea es más de razonamiento que de redacción, así
#: que se verifica con el set de casos de `tests/test_interprete_busqueda.py`.
MODELO = "gpt-4.1-nano"

#: Etiquetas de lo que este catálogo no tiene. Cerradas a propósito: el frontend
#: escribe un mensaje distinto para cada una y una etiqueta inventada no tendría
#: ninguno.
FUERA_DE_ALCANCE = ("precio", "beca", "requisitos", "ranking")

NIVELES_LEGIBLES = {
    "secundaria": "bachillerato / colegio",
    "pregrado": "pregrado",
    "bachelor": "pregrado (bachelor)",
    "maestria": "maestría",
    "mba": "MBA",
    "doctorado": "doctorado",
    "posgrado": "posgrado",
    "especializacion": "especialización",
    "diplomado": "diplomado",
    "curso_corto": "curso corto",
    "vacacional": "programa vacacional / campamento",
    "intercambio": "intercambio",
    "bootcamp": "bootcamp",
}

_PROMPT: Optional[str] = None


@dataclass
class Interpretacion:
    """Lo que se entendió · todo opcional y todo reversible por el estudiante."""

    conceptos: List[str] = field(default_factory=list)
    paises: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)
    niveles: List[str] = field(default_factory=list)
    ciudades: List[str] = field(default_factory=list)
    fuera_de_alcance: List[str] = field(default_factory=list)
    entendi: str = ""
    #: `False` cuando el modelo falló y se siguió sin él · la respuesta lo dice
    #: para que nadie confunda "no había nada que interpretar" con "no se pudo".
    interpretada: bool = False

    def hay_filtros(self) -> bool:
        return bool(self.paises or self.areas or self.niveles or self.ciudades)


def _prompt() -> str:
    global _PROMPT
    if _PROMPT is None:
        ruta = os.path.join(os.path.dirname(__file__), "..", "prompts",
                            "interpretar_busqueda.txt")
        with open(ruta, encoding="utf-8") as fh:
            _PROMPT = fh.read()
    return _PROMPT


def _vocabularios() -> Dict[str, str]:
    """Las listas cerradas que se le inyectan al modelo.

    Se le dan para que **elija de una lista en vez de inventar**. Salen de los
    módulos que ya son la fuente de verdad —`areas.AREAS`, `lugares`— y no de una
    copia: una lista duplicada aquí se desactualizaría en la siguiente tanda de
    extracción y el modelo empezaría a proponer filtros que no existen.
    """
    paises = sorted({p.nombre for p in lugares._PAISES.values()})
    return {
        "paises": ", ".join(paises),
        "areas": ", ".join(areas_mod.AREAS),
        "niveles": ", ".join(f"{k} ({v})" for k, v in NIVELES_LEGIBLES.items()),
    }


def _solo_conocidos(valores, validos) -> List[str]:
    """Descarta lo que el modelo se inventó pese a la lista cerrada."""
    vistos, salida = set(), []
    for v in valores or []:
        if not isinstance(v, str):
            continue
        v = v.strip()
        if v in validos and v not in vistos:
            vistos.add(v)
            salida.append(v)
    return salida


def _parsear(crudo: str) -> Optional[dict]:
    """El JSON que devolvió el modelo · `None` si no se puede leer.

    Se extrae con una expresión y no con `json.loads` directo porque los modelos
    pequeños envuelven la respuesta en ```json a pesar de que se les pida que no.
    """
    if not crudo:
        return None
    m = re.search(r"\{.*\}", crudo, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) else None
    except (ValueError, TypeError):
        return None


async def interpretar(consulta: str) -> Interpretacion:
    """Lo que el estudiante quiso decir · nunca lanza.

    Si algo falla —la clave, la red, un JSON roto— se devuelve una
    `Interpretacion` con `interpretada=False` y la consulta original como único
    concepto. La búsqueda entonces se comporta exactamente como antes de que
    este módulo existiera, que es la degradación correcta.
    """
    texto = (consulta or "").strip()
    if not texto:
        return Interpretacion()

    # El respaldo se arma antes de intentar nada, para que cualquier salida por
    # error ya lo tenga listo.
    respaldo = Interpretacion(conceptos=[texto], interpretada=False)

    s = get_settings()
    if not s.openai_api_key:
        return respaldo

    try:
        from openai import AsyncOpenAI

        cli = AsyncOpenAI(api_key=s.openai_api_key, timeout=6.0, max_retries=1)
        r = await cli.chat.completions.create(
            model=MODELO, temperature=0.0, max_tokens=400,
            messages=[{
                "role": "user",
                "content": _prompt().format(consulta=texto, **_vocabularios()),
            }],
        )
        d = _parsear(r.choices[0].message.content or "")
    except Exception:
        # El timeout es de 6 s a propósito: esto va en el camino crítico de una
        # búsqueda y es preferible buscar sin interpretar que hacer esperar.
        logger.warning("no se pudo interpretar la consulta", exc_info=True)
        return respaldo

    if not d:
        return respaldo

    f = d.get("filtros") or {}
    conceptos = [c.strip() for c in (d.get("conceptos") or [])
                 if isinstance(c, str) and c.strip()][:3]
    paises = _solo_conocidos(f.get("paises"), {p.nombre for p in lugares._PAISES.values()})
    areas = _solo_conocidos(f.get("areas"), set(areas_mod.AREAS))
    niveles = _solo_conocidos(f.get("niveles"), set(NIVELES_LEGIBLES))
    ciudades = [c.strip() for c in (f.get("ciudades") or [])
                if isinstance(c, str) and c.strip()][:3]
    fuera = _solo_conocidos(d.get("fuera_de_alcance"), set(FUERA_DE_ALCANCE))
    entendi = (d.get("entendi") or "").strip()[:200]

    # Si no se sacó nada del texto, no hay nada que haber entendido.
    #
    # Esto no es defensa teórica: escribiendo "hola", el modelo devolvía
    # `conceptos: []` —correcto— y a la vez `entendi: "Buscas algo al aire libre,
    # lejos del escritorio"`, que es **el ejemplo del prompt copiado tal cual**.
    # Esa frase se le muestra al estudiante para que confirme si le entendimos,
    # así que una alucinación ahí es de las que más confunden. Los modelos
    # pequeños copian los ejemplos cuando la entrada no les da de qué agarrarse,
    # y pedirles que no lo hagan no alcanza.
    if not conceptos and not (paises or areas or niveles or ciudades or fuera):
        entendi = ""

    return Interpretacion(
        # Sin conceptos NO se cae al texto original: que el modelo devuelva la
        # lista vacía es una respuesta, no un fallo — significa que la persona no
        # expresó ningún interés ("hola", "no sé qué estudiar"). Caer al texto
        # ahí volvería a buscar por parecido de "hola", que es lo que hoy
        # devuelve "Welcome Camp".
        conceptos=conceptos,
        paises=paises, areas=areas, niveles=niveles, ciudades=ciudades,
        fuera_de_alcance=fuera,
        entendi=entendi,
        interpretada=True,
    )
