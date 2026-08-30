"""D-002 · clasificación Reach/Match/Safety · unit tests."""
from types import SimpleNamespace as NS

from app.services import admission_fit_service as afs


def _prog(**kw):
    base = dict(
        acceptance_rate=None, avg_admitted_gpa=None, avg_admitted_gpa_scale=None,
        min_sat=None, avg_sat=None,
    )
    base.update(kw)
    return NS(**base)


# --- fallback por selectividad del programa (sin métricas del estudiante) ---

def test_none_when_no_program_data():
    assert afs.classify(_prog()) is None


def test_acceptance_rate_fallback():
    assert afs.classify(_prog(acceptance_rate=8)) == "reach"     # < 15%
    assert afs.classify(_prog(acceptance_rate=75)) == "safety"   # > 60%
    assert afs.classify(_prog(acceptance_rate=40)) == "match"    # intermedio


# --- personalizado con métricas del estudiante (futuro · SCOPE D-002) ---

def test_student_strong_sees_safety():
    # GPA y SAT por encima de los promedios + admisión alta → safety.
    # Con las escalas declaradas, que es lo único que hace comparable el GPA.
    p = _prog(
        acceptance_rate=70, avg_admitted_gpa=3.5, avg_admitted_gpa_scale=4.0,
        avg_sat=1200, min_sat=1100,
    )
    veredicto = afs.classify(
        p, student_gpa=4.0, student_gpa_scale=4.0, student_sat=1400
    )
    assert veredicto == "safety"


def test_student_weak_sees_reach():
    """GPA muy por debajo del promedio admitido → reach (OR de señales).

    Actualizado el 2026-08-30: ahora hay que declarar la escala de los dos
    lados. Antes este test pasaba comparando 3.0 contra 3.5 **en crudo**, que
    es justo lo que daba la respuesta contraria cuando los sistemas de notas no
    coincidían (un 4.2/5.0 le "ganaba" a un 3.8/4.0 siendo peor).
    """
    p = _prog(
        acceptance_rate=70, avg_admitted_gpa=3.5, avg_admitted_gpa_scale=4.0,
        avg_sat=1200, min_sat=1100,
    )
    veredicto = afs.classify(
        p, student_gpa=3.0, student_gpa_scale=4.0, student_sat=1400
    )
    assert veredicto == "reach"


def test_sin_la_escala_el_gpa_no_puede_declarar_debil_a_nadie():
    """El mismo caso SIN escalas · la señal de GPA no entra.

    No es una regresión: es la regla nueva. Un 3.0 sólo es "bajo" frente a un
    3.5 si los dos van sobre lo mismo, y aquí nadie lo dijo. El veredicto lo
    deciden entonces las señales que sí son comparables — SAT alto y 70 % de
    admisión —, y sale "safety".
    """
    p = _prog(acceptance_rate=70, avg_admitted_gpa=3.5, avg_sat=1200, min_sat=1100)

    assert afs.classify(p, student_gpa=3.0, student_sat=1400) == "safety"


def test_reach_wins_on_low_acceptance_even_if_student_strong():
    p = _prog(acceptance_rate=5, avg_admitted_gpa=3.5, avg_sat=1200, min_sat=1100)
    # acceptance < 15% es señal de reach (OR) aunque el alumno sea fuerte
    assert afs.classify(p, student_gpa=4.0, student_sat=1500) == "reach"


def test_match_middle_ground():
    p = _prog(acceptance_rate=45, avg_admitted_gpa=3.5, avg_sat=1200, min_sat=1100)
    assert afs.classify(p, student_gpa=3.6, student_sat=1250) == "match"


# --- hardening (revisión adversarial) ---

def test_safety_not_triggered_by_single_weak_signal():
    # Solo avg_sat curado (sin acceptance_rate) + SAT alto → NO debe ser safety
    # por una sola señal débil; cae a match.
    p = _prog(avg_sat=1200)
    assert afs.classify(p, student_sat=1400) == "match"


def test_acceptance_rate_0_to_1_scale_is_normalized():
    assert afs.classify(_prog(acceptance_rate=0.08)) == "reach"   # 8%
    assert afs.classify(_prog(acceptance_rate=0.75)) == "safety"  # 75%
