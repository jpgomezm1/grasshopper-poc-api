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
    hasta completar todos los hechos sería el formulario con otra cara.

    `grade` SÍ está incluido: desde la malla de 5 rutas es obligatorio para
    quien está en colegio (sin grado no hay a cuál de las 4 rutas enrutarlo),
    a diferencia de `budget` o de las preguntas propias de cada grado, que
    siguen siendo enriquecimiento opcional."""
    r = {
        "life_stage": "high_school", "birthdate": 2008, "grade": "11",
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


def test_a_un_estudiante_de_colegio_NO_se_le_pregunta_el_presupuesto():
    """No sabe cuánto puede pagar su familia, y preguntárselo delata que quien
    habla no es un orientador.

    El campo no se borra —el asesor o el papá lo llenan desde su panel, y de ahí
    sale `user.budget_band`— sólo se saca de ESTA conversación.
    """
    assert "budget" not in cat.faltantes({})
    assert "budget" not in cat.faltantes({"life_stage": "high_school"})
    assert "budget" not in cat.faltantes({"life_stage": "high_school_early"})
    assert cat.SOLO_PERFIL["budget"] == (cat.PERFIL_PROFESIONAL,)


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
    persona · el país y la modalidad pueden llegar después.

    `grade` es la excepción vocacional: no es logística, es lo que decide con
    qué tono y qué preguntas propias de su grado se le habla el resto de la
    conversación (ver `_bloque_perfil`)."""
    r = {"life_stage": "high_school", "birthdate": 2009, "grade": "11",
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


# ---------------------------------------------------------------------------
# Los dos perfiles · colegio y profesional
# ---------------------------------------------------------------------------

def test_el_perfil_sale_de_life_stage_sin_campo_nuevo():
    """Los seis valores de `life_stage` reparten entre los dos perfiles.

    Que no quede ninguno sin mapear importa: un valor huérfano devolvería None
    para siempre y esa persona nunca entraría a una rama.
    """
    assert cat.perfil({"life_stage": "high_school_early"}) == cat.PERFIL_COLEGIO
    assert cat.perfil({"life_stage": "high_school"}) == cat.PERFIL_COLEGIO
    assert cat.perfil({"life_stage": "university"}) == cat.PERFIL_PROFESIONAL
    assert cat.perfil({"life_stage": "recent_grad"}) == cat.PERFIL_PROFESIONAL
    assert cat.perfil({"life_stage": "working"}) == cat.PERFIL_PROFESIONAL
    assert cat.perfil({"life_stage": "career_change"}) == cat.PERFIL_PROFESIONAL

    opciones = set(cat.get_hecho("life_stage").opciones)
    assert opciones == set(cat.PERFIL_POR_LIFE_STAGE), (
        "hay un valor de life_stage sin perfil asignado"
    )


def test_sin_etapa_conocida_no_se_ramifica():
    """El perfil es None hasta que se sepa la etapa · y ahí no se activa rama."""
    assert cat.perfil({}) is None
    assert cat.perfil({"life_stage": "loquesea"}) is None
    assert "budget" not in cat.faltantes({})


def test_a_un_profesional_SI_se_le_pregunta_el_presupuesto():
    """La razón para no preguntarlo era la edad, no el campo: quien ya trabaja o
    ya se graduó es justamente quien paga."""
    for etapa in ("university", "recent_grad", "working", "career_change"):
        assert "budget" in cat.faltantes({"life_stage": etapa}), etapa


def test_el_presupuesto_no_bloquea_el_cierre_de_un_profesional():
    """Es una rama, no un obligatorio nuevo: sin él se puede cerrar igual.

    Sí hace falta completar los 3 obligatorios PROPIOS del profesional
    (`OBLIGATORIO_SI_PERFIL`, enganchados por `adult_track_hechos.py`) — ese
    es un bloqueo distinto al del presupuesto, que es lo que este test
    verifica que NO bloquea.
    """
    from app.data.adult_track_hechos import OBLIGATORIOS_ADULTO_IDS

    completo = {i: "x" for i in cat.OBLIGATORIOS}
    completo.update({i: "x" for i in OBLIGATORIOS_ADULTO_IDS})
    completo["life_stage"] = "working"
    assert cat.listo_para_cerrar(completo) is True


def test_el_prompt_le_habla_distinto_a_cada_perfil():
    """El bloque de perfil es lo que hace que la rama se note en la conversación
    y no sólo en qué campos se piden."""
    colegio = conv._bloque_perfil({"life_stage": "high_school"})
    profesional = conv._bloque_perfil({"life_stage": "working"})
    sin_saber = conv._bloque_perfil({})

    assert colegio != profesional
    # Al de colegio se le prohibe el dinero · al profesional se le habilita.
    assert "No le preguntas por dinero" in colegio
    assert "el dinero sí se habla" in profesional
    # Con perfil desconocido, tampoco.
    assert "no le preguntes por dinero" in sin_saber


def test_el_prompt_ya_no_asume_una_edad():
    """La audiencia sale del bloque de perfil, no del texto fijo del prompt."""
    from app.core.ai_client import load_prompt
    plantilla = load_prompt("onboarding_conversacional")
    assert "{perfil}" in plantilla
    assert "entre 15 y 19" not in plantilla


# ---------------------------------------------------------------------------
# La malla completa · 5 rutas (Cimientos, migración 067) · 2026-08-24
# ---------------------------------------------------------------------------
# `life_stage` no alcanza la resolución que la malla pide: `high_school_early`
# junta 9° y 10°, y a esos dos grados se les pregunta cosas distintas. La ruta
# se deriva de `life_stage` + `grade` (el entero que definió Cimientos), nunca
# se guarda aparte.


def test_la_ruta_de_un_profesional_no_necesita_el_grado():
    """Un profesional cae directo en su única ruta · preguntarle el grado no
    tiene sentido."""
    for etapa in ("university", "recent_grad", "working", "career_change"):
        assert cat.ruta({"life_stage": etapa}) == cat.RUTA_PROFESIONAL, etapa


def test_la_ruta_de_colegio_necesita_el_grado():
    """Con perfil colegio pero sin grado, se sabe que es colegio y no cuál de
    los cuatro — la ruta se queda en None, no se adivina."""
    assert cat.ruta({"life_stage": "high_school"}) is None
    assert cat.ruta({"life_stage": "high_school_early"}) is None


def test_las_cuatro_rutas_de_colegio_salen_del_grado():
    for grado, esperada in (
        ("9", cat.RUTA_GRADO_9), ("10", cat.RUTA_GRADO_10),
        ("11", cat.RUTA_GRADO_11), ("12", cat.RUTA_GRADO_12),
    ):
        r = {"life_stage": "high_school_early", "grade": grado}
        assert cat.ruta(r) == esperada, grado


def test_sin_etapa_la_ruta_tambien_es_none():
    assert cat.ruta({}) is None
    assert cat.ruta({"grade": "9"}) is None  # el grado solo no basta


def test_el_grado_se_pregunta_a_quien_esta_en_colegio():
    """Es el hecho nuevo del que depende TODA la ramificación de rutas."""
    assert "grade" in cat.faltantes({"life_stage": "high_school"})
    assert "grade" in cat.faltantes({"life_stage": "high_school_early"})


def test_al_profesional_no_se_le_pregunta_el_grado():
    assert "grade" not in cat.faltantes({"life_stage": "working"})


def test_el_grado_bloquea_el_cierre_SOLO_para_colegio():
    """A diferencia de `budget`, `grade` sí es obligatorio — pero condicionado
    al perfil, igual que la pregunta misma (`SOLO_PERFIL`)."""
    sin_grado = {"life_stage": "high_school", "birthdate": 2008,
                 "voice_passion": "x", "voice_strengths": "x", "main_goal": ["discover"]}
    assert not cat.listo_para_cerrar(sin_grado)

    con_grado = {**sin_grado, "grade": "10"}
    assert cat.listo_para_cerrar(con_grado)

    # Para un profesional, `grade` ni siquiera aplica: no puede bloquear lo
    # que no se le pregunta. Pero sus TRES propios obligatorios (enganchados
    # por el mismo mecanismo, ver `test_career_engancha_sus_obligatorios_por_perfil`
    # más abajo) sí bloquean — sin ellos el análisis de brecha no tiene con
    # qué comparar, mismo motivo por el que `grade` bloquea a colegio.
    profesional_sin_grade = {"life_stage": "working", "birthdate": 1998,
                             "voice_passion": "x", "voice_strengths": "x",
                             "main_goal": ["discover"],
                             "career_linkedin_profile_text": "algo",
                             "career_job_satisfaction_score": 3,
                             "career_target_role": "Data Analyst"}
    assert cat.listo_para_cerrar(profesional_sin_grade)


def test_grade_no_es_obligatorio_global():
    """`OBLIGATORIOS` sigue siendo la tupla estática de siempre: `grade` vive
    en `OBLIGATORIO_SI_PERFIL`, no ahí — dos fuentes de verdad para lo mismo ya
    se pagaron una vez en este archivo."""
    assert "grade" not in cat.OBLIGATORIOS
    assert cat.OBLIGATORIO_SI_PERFIL["grade"] == (cat.PERFIL_COLEGIO,)


def test_career_engancha_sus_obligatorios_por_perfil_no_al_global():
    """El módulo adulto (`adult_track_hechos.py`) sugería sumar sus 3
    obligatorios directo a `OBLIGATORIOS`; el enganche real los puso en
    `OBLIGATORIO_SI_PERFIL` en su lugar, exactamente por lo que prueba
    `test_las_dos_fuentes_de_verdad_de_lo_obligatorio_coinciden` — todo lo que
    está en `OBLIGATORIOS` tiene que aparecer en `faltantes({})` sin importar
    el perfil, y estos tres NO deben (sólo aplican a un profesional)."""
    from app.data.adult_track_hechos import OBLIGATORIOS_ADULTO_IDS

    for hecho_id in OBLIGATORIOS_ADULTO_IDS:
        assert hecho_id not in cat.OBLIGATORIOS, hecho_id
        assert cat.OBLIGATORIO_SI_PERFIL.get(hecho_id) == (cat.PERFIL_PROFESIONAL,), hecho_id

    # Y sí están enganchados de verdad: el catálogo los conoce, se pueden
    # preguntar (`aplica`) y bloquean el cierre de un profesional que no los
    # haya respondido.
    for hecho_id in OBLIGATORIOS_ADULTO_IDS:
        assert cat.get_hecho(hecho_id) is not None, hecho_id
        assert cat.aplica(hecho_id, {"life_stage": "working"}) is True, hecho_id
        assert cat.aplica(hecho_id, {"life_stage": "high_school_early"}) is False, hecho_id


def test_las_preguntas_de_grado_9_solo_aplican_en_grado_9():
    r9 = {"life_stage": "high_school_early", "grade": "9"}
    r10 = {"life_stage": "high_school_early", "grade": "10"}

    assert "g9_materias_favoritas" in cat.faltantes(r9)
    assert "g9_idolos" in cat.faltantes(r9)
    assert "g9_materias_favoritas" not in cat.faltantes(r10)


def test_las_preguntas_de_grado_10_solo_aplican_en_grado_10():
    r10 = {"life_stage": "high_school_early", "grade": "10"}
    r9 = {"life_stage": "high_school_early", "grade": "9"}

    assert "g10_materias_elegir" in cat.faltantes(r10)
    assert "g10_que_lo_pone_nervioso" in cat.faltantes(r10)
    assert "g10_materias_elegir" not in cat.faltantes(r9)


def test_las_preguntas_de_grado_11_solo_aplican_en_grado_11():
    r11 = {"life_stage": "high_school", "grade": "11"}
    r12 = {"life_stage": "high_school", "grade": "12"}

    for hecho in ("g11_carreras_en_mente", "g11_psat_sat", "g11_visitas_universidades"):
        assert hecho in cat.faltantes(r11), hecho
        assert hecho not in cat.faltantes(r12), hecho


def test_las_preguntas_de_grado_12_solo_aplican_en_grado_12():
    r12 = {"life_stage": "high_school", "grade": "12"}
    r11 = {"life_stage": "high_school", "grade": "11"}

    assert "g12_ya_aplico" in cat.faltantes(r12)
    assert "g12_puntajes" in cat.faltantes(r12)
    assert "g12_ya_aplico" not in cat.faltantes(r11)


def test_sin_grado_conocido_no_se_activa_ninguna_pregunta_de_ruta():
    """Ruta desconocida = no se ramifica, el mismo criterio conservador que ya
    usa `SOLO_PERFIL`."""
    sin_grado = cat.faltantes({"life_stage": "high_school"})
    for hecho_id in cat.SOLO_SI_RUTA:
        assert hecho_id not in sin_grado, hecho_id


def test_las_preguntas_de_ruta_no_bloquean_el_cierre():
    """Son enriquecimiento, no obligatorio nuevo — igual que `budget` para un
    profesional."""
    r = {"life_stage": "high_school_early", "grade": "9", "birthdate": 2011,
         "voice_passion": "x", "voice_strengths": "x", "main_goal": ["discover"]}
    assert cat.listo_para_cerrar(r)


# ---------------------------------------------------------------------------
# Los datos del colegio · terminan en 11 o 12, y acreditación · con "no sé"
# ---------------------------------------------------------------------------


def test_los_datos_del_colegio_solo_se_piden_a_colegio():
    assert "school_last_grade" not in cat.faltantes({"life_stage": "working"})
    assert "school_accreditation" not in cat.faltantes({"life_stage": "working"})
    assert "school_last_grade" in cat.faltantes({"life_stage": "high_school"})
    assert "school_accreditation" in cat.faltantes({"life_stage": "high_school"})


def test_los_datos_del_colegio_admiten_no_se():
    """Regla del cliente, literal: se pregunta CON OPCIÓN 'no sé'."""
    opciones_grado = cat.get_hecho("school_last_grade").opciones
    opciones_acreditacion = cat.get_hecho("school_accreditation").opciones

    assert opciones_grado["unknown"] == "No sé"
    assert opciones_acreditacion["unknown"] == "No sé"


def test_modulos_ap_ib_solo_si_el_colegio_es_ib_o_ap():
    """"Si no se sabe, NO se muestran módulos AP/IB" — ni con NULL (no
    preguntado) ni con "unknown" (preguntó, no sabe) se activa."""
    base = {"life_stage": "high_school_early", "grade": "9"}

    assert "colegio_ap_ib_detalle" not in cat.faltantes(base)
    assert "colegio_ap_ib_detalle" not in cat.faltantes(
        {**base, "school_accreditation": "unknown"}
    )
    assert "colegio_ap_ib_detalle" not in cat.faltantes(
        {**base, "school_accreditation": "local"}
    )
    assert "colegio_ap_ib_detalle" in cat.faltantes(
        {**base, "school_accreditation": "ib"}
    )
    assert "colegio_ap_ib_detalle" in cat.faltantes(
        {**base, "school_accreditation": "ap"}
    )


def test_ap_ib_aplica_sin_importar_el_grado():
    """La acreditación es del colegio, no de la ruta: un IB puede tener
    estudiantes en cualquiera de los 4 grados."""
    for grado in ("9", "10", "11", "12"):
        r = {"life_stage": "high_school_early", "grade": grado,
             "school_accreditation": "ib"}
        assert "colegio_ap_ib_detalle" in cat.faltantes(r), grado


# ---------------------------------------------------------------------------
# El chat le habla distinto a cada una de las 5 rutas
# ---------------------------------------------------------------------------


def test_las_5_rutas_producen_5_bloques_distintos():
    bloques = {
        r: conv._bloque_perfil({
            "life_stage": "working" if r == cat.RUTA_PROFESIONAL else "high_school_early",
            "grade": None if r == cat.RUTA_PROFESIONAL else r.rsplit("_", 1)[-1],
        })
        for r in cat.RUTAS
    }
    # Las 5 son distintas entre sí · si dos coincidieran, esa rama no se nota.
    assert len(set(bloques.values())) == 5


def test_grado_9_es_amigable_y_sin_presion():
    bloque = conv._bloque_perfil({"life_stage": "high_school_early", "grade": "9"})
    assert "presión" in bloque.lower()
    assert "No le preguntas por dinero" in bloque


def test_grado_12_es_de_ejecucion_y_fechas():
    bloque = conv._bloque_perfil({"life_stage": "high_school", "grade": "12"})
    assert "ejecución" in bloque.lower()
    assert "No le preguntas por dinero" in bloque  # sigue sin ser quien paga


def test_grado_11_no_asume_si_es_su_ultimo_ano():
    """Sin `school_last_grade` no se sabe si once es el último año o el
    penúltimo — el bloque no debe darlo por hecho en ningún sentido."""
    bloque = conv._bloque_perfil({"life_stage": "high_school", "grade": "11"})
    assert "no lo sabes" in bloque.lower() or "no sabes" in bloque.lower()


def test_colegio_sin_grado_conocido_usa_el_bloque_generico_no_uno_de_ruta():
    """Antes de saber el grado, sigue sin haber presión de dinero, pero
    tampoco se adivina un tono de ejecución o de exploración."""
    bloque = conv._bloque_perfil({"life_stage": "high_school"})
    assert "No le preguntas por dinero" in bloque
    assert "ejecución" not in bloque.lower()
    assert bloque != conv._bloque_perfil({"life_stage": "high_school_early", "grade": "9"})


# ---------------------------------------------------------------------------
# La rotación de tramo reconoce que `grade` es obligatorio SOLO para colegio
# ---------------------------------------------------------------------------


def test_grado_sin_responder_cede_a_otro_obligatorio_de_colegio():
    """Sin pasarle el contexto, `grade` se trataría como opcional y se iría
    al fondo detrás de diez preguntas — el mismo bug que ya se corrigió una
    vez para `main_goal`."""
    contexto = {"life_stage": "high_school"}
    faltan = ["grade", "voice_passion", "voice_hobbies", "voice_experience"]

    rotado = conv._rotar_dentro_del_tramo(faltan, faltan, contexto)

    # `voice_passion` es obligatorio global · `grade` es obligatorio de
    # colegio · deben quedar juntos en el mismo tramo, y ninguno detrás de
    # los opcionales.
    assert rotado[0] == "voice_passion"
    assert "grade" in rotado
    assert rotado.index("grade") < rotado.index("voice_hobbies")


def test_grado_sin_contexto_se_degrada_al_comportamiento_anterior():
    """Sin `recolectados` (el default), `grade` no aparece en `OBLIGATORIOS` y
    se trata como cualquier opcional — el comportamiento previo a la malla de
    5 rutas, para no romper a quien todavía llama sin el tercer argumento."""
    faltan = ["grade", "voice_hobbies", "voice_experience"]
    rotado = conv._rotar_dentro_del_tramo(faltan, faltan)

    assert rotado[0] != "grade"
