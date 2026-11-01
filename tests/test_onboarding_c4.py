"""C-4 · Sprint 4 · el onboarding sigue siendo natural (probado con llamadas reales).

Lo que protegen estos tests:
 1. Lo que la persona cuenta en este mensaje llega al modelo marcado como NUEVO:
    sin la marca respondía "eso ya lo tenía" a algo que acababa de oír.
 2. Un dato que no corresponde a su etapa no se guarda (las materias de 9° en
    una estudiante de 11°).
 3. El prompt le dice que pregunte lo que toca y no vuelva a la pregunta
    anterior (insistía cuatro veces con la misma).

Las dos llamadas al modelo (el extractor y la respuesta) se reemplazan en el
módulo: lo que se prueba es lo que el código le arma al modelo.
"""
from __future__ import annotations

from app.services import onboarding_conversacional as oc

ONCE = {"life_stage": "high_school", "grade": "11", "international_interest": "intl_yes"}


def test_lo_nuevo_va_marcado():
    bloque = oc._bloque_recolectado({**ONCE, "school_last_grade": "11"}, {"school_last_grade"})
    lineas = bloque.splitlines()
    assert any("NUEVO" in l for l in lineas if "once o doce" in l)
    assert not any("NUEVO" in l for l in lineas if "exterior" in l.lower() or "estudiar" in l.lower())


def test_sin_nuevos_no_marca_nada():
    assert "NUEVO" not in oc._bloque_recolectado(dict(ONCE))


def _turno(monkeypatch, extraidos):
    sistema = {}

    def falso_extraer(mensaje, recolectados, **kw):
        return dict(extraidos), []

    def falso_chat(mensajes, system, **kw):
        sistema["texto"] = system
        return "Qué buena combinación.", {"model": "x"}

    monkeypatch.setattr(oc, "extraer", falso_extraer)
    monkeypatch.setattr(oc, "call_claude_chat", falso_chat)
    historial = [{"role": "assistant", "content": "hola"}, {"role": "user", "content": "x"}]
    _, actualizados, _ = oc.responder("me gustan la biología y la química", historial, dict(ONCE), session_id="t")
    return actualizados, sistema["texto"]


def test_un_dato_de_otra_etapa_no_se_guarda(monkeypatch):
    actualizados, _ = _turno(monkeypatch, {"g9_materias_favoritas": "biología y química"})
    assert "g9_materias_favoritas" not in actualizados


def test_lo_que_si_aplica_se_guarda_y_llega_marcado(monkeypatch):
    actualizados, sistema = _turno(monkeypatch, {"countries": ["canada", "spain"]})
    assert actualizados["countries"] == ["canada", "spain"]
    assert "NUEVO" in sistema


def test_el_prompt_pide_reconocer_lo_nuevo_y_no_volver_a_la_pregunta_anterior():
    from app.core.ai_client import load_prompt

    texto = load_prompt(oc.PROMPT_NAME)
    assert "Nunca le digas que ya lo sabías" in texto
    assert "aunque en tu mensaje anterior hayas preguntado otra cosa" in texto
