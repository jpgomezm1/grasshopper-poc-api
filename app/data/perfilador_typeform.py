"""Catálogo de hechos del perfilador comercial · el Typeform vuelto conversación.

Origen del dato: `Docs/Cliente/Recibidos del cliente/Sprint 3 (jul 2026)/` ·
export del Typeform "Asesoria Gratuita V05" que la agencia usa HOY en su web.

El export trae **61 preguntas · 35 distintas**, y esa inflación es puro árbol de
decisión: *"¿Cuál es tu destino de interés?"* aparece **10 veces** y *"¿Qué tipo de
experiencia quieres vivir?"* 4, porque un formulario no puede preguntar
condicionalmente en una sola pasada. Las 61 casillas recogen **~20 hechos**.

Este módulo es esa lista de 20 hechos. El bot no recorre preguntas: recorre
**hechos que le faltan**, y decide en cada turno cuál pedir. Es la diferencia
entre lo que hay hoy y lo que pidió Verónica:

    "yo tengo que volverme tan inteligente de preguntar las tantas preguntas
     necesite, pero tampoco volverlo casi que un formulario, porque no hice nada"
     (reunión 21-07, 38:26)

⚠️ **Lo que el export NO trae** y está pedido al cliente: las opciones de respuesta
de cada pregunta, la fórmula de `score`, el significado de `variable_abc` y el
mapeo de `ending`. Donde un hecho coincide con un campo que la plataforma ya
guarda, las opciones de aquí son **las canónicas de la plataforma** (las que
consumen `journey_service.seed_answers_from_onboarding` y `study_preferences.py`)
— no se inventan. Donde el hecho es sólo del perfilador, las opciones salen de las
palabras textuales de Verónica en la reunión y están marcadas
`PENDIENTE_CONFIRMAR`.

Regla del repo que aplica aquí: si añades un hecho, **conéctalo a su consumidor en
el mismo commit**. Un campo que nadie lee es el defecto que este proyecto ya
cometió cuatro veces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Marca los conjuntos de opciones que salieron de la reunión y no del export.
# Sirve para poder listarlos cuando se le lleven a Verónica a validar.
PENDIENTE_CONFIRMAR = "pendiente_confirmar_con_cliente"


@dataclass(frozen=True)
class Hecho:
    """Un dato que el perfilador necesita obtener, no una pregunta que hacer."""

    id: str
    # Copy LITERAL del Typeform · es la referencia de qué se pregunta hoy, no un
    # guion. El bot reformula según la conversación; esto le da el sentido exacto.
    pregunta_typeform: str
    bloque: str
    tipo: str  # texto · opcion · multi · entero · booleano
    opciones: Optional[Dict[str, str]] = None
    # Si el hecho existe también en la plataforma, la clave con la que se guarda
    # en `User.onboarding_answers`. None = sólo vive en el perfilador comercial.
    onboarding_key: Optional[str] = None
    # Filtro duro: su valor puede matar o degradar el lead por sí solo.
    alarma: bool = False
    # Sin estos el lead no sirve para nada · el bot no cierra sin ellos.
    obligatorio: bool = False
    origen_opciones: Optional[str] = None
    nota: Optional[str] = None


# ---------------------------------------------------------------------------
# Vocabularios canónicos de la plataforma
#
# NO tocar sin mirar quién los consume. `life_stage`, `timeline`, `main_goal` y
# `budget` los traduce `journey_service._ONBOARDING_*_MAP` para sembrar el
# journey: un valor que no esté aquí se descarta y el journey vuelve a preguntar
# lo mismo, que es exactamente la queja S9 de Sandra.
# ---------------------------------------------------------------------------

OCUPACION_A_LIFE_STAGE = {
    "high_school_early": "Estoy en el colegio",
    "high_school": "Estoy en último año de colegio",
    "university": "Estoy en la universidad",
    "recent_grad": "Me gradué hace poco",
    "working": "Estoy trabajando",
    "career_change": "Quiero un cambio de carrera",
}

CUANDO_VIAJAR = {
    "asap": "Ya, tengo que decidir pronto",
    "6_months": "En los próximos 6 meses",
    "1_year": "En un año, más o menos",
    "2_years": "En uno o dos años",
    "exploring": "Sin fecha: solo quiero conocerme mejor",
}

INVERSION = {
    "under_5k": "Menos de $5,000 USD",
    "5k_15k": "$5,000 - $15,000 USD",
    "15k_30k": "$15,000 - $30,000 USD",
    "over_30k": "Más de $30,000 USD",
    "unknown": "No sé todavía",
}

PASAPORTE = {
    "yes": "Sí, vigente",
    "no": "No tengo",
    "in_progress": "Está en trámite",
}

PAISES = {
    "usa": "USA",
    "canada": "Canadá",
    "spain": "España",
    "uk": "UK",
    "germany": "Alemania",
    "australia": "Australia",
    "other": "Otro",
}

# El Typeform tiene 7 variantes de la MISMA mecánica comercial: cuando el destino
# que la persona quiere no es viable, propone uno de los que la agencia representa
# ("Para cumplir tu propósito podemos ofrecerte como destino Francia ¿Estás de
# acuerdo?"). En conversación eso es un solo movimiento, no siete preguntas.
DESTINOS_CONTRAOFERTA = [
    "Francia",
    "Alemania",
    "Portugal",
    "China",
    "Italia",
    "Japón",
    "España",
]

# Palabras textuales de Verónica (21-07, 18:34) cuando le explicó a JP qué
# distingue un lead de la agencia de uno de GrassHopper. La última opción es la
# que dispara la "miga de pan": no la resuelve el bot, la resuelve GrassHopper.
TIPO_EXPERIENCIA = {
    "idioma": "Aprender o perfeccionar un idioma",
    "pregrado": "Hacer un pregrado",
    "posgrado": "Hacer un posgrado o maestría",
    "tecnico": "Un programa técnico",
    "estudiar_trabajar": "Estudiar y trabajar",
    "campamento": "Un campamento de verano",
    "orientacion": "Orientación profesional / entender mis habilidades",
}

# Verónica, misma reunión: "ofrézcame un programa que también me lleve a tener la
# oportunidad de quedarme en el destino, eso es súper importante".
TIPO_SERVICIO = {
    "solo_estudio": "Solo estudiar",
    "estudio_trabajo": "Estudiar con opción de trabajar",
    "migratorio": "Estudiar con ruta para quedarme en el destino",
    "no_sabe": "Todavía no lo tengo claro",
}

NIVEL_IDIOMA = {
    "basico": "Básico",
    "intermedio": "Intermedio",
    "avanzado": "Avanzado",
    "nativo": "Nativo o bilingüe",
    "ninguno": "Ninguno",
}

MODALIDAD = {
    "in_person": "Presencial",
    "hybrid": "Híbrido",
    "online": "Virtual",
    "no_preference": "Me da igual",
}


# ---------------------------------------------------------------------------
# Los ~20 hechos
# ---------------------------------------------------------------------------

HECHOS: List[Hecho] = [
    # --- Contacto · sin esto no hay lead -----------------------------------
    Hecho(
        id="nombre",
        pregunta_typeform="¿Cuál es tu nombre?",
        bloque="contacto",
        tipo="texto",
        obligatorio=True,
        nota="El Typeform lo parte en nombre y apellido; en conversación se pide una vez.",
    ),
    Hecho(
        id="apellido",
        pregunta_typeform="¿Cuál es tu apellido?",
        bloque="contacto",
        tipo="texto",
    ),
    Hecho(
        id="correo",
        pregunta_typeform="¿Cuál es tu correo electrónico?",
        bloque="contacto",
        tipo="texto",
        obligatorio=True,
    ),
    Hecho(
        id="celular",
        pregunta_typeform="¿Cuál es tu número celular?",
        bloque="contacto",
        tipo="texto",
        obligatorio=True,
        nota="Es el canal por el que el equipo comercial devuelve la llamada.",
    ),
    Hecho(
        id="ubicacion",
        pregunta_typeform="¿Dónde estas ubicado?",
        bloque="contacto",
        tipo="texto",
    ),
    Hecho(
        id="ciudad",
        pregunta_typeform="¿Cuál es tu ciudad?",
        bloque="contacto",
        tipo="texto",
        onboarding_key="city",
        nota=(
            "Se guarda en la MISMA clave que leen crm_service:725/1091 y "
            "dossier_service:100. Durante meses esos tres leyeron un `city` que "
            "nadie escribía; el perfilador es ahora una de las dos fuentes."
        ),
    ),
    Hecho(
        id="nacionalidad",
        pregunta_typeform="¿Cuál es tu Nacionalidad?",
        bloque="perfil",
        tipo="texto",
    ),
    Hecho(
        id="edad",
        pregunta_typeform="¿Cuál es tu edad?",
        bloque="perfil",
        tipo="entero",
        nota=(
            "Verónica: 'me pareció súper bacano campo de verano y tiene 25 años, "
            "ya no clasifico'. La edad descarta programas enteros."
        ),
    ),
    Hecho(
        id="ocupacion",
        pregunta_typeform="¿Cuál es tu ocupación?",
        bloque="perfil",
        tipo="opcion",
        opciones=OCUPACION_A_LIFE_STAGE,
        onboarding_key="life_stage",
        obligatorio=True,
        nota=(
            "El Typeform la pide como texto libre; se recoge contra el vocabulario "
            "de la plataforma para que siembre el journey sin traducción a mano."
        ),
    ),
    Hecho(
        id="profesion",
        pregunta_typeform="¿Cual es tu profesión?",
        bloque="perfil",
        tipo="texto",
        nota="Sólo aplica a quien ya estudió · el bot no la pregunta a un colegial.",
    ),
    # --- Filtros duros · las alarmas de Verónica ---------------------------
    Hecho(
        id="pasaporte",
        pregunta_typeform="¿Cuentas con pasaporte vigente?",
        bloque="filtros",
        tipo="opcion",
        opciones=PASAPORTE,
        onboarding_key="passport",
        alarma=True,
        obligatorio=True,
    ),
    Hecho(
        id="visa_usa_negada",
        pregunta_typeform="¿Te han negado la visa americana en algún momento?",
        bloque="filtros",
        tipo="booleano",
        alarma=True,
        obligatorio=True,
        nota=(
            "Verónica (12:03): 'si me negaron visa de EEUU e Inglaterra, eso me "
            "prende una alarma'. Es la alarma más fuerte del perfilador."
        ),
    ),
    Hecho(
        id="visa_usa_vigente",
        pregunta_typeform="¿Tienes visa americana de turismo vigente?",
        bloque="filtros",
        tipo="booleano",
        nota="Señal positiva: acelera el proceso y abre destino USA.",
    ),
    Hecho(
        id="visa_vencimiento",
        pregunta_typeform="¿Fecha de vencimiento de visa?",
        bloque="filtros",
        tipo="texto",
        nota="Sólo si `visa_usa_vigente` es verdadero.",
    ),
    # --- Intención ---------------------------------------------------------
    Hecho(
        id="tipo_experiencia",
        pregunta_typeform="¿Qué tipo de experiencia quieres vivir?",
        bloque="intencion",
        tipo="opcion",
        opciones=TIPO_EXPERIENCIA,
        obligatorio=True,
        origen_opciones=PENDIENTE_CONFIRMAR,
        nota=(
            "La opción 'orientacion' es la bifurcación del negocio: ahí el lead NO "
            "es de la agencia, es de GrassHopper, y el bot debe ofrecer la miga de "
            "pan en vez de seguir perfilando destino."
        ),
    ),
    Hecho(
        id="que_estudiar",
        pregunta_typeform="¿Qué te gustaría estudiar?",
        bloque="intencion",
        tipo="texto",
        onboarding_key="study_area",
        nota="Texto libre a propósito · el catálogo lo resuelve después.",
    ),
    Hecho(
        id="tipo_servicio",
        pregunta_typeform="¿Qué tipo de servicio requieres?",
        bloque="intencion",
        tipo="opcion",
        opciones=TIPO_SERVICIO,
        origen_opciones=PENDIENTE_CONFIRMAR,
    ),
    Hecho(
        id="modalidad",
        pregunta_typeform="(no está en el Typeform · la pidió en la reunión)",
        bloque="intencion",
        tipo="opcion",
        opciones=MODALIDAD,
        onboarding_key="modality",
        nota=(
            "R6-ON-5 · Verónica: 'hay una pregunta que no hemos hecho: ¿cómo "
            "quieres hacer tu programa, presencial, híbrido, virtual?, porque las "
            "tres formas existen'. No está en el Typeform viejo; entra aquí."
        ),
    ),
    # --- Destino -----------------------------------------------------------
    Hecho(
        id="destino_interes",
        pregunta_typeform="¿Cuál es tu destino de interés?",
        bloque="destino",
        tipo="multi",
        opciones=PAISES,
        onboarding_key="countries",
        obligatorio=True,
        nota="Las 10 repeticiones del Typeform son ramas del árbol · aquí es un hecho.",
    ),
    Hecho(
        id="destino_contraoferta_aceptada",
        pregunta_typeform=(
            "Para cumplir tu propósito podemos ofrecerte como destino "
            "{pais} ¿Estás de acuerdo?"
        ),
        bloque="destino",
        tipo="texto",
        nota=(
            "Las 7 variantes por país del Typeform son UNA mecánica: si el destino "
            "que quiere no es viable, se propone uno de los que la agencia "
            "representa. Guarda el país propuesto y si aceptó."
        ),
    ),
    # --- Idiomas -----------------------------------------------------------
    Hecho(
        id="idioma_aprender",
        pregunta_typeform="¿Qué idioma te interesa aprender?",
        bloque="idiomas",
        tipo="texto",
    ),
    Hecho(
        id="nivel_ingles",
        pregunta_typeform="¿Cuál es tu nivel de inglés?",
        bloque="idiomas",
        tipo="opcion",
        opciones=NIVEL_IDIOMA,
        origen_opciones=PENDIENTE_CONFIRMAR,
        nota=(
            "Declarado, NO medido. El examen real es el de AMES dentro de la "
            "plataforma; esto es sólo la percepción de la persona y no debe "
            "presentarse como un nivel certificado."
        ),
    ),
    Hecho(
        id="segundo_idioma",
        pregunta_typeform="¿Dominas un segundo idioma? ¿Cuál? ¿Cuál es tu nivel?",
        bloque="idiomas",
        tipo="texto",
        nota="Tres preguntas encadenadas del Typeform · en conversación es una.",
    ),
    # --- Cierre comercial --------------------------------------------------
    Hecho(
        id="cuando_viajar",
        pregunta_typeform="¿Cuándo deseas viajar?",
        bloque="cierre",
        tipo="opcion",
        opciones=CUANDO_VIAJAR,
        onboarding_key="timeline",
        obligatorio=True,
    ),
    Hecho(
        id="inversion",
        pregunta_typeform="¿Cuánto piensas invertir en tus estudios?",
        bloque="cierre",
        tipo="opcion",
        opciones=INVERSION,
        onboarding_key="budget",
        alarma=True,
        obligatorio=True,
        nota=(
            "Verónica (12:03): 'le pregunto qué presupuesto piensas invertir, "
            "no, mil dólares → de una que ha muerto'. Aparece 3 veces en el "
            "Typeform porque cada rama la vuelve a pedir."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Accesores
# ---------------------------------------------------------------------------

_POR_ID: Dict[str, Hecho] = {h.id: h for h in HECHOS}


def get_hecho(hecho_id: str) -> Optional[Hecho]:
    return _POR_ID.get(hecho_id)


def ids_obligatorios() -> List[str]:
    """Sin estos el bot no cierra la conversación."""
    return [h.id for h in HECHOS if h.obligatorio]


def ids_alarma() -> List[str]:
    """Los que por sí solos pueden degradar o matar el lead."""
    return [h.id for h in HECHOS if h.alarma]


def faltantes(recolectados: Dict[str, Any]) -> List[Hecho]:
    """Hechos que aún no tienen valor · el bot prioriza sobre esta lista.

    Un valor `None` cuenta como faltante a propósito: el extractor deja `None`
    cuando no pudo mapear con confianza, y eso significa "hay que volver a
    preguntarlo", no "ya se preguntó".
    """
    return [h for h in HECHOS if recolectados.get(h.id) is None]


def mapa_a_onboarding(recolectados: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce los hechos del perfilador a claves de `User.onboarding_answers`.

    Es el puente que pidió Verónica: quien llega a la plataforma **por rebote de
    la página** no debe volver a responder lo que el bot ya preguntó
    ("no importa si yo entro de cero, me las hace; si entro por rebote, ya las
    hizo", 43:29).

    Sólo viaja lo que tiene `onboarding_key`: el resto (visas, contacto,
    contraoferta) es del perfilador comercial y no tiene sentido dentro de la
    plataforma.

    **Dos cosas que a propósito NO se derivan:**

    - `main_goal` desde `tipo_experiencia`. Se parecen, pero no son lo mismo:
      "hacer un pregrado" no dice si la persona quiere *definir qué estudiar* o
      ya lo tiene claro. `journey_service` ya tomó esta decisión para dos de sus
      opciones (`_GOALS_SIN_EQUIVALENTE`) con el argumento correcto: sembrar una
      equivalencia forzada es registrar que eligió algo que no eligió. Se deja
      vacío y la plataforma lo pregunta.
    - `birthdate` desde `edad`. Una edad declarada da el año con ±1 de error, y
      ese campo alimenta el gate de menores (M-006, el permiso de los padres).
      Un año equivocado ahí puede saltarse un consentimiento parental — no es un
      redondeo aceptable.
    """
    salida: Dict[str, Any] = {}
    for hecho in HECHOS:
        if not hecho.onboarding_key:
            continue
        valor = recolectados.get(hecho.id)
        if valor is None:
            continue
        salida[hecho.onboarding_key] = valor
    return salida


def opciones_pendientes_de_confirmar() -> List[str]:
    """Hechos cuyas opciones inventamos nosotros · para llevárselos a Verónica."""
    return [h.id for h in HECHOS if h.origen_opciones == PENDIENTE_CONFIRMAR]
