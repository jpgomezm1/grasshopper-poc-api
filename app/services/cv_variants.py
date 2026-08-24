"""Variantes de la Hoja de Vida · destino (estándar) × apariencia (estilo).

Tres estándares por tres estilos son nueve combinaciones, y nadie quiere nueve
renderizadores. La separación que lo evita:

  * **El estándar decide el CONTENIDO** — si va foto, cuántas páginas y en qué
    orden salen las secciones. Es política de datos, no cosmética.
  * **El estilo decide el CSS** — se apila encima de una base común.
  * `CVData` no cambia. Sigue siendo el único modelo de contenido.

La consecuencia más útil de separarlo así es que **el estándar `us` omite la
foto**: en Estados Unidos incluirla se lee como sesgo y muchas oficinas de
admisión descartan el documento. El estudiante no tiene por qué saber eso — el
formato lo sabe por él, y `nota` es el texto con el que la interfaz se lo
explica en vez de callárselo.

`latam` es el valor por defecto **a propósito**: reproduce exactamente el orden
que el CV tenía antes de que existiera este módulo, así que nada de lo que ya
estaba impreso cambia de forma silenciosa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Las claves de sección que sabe emitir `cv_pdf_service`. El encabezado no está
# aquí porque no es reordenable: siempre va primero, en los tres estándares.
SECCIONES_VALIDAS = ("perfil", "tests", "actividades")


@dataclass(frozen=True)
class Estandar:
    """Convención del país o sistema al que se va a mandar el documento."""

    clave: str
    nombre: str
    permite_foto: bool
    max_paginas: int
    orden_secciones: Tuple[str, ...]
    #: Lo que la interfaz le muestra al estudiante para justificar la diferencia.
    #: Sin esto, quitarle la foto sin avisar parece un bug.
    nota: str


@dataclass(frozen=True)
class Estilo:
    """Apariencia. Puramente cosmético · nunca cambia qué información sale."""

    clave: str
    nombre: str
    descripcion: str
    css: str = ""


ESTANDARES: Dict[str, Estandar] = {
    "latam": Estandar(
        clave="latam",
        nombre="Latinoamérica",
        permite_foto=True,
        max_paginas=2,
        # Mismo orden que tenía el CV antes de existir este módulo.
        orden_secciones=("perfil", "tests", "actividades"),
        nota=(
            "El formato más común en Colombia y la región. Admite foto y suele "
            "abrir con un perfil breve."
        ),
    ),
    "us": Estandar(
        clave="us",
        nombre="Estados Unidos",
        permite_foto=False,
        max_paginas=1,
        # Allá pesa primero lo que hiciste; los tests psicométricos no son parte
        # de la convención, así que van al final y no compiten con lo demás.
        orden_secciones=("perfil", "actividades", "tests"),
        nota=(
            "En Estados Unidos la foto se omite: incluirla se interpreta como "
            "sesgo y muchas universidades descartan el documento. Aquí tu foto "
            "no se imprime aunque la hayas subido. Se busca que quepa en una "
            "página."
        ),
    ),
    "europass": Estandar(
        clave="europass",
        nombre="Europa (estilo Europass)",
        permite_foto=True,
        max_paginas=2,
        orden_secciones=("perfil", "tests", "actividades"),
        nota=(
            "La convención europea es más detallada y sí admite foto. El nivel "
            "de idioma es una sección esperada, no un adorno."
        ),
    ),
}

ESTANDAR_POR_DEFECTO = "latam"


# --- Estilos ---------------------------------------------------------------
# Cada bloque se APILA sobre el CSS base, no lo reemplaza: así un cambio en la
# base (un margen, un color de marca) llega a los tres sin tocarlos uno por uno.

_CSS_MODERNO = """
/* Moderno · barra de color, títulos sin caja y más aire. */
.header { border-bottom: none; padding: 5mm 6mm; margin-bottom: 6mm;
          background: #47368C; border-radius: 6px; }
.name { color: #ffffff; }
.headline { color: #F2C9B4; }
.contact, .contact b { color: #EAE7F4; }
h2 { border-bottom: none; color: #47368C; font-weight: 800;
     letter-spacing: 0.10em; }
h2::after { content: ""; display: block; width: 14mm; height: 2px;
            background: #EE7238; margin-top: 1.5mm; }
.test-card { background: #ffffff; border-left-width: 4px; }
.activity { border-left-color: #EE7238; }
"""

_CSS_COMPACTO = """
/* Compacto · para el estándar de una página. Aprieta interlineado y espacios
   antes que recortar contenido: quitar información es decisión del estudiante,
   no del estilo. */
body { font-size: 9.5pt; line-height: 1.35; }
@page { margin: 12mm 12mm; }
.name { font-size: 21pt; }
.headline { font-size: 10.5pt; }
h2 { font-size: 11pt; margin: 4.5mm 0 2mm 0; }
.header { padding-bottom: 3mm; margin-bottom: 4.5mm; }
.activity { margin-bottom: 2.5mm; }
.chip { padding: 0.6mm 2.4mm; font-size: 8.5pt; }
.test-card { padding: 1.8mm 2.5mm; }
.footer { margin-top: 5mm; }
"""

ESTILOS: Dict[str, Estilo] = {
    "clasico": Estilo(
        clave="clasico",
        nombre="Clásico",
        descripcion="Sobrio y legible. Es el que sirve para casi todo.",
        css="",
    ),
    "moderno": Estilo(
        clave="moderno",
        nombre="Moderno",
        descripcion="Encabezado con bloque de color. Se nota más en una pila de hojas.",
        css=_CSS_MODERNO,
    ),
    "compacto": Estilo(
        clave="compacto",
        nombre="Compacto",
        descripcion="Aprieta el espacio para caber en una página sin quitar contenido.",
        css=_CSS_COMPACTO,
    ),
}

ESTILO_POR_DEFECTO = "clasico"


def obtener_estandar(clave: Optional[str]) -> Estandar:
    """Devuelve el estándar pedido · cae al por defecto en vez de reventar.

    Un querystring inválido no debe dejar al estudiante sin hoja de vida: la
    propiedad de "siempre generable" que el servicio del PDF defiende en su
    docstring aplica también a los parámetros.
    """
    return ESTANDARES.get((clave or "").strip().lower(), ESTANDARES[ESTANDAR_POR_DEFECTO])


def obtener_estilo(clave: Optional[str]) -> Estilo:
    """Igual que `obtener_estandar`, para el estilo."""
    return ESTILOS.get((clave or "").strip().lower(), ESTILOS[ESTILO_POR_DEFECTO])


def debe_incluir_foto(estandar: Estandar, *, quiere_foto: bool, hay_foto: bool) -> bool:
    """Las tres condiciones que deben cumplirse para imprimir la foto.

    El estándar tiene la última palabra: aunque el estudiante haya subido su
    foto y haya marcado que la quiere, `us` no la imprime. Es la regla que
    justifica que esto sea política de datos y no una casilla de estilo.
    """
    return bool(estandar.permite_foto and quiere_foto and hay_foto)


def catalogo() -> Dict[str, List[Dict[str, object]]]:
    """El catálogo que consume la interfaz para pintar el selector."""
    return {
        "estandares": [
            {
                "clave": e.clave,
                "nombre": e.nombre,
                "permite_foto": e.permite_foto,
                "max_paginas": e.max_paginas,
                "nota": e.nota,
            }
            for e in ESTANDARES.values()
        ],
        "estilos": [
            {"clave": s.clave, "nombre": s.nombre, "descripcion": s.descripcion}
            for s in ESTILOS.values()
        ],
    }
