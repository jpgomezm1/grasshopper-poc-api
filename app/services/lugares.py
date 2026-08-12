"""Geografía · la única fuente de verdad para cruzar los dos catálogos.

Los dos catálogos de este producto guardan el país como texto libre, y no se
parecen entre sí. Medido sobre la base real:

  * `programs` (2.508 instituciones autorizadas) → 25 valores distintos, y está
    **en dos idiomas dentro de la misma tabla**: tiene `Ireland` *e* `Irlanda`,
    `Italy` *e* `Italia`.
  * `programas_investigados` (15.483 programas) → 20 valores, en español:
    `Reino Unido`, `Estados Unidos`, `Canadá`.

Sin normalizar, cualquier vista que junte los dos —una lista por lugar, un
mapa— muestra Canadá dos veces y parte los conteos por la mitad.

## Por qué una tabla escrita a mano y no coincidencia difusa

Son 45 valores en total y no van a crecer solos: los produce un Excel de la
agencia y un scraper nuestro. Una tabla explícita se lee, se revisa y falla de
forma evidente; una heurística de similitud acertaría en `Italy`/`Italia` y
metería `Austria` en `Australia` sin que nadie lo note.

## Lo que NO es un país

`ASIA`, `International` y `Varios destinos` están en esas columnas y no son
países. `pais_canonico` devuelve `None` para ellos **a propósito**: no se les
inventa un código ni se les planta un pin en un mapa. Quien los consuma decide
qué hacer, pero no puede confundirlos con un país de verdad.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Pais:
    """Un país canónico · el código manda, el nombre es para mostrar."""

    iso: str
    #: En español · el producto es sólo español (target Colombia, sin i18n).
    nombre: str


def _plano(texto: Optional[str]) -> str:
    """minúsculas, sin tildes y con los espacios colapsados.

    Es lo que hace que `Canadá`/`Canada` y `Paises Bajos`/`Países Bajos` no
    necesiten dos entradas en la tabla de abajo.
    """
    if not texto:
        return ""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


# Los 22 países reales que aparecen en los dos catálogos, con todas las formas
# en que están escritos. Las claves van ya "planas" (ver `_plano`).
_PAISES: Dict[str, Pais] = {}


def _registrar(iso: str, nombre: str, *variantes: str) -> None:
    pais = Pais(iso=iso, nombre=nombre)
    for v in (nombre, *variantes):
        _PAISES[_plano(v)] = pais


_registrar("AU", "Australia")
_registrar("AT", "Austria")
_registrar("BE", "Bélgica", "Belgium")
_registrar("BG", "Bulgaria")
_registrar("CA", "Canadá", "Canada")
_registrar("CH", "Suiza", "Switzerland")
_registrar("CN", "China")
_registrar("CZ", "República Checa", "Czech Republic", "Czechia")
_registrar("DE", "Alemania", "Germany")
_registrar("ES", "España", "Spain")
_registrar("FR", "Francia", "France")
_registrar("GB", "Reino Unido", "UK", "United Kingdom", "Great Britain")
_registrar("IE", "Irlanda", "Ireland")
_registrar("IT", "Italia", "Italy")
_registrar("MT", "Malta")
_registrar("NL", "Países Bajos", "Netherlands", "Holanda")
_registrar("NZ", "Nueva Zelanda", "New Zealand")
_registrar("PL", "Polonia", "Poland")
_registrar("US", "Estados Unidos", "USA", "United States", "EEUU", "EE.UU.")
_registrar("AE", "Emiratos Árabes Unidos", "UAE", "United Arab Emirates")

# Chipre del Norte no tiene código ISO-3166: sólo lo reconoce Turquía. Se le da
# un código propio con prefijo `X` (el rango que ISO reserva para uso privado)
# para que no colisione nunca con uno oficial, y se deja igual de utilizable
# que los demás — hay programas ahí y el estudiante tiene que poder verlos.
_registrar(
    "XNC", "Chipre del Norte",
    "República Turca del Norte de Chipre", "Northern Cyprus",
)

#: Valores que están en la columna de país y NO son países. Se listan explícitos
#: para poder distinguir "esto no es un país" de "esto no lo conozco todavía":
#: lo segundo merece que alguien lo mire, lo primero no.
NO_SON_PAISES = frozenset({
    _plano("International"),
    _plano("ASIA"),
    _plano("Varios destinos"),
})


def pais_canonico(texto: Optional[str]) -> Optional[Pais]:
    """El país canónico de un texto suelto · `None` si no lo es o no se conoce.

    Devuelve `None` tanto para `'International'` como para un país que no esté
    en la tabla. La diferencia entre esos dos casos la da `es_pais_desconocido`,
    que es la que sirve para avisar de que hay que ampliar la tabla.
    """
    return _PAISES.get(_plano(texto))


def es_pais_desconocido(texto: Optional[str]) -> bool:
    """Hay algo escrito, no es un "no-país" conocido, y aun así no lo tenemos.

    Sirve para que un valor nuevo del Excel de la agencia salte a la vista en
    vez de desaparecer del mapa en silencio.
    """
    plano = _plano(texto)
    if not plano or plano in NO_SON_PAISES:
        return False
    return plano not in _PAISES


def clave_lugar(ciudad: Optional[str], pais: Optional[str]) -> Optional[str]:
    """La clave con la que un lugar se cruza entre los dos catálogos.

    Formato: ``<iso>:<ciudad plana>`` — por ejemplo ``gb:london``.

    Es lo que hace que `'Londres' / 'Reino Unido'` y `'London' / 'UK'` sean el
    mismo lugar. Devuelve `None` si no hay país reconocible o no hay ciudad:
    **un lugar sin clave no se inventa**, se queda fuera del mapa y se cuenta
    aparte (son 341 instituciones y 4.332 programas, y desaparecer en silencio
    sería lo peor que podrían hacer).
    """
    p = pais_canonico(pais)
    c = _plano(ciudad)
    if p is None or not c:
        return None
    return f"{p.iso.lower()}:{_ciudad_canonica(c)}"


#: Ciudades que los dos catálogos escriben distinto. La lista es corta a
#: propósito: sólo entran las que de verdad aparecen en ambos lados, porque
#: cada entrada de más es una oportunidad de equivocarse.
_CIUDADES = {
    "londres": "london",
    "roma": "rome",
    "milan": "milano",
    "viena": "vienna",
    "ginebra": "geneva",
    "zurich": "zurich",
    "munich": "munich",
    "colonia": "cologne",
    "florencia": "florence",
    "venecia": "venice",
    "napoles": "naples",
    "turin": "torino",
    "la haya": "the hague",
    "amberes": "antwerp",
    "brujas": "bruges",
    "praga": "prague",
    "varsovia": "warsaw",
    "cracovia": "krakow",
    "nueva york": "new york",
    "los angeles": "los angeles",
    "dublin": "dublin",
    "edimburgo": "edinburgh",
    "atenas": "athens",
    "lisboa": "lisbon",
}


def _ciudad_canonica(ciudad_plana: str) -> str:
    return _CIUDADES.get(ciudad_plana, ciudad_plana)


# ---------------------------------------------------------------------------
# Recuperar lugares que se estaban perdiendo (2026-08-11)
# ---------------------------------------------------------------------------
#
# 4.731 opciones no salían en el mapa por no tener una ciudad utilizable. Medido,
# la mayoría se recupera **sin salir a internet y sin inventar nada**:
#
#   * 116 campos traen varias ciudades a la vez (`'Madrid, Valencia, Canarias'`
#     carga 410 programas él solo). Se toma la primera.
#   * ~800 programas no tienen ciudad, pero **su institución sí la tiene** en el
#     catálogo autorizado. Si la universidad está en Toronto, sus programas
#     también: eso es un hecho, no una deducción.
#
# Lo que se recupera **queda marcado con su origen**. Un lugar deducido y uno
# que puso la agencia no pueden verse igual: es la misma disciplina con la que
# este producto separa lo autorizado de lo investigado.

#: De dónde salió la ubicación de una fila.
ORIGEN_EXACTO = "exacto"        # la ciudad tal cual la escribió la agencia
ORIGEN_RECORTADO = "recortado"  # el campo traía varias y se tomó la primera
ORIGEN_INSTITUCION = "institucion"  # se heredó de la institución

_SEPARADORES = re.compile(r"\s*(?:,|/|;|\sy\s|&)\s*")


def primera_ciudad(ciudad: Optional[str]) -> Optional[str]:
    """De `'Madrid, Valencia, Canarias'` devuelve `'Madrid'`.

    Un campo con varias ciudades no es un punto en el mapa, pero **sí contiene
    uno**: la primera es la que la agencia escribió primero y en la práctica es
    la principal. Se queda con esa y la marca como recortada, en vez de tirar
    los 410 programas que cuelgan de ese campo.
    """
    if not ciudad:
        return None
    for trozo in _SEPARADORES.split(str(ciudad)):
        limpio = trozo.strip()
        # Descarta restos tipo `'VA'` o `'UK'` que quedan al partir.
        if len(limpio) > 2:
            return limpio
    return None


def resolver_lugar(
    ciudad: Optional[str],
    pais: Optional[str],
    ciudad_de_la_institucion: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """La clave del lugar y **de dónde salió** · `(clave, origen)`.

    Intenta tres cosas, en orden de menos a más deducción:

      1. La ciudad tal cual → `exacto`.
      2. La primera de un campo con varias → `recortado`.
      3. La ciudad de su institución → `institucion`.

    Devuelve `(None, None)` si ninguna funciona. **Nunca inventa**: si no hay
    de dónde sacarla, la fila se queda fuera del mapa y se cuenta aparte, que
    es lo que veníamos haciendo.

    Vive aquí y no en cada endpoint a propósito: el mapa y el filtro por lugar
    tienen que resolver **igual**, o el pin prometería una cantidad y la lista
    mostraría otra.
    """
    clave = clave_lugar(ciudad, pais)
    if clave:
        return clave, ORIGEN_EXACTO

    recortada = primera_ciudad(ciudad)
    if recortada and recortada != (ciudad or "").strip():
        clave = clave_lugar(recortada, pais)
        if clave:
            return clave, ORIGEN_RECORTADO

    if ciudad_de_la_institucion:
        # La institución puede tener también un campo con varias · se recorta
        # igual antes de usarla.
        heredada = clave_lugar(ciudad_de_la_institucion, pais) or clave_lugar(
            primera_ciudad(ciudad_de_la_institucion), pais
        )
        if heredada:
            return heredada, ORIGEN_INSTITUCION

    return None, None


def nombre_de_ciudad(ciudad: Optional[str]) -> Optional[str]:
    """La ciudad tal cual, sólo con los espacios limpios · para mostrar.

    No se traduce ni se "corrige" el nombre que puso la agencia: si su ficha
    dice `Londres`, su asesor va a hablar de Londres.
    """
    if not ciudad:
        return None
    limpio = re.sub(r"\s+", " ", str(ciudad)).strip()
    return limpio or None
