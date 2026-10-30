"""C-3 · Sprint 4 · la IA no hace cuentas de fechas a la vista.

En una prueba de Verónica (con la cuenta de su hija, en 11°), el onboarding
escribió: *"Con 16 años y graduándote en 2026 — perdón, en junio de 2028 —
tienes tiempo real para explorar"*. El prompt no le decía al modelo qué fecha
era hoy, así que hacía la cuenta de cabeza y se corregía en voz alta.

Lo que protegen estos tests:

 1. Que la fecha de hoy y los años de colegio que le quedan se le den
    **calculados en código** (`_bloque_momento`), igual que ya se hace con la
    edad.
 2. Que el año de graduación NO se calcule: depende del calendario del colegio
    (A o B), que no preguntamos. Por eso se dan años escolares, no un año.
 3. Que el prompt le prohíba inventar un año o un mes de graduación y
    corregirse en voz alta.
"""
from __future__ import annotations

from datetime import date

from app.core.ai_client import load_prompt
from app.services import onboarding_conversacional as conv

HOY = date(2026, 10, 29)


def _momento(**recolectados):
    return conv._bloque_momento(recolectados, HOY)


# ---------------------------------------------------------------------------
# La fecha
# ---------------------------------------------------------------------------


def test_siempre_dice_la_fecha_de_hoy_con_el_mes_en_palabras():
    assert "Hoy es 29 de octubre de 2026." in _momento()


def test_a_un_profesional_solo_se_le_da_la_fecha():
    """Sin grado no hay años de colegio que contar."""
    bloque = _momento(life_stage="professional")
    assert "Hoy es" in bloque
    assert "colegio" not in bloque


# ---------------------------------------------------------------------------
# Los años de colegio · con y sin saber hasta dónde llega el colegio
# ---------------------------------------------------------------------------


def test_once_en_colegio_que_llega_a_doce_le_quedan_dos():
    """El caso de la prueba: 11° en un colegio que llega a 12°."""
    assert "2 años escolares, incluido el que cursa ahora" in _momento(
        grade="11", school_last_grade="12",
    )


def test_once_en_colegio_que_llega_a_once_es_su_ultimo_ano():
    assert "el que cursa ahora es el último" in _momento(grade="11", school_last_grade="11")


def test_doce_siempre_es_el_ultimo_aunque_no_se_sepa_el_colegio():
    assert "el que cursa ahora es el último" in _momento(grade=12)


def test_sin_saber_el_colegio_se_da_un_rango_y_se_dice_por_que():
    """11° sin saber si el colegio llega a once o a doce: 1 o 2 años."""
    bloque = _momento(grade="11")
    assert "entre 1 y 2 años escolares" in bloque
    assert "once o a doce" in bloque


def test_noveno_y_decimo():
    assert "entre 3 y 4 años escolares" in _momento(grade="9")
    assert "2 años escolares" in _momento(grade="10", school_last_grade="11")
    assert "entre 2 y 3 años escolares" in _momento(grade="10", school_last_grade="unknown")


def test_si_los_datos_se_contradicen_no_adivina():
    """12° en un colegio que "llega a once": uno de los dos está mal y no se
    sabe cuál. Mejor no darle nada que darle un número inventado."""
    bloque = _momento(grade="12", school_last_grade="11")
    assert "colegio" not in bloque


def test_nunca_le_da_un_ano_de_graduacion():
    """El año depende del calendario (A o B), que no preguntamos."""
    for combinacion in (
        {"grade": "9"}, {"grade": "11", "school_last_grade": "12"}, {"grade": 12},
    ):
        bloque = conv._bloque_momento(combinacion, HOY)
        assert "gradu" not in bloque.lower()
        for anio in ("2027", "2028", "2029", "2030"):
            assert anio not in bloque


# ---------------------------------------------------------------------------
# El prompt
# ---------------------------------------------------------------------------


def test_el_prompt_tiene_donde_recibir_el_momento():
    assert "{momento}" in load_prompt(conv.PROMPT_NAME)


def test_el_prompt_prohibe_inventar_la_graduacion_y_corregirse_en_voz_alta():
    prompt = load_prompt(conv.PROMPT_NAME)
    assert "No calculas ni dices un año ni un mes de graduación" in prompt
    assert "Nunca te corriges en voz alta" in prompt


def test_al_modelo_le_llega_el_momento_ya_calculado(monkeypatch):
    """La punta que importa: que `responder` de verdad lo meta en el system
    prompt, y que no quede el marcador sin reemplazar."""
    capturado = {}

    def falso_extraer(mensaje, recolectados, **_):
        return {"life_stage": "high_school", "grade": "11", "school_last_grade": "12"}, []

    def falso_claude(mensajes, system, **_):
        capturado["system"] = system
        return "Cuéntame más.", {"model": "fake", "tokens_input": 1, "tokens_output": 1}

    monkeypatch.setattr(conv, "extraer", falso_extraer)
    monkeypatch.setattr(conv, "call_claude_chat", falso_claude)

    conv.responder("Estoy en once y mi colegio llega a doce", [], {}, session_id="t-c3")

    system = capturado["system"]
    assert "{momento}" not in system
    assert "Hoy es " in system
    assert "2 años escolares, incluido el que cursa ahora" in system
