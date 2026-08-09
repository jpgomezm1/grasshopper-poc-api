"""El onboarding como conversación · lo que NO puede cambiar al quitar el formulario.

Verónica, 21-07: *"No podemos llevar la IA a ser como un formulario"* · *"con ocho
preguntas fui capaz de entender a Sebastián; con trece ni lo entendí"*.

Lo que protegen estos tests, en orden de importancia:

 1. **Que el contrato con el resto del producto no cambie.** El recomendador, el
    gate de menores y los prompts leen `User.onboarding_answers`. Si el chat
    guarda otras claves u otros códigos, todo eso deja de funcionar en silencio.
 2. **Que el año de nacimiento siga produciendo `YYYY-12-31`.** Esa fecha da la
    edad MÍNIMA posible, así que ante la duda la persona queda como menor y se le
    pide consentimiento parental. Enero 1 invertiría exactamente esa garantía.
 3. Que no se le pregunte a nadie lo que no aplica · preguntar el pasaporte a
    quien va a estudiar en Colombia es el paso de más que sobraba.
"""
from __future__ import annotations

from app.data import onboarding_hechos as cat
from app.services import onboarding_conversacional as conv


# ---------------------------------------------------------------------------
# El contrato con el resto del producto
# ---------------------------------------------------------------------------


def test_las_claves_son_las_MISMAS_del_formulario():
    """`onboarding_key` es lo que lee todo lo demás. Si el chat inventa claves
    nuevas, el recomendador deja de ver el presupuesto y los países."""
    claves = {h.onboarding_key for h in cat.HECHOS if h.onboarding_key}

    assert {"life_stage", "birthdate", "timeline", "main_goal", "modality",
            "international_interest", "countries", "budget", "passport",
            "voice_passion", "voice_hobbies", "voice_experience",
            "voice_strengths", "voice_concerns"} <= claves


def test_los_codigos_son_los_canonicos_de_la_plataforma():
    """`life_stage` alimenta `academic_level`, que filtra por etapa. Un código
    distinto significa que el filtro deja de reconocerlo y no descarta nada."""
    from app.services import academic_level as al

    etapas = cat.get_hecho("life_stage").opciones
    for codigo in etapas:
        assert al.normalizar_etapa(codigo) is not None, codigo


def test_el_ano_de_nacimiento_se_guarda_como_31_de_diciembre():
    """Diciembre 31 da la edad MÍNIMA posible para ese año: ante la duda, la
    persona se clasifica como menor y se le pide consentimiento parental. Enero
    1 haría exactamente lo contrario."""
    fuera = conv.a_onboarding_answers({"birthdate": 2008})

    assert fuera["birthdate"] == "2008-12-31"


def test_el_ano_como_texto_tambien_se_convierte():
    """El extractor puede devolverlo como string según cómo lo escriba la
    persona."""
    assert conv.a_onboarding_answers({"birthdate": "2008"})["birthdate"] == "2008-12-31"


def test_lo_no_dicho_no_se_guarda():
    """Un campo vacío no puede llegar como `None` a `onboarding_answers`: el
    recomendador lo leería como una respuesta."""
    fuera = conv.a_onboarding_answers(
        {"life_stage": "high_school", "budget": None, "countries": []}
    )

    assert "budget" not in fuera
    assert "countries" not in fuera
    assert fuera["life_stage"] == "high_school"


# ---------------------------------------------------------------------------
# Qué se pregunta y qué no
# ---------------------------------------------------------------------------


def test_no_se_le_pide_pasaporte_a_quien_estudia_en_Colombia():
    """Es el paso de más que hacía sentir el formulario un interrogatorio."""
    r = {"international_interest": "intl_no"}

    assert "passport" not in cat.faltantes(r)
    assert "countries" not in cat.faltantes(r)


def test_a_quien_si_quiere_el_exterior_si_se_le_piden():
    r = {"international_interest": "intl_yes"}

    assert "passport" in cat.faltantes(r)
    assert "countries" in cat.faltantes(r)


def test_lo_duro_se_pregunta_primero():
    """Etapa, nacimiento y presupuesto son filtros duros · sin ellos el
    recomendador no puede descartar lo imposible."""
    orden = cat.faltantes({})

    assert set(orden[:3]) == set(cat.DUROS)


def test_se_cierra_sin_haber_preguntado_las_catorce():
    """El perfil sigue creciendo con el uso (journey, bitácora, tests). Insistir
    hasta completar los 14 datos sería el formulario con otra cara."""
    r = {
        "life_stage": "high_school", "birthdate": 2008, "timeline": "asap",
        "main_goal": ["discover"], "voice_passion": "dibujar personajes",
    }

    assert cat.listo_para_cerrar(r)
    assert len(r) < len(cat.HECHOS)


def test_sin_lo_obligatorio_no_cierra():
    assert not cat.listo_para_cerrar({"voice_passion": "algo"})
    assert not cat.listo_para_cerrar({"life_stage": "high_school"})


# ---------------------------------------------------------------------------
# El extractor valida contra el catálogo correcto
# ---------------------------------------------------------------------------


def test_el_extractor_conoce_los_hechos_del_onboarding():
    """Con el catálogo comercial por defecto, TODO lo del onboarding se
    descartaría por no estar en su vocabulario."""
    from app.services import fact_extractor as fx

    ids = fx._tool_schema(cat)["properties"]["hechos"]["items"]["properties"]["id"]["enum"]

    assert "voice_passion" in ids
    assert "life_stage" in ids
    assert len(ids) == len(cat.HECHOS)
