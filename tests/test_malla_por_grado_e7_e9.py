"""E-7 / E-8 / E-9 · Sprint 4 · lo que ya estaba resuelto, fijado.

Revisado el 2026-10-30:

- **E-7 · el grado.** El onboarding (formulario y chat) y el bot gratuito
  escriben `user.grade` por el mismo camino (`_sync_onboarding_to_user_columns`).
  Ya lo prueban `test_bot_gratuito_traspaso_b7` (el bot deja `grade == 11`) y
  `test_year_memory_writer` (el onboarding). Aquí no se repite.
- **E-8 · pasar de año.** La foto del año que se va ya la prueba
  `test_year_memory_writer`. Lo nuevo de Sprint 4 es lo que eso arrastra: la
  malla (y con ella la guía) cambia sola, y el plan NO, porque el plan no
  depende del grado. Eso se prueba aquí, de punta a punta.
- **E-9 · la lectura en palabras fáciles.** Los 9 tests de la matriz tienen
  sus dimensiones con nombre legible. Si alguien suma un test a la matriz sin
  su lectura, la IA recibiría claves crudas: falla aquí.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.test_bot_gratuito_b4 import app_db  # noqa: F401
from tests.test_planes_d1 import _plan, _usuario


@pytest.mark.planes_reales
def test_pasar_de_decimo_a_once_cambia_la_guia_y_no_el_plan(app_db):
    from app.api.v1.auth import _sync_onboarding_to_user_columns
    from app.db.models import StudentYearSnapshot, User
    from app.services import plan_service

    app, Sesion = app_db
    s = Sesion()
    u = _usuario(s, "e8@malla.dev")
    respuestas = {"life_stage": "high_school_early", "grade": "10"}
    u.onboarding_answers = respuestas
    _sync_onboarding_to_user_columns(u, respuestas, s)
    s.commit()
    hasta = datetime.utcnow() + timedelta(days=200)
    _plan(s, u, "pago", datetime.utcnow() - timedelta(days=1), hasta)
    s.close()

    def guia():
        with TestClient(app) as c:
            r = c.post("/api/v1/auth/login", json={"email": "e8@malla.dev", "password": "testpass123"})
            h = {"Authorization": f"Bearer {r.json()['access_token']}"}
            return [t["id"] for t in c.get("/api/v1/me/dashboard", headers=h).json()["tests_de_su_etapa"]]

    assert guia() == ["bigfive", "habilidades-blandas", "motivadores"]

    # Pasa de año: el mismo camino que usa el onboarding al guardar.
    s = Sesion()
    u = s.query(User).filter(User.email == "e8@malla.dev").first()
    respuestas = {"life_stage": "high_school", "grade": "11"}
    u.onboarding_answers = respuestas
    _sync_onboarding_to_user_columns(u, respuestas, s)
    s.commit()
    assert u.grade == 11
    # La foto del año que se fue (para el check-in de evolución).
    assert s.query(StudentYearSnapshot).filter(StudentYearSnapshot.user_id == u.id).count() == 1
    vigente = plan_service.plan_vigente(s, u)
    assert (vigente.plan, vigente.hasta) == ("pago", hasta)
    s.close()

    assert guia() == ["istrong", "mbti", "bigfive"]


def test_cada_test_de_la_matriz_tiene_su_lectura():
    from app.data import permisos as matriz
    from app.services.test_interpretation_service import _label_map

    todos = {t for tests in matriz.TESTS_POR_TRAMO.values() for t in tests}
    sin_lectura = sorted(t for t in todos if not _label_map(t))
    assert sin_lectura == [], f"Tests de la matriz sin lectura en palabras fáciles: {sin_lectura}"
