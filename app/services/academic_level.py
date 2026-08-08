"""A8 · Qué nivel de programa le corresponde a cada etapa de vida.

Verónica, reunión del 21-07: *"la IA debería ir a la institución a buscar qué
foundations, pregrados y maestrías tiene que le puedan servir a esa persona
según su perfil"* · y su ejemplo concreto: **pregrado si está en último año de
colegio**.

Hasta ahora el recomendador puntuaba por presupuesto, país, intereses, RIASEC y
becas — **nada relacionaba el nivel académico con dónde está la persona**. Un
estudiante de grado 11 podía recibir un MBA.

## Por qué se bloquea tan poco

`Program.type` **está adivinado**: `scripts/build_programs_from_catalog.py`
lo deriva de la categoría de la institución y de palabras sueltas en texto
libre, y cuando nada calza cae en `curso_corto`. Filtrar duro sobre un dato
adivinado esconde oferta real.

Por eso la única razón para descartar es **credencial imposible**: no se puede
cursar una maestría sin haber terminado un pregrado. Eso no es una preferencia
ni un gusto — es un requisito de admisión, y sigue siendo cierto aunque el
`type` esté mal adivinado en alguna fila. Todo lo demás **pondera**, no filtra.

## Vocabulario doble, a propósito

La etapa llega con dos vocabularios distintos según de dónde venga la persona:
códigos en `users.onboarding_answers` (`high_school`) y textos de opción en
`sessions.answers` (`"Terminando el colegio"`). Los dos se normalizan aquí, en
un solo sitio, para no repetir la traducción en cada consumidor.

`high_school_early` vs `high_school` existen separados desde R6-ON-1b porque
ella lo pidió dos veces en la reunión (*"estoy en el colegio o estoy en último
año"*, *"Susana de 11 grados"*): antes un estudiante de 9° le decía a la IA que
estaba a punto de graduarse.
"""
from __future__ import annotations

from typing import Optional, Set

# Etapas canónicas de este módulo.
EN_COLEGIO = "en_colegio"
TERMINANDO_COLEGIO = "terminando_colegio"
EN_UNIVERSIDAD = "en_universidad"
EGRESADO = "egresado"
TRABAJANDO = "trabajando"

# Los dos vocabularios con los que llega la etapa. `career_change` y
# `recent_grad` caen los dos en EGRESADO: para efectos de qué nivel puede
# cursar, ya tienen un título terminado o están fuera del sistema académico.
_NORMALIZACION = {
    # Códigos de users.onboarding_answers["life_stage"]
    "high_school_early": EN_COLEGIO,
    "high_school": TERMINANDO_COLEGIO,
    "university": EN_UNIVERSIDAD,
    "recent_grad": EGRESADO,
    "career_change": EGRESADO,
    "working": TRABAJANDO,
    # Textos de sessions.answers["lifeStage"] (las opciones del journey)
    "en el colegio": EN_COLEGIO,
    "terminando el colegio": TERMINANDO_COLEGIO,
    "en la universidad": EN_UNIVERSIDAD,
    "ya trabajando": TRABAJANDO,
    # "En transición / no seguro" NO está: es justo la persona de la que no
    # sabemos si tiene título. Ante la duda no se le esconde nada.
}

# Las etapas canónicas se reconocen a sí mismas · normalizar dos veces tiene que
# dar lo mismo que normalizar una.
#
# Sin esto, `normalizar_etapa("terminando_colegio")` —el propio valor que este
# módulo devuelve— daba None, y con None este módulo **no descarta nada**: a un
# estudiante de 11° le volvían a aparecer maestrías y doctorados. Es el bug que
# A8 vino a arreglar, entrando por otra puerta. Cualquiera que guarde la etapa ya
# normalizada y la vuelva a pasar cae en él, sin ningún síntoma visible.
_NORMALIZACION.update({e: e for e in (
    EN_COLEGIO, TERMINANDO_COLEGIO, EN_UNIVERSIDAD, EGRESADO, TRABAJANDO,
)})

# Niveles que exigen un título que la persona todavía NO puede tener.
_POSGRADO = {"maestria", "mba", "doctorado", "especializacion", "posgrado"}

_IMPOSIBLES = {
    # Sin bachillerato terminado no hay posgrado. El pregrado NO se bloquea:
    # planear la carrera desde el colegio es exactamente lo que hace esta
    # agencia, y las foundations son la vía.
    EN_COLEGIO: _POSGRADO,
    TERMINANDO_COLEGIO: _POSGRADO,
    # En la universidad todavía no hay título terminado. La maestría sí se
    # deja pasar: planearla mientras se termina el pregrado es normal y es
    # media conversación de esta agencia. El doctorado no.
    EN_UNIVERSIDAD: {"doctorado"},
    # Con un título en la mano nada es imposible.
    EGRESADO: set(),
    TRABAJANDO: set(),
}

_PREFERIDOS = {
    EN_COLEGIO: {"secundaria", "intercambio", "vacacional"},
    TERMINANDO_COLEGIO: {"pregrado", "bachelor", "intercambio", "vacacional"},
    EN_UNIVERSIDAD: {"pregrado", "bachelor", "intercambio", "curso_corto", "diplomado"},
    EGRESADO: {"maestria", "posgrado", "especializacion", "diplomado", "curso_corto"},
    TRABAJANDO: {"maestria", "mba", "especializacion", "diplomado", "bootcamp", "curso_corto"},
}

# Lo que devuelve `evaluar`.
IMPOSIBLE = "imposible"
PREFERIDO = "preferido"
NEUTRO = "neutro"


def normalizar_etapa(valor: Optional[str]) -> Optional[str]:
    """Traduce cualquiera de los dos vocabularios a la etapa canónica.

    Devuelve None cuando no se reconoce — que es lo correcto para
    "En transición / no seguro" y para cualquier valor futuro que nadie haya
    mapeado todavía: sin etapa, este módulo no descarta nada.
    """
    if not valor:
        return None
    return _NORMALIZACION.get(str(valor).strip().lower())


def evaluar(program_type: Optional[str], life_stage: Optional[str]) -> str:
    """¿Este nivel es imposible, preferido o indiferente para esta persona?

    Una decisión, una función (regla del repo): la usan el filtro del
    recomendador y el bloque que ve el modelo, y no puede haber dos criterios
    distintos rondando.

    Devuelve NEUTRO —nunca IMPOSIBLE— cuando falta cualquiera de los dos datos.
    El catálogo demo estático no trae `type`, y una etapa que no reconocemos no
    es motivo para esconderle oferta a nadie.
    """
    etapa = normalizar_etapa(life_stage)
    if etapa is None or not program_type:
        return NEUTRO

    tipo = str(program_type).strip().lower()
    if tipo in _IMPOSIBLES.get(etapa, set()):
        return IMPOSIBLE
    if tipo in _PREFERIDOS.get(etapa, set()):
        return PREFERIDO
    return NEUTRO


def etapa_legible(life_stage: Optional[str]) -> Optional[str]:
    """La etapa en español, para el prompt. None si no se reconoce."""
    etapa = normalizar_etapa(life_stage)
    return {
        EN_COLEGIO: "en el colegio (aún le faltan años para graduarse)",
        TERMINANDO_COLEGIO: "terminando el colegio (último año)",
        EN_UNIVERSIDAD: "cursando la universidad",
        EGRESADO: "ya terminó sus estudios / en transición",
        TRABAJANDO: "trabajando",
    }.get(etapa) if etapa else None


def niveles_fuera_de_alcance(life_stage: Optional[str]) -> Set[str]:
    """Los niveles que esta persona no puede cursar todavía · para el prompt.

    Se le dice al modelo explícitamente además de filtrarlos del catálogo: el
    filtro evita que aparezcan, y esta lista evita que los mencione como
    sugerencia en el `why_match`.
    """
    etapa = normalizar_etapa(life_stage)
    return set(_IMPOSIBLES.get(etapa, set())) if etapa else set()
