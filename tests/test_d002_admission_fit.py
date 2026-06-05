"""D-002 · clasificación Reach/Match/Safety · unit tests."""
from types import SimpleNamespace as NS

from app.services import admission_fit_service as afs


def _prog(**kw):
    base = dict(
        acceptance_rate=None, avg_admitted_gpa=None, min_sat=None, avg_sat=None
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
    p = _prog(acceptance_rate=70, avg_admitted_gpa=3.5, avg_sat=1200, min_sat=1100)
    # GPA y SAT por encima de los promedios + admisión alta → safety
    assert afs.classify(p, student_gpa=4.0, student_sat=1400) == "safety"


def test_student_weak_sees_reach():
    p = _prog(acceptance_rate=70, avg_admitted_gpa=3.5, avg_sat=1200, min_sat=1100)
    # GPA muy por debajo del promedio admitido → reach (OR de señales)
    assert afs.classify(p, student_gpa=3.0, student_sat=1400) == "reach"


def test_reach_wins_on_low_acceptance_even_if_student_strong():
    p = _prog(acceptance_rate=5, avg_admitted_gpa=3.5, avg_sat=1200, min_sat=1100)
    # acceptance < 15% es señal de reach (OR) aunque el alumno sea fuerte
    assert afs.classify(p, student_gpa=4.0, student_sat=1500) == "reach"


def test_match_middle_ground():
    p = _prog(acceptance_rate=45, avg_admitted_gpa=3.5, avg_sat=1200, min_sat=1100)
    assert afs.classify(p, student_gpa=3.6, student_sat=1250) == "match"
