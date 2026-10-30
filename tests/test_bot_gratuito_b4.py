"""B-4 · Sprint 4 · el bot gratuito guarda lo respondido y el contacto.

Lo que protegen estos tests:
 1. Que el prospecto quede en `bot_conversations` (la bandeja que el equipo ya
    lee), marcado como del bot gratuito.
 2. Que el consentimiento quede guardado con su texto exacto, y que a un
    estudiante de colegio se le pida además el aval de un adulto.
 3. Que el endpoint público no acepte basura: sin consentimiento, sin contacto,
    con claves que no son del bot o con textos larguísimos.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

URL = "/api/v1/bot-gratuito/lead"

RESPUESTAS = {
    "who": "colegio", "stage": "11", "spark": "I", "motor": "LOG",
    "dest": "ext", "budget": "b2", "extra": "ib",
    "materias": "Biología y química", "flow": "",
}


def _pedido(**cambios):
    base = {
        "respuestas": dict(RESPUESTAS),
        "contacto": {"nombre": "Sara", "whatsapp": "+57 300 000 0000", "email": "", "cuando": "soon"},
        "acepta_tratamiento": True,
    }
    base.update(cambios)
    return base


@pytest.fixture()
def app_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.db import database as dbmod
    from app.db.models import Base

    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", Sesion)
    Base.metadata.create_all(bind=engine)

    def _get_db():
        db = Sesion()
        try:
            yield db
        finally:
            db.close()

    from app.main import app
    from app.core.rate_limiter import limiter

    app.dependency_overrides[dbmod.get_db] = _get_db
    limiter.reset()
    yield app, Sesion
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _leads(Sesion):
    from app.db.models import BotConversation

    db = Sesion()
    try:
        return db.query(BotConversation).all()
    finally:
        db.close()


def test_guarda_el_prospecto_sin_cuenta(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido())
    assert r.status_code == 200, r.text
    assert r.json()["lead_id"]

    [lead] = _leads(Sesion)
    assert lead.name == "Sara"
    assert lead.phone == "+57 300 000 0000"
    assert lead.email is None
    assert lead.is_completed is True
    assert lead.transcript == []
    assert lead.hechos["_fuente"] == "bot_gratuito"
    assert lead.hechos["cuando"] == "soon"
    assert lead.hechos["respuestas"]["stage"] == "11"
    assert lead.hechos["respuestas"]["materias"] == "Biología y química"
    # La abierta que se saltó no se guarda vacía.
    assert "flow" not in lead.hechos["respuestas"]


def test_el_consentimiento_queda_con_su_texto_y_el_aval_del_adulto_si_es_de_colegio(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        c.post(URL, json=_pedido())
        pro = _pedido()
        pro["respuestas"] = {**RESPUESTAS, "who": "pro", "stage": "p2", "extra": "li-later"}
        c.post(URL, json=pro)

    colegio, profesional = sorted(_leads(Sesion), key=lambda l: l.hechos["respuestas"]["who"])
    c1 = colegio.hechos["_consentimiento"]
    assert c1["version"] == "bot-gratuito-v1"
    assert "Autorizo el tratamiento de mis datos personales" in c1["texto"]
    assert "mi papá, mamá o acudiente autoriza" in c1["texto"]
    assert c1["aceptado_en"].endswith("Z")
    assert "acudiente" not in profesional.hechos["_consentimiento"]["texto"]


@pytest.mark.parametrize(
    "cambio, motivo",
    [
        ({"acepta_tratamiento": False}, "autorización"),
        ({"contacto": {"nombre": "Sara", "whatsapp": "", "email": "", "cuando": "soon"}}, "al menos un medio"),
        ({"contacto": {"nombre": "Sara", "email": "no-es-correo", "cuando": "soon"}}, "correo"),
        ({"contacto": {"nombre": "Sara", "email": "a@b.co", "cuando": "ayer"}}, "cuándo"),
    ],
)
def test_rechaza_lo_que_no_cumple(app_db, cambio, motivo):
    app, Sesion = app_db
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(**cambio))
    assert r.status_code == 422
    assert motivo in r.json()["detail"]
    assert _leads(Sesion) == []


def test_rechaza_claves_que_no_son_del_bot(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(respuestas={**RESPUESTAS, "rol": "admin"}))
    assert r.status_code == 422
    assert _leads(Sesion) == []


def test_rechaza_si_falta_una_cerrada(app_db):
    app, Sesion = app_db
    sin_motor = {k: v for k, v in RESPUESTAS.items() if k != "motor"}
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(respuestas=sin_motor))
    assert r.status_code == 422
    assert "motor" in r.json()["detail"]


def test_las_abiertas_se_recortan_al_tope(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(respuestas={**RESPUESTAS, "flow": "x" * 900}))
    assert r.status_code == 200
    assert len(_leads(Sesion)[0].hechos["respuestas"]["flow"]) == 300


def test_el_correo_se_guarda_en_minusculas(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        c.post(URL, json=_pedido(contacto={"nombre": "Sara", "email": "Sara@Correo.COM", "cuando": "now"}))
    assert _leads(Sesion)[0].email == "sara@correo.com"


# ---------------------------------------------------------------------------
# B-6 · el siguiente paso y las acciones de la señal preliminar
# ---------------------------------------------------------------------------


def test_devuelve_el_siguiente_paso_pero_no_el_puntaje(app_db):
    app, _ = app_db
    with TestClient(app) as c:
        caliente = c.post(URL, json=_pedido()).json()
        frio = _pedido()
        frio["respuestas"] = {**RESPUESTAS, "stage": "9", "budget": "nose", "dest": "nose"}
        frio["contacto"] = {**frio["contacto"], "cuando": "later"}
        frio = c.post(URL, json=frio).json()
    assert caliente["siguiente_paso"] == "contacto"
    assert frio["siguiente_paso"] == "contenido"
    for cuerpo in (caliente, frio):
        assert set(cuerpo) == {"lead_id", "siguiente_paso"}


def test_la_accion_queda_en_el_prospecto_y_no_se_duplica(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        lead_id = c.post(URL, json=_pedido()).json()["lead_id"]
        for _ in range(2):
            r = c.post(f"{URL}/{lead_id}/accion", json={"accion": "contacto"})
            assert r.status_code == 200, r.text
    [lead] = _leads(Sesion)
    assert [a["accion"] for a in lead.hechos["acciones"]] == ["contacto"]
    assert lead.hechos["acciones"][0]["en"].endswith("Z")


def test_accion_desconocida_o_prospecto_ajeno(app_db):
    app, Sesion = app_db
    from app.db.models import BotConversation

    db = Sesion()
    ajeno = BotConversation(hechos={}, transcript=[])
    db.add(ajeno)
    db.commit()
    ajeno_id = str(ajeno.id)
    db.close()

    with TestClient(app) as c:
        lead_id = c.post(URL, json=_pedido()).json()["lead_id"]
        assert c.post(f"{URL}/{lead_id}/accion", json={"accion": "borrar"}).status_code == 422
        # Un prospecto del bot conversacional no se toca desde aquí.
        assert c.post(f"{URL}/{ajeno_id}/accion", json={"accion": "contacto"}).status_code == 404
        assert c.post(
            f"{URL}/00000000-0000-0000-0000-000000000000/accion", json={"accion": "contacto"},
        ).status_code == 404
