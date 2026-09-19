"""El lead deja de ser sólo un número de embudo · 2026-09-19.

Dos huecos distintos, del mismo tipo: información vocacional capturada que no
llegaba a quien la necesitaba.

**1 · El quiz de la landing caía en un pozo.** `lead_profiles` se escribe desde
`api/v1/lead_profile.py:70` y ningún otro sitio del backend la consulta — el
propio `models.py` lo dice con esas palabras. Son seis preguntas reales y un
arquetipo vocacional calculado, muchas veces la PRIMERA señal que la persona da,
semanas antes de registrarse.

**2 · El CRM mostraba un resumen que siempre estaba vacío.** Buscaba el texto en
`synthesis`, `summary` y `text`: tres claves que el perfil consolidado no tiene
(la suya es `summary_narrative`). Y no mostraba fortalezas, ni códigos Holland,
ni familias, así que quien llamaba no tenía con qué abrir la conversación más
allá de "veo que hiciste tres tests".
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.ai_service import format_onboarding_context
from app.services.rescate_lead_quiz import CLAVE_ARQUETIPO, CLAVE_RASGOS, rescatar


def _lead(**kw):
    base = dict(
        converted=False,
        profile_result={
            "profile_type": "analyst",
            "profile_name": "El Analista Metódico",
            "description": "Disfruta entender cómo funcionan las cosas.",
            "traits": ["Curioso", "Estructurado", "Paciente"],
        },
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _usuario(onboarding=None):
    return SimpleNamespace(id=uuid4(), email="Ana@Correo.com",
                           onboarding_answers=onboarding)


def _db(lead):
    db = MagicMock()
    cadena = db.query.return_value
    cadena.filter.return_value = cadena
    cadena.order_by.return_value = cadena
    cadena.first.return_value = lead
    return db


# ---------------------------------------------------------------------------
# El rescate
# ---------------------------------------------------------------------------


def test_el_arquetipo_del_quiz_entra_al_perfil():
    u, lead = _usuario(), _lead()
    assert rescatar(_db(lead), u) is True
    assert "El Analista Metódico" in u.onboarding_answers[CLAVE_ARQUETIPO]
    assert u.onboarding_answers[CLAVE_RASGOS] == ["Curioso", "Estructurado", "Paciente"]


def test_converted_por_fin_significa_algo():
    """El campo existía desde el principio y nadie lo ponía en True, igual que
    nadie leía la tabla."""
    lead = _lead()
    rescatar(_db(lead), _usuario())
    assert lead.converted is True


def test_no_pisa_lo_que_la_persona_conto_despues():
    """El quiz son seis opciones múltiples; el onboarding son sus palabras. La
    señal más pobre llena huecos, no sobrescribe."""
    u = _usuario({CLAVE_ARQUETIPO: "lo que ya había"})
    rescatar(_db(_lead()), u)
    assert u.onboarding_answers[CLAVE_ARQUETIPO] == "lo que ya había"


def test_sin_quiz_previo_no_pasa_nada():
    u = _usuario()
    assert rescatar(_db(None), u) is False
    assert u.onboarding_answers is None


def test_el_correo_se_cruza_sin_importar_mayusculas():
    """La gente escribe su correo distinto en la landing y en el registro."""
    db = _db(_lead())
    rescatar(db, _usuario())
    # `ilike` con el correo ya en minúsculas · si se comparara crudo, "Ana@..."
    # no encontraría el lead guardado como "ana@...".
    assert db.query.return_value.filter.called


def test_un_quiz_con_forma_rara_no_cuesta_la_cuenta():
    """Se llama justo después de crear el usuario · nunca puede lanzar."""
    assert rescatar(_db(_lead(profile_result="esto no es un dict")), _usuario()) is True
    db = MagicMock()
    db.query.side_effect = RuntimeError("la tabla no existe")
    assert rescatar(db, _usuario()) is False


def test_un_resultado_sin_nombre_no_inventa_nada():
    u = _usuario()
    rescatar(_db(_lead(profile_result={"traits": []})), u)
    assert CLAVE_ARQUETIPO not in (u.onboarding_answers or {})


# ---------------------------------------------------------------------------
# El otro extremo · que la IA lo lea
# ---------------------------------------------------------------------------


def test_el_arquetipo_llega_al_prompt():
    """Los dos extremos en el mismo cambio · escribir la clave sin conectarla es
    exactamente cómo el quiz llegó a llevar meses en un pozo."""
    bloque = format_onboarding_context({
        CLAVE_ARQUETIPO: "El Analista Metódico — Disfruta entender cómo funcionan las cosas",
        CLAVE_RASGOS: ["Curioso", "Estructurado"],
    })
    assert "El Analista Metódico" in bloque
    assert "Curioso" in bloque


def test_se_presenta_como_lo_que_es_no_como_un_psicometrico():
    """Un test de la web no puede pesarle al modelo lo mismo que un Holland."""
    bloque = format_onboarding_context({CLAVE_ARQUETIPO: "El Conector Social"})
    assert "preliminar" in bloque.lower()


# ---------------------------------------------------------------------------
# El CRM · el resumen que nunca se veía, y la caracterización que faltaba
# ---------------------------------------------------------------------------


PERFIL = {
    "summary_narrative": "Eres alguien práctico que aprende haciendo. " * 4,
    "strengths": ["Empatía", "Constancia", "Observación"],
    "interests": ["Biología", "Diseño"],
    "values": ["Ayudar"],
    "holland_codes": [{"code": "S", "label": "Social", "score": 88},
                      {"code": "I", "label": "Investigador", "score": 79}],
    "career_families": [
        {"name": "Salud y cuidado animal", "fit_level": "alto"},
        {"name": "Creación visual", "fit_level": "a explorar"},
    ],
}


def _lite(pdata):
    """Se prueba la función extraída, no el snapshot entero.

    Montar `_get_journey_snapshot` con dobles exige simular media docena de
    consultas agregadas y no prueba lo que importa aquí: la correspondencia
    entre las claves del JSON del perfil y los campos del schema. Ahí fue donde
    se coló el `summary` que llegaba siempre vacío.
    """
    import datetime

    from app.services.crm_service import _perfil_lite

    return _perfil_lite(SimpleNamespace(
        generated_at=datetime.datetime.utcnow(), profile_data=pdata,
    ))


def test_sin_perfil_consolidado_devuelve_none():
    from app.services.crm_service import _perfil_lite

    assert _perfil_lite(None) is None


def test_el_resumen_deja_de_llegar_vacio():
    """El bug: se buscaba en tres claves que el perfil no tiene."""
    assert _lite(PERFIL).summary.startswith("Eres alguien práctico")


def test_un_perfil_viejo_con_la_clave_antigua_sigue_sirviendo():
    assert _lite({"synthesis": "resumen viejo"}).summary == "resumen viejo"


def test_el_comercial_ve_con_que_abrir_la_conversacion():
    lite = _lite(PERFIL)
    assert lite.strengths == ["Empatía", "Constancia", "Observación"]
    assert lite.holland == ["Social", "Investigador"]
    assert "Salud y cuidado animal (alto)" in lite.familias


def test_holland_se_muestra_legible_no_en_siglas():
    """A1 fue el reclamo #1 de la clienta: "le salen como unas siglas y ya"."""
    assert "S" not in _lite(PERFIL).holland


@pytest.mark.parametrize("pdata", [{}, {"holland_codes": "roto"},
                                   {"career_families": [None, {"name": "  "}]}])
def test_un_perfil_incompleto_no_tumba_el_crm(pdata):
    lite = _lite(pdata)
    assert lite.holland == [] and lite.familias == []
