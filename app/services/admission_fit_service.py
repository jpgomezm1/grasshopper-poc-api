"""Clasificación Reach / Match / Safety · D-002 (2026-06-04).

Categoriza qué tan alcanzable es un programa para un estudiante:
  - reach  · exigente / aspiracional
  - match  · en su nivel
  - safety · muy alcanzable

Regla determinista (no IA), basada en las variables de admisión del programa
(`acceptance_rate`, `avg_admitted_gpa`, `min_sat`, `avg_sat`) y, si están
disponibles, las métricas del estudiante (GPA/SAT).

ESTADO DE DATOS (2026-06-04):
- Hoy NO existen métricas académicas del estudiante (GPA/SAT) en el modelo → la
  clasificación cae al **fallback por selectividad del programa** (acceptance_rate).
- Los campos de admisión del programa están NULL en el catálogo real → hay que
  curarlos (admin) para que aparezca el badge. Si no hay datos → None (sin badge).

Umbrales por defecto (TUNABLES · el cliente afinará criterios por país).
"""
from __future__ import annotations

from typing import Any, Optional

# Umbrales por defecto (porcentaje de admisión 0-100).
REACH_ACCEPTANCE_MAX = 15.0   # < 15% admisión → muy selectivo (reach)
SAFETY_ACCEPTANCE_MIN = 60.0  # > 60% admisión → accesible (safety)

GPA_MARGIN = 0.3
SAT_MARGIN = 100

Category = str  # "reach" | "match" | "safety"


def classify(
    program: Any,
    *,
    student_gpa: Optional[float] = None,
    student_sat: Optional[int] = None,
) -> Optional[Category]:
    """Devuelve 'reach'|'match'|'safety' o None si no hay datos suficientes."""
    ar = getattr(program, "acceptance_rate", None)
    avg_gpa = getattr(program, "avg_admitted_gpa", None)
    avg_sat = getattr(program, "avg_sat", None)
    min_sat = getattr(program, "min_sat", None)

    if ar is None and avg_gpa is None and min_sat is None and avg_sat is None:
        return None  # sin datos del programa → no clasificamos

    # Señales (SCOPE D-002): reach = OR de señales · safety = AND de señales.
    reach_signals: list[bool] = []
    safety_signals: list[bool] = []

    if student_gpa is not None and avg_gpa is not None:
        reach_signals.append(student_gpa < avg_gpa - GPA_MARGIN)
        safety_signals.append(student_gpa > avg_gpa + GPA_MARGIN)
    if student_sat is not None and min_sat is not None:
        reach_signals.append(student_sat < min_sat + SAT_MARGIN)
    if student_sat is not None and avg_sat is not None:
        safety_signals.append(student_sat > avg_sat + SAT_MARGIN)
    if ar is not None:
        reach_signals.append(ar < REACH_ACCEPTANCE_MAX)
        safety_signals.append(ar > SAFETY_ACCEPTANCE_MIN)

    if not reach_signals and not safety_signals:
        return None

    if any(reach_signals):
        return "reach"
    if safety_signals and all(safety_signals):
        return "safety"
    return "match"
