"""Las preguntas por grado y las del adulto llegan a la IA · 2026-09-18.

Una auditoría de la cadena perfil → recomendación encontró **trece respuestas
guardadas que no leía nadie**:

    g9_materias_favoritas · g9_idolos · g10_materias_elegir ·
    g10_que_lo_pone_nervioso · g11_carreras_en_mente · g11_psat_sat ·
    g11_visitas_universidades · g12_ya_aplico · g12_puntajes ·
    colegio_ap_ib_detalle · career_current_role ·
    career_job_satisfaction_text · career_target_role

Todas se persisten en `User.onboarding_answers` (tienen `onboarding_key` en
`onboarding_hechos.HECHOS`), y `format_onboarding_context` —el bloque que ve la
IA en reflection, synthesis, routes, el chat de Mento y el perfil consolidado—
no tocaba ninguna. O sea: se le preguntaba a un chico de 11° qué carreras tiene
en mente y después se le recomendaba sin usarlo.

Es el defecto #1 del `backend/CLAUDE.md` ("escribir un campo que nadie lee") a
escala. El test de completitud de abajo es lo que impide que vuelva a pasar en
silencio: agregar un hecho nuevo al catálogo sin decidir a dónde va, falla.
"""
from __future__ import annotations

import pytest

from app.data.onboarding_hechos import HECHOS
from app.services.ai_service import (
    ONBOARDING_FUERA_DEL_PROMPT,
    _ONBOARDING_RELATO,
    format_onboarding_context,
)


#: Claves que el bloque renderiza a mano, fuera de la tabla `_ONBOARDING_RELATO`
#: (tienen formato propio: etiquetas de vocabulario cerrado, listas, escalas).
_RENDERIZADAS_A_MANO = {
    "voice_passion", "voice_hobbies", "voice_experience", "voice_career",
    "voice_strengths", "voice_concerns", "main_goal", "international_interest",
    "modality", "city", "preferred_cities", "study_area",
    "career_job_satisfaction_score",
}


# ---------------------------------------------------------------------------
# La red de seguridad · ningún hecho nuevo se queda sin destino
# ---------------------------------------------------------------------------


def test_cada_hecho_del_catalogo_tiene_un_destino_decidido():
    """Si agregas una pregunta al onboarding, este test te obliga a conectarla.

    Tres destinos válidos: la tabla `_ONBOARDING_RELATO`, el renderizado a mano,
    o `ONBOARDING_FUERA_DEL_PROMPT` (que exige escribir POR QUÉ no va). Lo que no
    se puede es olvidarla — que es exactamente como llegaron aquí las trece.
    """
    en_tabla = {clave for clave, _ in _ONBOARDING_RELATO}
    con_destino = en_tabla | _RENDERIZADAS_A_MANO | ONBOARDING_FUERA_DEL_PROMPT

    sin_destino = sorted(
        h.onboarding_key
        for h in HECHOS
        if h.onboarding_key and h.onboarding_key not in con_destino
    )
    assert not sin_destino, (
        "Estos hechos se guardan en onboarding_answers y nadie los lee: "
        f"{sin_destino}. Conéctalos en `format_onboarding_context` o decláralos "
        "en `ONBOARDING_FUERA_DEL_PROMPT` con la razón."
    )


def test_la_tabla_no_tiene_claves_muertas():
    """Al revés: una fila que apunte a un hecho inexistente es ruido que nadie
    va a notar, porque `onboarding.get(clave)` devuelve None sin quejarse."""
    del_catalogo = {h.onboarding_key for h in HECHOS if h.onboarding_key}
    muertas = sorted(c for c, _ in _ONBOARDING_RELATO if c not in del_catalogo)
    assert not muertas, f"filas que no corresponden a ningún hecho: {muertas}"


# ---------------------------------------------------------------------------
# Lo que la persona escribió aparece, con su pregunta
# ---------------------------------------------------------------------------


def test_las_carreras_que_tiene_en_mente_llegan_al_prompt():
    """El caso más caro de los trece: lo escribe la persona y decidía nada."""
    bloque = format_onboarding_context(
        {"g11_carreras_en_mente": "Medicina, o algo con animales. Veterinaria?"}
    )
    assert "Veterinaria" in bloque
    # Y con contexto: un texto suelto no le dice al modelo qué está leyendo.
    assert "Carreras que tiene en mente" in bloque


def test_el_rol_al_que_quiere_llegar_llega_al_prompt():
    """La ruta del adulto tenía el mismo hueco que la del colegio."""
    bloque = format_onboarding_context(
        {
            "career_current_role": "Analista de datos en una EPS",
            "career_target_role": "Product manager",
        }
    )
    assert "Analista de datos" in bloque
    assert "Product manager" in bloque


@pytest.mark.parametrize("clave,valor", list(_ONBOARDING_RELATO))
def test_toda_la_tabla_se_rinde(clave, valor):
    """Cada fila, una por una · una etiqueta mal escrita no rompe nada y por eso
    hay que comprobarlo: el valor simplemente desaparecería del prompt."""
    bloque = format_onboarding_context({clave: "RESPUESTA-DE-PRUEBA"})
    assert "RESPUESTA-DE-PRUEBA" in bloque, f"{clave} no llega al prompt"
    assert valor in bloque


def test_la_satisfaccion_laboral_lleva_su_escala():
    """Un "3" suelto el modelo lo puede leer como 3/10 y concluir que la persona
    está mucho peor de lo que dijo. La escala es parte del dato."""
    bloque = format_onboarding_context({"career_job_satisfaction_score": 3})
    assert "3 de 5" in bloque


def test_una_escala_fuera_de_rango_no_se_escribe():
    """Antes que afirmarle al modelo una satisfacción que nadie midió, nada."""
    assert "de 5" not in format_onboarding_context(
        {"career_job_satisfaction_score": 9}
    )
    assert "de 5" not in format_onboarding_context(
        {"career_job_satisfaction_score": "alto"}
    )


# ---------------------------------------------------------------------------
# Lo que ya funcionaba sigue igual
# ---------------------------------------------------------------------------


def test_sin_datos_sigue_devolviendo_el_centinela():
    assert format_onboarding_context({}) == "(sin datos del onboarding)"
    assert format_onboarding_context(None) == "(sin datos del onboarding)"


def test_las_respuestas_de_voz_no_se_movieron():
    bloque = format_onboarding_context({"voice_passion": "Me apasiona cocinar"})
    assert "Me apasiona cocinar" in bloque


def test_el_tope_por_campo_tambien_protege_a_las_nuevas():
    """`_add` corta a 600 caracteres · sin esto, trece campos largos inflan
    TODOS los prompts del journey, no sólo uno."""
    bloque = format_onboarding_context({"g12_puntajes": "x" * 2000})
    assert "…" in bloque
    assert len(bloque) < 1000


def test_las_llaves_del_usuario_no_revientan_el_format():
    """Estos textos viajan a plantillas con `str.format`: un `{` suelto la tumba."""
    bloque = format_onboarding_context({"g9_idolos": "mi profe de {mate}"})
    assert "{" not in bloque and "}" not in bloque
