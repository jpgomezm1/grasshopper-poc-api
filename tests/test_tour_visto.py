"""Auditoría 2026-11-02 · E11-4: el recorrido de bienvenida se recuerda en la cuenta.

Antes vivía solo en `localStorage` y volvía a salir en cada navegador. Ahora
`POST /auth/me/tour-visto` lo marca y `/auth/me` lo devuelve en `tour_visto`.
"""
from fastapi.testclient import TestClient

from tests.test_sprint8_super_admin import _login, _make_super_admin, app_with_db  # noqa: F401


def test_el_tour_queda_marcado_en_la_cuenta(app_with_db):  # noqa: F811
    app, SessionLocal = app_with_db
    _make_super_admin(SessionLocal)
    client = TestClient(app)
    H = {"Authorization": f"Bearer {_login(client, 'root@grasshopper.example.com', 'rootpass123')}"}

    assert client.get("/api/v1/auth/me", headers=H).json()["tour_visto"] is False
    assert client.post("/api/v1/auth/me/tour-visto", headers=H).status_code == 204
    assert client.get("/api/v1/auth/me", headers=H).json()["tour_visto"] is True
    # Idempotente.
    assert client.post("/api/v1/auth/me/tour-visto", headers=H).status_code == 204
