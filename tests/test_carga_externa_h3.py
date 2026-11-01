"""H-3 · Sprint 4 · "cuando le subo reportes de exámenes se demora mucho".

Medido en local: la lectura con IA de un reporte de 11 páginas tarda ~10 s, así
que lo que se cambió es (1) un modelo de extracción más barato, adoptado solo
porque acierta lo mismo en las 12 muestras del golden, (2) un parser de JSON que
no se cae si el modelo agrega texto después, y (3) que la persona no tenga que
quedarse mirando: al terminar le llega una notificación que la lleva a revisar.

Lo que protegen estos tests:
 1. El parser de reportes usa el modelo de extracción; las otras lecturas
    (diplomas, logros) siguen con el de siempre.
 2. Con Haiku 5.5 no se manda `temperature` (devuelve 400) y el razonamiento va
    encendido con esfuerzo bajo; con los modelos de la familia 4, temperature=0.
 3. JSON con texto pegado después se lee bien.
 4. Al terminar la lectura le llega una notificación con el enlace a revisar.
 5. El historial distingue "confirmado" de "listo para revisar".

Se mockea la frontera (el cliente de la API), no el parser.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _usuario

# La forma real de una respuesta RIASEC (ver `test_external_parser_payload_discrimination`).
_RESPUESTA_RIASEC = {
    "confidence": 0.95,
    "payload": {
        "holland_code": "ECI",
        "realistic": 30, "investigative": 70, "artistic": 50,
        "social": 40, "enterprising": 90, "conventional": 80,
        "suggested_careers": ["Administración"],
    },
}


class _ClienteFalso:
    """Imita `get_client()` y guarda con qué se llamó a messages.create."""

    def __init__(self, texto: str):
        self.llamadas = []
        self._texto = texto
        self.messages = SimpleNamespace(create=self._create)

    def with_options(self, **_):
        return self

    def _create(self, **kwargs):
        self.llamadas.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self._texto)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


@pytest.fixture()
def cliente(monkeypatch):
    def armar(texto=json.dumps(_RESPUESTA_RIASEC)):
        falso = _ClienteFalso(texto)
        monkeypatch.setattr("app.services.document_ai.get_client", lambda: falso)
        monkeypatch.setattr(
            "app.services.external_test_parser.extract_text_from_upload",
            lambda *a, **k: ("Holland RIASEC E 90 C 80 I 70", {"has_text_layer": True}),
        )
        return falso

    return armar


def _parsear():
    from app.services.external_test_parser import parse_external_test

    return parse_external_test(test_type="riasec", file_bytes=b"%PDF", content_type="application/pdf", filename="r.pdf")


def test_el_parser_usa_el_modelo_de_extraccion_sin_temperature(cliente):
    from app.config import get_settings

    falso = cliente()
    out = _parsear()
    assert out.parsing_status in ("done", "needs_review"), out.error_message
    [llamada] = falso.llamadas
    assert llamada["model"] == get_settings().ai_model_extraccion == "claude-haiku-5-5"
    assert "temperature" not in llamada
    assert llamada["thinking"] == {"type": "adaptive"}
    assert llamada["output_config"] == {"effort": "low"}


def test_las_otras_lecturas_siguen_con_el_modelo_de_siempre(cliente, monkeypatch):
    from app.config import get_settings
    from app.services import document_ai

    monkeypatch.setattr(get_settings(), "ai_model", "claude-sonnet-4-6")
    falso = cliente()
    document_ai.call_claude_text("lee este diploma")
    [llamada] = falso.llamadas
    assert llamada["model"] == "claude-sonnet-4-6"
    assert llamada["temperature"] == 0
    assert "thinking" not in llamada


def test_json_con_texto_pegado_despues_se_lee(cliente):
    cliente(json.dumps(_RESPUESTA_RIASEC) + "\n\nNota: revisé la tabla {completa} del reporte.")
    out = _parsear()
    assert out.result is not None, out.error_message
    assert out.result.payload.enterprising == 90


def test_al_terminar_le_llega_una_notificacion_con_el_enlace(app_db, cliente, monkeypatch):
    from app.api.v1 import external_test_uploads as rutas
    from app.db.models import ExternalTestUpload, Notification
    from app.services import storage_service

    _, Sesion = app_db
    monkeypatch.setattr(rutas, "SessionLocal", Sesion)
    cliente()
    backend = storage_service.get_backend()
    if not hasattr(backend, "_store"):
        pytest.skip("solo con el almacenamiento en memoria")
    backend._store["h3/r.pdf"] = (b"%PDF", "application/pdf")

    s = Sesion()
    u = _usuario(s, "carga@h3.dev")
    carga = ExternalTestUpload(user_id=u.id, test_type="riasec", file_path="h3/r.pdf",
                               content_type="application/pdf", parsing_status="pending")
    s.add(carga)
    s.commit()
    cid, uid = carga.id, u.id
    s.close()

    # En Postgres el id llega como texto; SQLite (los tests) necesita el UUID.
    rutas._run_parse_task(cid)

    s = Sesion()
    [aviso] = s.query(Notification).filter(Notification.user_id == uid).all()
    assert aviso.type == "carga_externa.lista"
    assert aviso.title == "Tu reporte de Holland (RIASEC) está listo"
    assert aviso.data["navigate_to"] == f"/tests/upload?upload={cid}"
    s.close()


def test_el_historial_distingue_confirmado_de_listo(app_db):
    from fastapi.testclient import TestClient

    from app.db.models import ExternalTestUpload, VocationalTestResult

    app, Sesion = app_db
    s = Sesion()
    u = _usuario(s, "hist@h3.dev")
    lista = ExternalTestUpload(user_id=u.id, test_type="mbti", file_path="a", parsing_status="done")
    confirmada = ExternalTestUpload(user_id=u.id, test_type="riasec", file_path="b", parsing_status="done")
    s.add_all([lista, confirmada])
    s.commit()
    s.add(VocationalTestResult(user_id=u.id, test_id="holland", scores={}, answers={},
                               source="external_upload", external_upload_id=confirmada.id))
    s.commit()
    ids = {"lista": str(lista.id), "confirmada": str(confirmada.id)}
    s.close()

    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": "hist@h3.dev", "password": "testpass123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        filas = {f["id"]: f for f in c.get("/api/v1/external-test-uploads", headers=h).json()}
        uno = c.get(f"/api/v1/external-test-uploads/{ids['lista']}", headers=h).json()
    assert filas[ids["confirmada"]]["confirmado"] is True
    assert filas[ids["lista"]]["confirmado"] is False
    assert uno["confirmado"] is False


def test_el_aviso_de_prospecto_caliente_lleva_a_prospectos():
    """G-4 · la campana navega con `navigate_to`; antes iba como `ruta` y no llevaba a nada."""
    import inspect

    from app.services import aviso_prospectos

    fuente = inspect.getsource(aviso_prospectos.avisar_caliente)
    assert '"navigate_to": "/gh/prospectos"' in fuente
    assert '"ruta":' not in fuente
