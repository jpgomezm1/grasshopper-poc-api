"""D-7 · Sprint 4 · el acudiente y el plan del estudiante.

Revisado el 2026-10-30: el panel del acudiente (`/parent/...`) solo LEE lo que
el estudiante ya hizo (perfil, línea de tiempo, reportes ya generados, eventos,
mensajes, documentos legales). No genera nada con IA ni abre funciones pagas.
Encaja con la regla de D-3: leer lo hecho no se bloquea. Con un estudiante
gratis, simplemente hay menos que ver.

Este test deja eso fijo:
 1. El acudiente de un estudiante GRATIS ve su panel sin ningún 402.
 2. El acudiente pasa por rol (`pago`, origen `rol`): la llave no lo frena.
 3. Ninguna ruta del panel del acudiente lleva la llave del plan: si alguien se
    la pone, falla aquí y tiene que decidir si de verdad es pago.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _usuario

pytestmark = pytest.mark.planes_reales


@pytest.fixture()
def familia(app_db):
    from app.db.models import ParentRelationship, UserRole

    app, Sesion = app_db
    s = Sesion()
    hija = _usuario(s, "hija@d7.dev")  # estudiante sin plan → gratis
    hija.onboarding_answers = {"life_stage": "high_school", "grade": "11"}
    mama = _usuario(s, "mama@d7.dev", role=UserRole.PARENT)
    s.add(ParentRelationship(parent_user_id=mama.id, student_user_id=hija.id, relationship_type="madre"))
    s.commit()
    ids = {"hija": hija.id, "mama": mama.id}
    s.close()
    return app, Sesion, ids


def _h(c, email):
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_el_acudiente_de_un_gratis_ve_su_panel_sin_402(familia):
    app, _, ids = familia
    rutas = [
        "/api/v1/parent/me",
        f"/api/v1/parent/children/{ids['hija']}/profile",
        f"/api/v1/parent/children/{ids['hija']}/timeline",
        f"/api/v1/parent/children/{ids['hija']}/reports",
        "/api/v1/parent/events",
        "/api/v1/parent/messages",
    ]
    with TestClient(app, raise_server_exceptions=False) as c:
        h = _h(c, "mama@d7.dev")
        for ruta in rutas:
            r = c.get(ruta, headers=h)
            assert r.status_code != 402, (ruta, r.text)


def test_el_acudiente_pasa_por_rol(familia):
    app, Sesion, ids = familia
    from app.db.models import User
    from app.services import plan_service

    s = Sesion()
    mama = s.query(User).filter(User.id == ids["mama"]).first()
    hija = s.query(User).filter(User.id == ids["hija"]).first()
    assert (plan_service.plan_vigente(s, mama).plan, plan_service.plan_vigente(s, mama).origen) == ("pago", "rol")
    assert plan_service.plan_vigente(s, hija).plan == "gratis"
    s.close()


def test_ninguna_ruta_del_acudiente_lleva_la_llave_del_plan():
    """Si alguien le pone la llave a una ruta del acudiente, que decida a
    propósito: el panel es de lectura y la regla es no bloquear lo ya hecho."""
    from app.api.v1 import parent_panel
    from app.api.v1.llave_plan import requiere_ingles, requiere_lectura_nueva, requiere_test

    llaves = {requiere_test, requiere_ingles, requiere_lectura_nueva}
    for ruta in parent_panel.router.routes:
        deps = {d.call for d in ruta.dependant.dependencies}
        for d in ruta.dependant.dependencies:
            deps |= {sub.call for sub in d.dependencies}
        nombres = {getattr(f, "__qualname__", "") for f in deps}
        assert not (deps & llaves), ruta.path
        assert not any(n.startswith("requiere.<locals>") for n in nombres), ruta.path
