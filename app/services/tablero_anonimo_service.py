"""El tablero agregado y anónimo de una organización · F-2 / F-4, Sprint 4.

Para un programa estatal es el "tablero de política pública" del demo; para una
empresa, la vista de RR. HH.; para un colegio, una vista más (agregada) además
de las que ya tiene. Indicadores mínimos y genéricos a propósito: los que
quiera cada cliente concreto se definen con él (F-2 y F-4 se construyeron como
base, sin cliente real todavía).

## Ningún grupo pequeño

Un conteo de "1 persona de 12° interesada en Alemania" identifica a alguien.
Por eso:

- Con menos de `MINIMO` participantes no se muestra ningún desglose.
- En cada desglose, las categorías con menos de `MINIMO` personas se juntan en
  "Otros"; si "Otros" también queda por debajo, no se muestra.
- Nunca sale un nombre, un correo ni un id.

Sin cifras inventadas: todo sale de lo que cada persona respondió o hizo.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

MINIMO = 5

NOMBRE_TRAMO = {
    "grado_9": "9°",
    "grado_10": "10°",
    "grado_11": "11°",
    "grado_12": "12°",
    "profesional": "Profesional",
    None: "Sin dato",
}
NOMBRE_RIASEC = {
    "R": "Realista (hacer y construir)",
    "I": "Investigador",
    "A": "Artístico",
    "S": "Social",
    "E": "Emprendedor",
    "C": "Convencional (organizar)",
}
NOMBRE_DESTINO = {
    "intl_yes": "En el exterior",
    "intl_maybe": "Todavía no sabe",
    "intl_no": "En Colombia",
    None: "Sin dato",
}

NOTA = (
    "Solo cifras agregadas. Para proteger a cada participante, los grupos de "
    f"menos de {MINIMO} personas se juntan en «Otros» o no se muestran."
)


def _desglose(conteo: Counter, nombres: Dict[Any, str]) -> List[Dict[str, Any]]:
    filas: List[Dict[str, Any]] = []
    otros = 0
    for clave, n in conteo.most_common():
        if n >= MINIMO:
            filas.append({"categoria": nombres.get(clave, str(clave)), "personas": n})
        else:
            otros += n
    if otros >= MINIMO:
        filas.append({"categoria": "Otros", "personas": otros})
    return filas


def _letra_dominante(scores: Any) -> Optional[str]:
    """La letra RIASEC más alta · mismo criterio que `school_panel_service`."""
    if not isinstance(scores, dict):
        return None
    codigo = scores.get("holland_code")
    if isinstance(codigo, str) and codigo[:1].upper() in NOMBRE_RIASEC:
        return codigo[:1].upper()
    letras = [k for k in NOMBRE_RIASEC if k in scores]
    if not letras:
        return None
    try:
        return max(letras, key=lambda k: float(scores.get(k) or 0))
    except (TypeError, ValueError):
        return None


def armar(db: Any, school: Any) -> Dict[str, Any]:
    from app.db.models import OnboardingStatus, User, UserRole, VocationalTestResult
    from app.services import permisos_service

    personas = (
        db.query(User)
        .filter(User.school_id == school.id, User.role == UserRole.STUDENT, User.is_active.is_(True))
        .all()
    )
    total = len(personas)
    base: Dict[str, Any] = {
        "tipo": getattr(school, "tipo", None) or "colegio",
        "participantes": total,
        "minimo": MINIMO,
        "nota": NOTA,
    }
    if total < MINIMO:
        return {**base, "suficientes": False}

    ids = [p.id for p in personas]
    con_onboarding = sum(1 for p in personas if p.onboarding_status == OnboardingStatus.COMPLETED)
    resultados = (
        db.query(VocationalTestResult.user_id, VocationalTestResult.test_id, VocationalTestResult.scores)
        .filter(VocationalTestResult.user_id.in_(ids))
        .all()
    )
    con_tests = len({u for u, _, _ in resultados})

    letra_por_persona: Dict[Any, str] = {}
    for user_id, test_id, scores in resultados:
        if test_id in ("holland", "riasec", "istrong"):
            letra = _letra_dominante(scores)
            if letra:
                letra_por_persona[user_id] = letra

    def respuesta(p, clave):
        r = p.onboarding_answers or {}
        return r.get(clave) if isinstance(r, dict) else None

    return {
        **base,
        "suficientes": True,
        "avance": {
            "completaron_la_conversacion_inicial": con_onboarding,
            "hicieron_al_menos_un_test": con_tests,
            "midieron_su_ingles": sum(1 for p in personas if p.english_test_completed),
        },
        "por_etapa": _desglose(Counter(permisos_service.tramo_de(p) for p in personas), NOMBRE_TRAMO),
        "intereses": _desglose(Counter(letra_por_persona.values()), NOMBRE_RIASEC),
        "destino": _desglose(Counter(respuesta(p, "international_interest") for p in personas), NOMBRE_DESTINO),
        "ingles": _desglose(
            Counter((p.english_cefr_level or "").upper() or None for p in personas if p.english_test_completed),
            {None: "Sin dato"},
        ),
    }
