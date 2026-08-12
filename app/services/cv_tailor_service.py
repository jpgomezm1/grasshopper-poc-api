"""Adaptar el CV a una convocatoria y decir qué falta · paso 2.

Toma lo que `cv_target_service` entendió de la convocatoria y la hoja de vida
real del estudiante, y devuelve dos cosas:

  * una **propuesta** de CV adaptado, con forma de `overrides`;
  * los **faltantes** — lo que la convocatoria pide y él hoy no tiene.

De las dos, la que más se va a sentir es la segunda. Un estudiante de colegio no
tiene forma de saber si su hoja de vida está bien; esto se lo dice antes de que
lo descubra por un rechazo.

## Dos cosas que no son negociables

**No inventa experiencia.** El prompt lo prohíbe y `normalizar()` lo acota, pero
la garantía estructural es otra: los faltantes van en su propio campo, separados
del CV. Si el modelo se inventa un curso, aparece como algo que le FALTA, no como
algo que tiene.

**No escribe.** Devuelve una propuesta que el estudiante aplica si quiere, igual
que `linkedin_import_service`: *"es la hoja de vida de la persona y lleva su
nombre"*. `a_overrides()` la traduce a los campos que ya entiende
`cv_profile_service`, y nada se guarda hasta que él lo confirme.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CVTailorError(RuntimeError):
    """No se pudo adaptar la hoja de vida."""


ESQUEMA_ADAPTACION: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "Una línea, máx 120 caracteres."},
        "summary": {"type": "string", "description": "2-4 frases en primera persona."},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "interests": {"type": "array", "items": {"type": "string"}},
        "destacar_actividades": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Nombres EXACTOS de actividades suyas que más sirven aquí.",
        },
        "ajuste": {
            "type": "integer",
            "description": "0-100 · qué tan bien encaja hoy, sin inflar.",
        },
        "resumen_ajuste": {"type": "string"},
        "faltantes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "que": {"type": "string"},
                    "por_que": {"type": "string"},
                    "como_resolverlo": {"type": "string"},
                },
                "required": ["que"],
            },
        },
        "sugerencias": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ajuste", "faltantes"],
}


def _texto(valor: Any, limite: int) -> Optional[str]:
    if valor is None:
        return None
    limpio = str(valor).strip()
    return limpio[:limite] if limpio else None


def _lista(valor: Any, max_items: int, limite: int) -> List[str]:
    if not isinstance(valor, list):
        return []
    salida: List[str] = []
    for item in valor:
        t = _texto(item, limite)
        if t:
            salida.append(t)
    return salida[:max_items]


def _faltantes(valor: Any) -> List[Dict[str, Optional[str]]]:
    if not isinstance(valor, list):
        return []
    salida = []
    for item in valor:
        if not isinstance(item, dict):
            # Un modelo puede devolver la lista como strings sueltos. Se acepta
            # en vez de descartarlo: el `que` es lo único imprescindible.
            texto = _texto(item, 240)
            if texto:
                salida.append({"que": texto, "por_que": None, "como_resolverlo": None})
            continue
        que = _texto(item.get("que"), 240)
        if not que:
            continue
        salida.append(
            {
                "que": que,
                "por_que": _texto(item.get("por_que"), 300),
                "como_resolverlo": _texto(item.get("como_resolverlo"), 300),
            }
        )
    return salida[:6]


def normalizar(bruto: Dict[str, Any]) -> Dict[str, Any]:
    """Acota lo que devolvió el modelo · nunca se confía en crudo."""
    ajuste = bruto.get("ajuste")
    try:
        ajuste = int(ajuste)
    except (TypeError, ValueError):
        ajuste = None
    if ajuste is not None:
        # Un 130 o un -5 llegan a una barra de progreso en pantalla.
        ajuste = max(0, min(100, ajuste))

    return {
        "headline": _texto(bruto.get("headline"), 120),
        "summary": _texto(bruto.get("summary"), 2000),
        "strengths": _lista(bruto.get("strengths"), 6, 100),
        "interests": _lista(bruto.get("interests"), 6, 100),
        "destacar_actividades": _lista(bruto.get("destacar_actividades"), 4, 200),
        "ajuste": ajuste,
        "resumen_ajuste": _texto(bruto.get("resumen_ajuste"), 400),
        "faltantes": _faltantes(bruto.get("faltantes")),
        "sugerencias": _lista(bruto.get("sugerencias"), 4, 300),
    }


def describir_cv(cv: Any) -> str:
    """Serializa el `CVData` a texto plano para metérselo al prompt.

    Se manda texto y no JSON a propósito: el modelo tiene que razonar sobre el
    contenido, no sobre la estructura, y un JSON invita a devolver el mismo JSON
    con los campos movidos de sitio.
    """
    lineas: List[str] = [f"Nombre: {getattr(cv, 'student_name', '') or '—'}"]

    for etiqueta, atributo in (
        ("Ocupación actual", "current_occupation"),
        ("Colegio", "school_name"),
        ("Grado", "grade"),
        ("Nivel de inglés", "english_level"),
        ("Titular actual", "headline"),
    ):
        valor = getattr(cv, atributo, None)
        if valor:
            lineas.append(f"{etiqueta}: {valor}")

    if getattr(cv, "summary", None):
        lineas.append(f"\nPerfil:\n{cv.summary}")

    for etiqueta, atributo in (
        ("Fortalezas", "strengths"),
        ("Áreas de interés", "interests"),
        ("Valores", "values"),
        ("Caminos que le interesan", "career_paths"),
    ):
        valores = getattr(cv, atributo, None) or []
        if valores:
            lineas.append(f"{etiqueta}: {', '.join(str(v) for v in valores)}")

    highlights = getattr(cv, "test_highlights", None) or []
    if highlights:
        lineas.append("\nResultados de tests:")
        for fila in highlights:
            lineas.append(f"  - {fila[0]}: {fila[1]}")

    actividades = getattr(cv, "activities", None) or []
    if actividades:
        lineas.append("\nActividades:")
        for a in actividades:
            partes = [f"  - {a.name} ({a.category_label})"]
            if getattr(a, "role", None):
                partes.append(f"rol: {a.role}")
            if getattr(a, "period", None):
                partes.append(a.period)
            if getattr(a, "hours_per_week", None):
                partes.append(f"{a.hours_per_week} h/sem")
            lineas.append(" · ".join(partes))
            if getattr(a, "description", None):
                lineas.append(f"      {a.description}")
            for logro in (getattr(a, "achievements", None) or []):
                lineas.append(f"      · {logro}")
    else:
        # Decirlo explícitamente importa: si no, el modelo asume que se le
        # olvidó pasarlas y se las inventa.
        lineas.append("\nActividades: ninguna registrada todavía.")

    return "\n".join(lineas)


def describir_convocatoria(parsed: Dict[str, Any]) -> str:
    """Serializa lo que `cv_target_service` entendió, para el prompt."""
    lineas: List[str] = []
    if parsed.get("title"):
        lineas.append(f"Título: {parsed['title']}")
    if parsed.get("organization"):
        lineas.append(f"Organización: {parsed['organization']}")
    if parsed.get("kind"):
        lineas.append(f"Tipo: {parsed['kind']}")
    if parsed.get("resumen"):
        lineas.append(f"De qué se trata: {parsed['resumen']}")

    for etiqueta, clave in (
        ("Requisitos (obligatorios)", "requisitos"),
        ("Deseables", "deseables"),
        ("Habilidades que pide", "habilidades"),
        ("Idiomas", "idiomas"),
    ):
        valores = parsed.get(clave) or []
        if valores:
            lineas.append(f"\n{etiqueta}:")
            lineas.extend(f"  - {v}" for v in valores)

    if parsed.get("fechas"):
        lineas.append(f"\nFechas: {parsed['fechas']}")

    return "\n".join(lineas) or "(no se pudo interpretar la convocatoria)"


def adaptar(
    *, cv: Any, parsed: Dict[str, Any], session_id: str
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Adapta y revisa. Devuelve ``(adaptacion, metadata_de_ia)``."""
    from app.core.ai_client import call_claude_tool, load_prompt

    prompt = load_prompt("cv_tailor").format(
        convocatoria=describir_convocatoria(parsed),
        hoja_de_vida=describir_cv(cv),
    )

    datos, meta = call_claude_tool(
        prompt,
        tool_name="adaptar_hoja_de_vida",
        tool_description=(
            "Devuelve la hoja de vida adaptada a la convocatoria y lo que le "
            "falta al candidato, sin inventar experiencia."
        ),
        input_schema=ESQUEMA_ADAPTACION,
        session_id=session_id,
        feature="cv_tailor",
        max_tokens=3000,
        temperature=0.2,
    )

    if not datos:
        raise CVTailorError(
            "No pude adaptar tu hoja de vida en este momento. Intenta de nuevo."
        )

    return normalizar(datos), meta


def a_overrides(adaptacion: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce la propuesta a los campos que entiende `cv_profile_service`.

    Sólo se emiten las cuatro claves editables que ese servicio acepta
    (`headline`, `summary`, `strengths`, `interests`). `destacar_actividades` no
    se traduce a `excluded_activity_ids`: destacar no es lo mismo que **quitar**,
    y borrar del CV una actividad que el estudiante registró porque un modelo la
    consideró poco relevante es una decisión suya, no nuestra.

    `values` y `career_paths` tampoco se tocan — son suyos y no dependen de a
    dónde se postule.
    """
    overrides: Dict[str, Any] = {}
    for clave in ("headline", "summary", "strengths", "interests"):
        valor = adaptacion.get(clave)
        if valor:
            overrides[clave] = valor
    return overrides
