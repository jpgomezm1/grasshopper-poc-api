"""Variantes de la Hoja de Vida · destino (estándar) × apariencia (estilo).

Cuatro estándares por tres estilos son doce combinaciones, y nadie quiere doce
renderizadores. La separación que lo evita:

  * **El estándar decide el CONTENIDO** — si va foto, cuántas páginas, qué
    secciones salen y en qué orden, y si el documento lleva cláusula legal al
    pie. Es política de datos, no cosmética.
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

## España y Colombia (2026-08-25)

Pedido literal de la clienta en la reunión del 24-08:

    "voy a ir para España, pues una hoja de vida tipo que se usa en España o la
     que se usa en Colombia"

**Colombia no es un estándar nuevo: es `latam`.** La convención colombiana —
foto tipo documento, dos páginas, perfil arriba— es la misma que ya
implementaba ese estándar, así que se le cambió el nombre visible a "Colombia y
Latinoamérica" y se registró `colombia` como ALIAS. Crear una entrada aparte,
idéntica campo por campo, habría sido justo el capricho que esta tarea pedía
evitar; y renombrar la clave habría roto las filas de `cv_profiles` que ya
tienen `estandar="latam"` guardado.

**España sí es distinta de verdad**, y en cuatro cosas concretas:

  1. **Idiomas es una sección propia**, con el nivel del Marco Común Europeo
     (MCER) explícito. En Colombia el nivel de inglés es una línea más del
     encabezado; en España se espera verlo aparte. Por eso `espana` (y
     `europass`) llevan `"idiomas"` en `orden_secciones` — y por eso el
     encabezado deja de repetirlo cuando la sección existe (ver
     :func:`idioma_va_en_seccion`). Nota al margen: la `nota` de `europass` ya
     prometía esa sección desde que se escribió el módulo, pero la sección no
     existía. Ahora existe.
  2. **La cláusula de protección de datos al pie** (`aviso_legal`) es costumbre
     en España desde el RGPD y su ausencia se nota; en Colombia no se usa en la
     hoja de vida.
  3. **Los resultados de tests psicométricos van al final**: no forman parte de
     la convención española y compiten con lo que allá sí se lee primero. No se
     eliminan —son valiosos y son suyos— pero no abren el documento.
  4. Se valora la brevedad: dos páginas como máximo, igual que en Colombia,
     pero con las actividades por delante de los tests.

## Cómo se agrega otro país

1. Añade una entrada a :data:`ESTANDARES` con su política **y su `nota`**: la
   nota no es opcional, es lo que le explica a la persona por qué su documento
   cambió. Si no sabes escribir la nota, es que todavía no sabes cuál es la
   diferencia real y no deberías añadir el estándar.
2. Si el país necesita una sección que aún no existe, agrégala a
   :data:`SECCIONES_VALIDAS` y **a los dos renderizadores** — `cv_pdf_service`
   y `cv_docx_service` tienen cada uno su propio mapa `_SECCIONES`. Si sólo la
   pones en uno, el estudiante se baja el Word y el PDF y son documentos
   distintos (el bug P0-8, otra vez).
3. Si es sólo otro nombre para una convención que ya está, va en
   :data:`ALIAS`, no en `ESTANDARES`.
4. Añade el caso al test `test_herramientas_mini_apps.py::TestHojaDeVidaPorPais`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Las claves de sección que saben emitir `cv_pdf_service` y `cv_docx_service`.
# El encabezado no está aquí porque no es reordenable: siempre va primero, en
# todos los estándares.
SECCIONES_VALIDAS = ("perfil", "idiomas", "tests", "actividades")


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
    #: Cláusula legal al pie del documento. Es costumbre en España desde el
    #: RGPD y no se usa en la hoja de vida colombiana, así que la decide el
    #: destino y no el estilo. `None` = el documento no lleva ninguna.
    aviso_legal: Optional[str] = None


@dataclass(frozen=True)
class Estilo:
    """Apariencia. Puramente cosmético · nunca cambia qué información sale."""

    clave: str
    nombre: str
    descripcion: str
    css: str = ""


#: La cláusula que en España se pone al final de la hoja de vida. Redactada en
#: términos del RGPD (Reglamento (UE) 2016/679), que es el marco que allá
#: aplica — no la Ley 1581 colombiana, que rige lo que hacemos NOSOTROS con el
#: dato, no lo que la persona autoriza a la empresa a la que se postula.
_CLAUSULA_RGPD = (
    "Autorizo el tratamiento de los datos personales incluidos en este "
    "documento con la única finalidad de participar en el proceso de selección, "
    "conforme al Reglamento (UE) 2016/679 (RGPD). Puedo ejercer mis derechos de "
    "acceso, rectificación, supresión y oposición en cualquier momento."
)


ESTANDARES: Dict[str, Estandar] = {
    "latam": Estandar(
        clave="latam",
        # "Colombia" va primero en el nombre porque es el país de casi todos
        # los usuarios y porque la clienta lo pidió por su nombre. La clave
        # sigue siendo `latam` para no romper las filas ya guardadas.
        nombre="Colombia y Latinoamérica",
        permite_foto=True,
        max_paginas=2,
        # Mismo orden que tenía el CV antes de existir este módulo.
        orden_secciones=("perfil", "tests", "actividades"),
        nota=(
            "La hoja de vida como se usa en Colombia y en la región: admite "
            "foto, abre con un perfil breve y cabe en dos páginas. El nivel de "
            "idioma va en el encabezado, no en una sección aparte."
        ),
    ),
    "espana": Estandar(
        clave="espana",
        nombre="España",
        permite_foto=True,
        max_paginas=2,
        # Idiomas es sección propia y los tests cierran: ver el docstring del
        # módulo, punto 1 y punto 3 de las diferencias reales.
        orden_secciones=("perfil", "idiomas", "actividades", "tests"),
        nota=(
            "En España el currículum admite foto, se espera que los idiomas "
            "aparezcan en su propia sección con el nivel del Marco Común "
            "Europeo (MCER), y se acostumbra cerrar con una cláusula de "
            "protección de datos (RGPD) que aquí se añade automáticamente. Los "
            "resultados de tus tests siguen saliendo, pero al final: allá no "
            "son parte del formato habitual."
        ),
        aviso_legal=_CLAUSULA_RGPD,
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
        # "idiomas" se añadió el 2026-08-25: su `nota` prometía esa sección
        # desde el primer día y la sección no existía — un texto que le
        # explicaba al estudiante algo que el documento no hacía.
        orden_secciones=("perfil", "idiomas", "tests", "actividades"),
        nota=(
            "La convención europea es más detallada y sí admite foto. El nivel "
            "de idioma es una sección esperada, no un adorno."
        ),
    ),
}

ESTANDAR_POR_DEFECTO = "latam"

#: Otros nombres con los que se puede pedir un estándar que YA existe. No son
#: entradas del catálogo (`/me/cv/formatos` sigue mostrando cuatro opciones):
#: son sinónimos que se resuelven al entrar. `colombia` está aquí y no en
#: `ESTANDARES` porque la convención colombiana ES la de `latam`, campo por
#: campo — ver el docstring del módulo.
ALIAS: Dict[str, str] = {
    "colombia": "latam",
    "co": "latam",
    "españa": "espana",
    "spain": "espana",
    # "es" NO está aquí a propósito: es el código de idioma español y un día
    # alguien lo va a mandar creyendo que pide "en español", no "para España".
}


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


def canonico(clave: Optional[str]) -> Optional[str]:
    """La clave real de un estándar, resolviendo alias · `None` si no existe.

    Es lo que usa `cv_profile_service.save_formato` para guardar: si alguien
    manda "colombia", en la base queda "latam". Sin esto, la preferencia se
    guardaría con una clave que después nadie sabe leer — el anti-patrón de
    escribir un dato que ningún lector entiende.
    """
    limpia = (clave or "").strip().lower()
    limpia = ALIAS.get(limpia, limpia)
    return limpia if limpia in ESTANDARES else None


def obtener_estandar(clave: Optional[str]) -> Estandar:
    """Devuelve el estándar pedido · cae al por defecto en vez de reventar.

    Un querystring inválido no debe dejar al estudiante sin hoja de vida: la
    propiedad de "siempre generable" que el servicio del PDF defiende en su
    docstring aplica también a los parámetros.
    """
    return ESTANDARES[canonico(clave) or ESTANDAR_POR_DEFECTO]


def idioma_va_en_seccion(estandar: Estandar) -> bool:
    """¿Este destino imprime los idiomas en su propia sección?

    Cuando la respuesta es sí, el encabezado **deja de repetir** el nivel de
    inglés. Que el mismo dato salga dos veces en una hoja de vida de dos
    páginas se lee como descuido, y la sección es la que manda porque es la que
    el formato del país espera.
    """
    return "idiomas" in estandar.orden_secciones


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
                # La pantalla necesita poder advertir de la cláusula legal
                # ANTES de que la persona descargue el documento con ella.
                "lleva_aviso_legal": bool(e.aviso_legal),
            }
            for e in ESTANDARES.values()
        ],
        "estilos": [
            {"clave": s.clave, "nombre": s.nombre, "descripcion": s.descripcion}
            for s in ESTILOS.values()
        ],
    }
