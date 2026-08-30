"""Memoria entre años · `year_memory_service.get_year_comparison` (fase 2 de 4).

Cubre:
  (a) sin ningún `StudentYearSnapshot` → has_memory=False, previous=None,
      pero "hoy" sigue completo (grade + intereses + tests + rutas activas).
  (b) con snapshot y MISMO grado → has_memory=True, is_new_grade=False.
  (c) con snapshot y grado DISTINTO → is_new_grade=True.
  (d) grado ausente en cualquiera de los dos lados → nunca is_new_grade=True
      (no se puede afirmar "cambió" con un None de por medio).
  (e) changed_fields detecta lo que cambió y NO lo que quedó igual (prueba al
      revés: forzar que quede igual y verificar que ese campo deja de listarse).
  (f) "hoy" trae tests tomados (uno por test_id, el más reciente) y rutas
      activas reales de la base — no inventadas.
  (g) "año pasado" nunca trae tests_available/route_available en True — el
      cimiento no versiona esas tablas por año.
  (h) extracción de intereses tolera onboarding_answers vacío/None sin lanzar.

SQLite in-memory · mismo patrón que tests/test_cimientos_malla_completa.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def db_session(monkeypatch):
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setenv("DATABASE_URL", sqlite_url)

    from app.db.models import Base
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


ONBOARDING_2025 = {
    "life_stage": "high_school_early",
    "voice_passion": "diseñar videojuegos",
    "voice_hobbies": "dibujar y programar",
    "voice_strengths": "creatividad",
    "main_goal": ["discover"],  # tipo="multi" en el catálogo · así lo guardan
                                # journey_service/ai_service, una lista.
    "international_interest": "intl_maybe",
    "countries": ["usa", "canada"],
}


def _seed_user(db, *, email, **overrides):
    from app.db.models import User

    defaults = dict(email=email, hashed_password="x", name="Estudiante")
    defaults.update(overrides)
    u = User(**defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _seed_snapshot(db, user_id, *, school_year, grade, answers):
    from app.db.models import StudentYearSnapshot

    snap = StudentYearSnapshot(
        user_id=user_id,
        school_year=school_year,
        grade=grade,
        onboarding_answers_snapshot=answers,
    )
    db.add(snap)
    db.commit()
    return snap


# ---------------------------------------------------------------------------
# (a) sin snapshot · has_memory False pero "hoy" completo
# ---------------------------------------------------------------------------

def test_sin_snapshot_no_hay_memoria_pero_hoy_esta_completo(db_session):
    from app.db.models import VocationalTestResult
    from app.services.year_memory_service import get_year_comparison

    u = _seed_user(
        db_session,
        email="nuevo@grasshopper.dev",
        grade=10,
        onboarding_answers=ONBOARDING_2025,
    )
    db_session.add(VocationalTestResult(
        user_id=u.id, test_id="riasec", answers={}, scores={"R": 80},
    ))
    db_session.commit()

    comp = get_year_comparison(db_session, u)

    assert comp.has_memory is False
    assert comp.is_new_grade is False
    assert comp.previous is None
    assert comp.changed_fields == []
    # "hoy" no depende de que haya memoria · sigue viniendo del estado vigente.
    assert comp.today.grade == 10
    assert comp.today.perfil.pasion == "diseñar videojuegos"
    assert [t["test_id"] for t in comp.today.tests_taken] == ["riasec"]


# ---------------------------------------------------------------------------
# (b) snapshot con el MISMO grado · hay memoria pero no es "grado nuevo"
# ---------------------------------------------------------------------------

def test_snapshot_mismo_grado_no_dispara_grado_nuevo(db_session):
    from app.services.year_memory_service import get_year_comparison

    u = _seed_user(
        db_session, email="mismo-grado@grasshopper.dev", grade=10,
        onboarding_answers=ONBOARDING_2025,
    )
    _seed_snapshot(db_session, u.id, school_year=2025, grade=10, answers=ONBOARDING_2025)

    comp = get_year_comparison(db_session, u)

    assert comp.has_memory is True
    assert comp.is_new_grade is False
    assert comp.previous.school_year == 2025
    assert comp.previous.grade == 10


# ---------------------------------------------------------------------------
# (c) snapshot con grado DISTINTO · es "grado nuevo"
# ---------------------------------------------------------------------------

def test_snapshot_grado_distinto_dispara_grado_nuevo(db_session):
    from app.services.year_memory_service import get_year_comparison

    u = _seed_user(
        db_session, email="grado-nuevo@grasshopper.dev", grade=11,
        onboarding_answers=ONBOARDING_2025,
    )
    _seed_snapshot(db_session, u.id, school_year=2025, grade=10, answers=ONBOARDING_2025)

    comp = get_year_comparison(db_session, u)

    assert comp.has_memory is True
    assert comp.is_new_grade is True
    assert comp.previous.grade == 10
    assert comp.today.grade == 11

    # Prueba al revés (regla B) · si el grado vuelve a coincidir, dejar de
    # disparar. Si esto fallara, sería señal de que is_new_grade quedó fijo
    # en True sin comparar de verdad.
    u.grade = 10
    comp_igual = get_year_comparison(db_session, u)
    assert comp_igual.is_new_grade is False


# ---------------------------------------------------------------------------
# (d) grado ausente en alguno de los dos lados · nunca "grado nuevo"
# ---------------------------------------------------------------------------

def test_grado_none_en_cualquier_lado_no_dispara_grado_nuevo(db_session):
    from app.services.year_memory_service import get_year_comparison

    # Snapshot con grado conocido, usuario hoy sin grado (ej. pasó a perfil
    # profesional y grade quedó None) · ambiguo, no se afirma un cambio.
    u = _seed_user(
        db_session, email="sin-grado-hoy@grasshopper.dev", grade=None,
        onboarding_answers=ONBOARDING_2025,
    )
    _seed_snapshot(db_session, u.id, school_year=2025, grade=11, answers=ONBOARDING_2025)
    comp = get_year_comparison(db_session, u)
    assert comp.is_new_grade is False

    # Y al revés: snapshot sin grado, usuario hoy con grado.
    u2 = _seed_user(
        db_session, email="sin-grado-antes@grasshopper.dev", grade=9,
        onboarding_answers=ONBOARDING_2025,
    )
    _seed_snapshot(db_session, u2.id, school_year=2025, grade=None, answers=ONBOARDING_2025)
    comp2 = get_year_comparison(db_session, u2)
    assert comp2.is_new_grade is False


# ---------------------------------------------------------------------------
# (e) changed_fields · detecta lo que cambió, no lo que quedó igual
# ---------------------------------------------------------------------------

def test_changed_fields_detecta_solo_lo_que_cambio(db_session):
    from app.services.year_memory_service import get_year_comparison

    hoy = dict(ONBOARDING_2025)
    hoy["voice_passion"] = "diseñar productos digitales"  # cambió
    # voice_hobbies queda IGUAL a propósito

    u = _seed_user(
        db_session, email="cambios@grasshopper.dev", grade=11,
        onboarding_answers=hoy,
    )
    _seed_snapshot(db_session, u.id, school_year=2025, grade=10, answers=ONBOARDING_2025)

    comp = get_year_comparison(db_session, u)

    from app.data.onboarding_hechos import get_hecho
    etiqueta_pasion = get_hecho("voice_passion").pregunta_typeform
    etiqueta_hobbies = get_hecho("voice_hobbies").pregunta_typeform

    assert etiqueta_pasion in comp.changed_fields
    assert etiqueta_hobbies not in comp.changed_fields

    # Prueba al revés: si ahora también coincide voice_passion, deja de listarse.
    u.onboarding_answers = dict(hoy, voice_passion=ONBOARDING_2025["voice_passion"])
    comp_sin_cambio = get_year_comparison(db_session, u)
    assert etiqueta_pasion not in comp_sin_cambio.changed_fields


def test_changed_fields_vacios_en_los_dos_lados_no_cuenta_como_cambio(db_session):
    """Que los dos años tengan 'no contestó' en un campo no es un cambio real."""
    from app.services.year_memory_service import get_year_comparison

    sin_presupuesto = dict(ONBOARDING_2025)
    sin_presupuesto.pop("budget", None)

    u = _seed_user(
        db_session, email="sin-presupuesto@grasshopper.dev", grade=11,
        onboarding_answers=sin_presupuesto,
    )
    _seed_snapshot(db_session, u.id, school_year=2025, grade=10, answers=sin_presupuesto)

    comp = get_year_comparison(db_session, u)
    from app.data.onboarding_hechos import get_hecho
    etiqueta_presupuesto = get_hecho("budget").pregunta_typeform
    assert etiqueta_presupuesto not in comp.changed_fields


# ---------------------------------------------------------------------------
# (f) "hoy" trae tests reales (uno por test_id, el más reciente) y rutas activas
# ---------------------------------------------------------------------------

def test_hoy_trae_un_test_por_tipo_ordenado_por_mas_reciente(db_session):
    """`vocational_test_results` fuerza `UniqueConstraint(user_id, test_id)`
    (uq_user_test) · repetir un test actualiza la misma fila, nunca crea una
    segunda. Por eso el escenario real a probar es "dos tipos distintos de
    test, cada uno con su propia fecha", no un duplicado del mismo tipo."""
    from app.db.models import VocationalTestResult
    from app.services.year_memory_service import get_year_comparison

    u = _seed_user(db_session, email="tests@grasshopper.dev", grade=11)
    antes = datetime.utcnow() - timedelta(days=200)
    ahora = datetime.utcnow()
    db_session.add(VocationalTestResult(
        user_id=u.id, test_id="big5", answers={}, scores={}, created_at=antes,
    ))
    db_session.add(VocationalTestResult(
        user_id=u.id, test_id="riasec", answers={}, scores={}, created_at=ahora,
    ))
    db_session.commit()

    comp = get_year_comparison(db_session, u)
    por_tipo = {t["test_id"]: t["taken_at"] for t in comp.today.tests_taken}
    # En ISO, no `datetime`: este dict acaba dentro de una columna JSON
    # (el reporte al colegio) y un datetime crudo revienta el INSERT.
    assert por_tipo == {"riasec": ahora.isoformat(), "big5": antes.isoformat()}
    # El más reciente (riasec) sale primero.
    assert comp.today.tests_taken[0]["test_id"] == "riasec"

    # Reversal (regla B): si el test se re-toma (misma fila, nueva fecha), la
    # comparación tiene que reflejar la fecha nueva, no seguir mostrando la
    # vieja.
    fila_big5 = (
        db_session.query(VocationalTestResult)
        .filter_by(user_id=u.id, test_id="big5").one()
    )
    fila_big5.created_at = datetime.utcnow() + timedelta(days=1)
    db_session.commit()
    comp2 = get_year_comparison(db_session, u)
    assert comp2.today.tests_taken[0]["test_id"] == "big5"


def test_hoy_trae_rutas_activas_no_pausadas(db_session):
    from app.db.models import Route, RouteStatus, Session as JourneySession
    from app.services.year_memory_service import get_year_comparison

    u = _seed_user(db_session, email="rutas@grasshopper.dev", grade=11)
    sess = JourneySession(user_id=u.id)
    db_session.add(sess)
    db_session.commit()

    db_session.add(Route(
        session_id=sess.id, key="stem", name="Ingeniería",
        why="x", what_it_looks_like="x", next_step="x",
        status=RouteStatus.ACTIVE,
    ))
    db_session.add(Route(
        session_id=sess.id, key="arts", name="Diseño (pausada)",
        why="x", what_it_looks_like="x", next_step="x",
        status=RouteStatus.PAUSED,
    ))
    db_session.commit()

    comp = get_year_comparison(db_session, u)
    assert comp.today.active_routes == ["Ingeniería"]


# ---------------------------------------------------------------------------
# (g) "año pasado" nunca trae tests_available/route_available en True
# ---------------------------------------------------------------------------

def test_anio_pasado_nunca_reporta_tests_ni_ruta_disponibles(db_session):
    from app.services.year_memory_service import get_year_comparison

    u = _seed_user(db_session, email="honesto@grasshopper.dev", grade=11)
    _seed_snapshot(db_session, u.id, school_year=2025, grade=10, answers=ONBOARDING_2025)

    comp = get_year_comparison(db_session, u)
    assert comp.previous.tests_available is False
    assert comp.previous.route_available is False


# ---------------------------------------------------------------------------
# (h) extracción de intereses tolera onboarding_answers vacío/None
# ---------------------------------------------------------------------------

def test_extraccion_de_intereses_tolera_vacio_y_none(db_session):
    from app.services.year_memory_service import _intereses_declarados

    assert _intereses_declarados(None).esta_vacio() is True
    assert _intereses_declarados({}).esta_vacio() is True
    assert _intereses_declarados({"voice_passion": "   "}).esta_vacio() is True
