"""El Journey conversa · texto libre que guarda el MISMO valor que el botón.

El Journey se presenta como una conversación con Hop y no lo era: cada paso
pintaba burbujas pero por dentro era un `SINGLE_CHOICE` contra la máquina de
estados, sin una sola llamada al modelo. Esto abre un camino de entrada nuevo —
contestar con sus palabras— **sin cambiar el formato de lo que se guarda**.

Por qué ese matiz es todo el trabajo: las respuestas del Journey las leen SEIS
servicios, entre ellos `clinical_analysis_service` (el detector de riesgo
suicida, que el CLAUDE.md prohíbe tocar) y `crm_service` (escribe en Bitrix, el
CRM de producción de la clienta). Si el valor guardado cambia de forma, se los
toca a todos por la puerta de atrás.

De ahí el test que sostiene el plan y que va primero en este archivo:
`test_texto_libre_guarda_el_mismo_valor_que_el_boton`. Si ese falla, no importa
lo bonito que conteste Hop.

**Se mockea la frontera, el SDK de Anthropic** —regla nº2 del CLAUDE.md del
backend—, no el servicio que se está probando: así el test recorre de verdad
`journey_interprete` + `call_claude_tool` + la validación contra las opciones
canónicas, y encima puede mirar lo que se le mandó al modelo (el `enum`).
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.state_machine import get_step
from app.schemas.ai_outputs import (
    EmpathyReflectionOutput,
    SynthesisChip,
    SynthesisOutput,
)
from app.services.journey_interprete import FLAG, PASOS_HABILITADOS


# El paso del piloto · una sola pregunta encendida, como manda el plan.
PASO = "weeklyActivities"

# Lo que la persona escribiría hablando, en vez de pulsar "Proyectos prácticos".
TEXTO_CON_RODEOS = (
    "pues me gustaría estar metido en proyectos, armando cosas con las manos, "
    "no tanto sentado en clase"
)
OPCION_CANONICA = "Proyectos prácticos"


# ── el SDK falso · la frontera ──────────────────────────────────────────────


class _BloqueTool:
    def __init__(self, entrada):
        self.type = "tool_use"
        self.input = entrada


class _Uso:
    input_tokens = 120
    output_tokens = 40


class _Respuesta:
    def __init__(self, entrada):
        self.content = [_BloqueTool(entrada)]
        self.usage = _Uso()
        self.stop_reason = "tool_use"


class SDKFalso:
    """Suplanta al cliente de Anthropic · guion de respuestas, y memoria.

    Guarda los kwargs de cada llamada porque hay un test que comprueba QUÉ se
    le mandó al modelo: que el `enum` sean las opciones del paso y no una copia
    escrita a mano que pueda quedarse atrás de la copy de la clienta.
    """

    def __init__(self, guion):
        self.guion = list(guion)
        self.llamadas = []

    # El código productivo hace `get_client().with_options(...)`.
    def with_options(self, **_kwargs):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.llamadas.append(kwargs)
        siguiente = self.guion.pop(0) if self.guion else {}
        if isinstance(siguiente, Exception):
            raise siguiente
        return _Respuesta(siguiente)


def _sdk(monkeypatch, *guion):
    from app.core import ai_client

    falso = SDKFalso(guion)
    monkeypatch.setattr(ai_client, "get_client", lambda: falso)
    return falso


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

    # La IA de los pasos de reflexión no es lo que se prueba aquí, pero el
    # journey pasa por ellos para llegar al paso del piloto.
    from app.services import journey_service as js

    monkeypatch.setattr(
        js,
        "generate_empathy_reflection",
        lambda *a, **k: EmpathyReflectionOutput(text="Te entiendo.", detected_emotion=None),
    )
    monkeypatch.setattr(
        js,
        "generate_synthesis",
        lambda *a, **k: SynthesisOutput(
            text="Esto es lo que entiendo.",
            chips=[SynthesisChip(label="Etapa", value="x")],
            key_motivations=[],
            constraints=[],
        ),
    )

    with TestClient(app) as client:
        yield client, TestingSessionLocal
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _sin_cache_de_flags():
    """El caché de flags es global al proceso y dura 60 s · sin esto el estado
    de un test se filtra al siguiente y el de "flag apagado" pasaría por
    casualidad (misma precaución que en el test de JR-2)."""
    from app.services import feature_flags_service as ff

    ff.invalidate_cache()
    yield
    ff.invalidate_cache()


def _estudiante(client, email):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Test2026!", "name": "Conversa"},
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
    db.add(
        FeatureFlag(
            key=FLAG,
            name="Journey conversacional",
            enabled=enabled,
        )
    )
    db.commit()
    db.close()
    ff.invalidate_cache()


def _estado(client, H, sid):
    r = client.get(f"/api/v1/sessions/{sid}", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _responder(client, H, sid, step_id, payload):
    return client.post(
        f"/api/v1/sessions/{sid}/events",
        headers=H,
        json={"event_type": "answer", "step_id": step_id, "payload": payload},
    )


def _interpretar(client, H, sid, texto, step_id=PASO):
    return client.post(
        f"/api/v1/sessions/{sid}/interpretar",
        headers=H,
        json={"step_id": step_id, "texto": texto},
    )


def _caminar_hasta(client, H, sid, destino):
    """Avanza el journey con respuestas genéricas hasta el paso pedido."""
    for _ in range(20):
        estado = _estado(client, H, sid)
        if estado["step_id"] == destino:
            return estado
        vista = estado["view_type"]
        if vista == "OPEN_TEXT":
            payload = {"value": "respuesta de prueba"}
        elif vista == "SINGLE_CHOICE":
            payload = {"value": (estado.get("options") or ["x"])[0]}
        elif vista == "MULTI_CHOICE":
            payload = {"value": [(estado.get("options") or ["x"])[0]]}
        else:
            payload = {}
        r = _responder(client, H, sid, estado["step_id"], payload)
        assert r.status_code == 200, f"{estado['step_id']}: {r.text}"
    raise AssertionError(f"no llegó a {destino} en 20 pasos")


def _respuestas_guardadas(SL, sid):
    from app.db.models import Session as JS

    db = SL()
    try:
        sesion = db.query(JS).filter(JS.id == UUID(sid)).first()
        return dict(sesion.answers or {}), sesion.current_step
    finally:
        db.close()


# ── EL test · el que sostiene el plan ───────────────────────────────────────


def test_texto_libre_guarda_el_mismo_valor_que_el_boton(env, monkeypatch):
    """Escribir con rodeos y pulsar el botón dejan la sesión IDÉNTICA.

    Es el contrato con los seis servicios de aguas abajo: el texto libre es un
    camino de entrada nuevo, no un formato nuevo. Se comparan dos sesiones
    reales, no el valor contra sí mismo — así el test también detecta que el
    camino nuevo avance distinto (a otro paso) aunque guarde bien.
    """
    client, SL = env
    _prender_flag(SL)

    # A · la de siempre: pulsa el botón.
    Ha = _estudiante(client, "conversa.boton@example.com")
    sid_a = _sesion(client, Ha)
    _caminar_hasta(client, Ha, sid_a, PASO)
    assert _responder(client, Ha, sid_a, PASO, {"value": OPCION_CANONICA}).status_code == 200

    # B · la nueva: lo cuenta con sus palabras.
    Hb = _estudiante(client, "conversa.texto@example.com")
    sid_b = _sesion(client, Hb)
    _caminar_hasta(client, Hb, sid_b, PASO)

    _sdk(
        monkeypatch,
        {
            "opcion": OPCION_CANONICA,
            "confianza": "alta",
            "respuesta_de_hop": "Se te nota cuando hablas de construir cosas.",
        },
    )
    r = _interpretar(client, Hb, sid_b, TEXTO_CON_RODEOS)
    assert r.status_code == 200, r.text
    leido = r.json()
    assert leido["opcion"] == OPCION_CANONICA
    assert leido["necesita_confirmar"] is False
    assert leido["respuesta_de_hop"]  # Hop dice algo antes de avanzar

    # El front manda el valor canónico por el MISMO endpoint que el botón.
    assert _responder(client, Hb, sid_b, PASO, {"value": leido["opcion"]}).status_code == 200

    respuestas_a, paso_a = _respuestas_guardadas(SL, sid_a)
    respuestas_b, paso_b = _respuestas_guardadas(SL, sid_b)

    assert respuestas_b[PASO] == respuestas_a[PASO] == OPCION_CANONICA
    assert paso_b == paso_a  # avanzó al mismo sitio
    # Y nada del texto libre se filtró a la sesión: ni el crudo, ni claves nuevas.
    assert set(respuestas_b) == set(respuestas_a)
    assert TEXTO_CON_RODEOS not in str(respuestas_b)


# ── el intérprete no puede inventar ─────────────────────────────────────────


def test_nunca_devuelve_una_opcion_que_no_existe_en_el_paso(env, monkeypatch):
    """Se le da un payload con una opción inventada y tiene que descartarla.

    Es el blindaje que impide que una respuesta inventada acabe en el perfil,
    en el CV y en el dossier de la asesora.
    """
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.inventada@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, PASO)

    _sdk(
        monkeypatch,
        {
            "opcion": "Trabajar en la panadería de mi tío",
            "confianza": "alta",
            "respuesta_de_hop": "Entiendo.",
        },
    )
    r = _interpretar(client, H, sid, "ahorita estoy en la panadería de mi tío")
    assert r.status_code == 200, r.text
    assert r.json()["opcion"] is None
    assert r.json()["respuesta_de_hop"]  # repregunta, no silencio

    respuestas, paso = _respuestas_guardadas(SL, sid)
    assert PASO not in respuestas  # no se guardó NADA
    assert paso == PASO  # no avanzó


def test_texto_ambiguo_no_guarda_nada_y_hop_repregunta(env, monkeypatch):
    """`null` es una respuesta válida y esperada: se repregunta, no se adivina."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.ambiguo@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, PASO)

    _sdk(
        monkeypatch,
        {
            "confianza": "baja",
            "respuesta_de_hop": "No estoy seguro de entenderte, ¿me lo cuentas de otra forma?",
        },
    )
    r = _interpretar(client, H, sid, "no sé, cualquier cosa")
    assert r.status_code == 200, r.text
    assert r.json()["opcion"] is None
    assert r.json()["necesita_confirmar"] is False

    respuestas, paso = _respuestas_guardadas(SL, sid)
    assert PASO not in respuestas
    assert paso == PASO


def test_una_opcion_valida_con_confianza_baja_tampoco_se_propone(env, monkeypatch):
    """El modelo elige una opción y a la vez dice que no está seguro.

    Se le cree lo segundo. Pasa cuando la persona menciona algo de pasada
    ("los proyectos del colegio me estresan") y el modelo se agarra de la
    palabra: la opción existe, pero ella no la eligió.
    """
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.validabaja@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, PASO)

    _sdk(
        monkeypatch,
        {
            "opcion": OPCION_CANONICA,  # existe en el paso
            "confianza": "baja",  # …pero no está seguro
            "respuesta_de_hop": "¿Me cuentas un poco más de cómo sería tu semana?",
        },
    )
    r = _interpretar(client, H, sid, "los proyectos del colegio me estresan")
    assert r.status_code == 200, r.text
    assert r.json()["opcion"] is None
    assert r.json()["necesita_confirmar"] is False

    respuestas, paso = _respuestas_guardadas(SL, sid)
    assert PASO not in respuestas
    assert paso == PASO


def test_con_confianza_media_se_confirma_antes_de_guardar(env, monkeypatch):
    """Un clic barato evita un dato torcido · y hasta ese clic no se guarda nada."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.media@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, PASO)

    _sdk(
        monkeypatch,
        {
            "opcion": OPCION_CANONICA,
            "confianza": "media",
            "respuesta_de_hop": "Entiendo que prefieres proyectos prácticos, ¿es así?",
        },
    )
    r = _interpretar(client, H, sid, "algo de hacer cosas, creo")
    assert r.status_code == 200, r.text
    leido = r.json()
    assert leido["opcion"] == OPCION_CANONICA
    assert leido["necesita_confirmar"] is True

    respuestas, paso = _respuestas_guardadas(SL, sid)
    assert PASO not in respuestas  # todavía no
    assert paso == PASO

    # La persona confirma · a partir de ahí es el camino del botón.
    assert _responder(client, H, sid, PASO, {"value": leido["opcion"]}).status_code == 200
    respuestas, _ = _respuestas_guardadas(SL, sid)
    assert respuestas[PASO] == OPCION_CANONICA


def test_el_enum_que_recibe_el_modelo_son_las_opciones_del_paso(env, monkeypatch):
    """La copy es de la clienta · el vocabulario del modelo sale del paso.

    Si alguien reescribe una opción en `state_machine.py`, el `enum` la sigue
    sin que nadie tenga que acordarse de este archivo.
    """
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.enum@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, PASO)

    falso = _sdk(
        monkeypatch,
        {"opcion": OPCION_CANONICA, "confianza": "alta", "respuesta_de_hop": "Ok."},
    )
    assert _interpretar(client, H, sid, TEXTO_CON_RODEOS).status_code == 200

    assert len(falso.llamadas) == 1
    kwargs = falso.llamadas[0]
    herramienta = kwargs["tools"][0]
    assert kwargs["tool_choice"] == {"type": "tool", "name": herramienta["name"]}
    esquema = herramienta["input_schema"]
    assert esquema["properties"]["opcion"]["enum"] == get_step(PASO).options
    # `opcion` NO es obligatoria a propósito: omitirla es cómo el modelo se
    # abstiene, y abstenerse tiene que ser posible.
    assert "opcion" not in esquema.get("required", [])
    assert kwargs["temperature"] == 0


def test_con_el_modelo_caido_el_paso_se_completa_con_los_botones(env, monkeypatch):
    """Los botones son la red de seguridad · el Journey se termina igual."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.caido@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, PASO)

    _sdk(monkeypatch, RuntimeError("el SDK explotó"))
    r = _interpretar(client, H, sid, TEXTO_CON_RODEOS)
    assert r.status_code == 200, r.text  # el front no se queda sin respuesta
    assert r.json()["opcion"] is None
    assert r.json()["respuesta_de_hop"]

    respuestas, paso = _respuestas_guardadas(SL, sid)
    assert PASO not in respuestas
    assert paso == PASO

    # Y el camino de siempre sigue intacto.
    assert _responder(client, H, sid, PASO, {"value": OPCION_CANONICA}).status_code == 200
    respuestas, _ = _respuestas_guardadas(SL, sid)
    assert respuestas[PASO] == OPCION_CANONICA


def test_registra_el_consumo_de_ia_con_provider(env, monkeypatch):
    """`provider` es obligatorio y keyword-only · olvidarlo deja la auditoría
    vacía en silencio (ya pasó en este repo)."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.usage@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, PASO)

    _sdk(
        monkeypatch,
        {"opcion": OPCION_CANONICA, "confianza": "alta", "respuesta_de_hop": "Ok."},
    )
    assert _interpretar(client, H, sid, TEXTO_CON_RODEOS).status_code == 200

    from app.db.models import AIUsageLog
    from app.services.journey_interprete import FEATURE

    db = SL()
    try:
        filas = db.query(AIUsageLog).filter(AIUsageLog.feature == FEATURE).all()
        assert len(filas) == 1
        assert filas[0].provider == "anthropic"
        assert filas[0].tokens_input == 120
    finally:
        db.close()


# ── qué NO acepta texto libre ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "paso_pantalla",
    ["welcome", "empathy", "partialSummary1", "synthesis", "routes", "nextStep"],
)
def test_los_pasos_de_pantalla_no_son_conversacionales(paso_pantalla):
    """Pantallas y pasos de efecto lateral quedan fuera por lista explícita."""
    assert paso_pantalla not in PASOS_HABILITADOS
    # `testInvitation` saca a la persona del journey y depende del TEXTO de la
    # opción, que es copy de la clienta: es botón a propósito.
    assert "testInvitation" not in PASOS_HABILITADOS


def test_solo_un_paso_esta_habilitado(env):
    """El plan es explícito: se enciende UNO, se mira en producción, y sólo
    entonces se amplía. Si alguien añade pasos de golpe, este test avisa."""
    assert PASOS_HABILITADOS == (PASO,)


def test_un_paso_no_habilitado_no_acepta_texto_libre(env, monkeypatch):
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.otropaso@example.com")
    sid = _sesion(client, H)
    estado = _caminar_hasta(client, H, sid, "clarityLevel")
    assert estado["acepta_texto_libre"] is False

    falso = _sdk(monkeypatch, {})
    r = _interpretar(client, H, sid, "estoy perdidísima", step_id="clarityLevel")
    assert r.status_code == 409
    assert falso.llamadas == []  # no se gasta una llamada al modelo


def test_un_step_id_desincronizado_no_interpreta(env, monkeypatch):
    """Mismo criterio que `process_event`: sólo el paso ACTUAL de la sesión."""
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.desync@example.com")
    sid = _sesion(client, H)
    _caminar_hasta(client, H, sid, "clarityLevel")  # todavía no está en el paso

    falso = _sdk(monkeypatch, {})
    r = _interpretar(client, H, sid, TEXTO_CON_RODEOS)
    assert r.status_code == 409
    assert falso.llamadas == []


# ── el flag apagado ─────────────────────────────────────────────────────────


def test_con_el_flag_apagado_el_journey_es_el_de_siempre(env, monkeypatch):
    """Sin la fila del flag no hay que crear nada para que producción siga
    igual (`is_feature_enabled` es fail-closed)."""
    client, SL = env
    H = _estudiante(client, "conversa.flagoff@example.com")
    sid = _sesion(client, H)
    estado = _caminar_hasta(client, H, sid, PASO)

    assert estado["acepta_texto_libre"] is False

    falso = _sdk(monkeypatch, {})
    assert _interpretar(client, H, sid, TEXTO_CON_RODEOS).status_code == 409
    assert falso.llamadas == []

    # Y el paso se responde como siempre.
    assert _responder(client, H, sid, PASO, {"value": OPCION_CANONICA}).status_code == 200
    respuestas, _ = _respuestas_guardadas(SL, sid)
    assert respuestas[PASO] == OPCION_CANONICA


def test_con_el_flag_prendido_el_paso_se_anuncia_conversacional(env):
    client, SL = env
    _prender_flag(SL)
    H = _estudiante(client, "conversa.anuncio@example.com")
    sid = _sesion(client, H)
    estado = _caminar_hasta(client, H, sid, PASO)

    assert estado["acepta_texto_libre"] is True
    # Los botones NO desaparecen · son la red de seguridad.
    assert estado["options"] == get_step(PASO).options
