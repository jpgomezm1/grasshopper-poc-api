"""Lee un logro de lo que el estudiante escribe, o de un diploma que sube.

AH, 2026-08-28: *"en mi perfil quiero que se puedan como subir logros, es decir
por ejemplo soy el capitán del equipo de fútbol, o sea que pueda ser en modo
conversacional o subiendo el PDF o la imagen del diploma"*.

## Lo que este módulo NO hace

**No guarda nada.** Devuelve una ficha para que la persona la revise; escribir
en `extracurricular_activities` es del endpoint de siempre (`POST
/me/activities`), después de que ella confirme. Un lector que además guarda es
un lector que mete datos inventados en la base la primera vez que se equivoca.

**No archiva el archivo.** Decisión de AH: se lee el PDF o la foto, se extrae
lo que dice, y los bytes se descartan. No es pereza — `STORAGE_BACKEND` está en
`stub` en producción y el stub guarda los blobs en un diccionario en memoria
del proceso (lo dice su propio docstring: *"NOT a substitute for the real
backend in any production-like environment"*). Prometer "tu diploma queda
guardado" y perderlo en el siguiente reinicio del dyno es peor que no ofrecerlo.

Si algún día se activa Supabase, archivar el original es un añadido encima de
esto, no un rediseño.

## Las dos entradas son la misma salida

    "soy el capitán del equipo de fútbol"  ─┐
                                            ├─→ texto ─→ Claude ─→ LogroLeido
    PDF o foto del diploma                 ─┘

Un PDF con capa de texto se lee con pdfplumber (barato); una foto, o un PDF
escaneado, van a Claude visión. Esa bifurcación ya existía para los tests
externos y vive en `document_parser` + `document_ai` — aquí sólo se usa.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.ai_client import load_prompt
from app.db.models import EXTRACURRICULAR_CATEGORIES
from app.services import document_ai
from app.services.document_parser import (
    DocumentParseError,
    extract_text_from_upload,
    is_image,
)

logger = logging.getLogger(__name__)

FEATURE = "leer_logro"

# Más allá de esto no es un diploma, es un libro · y el modelo se atraganta.
MAX_CARACTERES = 12000
# Un texto de dos palabras no da para leer nada y gasta una llamada.
MIN_CARACTERES = 8


class LectorError(RuntimeError):
    """No se pudo leer · el mensaje es para mostrárselo a la persona."""


@dataclass
class LogroLeido:
    """La ficha propuesta · NADA de esto se guarda hasta que la persona confirme."""

    encontrado: bool
    categoria: Optional[str] = None
    nombre: Optional[str] = None
    rol: Optional[str] = None
    horas_semana: Optional[int] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    descripcion: Optional[str] = None
    logros: List[str] = field(default_factory=list)
    confianza: float = 0.0
    # Lo que la app le va a preguntar después para completar la ficha.
    falta: List[str] = field(default_factory=list)
    usage: Optional[dict] = None


def _solo_json(texto: str) -> Dict[str, Any]:
    """El JSON del modelo, aunque venga envuelto.

    Se le pide que devuelva JSON pelado y casi siempre lo hace, pero de vez en
    cuando lo mete en ```json o le pone una frase delante. Fallar por eso sería
    tirar una respuesta buena.
    """
    t = (texto or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    ini, fin = t.find("{"), t.rfind("}")
    if ini != -1 and fin > ini:
        try:
            return json.loads(t[ini : fin + 1])
        except json.JSONDecodeError:
            pass
    raise LectorError("no pude entender lo que me mandaste · intenta de otra forma")


_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fecha(v: Any) -> Optional[str]:
    """Sólo fechas completas.

    El prompt ya lo pide, pero el modelo a veces manda "2024" o "2024-05". Una
    fecha a medias que el front convierta en 2024-01-01 es un dato inventado
    con apariencia de dato exacto — el tipo de cosa por la que este proyecto ya
    recibió un reclamo del cliente.
    """
    if isinstance(v, str) and _FECHA.match(v.strip()):
        return v.strip()
    return None


def _entero(v: Any, tope: int) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and 0 <= v <= tope:
        return int(v)
    return None


def _texto(v: Any, limite: int) -> Optional[str]:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s[:limite] if s else None


def _a_ficha(crudo: Dict[str, Any], usage: Optional[dict]) -> LogroLeido:
    """Valida campo por campo · lo que no encaje se descarta, no se corrige."""
    if not crudo.get("encontrado"):
        return LogroLeido(encontrado=False, usage=usage)

    categoria = crudo.get("categoria")
    if categoria not in EXTRACURRICULAR_CATEGORIES:
        # La lista es abierta en la base, pero si el modelo se inventa una
        # categoría el filtro de la UI deja de encontrarla. "other" es honesto.
        categoria = "other"

    nombre = _texto(crudo.get("nombre"), 120)
    if not nombre:
        # Sin nombre no hay actividad que guardar · vale más decir que no se
        # encontró que proponer una ficha a la que le falta lo esencial.
        return LogroLeido(encontrado=False, usage=usage)

    logros_crudos = crudo.get("logros")
    logros = [
        s.strip()[:200]
        for s in (logros_crudos if isinstance(logros_crudos, list) else [])
        if isinstance(s, str) and s.strip()
    ][:10]

    falta_crudo = crudo.get("falta")
    falta = [
        s.strip()[:120]
        for s in (falta_crudo if isinstance(falta_crudo, list) else [])
        if isinstance(s, str) and s.strip()
    ][:3]

    confianza = crudo.get("confianza")
    confianza = float(confianza) if isinstance(confianza, (int, float)) else 0.0
    confianza = max(0.0, min(1.0, confianza))

    return LogroLeido(
        encontrado=True,
        categoria=categoria,
        nombre=nombre,
        rol=_texto(crudo.get("rol"), 120),
        horas_semana=_entero(crudo.get("horas_semana"), 168),
        fecha_inicio=_fecha(crudo.get("fecha_inicio")),
        fecha_fin=_fecha(crudo.get("fecha_fin")),
        descripcion=_texto(crudo.get("descripcion"), 4000),
        logros=logros,
        confianza=confianza,
        falta=falta,
        usage=usage,
    )


def leer_de_texto(texto: str) -> LogroLeido:
    """Lo que la persona escribió, tal cual."""
    limpio = (texto or "").strip()
    if len(limpio) < MIN_CARACTERES:
        raise LectorError("cuéntame un poco más para poder armarlo")
    if len(limpio) > MAX_CARACTERES:
        limpio = limpio[:MAX_CARACTERES]

    prompt = load_prompt("leer_logro").replace("{texto}", limpio)
    respuesta, meta = document_ai.call_claude_text(prompt)
    return _a_ficha(_solo_json(respuesta), meta)


def leer_de_archivo(
    *,
    file_bytes: bytes,
    content_type: Optional[str],
    filename: Optional[str],
) -> LogroLeido:
    """Un diploma, constancia o certificado · PDF o imagen.

    Los bytes NO se guardan en ningún lado: se leen y se descartan. Ver el
    docstring del módulo.
    """
    try:
        texto, _meta_doc = extract_text_from_upload(file_bytes, content_type, filename)
    except DocumentParseError as exc:
        raise LectorError("no pude leer el archivo · prueba con una foto más nítida") from exc

    prompt_base = load_prompt("leer_logro")

    # Con capa de texto se manda el texto (barato). Sin ella —una foto, o un PDF
    # escaneado— va la imagen a visión, que es la única forma de leerlo.
    if texto and len(texto.strip()) >= MIN_CARACTERES:
        prompt = prompt_base.replace("{texto}", texto[:MAX_CARACTERES])
        respuesta, meta = document_ai.call_claude_text(prompt)
    elif is_image(content_type, filename):
        prompt = prompt_base.replace(
            "{texto}", "(el texto está en la imagen adjunta · léelo de ahí)"
        )
        respuesta, meta = document_ai.call_claude_vision(
            prompt, file_bytes, (content_type or "image/jpeg").lower()
        )
    else:
        # Un PDF sin capa de texto que no es imagen: no hay de dónde leer.
        raise LectorError(
            "ese PDF no tiene texto que pueda leer · súbelo como foto y lo intento"
        )

    return _a_ficha(_solo_json(respuesta), meta)
