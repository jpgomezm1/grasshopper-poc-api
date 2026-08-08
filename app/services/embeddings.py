"""Embeddings · la frontera con el proveedor de vectores.

Un solo sitio habla con el modelo de embeddings. El resto del código pide
vectores a estas funciones y no sabe de qué proveedor vienen — que es lo que
permite mockear **la frontera** en los tests en vez de la función que se está
probando (ver `backend/CLAUDE.md`, el segundo error que más se repite aquí).

Modelo: `text-embedding-3-small`, 1536 dimensiones, fijadas en la migración 059.
Cambiar de modelo cambia la dimensión y obliga a regenerar los 15.483 vectores,
así que no es un parámetro de configuración: es una decisión con migración.
"""
from __future__ import annotations

import logging
from typing import List, Sequence

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

MODELO = "text-embedding-3-small"
DIMENSIONES = 1536

# La API acepta lotes; 256 textos por llamada mantiene la petición bien lejos del
# límite de tokens y hace que un fallo cueste poco trabajo repetido.
TAMANO_LOTE = 256


def _cliente() -> AsyncOpenAI:
    s = get_settings()
    if not s.openai_api_key:
        raise RuntimeError("falta OPENAI_API_KEY · no se pueden generar embeddings")
    return AsyncOpenAI(api_key=s.openai_api_key)


async def embeber(textos: Sequence[str]) -> List[List[float]]:
    """Vectores para una lista de textos, en el mismo orden.

    Devuelve exactamente tantos vectores como textos recibió. Si el proveedor
    devolviera menos, es un error y se levanta: rellenar con ceros metería
    programas que "se parecen a todo" en cada búsqueda.
    """
    if not textos:
        return []
    cliente = _cliente()
    fuera: List[List[float]] = []
    for i in range(0, len(textos), TAMANO_LOTE):
        trozo = list(textos[i:i + TAMANO_LOTE])
        # La API rechaza cadenas vacías · se sustituyen por un espacio para no
        # desalinear el orden de la respuesta con el de la entrada.
        trozo = [t if (t or "").strip() else " " for t in trozo]
        r = await cliente.embeddings.create(model=MODELO, input=trozo)
        if len(r.data) != len(trozo):
            raise RuntimeError(
                f"el proveedor devolvió {len(r.data)} vectores para {len(trozo)} textos"
            )
        fuera.extend(d.embedding for d in sorted(r.data, key=lambda d: d.index))
    return fuera


async def embeber_uno(texto: str) -> List[float]:
    return (await embeber([texto]))[0]


def texto_de_programa(p) -> str:
    """El texto que representa a un programa en el espacio vectorial.

    Se incluyen área y nivel además del nombre porque **el nombre solo no
    distingue**: "Foundation Year" o "General English" aparecen idénticos en
    decenas de instituciones, y sin el área un curso de inglés de una escuela de
    diseño y uno de una de negocios producen el mismo vector.

    No se incluye el país: el país es un filtro duro que resuelve SQL. Meterlo
    aquí haría que "quiero estudiar en Canadá" empuje por parecido de texto
    programas que no están en Canadá.
    """
    partes = [p.nombre or ""]
    if p.area:
        partes.append(f"Área de estudio: {p.area}")
    if p.nivel:
        partes.append(f"Nivel: {p.nivel}")
    if p.institucion:
        partes.append(f"Institución: {p.institucion}")
    return ". ".join(x for x in partes if x)


def texto_de_institucion(p) -> str:
    """El texto que representa a una ficha del catálogo autorizado (`programs`).

    Es más pobre que el de un programa investigado y no hay nada que hacer: las
    2.511 fichas del cliente están a nivel institución (`name` es igual a
    `institution`), el `area` está vacío en el 98% y lo único que suele haber es
    `subject`, que trae lo que la agencia está autorizada a vender ahí
    ("Idiomas", "Vocacionales (Cert, Dip, Adv Dip)").

    Por eso se incluye el país: aquí sí aporta señal, porque sin área ni
    descripción el nombre solo no distingue casi nada. En los programas
    investigados se excluye a propósito —allá el país es filtro duro y meterlo
    ensuciaría el parecido—, y esa asimetría es deliberada.
    """
    partes = [p.name or ""]
    if getattr(p, "subject", None):
        partes.append(f"Ofrece: {p.subject}")
    if getattr(p, "area", None):
        partes.append(f"Área de estudio: {p.area}")
    if getattr(p, "type", None):
        partes.append(f"Nivel: {p.type}")
    if getattr(p, "country", None):
        partes.append(f"País: {p.country}")
    return ". ".join(x for x in partes if x)


def texto_de_perfil(
    intereses: Sequence[str] = (),
    rutas: Sequence[str] = (),
    areas_afines: Sequence[str] = (),
    en_sus_palabras: str = "",
) -> str:
    """El texto que representa a un estudiante en el mismo espacio.

    Va deliberadamente en el mismo registro que `texto_de_programa` —frases
    cortas, "Área de estudio: X"— porque dos textos escritos de forma parecida se
    comparan mejor que un párrafo libre contra una ficha telegráfica.

    `en_sus_palabras` es lo que la persona dijo en el journey. Es lo que ninguna
    taxonomía captura ("me gustan los animales pero también dibujar") y por eso
    va primero: es la señal más rica que tenemos.
    """
    partes = []
    if en_sus_palabras.strip():
        partes.append(en_sus_palabras.strip())
    if areas_afines:
        partes.append("Área de estudio: " + ", ".join(areas_afines))
    if intereses:
        partes.append("Intereses: " + ", ".join(intereses))
    if rutas:
        partes.append("Rutas profesionales que le interesan: " + ", ".join(rutas))
    return ". ".join(partes)
