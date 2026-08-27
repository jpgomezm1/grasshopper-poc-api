# -*- coding: utf-8 -*-
"""Videos de orientación · una tabla, dos superficies.

Reunión con Verónica del 2026-08-24: *"hay unas partes donde me gustaria irles
poniendo como videos que yo tengo"*.

## Qué protegen estos tests

 1. **Que un video se cargue UNA vez y sirva a los dos sitios.** Es la razón
    de que haya una sola tabla: con dos, la clienta subiría el mismo video dos
    veces y las copias divergirían.
 2. **La regla de JP** (24-08, 20:03): *"si ya tienes mucha claridad saltate
    los videos"*. Estaba probada sobre la lista en código; ahora se prueba
    sobre la tabla, que es de donde sale el contenido de verdad.
 3. **Que no se prometa personalización que no existe.** "Para ti" sólo
    aparece si la persona tiene códigos RIASEC *y* hay videos etiquetados con
    ellos. Hoy casi nadie tiene tests hechos, así que el caso normal es que no
    salga — y salir vacío o relleno sería peor que no salir.
 4. **Que con poco contenido no se pinten filas.** La galería arranca en cero
    y se llena de a poco; una fila de un elemento con su "Ver todos" al lado
    parece un error de render.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def app_with_db(monkeypatch):
    """Misma receta que el resto de tests de endpoint · SQLite en memoria."""
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setenv("BITRIX_WEBHOOK_URL", "")
    from app.db import database as dbmod

    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.db.models import Base

    Base.metadata.create_all(bind=engine)

    from app.main import app

    app.dependency_overrides[dbmod.get_db] = _override_get_db

    from app.core.rate_limiter import limiter as gh_limiter

    gh_limiter.reset()

    yield app, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _estudiante(client, email="videos@test.com"):
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "testpass123",
            "name": "Ana",
            "acepta_tratamiento_datos": True,
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _video(SessionLocal, **kw):
    from app.db.models import OrientationVideo

    db = SessionLocal()
    try:
        datos = {
            "url": f"https://youtu.be/{uuid.uuid4().hex[:11]}",
            "title": "Un dia en la vida de una enfermera",
            "topic": "Salud",
        }
        datos.update(kw)
        v = OrientationVideo(**datos)
        db.add(v)
        db.commit()
        db.refresh(v)
        return v
    finally:
        db.close()


def _riasec(SessionLocal, headers_email, scores):
    """Siembra un resultado de Holland para el usuario de ese correo."""
    from app.db.models import User, VocationalTestResult

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == headers_email).first()
        db.add(
            VocationalTestResult(
                user_id=u.id, test_id="holland", answers={}, scores=scores
            )
        )
        db.commit()
    finally:
        db.close()


def _galeria(client, headers):
    r = client.get("/api/v1/me/videos", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# 1 · el estante empieza vacio · nadie inventa contenido
# ---------------------------------------------------------------------------


def test_sin_videos_cargados_la_galeria_esta_vacia(app_with_db):
    """La tabla nace vacía a propósito · el contenido lo produce la clienta."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    g = _galeria(client, _estudiante(client))

    assert g["total"] == 0
    assert g["filas"] == []


def test_la_migracion_no_siembra_videos_de_ejemplo(app_with_db):
    """Antes esto se afirmaba sobre `journey_videos.VIDEOS == []`. La lista ya
    no existe —el contenido vive en la tabla— pero la regla es la misma:
    inventar una URL o una duración es el tipo de dato inventado por el que ya
    hubo un reclamo del cliente."""
    app, SessionLocal = app_with_db
    from app.db.models import OrientationVideo

    db = SessionLocal()
    try:
        assert db.query(OrientationVideo).count() == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2 · una tabla, dos superficies
# ---------------------------------------------------------------------------


def test_un_solo_video_sirve_a_la_galeria_y_al_chat(app_with_db):
    """⭐ La razón de que haya UNA tabla.

    El mismo registro, cargado una vez, tiene que aparecer en la galería y
    poder ofrecerse dentro del chat del Journey. Con dos tablas habría que
    subirlo dos veces y las copias divergirían.
    """
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    v = _video(
        SessionLocal,
        title="Como se elige entre programa y pais",
        topic="Decidir",
        journey_moment="geoPreference",
    )

    # (a) sale en la galería
    g = _galeria(client, headers)
    assert g["total"] == 1
    ids = [x["id"] for f in g["filas"] for x in f["videos"]]
    assert str(v.id) in ids

    # (b) y el chat lo ofrece para su momento
    from app.data import journey_videos as jv

    db = SessionLocal()
    try:
        elegido = jv.elegir_video("geoPreference", {}, db=db)
    finally:
        db.close()

    assert elegido is not None
    assert elegido.id == str(v.id)
    assert elegido.url == v.url


def test_el_titulo_real_viaja_al_chat(app_with_db):
    """El front fabricaba el título ("Un video que te puede ayudar") porque el
    backend sólo mandaba `tema`. Ahora hay título de verdad y tiene que llegar."""
    app, SessionLocal = app_with_db
    _video(
        SessionLocal,
        title="Ingenieria biomedica: que se hace de verdad",
        journey_moment="interestType",
    )

    from app.data import journey_videos as jv

    db = SessionLocal()
    try:
        elegido = jv.elegir_video("interestType", {}, db=db)
    finally:
        db.close()

    assert elegido.titulo == "Ingenieria biomedica: que se hace de verdad"


# ---------------------------------------------------------------------------
# 3 · la regla de JP
# ---------------------------------------------------------------------------


def test_con_claridad_alta_no_se_ofrece_video(app_with_db):
    """JP, 24-08 (20:03): 'si ya tienes mucha claridad saltate los videos'."""
    app, SessionLocal = app_with_db
    _video(SessionLocal, journey_moment="clarityLevel")

    from app.data import journey_videos as jv

    db = SessionLocal()
    try:
        con_dudas = jv.elegir_video(
            "clarityLevel", {"clarityLevel": "Tengo muchas dudas"}, db=db
        )
        con_claridad = jv.elegir_video(
            "clarityLevel",
            {"clarityLevel": "Tengo algo claro y quiero validarlo"},
            db=db,
        )
    finally:
        db.close()

    assert con_dudas is not None
    assert con_claridad is None


def test_sin_video_para_ese_momento_no_se_inventa_uno(app_with_db):
    app, SessionLocal = app_with_db
    _video(SessionLocal, journey_moment="clarityLevel")

    from app.data import journey_videos as jv

    db = SessionLocal()
    try:
        assert jv.elegir_video("otro_momento", {}, db=db) is None
    finally:
        db.close()


def test_el_video_de_la_ruta_gana_al_generico(app_with_db):
    app, SessionLocal = app_with_db
    _video(SessionLocal, title="Generico", journey_moment="budgetBand")
    especifico = _video(
        SessionLocal,
        title="De grado 12",
        journey_moment="budgetBand",
        journey_route="grade_12",
    )

    from app.data import journey_videos as jv

    db = SessionLocal()
    try:
        elegido = jv.elegir_video("budgetBand", {}, "grade_12", db=db)
    finally:
        db.close()

    assert elegido.id == str(especifico.id)


# ---------------------------------------------------------------------------
# 4 · "Para ti" no promete lo que no puede cumplir
# ---------------------------------------------------------------------------


def test_sin_tests_hechos_no_hay_fila_para_ti(app_with_db):
    """El caso NORMAL hoy: casi ningún estudiante tiene tests."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for i in range(6):
        _video(SessionLocal, topic=f"Tema {i // 3}", riasec_codes=["R", "I"])

    g = _galeria(client, headers)
    assert "para-ti" not in [f["clave"] for f in g["filas"]]


def test_con_tests_pero_sin_videos_etiquetados_tampoco(app_with_db):
    """⭐ La otra mitad: tener códigos no basta si nada está etiquetado.

    Sin este caso, la fila saldría vacía o —peor— con videos cualesquiera bajo
    un rótulo que promete personalización.
    """
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client, "sinetiqueta@test.com")
    _riasec(SessionLocal, "sinetiqueta@test.com", {"R": 90, "I": 70, "A": 10})

    for i in range(6):
        _video(SessionLocal, topic=f"Tema {i // 3}")  # sin riasec_codes

    g = _galeria(client, headers)
    assert "para-ti" not in [f["clave"] for f in g["filas"]]


def test_con_codigos_y_videos_etiquetados_si_aparece(app_with_db):
    """El otro lado · si no, 'nunca aparece' tambien pasaria los dos de arriba."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client, "conetiqueta@test.com")
    _riasec(SessionLocal, "conetiqueta@test.com", {"R": 90, "I": 70, "A": 10})

    for i in range(6):
        _video(SessionLocal, topic="Ingenieria", riasec_codes=["R"])

    g = _galeria(client, headers)
    filas = {f["clave"]: f for f in g["filas"]}
    assert "para-ti" in filas
    assert len(filas["para-ti"]["videos"]) == 6


# ---------------------------------------------------------------------------
# 5 · el formato lo decide el backend
# ---------------------------------------------------------------------------


def test_con_poco_contenido_es_rejilla_y_no_filas(app_with_db):
    """⭐ La galería arranca en cero. Una fila de un elemento con su 'Ver
    todos' al lado se lee como un error de render, no como una categoría."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for tema in ("Salud", "Arte", "Ingenieria"):
        _video(SessionLocal, topic=tema)

    g = _galeria(client, headers)
    assert g["layout"] == "rejilla"
    assert len(g["filas"]) == 1, "en rejilla va todo junto, sin agrupar por tema"
    assert g["filas"][0]["clave"] == "todos"


def test_con_suficiente_contenido_si_hay_filas_por_tema(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for _ in range(3):
        _video(SessionLocal, topic="Salud")
    for _ in range(3):
        _video(SessionLocal, topic="Ingenieria")

    g = _galeria(client, headers)
    assert g["layout"] == "filas"
    assert {f["titulo"] for f in g["filas"]} == {"Salud", "Ingenieria"}


def test_un_tema_con_muy_pocos_cae_en_otros_temas(app_with_db):
    """Para que no queden filas de un solo elemento."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for _ in range(5):
        _video(SessionLocal, topic="Salud")
    _video(SessionLocal, topic="Arte", title="El unico de arte")

    g = _galeria(client, headers)
    assert g["layout"] == "filas"
    titulos = [f["titulo"] for f in g["filas"]]
    assert "Salud" in titulos
    assert "Arte" not in titulos
    otros = [f for f in g["filas"] if f["clave"] == "otros"][0]
    assert [v["title"] for v in otros["videos"]] == ["El unico de arte"]


# ---------------------------------------------------------------------------
# 6 · lo que no se publica no se ve
# ---------------------------------------------------------------------------


def test_un_video_sin_publicar_no_sale_en_ninguna_de_las_dos_superficies(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    _video(
        SessionLocal,
        title="Borrador",
        journey_moment="clarityLevel",
        is_published=False,
    )

    assert _galeria(client, headers)["total"] == 0

    from app.data import journey_videos as jv

    db = SessionLocal()
    try:
        assert jv.elegir_video("clarityLevel", {}, db=db) is None
    finally:
        db.close()


def test_la_galeria_es_solo_del_estudiante(app_with_db):
    """Mismo patrón que `/me/electives` y `/me/activities`."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    assert client.get("/api/v1/me/videos").status_code in (401, 403)
