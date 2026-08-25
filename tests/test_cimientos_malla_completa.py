"""Cimientos del modelo de datos para la malla completa (fase 1 de 4).

Protege el CONTRATO que el resto de agentes va a programar contra:

  1. `users.grade` existe, es un entero independiente de `life_stage`, y
     sobrevive un roundtrip real por la base (no sólo un atributo en memoria).
  2. `users.school_reported_last_grade` / `users.school_reported_accreditation`
     existen y son NULLABLE (nadie los preguntó todavía = NULL, no error).
  3. `StudentYearSnapshot` guarda una foto por (usuario, año) y la unicidad se
     hace cumplir en la base — no sólo "se supone que nadie duplica".
  4. El patrón de consulta que describe el docstring del modelo (última foto
     por `school_year` = "qué dijo el año pasado") funciona de verdad.

SQLite in-memory · mismo patrón que tests/test_stale_recommendation_cache.py.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
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


def _seed_user(db, *, email, **overrides):
    from app.db.models import User

    defaults = dict(email=email, hashed_password="x", name="Estudiante Cimientos")
    defaults.update(overrides)
    u = User(**defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------------------
# 1. users.grade
# ---------------------------------------------------------------------------

class TestGradoDelEstudiante:
    def test_persiste_el_grado_y_sobrevive_un_reload_real(self, db_session):
        """No basta con que el atributo exista en memoria: tiene que volver
        de la base tal cual se guardó, para una sesión distinta a la que
        escribió."""
        from app.db.models import User

        u = _seed_user(db_session, email="grado11@grasshopper.dev", grade=11)
        user_id = u.id
        db_session.expunge_all()

        recargado = db_session.query(User).filter_by(id=user_id).one()
        assert recargado.grade == 11

    def test_grado_es_nullable_por_defecto(self, db_session):
        """Aditivo: filas nuevas sin dato de grado no deben fallar ni
        inventarse un valor."""
        u = _seed_user(db_session, email="sin-grado@grasshopper.dev")
        assert u.grade is None

    def test_grado_es_independiente_de_life_stage(self, db_session):
        """`life_stage` vive en `onboarding_answers` (JSON) y `grade` es una
        columna aparte: cambiar uno no debe tocar el otro. Es justo la
        distinción que motiva que `grade` no viva sólo dentro de
        `onboarding_answers` (ver comentario en app/db/models.py)."""
        u = _seed_user(
            db_session,
            email="independiente@grasshopper.dev",
            grade=9,
            onboarding_answers={"life_stage": "high_school_early"},
        )
        assert u.grade == 9
        assert u.onboarding_answers["life_stage"] == "high_school_early"

        # Cambiar el grado (paso de año) no debe pisar el JSON de onboarding.
        u.grade = 10
        db_session.commit()
        db_session.refresh(u)
        assert u.grade == 10
        assert u.onboarding_answers["life_stage"] == "high_school_early"


# ---------------------------------------------------------------------------
# 2. Lo que el estudiante cree de su colegio
# ---------------------------------------------------------------------------

class TestDatosDeColegioAutoreportados:
    def test_persiste_hasta_que_grado_llega_el_colegio(self, db_session):
        from app.db.models import User

        u = _seed_user(
            db_session,
            email="colegio12@grasshopper.dev",
            school_reported_last_grade=12,
            school_reported_accreditation="ib",
        )
        user_id = u.id
        db_session.expunge_all()

        recargado = db_session.query(User).filter_by(id=user_id).one()
        assert recargado.school_reported_last_grade == 12
        assert recargado.school_reported_accreditation == "ib"

    def test_no_se_sabe_se_guarda_distinto_de_no_se_pregunto(self, db_session):
        """"unknown" (preguntado, respondió "no sé") y NULL (no preguntado
        todavía) son estados distintos, aunque ambos oculten los módulos
        AP/IB en la capa que los consuma (fuera de esta fase)."""
        no_preguntado = _seed_user(db_session, email="no-preguntado@grasshopper.dev")
        no_sabe = _seed_user(
            db_session,
            email="no-sabe@grasshopper.dev",
            school_reported_accreditation="unknown",
        )
        assert no_preguntado.school_reported_accreditation is None
        assert no_sabe.school_reported_accreditation == "unknown"
        assert no_preguntado.school_reported_accreditation != no_sabe.school_reported_accreditation


# ---------------------------------------------------------------------------
# 3. Memoria por año escolar
# ---------------------------------------------------------------------------

class TestMemoriaPorAnioEscolar:
    def test_guarda_una_foto_por_usuario_y_anio(self, db_session):
        from app.db.models import StudentYearSnapshot

        u = _seed_user(db_session, email="memoria@grasshopper.dev", grade=10)
        snap = StudentYearSnapshot(
            user_id=u.id,
            school_year=2025,
            grade=9,
            onboarding_answers_snapshot={"voice_passion": "me gusta dibujar"},
        )
        db_session.add(snap)
        db_session.commit()
        db_session.refresh(snap)

        assert snap.id is not None
        assert snap.grade == 9
        assert snap.onboarding_answers_snapshot["voice_passion"] == "me gusta dibujar"
        # El snapshot es independiente del User actual (que ya va en grado 10).
        assert u.grade == 10

    def test_no_permite_dos_fotos_del_mismo_anio_para_el_mismo_usuario(self, db_session):
        """La unicidad la hace cumplir la base (`uq_student_year_snapshot`),
        no la buena voluntad de quien escriba el servicio que llene esta
        tabla más adelante."""
        from app.db.models import StudentYearSnapshot

        u = _seed_user(db_session, email="duplicado@grasshopper.dev")
        db_session.add(StudentYearSnapshot(user_id=u.id, school_year=2026, grade=11))
        db_session.commit()

        db_session.add(StudentYearSnapshot(user_id=u.id, school_year=2026, grade=11))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_mismo_usuario_puede_tener_fotos_de_anios_distintos(self, db_session):
        from app.db.models import StudentYearSnapshot

        u = _seed_user(db_session, email="multi-anio@grasshopper.dev")
        db_session.add(StudentYearSnapshot(user_id=u.id, school_year=2025, grade=9))
        db_session.add(StudentYearSnapshot(user_id=u.id, school_year=2026, grade=10))
        db_session.commit()

        fotos = (
            db_session.query(StudentYearSnapshot)
            .filter_by(user_id=u.id)
            .order_by(StudentYearSnapshot.school_year)
            .all()
        )
        assert [f.school_year for f in fotos] == [2025, 2026]
        assert [f.grade for f in fotos] == [9, 10]

    def test_que_dijo_el_anio_pasado_vs_que_dice_hoy(self, db_session):
        """El patrón de consulta descrito en el docstring del modelo: la foto
        más reciente en la tabla de memoria es "el año pasado"; lo vigente
        ("hoy") sigue viviendo en `users.onboarding_answers`, sin duplicarse."""
        from app.db.models import StudentYearSnapshot

        u = _seed_user(
            db_session,
            email="antes-y-ahora@grasshopper.dev",
            grade=11,
            onboarding_answers={"voice_passion": "ahora me interesa la biología"},
        )
        db_session.add(StudentYearSnapshot(
            user_id=u.id,
            school_year=2025,
            grade=10,
            onboarding_answers_snapshot={"voice_passion": "antes me interesaba el arte"},
        ))
        db_session.commit()

        anio_pasado = (
            db_session.query(StudentYearSnapshot)
            .filter_by(user_id=u.id)
            .order_by(StudentYearSnapshot.school_year.desc())
            .first()
        )
        hoy = u.onboarding_answers

        assert anio_pasado.onboarding_answers_snapshot["voice_passion"] == "antes me interesaba el arte"
        assert hoy["voice_passion"] == "ahora me interesa la biología"
        assert anio_pasado.grade == 10
        assert u.grade == 11

    def test_se_borra_en_cascada_si_se_borra_el_usuario(self, db_session):
        from app.db.models import StudentYearSnapshot, User

        u = _seed_user(db_session, email="cascada@grasshopper.dev")
        db_session.add(StudentYearSnapshot(user_id=u.id, school_year=2026, grade=11))
        db_session.commit()

        db_session.delete(u)
        db_session.commit()

        assert db_session.query(StudentYearSnapshot).count() == 0

    def test_relationship_user_year_snapshots(self, db_session):
        """El `relationship` declarado en User debe reflejar lo que hay en
        la tabla sin una consulta manual aparte."""
        from app.db.models import StudentYearSnapshot

        u = _seed_user(db_session, email="relationship@grasshopper.dev")
        db_session.add(StudentYearSnapshot(user_id=u.id, school_year=2026, grade=9))
        db_session.commit()
        db_session.refresh(u)

        assert len(u.year_snapshots) == 1
        assert u.year_snapshots[0].school_year == 2026
