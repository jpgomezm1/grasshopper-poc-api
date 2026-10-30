"""B-7 · Sprint 4 · lo que contó en el bot gratuito llega a su cuenta.

Verónica: *"cuando me logueo o abro cuenta no me trae esta información que yo
ya le di y vuelve y me pregunta"*. Lo que protegen estos tests:

 1. Las equivalencias bot → onboarding, y que lo que no tiene equivalencia
    exacta (presupuesto, papá/mamá, "ya me gradué") NO se pase.
 2. El enlace por id (mismo dispositivo) y por correo (otro dispositivo), sin
    tomar un prospecto que ya es de otra cuenta.
 3. Que no pise lo que la cuenta ya tenía.
 4. Que el onboarding no vuelva a preguntar la etapa, y que igual muestre la
    bienvenida a quien todavía no ha conversado con Hopper.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.bot_gratuito_traspaso import hechos_desde_respuestas
from tests.test_bot_gratuito_b4 import RESPUESTAS, URL, _leads, _pedido, app_db  # noqa: F401

IMPORTAR = "/api/v1/bot-gratuito/importar"
INICIO = "/api/v1/onboarding-chat/inicio"

# ---------------------------------------------------------------------------
# 1 · Las equivalencias
# ---------------------------------------------------------------------------


def test_estudiante_de_once_con_colegio_ib_que_quiere_el_exterior():
    h = hechos_desde_respuestas({**RESPUESTAS, "flow": "Cocinar y montar a caballo"})
    assert h == {
        "life_stage": "high_school",
        "grade": "11",
        "school_accreditation": "ib",
        "international_interest": "intl_yes",
        "voice_passion": "Cocinar y montar a caballo",
    }


def test_en_noveno_las_materias_pasan_a_su_hecho():
    h = hechos_desde_respuestas({**RESPUESTAS, "stage": "9", "extra": "que", "materias": "Arte"})
    assert h["life_stage"] == "high_school_early"
    assert h["g9_materias_favoritas"] == "Arte"


def test_fuera_de_noveno_las_materias_no_tienen_donde_ir():
    assert "g9_materias_favoritas" not in hechos_desde_respuestas(RESPUESTAS)


def test_universidad_y_trabajo():
    assert hechos_desde_respuestas({"who": "uni", "stage": "u2"})["life_stage"] == "university"
    assert hechos_desde_respuestas({"who": "uni", "stage": "u4"})["life_stage"] == "recent_grad"
    assert hechos_desde_respuestas({"who": "pro", "stage": "p1"})["life_stage"] == "working"


def test_lo_que_no_tiene_equivalencia_exacta_no_se_pasa():
    # Papá o mamá: quien llenó el bot no es el estudiante.
    assert hechos_desde_respuestas({**RESPUESTAS, "who": "padre"}) == {}
    # "Ya me gradué" del colegio: desde E-6 tiene su etapa exacta, y el grado no
    # se pasa (es implícito: 12).
    assert hechos_desde_respuestas({**RESPUESTAS, "stage": "grad"})["life_stage"] == "school_grad"
    assert "grade" not in hechos_desde_respuestas({**RESPUESTAS, "stage": "grad"})
    # Colegio alemán o francés: el onboarding no tiene esa opción.
    assert "school_accreditation" not in hechos_desde_respuestas({**RESPUESTAS, "extra": "de-fr"})
    # El presupuesto nunca: los tramos no coinciden.
    assert "budget" not in hechos_desde_respuestas(RESPUESTAS)
    # "No sé" el destino no se convierte en un sí o un no.
    assert "international_interest" not in hechos_desde_respuestas({**RESPUESTAS, "dest": "nose"})


# ---------------------------------------------------------------------------
# 2 · Sobre HTTP
# ---------------------------------------------------------------------------


def _cuenta(Sesion, email):
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    db = Sesion()
    try:
        u = User(
            email=email,
            hashed_password=get_password_hash("testpass123"),
            name="Sara",
            role=UserRole.STUDENT,
            onboarding_status=OnboardingStatus.NOT_STARTED,
            onboarding_answers={},
        )
        db.add(u)
        db.commit()
        return u.id
    finally:
        db.close()


def _entrar(c, email):
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _usuario(Sesion, user_id):
    from app.db.models import User

    db = Sesion()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


def _con_correo(email):
    p = _pedido()
    p["contacto"] = {"nombre": "Sara", "email": email, "cuando": "soon"}
    p["respuestas"] = {**RESPUESTAS, "flow": "Cocinar"}
    return p


def test_mismo_dispositivo_por_id(app_db):
    app, Sesion = app_db
    uid = _cuenta(Sesion, "sara.b7@grasshopper.dev")
    with TestClient(app) as c:
        # El prospecto tiene OTRO correo (lo llenó con el de su mamá): igual se
        # enlaza, porque el id solo lo tiene esta pestaña.
        lead_id = c.post(URL, json=_con_correo("mama@correo.com")).json()["lead_id"]
        r = c.post(IMPORTAR, json={"lead_id": lead_id}, headers=_entrar(c, "sara.b7@grasshopper.dev"))
    assert r.status_code == 200, r.text
    assert r.json()["importado"] is True
    assert "life_stage" in r.json()["hechos"]

    u = _usuario(Sesion, uid)
    assert u.onboarding_answers["life_stage"] == "high_school"
    assert u.onboarding_answers["voice_passion"] == "Cocinar"
    assert u.grade == 11
    [lead] = _leads(Sesion)
    assert lead.converted_user_id == uid


def test_otro_dispositivo_por_correo(app_db):
    app, Sesion = app_db
    uid = _cuenta(Sesion, "sara.otro@grasshopper.dev")
    with TestClient(app) as c:
        c.post(URL, json=_con_correo("Sara.Otro@grasshopper.dev"))
        r = c.post(IMPORTAR, json={}, headers=_entrar(c, "sara.otro@grasshopper.dev"))
    assert r.json()["importado"] is True
    assert _usuario(Sesion, uid).onboarding_answers["life_stage"] == "high_school"


def test_no_toma_un_prospecto_que_ya_es_de_otra_cuenta(app_db):
    app, Sesion = app_db
    _cuenta(Sesion, "primera@grasshopper.dev")
    uid2 = _cuenta(Sesion, "segunda@grasshopper.dev")
    with TestClient(app) as c:
        lead_id = c.post(URL, json=_con_correo("primera@grasshopper.dev")).json()["lead_id"]
        c.post(IMPORTAR, json={"lead_id": lead_id}, headers=_entrar(c, "primera@grasshopper.dev"))
        r = c.post(IMPORTAR, json={"lead_id": lead_id}, headers=_entrar(c, "segunda@grasshopper.dev"))
    assert r.json() == {"importado": False, "hechos": []}
    assert _usuario(Sesion, uid2).onboarding_answers == {}


def test_sin_prospecto_no_pasa_nada(app_db):
    app, Sesion = app_db
    _cuenta(Sesion, "sin.bot@grasshopper.dev")
    with TestClient(app) as c:
        r = c.post(IMPORTAR, json={}, headers=_entrar(c, "sin.bot@grasshopper.dev"))
    assert r.json() == {"importado": False, "hechos": []}


def test_no_pisa_lo_que_la_cuenta_ya_tenia(app_db):
    app, Sesion = app_db
    from app.db.models import User

    uid = _cuenta(Sesion, "ya.tenia@grasshopper.dev")
    db = Sesion()
    u = db.query(User).filter(User.id == uid).first()
    u.onboarding_answers = {"voice_passion": "Lo que escribí en el chat"}
    db.commit()
    db.close()
    with TestClient(app) as c:
        lead_id = c.post(URL, json=_con_correo("ya.tenia@grasshopper.dev")).json()["lead_id"]
        c.post(IMPORTAR, json={"lead_id": lead_id}, headers=_entrar(c, "ya.tenia@grasshopper.dev"))
    respuestas = _usuario(Sesion, uid).onboarding_answers
    assert respuestas["voice_passion"] == "Lo que escribí en el chat"
    assert respuestas["life_stage"] == "high_school"


def test_el_onboarding_no_repregunta_y_sigue_mostrando_la_bienvenida(app_db):
    app, Sesion = app_db
    _cuenta(Sesion, "inicio.b7@grasshopper.dev")
    with TestClient(app) as c:
        h = _entrar(c, "inicio.b7@grasshopper.dev")
        # Antes del traspaso: la bienvenida y la pregunta por la etapa.
        antes = c.get(INICIO, headers=h).json()
        assert antes["bienvenida"] is True
        assert "en qué etapa estás" in antes["respuesta"]

        lead_id = c.post(URL, json=_con_correo("x@y.co")).json()["lead_id"]
        c.post(IMPORTAR, json={"lead_id": lead_id}, headers=h)

        despues = c.get(INICIO, headers=h).json()
    assert despues["bienvenida"] is True
    assert despues["recolectado"]["life_stage"] == "high_school"
    assert despues["respuesta"].startswith("Ya me contaste algunas cosas en el perfil gratis")
    assert "en qué etapa estás" not in despues["respuesta"]
    assert "Hola" not in despues["respuesta"]


def test_importar_dos_veces_no_duplica(app_db):
    app, Sesion = app_db
    uid = _cuenta(Sesion, "dos.veces@grasshopper.dev")
    with TestClient(app) as c:
        h = _entrar(c, "dos.veces@grasshopper.dev")
        lead_id = c.post(URL, json=_con_correo("dos.veces@grasshopper.dev")).json()["lead_id"]
        primera = c.post(IMPORTAR, json={"lead_id": lead_id}, headers=h).json()
        segunda = c.post(IMPORTAR, json={"lead_id": lead_id}, headers=h).json()
    assert primera["hechos"]
    assert segunda == {"importado": True, "hechos": []}
    assert _usuario(Sesion, uid).onboarding_answers["_desde_bot_gratuito"] == sorted(primera["hechos"])


def test_sin_sesion_no_se_puede(app_db):
    app, _ = app_db
    with TestClient(app) as c:
        assert c.post(IMPORTAR, json={}).status_code in (401, 403)
