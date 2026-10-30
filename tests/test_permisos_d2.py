"""D-2 · Sprint 4 · qué puede usar cada quien: plan × grado × la matriz.

Lo que protegen estos tests:
 1. La matriz aprobada por JP (2026-10-29): qué es gratis, qué es pago, qué es VIP.
 2. Cada grado ve sus tests, y solo los suyos (D1).
 3. Las excepciones: sin grado conocido se ofrece todo (D9), quien no es
    estudiante no se filtra, lo que no existe aparece como `no_disponible`.
 4. Que la matriz sea coherente con lo que existe (no nombra tests inventados).
 5. `GET /me/permisos` sobre HTTP.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data import permisos as matriz
from app.data import vocational_tests
from app.services import permisos_service as svc
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401

# La regla real de planes, sin el `pago` por defecto de `conftest.py`.
pytestmark = pytest.mark.planes_reales
from tests.test_planes_d1 import _plan, _usuario

GRADOS = {
    "grado_9": {"life_stage": "high_school_early", "grade": "9"},
    "grado_10": {"life_stage": "high_school_early", "grade": "10"},
    "grado_11": {"life_stage": "high_school", "grade": "11"},
    "grado_12": {"life_stage": "high_school", "grade": "12"},
    "profesional": {"life_stage": "working"},
}


@pytest.fixture()
def db(app_db):
    _, Sesion = app_db
    s = Sesion()
    yield s
    s.close()


def _estudiante(db, email, plan=None, respuestas=None):
    u = _usuario(db, email)
    u.onboarding_answers = dict(respuestas or {})
    db.commit()
    if plan:
        _plan(db, u, plan, datetime.utcnow() - timedelta(days=1))
    return u


# ---------------------------------------------------------------------------
# 1 · La matriz
# ---------------------------------------------------------------------------


def test_gratis_solo_tiene_el_bot_y_el_onboarding(db):
    p = svc.permisos(db, _estudiante(db, "g@d2.dev", respuestas=GRADOS["grado_11"]))
    abiertas = {k for k, a in p.funciones.items() if a.permitido}
    assert abiertas == {"onboarding", "senal_preliminar"}
    assert p.funciones["tests"].motivo == "plan"
    assert p.funciones["tests"].plan_requerido == "pago"
    assert not any(a.permitido for a in p.tests.values())


def test_pago_abre_todo_menos_lo_vip(db):
    p = svc.permisos(db, _estudiante(db, "p@d2.dev", "pago", GRADOS["grado_11"]))
    for clave in ("tests", "lectura_tests", "reporte_pdf", "hoja_de_vida", "carta_motivacion",
                  "chat_hopper", "programas", "biblioteca", "practica_examenes"):
        assert p.funciones[clave].permitido, clave
    assert p.funciones["sesion_1a1"].motivo == "plan"
    assert p.funciones["sesion_1a1"].plan_requerido == "vip"


def test_vip_abre_la_sesion_y_el_profiler_aparece_como_no_disponible(db):
    p = svc.permisos(db, _estudiante(db, "v@d2.dev", "vip", GRADOS["grado_11"]))
    assert p.funciones["sesion_1a1"].permitido
    assert p.funciones["profiler"].motivo == "no_disponible"


@pytest.mark.parametrize("tramo", ["grado_9", "grado_10"])
def test_la_practica_de_examenes_no_es_de_9_ni_10(db, tramo):
    p = svc.permisos(db, _estudiante(db, f"{tramo}@d2.dev", "pago", GRADOS[tramo]))
    assert p.funciones["practica_examenes"].motivo == "no_es_de_su_grado"


# ---------------------------------------------------------------------------
# 2 · Cada grado ve sus tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tramo", list(GRADOS))
def test_cada_grado_ve_exactamente_sus_tests(db, tramo):
    p = svc.permisos(db, _estudiante(db, f"t-{tramo}@d2.dev", "pago", GRADOS[tramo]))
    assert p.tramo == tramo
    abiertos = {t for t, a in p.tests.items() if a.permitido}
    assert abiertos == set(matriz.TESTS_POR_TRAMO[tramo])
    for t, a in p.tests.items():
        if not a.permitido:
            assert a.motivo == "no_es_de_su_grado"


def test_el_ingles_no_es_de_noveno(db):
    p9 = svc.permisos(db, _estudiante(db, "i9@d2.dev", "pago", GRADOS["grado_9"]))
    p11 = svc.permisos(db, _estudiante(db, "i11@d2.dev", "pago", GRADOS["grado_11"]))
    assert p9.ingles.motivo == "no_es_de_su_grado"
    assert p11.ingles.permitido


# ---------------------------------------------------------------------------
# 3 · Las excepciones
# ---------------------------------------------------------------------------


def test_sin_grado_conocido_se_ofrece_todo_lo_de_su_plan(db):
    """D9: una cuenta vieja que nunca dijo su grado no pierde tests."""
    p = svc.permisos(db, _estudiante(db, "sin-grado@d2.dev", "pago"))
    assert p.tramo is None
    assert all(a.permitido for a in p.tests.values())
    assert p.funciones["practica_examenes"].permitido


def test_el_grado_se_lee_tambien_de_la_columna(db):
    u = _estudiante(db, "columna@d2.dev", "pago", {"life_stage": "high_school"})
    u.grade = 11
    db.commit()
    assert svc.permisos(db, u).tramo == "grado_11"


def test_quien_no_es_estudiante_no_se_filtra(db):
    from app.db.models import UserRole

    p = svc.permisos(db, _usuario(db, "psico@d2.dev", role=UserRole.PSYCHOLOGIST))
    assert p.tramo is None
    assert all(a.permitido for a in p.tests.values())


# ---------------------------------------------------------------------------
# 4 · La matriz es coherente con lo que existe
# ---------------------------------------------------------------------------


def test_la_matriz_solo_nombra_tests_que_existen():
    existentes = {t["id"] for t in vocational_tests.VOCATIONAL_TESTS}
    for tramo, ids in matriz.TESTS_POR_TRAMO.items():
        assert set(ids) <= existentes, (tramo, set(ids) - existentes)


def test_todo_test_existente_es_de_algun_grado():
    """Si alguien agrega un test y se olvida de la matriz, nadie lo vería."""
    existentes = {t["id"] for t in vocational_tests.VOCATIONAL_TESTS}
    en_la_matriz = {t for ids in matriz.TESTS_POR_TRAMO.values() for t in ids}
    assert existentes <= en_la_matriz, existentes - en_la_matriz


def test_los_planes_minimos_son_validos():
    for clave, spec in matriz.FUNCIONES.items():
        assert spec["plan"] in matriz.ORDEN_PLAN, clave


# ---------------------------------------------------------------------------
# 5 · HTTP
# ---------------------------------------------------------------------------


def test_get_me_permisos(app_db):
    app, Sesion = app_db
    s = Sesion()
    _estudiante(s, "http@d2.dev", "pago", GRADOS["grado_9"])
    s.close()
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": "http@d2.dev", "password": "testpass123"})
        cuerpo = c.get("/api/v1/me/permisos", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert cuerpo["plan"] == "pago"
    assert cuerpo["tramo"] == "grado_9"
    assert cuerpo["tests"]["vark"] == {"permitido": True, "motivo": None, "plan_requerido": None}
    assert cuerpo["tests"]["mbti"]["motivo"] == "no_es_de_su_grado"
    assert cuerpo["funciones"]["sesion_1a1"]["plan_requerido"] == "vip"
