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

# ---------------------------------------------------------------------------
# Los hechos duros · se confirman, no se infieren
# ---------------------------------------------------------------------------
DUROS = ("life_stage", "birthdate")

# ---------------------------------------------------------------------------
# Lo que Hop NO le pregunta al estudiante
# ---------------------------------------------------------------------------
# **El presupuesto.** Quien conversa aquí es un chico de 15 a 18 años: no sabe
# cuánto puede pagar su familia, y preguntárselo delata que quien habla no es un
# orientador sino un formulario de admisión. JP, 2026-08-09: *"temas de
# presupuesto no tiene mucho sentido hacerle esa pregunta (él no sabe, pagan los
# papás)"*.
#
# El campo NO se borra: existe en `onboarding_answers` y lo puede llenar el
# asesor o el papá desde su propio panel, y de ahí sale `user.budget_band` que
# usa el recomendador. Sólo se saca de la conversación con el estudiante.
#
# Hoy además no filtra casi nada: el catálogo entero dice "costo por confirmar"
# desde que se quitaron los precios que eran falsos.
NO_SE_LE_PREGUNTAN = ("budget",)

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
        opciones={
            "discover": "Descubrir qué estudiar",
            "study": "Estudiar una carrera",
            "learn_language": "Aprender un idioma",
            "work": "Trabajar en el exterior",
            "emigrate": "Emigrar",
            "explore": "Vivir la experiencia",
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
    # Quién es y en qué momento está.
    "life_stage", "birthdate",
    # Lo vocacional · el corazón de lo que hace un orientador.
    "voice_passion", "voice_strengths", "voice_experience", "voice_hobbies",
    "voice_concerns",
    # Qué espera de esto.
    "main_goal", "timeline",
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
    return True


def faltantes(recolectados: Dict[str, Any]) -> List[str]:
    """Lo que falta por saber, en el orden en que conviene preguntarlo.

    Primero los duros —sin ellos el producto no puede filtrar bien— y después lo
    blando, que además fluye mejor cuando ya hay algo de confianza.
    """
    def peso(h: Hecho) -> tuple:
        # El tramo sale de `OBLIGATORIOS` y no del campo `obligatorio` del
        # dataclass: tenerlos como dos fuentes de verdad ya produjo que
        # `faltantes` priorizara `timeline` (obligatorio en el dataclass) por
        # encima de las fortalezas, mientras `listo_para_cerrar` ni las miraba.
        return (
            0 if h.id in DUROS else (1 if h.id in OBLIGATORIOS else 2),
            ORDEN_CONVERSACION.index(h.id) if h.id in ORDEN_CONVERSACION
            else len(ORDEN_CONVERSACION),
        )

    pendientes = [
        h for h in HECHOS
        if recolectados.get(h.id) in (None, "", [], {})
        and aplica(h.id, recolectados)
        and h.id not in NO_SE_LE_PREGUNTAN
    ]
    return [h.id for h in sorted(pendientes, key=peso)]


def listo_para_cerrar(recolectados: Dict[str, Any]) -> bool:
    """Con los obligatorios basta · el resto lo puede aportar después.

    El perfil sigue creciendo con el uso (journey, bitácora, tests), así que el
    onboarding no tiene que sacarlo todo de una. Insistir hasta completar los 14
    sería reconstruir el formulario con otra cara.
    """
    return all(
        recolectados.get(i) not in (None, "", [], {})
        for i in OBLIGATORIOS
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
