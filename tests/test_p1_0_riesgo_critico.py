"""P1-0 · Detector de riesgo crítico · Sprint 3 (2026-07-28).

El overlay determinista de `clinical_analysis_service` es la red de seguridad que
corre SIEMPRE, incluso si la IA falla o minimiza. Llevaba abierto desde junio con
tres defectos, dos de ellos silenciosos. Estos tests fijan el comportamiento para
que no vuelvan a aparecer.

El resultado solo lo ven psicóloga / asesor / super_admin (nunca el estudiante ni
la familia), así que el sesgo correcto es hacia el falso positivo.
"""
from __future__ import annotations

import pytest

from app.services.clinical_analysis_service import (
    CRITICAL_RISK_KEYWORDS,
    NEGATIVE_KEYWORDS,
    _matched_keywords,
    _normalize,
    _scan_keywords,
)


# ---------------------------------------------------------------------------
# Defecto 1 · las tildes hacían inútiles varias keywords
# ---------------------------------------------------------------------------


def test_normaliza_tildes():
    assert _normalize("PRESIÓN") == "presion"
    assert _normalize("Pánico") == "panico"
    assert _normalize("vacío") == "vacio"


@pytest.mark.parametrize(
    "texto,keyword",
    [
        ("Siento mucha presión de mis papás", "presion"),
        ("Me dan ataques de pánico antes de los exámenes", "panic"),
        ("Me siento vacío todo el tiempo", "vacio"),
    ],
)
def test_keywords_con_tilde_ahora_si_coinciden(texto, keyword):
    """Antes _scan_keywords solo hacía .lower(): 'presion' nunca encontraba 'presión'."""
    assert keyword in NEGATIVE_KEYWORDS
    assert _scan_keywords(texto, (keyword,)) == 1


# ---------------------------------------------------------------------------
# Defecto 2 · "quier morir" no podía coincidir con nada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "a veces quiero morir",
        "tengo ganas de morir",
        "ya no quiero vivir",
        "he pensado en quitarme la vida",
        "pienso en suicidarme",
        "me quiero morir",
        "a veces pienso en hacerme daño",
        "he pensado en cortarme",
        "estarían mejor sin mí",
    ],
)
def test_ideacion_explicita_es_detectada(texto):
    """La keyword vieja era 'quier morir', que no es substring de 'quiero morir'
    (después de 'quier' viene 'o') ni de 'quiere morir' (viene 'e'). Era la única
    keyword de ideación del sistema y no podía dispararse nunca."""
    assert _matched_keywords(texto, CRITICAL_RISK_KEYWORDS), f"sin detectar: {texto!r}"


def test_la_keyword_rota_ya_no_existe():
    assert "quier morir" not in NEGATIVE_KEYWORDS
    assert "quier morir" not in CRITICAL_RISK_KEYWORDS


# ---------------------------------------------------------------------------
# Defecto 3 · una señal aislada no levantaba nada (exigía >=2)
# ---------------------------------------------------------------------------


def test_una_sola_expresion_basta_para_riesgo_critico():
    """Una ideación explícita y aislada tiene que levantar la señal por sí sola."""
    corpus = "Todo bien con el colegio y mis amigos. A veces quiero morir. Me gusta dibujar."
    assert len(_matched_keywords(corpus, CRITICAL_RISK_KEYWORDS)) >= 1


def test_devuelve_cuales_coincidieron_no_solo_cuantas():
    """La psicóloga necesita saber QUÉ disparó la alerta para poder revisarlo."""
    encontradas = _matched_keywords("pienso en suicidarme", CRITICAL_RISK_KEYWORDS)
    assert "suicid" in encontradas


# ---------------------------------------------------------------------------
# No sobre-disparar: texto normal de orientación no puede levantar riesgo crítico
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Quiero estudiar diseño de modas y tener mi propia marca",
        "Me preocupa que mis papás prefieran que estudie algo más tradicional",
        "No sé qué carrera elegir, estoy confundida",
        "Me da miedo equivocarme de carrera",
        "",
    ],
)
def test_texto_normal_no_dispara_riesgo_critico(texto):
    assert _matched_keywords(texto, CRITICAL_RISK_KEYWORDS) == []


def test_riesgo_critico_esta_en_el_esquema():
    """Si no está en el Literal, Pydantic rechaza el patrón y la alerta se pierde."""
    from app.schemas.clinical import BehavioralPattern

    p = BehavioralPattern(
        pattern="riesgo_critico",
        confidence=0.95,
        evidence="test",
        severity="high",
        suggested_intervention="test",
    )
    assert p.pattern == "riesgo_critico"
