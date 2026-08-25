"""Los 14 pasos del onboarding, vueltos hechos que una conversación recoge.

Verónica, reunión 21-07:

    "No podemos llevar la IA a ser como un formulario."
    "Con ocho preguntas fui capaz de entender a Sebastián; con 13 ni lo entendí."

El onboarding de la plataforma tiene **14 pasos** (6 de opción única, 2 múltiples,
1 de año, 5 de voz) y en el flujo "quiero estudiar en el exterior" —el caso de su
propio hijo— se recorren 13. Ese es el formulario del que se quejó, y hasta ahora
seguía en pie: lo que se volvió conversación fue el **bot comercial** de su web,
que es otra pantalla.

Este módulo es la misma lista de datos, expresada como hechos. La conversación no
recorre pasos: recorre **lo que le falta**, y decide en cada turno qué pedir. Es
el mismo motor que ya usa el perfilador (`conversation_engine`).

---

## Lo que NO puede inferir la IA

Tres campos se confirman **explícitamente** aunque la persona los haya insinuado,
porque un error en ellos no es una molestia sino un daño:

- **`birthdate`** · alimenta el gate de consentimiento parental. Deducir el año de
  nacimiento de una charla y equivocarse significa dejar entrar a un menor sin el
  consentimiento de sus padres, o bloquear a un mayor. Se pregunta y se confirma.
- **`life_stage`** · es filtro duro del recomendador (`academic_level`). Si dice
  "universidad" cuando está en el colegio, le aparecen maestrías.
- **`budget`** · define qué se le muestra como alcanzable.

El resto —lo que le apasiona, sus hobbies, sus fortalezas, lo que le preocupa— es
justamente donde una conversación gana: son las cinco preguntas de voz de hoy, y
en un chat salen solas sin que nadie tenga que grabarse.

## Las claves son las de siempre

`onboarding_key` es la clave con la que el dato se guarda en
`User.onboarding_answers`, y los valores son **los mismos** que produce el
formulario. Eso es lo que permite cambiar la pantalla sin tocar nada más: el
recomendador, el gate de menores, `seed_session_from_onboarding` y los prompts de
IA siguen leyendo lo mismo que leían.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.data.perfilador_typeform import Hecho
# La ruta del adulto profesional · construida aparte por otro agente porque no
# podía tocar este archivo, con el enganche ya documentado en su propio
# docstring (`app/data/adult_track_hechos.py`). Se engancha aquí, al final del
# módulo (ver el bloque "Enganche de la ruta profesional"), con el mismo
# patrón que ya usa `budget` vía `SOLO_PERFIL`.
from app.data.adult_track_hechos import (
    HECHOS_ADULTO,
    OBLIGATORIOS_ADULTO_IDS,
    ORDEN_SUGERIDO_ADULTO,
    QUE_AVERIGUAR_ADULTO,
    SOLO_PERFIL_ADULTO,
)

# ---------------------------------------------------------------------------
# Los hechos duros · se confirman, no se infieren
# ---------------------------------------------------------------------------
DUROS = ("life_stage", "birthdate")

# ---------------------------------------------------------------------------
# Los dos perfiles · de quién es esta conversación
# ---------------------------------------------------------------------------
# AH, 2026-08-24: *"debemos de separar al usuario en dos tipos de perfiles para
# a partir de allí hacerle las preguntas"*.
#
# No hace falta un campo nuevo ni una pregunta más: `life_stage` ya se pregunta
# de primero, ya es hecho duro y sus seis valores caen limpio en los dos grupos.
# El perfil se **deriva**, no se guarda · guardarlo sería una segunda fuente de
# verdad para el mismo dato, que es exactamente el error que ya se pagó aquí
# cuando `OBLIGATORIOS` y `Hecho.obligatorio` discrepában.
#
# Mientras no se sepa la etapa el perfil es `None`, y en ese caso **no se activa
# ninguna rama**: se pregunta lo común a los dos. Es lo conservador · una rama
# elegida con un perfil adivinado es peor que no ramificar.
PERFIL_COLEGIO = "colegio"
PERFIL_PROFESIONAL = "profesional"

PERFIL_POR_LIFE_STAGE: Dict[str, str] = {
    # Colegio · desde 9° en adelante.
    "high_school_early": PERFIL_COLEGIO,   # 9° y 10°
    "high_school": PERFIL_COLEGIO,         # 11°
    # Profesionales · ya está en la universidad o ya pasó por ella.
    "university": PERFIL_PROFESIONAL,
    "recent_grad": PERFIL_PROFESIONAL,
    "working": PERFIL_PROFESIONAL,
    "career_change": PERFIL_PROFESIONAL,
}


def perfil(recolectados: Dict[str, Any]) -> Optional[str]:
    """`colegio`, `profesional` o None si todavía no se sabe la etapa."""
    return PERFIL_POR_LIFE_STAGE.get(recolectados.get("life_stage"))


# ---------------------------------------------------------------------------
# Hechos que sólo le corresponden a un perfil
# ---------------------------------------------------------------------------
# **El presupuesto.** No se le pregunta a un estudiante de colegio: no sabe
# cuánto puede pagar su familia, y preguntárselo delata que quien habla no es un
# orientador sino un formulario de admisión. JP, 2026-08-09: *"temas de
# presupuesto no tiene mucho sentido hacerle esa pregunta (él no sabe, pagan los
# papás)"*.
#
# Esa razón es la EDAD, no el campo · a un profesional que ya trabaja o ya se
# graduó sí le corresponde, porque en su caso sí es quien paga. Por eso el
# presupuesto deja de estar suprimido en bloque y pasa a depender del perfil.
#
# El campo nunca se borró: existe en `onboarding_answers` y también lo puede
# llenar el asesor o el papá desde su panel, y de ahí sale `user.budget_band`
# que usa el recomendador.
SOLO_PERFIL: Dict[str, tuple] = {
    "budget": (PERFIL_PROFESIONAL,),
    # El grado y los datos del colegio sólo tienen sentido para quien todavía
    # está en el colegio · a un profesional preguntarle "¿en qué grado vas?"
    # no tiene sentido.
    "grade": (PERFIL_COLEGIO,),
    "school_last_grade": (PERFIL_COLEGIO,),
    "school_accreditation": (PERFIL_COLEGIO,),
}

# ---------------------------------------------------------------------------
# Las cinco rutas de la malla completa · Cimientos (migración 067)
# ---------------------------------------------------------------------------
# La malla completa pide 5 rutas —9°, 10°, 11°, 12° y adulto profesional—, y
# `life_stage` no alcanza la resolución que eso exige: `high_school_early` mete
# 9° y 10° en un solo valor, y a esos dos grados la malla les pide cosas
# distintas (ver contrato de Cimientos). Por eso la ruta se deriva de DOS
# hechos, no de uno: `life_stage` (para saber si es colegio o ya no) y `grade`
# (para saber cuál de los cuatro grados, sólo si es colegio).
#
# Igual que `perfil()`, la ruta se DERIVA y no se guarda: guardarla sería la
# misma segunda fuente de verdad que ya se pagó aquí. `user.grade` (Cimientos)
# es la fuente real del grado; este módulo sólo lo traduce a una ruta de
# conversación.
RUTA_GRADO_9 = "grado_9"
RUTA_GRADO_10 = "grado_10"
RUTA_GRADO_11 = "grado_11"
RUTA_GRADO_12 = "grado_12"
RUTA_PROFESIONAL = "profesional"

RUTAS = (RUTA_GRADO_9, RUTA_GRADO_10, RUTA_GRADO_11, RUTA_GRADO_12, RUTA_PROFESIONAL)

# Claves como STRING · son el mismo código que guarda el hecho `grade` (ver
# HECHOS más abajo) y el mismo tipo que `user.grade` expone hacia afuera en
# `onboarding_answers["grade"]` (entero en la columna, string en el JSON —
# igual que ya hace `birthdate`).
RUTA_POR_GRADO: Dict[str, str] = {
    "9": RUTA_GRADO_9,
    "10": RUTA_GRADO_10,
    "11": RUTA_GRADO_11,
    "12": RUTA_GRADO_12,
}


def ruta(recolectados: Dict[str, Any]) -> Optional[str]:
    """Una de las 5 rutas de la malla, o None si todavía no se puede saber.

    Un profesional cae directo en su única ruta sin necesitar el grado. Un
    estudiante de colegio necesita AMBOS hechos: mientras no se sepa el grado,
    se sabe que es "colegio" pero no cuál de los cuatro — y aquí, como en
    `perfil()`, ruta desconocida es mejor que ruta adivinada.
    """
    p = perfil(recolectados)
    if p == PERFIL_PROFESIONAL:
        return RUTA_PROFESIONAL
    if p != PERFIL_COLEGIO:
        return None
    grado = recolectados.get("grade")
    if grado in (None, "", [], {}):
        return None
    return RUTA_POR_GRADO.get(str(grado))


# Hechos que sólo aplican dentro de UNA ruta de colegio · las preguntas propias
# de cada grado que pidió el cliente (materias, admisiones, PSAT/SAT…). Con
# ruta desconocida `aplica()` devuelve False, el mismo criterio conservador de
# `SOLO_PERFIL`: preguntar por el PSAT a alguien que resultó estar en 9° sería
# peor que preguntarlo un turno más tarde.
SOLO_SI_RUTA: Dict[str, tuple] = {
    "g9_materias_favoritas": (RUTA_GRADO_9,),
    "g9_idolos": (RUTA_GRADO_9,),
    "g10_materias_elegir": (RUTA_GRADO_10,),
    "g10_que_lo_pone_nervioso": (RUTA_GRADO_10,),
    "g11_carreras_en_mente": (RUTA_GRADO_11,),
    "g11_psat_sat": (RUTA_GRADO_11,),
    "g11_visitas_universidades": (RUTA_GRADO_11,),
    "g12_ya_aplico": (RUTA_GRADO_12,),
    "g12_puntajes": (RUTA_GRADO_12,),
}

# Las preguntas de AP/IB son un caso aparte: no dependen de la ruta (un colegio
# IB puede tener estudiantes en cualquiera de los 4 grados) sino de lo que el
# propio estudiante contó sobre su colegio. Regla del cliente, literal: "si no
# se sabe, NO se muestran módulos AP/IB" — por eso NULL (no preguntado) y
# "unknown" (preguntó y dijo "no sé") se tratan exactamente igual acá: ninguno
# de los dos habilita la pregunta.
SOLO_SI_ACREDITACION: Dict[str, tuple] = {
    "colegio_ap_ib_detalle": ("ib", "ap"),
}

# El grado es "duro" (bloquea el cierre) pero SÓLO para quien está en colegio:
# es lo que decide a cuál de las cuatro rutas entra, y sin eso la malla no
# tiene dónde enrutarlo. Para un profesional no aplica —`aplica()` ya lo
# excluye— así que no hace falta que estos dos DE los mismos requisitos
# discrepen entre sí.
#
# Las tres claves del profesional (`career_linkedin_profile_text`,
# `career_job_satisfaction_score`, `career_target_role`) se suman más abajo,
# en el bloque "Enganche de la ruta profesional" — mismo mecanismo, sin
# necesidad de tocar esta tupla ahora que ya está definida.
OBLIGATORIO_SI_PERFIL: Dict[str, tuple] = {
    "grade": (PERFIL_COLEGIO,),
}


def es_obligatorio(hecho_id: str, recolectados: Dict[str, Any]) -> bool:
    """¿Este hecho bloquea el cierre? Los globales SIEMPRE, `grade` sólo si
    aplica a este perfil — el mismo patrón condicional que ya usa `aplica()`.

    Pública (no `_es_obligatorio`) a propósito: `onboarding_conversacional`
    también la necesita para que la rotación "cede el turno a otro
    obligatorio" trate a `grade` como lo que es para un colegial, y no como
    un opcional más.
    """
    if hecho_id in OBLIGATORIOS:
        return True
    perfiles = OBLIGATORIO_SI_PERFIL.get(hecho_id)
    return perfiles is not None and perfil(recolectados) in perfiles


# Los que hacen falta para poder cerrar. `countries` y `passport` no están: sólo
# aplican a quien dice que sí le interesa el exterior, y colgarlos de todos era
# parte de por qué el formulario se sentía largo.
# Con esto Hop ya puede orientar. Son los que describen a la PERSONA y su
# momento, no su logística: eso es lo que un orientador necesita para hablar con
# sentido, y lo demás puede llegar después.
OBLIGATORIOS = ("life_stage", "birthdate", "voice_passion", "voice_strengths",
                "main_goal")

HECHOS: List[Hecho] = [
    Hecho(
        id="life_stage",
        pregunta_typeform="¿En qué etapa estás hoy?",
        bloque="contexto",
        tipo="opcion",
        opciones={
            "high_school_early": "En el colegio (9° o 10°)",
            "high_school": "Terminando el colegio (11°)",
            "university": "En la universidad",
            "recent_grad": "Recién graduado",
            "working": "Trabajando",
            "career_change": "Buscando cambiar de carrera",
        },
        onboarding_key="life_stage",
        obligatorio=True,
        nota="Filtro duro del recomendador · confirmar, no inferir",
    ),
    Hecho(
        id="birthdate",
        pregunta_typeform="¿En qué año naciste?",
        bloque="contexto",
        tipo="entero",
        onboarding_key="birthdate",
        obligatorio=True,
        alarma=True,
        nota="Alimenta el gate de consentimiento parental · confirmar SIEMPRE",
    ),
    Hecho(
        id="timeline",
        pregunta_typeform="¿Cuándo necesitas tener tomada la decisión?",
        bloque="contexto",
        tipo="opcion",
        opciones={
            "asap": "Lo antes posible",
            "6_months": "En unos 6 meses",
            "1_year": "En un año",
            "2_years": "En dos años o más",
            "exploring": "Todavía estoy explorando",
        },
        onboarding_key="timeline",
        obligatorio=True,
    ),
    Hecho(
        id="main_goal",
        pregunta_typeform="¿Qué quieres resolver con esta orientación?",
        bloque="contexto",
        tipo="multi",
        # Las etiquetas traen ejemplos de cómo lo dice un estudiante de verdad,
        # no sólo el nombre de la categoría. Sin ellos, este hecho falló dos
        # veces seguidas probándolo: *"quiero saber si de verdad puedo vivir de
        # esto, y si sí, dónde estudiarlo"* —que es literalmente el objetivo— se
        # extrajo como `voice_concerns` y `main_goal` quedó vacío, bloqueando el
        # cierre de la conversación.
        #
        # Nadie de 16 años dice "quiero descubrir qué estudiar": dice "no sé qué
        # hacer" o "quiero saber si esto es lo mío".
        opciones={
            "discover": "Descubrir qué estudiar · también: 'no sé qué hacer', "
                        "'saber si esto que me gusta es lo mío', 'confirmar si "
                        "voy bien encaminado', 'saber si puedo vivir de esto'",
            "study": "Estudiar una carrera · también: 'saber dónde estudiarlo', "
                     "'encontrar universidad', 'elegir dónde'",
            "learn_language": "Aprender un idioma",
            "work": "Trabajar en el exterior",
            "emigrate": "Emigrar · irse a vivir a otro país",
            "explore": "Vivir la experiencia de estar afuera",
        },
        onboarding_key="main_goal",
        obligatorio=True,
    ),
    Hecho(
        id="modality",
        pregunta_typeform="¿Cómo te gustaría estudiar?",
        bloque="contexto",
        tipo="opcion",
        opciones={
            "in_person": "Presencial",
            "hybrid": "Híbrido",
            "online": "En línea",
            "no_preference": "Me da igual",
        },
        onboarding_key="modality",
    ),

    # -----------------------------------------------------------------------
    # Lo blando · hoy son cinco grabaciones de voz. En una conversación sale
    # solo, y con más matiz: nadie se graba contando que le preocupa decepcionar
    # a su papá, pero sí lo escribe.
    # -----------------------------------------------------------------------
    Hecho(
        id="voice_passion",
        pregunta_typeform="Cuéntame sobre ti: ¿qué te apasiona y qué te gustaría lograr en tu vida?",
        bloque="persona",
        tipo="texto",
        onboarding_key="voice_passion",
        obligatorio=True,
    ),
    Hecho(
        id="voice_hobbies",
        pregunta_typeform="¿Qué actividades disfrutas hacer en tu tiempo libre?",
        bloque="persona",
        tipo="texto",
        onboarding_key="voice_hobbies",
    ),
    Hecho(
        id="voice_experience",
        pregunta_typeform="¿Qué has hecho hasta ahora, y qué te gustó y qué no de eso?",
        bloque="persona",
        tipo="texto",
        onboarding_key="voice_experience",
    ),
    Hecho(
        id="voice_strengths",
        pregunta_typeform="¿Qué habilidades consideras que son tus fortalezas?",
        bloque="persona",
        tipo="texto",
        onboarding_key="voice_strengths",
    ),
    Hecho(
        id="voice_concerns",
        pregunta_typeform="¿Hay algo que te preocupe o te genere dudas sobre tu futuro?",
        bloque="persona",
        tipo="texto",
        onboarding_key="voice_concerns",
    ),

    # -----------------------------------------------------------------------
    # El grado y los datos del colegio · sólo a quien está en colegio
    # (`SOLO_PERFIL`). Es lo que abre la malla completa de 5 rutas: sin el
    # grado, `ruta()` no puede saber cuál de los cuatro pedirle.
    # -----------------------------------------------------------------------
    Hecho(
        id="grade",
        pregunta_typeform="¿En qué grado estás?",
        bloque="contexto",
        tipo="opcion",
        opciones={
            "9": "Noveno",
            "10": "Décimo",
            "11": "Once",
            "12": "Doce",
        },
        onboarding_key="grade",
        # OJO: el campo `obligatorio` de este dataclass es vestigial (ver el
        # comentario de `timeline` en el módulo original) — lo que de verdad
        # bloquea el cierre es `OBLIGATORIO_SI_PERFIL`, más abajo, porque acá
        # la obligatoriedad depende del perfil y una sola fuente de verdad ya
        # es la lección aprendida de este archivo.
        nota="Enruta a una de las 5 rutas de la malla completa · no se deduce "
             "de `life_stage`, que sólo distingue 9°/10° juntos de 11° · "
             "bloquea el cierre SÓLO para colegio (ver OBLIGATORIO_SI_PERFIL)",
    ),
    Hecho(
        id="school_last_grade",
        pregunta_typeform="¿Hasta qué grado llega tu colegio, once o doce?",
        bloque="contexto",
        tipo="opcion",
        opciones={
            "11": "Termina en once",
            "12": "Termina en doce",
            "unknown": "No sé",
        },
        onboarding_key="school_reported_last_grade",
        nota="Autoreportado, no verificado · un colegio que llega a doce "
             "cambia si once es el último año o el penúltimo",
    ),
    Hecho(
        id="school_accreditation",
        pregunta_typeform="¿Tu colegio es IB, tiene programa AP, es americano, "
                          "bilingüe o de calendario local?",
        bloque="contexto",
        tipo="opcion",
        opciones={
            "ib": "Bachillerato Internacional (IB)",
            "ap": "Programa AP (Advanced Placement)",
            "american": "Currículo americano",
            "bilingual": "Bilingüe",
            "local": "Calendario colombiano estándar",
            "unknown": "No sé",
        },
        onboarding_key="school_reported_accreditation",
        nota="Gatea los módulos AP/IB · si no se sabe (NULL o 'unknown'), NO "
             "se muestran — regla explícita del cliente",
    ),

    # -----------------------------------------------------------------------
    # Lo propio de cada grado · lo que pidió el cliente para cada una de las
    # 4 rutas de colegio. `SOLO_SI_RUTA` las limita a su grado; no bloquean el
    # cierre, son enriquecimiento — igual que `voice_hobbies` o `voice_career`.
    # -----------------------------------------------------------------------
    Hecho(
        id="g9_materias_favoritas",
        pregunta_typeform="¿Cuáles son tus materias favoritas del colegio?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g9_materias_favoritas",
        nota="Sólo grado 9 · tono exploratorio, sin presión de decidir",
    ),
    Hecho(
        id="g9_idolos",
        pregunta_typeform="¿Hay alguien a quien admiras o te gustaría parecerte?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g9_idolos",
        nota="Sólo grado 9",
    ),
    Hecho(
        id="g10_materias_elegir",
        pregunta_typeform="Si pudieras elegir qué materias profundizar, ¿cuáles serían?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g10_materias_elegir",
        nota="Sólo grado 10",
    ),
    Hecho(
        id="g10_que_lo_pone_nervioso",
        pregunta_typeform="¿Qué es lo que más te pone nervioso de tener que ir "
                          "decidiendo tu futuro?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g10_que_lo_pone_nervioso",
        nota="Sólo grado 10",
    ),
    Hecho(
        id="g11_carreras_en_mente",
        pregunta_typeform="¿Qué carreras tienes en mente hoy, aunque no estés seguro?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g11_carreras_en_mente",
        nota="Sólo grado 11",
    ),
    Hecho(
        id="g11_psat_sat",
        pregunta_typeform="¿Ya presentaste el PSAT o el SAT? ¿Cómo te fue o cómo "
                          "te sientes con eso?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g11_psat_sat",
        nota="Sólo grado 11",
    ),
    Hecho(
        id="g11_visitas_universidades",
        pregunta_typeform="¿Has visitado alguna universidad o feria educativa? "
                          "¿Qué te dejó esa visita?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g11_visitas_universidades",
        nota="Sólo grado 11",
    ),
    Hecho(
        id="g12_ya_aplico",
        pregunta_typeform="¿Ya aplicaste a alguna universidad o programa?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g12_ya_aplico",
        nota="Sólo grado 12 · tono de ejecución, ya no de exploración",
    ),
    Hecho(
        id="g12_puntajes",
        pregunta_typeform="¿Qué puntajes tienes hasta ahora (SAT, ICFES u otros)?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="g12_puntajes",
        nota="Sólo grado 12",
    ),
    Hecho(
        id="colegio_ap_ib_detalle",
        pregunta_typeform="¿En qué materias AP o del programa IB estás, y cómo "
                          "te está yendo con ellas?",
        bloque="ruta",
        tipo="texto",
        onboarding_key="colegio_ap_ib_detalle",
        nota="Sólo si el colegio es IB o AP · cualquier grado",
    ),

    # -----------------------------------------------------------------------
    # El bloque del exterior · sólo aplica si dice que le interesa. En el
    # formulario estas tres son las que llevan el recorrido de 10 pasos a 13,
    # que es exactamente la queja del cliente.
    # -----------------------------------------------------------------------
    Hecho(
        id="international_interest",
        pregunta_typeform="¿Dónde te gustaría vivir tu experiencia de estudio?",
        bloque="destino",
        tipo="opcion",
        opciones={
            "intl_yes": "En el exterior",
            "intl_maybe": "Todavía no sé",
            "intl_no": "En Colombia",
        },
        onboarding_key="international_interest",
    ),
    Hecho(
        id="countries",
        pregunta_typeform="¿Qué países te interesan?",
        bloque="destino",
        tipo="multi",
        opciones={
            "usa": "Estados Unidos", "canada": "Canadá", "spain": "España",
            "uk": "Reino Unido", "germany": "Alemania", "australia": "Australia",
            "other": "Otro",
        },
        onboarding_key="countries",
        nota="Sólo si international_interest != intl_no",
    ),
    Hecho(
        id="budget",
        pregunta_typeform="¿Cuál es tu presupuesto aproximado?",
        bloque="destino",
        tipo="opcion",
        opciones={
            "under_5k": "Menos de USD 5.000",
            "5k_15k": "Entre USD 5.000 y 15.000",
            "15k_30k": "Entre USD 15.000 y 30.000",
            "over_30k": "Más de USD 30.000",
            "unknown": "Todavía no lo sé",
        },
        onboarding_key="budget",
        nota="Define qué se le muestra como alcanzable · confirmar",
    ),
    Hecho(
        id="passport",
        pregunta_typeform="¿Tienes pasaporte vigente?",
        bloque="destino",
        tipo="opcion",
        opciones={"yes": "Sí", "no": "No", "in_progress": "En trámite"},
        onboarding_key="passport",
        nota="Sólo si international_interest != intl_no",
    ),
]

_POR_ID = {h.id: h for h in HECHOS}

# ---------------------------------------------------------------------------
# El orden de la conversación · primero la persona, después la logística
# ---------------------------------------------------------------------------
# Hop es un **orientador vocacional**, no alguien tomando datos de admisión.
# Un orientador pregunta primero quién eres, qué se te da bien y qué te mueve;
# el país, la modalidad y el pasaporte vienen después, cuando ya hay algo que
# orientar. Con el orden invertido —que es como venía— la conversación se siente
# un trámite aunque las preguntas sean las mismas.
#
# La lista del catálogo (`HECHOS`) conserva el orden del formulario original,
# que sirve para leerlo contra la pantalla vieja. Este es el orden en que se
# CONVERSA, que es otra cosa.
ORDEN_CONVERSACION = [
    # Quién es y en qué momento está. `grade` va aquí y no después de lo
    # vocacional: el tono de TODO lo que sigue depende de la ruta (9° no se
    # trata como 12°), así que hace falta saberlo temprano.
    "life_stage", "birthdate", "grade",
    # Lo vocacional · el corazón de lo que hace un orientador.
    "voice_passion", "voice_strengths", "voice_experience", "voice_hobbies",
    "voice_concerns",
    # Qué espera de esto.
    "main_goal", "timeline",
    # Lo propio de cada grado · sólo una de las cuatro ramas se activa nunca,
    # `SOLO_SI_RUTA` se encarga de que las otras tres ni aparezcan.
    "g9_materias_favoritas", "g9_idolos",
    "g10_materias_elegir", "g10_que_lo_pone_nervioso",
    "g11_carreras_en_mente", "g11_psat_sat", "g11_visitas_universidades",
    "g12_ya_aplico", "g12_puntajes",
    # Datos del colegio · sólo sirven para gatear si se muestran AP/IB, así
    # que no urge preguntarlos antes que lo vocacional.
    "school_last_grade", "school_accreditation", "colegio_ap_ib_detalle",
    # Y sólo al final, la logística.
    "international_interest", "countries", "modality", "passport",
]

# Los del bloque destino sólo se piden a quien dice que le interesa el exterior.
# Es lo que baja el recorrido de 13 pasos a los ~8 que la clienta pedía.
SOLO_SI_EXTERIOR = ("countries", "passport")


# ---------------------------------------------------------------------------
# Qué hay que averiguar · NO cómo preguntarlo
# ---------------------------------------------------------------------------
# Al modelo se le pasaba el texto literal de la pregunta del formulario
# ("¿En qué etapa estás hoy?") y lo repetía tal cual. Por eso la conversación
# sonaba idéntica siempre, sin importar lo que la persona hubiera contado: eran
# las mismas catorce frases en otro envase.
#
# Estas descripciones dicen **qué necesitamos saber y para qué**, y dejan que el
# modelo formule la pregunta a partir de lo que la persona acaba de decir. A
# quien contó que dibuja se le pregunta por sus fortalezas de otra manera que a
# quien contó que juega fútbol.
QUE_AVERIGUAR = {
    "life_stage": "en qué punto de sus estudios está (colegio, universidad, "
                  "trabajando, buscando cambiar) · define qué se le puede ofrecer",
    "birthdate": "el año en que nació · hay que preguntarlo, no deducirlo de que "
                 "esté en un grado",
    "timeline": "con cuánto tiempo cuenta para decidir",
    "main_goal": "qué espera sacar de esta orientación · descubrir qué estudiar, "
                 "elegir dónde, aprender un idioma, irse a vivir afuera",
    "modality": "si se imagina estudiando presencial, en línea o le da igual",
    "voice_passion": "qué le mueve de verdad y qué le gustaría llegar a hacer",
    "voice_hobbies": "en qué se le va el tiempo cuando nadie lo obliga",
    "voice_experience": "qué ha hecho o probado hasta ahora, y qué le gustó y "
                        "qué no de eso",
    "voice_strengths": "en qué siente que es bueno · sirve preguntarle qué le "
                       "dicen los demás que hace bien, cuesta menos responder",
    "voice_concerns": "qué le preocupa o le da miedo de esta decisión",
    "international_interest": "si se ve estudiando fuera del país o prefiere quedarse",
    "countries": "qué países o ciudades le llaman la atención",
    "passport": "si ya tiene pasaporte vigente o le toca tramitarlo",
    "grade": "en qué grado del colegio está · 9°, 10°, 11° o 12° · se pregunta, "
             "no se deduce de la edad",
    "school_last_grade": "hasta qué grado llega su colegio, once o doce · si no "
                         "lo sabe, así se registra",
    "school_accreditation": "si su colegio es IB, tiene programa AP, es "
                            "americano, bilingüe o de calendario local · si no "
                            "lo sabe, así se registra",
    "g9_materias_favoritas": "cuáles materias del colegio le gustan más",
    "g9_idolos": "a quién admira o a quién le gustaría parecerse",
    "g10_materias_elegir": "qué materias elegiría profundizar si pudiera",
    "g10_que_lo_pone_nervioso": "qué le pone nervioso de tener que ir "
                                "decidiendo su futuro",
    "g11_carreras_en_mente": "qué carreras tiene en mente hoy, aunque no esté "
                             "seguro todavía",
    "g11_psat_sat": "si ya presentó el PSAT o el SAT, y cómo le fue o cómo se "
                    "siente con eso",
    "g11_visitas_universidades": "si ha visitado universidades o ferias "
                                 "educativas, y qué le dejó esa visita",
    "g12_ya_aplico": "si ya aplicó a alguna universidad o programa",
    "g12_puntajes": "qué puntajes tiene hasta ahora · SAT, ICFES u otros",
    "colegio_ap_ib_detalle": "en qué materias AP o del programa IB está, y "
                             "cómo le está yendo con ellas",
}


def que_averiguar(hecho_id: str) -> str:
    """Qué hay que saber de este hecho · en lenguaje de orientador."""
    h = _POR_ID.get(hecho_id)
    return QUE_AVERIGUAR.get(hecho_id) or (h.pregunta_typeform if h else hecho_id)


def get_hecho(hecho_id: str) -> Optional[Hecho]:
    return _POR_ID.get(hecho_id)


def aplica(hecho_id: str, recolectados: Dict[str, Any]) -> bool:
    """¿Este hecho tiene sentido para esta persona?

    Preguntarle el pasaporte a quien acaba de decir que quiere estudiar en
    Colombia es justo el tipo de paso de más que hizo que el formulario se
    sintiera un interrogatorio.
    """
    if hecho_id in SOLO_SI_EXTERIOR:
        return recolectados.get("international_interest") != "intl_no"
    # Las preguntas de AP/IB · gatean por lo que el estudiante contó de su
    # colegio, no por la ruta. Con acreditación desconocida (NULL o
    # "unknown") no se ramifica: es la regla explícita del cliente.
    if hecho_id in SOLO_SI_ACREDITACION:
        return recolectados.get("school_accreditation") in SOLO_SI_ACREDITACION[hecho_id]
    # Lo propio de cada grado. Con ruta desconocida devuelve False a
    # propósito, mismo criterio que el resto de este archivo: preguntar el
    # PSAT a quien resultó estar en 9° es peor que preguntarlo un turno tarde.
    if hecho_id in SOLO_SI_RUTA:
        return ruta(recolectados) in SOLO_SI_RUTA[hecho_id]
    # La rama por perfil. Con perfil desconocido devuelve False a propósito: el
    # hecho se retoma solo, en cuanto `life_stage` deje de faltar.
    if hecho_id in SOLO_PERFIL:
        return perfil(recolectados) in SOLO_PERFIL[hecho_id]
    return True


def faltantes(recolectados: Dict[str, Any]) -> List[str]:
    """Lo que falta por saber, en el orden en que conviene preguntarlo.

    Primero los duros —sin ellos el producto no puede filtrar bien— y después lo
    blando, que además fluye mejor cuando ya hay algo de confianza.
    """
    def peso(h: Hecho) -> tuple:
        # El tramo sale de `OBLIGATORIOS`/`es_obligatorio` y no del campo
        # `obligatorio` del dataclass: tenerlos como dos fuentes de verdad ya
        # produjo que `faltantes` priorizara `timeline` (obligatorio en el
        # dataclass) por encima de las fortalezas, mientras `listo_para_cerrar`
        # ni las miraba.
        return (
            0 if h.id in DUROS else (1 if es_obligatorio(h.id, recolectados) else 2),
            ORDEN_CONVERSACION.index(h.id) if h.id in ORDEN_CONVERSACION
            else len(ORDEN_CONVERSACION),
        )

    pendientes = [
        h for h in HECHOS
        if recolectados.get(h.id) in (None, "", [], {})
        and aplica(h.id, recolectados)
    ]
    return [h.id for h in sorted(pendientes, key=peso)]


def _obligatorios_activos(recolectados: Dict[str, Any]) -> List[str]:
    """Los obligatorios globales + los que lo son sólo para este perfil.

    `grade` bloquea el cierre de un estudiante de colegio (sin grado la malla
    no sabe dónde enrutarlo); `career_linkedin_profile_text`,
    `career_job_satisfaction_score` y `career_target_role` bloquean el cierre
    de un profesional (sin eso no hay con qué comparar el puesto ideal). Ver
    `OBLIGATORIO_SI_PERFIL`.
    """
    extra = [i for i in OBLIGATORIO_SI_PERFIL if perfil(recolectados) in OBLIGATORIO_SI_PERFIL[i]]
    return list(OBLIGATORIOS) + extra


def listo_para_cerrar(recolectados: Dict[str, Any]) -> bool:
    """Con los obligatorios basta · el resto lo puede aportar después.

    El perfil sigue creciendo con el uso (journey, bitácora, tests), así que el
    onboarding no tiene que sacarlo todo de una. Insistir hasta completar los 14
    sería reconstruir el formulario con otra cara.
    """
    return all(
        recolectados.get(i) not in (None, "", [], {})
        for i in _obligatorios_activos(recolectados)
        if aplica(i, recolectados)
    )


def a_onboarding_answers(recolectados: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce lo recolectado al diccionario que guarda `PUT /me/onboarding`.

    Es el contrato con todo el resto del producto: el recomendador, el gate de
    menores, `seed_session_from_onboarding` y los prompts de IA siguen leyendo
    exactamente lo que leían cuando esto era un formulario.
    """
    fuera: Dict[str, Any] = {}
    for h in HECHOS:
        if not h.onboarding_key:
            continue
        v = recolectados.get(h.id)
        if v in (None, "", [], {}):
            continue
        fuera[h.onboarding_key] = v
    return fuera


# ---------------------------------------------------------------------------
# Enganche de la ruta profesional · Cimientos (migración 067)
# ---------------------------------------------------------------------------
# `app/data/adult_track_hechos.py` es de otro agente que no podía tocar este
# archivo: dejó los 5 hechos del profesional listos y documentó el enganche
# exacto en su propio docstring, con el mismo patrón que ya usa `budget` vía
# `SOLO_PERFIL`. Se aplica aquí, al final del módulo, porque muta estructuras
# (`HECHOS`, `_POR_ID`, `SOLO_PERFIL`, `QUE_AVERIGUAR`, `OBLIGATORIOS`,
# `ORDEN_CONVERSACION`) que ya quedaron definidas arriba — todo esto corre una
# sola vez, al importar el módulo, mucho antes de que cualquier función
# (`aplica`, `faltantes`, `listo_para_cerrar`, `que_averiguar`...) se llame de
# verdad, así que el orden de ejecución no importa.
HECHOS.extend(HECHOS_ADULTO)
_POR_ID.update({h.id: h for h in HECHOS_ADULTO})
SOLO_PERFIL.update(SOLO_PERFIL_ADULTO)
QUE_AVERIGUAR.update(QUE_AVERIGUAR_ADULTO)

# NO se suman al global `OBLIGATORIOS` (el módulo adulto lo sugería así, pero
# eso rompe la invariante que ya prueba este archivo: que todo lo que está en
# `OBLIGATORIOS` aparece SIEMPRE en `faltantes({})`, sin importar el perfil —
# ver `test_las_dos_fuentes_de_verdad_de_lo_obligatorio_coinciden`). Se
# enganchan exactamente como ya se engancha `grade` para colegio:
# condicionados a un perfil en `OBLIGATORIO_SI_PERFIL`. `listo_para_cerrar()`
# y `es_obligatorio()` ya saben leer esta condición — a un estudiante de
# colegio jamás se le exige, porque `aplica()` los excluye de raíz.
OBLIGATORIO_SI_PERFIL.update({i: (PERFIL_PROFESIONAL,) for i in OBLIGATORIOS_ADULTO_IDS})

# Después de lo vocacional (voice_*) y antes de la logística de colegio, que a
# un profesional no le aplica — es la ubicación que sugirió el propio módulo
# adulto. Si el id ancla llegara a cambiar de nombre, no truena: se agregan al
# final en vez de perderse.
_ANCLA_ORDEN_ADULTO = "voice_concerns"
if _ANCLA_ORDEN_ADULTO in ORDEN_CONVERSACION:
    _idx = ORDEN_CONVERSACION.index(_ANCLA_ORDEN_ADULTO) + 1
    ORDEN_CONVERSACION[_idx:_idx] = ORDEN_SUGERIDO_ADULTO
else:  # pragma: no cover · red de seguridad, no debería pasar
    ORDEN_CONVERSACION.extend(ORDEN_SUGERIDO_ADULTO)
