"""La ruta del adulto profesional · análisis de brecha contra el "puesto ideal".

Compara el perfil profesional de la persona (estructurado a partir de su
LinkedIn con `linkedin_import_service`, que YA EXISTE y no se reescribe aquí)
contra el cargo al que le gustaría llegar, y devuelve:

  * `fortalezas_alineadas` · qué de lo que ya tiene encaja con ese puesto.
  * `brechas`               · qué le falta y qué tan bloqueante es.
  * `plan_upskilling`       · con qué cerrar cada brecha.

## Por qué NO inventa salario ni demanda de mercado

Se pidió explícitamente ser honestos: "no inventes datos de salarios ni de
demanda de mercado que no tengamos [...] ya hubo un reclamo del cliente por
contenido inventado por nosotros" (instrucción de la tarea, 2026-08-24). Igual
que `cv_tailor_service` separa lo inventable de lo real con una garantía
ESTRUCTURAL (los faltantes van en su propio campo, nunca en el CV), aquí la
garantía no depende de que el modelo obedezca el prompt:

1. El prompt (`app/prompts/career_gap_analysis.txt`) lo prohíbe explícitamente.
2. `_redactar_cifras()` escanea TODO texto libre que devuelve el modelo y
   redacta cualquier cifra con forma de dinero o de porcentaje antes de que
   llegue a la persona — así el modelo no puede colar un "$3.5M" o un "40% de
   demanda" ni por accidente.
3. `disclaimer` es un texto FIJO que pone este módulo, no el modelo. Nunca
   depende de que Claude decida mencionarlo.

## Qué NO hace este módulo

No decide QUIÉN puede usar esta ruta (eso lo filtra el router, con
`onboarding_hechos.perfil()` — lectura, no edición, de ese archivo). No
persiste nada — recibe datos ya leídos y devuelve el resultado; quien llama
decide dónde guardarlo (ver `app/api/v1/career_gap.py`, que lo guarda en
`user.onboarding_answers`, igual que `study_preferences.py`: no hay migración
para esto y no hace falta una).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CareerGapError(RuntimeError):
    """No se pudo hacer el análisis de brecha."""


DISCLAIMER = (
    "Este análisis compara tu perfil con el puesto que describiste, a partir "
    "de lo que nos contaste. No incluye cifras de salario ni de demanda "
    "laboral: no tenemos esa información conectada todavía. Para eso, lo "
    "mejor es consultar fuentes de mercado actualizadas."
)

MIN_TARGET_ROLE_CHARS = 4
MAX_TARGET_ROLE_CHARS = 200

# ---------------------------------------------------------------------------
# Red de seguridad anti-invención · ver docstring del módulo, punto 2.
# ---------------------------------------------------------------------------
_RE_DINERO = re.compile(
    r"(?:\$\s?\d[\d.,]*\s?(?:k|mil|millones|m)?)"
    r"|(?:\b(?:USD|COP|EUR|GBP)\s?\d[\d.,]*\b)"
    r"|(?:\b\d[\d.,]*\s?(?:USD|COP|EUR|GBP)\b)",
    re.IGNORECASE,
)
_RE_PORCENTAJE = re.compile(r"\b\d{1,3}(?:[.,]\d+)?\s?%")


def _redactar_cifras(texto: Optional[str]) -> Optional[str]:
    """Quita cualquier cifra con forma de dinero o de porcentaje.

    No intenta distinguir una cifra "real" de una inventada — no hay forma de
    saberlo desde aquí. La postura es la más segura: ninguna cifra de este
    tipo puede venir del modelo, punto. Si algún día se conecta una fuente de
    mercado de verdad, esas cifras se inyectan en Python, no se le piden al
    modelo que las redacte él solo.
    """
    if not texto:
        return texto
    limpio = _RE_DINERO.sub("[cifra no disponible]", texto)
    limpio = _RE_PORCENTAJE.sub("[dato no disponible]", limpio)
    return limpio


ESQUEMA_BRECHA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string", "description": "2-4 frases, sin cifras inventadas."},
        "fortalezas_alineadas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Hasta 6 · lo que YA tiene y encaja con el puesto ideal.",
        },
        "brechas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "area": {"type": "string"},
                    "descripcion": {"type": "string"},
                    "impacto": {"type": "string", "enum": ["alto", "medio", "bajo"]},
                },
                "required": ["area"],
            },
        },
        "plan_upskilling": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "brecha": {"type": "string"},
                    "como_cerrarla": {"type": "string"},
                    "tipo": {
                        "type": "string",
                        "enum": ["curso", "certificacion", "practica", "proyecto", "mentoria"],
                    },
                    "prioridad": {"type": "string", "enum": ["alta", "media", "baja"]},
                },
                "required": ["brecha", "como_cerrarla"],
            },
        },
    },
    "required": ["resumen", "brechas", "plan_upskilling"],
}


def _texto(valor: Any, limite: int) -> Optional[str]:
    if valor is None:
        return None
    limpio = str(valor).strip()
    if not limpio:
        return None
    return _redactar_cifras(limpio)[:limite]


def _lista_texto(valor: Any, max_items: int, limite: int) -> List[str]:
    if not isinstance(valor, list):
        return []
    salida: List[str] = []
    for item in valor:
        t = _texto(item, limite)
        if t:
            salida.append(t)
    return salida[:max_items]


_IMPACTOS_VALIDOS = {"alto", "medio", "bajo"}
_TIPOS_VALIDOS = {"curso", "certificacion", "practica", "proyecto", "mentoria"}
_PRIORIDADES_VALIDAS = {"alta", "media", "baja"}


def _brechas(valor: Any) -> List[Dict[str, Optional[str]]]:
    if not isinstance(valor, list):
        return []
    salida = []
    for item in valor:
        if not isinstance(item, dict):
            texto = _texto(item, 200)
            if texto:
                salida.append({"area": texto, "descripcion": None, "impacto": None})
            continue
        area = _texto(item.get("area"), 120)
        if not area:
            continue
        impacto = item.get("impacto")
        impacto = impacto if impacto in _IMPACTOS_VALIDOS else None
        salida.append(
            {
                "area": area,
                "descripcion": _texto(item.get("descripcion"), 400),
                "impacto": impacto,
            }
        )
    return salida[:6]


def _plan_upskilling(valor: Any) -> List[Dict[str, Optional[str]]]:
    if not isinstance(valor, list):
        return []
    salida = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        como = _texto(item.get("como_cerrarla"), 400)
        if not como:
            continue
        tipo = item.get("tipo")
        tipo = tipo if tipo in _TIPOS_VALIDOS else None
        prioridad = item.get("prioridad")
        prioridad = prioridad if prioridad in _PRIORIDADES_VALIDAS else None
        salida.append(
            {
                "brecha": _texto(item.get("brecha"), 120),
                "como_cerrarla": como,
                "tipo": tipo,
                "prioridad": prioridad,
            }
        )
    return salida[:6]


def normalizar(bruto: Dict[str, Any]) -> Dict[str, Any]:
    """Acota y limpia lo que devolvió el modelo · nunca se confía en crudo.

    `disclaimer` se pone SIEMPRE aquí, no se lee de `bruto`: es la garantía
    estructural del punto 3 del docstring del módulo.
    """
    return {
        "resumen": _texto(bruto.get("resumen"), 800),
        "fortalezas_alineadas": _lista_texto(bruto.get("fortalezas_alineadas"), 6, 200),
        "brechas": _brechas(bruto.get("brechas")),
        "plan_upskilling": _plan_upskilling(bruto.get("plan_upskilling")),
        "disclaimer": DISCLAIMER,
    }


def describir_perfil_actual(
    perfil_linkedin: Optional[Dict[str, Any]],
    *,
    current_role: Optional[str] = None,
    job_satisfaction_score: Optional[int] = None,
    job_satisfaction_text: Optional[str] = None,
) -> str:
    """Serializa el perfil a texto plano para el prompt · no a JSON.

    Mismo motivo que `cv_tailor_service.describir_cv`: el modelo tiene que
    razonar sobre el contenido, no reordenar una estructura.
    """
    perfil_linkedin = perfil_linkedin or {}
    lineas: List[str] = []

    if current_role:
        lineas.append(f"Cargo actual (autoreportado): {current_role}")
    if job_satisfaction_score is not None:
        lineas.append(
            f"Satisfacción actual con su trabajo (1-5): {job_satisfaction_score}"
        )
    if job_satisfaction_text:
        lineas.append(f"Por qué se siente así: {job_satisfaction_text}")

    if perfil_linkedin.get("headline"):
        lineas.append(f"Titular de LinkedIn: {perfil_linkedin['headline']}")
    if perfil_linkedin.get("summary"):
        lineas.append(f"Resumen de perfil:\n{perfil_linkedin['summary']}")

    fortalezas = perfil_linkedin.get("strengths") or []
    if fortalezas:
        lineas.append(f"Fortalezas (de su LinkedIn): {', '.join(fortalezas)}")

    intereses = perfil_linkedin.get("interests") or []
    if intereses:
        lineas.append(f"Áreas de interés: {', '.join(intereses)}")

    experiencia = perfil_linkedin.get("experience") or []
    if experiencia:
        lineas.append("\nExperiencia (de más reciente a más antigua):")
        for e in experiencia:
            trozo = e.get("role") or "(sin cargo)"
            if e.get("organization"):
                trozo += f" en {e['organization']}"
            if e.get("period"):
                trozo += f" ({e['period']})"
            lineas.append(f"  - {trozo}")
    else:
        # Decirlo explícito para que el modelo no asuma que faltó pasarla y
        # se la invente — mismo patrón que `cv_tailor_service`.
        lineas.append("\nExperiencia: ninguna registrada en el perfil de LinkedIn.")

    educacion = perfil_linkedin.get("education") or []
    if educacion:
        lineas.append("\nEducación:")
        for e in educacion:
            trozo = e.get("title") or "(sin título)"
            if e.get("institution"):
                trozo += f" — {e['institution']}"
            if e.get("period"):
                trozo += f" ({e['period']})"
            lineas.append(f"  - {trozo}")

    if not lineas:
        lineas.append("(no hay datos de perfil todavía)")

    return "\n".join(lineas)


def analizar(
    *,
    perfil_linkedin: Optional[Dict[str, Any]],
    target_role: str,
    current_role: Optional[str] = None,
    job_satisfaction_score: Optional[int] = None,
    job_satisfaction_text: Optional[str] = None,
    session_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Compara el perfil contra el puesto ideal. Devuelve ``(analisis, meta_ia)``.

    ``target_role`` es obligatorio y se valida ANTES de llamar al modelo — sin
    él no hay nada que comparar, y no vale la pena gastar la llamada.
    """
    objetivo = (target_role or "").strip()
    if len(objetivo) < MIN_TARGET_ROLE_CHARS:
        raise CareerGapError(
            "Cuéntanos con un poco más de detalle cuál es tu puesto ideal."
        )
    objetivo = objetivo[:MAX_TARGET_ROLE_CHARS]

    from app.core.ai_client import call_claude_tool, load_prompt

    prompt = load_prompt("career_gap_analysis").format(
        perfil_actual=describir_perfil_actual(
            perfil_linkedin,
            current_role=current_role,
            job_satisfaction_score=job_satisfaction_score,
            job_satisfaction_text=job_satisfaction_text,
        ),
        puesto_ideal=objetivo,
    )

    datos, meta = call_claude_tool(
        prompt,
        tool_name="analizar_brecha_de_carrera",
        tool_description=(
            "Compara el perfil profesional actual contra el puesto ideal y "
            "devuelve fortalezas alineadas, brechas y un plan de upskilling, "
            "sin inventar cifras de salario ni de demanda laboral."
        ),
        input_schema=ESQUEMA_BRECHA,
        session_id=session_id,
        feature="career_gap_analysis",
        max_tokens=2500,
        temperature=0.2,
    )

    if not datos:
        raise CareerGapError(
            "No pude hacer tu análisis de brecha en este momento. Intenta de nuevo."
        )

    return normalizar(datos), meta
