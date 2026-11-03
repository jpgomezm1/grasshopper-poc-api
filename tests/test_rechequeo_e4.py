"""E-4 · Sprint 4 · el re-chequeo de 12°: "¿qué tan listo estás para decidir?".

Decisión #4 del demo de Verónica: "re-chequeo corto: motivadores + confianza en
la decisión". Lo que protegen estos tests:
 1. Las 8 afirmaciones aprobadas por JP (2026-10-30), 2 por dimensión.
 2. Se califica con la escala genérica (0-100 por dimensión) y los extras dicen
    dónde está firme y qué le falta, de lo más flojo a lo más firme.
 3. Solo se le ofrece a 12°, y en la matriz va antes de Motivadores.
 4. La lectura le prohíbe a la IA dar una nota global y la hace empezar por lo
    que le falta.
"""
from __future__ import annotations

import pytest

from app.data.rechequeo import (
    CLARIDAD,
    INFORMACION,
    PLAN,
    PREGUNTAS,
    RESPALDO,
    TEST_ID,
    calcular_rechequeo,
)


def _respuestas(cla, inf, res, pla):
    valor = {"cla": cla, "inf": inf, "res": res, "pla": pla}
    return {p["id"]: valor[p["id"].split("-")[1]] for p in PREGUNTAS}


def test_ocho_afirmaciones_dos_por_dimension():
    assert len(PREGUNTAS) == 8
    por_dim = {}
    for p in PREGUNTAS:
        por_dim.setdefault(p["category"], []).append(p["text"])
    assert {k: len(v) for k, v in por_dim.items()} == {CLARIDAD: 2, INFORMACION: 2, RESPALDO: 2, PLAN: 2}
    assert "Tengo claro qué quiero estudiar el próximo año." in por_dim[CLARIDAD]
    assert any("cómo vamos a pagar mis estudios" in t for t in por_dim[PLAN])


def test_se_califica_de_0_a_100_y_dice_que_le_falta():
    # Escala de 0 a 100 de verdad (JP, 2026-11-02): 1 → 0, 5 → 100. Antes era la
    # genérica (suma/máximo) y el piso era 20.
    from app.services.scoring_service import derive_test_extras
    from app.data.vocational_tests import calculate_vocational_scores

    r = _respuestas(cla=5, inf=4, res=3, pla=1)
    scores = calculate_vocational_scores(TEST_ID, r)
    assert scores == {CLARIDAD: 100, INFORMACION: 75, RESPALDO: 50, PLAN: 0}
    extras = derive_test_extras(TEST_ID, r)
    assert extras["orden"] == [PLAN, RESPALDO, INFORMACION, CLARIDAD]
    assert extras["falta"] == [PLAN]
    assert extras["firme"] == [INFORMACION, CLARIDAD]
    assert extras["label"] == "Te falta: Plan"


@pytest.mark.parametrize(
    "scores, label",
    [
        ({CLARIDAD: 90, INFORMACION: 80, RESPALDO: 70, PLAN: 100}, "Listo para decidir"),
        ({CLARIDAD: 60, INFORMACION: 60, RESPALDO: 80, PLAN: 60}, "A medio camino"),
        ({CLARIDAD: 20, INFORMACION: 40, RESPALDO: 80, PLAN: 30}, "Te falta: Claridad y Plan"),
        ({}, None),
    ],
)
def test_la_etiqueta(scores, label):
    assert calcular_rechequeo(scores)["label"] == label


def test_solo_se_le_ofrece_a_doce():
    from app.data.vocational_tests import get_all_tests_summary

    for grado in (9, 10, 11, None):
        assert TEST_ID not in {t["id"] for t in get_all_tests_summary(grade=grado)}
    assert TEST_ID in {t["id"] for t in get_all_tests_summary(grade=12)}


def test_en_la_matriz_va_antes_de_motivadores():
    from app.data import permisos as matriz

    assert matriz.TESTS_POR_TRAMO["grado_12"] == ("recheck", "motivadores")


def test_la_lectura_empieza_por_lo_que_falta_y_no_da_nota():
    from app.services.test_interpretation_service import _label_map, _resultado_block

    assert set(_label_map(TEST_ID)) == {CLARIDAD, INFORMACION, RESPALDO, PLAN}
    extras = calcular_rechequeo({CLARIDAD: 90, INFORMACION: 80, RESPALDO: 60, PLAN: 20})
    bloque = _resultado_block(TEST_ID, {"_extras": extras})
    assert "NO des una nota" in bloque
    assert "Le falta: Plan" in bloque
    assert "Está firme en: Información · Claridad" in bloque


# ---------------------------------------------------------------------------
# De punta a punta · por HTTP
# ---------------------------------------------------------------------------

from tests.test_bot_gratuito_b4 import app_db  # noqa: E402,F401


@pytest.mark.planes_reales
@pytest.mark.parametrize("grado, esperado", [("12", 200), ("11", 402)])
def test_doce_lo_envia_y_queda_guardado_con_su_lectura(app_db, grado, esperado):
    from datetime import datetime, timedelta

    from fastapi.testclient import TestClient

    from app.data.disclaimer import DISCLAIMER_VERSION
    from app.db.models import VocationalTestResult
    from tests.test_planes_d1 import _plan, _usuario

    app, Sesion = app_db
    s = Sesion()
    u = _usuario(s, f"rc{grado}@e4.dev")
    u.onboarding_answers = {"life_stage": "high_school", "grade": grado}
    u.grade = int(grado)
    u.test_disclaimers = {TEST_ID: {"accepted_at": "hoy", "version": DISCLAIMER_VERSION}}
    s.commit()
    _plan(s, u, "pago", datetime.utcnow() - timedelta(days=1))
    uid = u.id
    s.close()

    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"email": f"rc{grado}@e4.dev", "password": "testpass123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        env = c.post(
            f"/api/v1/vocational-tests/{TEST_ID}/submit",
            json={"answers": _respuestas(5, 4, 3, 1)},
            headers=h,
        )
    # En 11° no es de su etapa: la llave del plan (D-3) lo frena igual que a
    # cualquier test fuera de su malla.
    assert env.status_code == esperado, env.text
    if esperado != 200:
        return
    s = Sesion()
    fila = s.query(VocationalTestResult).filter_by(user_id=uid, test_id=TEST_ID).one()
    assert fila.scores[PLAN] == 0
    assert fila.scores["_extras"]["label"] == "Te falta: Plan"
    s.close()
