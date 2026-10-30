"""E-10 · Sprint 4 · "10 carreras afines" (10°) y "10 profesiones del futuro" (11°).

La malla de Verónica pide para 10° un "Reporte Vocacional Intermedio … → 10
carreras afines con su porqué" y para 11° "10 profesiones del futuro". El perfil
consolidado daba 3-5 familias con 3-6 carreras cada una: ninguna lista de 10, y
el prompt ni siquiera sabía en qué grado iba la persona.

Lo que protegen estos tests:
 1. El prompt le pide la lista SOLO a quien le toca (10° → carreras, 11° →
    profesiones; los demás, nada).
 2. La etapa entra al hash solo para 10° y 11°: esos perfiles se regeneran y
    traen su lista; los de las demás etapas no gastan IA de nuevo.
 3. De punta a punta (mockeando la llamada al SDK, no el servicio): la lista
    llega al perfil guardado.
 4. Una respuesta corta, larga o mal formada no tumba el perfil.
"""
from __future__ import annotations

import json

import pytest

from app.schemas.consolidated_profile import ConsolidatedProfile
from tests.test_bot_gratuito_b4 import app_db  # noqa: F401


def _perfil(**extra):
    base = {
        "summary_narrative": "n " * 130,
        "strengths": ["Liderazgo con ejecución", "Análisis frío", "Gestión de recursos"],
        "interests": ["Emprendimiento", "Finanzas", "Gestión"],
        "values": ["Autonomía"],
        "tests_used": ["bigfive"],
    }
    base.update(extra)
    return base


def _carrera(i):
    return {"name": f"Carrera {i}", "family": "Gestión y negocios", "why": "Porque contaste que organizaste la feria."}


def _inputs(etapa=None):
    i = {"demographic": {}, "tests": [], "journey_answers": {}, "onboarding": {}, "activities": []}
    if etapa:
        i["etapa"] = etapa
    return i


# ---------------------------------------------------------------------------
# 1 · El prompt
# ---------------------------------------------------------------------------


def test_a_decimo_le_pide_diez_carreras_y_no_profesiones():
    from app.services.consolidation_service import render_consolidate_prompt

    p = render_consolidate_prompt(_inputs("grado_10"))
    assert "VA EN GRADO 10" in p and "EXACTAMENTE 10 carreras" in p
    assert "Deja `profesiones_del_futuro` vacío" in p


def test_a_once_le_pide_diez_profesiones_sin_cifras():
    from app.services.consolidation_service import render_consolidate_prompt

    p = render_consolidate_prompt(_inputs("grado_11"))
    assert "VA EN GRADO 11" in p and "EXACTAMENTE 10 profesiones" in p
    assert "SIN cifras" in p


def test_a_los_demas_no_les_pide_lista():
    from app.services.consolidation_service import render_consolidate_prompt

    p = render_consolidate_prompt(_inputs())
    assert "no está en 10° ni en 11°" in p
    assert "VA EN GRADO" not in p


# ---------------------------------------------------------------------------
# 2 · La etapa en el hash, solo para 10° y 11°
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "respuestas, etapa",
    [
        ({"life_stage": "high_school_early", "grade": "10"}, "grado_10"),
        ({"life_stage": "high_school", "grade": "11"}, "grado_11"),
        ({"life_stage": "high_school_early", "grade": "9"}, None),
        ({"life_stage": "working"}, None),
    ],
)
def test_la_etapa_entra_solo_para_decimo_y_once(app_db, respuestas, etapa):
    from app.services.consolidation_service import gather_user_inputs
    from tests.test_planes_d1 import _usuario

    _, Sesion = app_db
    s = Sesion()
    u = _usuario(s, f"etapa{respuestas.get('grade', 'p')}@e10.dev")
    u.onboarding_answers = respuestas
    s.commit()
    assert gather_user_inputs(s, u).get("etapa") == etapa
    s.close()



# ---------------------------------------------------------------------------
# 3 · De punta a punta
# ---------------------------------------------------------------------------


def test_de_punta_a_punta_la_lista_llega_al_perfil_guardado(app_db, monkeypatch):
    from app.db.models import VocationalTestResult
    from app.services import consolidation_service as cs
    from tests.test_planes_d1 import _usuario

    _, Sesion = app_db
    s = Sesion()
    u = _usuario(s, "decimo@e10.dev")
    u.onboarding_answers = {"life_stage": "high_school_early", "grade": "10"}
    s.add(VocationalTestResult(user_id=u.id, test_id="bigfive", scores={"O": 70}, answers={}))
    s.commit()

    prompts = []

    def sdk_falso(prompt, **kw):
        prompts.append((prompt, kw))
        salida = _perfil(carreras_afines=[_carrera(i) for i in range(10)])
        return json.dumps(salida), {"model": "claude-test", "tokens_input": 1, "tokens_output": 1}

    monkeypatch.setattr(cs, "call_claude_with_meta", sdk_falso)
    perfil, fila, cacheado = cs.generate_or_get_profile(s, u)

    assert not cacheado
    assert "VA EN GRADO 10" in prompts[0][0]
    assert prompts[0][1]["max_tokens"] == 6000
    assert [c.name for c in perfil.carreras_afines] == [f"Carrera {i}" for i in range(10)]
    assert len(fila.profile_data["carreras_afines"]) == 10
    assert fila.profile_data["profesiones_del_futuro"] == []
    s.close()


# ---------------------------------------------------------------------------
# 4 · Tolerancia
# ---------------------------------------------------------------------------


def test_si_trae_menos_de_diez_se_muestra_lo_que_hay():
    p = ConsolidatedProfile.model_validate(_perfil(carreras_afines=[_carrera(i) for i in range(7)]))
    assert len(p.carreras_afines) == 7


def test_si_trae_mas_de_diez_se_toman_las_diez_primeras():
    p = ConsolidatedProfile.model_validate(_perfil(carreras_afines=[_carrera(i) for i in range(12)]))
    assert [c.name for c in p.carreras_afines] == [f"Carrera {i}" for i in range(10)]


def test_si_no_es_una_lista_queda_vacia_y_el_perfil_sobrevive():
    p = ConsolidatedProfile.model_validate(_perfil(profesiones_del_futuro="no sé"))
    assert p.profesiones_del_futuro == []


def test_los_perfiles_de_antes_siguen_siendo_validos():
    p = ConsolidatedProfile.model_validate(_perfil())
    assert p.carreras_afines == [] and p.profesiones_del_futuro == []
