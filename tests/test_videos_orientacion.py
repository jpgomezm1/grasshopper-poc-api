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
 4. **Que la ruta muestre por dónde va y NO bloquee.** AH pidió el 2026-08-29
    "ir desbloqueando los videos" y, al ver que chocaba con "MEMORIA SÍ, LLAVE
    NO" —decisión de producto de la migración 067, aplicada ya en seis sitios—
    eligió el camino visual: orden, palomitas y "sigue aquí", pero todo
    abrible. La respuesta NO trae ningún campo de bloqueo, y hay un test que
    lo fija para que nadie lo añada por inercia.
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


def _ruta(client, headers):
    r = client.get("/api/v1/me/videos", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _todos(ruta):
    return [v for e in ruta["etapas"] for v in e["videos"]]


def _marcar(client, headers, video_id):
    r = client.post(f"/api/v1/me/videos/{video_id}/visto", headers=headers)
    assert r.status_code == 204, r.text


# ---------------------------------------------------------------------------
# 1 · el estante empieza vacio · nadie inventa contenido
# ---------------------------------------------------------------------------


def test_sin_videos_cargados_la_ruta_esta_vacia(app_with_db):
    """La tabla nace vacía a propósito · el contenido lo produce la clienta."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    r = _ruta(client, _estudiante(client))

    assert r["total"] == 0
    assert r["etapas"] == []
    assert r["siguiente_id"] is None


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

    # (a) sale en la ruta
    r = _ruta(client, headers)
    assert r["total"] == 1
    assert str(v.id) in [x["id"] for x in _todos(r)]

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


def test_sin_tests_hechos_nada_sale_recomendado(app_with_db):
    """El caso NORMAL hoy: casi ningún estudiante tiene tests.

    La insignia "encaja contigo" no puede salir sin códigos: prometería una
    personalización que no existe.
    """
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for i in range(6):
        _video(SessionLocal, topic=f"Tema {i // 3}", riasec_codes=["R", "I"])

    assert not any(v["recomendado"] for v in _todos(_ruta(client, headers)))


def test_con_tests_pero_sin_videos_etiquetados_tampoco(app_with_db):
    """⭐ La otra mitad: tener códigos no basta si nada está etiquetado."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client, "sinetiqueta@test.com")
    _riasec(SessionLocal, "sinetiqueta@test.com", {"R": 90, "I": 70, "A": 10})

    for i in range(6):
        _video(SessionLocal, topic=f"Tema {i // 3}")  # sin riasec_codes

    assert not any(v["recomendado"] for v in _todos(_ruta(client, headers)))


def test_con_codigos_y_videos_etiquetados_si_se_marca(app_with_db):
    """El otro lado · si no, 'nunca recomendar' pasaria los dos de arriba."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client, "conetiqueta@test.com")
    _riasec(SessionLocal, "conetiqueta@test.com", {"R": 90, "I": 70, "A": 10})

    for _ in range(6):
        _video(SessionLocal, topic="Ingenieria", riasec_codes=["R"])

    assert all(v["recomendado"] for v in _todos(_ruta(client, headers)))


# ---------------------------------------------------------------------------
# 5 · la ruta · orden, avance y "sigue aqui"
# ---------------------------------------------------------------------------


def test_las_etapas_salen_en_orden_y_los_sin_etapa_al_final(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    _video(SessionLocal, title="C", stage="3 · Decidir", sort_order=1)
    _video(SessionLocal, title="A", stage="1 · Descubrir", sort_order=1)
    _video(SessionLocal, title="Z", stage=None, sort_order=1)
    _video(SessionLocal, title="B", stage="2 · Conocer", sort_order=1)

    r = _ruta(client, headers)
    assert [e["titulo"] for e in r["etapas"]] == [
        "1 · Descubrir", "2 · Conocer", "3 · Decidir", "Otros videos",
    ]


def test_el_siguiente_es_el_primero_sin_abrir_y_es_uno_solo(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for i in range(4):
        _video(SessionLocal, title=f"V{i}", stage="Etapa", sort_order=i)

    r = _ruta(client, headers)
    assert [v["siguiente"] for v in _todos(r)] == [True, False, False, False]
    assert r["siguiente_id"] == _todos(r)[0]["id"]


def test_al_abrir_uno_el_siguiente_avanza(app_with_db):
    """⭐ Es lo que convierte la lista en una ruta."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for i in range(3):
        _video(SessionLocal, title=f"V{i}", stage="Etapa", sort_order=i)

    r = _ruta(client, headers)
    primero = _todos(r)[0]
    _marcar(client, headers, primero["id"])

    r2 = _ruta(client, headers)
    assert r2["vistos"] == 1
    assert _todos(r2)[0]["visto"] is True
    assert _todos(r2)[1]["siguiente"] is True
    assert r2["siguiente_id"] == _todos(r2)[1]["id"]


def test_con_todo_abierto_no_hay_siguiente_inventado(app_with_db):
    """No se propone "vuelve a ver el primero" · la ruta simplemente esta hecha."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    for i in range(2):
        _video(SessionLocal, title=f"V{i}", stage="Etapa", sort_order=i)

    for v in _todos(_ruta(client, headers)):
        _marcar(client, headers, v["id"])

    r = _ruta(client, headers)
    assert r["vistos"] == r["total"] == 2
    assert r["siguiente_id"] is None
    assert not any(v["siguiente"] for v in _todos(r))


def test_marcar_dos_veces_no_cuenta_dos(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)
    v = _video(SessionLocal, stage="Etapa")

    _marcar(client, headers, str(v.id))
    _marcar(client, headers, str(v.id))

    assert _ruta(client, headers)["vistos"] == 1


def test_marcar_un_video_que_no_existe_es_404(app_with_db):
    """Sin esto quedarian filas apuntando a nada y el avance podria pasar del
    100%."""
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)

    r = client.post(
        "/api/v1/me/videos/00000000-0000-0000-0000-000000000000/visto",
        headers=headers,
    )
    assert r.status_code == 404


def test_lo_que_abrio_uno_no_lo_ve_abierto_otro(app_with_db):
    app, SessionLocal = app_with_db
    client = TestClient(app)
    ana = _estudiante(client, "ana@test.com")
    beto = _estudiante(client, "beto@test.com")
    v = _video(SessionLocal, stage="Etapa")

    _marcar(client, ana, str(v.id))

    assert _ruta(client, ana)["vistos"] == 1
    assert _ruta(client, beto)["vistos"] == 0


def test_la_ruta_NO_trae_ningun_campo_de_bloqueo(app_with_db):
    """⭐ "MEMORIA SI, LLAVE NO" (migracion 067, seis sitios del backend).

    AH pidio "ir desbloqueando" y eligio el camino visual al ver el choque.
    Este test existe para que nadie añada un candado por inercia: si algun dia
    se bloquea de verdad, es una decision de producto que se habla con la
    clienta, no un campo que aparece en un refactor.
    """
    app, SessionLocal = app_with_db
    client = TestClient(app)
    headers = _estudiante(client)
    for i in range(3):
        _video(SessionLocal, title=f"V{i}", stage="Etapa", sort_order=i)

    prohibidos = {"bloqueado", "locked", "disponible", "unlocked", "requiere"}
    for v in _todos(_ruta(client, headers)):
        assert not (prohibidos & set(v)), f"apareci\u00f3 un campo de bloqueo en {v.keys()}"


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

    assert _ruta(client, headers)["total"] == 0

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
