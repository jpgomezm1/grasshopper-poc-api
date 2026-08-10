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
    """Etapa y nacimiento son lo que no se puede deducir: uno decide si se le
    pide permiso a los padres y el otro qué nivel se le puede ofrecer.

    El presupuesto SALIO de aquí: a un estudiante de 16 no se le pregunta cuánto
    puede pagar su familia."""
    orden = cat.faltantes({})

    assert set(orden[:len(cat.DUROS)]) == set(cat.DUROS)
    assert "budget" not in cat.DUROS


def test_se_cierra_sin_haber_preguntado_las_catorce():
    """El perfil sigue creciendo con el uso (journey, bitácora, tests). Insistir
    hasta completar los 14 datos sería el formulario con otra cara."""
    r = {
        "life_stage": "high_school", "birthdate": 2008,
        "main_goal": ["discover"], "voice_passion": "dibujar personajes",
        "voice_strengths": "el color y las expresiones",
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


# ---------------------------------------------------------------------------
# Una pregunta por mensaje · 2026-08-09, probándolo con JP
# ---------------------------------------------------------------------------


def test_al_modelo_se_le_destaca_UNA_sola_pregunta():
    """Agrupó dos hechos en un mismo mensaje ("¿cómo te gustaría estudiar? ¿te
    ves yéndote a otro país?") dos veces en una conversación de seis turnos.

    La causa era el prompt: se le mostraba una lista numerada de seis pendientes
    y, al verla, trataba de ser eficiente. Pedirle en el texto que no lo hiciera
    no bastó —ya lo decía—, igual que pasó con la repetición de preguntas.

    **No puede agrupar lo que no ve.** Se destaca una y el resto va marcado como
    "todavía no", que le sirve para no cerrar antes de tiempo pero no para
    preguntarlo.
    """
    bloque = conv._bloque_faltantes(
        ["life_stage", "birthdate", "budget", "timeline"]
    )

    # La destacada aparece una vez.
    assert "Lo único que quieres averiguar ahora" in bloque
    assert bloque.count("Lo único que quieres averiguar ahora") == 1
    # Las demás están, pero explícitamente prohibidas para este turno.
    assert "no lo preguntes todavía" in bloque.lower()


def test_los_duros_se_marcan_para_que_no_los_deduzca():
    """`birthdate` decide si le pedimos permiso a sus padres."""
    bloque = conv._bloque_faltantes(["birthdate", "timeline"])

    assert "se pregunta, no se deduce" in bloque


def test_sin_pendientes_no_se_inventa_una_pregunta():
    assert "ya tienes todo" in conv._bloque_faltantes([])


def test_al_modelo_se_le_da_la_edad_calculada():
    """Probándolo, el modelo vio "2009" y cerró con *"tienes 15 años"* cuando
    eran 16. El dato guardado estaba bien; el error era suyo al hacer la cuenta.

    Un estudiante que lee mal su propia edad deja de creerle al resto de la
    conversación, y la aritmética es justo lo que no hay que delegarle a un
    modelo pudiendo dársela hecha.
    """
    from datetime import date

    bloque = conv._bloque_recolectado({"birthdate": 2009})
    esperada = date.today().year - 2009 - 1  # se cumple años el 31 de diciembre

    assert f"{esperada} años" in bloque
    assert "2009" in bloque


def test_dar_la_edad_no_cambia_lo_que_se_guarda():
    """El bloque es sólo lo que ve el modelo · la columna sigue siendo la fecha
    del 31 de diciembre, que es de lo que depende el gate de menores."""
    assert conv.a_onboarding_answers({"birthdate": 2009})["birthdate"] == "2009-12-31"


def test_en_el_primer_turno_NO_se_pospone_la_etapa_de_vida():
    """La rotación que evita insistir se disparaba en el primer turno.

    El historial arranca con el saludo, que pregunta por lo que le apasiona. Al
    contarlo como "ya se preguntó", el código creía que la etapa de vida se
    había preguntado sin obtener respuesta y la mandaba al final — así que el
    campo que decide si se le ofrecen maestrías a alguien de 11° quedaba
    postergado SIEMPRE, en toda conversación.

    Se comprueba sobre `_rotar_si_no_respondieron` con la condición corregida:
    sin mensajes del usuario, no hay nada que rotar.
    """
    from app.services.conversation_engine import _rotar_si_no_respondieron

    solo_saludo = [{"role": "assistant", "content": "¿qué te apasiona?"}]
    ya_hablo = any(t.get("role") == "user" for t in solo_saludo)
    assert ya_hablo is False

    faltan = ["life_stage", "birthdate", "budget"]
    # Con la condición corregida no se rota: la etapa sigue primero.
    assert _rotar_si_no_respondieron([] if not ya_hablo else faltan, faltan)[0] == "life_stage"
    # Y contando el saludo —el bug— sí se rotaba.
    assert _rotar_si_no_respondieron(faltan, faltan)[0] != "life_stage"


# ---------------------------------------------------------------------------
# La trampa que impedía cerrar · 2026-08-09, probándolo con JP
# ---------------------------------------------------------------------------


def test_un_obligatorio_sin_responder_no_se_va_detras_de_los_opcionales():
    """La conversación no podía cerrar NUNCA.

    A "¿qué quieres resolver?" respondió "saber si puedo vivir de esto". El
    extractor se abstuvo con razón —no mapeaba a ninguna opción— y `main_goal`,
    que es obligatorio, se fue al final detrás de diez preguntas opcionales.
    Como nunca volvía, `listo_para_cerrar` jamás era True y seguía preguntando
    hasta agotar los 14 datos: el formulario, por otra puerta.
    """
    faltan = ["main_goal", "voice_hobbies", "voice_experience", "modality"]
    rotado = conv._rotar_dentro_del_tramo(faltan, faltan)

    # Sigue al frente: es el único obligatorio que queda.
    assert rotado[0] == "main_goal"


def test_un_obligatorio_cede_el_turno_a_OTRO_obligatorio():
    """Insistir sí es lo que vuelve esto un formulario · si hay otro obligatorio
    pendiente, se pregunta ese y el primero se retoma después."""
    faltan = ["main_goal", "voice_passion", "voice_hobbies"]
    rotado = conv._rotar_dentro_del_tramo(faltan, faltan)

    assert rotado[0] == "voice_passion"
    assert "main_goal" in rotado


def test_un_opcional_sin_responder_si_baja():
    """Para lo opcional el comportamiento no cambia: si no lo respondieron, se
    pasa a otra cosa."""
    faltan = ["voice_hobbies", "voice_experience", "modality"]
    rotado = conv._rotar_dentro_del_tramo(faltan, faltan)

    assert rotado[0] != "voice_hobbies"


def test_en_el_primer_turno_no_se_rota_nada():
    faltan = ["life_stage", "birthdate"]

    assert conv._rotar_dentro_del_tramo([], faltan) == faltan


# ---------------------------------------------------------------------------
# Hop es un orientador vocacional, no un formulario de admisión · 2026-08-09
# ---------------------------------------------------------------------------
# JP: "el usuario será el estudiante · temas de presupuesto no tiene mucho
# sentido hacerle esa pregunta (él no sabe, pagan los papás) · quiero que el rol
# de Hop sea de orientador vocacional".


def test_a_un_estudiante_NO_se_le_pregunta_el_presupuesto():
    """Quien conversa tiene 15-19 años: no sabe cuánto puede pagar su familia, y
    preguntárselo delata que quien habla no es un orientador.

    El campo no se borra —el asesor o el papá lo llenan desde su panel, y de ahí
    sale `user.budget_band`— sólo se saca de esta conversación.
    """
    assert "budget" not in cat.faltantes({})
    assert "budget" not in cat.faltantes({"life_stage": "high_school"})
    assert "budget" in cat.NO_SE_LE_PREGUNTAN


def test_el_presupuesto_sigue_pudiendo_guardarse():
    """Que no se pregunte no significa que el campo desaparezca: el recomendador
    lo lee y alguien más lo va a llenar."""
    assert conv.a_onboarding_answers({"budget": "5k_15k"})["budget"] == "5k_15k"


def test_primero_la_persona_y_despues_la_logistica():
    """Un orientador pregunta quién eres antes que si tienes pasaporte. Con el
    orden invertido la conversación se siente un trámite aunque las preguntas
    sean las mismas."""
    orden = cat.faltantes({})
    pos = {h: i for i, h in enumerate(orden)}

    assert pos["voice_passion"] < pos["passport"]
    assert pos["voice_strengths"] < pos["countries"]
    assert pos["voice_strengths"] < pos["modality"]


def test_se_cierra_con_lo_vocacional_no_con_la_logistica():
    """Lo que un orientador necesita para hablar con sentido es quién es la
    persona · el país y la modalidad pueden llegar después."""
    r = {"life_stage": "high_school", "birthdate": 2009,
         "voice_passion": "dibujar personajes", "voice_strengths": "el color",
         "main_goal": ["discover"]}

    assert cat.listo_para_cerrar(r)


def test_al_modelo_se_le_dice_QUE_averiguar_no_COMO_preguntarlo():
    """Se le pasaba el texto literal del formulario y lo repetía tal cual: la
    conversación sonaba idéntica siempre, sin importar lo que la persona hubiera
    contado. Eran las mismas catorce frases en otro envase."""
    bloque = conv._bloque_faltantes(["voice_strengths", "main_goal"])

    # Ya no aparece la pregunta enlatada…
    assert "¿Qué habilidades consideras" not in bloque
    # …sino qué hay que averiguar, y la instrucción de formularla él.
    assert "en qué siente que es bueno" in bloque
    assert "Formula tú la pregunta" in bloque


def test_las_dos_fuentes_de_verdad_de_lo_obligatorio_coinciden():
    """`faltantes` ordenaba por el campo `obligatorio` del dataclass mientras
    `listo_para_cerrar` usaba la tupla `OBLIGATORIOS`. Con dos listas, una se
    queda atrás: `timeline` se priorizaba por encima de las fortalezas y el
    cierre ni las miraba."""
    orden = cat.faltantes({})
    primeros = set(orden[:len(cat.DUROS) + len(cat.OBLIGATORIOS)])

    for i in cat.OBLIGATORIOS:
        assert i in primeros, i


def test_las_opciones_del_objetivo_hablan_como_un_estudiante():
    """`main_goal` falló DOS veces probándolo con JP, con la misma frase:
    *"quiero saber si de verdad puedo vivir de esto, y si sí, dónde
    estudiarlo"* —que es literalmente el objetivo— se extrajo como
    `voice_concerns` y `main_goal` quedó vacío, bloqueando el cierre.

    La causa: las etiquetas eran nombres de categoría ("Descubrir qué
    estudiar") y nadie de 16 años habla así. Dice "no sé qué hacer" o "quiero
    saber si esto es lo mío". Las etiquetas ahora traen esos ejemplos.
    """
    opciones = cat.get_hecho("main_goal").opciones

    assert "no sé qué hacer" in opciones["discover"]
    assert "saber si puedo vivir de esto" in opciones["discover"]
    assert "dónde estudiarlo" in opciones["study"]
