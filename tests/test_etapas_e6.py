"""E-6 · Sprint 4 · "Ya terminé el colegio" y el universitario.

Quien acababa de terminar el colegio no tenía dónde ponerse: la única opción
parecida era "Recién graduado", que lo mandaba a la ruta profesional (anclas de
carrera, "mover tu carrera") y le quitaba el re-chequeo y la práctica de
exámenes. El demo de Verónica lo manda a 12°. Lo que protegen estos tests:
 1. "Ya terminé el colegio" es colegio, cae en la ruta de 12° y NO se le pregunta
    el grado (ni lo bloquea para cerrar el onboarding).
 2. La etapa manda sobre un grado viejo (estaba en 11°, ahora terminó).
 3. Al guardar, la columna `users.grade` queda en 12: la malla, la guía y el plan
    la leen de ahí.
 4. Para el recomendador sigue siendo pregrado.
 5. El bot gratuito pasa "Ya me gradué" (del colegio) a esa etapa.
 6. El dashboard dice la etapa, para el encuadre del universitario.
"""
from __future__ import annotations

import pytest

from app.data import onboarding_hechos as cat
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401


def test_ya_termine_el_colegio_es_colegio_y_cae_en_doce():
    h = {"life_stage": "school_grad"}
    assert cat.perfil(h) == cat.PERFIL_COLEGIO
    assert cat.ruta(h) == "grado_12"


def test_no_se_le_pregunta_el_grado_ni_lo_bloquea():
    h = {"life_stage": "school_grad"}
    assert cat.aplica("grade", h) is False
    assert cat.es_obligatorio("grade", h) is False
    # A un colegial normal, sí.
    assert cat.es_obligatorio("grade", {"life_stage": "high_school"}) is True


def test_la_etapa_manda_sobre_un_grado_viejo():
    assert cat.grado_de({"life_stage": "school_grad", "grade": "11"}) == "12"
    assert cat.ruta({"life_stage": "school_grad", "grade": "11"}) == "grado_12"


def test_las_opciones_ya_no_son_ambiguas():
    [etapa] = [h for h in cat.HECHOS if h.id == "life_stage"]
    assert etapa.opciones["school_grad"] == "Ya terminé el colegio"
    assert etapa.opciones["recent_grad"] == "Recién graduado de la universidad"


def test_para_el_recomendador_es_pregrado():
    from app.services import academic_level

    assert academic_level.normalizar_etapa("school_grad") == academic_level.normalizar_etapa("high_school")


def test_el_bot_pasa_ya_me_gradue_a_esa_etapa():
    from app.services.bot_gratuito_traspaso import hechos_desde_respuestas

    h = hechos_desde_respuestas({"who": "colegio", "stage": "grad"})
    assert h["life_stage"] == "school_grad"
    assert "grade" not in h


@pytest.mark.planes_reales
def test_al_guardar_queda_en_doce_y_la_guia_es_la_de_doce(app_db):
    from datetime import datetime, timedelta

    from fastapi.testclient import TestClient

    from tests.test_planes_d1 import _plan, _usuario

    app, Sesion = app_db
    s = Sesion()
    u = _usuario(s, "termine@e6.dev")
    s.commit()
    _plan(s, u, "pago", datetime.utcnow() - timedelta(days=1))
    s.close()

    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": "termine@e6.dev", "password": "testpass123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        # El mismo PUT del formulario del onboarding.
        g = c.put("/api/v1/auth/me/onboarding", json={"answers": {"life_stage": "school_grad"}}, headers=h)
        assert g.status_code == 200, g.text
        d = c.get("/api/v1/me/dashboard", headers=h).json()

    s = Sesion()
    from app.db.models import User

    assert s.query(User).filter(User.email == "termine@e6.dev").one().grade == 12
    s.close()
    assert d["ruta"] == "grado_12"
    assert [t["id"] for t in d["tests_de_su_etapa"]] == ["recheck", "motivadores"]
    assert d["etapa"] == "school_grad"
