"""El Journey como chat continuo · JP, reunión 24-08 (10:48 y 18:25).

    "esto del journey a mi todavia no me convence"
    "en Journey yo lo que me imagino es que sea como un chat continuo que le
     vaya haciendo preguntas al usuario para irlo perfilando"

Lo que protegen estos tests, en orden de importancia:

 1. **El contrato con el resto del producto no cambia.** `Session.answers`
    termina con las MISMAS claves y los MISMOS valores canónicos (los que
    salen de `state_machine.JOURNEY_STEPS[...].options`) que ya llenaba el
    wizard — es lo que leen `journey_service`, la síntesis, las rutas y el
    panel lateral.
 2. **El handoff al motor de síntesis/rutas es real**, no un `current_step`
    puesto a mano: se camina la cadena de `get_next_step`.
 3. **Nadie a mitad del wizard se ve afectado**: con el flag apagado, todo
    esto es 409 y no gasta una sola llamada al modelo.
 4. Las reglas textuales de la reunión — el video se ofrece y se salta según
    `clarityLevel` (JP, 20:03) — y el blindaje ya conocido (nada inventado,
    `interestType` topado a 2, el gate de menores).

**Se mockea la FRONTERA** (el SDK de Anthropic, `ai_client.get_client`), no
los servicios que se están probando — regla del CLAUDE.md del backend.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.state_machine import get_step
from app.data import journey_chat_hechos as catalogo
from app.services.journey_chat_service import FEATURE


# ── el SDK falso · la frontera ──────────────────────────────────────────────


class _BloqueTool:
    def __init__(self, entrada):
        self.type = "tool_use"
        self.input = entrada


class _BloqueTexto:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _Uso:
    input_tokens = 150
    output_tokens = 60


class _Respuesta:
    def __init__(self, content, stop_reason):
        self.content = content
        self.usage = _Uso()
        self.stop_reason = stop_reason


class SDKFalso:
    """Guion de respuestas · cada entrada es `{"_tipo": "tool"|"text", ...}`.

    Un turno de `journey_chat_service.responder` hace DOS llamadas reales al
    SDK: primero `fact_extractor.extraer` (tool use) y después
    `call_claude_chat` (texto) — el guion se consume en ese orden.
    """

    def __init__(self, guion):
        self.guion = list(guion)
        self.llamadas = []

    def with_options(self, **_kwargs):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.llamadas.append(kwargs)
        siguiente = self.guion.pop(0) if self.guion else {"_tipo": "text", "texto": "Ok."}
        if isinstance(siguiente, Exception):
            raise siguiente
        if siguiente.get("_tipo") == "tool":
            return _Respuesta([_BloqueTool(siguiente["input"])], "tool_use")
        return _Respuesta([_BloqueTexto(siguiente.get("texto", "Ok."))], "end_turn")


def _sdk(monkeypatch, *guion):
    from app.core import ai_client

    falso = SDKFalso(list(guion))
    monkeypatch.setattr(ai_client, "get_client", lambda: falso)
    return falso


def _turno_sdk(hecho_id, valor, respuesta_hop="Entendido, seguimos."):
    """El guion de un turno que hace que el extractor complete `hecho_id`."""
    if isinstance(valor, list):
        item = {"id": hecho_id, "valores": valor, "confianza": "alta"}
    else:
        item = {"id": hecho_id, "valor": valor, "confianza": "alta"}
    return (
        {"_tipo": "tool", "input": {"hechos": [item]}},
        {"_tipo": "text", "texto": respuesta_hop},
    )


# ── entorno ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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

    from app.core.rate_limiter import limiter
    limiter.reset()

    with TestClient(app) as client:
        yield client, TestingSessionLocal
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _sin_cache_de_flags():
    """El caché de flags dura 60s en proceso · sin esto un test contamina al
    siguiente (misma precaución que JR-2 y `journey_interprete`)."""
    from app.services import feature_flags_service as ff

    ff.invalidate_cache()
    yield
    ff.invalidate_cache()


def _estudiante(client, email):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Test2026!", "name": "Continuo"},
    )
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _sesion(client, H):
    r = client.get("/api/v1/auth/me/session", headers=H)
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _prender_flag(SL, enabled=True):
    from app.db.models import FeatureFlag
    from app.services import feature_flags_service as ff

    db = SL()
    db.add(FeatureFlag(key="journey_chat_continuo", name="Journey chat continuo", enabled=enabled))
    db.commit()
    db.close()
    ff.invalidate_cache()


def _set_onboarding(SL, email, onboarding):
    from app.db.models import User

    db = SL()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.onboarding_answers = onboarding
        db.commit()
    finally:
        db.close()


def _turno(client, H, sid, mensaje="algo"):
    return client.post(
        f"/api/v1/journey-chat/{sid}/turno", headers=H, json={"mensaje": mensaje, "historial": []},
    )


def _inicio(client, H, sid):
    return client.get(f"/api/v1/journey-chat/{sid}/inicio", headers=H)


def _sesion_db(SL, sid):
    from app.db.models import Session as JS

    db = SL()
    try:
        s = db.query(JS).filter(JS.id == UUID(sid)).first()
        return dict(s.answers or {}), s.current_step
    finally:
        db.close()


# ── EL test · el que sostiene el plan ───────────────────────────────────────


def test_el_chat_llena_las_mismas_claves_canonicas_que_el_wizard(env, monkeypatch):
    """Completa TODO el catálogo por chat y compara contra el vocabulario
    REAL del wizard (`state_machine.JOURNEY_STEPS[...].options`) — no una
    copia escrita a mano que pueda quedarse atrás."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "chat.completo@example.com")
    sid = _sesion(client, H)

    assert _inicio(client, H, sid).status_code == 200

    valores = {
        "lifeStage": get_step("lifeStage").options[0],
        "timeHorizon": get_step("timeHorizon").options[1],
        "clarityLevel": get_step("clarityLevel").options[0],  # NO "alta" · para que sí quede pendiente por completar el resto
        "interestType": [get_step("interestType").options[0]],
        "weeklyActivities": get_step("weeklyActivities").options[2],
        "budgetBand": get_step("budgetBand").options[0],
        "languageLevel": get_step("languageLevel").options[1],
        "geoPreference": get_step("geoPreference").options[0],
    }

    ultimo = None
    for hecho_id in catalogo.faltantes({}):
        if hecho_id not in valores:
            continue  # dontWant / declaredAspirations son opcionales · no hace falta responderlos
        _sdk(monkeypatch, *_turno_sdk(hecho_id, valores[hecho_id]))
        ultimo = _turno(client, H, sid, mensaje=f"mi respuesta sobre {hecho_id}")
        assert ultimo.status_code == 200, ultimo.text

    cuerpo = ultimo.json()
    assert cuerpo["listo"] is True
    assert cuerpo["journey"] is not None
    assert cuerpo["journey"]["step_id"] == "synthesis"  # handoff real, no puesto a mano

    respuestas, paso = _sesion_db(SL, sid)
    for hecho_id, esperado in valores.items():
        assert respuestas[hecho_id] == esperado, hecho_id
    assert paso == "synthesis"
    # Nada del texto libre que se le "dijo" a Hop (los mensajes del turno) se
    # filtró a la sesión: sólo quedan los valores canónicos.
    assert "mi respuesta sobre" not in str(respuestas)


# ── el flag apagado ─────────────────────────────────────────────────────────


def test_con_el_flag_apagado_es_409_y_no_gasta_llamadas(env, monkeypatch):
    client, SL = env
    H = _estudiante(client, "chat.flagoff@example.com")
    sid = _sesion(client, H)

    falso = _sdk(monkeypatch, *_turno_sdk("lifeStage", "x"))
    assert _inicio(client, H, sid).status_code == 409
    assert _turno(client, H, sid).status_code == 409
    assert falso.llamadas == []


# ── blindaje ya conocido, aplicado a este catálogo ──────────────────────────


def test_interestType_se_topa_a_dos(env, monkeypatch):
    """El paso original admite máximo 2 (`max_select`) · el extractor no
    conoce límites por hecho, así que el tope se aplica después de extraer."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "chat.tope@example.com")
    sid = _sesion(client, H)

    tres = get_step("interestType").options[:3]
    assert len(tres) == 3
    _sdk(monkeypatch, *_turno_sdk("interestType", tres))
    r = _turno(client, H, sid)
    assert r.status_code == 200, r.text
    assert len(r.json()["recolectado"]["interestType"]) == 2
    assert r.json()["recolectado"]["interestType"] == tres[:2]


def test_una_opcion_inventada_no_se_guarda(env, monkeypatch):
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "chat.inventada@example.com")
    sid = _sesion(client, H)

    _sdk(monkeypatch, *_turno_sdk("lifeStage", "Astronauta jubilado"))
    r = _turno(client, H, sid)
    assert r.status_code == 200, r.text
    assert "lifeStage" not in r.json()["recolectado"]


def test_registra_el_consumo_de_ia_con_provider(env, monkeypatch):
    """`provider` es obligatorio y keyword-only · olvidarlo deja la auditoría
    vacía en silencio (ya pasó en este repo)."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "chat.usage@example.com")
    sid = _sesion(client, H)

    _sdk(monkeypatch, *_turno_sdk("lifeStage", get_step("lifeStage").options[0]))
    assert _turno(client, H, sid).status_code == 200

    from app.db.models import AIUsageLog

    db = SL()
    try:
        filas = db.query(AIUsageLog).filter(AIUsageLog.feature == FEATURE).all()
        assert len(filas) == 1
        assert filas[0].provider == "anthropic"
        assert filas[0].tokens_input == 150
    finally:
        db.close()


def test_con_el_modelo_caido_no_se_pierde_lo_ya_extraido(env, monkeypatch):
    """La extracción (tool call) puede tener éxito aunque la respuesta de
    charla (text call) falle — los hechos ya dichos no se pierden."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "chat.caido@example.com")
    sid = _sesion(client, H)

    _sdk(
        monkeypatch,
        {"_tipo": "tool", "input": {"hechos": [
            {"id": "lifeStage", "valor": get_step("lifeStage").options[0], "confianza": "alta"},
        ]}},
        RuntimeError("el SDK explotó en la charla"),
    )
    r = _turno(client, H, sid)
    assert r.status_code == 200, r.text
    assert r.json()["respuesta"]  # mensaje de fallback, no vacío
    assert r.json()["recolectado"]["lifeStage"] == get_step("lifeStage").options[0]

    respuestas, _ = _sesion_db(SL, sid)
    assert respuestas["lifeStage"] == get_step("lifeStage").options[0]


# ── las reglas de la reunión 24-08 ──────────────────────────────────────────


def test_geoPreference_se_salta_a_quien_ya_dijo_que_se_queda_en_su_pais():
    """Misma regla que `state_machine.JOURNEY_STEPS['geoPreference'].skip_if`
    · reusada, no reimplementada."""
    onboarding = {"international_interest": "intl_no"}
    assert "geoPreference" not in catalogo.faltantes({}, onboarding, {})
    assert catalogo.aplica("geoPreference", {}, onboarding, {}) is False


def test_languageLevel_se_salta_con_examen_medido_y_flag_de_test_prendido():
    contexto = {"test_invitation_enabled": True, "has_english_test": True}
    assert "languageLevel" not in catalogo.faltantes({}, None, contexto)


def test_dontWant_y_declaredAspirations_no_bloquean_el_cierre():
    """Se degradan con gracia aguas abajo (ai_service usa 'No especificado')
    · insistir en ellos sería el mismo formulario con otra cara."""
    completo = {i: get_step(i).options[0] if get_step(i) and get_step(i).options else "x"
                for i in catalogo.OBLIGATORIOS}
    assert catalogo.listo_para_cerrar(completo) is True
    assert "dontWant" not in completo


def test_el_video_se_ofrece_y_se_salta_segun_claridad(monkeypatch):
    """JP, 24-08 (20:03): 'si ya tienes mucha claridad saltate los videos'."""
    from app.data import journey_videos as jv

    video = jv.JourneyVideo(
        id="v1", momento="clarityLevel", url="https://cdn.example.com/v1.mp4",
        duracion_segundos=90, tema="Cómo leer tu nivel de claridad",
    )
    monkeypatch.setattr(jv, "VIDEOS", [video])

    # Claridad baja/media · se ofrece.
    assert jv.elegir_video("clarityLevel", {"clarityLevel": "Tengo muchas dudas"}) == video
    # Claridad alta · se salta, tal cual lo pidió JP.
    assert jv.elegir_video("clarityLevel", {"clarityLevel": "Tengo algo claro y quiero validarlo"}) is None
    # Sin nada cargado para ese momento, no se inventa un video.
    assert jv.elegir_video("otro_momento", {}) is None


def test_no_hay_videos_de_ejemplo_cargados():
    """El estante empieza vacío a propósito · el contenido lo sube la
    clienta, no se inventa (CLAUDE.md: 'la IA NUNCA inventa datos duros')."""
    from app.data import journey_videos as jv

    assert jv.VIDEOS == []


# ── el gate de menores sigue aplicando ──────────────────────────────────────


def test_menor_sin_consentimiento_no_puede_avanzar_el_chat(env, monkeypatch):
    from datetime import date

    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "chat.menor@example.com")
    sid = _sesion(client, H)

    from app.db.models import User

    db = SL()
    try:
        u = db.query(User).filter(User.email == "chat.menor@example.com").first()
        hoy = date.today()
        u.birthdate = date(hoy.year - 14, 6, 1)  # 14 años · bajo el umbral
        db.commit()
    finally:
        db.close()

    _sdk(monkeypatch, *_turno_sdk("lifeStage", get_step("lifeStage").options[0]))
    r = _turno(client, H, sid)
    assert r.status_code == 403
    assert r.json()["detail"] == "minor_parental_consent_required"
