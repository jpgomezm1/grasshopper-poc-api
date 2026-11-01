"""J-4 · Sprint 4 · los recordatorios cuando deja un paso a medias.

Se construyen sobre RM-1 (`outreach_service`), que ya decidía a quién escribirle
y con qué cuidado (consentimiento, menores, frecuencia, interruptor apagado:
eso lo protege `test_rm1_acompanamiento.py`). Lo que estos tests agregan:

 1. El "a medias" literal: hizo algunos tests de su grado y no todos.
 2. Ningún recordatorio lleva a algo que su plan no incluye (un gratis no
    recibe "haz un test") ni a algo que no es de su grado (inglés en 9°).
 3. El enlace del inglés va a la pantalla real (`/english-test`).
 4. El aviso de la campana se puede tocar (`navigate_to`).

Con planes reales: la regla de `conftest.py` da `pago` a todos por defecto.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services import outreach_service as svc
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan
from tests.test_rm1_acompanamiento import (  # noqa: F401
    HACE_MUCHO,
    _apagado_por_defecto,
    _estudiante,
    _prender,
    _sesion,
    _sin_modelo_real,
)

pytestmark = pytest.mark.planes_reales

ONCE = {"life_stage": "high_school", "grade": "11"}
NOVENO = {"life_stage": "high_school_early", "grade": "9"}


@pytest.fixture()
def db(app_db):
    _, Sesion = app_db
    s = Sesion()
    yield s
    s.close()


def _con_plan(db, u, plan="pago"):
    _plan(db, u, plan, datetime.utcnow() - timedelta(days=60))


def _test(db, u, test_id, hace_dias=10):
    from app.db.models import VocationalTestResult

    db.add(VocationalTestResult(
        user_id=u.id, test_id=test_id, answers={}, scores={},
        created_at=datetime.utcnow() - timedelta(days=hace_dias),
    ))
    db.commit()


# --- 1 · tests de su grado a medias ------------------------------------------


def test_hizo_uno_de_tres_y_no_volvio(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _con_plan(db, u)
    _test(db, u, "istrong")
    m = svc.detectar_motivo(db, u)
    assert m.clave == "tests_a_medias"
    assert m.asunto == "Te faltan 2 tests de tu grado"
    assert m.destino == "/tests"


def test_le_falta_uno(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _con_plan(db, u)
    _test(db, u, "istrong")
    _test(db, u, "mbti")
    assert svc.detectar_motivo(db, u).asunto == "Te falta 1 test de tu grado"


def test_si_lo_hizo_hace_poco_no_se_le_escribe_por_eso(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _con_plan(db, u)
    _test(db, u, "istrong", hace_dias=2)
    m = svc.detectar_motivo(db, u)
    assert m is None or m.clave != "tests_a_medias"


def test_con_todos_los_de_su_grado_no_hay_a_medias(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _con_plan(db, u)
    for t in ("istrong", "mbti", "bigfive"):
        _test(db, u, t)
    m = svc.detectar_motivo(db, u)
    assert m is None or m.clave != "tests_a_medias"


def test_un_test_de_otro_grado_no_cuenta_como_empezar_los_suyos(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _con_plan(db, u)
    _test(db, u, "vark")  # de 9°
    m = svc.detectar_motivo(db, u)
    assert m is None or m.clave != "tests_a_medias"


# --- 2 · plan y grado ----------------------------------------------------------


def test_a_un_gratis_no_se_le_manda_a_los_tests(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))  # sin plan = gratis
    assert svc.detectar_motivo(db, u) is None


def test_a_un_gratis_si_se_le_recuerda_el_recorrido_a_medias(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _sesion(db, u, completada=False)
    m = svc.detectar_motivo(db, u)
    assert m is not None and m.clave == "journey_a_medias"


def test_en_noveno_no_se_le_habla_del_ingles(db):
    u = _estudiante(db, onboarding_answers=dict(NOVENO))
    _con_plan(db, u)
    for t in ("vark", "motivadores", "holland"):
        _test(db, u, t)
    assert svc.detectar_motivo(db, u) is None


# --- 3-4 · los enlaces -----------------------------------------------------------


def test_el_ingles_lleva_a_la_pantalla_real(db):
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _con_plan(db, u)
    for t in ("istrong", "mbti", "bigfive"):
        _test(db, u, t)
    m = svc.detectar_motivo(db, u)
    assert m.clave == "ingles_pendiente"
    assert m.destino == "/english-test"


def test_el_aviso_de_la_campana_se_puede_tocar(db, monkeypatch):
    from app.db.models import Notification
    from app.services import email_service
    from app.services import outreach_sender as snd

    _prender(monkeypatch)

    class _Ok:
        delivered = True
        reason = None

    monkeypatch.setattr(email_service, "send_email", lambda **k: _Ok())
    u = _estudiante(db, onboarding_answers=dict(ONCE))
    _con_plan(db, u)
    _test(db, u, "istrong")
    r = snd.enviar(db, u, svc.detectar_motivo(db, u))
    assert r.resultado == snd.ENVIADO
    n = db.query(Notification).filter(Notification.user_id == u.id).one()
    assert n.data["navigate_to"] == "/tests"
