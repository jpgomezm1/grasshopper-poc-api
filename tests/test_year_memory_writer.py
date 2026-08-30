"""El ESCRITOR de la memoria por año · P1 de la revisión Sprint 2.

`StudentYearSnapshot` tenía tabla (migración 067) y lector completo
(`year_memory_service`), y **nadie escribía**. Verificado con un grep antes de
esto: ni un solo constructor fuera de `models.py`. La tabla vacía significa
`has_memory=False` para todo el mundo y el "Check-in de Evolución" que pidió
Verónica —*"la IA le recuerda qué le gustaba en 9° y pregunta si algo
cambió"*— sin poder dispararse jamás.

Estos tests fijan el contrato del escritor:

  (a) **Sólo cuando el grado CAMBIA.** El sync corre en CADA guardado del
      onboarding; fotografiar en todos llenaría la tabla de ruido.
  (b) **La primera vez no.** Alguien que declara grado por primera vez no
      tiene año anterior que conservar.
  (c) **Guarda lo SALIENTE, no lo nuevo.** Es el test que más importa: los dos
      llamadores sobrescriben `onboarding_answers` ANTES de llamar al sync, así
      que leer el atributo daría lo que la persona acaba de decir. Si esto se
      rompe, la IA diría "el año pasado dijiste…" citando lo de hoy — un error
      que nadie detectaría mirando la pantalla.
  (d) **Idempotente**, y se queda con la PRIMERA foto del año.
  (e) **Nunca rompe el guardado.** Best-effort, como el sync que lo llama.
  (f) **El lector lo ve.** La prueba de que el circuito quedó cerrado.

SQLite in-memory · mismo patrón que `test_year_memory_service.py`.
"""
from __future__ import annotations

from datetime import datetime

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


RESPUESTAS_DE_NOVENO = {
    "life_stage": "high_school_early",
    "grade": "9",
    "voice_passion": "diseñar videojuegos",
    "voice_hobbies": "dibujar y programar",
}


def _estudiante(db, *, grade=None, answers=None, email="alumno@test.com"):
    from app.db.models import User

    u = User(
        email=email,
        hashed_password="x",
        name="Estudiante",
        grade=grade,
        onboarding_answers=answers,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _snapshots(db, user_id):
    from app.db.models import StudentYearSnapshot

    return (
        db.query(StudentYearSnapshot)
        .filter(StudentYearSnapshot.user_id == user_id)
        .all()
    )


def _sync(db, user, answers):
    """Como lo llaman los dos endpoints reales: sobrescriben ANTES de sincronizar."""
    from app.api.v1.auth import _sync_onboarding_to_user_columns

    user.onboarding_answers = {**(user.onboarding_answers or {}), **answers}
    _sync_onboarding_to_user_columns(user, user.onboarding_answers, db)
    db.commit()


# ---------------------------------------------------------------------------
# (a) sólo cuando el grado cambia
# ---------------------------------------------------------------------------

def test_guardar_el_mismo_grado_no_toma_foto(db_session):
    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))

    _sync(db_session, u, {"voice_hobbies": "ahora también fotografía"})

    assert _snapshots(db_session, u.id) == []


def test_pasar_de_noveno_a_decimo_toma_UNA_foto(db_session):
    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))

    _sync(db_session, u, {"grade": "10"})

    fotos = _snapshots(db_session, u.id)
    assert len(fotos) == 1
    # El grado SALIENTE, no el nuevo.
    assert fotos[0].grade == 9
    assert u.grade == 10


# ---------------------------------------------------------------------------
# (b) la primera vez no hay año anterior que conservar
# ---------------------------------------------------------------------------

def test_declarar_grado_por_primera_vez_no_toma_foto(db_session):
    u = _estudiante(db_session, grade=None, answers={})

    _sync(db_session, u, {"grade": "9"})

    assert _snapshots(db_session, u.id) == []
    assert u.grade == 9


# ---------------------------------------------------------------------------
# (c) ⭐ guarda lo SALIENTE, no lo que acaba de decir
# ---------------------------------------------------------------------------

def test_la_foto_guarda_las_respuestas_de_ANTES_no_las_nuevas(db_session):
    """El test que más importa de este archivo.

    Los dos llamadores hacen `user.onboarding_answers = {**viejas, **nuevas}`
    antes del sync. Si el escritor leyera el atributo, guardaría lo de hoy como
    "lo del año pasado" — y la pantalla se vería perfecta mientras la IA cita
    mal.
    """
    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))

    _sync(db_session, u, {"grade": "10", "voice_passion": "ahora quiero medicina"})

    foto = _snapshots(db_session, u.id)[0]
    guardado = foto.onboarding_answers_snapshot

    assert guardado["voice_passion"] == "diseñar videojuegos"
    assert guardado["grade"] == "9"
    # Y lo de hoy sí es lo nuevo · la foto no se llevó el presente por delante.
    assert u.onboarding_answers["voice_passion"] == "ahora quiero medicina"


def test_la_foto_no_cambia_si_luego_se_muta_el_onboarding(db_session):
    # La columna es JSON y quien llama sigue trabajando sobre ese dict:
    # guardar la referencia haría que el snapshot cambiara con él.
    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))
    _sync(db_session, u, {"grade": "10"})

    u.onboarding_answers["voice_passion"] = "pisoteado"
    db_session.commit()

    foto = _snapshots(db_session, u.id)[0]
    assert foto.onboarding_answers_snapshot["voice_passion"] == "diseñar videojuegos"


# ---------------------------------------------------------------------------
# (d) idempotente · la primera foto del año es la que vale
# ---------------------------------------------------------------------------

def test_dos_cambios_de_grado_en_el_mismo_anio_no_duplican_ni_pisan(db_session):
    # La tabla tiene UniqueConstraint(user_id, school_year): un segundo cambio
    # el mismo año no puede crear otra fila. Y no debe pisar la primera, que es
    # la que capturó el estado saliente de verdad.
    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))

    _sync(db_session, u, {"grade": "10"})
    _sync(db_session, u, {"grade": "11"})

    fotos = _snapshots(db_session, u.id)
    assert len(fotos) == 1
    assert fotos[0].grade == 9
    assert fotos[0].onboarding_answers_snapshot["voice_passion"] == "diseñar videojuegos"


# ---------------------------------------------------------------------------
# (e) nunca rompe el guardado
# ---------------------------------------------------------------------------

def test_si_el_snapshot_falla_el_onboarding_igual_se_guarda(db_session, monkeypatch):
    # Perder una foto es una función que no se enciende ese año. Romper el
    # guardado es perderle las respuestas al estudiante.
    from app.services import year_memory_service

    def revienta(*_a, **_k):
        raise RuntimeError("base caída")

    monkeypatch.setattr(year_memory_service, "_respuestas_salientes", revienta)

    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))
    _sync(db_session, u, {"grade": "10", "voice_hobbies": "ajedrez"})

    assert u.grade == 10
    assert u.onboarding_answers["voice_hobbies"] == "ajedrez"


def test_sin_sesion_de_base_el_sync_sigue_funcionando(db_session):
    # `db` es opcional en la firma · sin ella no hay memoria, pero el resto del
    # sync (presupuesto, países, grado) tiene que seguir igual.
    from app.api.v1.auth import _sync_onboarding_to_user_columns

    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))
    u.onboarding_answers = {**u.onboarding_answers, "grade": "10"}
    _sync_onboarding_to_user_columns(u, u.onboarding_answers)
    db_session.commit()

    assert u.grade == 10
    assert _snapshots(db_session, u.id) == []


# ---------------------------------------------------------------------------
# (f) ⭐ el circuito completo · el lector por fin ve algo
# ---------------------------------------------------------------------------

def test_tras_pasar_de_anio_el_lector_ya_tiene_memoria(db_session):
    """La razón de ser de todo esto.

    Antes de este escritor, `has_memory` salía en False para TODOS los
    estudiantes del sistema, siempre.
    """
    from app.services.year_memory_service import get_year_comparison

    u = _estudiante(db_session, grade=9, answers=dict(RESPUESTAS_DE_NOVENO))
    antes = get_year_comparison(db_session, u)
    assert antes.has_memory is False

    _sync(db_session, u, {"grade": "10", "voice_passion": "ahora quiero medicina"})

    despues = get_year_comparison(db_session, u)
    assert despues.has_memory is True
    assert despues.is_new_grade is True
    assert despues.previous.grade == 9
    # Y detecta QUÉ cambió, que es lo que alimenta el check-in.
    #
    # `changed_fields` devuelve la PREGUNTA legible, no la clave cruda: el
    # lector la resuelve con `get_hecho` para que el check-in pueda decirle a
    # la persona "antes me dijiste X sobre esto" sin exponer nombres internos.
    assert len(despues.changed_fields) == 1
    assert "apasiona" in despues.changed_fields[0]
