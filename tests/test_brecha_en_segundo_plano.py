"""Recorridos Sprint 4 · el análisis de brecha en segundo plano.

En producción (2026-11-02): ninguna pantalla lanzaba el análisis, y la ruta que
existía (`/analyze`) tarda más de 30 s, así que el router de Heroku cortaba la
respuesta aunque el análisis sí se guardaba. Lo que protegen estos tests:

 1. La ruta nueva responde 202 enseguida y el trabajo deja el análisis guardado
    con estado "listo".
 2. Si falta el LinkedIn procesado pero está el texto del onboarding, lo procesa
    primero (no se le vuelve a pedir).
 3. Si algo falla, el estado queda "fallido" con un mensaje: nunca "en curso"
    para siempre.
 4. No lanza dos a la vez.
 5. Los tres programas se guardan junto al análisis del que salieron.

`TestClient` corre las tareas en segundo plano al terminar la respuesta, así
que el resultado se ve en la siguiente consulta. Se reemplazan los dos servicios
de IA (probados en sus propios tests) por respuestas fijas.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.services import career_gap_service, linkedin_import_service
from tests.test_career_gap import _headers, _student, app_with_db  # noqa: F401

URL = "/api/v1/me/career-gap"
ANALISIS = {"resumen": "Te falta poco.", "brechas": [{"area": "SQL avanzado", "impacto": "alto"}], "plan_upskilling": []}
META = {"model": "x", "tokens_input": 1, "tokens_output": 1, "latency_ms": 1}


@pytest.fixture()
def ia(monkeypatch):
    llamadas = {"linkedin": 0, "analisis": 0}

    def importar(texto):
        llamadas["linkedin"] += 1
        return {"headline": "Analista"}, META

    def analizar(**kw):
        llamadas["analisis"] += 1
        assert kw["perfil_linkedin"] == {"headline": "Analista"}
        return ANALISIS, META

    monkeypatch.setattr(linkedin_import_service, "importar_desde_texto", importar)
    monkeypatch.setattr(career_gap_service, "analizar", analizar)
    return llamadas


PROFESIONAL = {
    "life_stage": "working",
    "career_target_role": "Analista de datos",
    "career_linkedin_profile_text": "Administrador con 6 años en reportes.",
}


def test_responde_202_y_deja_el_analisis_listo(app_with_db, ia):  # noqa: F811
    app, Sesion = app_with_db
    _student(Sesion, "bg1@e.dev", dict(PROFESIONAL))
    with TestClient(app) as c:
        h = _headers(c, "bg1@e.dev")
        antes = c.get(URL, headers=h).json()
        assert antes["can_start_analysis"] is True and antes["analysis"] is None
        r = c.post(f"{URL}/analizar-en-segundo-plano", headers=h)
        assert r.status_code == 202 and r.json() == {"estado": "en_curso"}
        despues = c.get(URL, headers=h).json()
    assert despues["analysis_status"] == "listo"
    assert despues["analysis"]["resumen"] == "Te falta poco."
    # Procesó primero el LinkedIn del onboarding, una sola vez.
    assert ia == {"linkedin": 1, "analisis": 1}
    assert despues["linkedin_profile"] == {"headline": "Analista"}


def test_si_falla_queda_fallido_con_mensaje(app_with_db, monkeypatch):  # noqa: F811
    app, Sesion = app_with_db
    _student(Sesion, "bg2@e.dev", dict(PROFESIONAL))

    def roto(texto):
        raise linkedin_import_service.LinkedInImportError("el proveedor no responde")

    monkeypatch.setattr(linkedin_import_service, "importar_desde_texto", roto)
    with TestClient(app) as c:
        h = _headers(c, "bg2@e.dev")
        assert c.post(f"{URL}/analizar-en-segundo-plano", headers=h).status_code == 202
        estado = c.get(URL, headers=h).json()
    assert estado["analysis_status"] == "fallido"
    assert "Inténtalo de nuevo" in estado["analysis_error"]


def test_sin_puesto_ideal_ni_linkedin_responde_409(app_with_db, ia):  # noqa: F811
    app, Sesion = app_with_db
    _student(Sesion, "bg3@e.dev", {"life_stage": "working"})
    with TestClient(app) as c:
        r = c.post(f"{URL}/analizar-en-segundo-plano", headers=_headers(c, "bg3@e.dev"))
    assert r.status_code == 409
    assert set(r.json()["detail"]["missing"]) == {"linkedin_profile", "target_role"}


def test_no_lanza_dos_a_la_vez(app_with_db, ia):  # noqa: F811
    from datetime import datetime, timezone

    app, Sesion = app_with_db
    _student(Sesion, "bg4@e.dev", {
        **PROFESIONAL,
        "career_gap_analysis_status": "en_curso",
        "career_gap_analysis_started_at": datetime.now(timezone.utc).isoformat(),
    })
    with TestClient(app) as c:
        r = c.post(f"{URL}/analizar-en-segundo-plano", headers=_headers(c, "bg4@e.dev"))
    assert r.status_code == 202
    assert ia == {"linkedin": 0, "analisis": 0}  # no se lanzó otro


def test_los_programas_se_guardan_con_su_analisis(monkeypatch):
    from app.services import busqueda_programas as bp
    from app.services import programas_para_la_brecha as ppb

    busquedas = {"n": 0}
    monkeypatch.setattr(bp, "perfil_del_usuario", lambda db, u: SimpleNamespace(etapa_de_vida="working", codigos_riasec=()))
    monkeypatch.setattr(ppb, "_vector", lambda t: [1.0])

    def buscar(db, **kw):
        busquedas["n"] += 1
        return [SimpleNamespace(id=f"p{busquedas['n']}", nombre="P", institucion="I", pais=None, ciudad=None,
                                nivel="curso", duracion=None, url_fuente=None, program_id=None, confianza=None)]

    monkeypatch.setattr(bp, "buscar", buscar)
    db = SimpleNamespace(commit=lambda: None)
    user = SimpleNamespace(id="u", onboarding_answers={
        "career_gap_analysis": ANALISIS, "career_gap_analysis_generated_at": "2026-11-02T20:00:00",
        "career_target_role": "Analista",
    })
    primera = ppb.elegir(db, user)
    hechas = busquedas["n"]
    segunda = ppb.elegir(db, user)
    assert segunda == primera and busquedas["n"] == hechas  # la segunda no buscó

    # Un análisis nuevo (otra fecha) recalcula.
    user.onboarding_answers = {**user.onboarding_answers, "career_gap_analysis_generated_at": "2026-11-03T09:00:00"}
    ppb.elegir(db, user)
    assert busquedas["n"] > hechas
