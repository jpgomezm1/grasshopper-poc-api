"""Clasificación Reach / Match / Safety · D-002 (2026-06-04).

Categoriza qué tan alcanzable es un programa para un estudiante:
  - reach  · exigente / aspiracional
  - match  · en su nivel
  - safety · muy alcanzable

Regla determinista (no IA), basada en las variables de admisión del programa
(`acceptance_rate`, `avg_admitted_gpa`, `min_sat`, `avg_sat`) y, si están
disponibles, las métricas del estudiante (GPA/SAT).

LA TRAMPA DEL GPA (arreglada el 2026-08-30)
------------------------------------------
Los promedios NO se comparan crudos: se normalizan a 0-100 con la escala de
cada lado (`student_gpa_scale` y `Program.avg_admitted_gpa_scale`, migración
074). Sin las dos escalas la señal de GPA no se usa.

Comparar crudo daba la respuesta CONTRARIA a la verdadera: un 4.2/5.0
colombiano (84 %) frente a un 3.8/4.0 gringo (95 %) salía "safety" cuando es
"reach". Era inofensivo sólo mientras `student_gpa` llegara siempre `None`, y
dejaba de serlo el día que se cargara el Excel de admisión.

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

# El margen del GPA va en PUNTOS PORCENTUALES, no en "puntos de promedio":
# 0.3 significaba cosas distintas sobre 4.0 (7,5 %) que sobre 100 (0,3 %). Un
# 7,5 % es el equivalente al 0.3 sobre 4.0 que estaba puesto, así que la
# clasificación no se mueve para el caso que ya funcionaba.
GPA_MARGIN_PCT = 7.5
SAT_MARGIN = 100

Category = str  # "reach" | "match" | "safety"


def _a_porcentaje(nota: Optional[float], escala: Optional[float]) -> Optional[float]:
    """El promedio como 0-100 · la única forma comparable entre sistemas.

    Devuelve `None` en cuanto falta la escala: comparar un 4.2 con un 3.8 sin
    saber sobre cuánto va cada uno da la respuesta contraria a la verdadera
    (4.2/5.0 = 84 % está POR DEBAJO de 3.8/4.0 = 95 %, pero crudos 4.2 > 3.8).
    """
    if nota is None or not escala:
        return None
    try:
        nota_f, escala_f = float(nota), float(escala)
    except (TypeError, ValueError):
        return None
    if escala_f <= 0 or not (0 <= nota_f <= escala_f):
        return None
    return (nota_f / escala_f) * 100


def classify(
    program: Any,
    *,
    student_gpa: Optional[float] = None,
    student_gpa_scale: Optional[float] = None,
    student_sat: Optional[int] = None,
) -> Optional[Category]:
    """Devuelve 'reach'|'match'|'safety' o None si no hay datos suficientes.

    `student_gpa` **necesita su `student_gpa_scale`**, y el programa necesita
    su `avg_admitted_gpa_scale`. Si falta cualquiera de las dos, la señal de
    GPA no se usa — las otras (SAT, tasa de admisión) siguen valiendo. Preferir
    una señal menos a una señal falsa es la misma regla que aplica la
    calculadora del acudiente cuando se niega a convertir monedas.
    """
    ar = getattr(program, "acceptance_rate", None)
    avg_gpa = getattr(program, "avg_admitted_gpa", None)
    avg_gpa_scale = getattr(program, "avg_admitted_gpa_scale", None)
    avg_sat = getattr(program, "avg_sat", None)
    min_sat = getattr(program, "min_sat", None)

    # Defensivo: si acceptance_rate fue curado en escala 0-1 (error humano
    # frecuente), lo normalizamos a 0-100 para no clasificar mal en silencio.
    if ar is not None and 0 < ar <= 1:
        ar = ar * 100

    if ar is None and avg_gpa is None and min_sat is None and avg_sat is None:
        return None  # sin datos del programa → no clasificamos

    # Señales (SCOPE D-002): reach = OR de señales · safety = AND de señales.
    reach_signals: list[bool] = []
    safety_signals: list[bool] = []

    # Peras con peras · los dos lados normalizados a 0-100, y si a alguno le
    # falta la escala esta señal simplemente no entra.
    gpa_estudiante_pct = _a_porcentaje(student_gpa, student_gpa_scale)
    gpa_programa_pct = _a_porcentaje(avg_gpa, avg_gpa_scale)
    if gpa_estudiante_pct is not None and gpa_programa_pct is not None:
        reach_signals.append(gpa_estudiante_pct < gpa_programa_pct - GPA_MARGIN_PCT)
        safety_signals.append(gpa_estudiante_pct > gpa_programa_pct + GPA_MARGIN_PCT)
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
    # Safety es AND de señales, pero evitamos declararlo por UNA sola señal débil
    # (p.ej. solo SAT) sin respaldo: exigimos ≥2 señales o que la tasa de admisión
    # (medida más directa de probabilidad de ingreso) sea alta.
    if safety_signals and all(safety_signals):
        if len(safety_signals) >= 2 or (ar is not None and ar > SAFETY_ACCEPTANCE_MIN):
            return "safety"
    return "match"
