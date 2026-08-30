"""Counselor Sync · P2 de la revisión Sprint 2.

Verónica (Paso 5): *"al finalizar cada etapa, el sistema genera un reporte
ejecutivo de progreso que el estudiante envía a su consejera antes de su
reunión presencial"*.

## Qué se prueba, y por qué en este orden

Lo primero son los PERMISOS, no el contenido. Esto mueve información de un
menor hacia adultos de su colegio: si el reporte sale bonito pero lo puede
leer el colegio equivocado, no sirve de nada que las tres secciones estén
bien.

  (a) el contenido son SUS tres preguntas, y nada más
  (b) la vista previa y lo enviado los arma el MISMO constructor
  (c) lo enviado se congela · no se recalcula después
  (d) ⭐ un colegio no ve los reportes de otro
  (e) ⭐ un estudiante no ve los de otro
  (f) ⭐ no se filtra análisis clínico
  (g) un B2C sin colegio recibe un 409 claro, no un 500
  (h) "leído" se marca una vez y no cuenta aperturas

SQLite in-memory · mismo patrón que el resto de la suite.
"""
from __future__ import annotations

import re
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


def _colegio(db, nombre="Colegio Cumbres"):
    from app.db.models import School

    # `slug` es NOT NULL en el modelo · se deriva del nombre igual que en el
    # panel de administracion, para no inventar un valor que luego no calce.
    s = School(name=nombre, slug=re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-"))
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _estudiante(db, *, school=None, email="alumno@test.com", **extra):
    from app.db.models import User, UserRole

    u = User(
        email=email,
        hashed_password="x",
        name="Camila Vargas",
        role=UserRole.STUDENT,
        school_id=(school.id if school else None),
        grade=10,
        onboarding_answers={
            "voice_passion": "diseñar videojuegos",
            "voice_hobbies": "dibujar",
            "grade": "10",
        },
        **extra,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------------------
# (a) el contenido son sus tres preguntas
# ---------------------------------------------------------------------------

def test_el_reporte_responde_las_tres_preguntas_de_veronica(db_session):
    # "ya sabe QUE QUIERE, QUE OPCIONES REALISTAS TIENE y QUE LE FALTA".
    from app.services import counselor_sync_service as cs

    u = _estudiante(db_session, school=_colegio(db_session))
    r = cs.construir_reporte(db_session, u)

    assert set(["que_quiere", "sobre_que_decide", "que_le_falta"]).issubset(r)
    assert r["que_quiere"]["pasion"] == "diseñar videojuegos"
    assert r["estudiante"]["grado"] == 10


def test_que_le_falta_sigue_la_misma_escalera_que_ve_el_estudiante(db_session):
    # Si esta lista dijera otra cosa que la guia en pantalla, el estudiante
    # llegaria a la reunion con una consejera que leyo pendientes distintos.
    from app.services import counselor_sync_service as cs

    u = _estudiante(db_session, school=_colegio(db_session))
    faltan = " · ".join(cs.construir_reporte(db_session, u)["que_le_falta"])

    assert "primer test" in faltan
    assert "inglés" in faltan
    assert "rutas" in faltan


# ---------------------------------------------------------------------------
# (b) y (c) una sola fuente, y lo enviado se congela
# ---------------------------------------------------------------------------

def test_lo_enviado_es_exactamente_lo_que_mostro_la_previa(db_session):
    from app.services import counselor_sync_service as cs

    u = _estudiante(db_session, school=_colegio(db_session))
    previa = cs.construir_reporte(db_session, u)
    enviado = cs.enviar(db_session, u).content
    db_session.commit()

    # `generado_en` cambia entre las dos llamadas, es lo unico que debe diferir.
    previa.pop("generado_en"), enviado.pop("generado_en")
    assert previa == enviado


def test_el_reporte_enviado_NO_cambia_si_el_estudiante_avanza_despues(db_session):
    """El corazón de por qué se guarda el contenido y no se recalcula.

    La consejera prepara la reunión con lo que recibió. Si el documento se
    actualizara solo, ella llegaría habiendo leído algo que ya no dice eso.
    """
    from app.services import counselor_sync_service as cs

    u = _estudiante(db_session, school=_colegio(db_session))
    reporte = cs.enviar(db_session, u)
    db_session.commit()
    faltaba_antes = list(reporte.content["que_le_falta"])

    # El estudiante sigue avanzando después de mandarlo.
    u.english_test_completed = True
    db_session.commit()
    db_session.refresh(reporte)

    assert reporte.content["que_le_falta"] == faltaba_antes
    # Y un reporte NUEVO sí refleja lo de ahora.
    assert "inglés" not in " · ".join(cs.construir_reporte(db_session, u)["que_le_falta"])


# ---------------------------------------------------------------------------
# (d) y (e) ⭐ los permisos · lo que de verdad puede hacer daño
# ---------------------------------------------------------------------------

def test_un_colegio_NO_ve_los_reportes_de_otro(db_session):
    from app.services import counselor_sync_service as cs

    cumbres = _colegio(db_session, "Cumbres")
    campestre = _colegio(db_session, "Gimnasio Campestre")

    de_cumbres = _estudiante(db_session, school=cumbres, email="a@test.com")
    de_campestre = _estudiante(db_session, school=campestre, email="b@test.com")
    cs.enviar(db_session, de_cumbres)
    cs.enviar(db_session, de_campestre)
    db_session.commit()

    buzon = cs.listar_del_colegio(db_session, cumbres.id)
    assert len(buzon) == 1
    assert buzon[0].student_user_id == de_cumbres.id


def test_un_estudiante_solo_ve_lo_que_el_mando(db_session):
    from app.services import counselor_sync_service as cs

    colegio = _colegio(db_session)
    uno = _estudiante(db_session, school=colegio, email="uno@test.com")
    otro = _estudiante(db_session, school=colegio, email="otro@test.com")
    cs.enviar(db_session, uno)
    cs.enviar(db_session, otro)
    db_session.commit()

    mios = cs.listar_del_estudiante(db_session, uno.id)
    assert len(mios) == 1
    assert mios[0].student_user_id == uno.id


# ---------------------------------------------------------------------------
# (f) ⭐ nada clínico se cuela
# ---------------------------------------------------------------------------

def test_el_reporte_no_lleva_analisis_clinico(db_session):
    """Que el estudiante pueda compartir su avance NO es una vía para sacar
    datos clínicos por la puerta de atrás.

    Esos viven en `clinical_analysis_service`, con su propio control de acceso
    y su base legal (Ley 1581/2012, Ley 1090/2006).
    """
    from app.services import counselor_sync_service as cs

    u = _estudiante(db_session, school=_colegio(db_session))
    plano = repr(cs.construir_reporte(db_session, u)).lower()

    for prohibido in ("clinic", "riesgo", "alerta", "diagnos", "suicid"):
        assert prohibido not in plano, f"se filtró «{prohibido}» al reporte del colegio"


# ---------------------------------------------------------------------------
# (g) sin colegio, un no claro
# ---------------------------------------------------------------------------

def test_un_estudiante_sin_colegio_no_puede_enviar(db_session):
    from app.services import counselor_sync_service as cs

    u = _estudiante(db_session, school=None)

    with pytest.raises(ValueError):
        cs.enviar(db_session, u)


# ---------------------------------------------------------------------------
# (h) leído se marca una vez
# ---------------------------------------------------------------------------

def test_leido_se_marca_una_vez_y_no_cuenta_aperturas(db_session):
    # Contar aperturas convertiria esto en un cronometro sobre la consejera,
    # que es lo contrario de aliviarle carga — el argumento entero del
    # documento de Veronica.
    from app.services import counselor_sync_service as cs

    u = _estudiante(db_session, school=_colegio(db_session))
    r = cs.enviar(db_session, u)
    db_session.commit()

    assert r.read_at is None
    cs.marcar_leido(db_session, r)
    db_session.commit()
    primera = r.read_at
    assert primera is not None

    cs.marcar_leido(db_session, r)
    db_session.commit()
    assert r.read_at == primera
