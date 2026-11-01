"""F-2 / F-4 · Sprint 4 · programas estatales y empresas sobre la maquinaria del colegio.

Lo que protegen estos tests:
 1. Una organización se crea con su tipo (colegio, programa, empresa) y un tipo
    inválido se rechaza.
 2. El personal de un programa o una empresa NO ve datos individuales: lista,
    detalle, exportación, reportes con nombres, buzón y `/schools/{id}/students`
    responden 403. Lo operativo (invitar, alta masiva, mensajes) sigue abierto.
 3. Un colegio sigue viendo todo como antes.
 4. El tablero: sin desglose con menos de 5 participantes; las categorías con
    menos de 5 personas se juntan en "Otros" o se ocultan; nunca un correo.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_sprint9_school_panel import _login, _make_school, _make_school_user, _make_super


def _org(client, Sesion, slug, tipo=None):
    _make_super(Sesion, email=f"root.{slug}@gh.dev")
    root = _login(client, f"root.{slug}@gh.dev", "rootpass123")
    school_id = _make_school(client, root, f"Org {slug}", slug)
    if tipo:
        r = client.patch(f"/api/v1/schools/{school_id}", json={"tipo": tipo}, headers={"Authorization": f"Bearer {root}"})
        assert r.status_code == 200, r.text
    _make_school_user(Sesion, school_id, f"admin@{slug}.dev", "school_admin")
    return school_id, {"Authorization": f"Bearer {_login(client, f'admin@{slug}.dev', 'schoolpass123')}"}


def _alumnos(Sesion, school_id, filas):
    """filas: lista de dicts de onboarding_answers, uno por estudiante."""
    from app.api.v1.auth import get_password_hash
    from app.db.models import OnboardingStatus, User, UserRole

    s = Sesion()
    for n, respuestas in enumerate(filas):
        s.add(User(
            email=f"p{n}.{school_id}@x.dev", hashed_password=get_password_hash("x12345678"),
            role=UserRole.STUDENT, school_id=UUID(str(school_id)),
            onboarding_status=OnboardingStatus.COMPLETED, onboarding_answers=dict(respuestas),
        ))
    s.commit()
    s.close()


# --- 1 · el tipo ----------------------------------------------------------------


def test_se_crea_con_su_tipo_y_un_tipo_invalido_se_rechaza(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        _make_super(Sesion, email="root.t@gh.dev")
        h = {"Authorization": f"Bearer {_login(c, 'root.t@gh.dev', 'rootpass123')}"}
        r = c.post("/api/v1/schools", json={"name": "Programa Futuro", "slug": "programa-futuro", "tipo": "programa"}, headers=h)
        assert r.status_code == 201, r.text
        assert r.json()["tipo"] == "programa"
        r = c.post("/api/v1/schools", json={"name": "Otra", "slug": "otra", "tipo": "ong"}, headers=h)
        assert r.status_code == 422


# --- 2-3 · la lista blanca ----------------------------------------------------


@pytest.mark.parametrize("tipo", ["programa", "empresa"])
def test_programa_y_empresa_no_ven_datos_individuales(app_db, tipo):
    app, Sesion = app_db
    with TestClient(app) as c:
        school_id, h = _org(c, Sesion, f"org-{tipo}", tipo)
        for metodo, ruta in [
            ("get", "/api/v1/school/me/students"),
            ("get", "/api/v1/school/me/students/export.csv"),
            ("get", "/api/v1/school/me/reports"),
            ("get", "/api/v1/school/me/dashboard"),
            ("get", "/api/v1/school/me/dashboard-rich"),
            ("get", "/api/v1/school/me/risk-alerts"),
            ("get", "/api/v1/school/me/cases"),
            ("get", "/api/v1/school/counselor-sync"),
            ("get", f"/api/v1/schools/{school_id}/students"),
        ]:
            r = getattr(c, metodo)(ruta, headers=h)
            assert r.status_code == 403, (ruta, r.status_code)
            assert r.json()["detail"]["code"] == "solo_agregado", ruta
        # Lo operativo sigue abierto.
        assert c.get("/api/v1/school/me", headers=h).status_code == 200
        assert c.get("/api/v1/school/me/invitations", headers=h).status_code == 200
        assert c.get("/api/v1/school/me/tablero", headers=h).status_code == 200
        r = c.post("/api/v1/school/me/students/bulk-invite", json={"emails": ["nuevo@x.dev"]}, headers=h)
        assert r.status_code != 403, r.text


def test_un_colegio_sigue_viendo_todo(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        _, h = _org(c, Sesion, "colegio-x")
        assert c.get("/api/v1/school/me/students", headers=h).status_code == 200
        assert c.get("/api/v1/school/me/reports", headers=h).status_code == 200
        assert c.get("/api/v1/school/me/dashboard", headers=h).status_code == 200


# --- 4 · el tablero -------------------------------------------------------------


def test_con_menos_de_5_participantes_no_hay_desglose(app_db):
    app, Sesion = app_db
    with TestClient(app) as c:
        school_id, h = _org(c, Sesion, "prog-chico", "programa")
        _alumnos(Sesion, school_id, [{"life_stage": "high_school", "grade": "11"}] * 4)
        t = c.get("/api/v1/school/me/tablero", headers=h).json()
    assert t["participantes"] == 4
    assert t["suficientes"] is False
    assert "por_etapa" not in t


def test_los_grupos_pequenos_se_juntan_o_se_ocultan_y_nunca_sale_un_correo(app_db):
    app, Sesion = app_db
    once = {"life_stage": "high_school", "grade": "11", "international_interest": "intl_no"}
    diez = {"life_stage": "high_school_early", "grade": "10", "international_interest": "intl_yes"}
    with TestClient(app) as c:
        school_id, h = _org(c, Sesion, "prog-grande", "programa")
        _alumnos(Sesion, school_id, [once] * 6 + [diez] * 2)
        r = c.get("/api/v1/school/me/tablero", headers=h)
    t = r.json()
    assert t["suficientes"] is True and t["participantes"] == 8
    assert t["por_etapa"] == [{"categoria": "11°", "personas": 6}]  # los 2 de 10° no salen
    assert t["destino"] == [{"categoria": "En Colombia", "personas": 6}]
    assert t["avance"]["completaron_la_conversacion_inicial"] == 8
    assert "@" not in r.text


def test_otros_aparece_cuando_juntos_llegan_al_minimo(app_db):
    from app.services import tablero_anonimo_service as svc
    from collections import Counter

    filas = svc._desglose(Counter({"a": 7, "b": 3, "c": 2}), {"a": "A"})
    assert filas == [{"categoria": "A", "personas": 7}, {"categoria": "Otros", "personas": 5}]


def test_un_programa_no_invita_psicologas_pero_si_participantes(app_db):
    """Una psicóloga ve a cada persona; en un programa o una empresa no corresponde."""
    app, Sesion = app_db
    with TestClient(app) as c:
        _, h = _org(c, Sesion, "prog-equipo", "programa")
        r = c.post("/api/v1/school/me/invitations", json={"email": "psy@x.dev", "role": "psychologist"}, headers=h)
        assert r.status_code == 403
        r = c.post("/api/v1/school/me/invitations", json={"email": "part@x.dev", "role": "student"}, headers=h)
        assert r.status_code != 403, r.text
