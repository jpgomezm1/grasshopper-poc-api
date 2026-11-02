"""E-5 · Sprint 4 · tres programas reales para cerrar la brecha profesional.

Lo que protegen estos tests:
 1. Los conceptos: el puesto ideal y hasta dos brechas de impacto alto o medio.
 2. Un programa por concepto, con su "para qué", y sin repetir programas.
 3. Si hay menos de tres conceptos, se completa hasta tres.
 4. Si el proveedor de vectores falla, lista vacía: nunca programas al azar.
 5. Por HTTP: 404 sin análisis; con análisis, los programas.

`bp.buscar` corre sobre pgvector y aquí la base es SQLite: se reemplaza la
búsqueda (probada en sus propios tests) y el proveedor de vectores, que es la
frontera externa. Lo que se prueba es la lógica de este módulo.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services import programas_para_la_brecha as ppb
from tests.test_career_gap import _headers, _student, app_with_db  # noqa: F401

ANALISIS = {
    "resumen": "Te falta poco.",
    "brechas": [
        {"area": "Comunicación con clientes", "impacto": "bajo"},
        {"area": "SQL avanzado", "impacto": "alto"},
        {"area": "Inglés B2", "impacto": "medio"},
        {"area": "Python", "impacto": "alto"},
    ],
    "plan_upskilling": [{"brecha": "SQL avanzado", "como_cerrarla": "Un curso", "tipo": "curso", "prioridad": "alta"}],
}


def _programa(id_, nombre):
    return SimpleNamespace(
        id=id_, nombre=nombre, institucion="Universidad X", pais="Colombia", ciudad="Bogotá",
        nivel="Especialización", duracion="1 año", url_fuente="https://x.edu", program_id="p1",
        confianza="verificable",
    )


def test_conceptos_puesto_ideal_y_brechas_importantes():
    assert ppb.conceptos(ANALISIS, "Analista de datos") == ["Analista de datos", "SQL avanzado", "Python"]
    # Sin puesto ideal: las brechas, primero las de impacto alto.
    assert ppb.conceptos(ANALISIS, None) == ["SQL avanzado", "Python", "Inglés B2"]
    # Las de impacto bajo no entran.
    assert "Comunicación con clientes" not in ppb.conceptos(ANALISIS, "X")


def _usuario(respuestas):
    return SimpleNamespace(onboarding_answers=respuestas)


def _preparar(monkeypatch, resultados_por_concepto, vector_ok=True):
    from app.services import busqueda_programas as bp

    monkeypatch.setattr(bp, "perfil_del_usuario", lambda db, u: SimpleNamespace(etapa_de_vida="working", codigos_riasec=()))
    monkeypatch.setattr(ppb, "_vector", lambda texto: ([1.0, float(len(texto))] if vector_ok else None))

    def buscar(db, vector_perfil=None, **kw):
        # El segundo valor del vector "dice" qué concepto se buscó.
        return resultados_por_concepto[int(vector_perfil[1])]

    monkeypatch.setattr(bp, "buscar", buscar)


def test_un_programa_por_concepto_con_su_para_que_y_sin_repetir(monkeypatch):
    puesto = "Analista de datos"
    _preparar(monkeypatch, {
        len(puesto): [_programa("a", "Analítica de datos"), _programa("b", "BI")],
        len("SQL avanzado"): [_programa("a", "Analítica de datos"), _programa("c", "Bases de datos")],
        len("Python"): [_programa("d", "Programación en Python")],
    })
    datos = ppb.elegir(None, _usuario({"career_gap_analysis": ANALISIS, "career_target_role": puesto}))
    assert [p["id"] for p in datos["programas"]] == ["a", "c", "d"]  # "a" no se repite
    assert [p["para"] for p in datos["programas"]] == [puesto, "SQL avanzado", "Python"]


def test_con_un_solo_concepto_completa_hasta_tres(monkeypatch):
    analisis = {"brechas": []}
    puesto = "Gerente de producto"
    _preparar(monkeypatch, {len(puesto): [_programa(str(i), f"P{i}") for i in range(5)]})
    datos = ppb.elegir(None, _usuario({"career_gap_analysis": analisis, "career_target_role": puesto}))
    assert len(datos["programas"]) == 3


def test_sin_proveedor_de_vectores_no_inventa(monkeypatch):
    _preparar(monkeypatch, {}, vector_ok=False)
    datos = ppb.elegir(None, _usuario({"career_gap_analysis": ANALISIS, "career_target_role": "X"}))
    assert datos["programas"] == []


def test_sin_analisis_devuelve_none():
    assert ppb.elegir(None, _usuario({})) is None


URL = "/api/v1/me/professional/programas-para-tu-brecha"


def test_http_404_sin_analisis_y_200_con_el(app_with_db, monkeypatch):  # noqa: F811
    app, Sesion = app_with_db
    _student(Sesion, "sin@e5.dev", {"life_stage": "working"})
    _student(Sesion, "con@e5.dev", {
        "life_stage": "working", "career_gap_analysis": ANALISIS, "career_target_role": "Analista de datos",
    })
    _preparar(monkeypatch, {
        len("Analista de datos"): [_programa("a", "Analítica")],
        len("SQL avanzado"): [_programa("b", "SQL")],
        len("Python"): [_programa("c", "Python")],
    })
    with TestClient(app) as c:
        assert c.get(URL, headers=_headers(c, "sin@e5.dev")).status_code == 404
        r = c.get(URL, headers=_headers(c, "con@e5.dev"))
    assert r.status_code == 200, r.text
    assert len(r.json()["programas"]) == 3
