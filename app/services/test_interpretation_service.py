"""P1-1 · Lectura narrativa del resultado de UN test, generada por IA.

Responde el reclamo #1 de la clienta (A1, 2026-07-28):

    "Cuando entro al resultado de los tests, le da muy poca información sobre su
    resultado al estudiante... la idea es que cada test pueda darle más información
    sobre él al estudiante Y SU FAMILIA."

Y en la reunión del 21-07:

    "Le salen como unas siglas y ya, pero no le explica: mira, eres analítico,
    entonces por eso te gustan estas cosas. Hay que darle qué significa ese test
    que hizo y qué significa eso para ti EN TU VIDA."

Qué NO es esto: el bloque que ya se pinta en la pantalla de resultados (P0-4) son
descripciones estáticas que ya vivían en el repo. Esto es una lectura del resultado
CONCRETO de esta persona, con sus puntajes y sus tensiones.

Caché: se guarda en `vocational_test_results.interpretation` junto con el hash de
los scores que la originaron. Si el estudiante repite el test, el hash deja de
coincidir y se regenera — si no, seguiría leyendo la lectura del resultado anterior.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_with_meta, load_prompt
from app.core.ai_json import parse_ai_json
from app.db.models import User, VocationalTestResult
from app.services.ai_usage_service import record_ai_usage
from app.services.scoring_service import (
    ISTRONG_BIS_INFO,
    ISTRONG_GOT_INFO,
    MOTIVADOR_INFO,
    VARK_INFO,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "interpret_test_v1"


class TestInterpretationUnavailable(Exception):
    """La interpretación no se pudo generar. El resultado del test se muestra igual."""


# ---------------------------------------------------------------------------
# Etiquetas legibles por dimensión
#
# ⚠️ DUPLICACIÓN CONOCIDA · Holland, Big Five, Valores y Anclas tienen sus etiquetas
# en el FRONT (`src/lib/types/vocationalTests.ts`) y no existían en el backend. El
# prompt se arma acá, así que hacen falta de este lado. Si alguien cambia una
# etiqueta allá, esto queda desfasado: hay un test que compara ambos conjuntos de
# claves para que la deriva se note. Unificarlo (una sola fuente servida por API)
# es trabajo aparte.
# ---------------------------------------------------------------------------

_HOLLAND = {
    "R": ("Realista", "Práctico, manual, orientado a hacer cosas concretas."),
    "I": ("Investigador", "Analítico, curioso, le gusta entender por qué."),
    "A": ("Artístico", "Creativo, expresivo, original."),
    "S": ("Social", "Colaborativo, disfruta ayudar y enseñar."),
    "E": ("Emprendedor", "Persuasivo, toma la iniciativa, orientado a resultados."),
    "C": ("Convencional", "Organizado, sistemático, atento al detalle."),
}

_BIGFIVE = {
    "O": ("Apertura", "Curiosidad e interés por ideas y experiencias nuevas."),
    "C": ("Responsabilidad", "Organización, disciplina y orientación a metas."),
    "E": ("Extraversión", "De dónde saca energía: de la gente o de la reflexión."),
    "A": ("Amabilidad", "Cooperación, empatía y consideración con otros."),
    # P0-3 · Reencuadre deliberado: no es un defecto ni un diagnóstico.
    "N": ("Sensibilidad emocional", "Con cuánta intensidad vive y registra las emociones."),
}

_VALUES = {
    "logro": ("Logro", "Alcanzar metas y ver resultados de lo que hace."),
    "independencia": ("Independencia", "Autonomía para decidir cómo trabajar."),
    "reconocimiento": ("Reconocimiento", "Que su aporte se note y se valore."),
    "relaciones": ("Relaciones", "Vínculos y trabajo con otras personas."),
    "apoyo": ("Apoyo", "Contar con guía y respaldo en el camino."),
    "condiciones": ("Condiciones", "Estabilidad y buenas condiciones de trabajo."),
}

_ANCHORS = {
    "TF": ("Competencia técnica", "Ser experto en un campo concreto."),
    "GM": ("Gestión general", "Coordinar personas y proyectos."),
    "AU": ("Autonomía", "Decidir cómo y cuándo trabajar."),
    "SE": ("Seguridad y estabilidad", "Previsibilidad y continuidad."),
    "EC": ("Creatividad emprendedora", "Crear algo propio."),
    "SV": ("Servicio a una causa", "Trabajar por algo que importa."),
    "CH": ("Puro desafío", "Resolver lo que parece imposible."),
    "LS": ("Estilo de vida", "Que el trabajo encaje con la vida que quiere."),
}

_MBTI_DIM = {
    "EI": ("Extraversión / Introversión", "De dónde saca la energía."),
    "SN": ("Sensorial / Intuitivo", "En qué se fija: hechos concretos o patrones."),
    "TF": ("Racional / Emocional", "Cómo decide: por lógica o por impacto en la gente."),
    "JP": ("Estructurado / Flexible", "Cómo organiza: cerrando o dejando abierto."),
}


def _label_map(test_id: str) -> Dict[str, tuple]:
    if test_id == "holland":
        return _HOLLAND
    if test_id == "bigfive":
        return _BIGFIVE
    if test_id == "values":
        return _VALUES
    if test_id == "career-anchors":
        return _ANCHORS
    if test_id == "mbti":
        return _MBTI_DIM
    if test_id == "istrong":
        combinado = {k: (v["name"], v["description"]) for k, v in ISTRONG_GOT_INFO.items()}
        combinado.update({k: (v["name"], "") for k, v in ISTRONG_BIS_INFO.items()})
        return combinado
    if test_id == "vark":
        return {k: (v.get("name", k), v.get("description", "")) for k, v in VARK_INFO.items()}
    if test_id == "motivadores":
        return {
            k: (v.get("name", k), v.get("description", "")) for k, v in MOTIVADOR_INFO.items()
        }
    return {}


def format_scores_block(test_id: str, scores: Dict[str, Any]) -> str:
    """Dimensiones ordenadas de mayor a menor, con nombre legible.

    Nunca se le pasa al modelo una sigla cruda: si no hay etiqueta conocida, se usa
    la clave tal cual pero queda registrado en el log — es señal de que falta un
    mapeo, no algo que deba llegarle al estudiante.
    """
    labels = _label_map(test_id)
    numericos = {k: v for k, v in (scores or {}).items() if isinstance(v, (int, float))}
    if not numericos:
        return "(sin puntajes numéricos)"

    filas: List[str] = []
    desconocidas: List[str] = []
    for clave, valor in sorted(numericos.items(), key=lambda kv: kv[1], reverse=True):
        etiqueta, descripcion = labels.get(clave, (clave, ""))
        if clave not in labels:
            desconocidas.append(clave)
        linea = f"- {etiqueta}: {round(float(valor))}"
        if descripcion:
            linea += f" · {descripcion}"
        filas.append(linea)

    if desconocidas:
        logger.warning(
            "Dimensiones sin etiqueta legible en interpret_test",
            extra={"test_id": test_id, "dimensiones": desconocidas},
        )
    return "\n".join(filas)


def _student_context(user: Optional[User]) -> str:
    """Lo que la persona contó de sí misma, para aterrizar los ejemplos.

    Reutiliza el mismo bloque que ya reciben los demás prompts (P1-3) en vez de
    armar otro formato distinto.
    """
    if user is None:
        return "(sin contexto adicional)"
    from app.services.ai_service import format_onboarding_context

    return format_onboarding_context(user.onboarding_answers)


def scores_hash(scores: Dict[str, Any]) -> str:
    canonical = json.dumps(scores or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(f"{PROMPT_VERSION}|{canonical}".encode("utf-8")).hexdigest()


def get_cached(result: VocationalTestResult) -> Optional[Dict[str, Any]]:
    """Interpretación vigente, o None si no hay o quedó obsoleta.

    Obsoleta = el estudiante repitió el test y los scores cambiaron.
    """
    if not result.interpretation or not result.interpretation_hash:
        return None
    if result.interpretation_hash != scores_hash(result.scores):
        return None
    return result.interpretation


def generate(
    db: DBSession,
    result: VocationalTestResult,
    test_name: str,
    test_description: str,
    user: Optional[User] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Genera (o devuelve de caché) la lectura del resultado."""
    if not force:
        cacheada = get_cached(result)
        if cacheada is not None:
            return cacheada

    prompt = load_prompt("interpret_test").format(
        test_name=test_name,
        test_description=test_description or "(sin descripción)",
        scores_block=format_scores_block(result.test_id, result.scores),
        student_context=_student_context(user),
    )

    try:
        raw, meta = call_claude_with_meta(
            prompt,
            session_id=str(result.user_id),
            feature="test_interpretation",
            max_tokens=2000,
            temperature=0.4,
            prompt_version=PROMPT_VERSION,
        )
    except Exception as exc:
        logger.warning(
            "Interpretación de test no disponible",
            extra={"test_id": result.test_id, "error": str(exc)[:200]},
        )
        raise TestInterpretationUnavailable(str(exc)) from exc

    try:
        data = parse_ai_json(raw)
    except Exception as exc:
        logger.warning(
            "Interpretación de test con JSON inválido",
            extra={"test_id": result.test_id, "error": str(exc)[:200]},
        )
        raise TestInterpretationUnavailable("Respuesta con formato inesperado.") from exc

    if not isinstance(data, dict) or not data.get("summary"):
        raise TestInterpretationUnavailable("Respuesta incompleta.")

    result.interpretation = data
    result.interpretation_hash = scores_hash(result.scores)
    result.interpretation_generated_at = datetime.utcnow()
    db.commit()

    # M-001 · el tracking de costos nunca puede tumbar la respuesta.
    try:
        record_ai_usage(
            db,
            provider="anthropic",
            model=meta.get("model"),
            feature="test_interpretation",
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
            user_id=result.user_id,
        )
    except Exception:
        pass

    return data
