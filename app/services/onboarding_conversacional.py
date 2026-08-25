"""El onboarding de la plataforma, como conversación en vez de formulario.

Verónica, reunión 21-07: *"No podemos llevar la IA a ser como un formulario"* ·
*"con ocho preguntas fui capaz de entender a Sebastián; con trece ni lo entendí"*.

El formulario tiene 14 pasos y en el flujo "quiero estudiar en el exterior" —el de
su propio hijo— se recorren 13. Esto lo reemplaza: un turno de conversación puede
resolver varios hechos a la vez, y los cinco pasos de voz se vuelven simplemente
lo que la persona cuenta.

## Qué se reusa y qué no

El **extractor de hechos** es el mismo del bot comercial, parametrizado por
catálogo (`fact_extractor.extraer(..., catalogo=onboarding_hechos)`). Ahí vive el
riesgo real —escribir en el perfil un valor que la persona nunca dijo— y su
blindaje (tool use forzado, validación contra el vocabulario canónico de la
plataforma, umbral de confianza) tiene que ser idéntico en las dos
conversaciones. Duplicarlo garantizaría que una copia se quedara atrás.

El **motor de turno** no se reusa: el del perfilador arrastra su propio cierre
comercial (contraoferta de destinos, score del lead) que aquí no aplica.

## El contrato con el resto del producto

`a_onboarding_answers()` produce **exactamente** el diccionario que producía el
formulario, con las mismas claves y los mismos códigos. El recomendador, el gate
de menores, `seed_session_from_onboarding` y los prompts de IA siguen leyendo lo
que leían: no saben que la pantalla cambió.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from app.core.ai_client import call_claude_chat, load_prompt
from app.data import onboarding_hechos as catalogo
from app.services.ai_usage_service import record_ai_usage
# Se importa en vez de duplicarse · es una función pura sobre listas y está
# probada contra el modelo real: pedirle en el prompt que no repita una pregunta
# mejora el tono pero no alcanza. Sin esto, el onboarding preguntó el presupuesto
# dos turnos seguidos mientras la persona le daba etapa, fecha y destino — el
# "formulario con burbujas" que esto vino a reemplazar.
from app.services.conversation_engine import _rotar_si_no_respondieron
from app.services.fact_extractor import extraer

logger = logging.getLogger(__name__)

PROMPT_NAME = "onboarding_conversacional"
PROMPT_VERSION = "onboarding_conversacional_v1"
FEATURE = "onboarding_conversacion"

# Cuántos turnos previos se le pasan al modelo. Suficiente para que la
# conversación tenga memoria corta y no para que el prompt crezca sin control.
MAX_HISTORIAL = 16

# Si el modelo no responde, la conversación no puede quedarse muda: la persona
# está en el primer minuto del producto y un silencio se lee como que se rompió.
MENSAJE_FALLBACK = (
    "Perdona, se me enredó la respuesta. ¿Me lo cuentas otra vez?"
)

SALUDO = (
    "¡Hola! Soy tu guía. Antes de mostrarte opciones quiero conocerte un poco.\n\n"
    "Cuéntame: ¿qué te apasiona y qué te gustaría lograr?"
)


def _bloque_recolectado(recolectados: Dict[str, Any]) -> str:
    con_valor = {k: v for k, v in recolectados.items() if v not in (None, "", [], {})}
    if not con_valor:
        return "(nada todavía · es el primer mensaje)"
    lineas = []
    for k, v in con_valor.items():
        h = catalogo.get_hecho(k)
        etiqueta = h.pregunta_typeform if h else k

        # La edad se le da calculada · probándolo, el modelo vio "2009" y cerró
        # con "tienes 15 años" cuando eran 16. El dato guardado estaba bien; el
        # error era suyo al hacer la cuenta. Un estudiante que lee mal su propia
        # edad deja de creerle al resto de la conversación, y la aritmética es
        # justo lo que no hay que delegarle a un modelo pudiendo dársela hecha.
        #
        # Se calcula desde el 31 de diciembre, igual que se guarda: da la edad
        # MÍNIMA posible, que es la dirección segura para el gate de menores.
        if k == "birthdate":
            try:
                from datetime import date
                anio = int(str(v)[:4])
                hoy = date.today()
                edad = hoy.year - anio - (0 if (hoy.month, hoy.day) >= (12, 31) else 1)
                lineas.append(f"- Edad → {edad} años (nació en {anio})")
                continue
            except (TypeError, ValueError):
                pass  # sin año usable se muestra crudo, como cualquier otro
        # Se le muestra la etiqueta legible y no el código: si ve `high_school`,
        # tiende a repetírselo a la persona tal cual.
        if h and h.opciones and isinstance(v, str):
            v = h.opciones.get(v, v)
        elif h and h.opciones and isinstance(v, list):
            v = ", ".join(h.opciones.get(x, x) for x in v)
        lineas.append(f"- {etiqueta} → {v}")
    return "\n".join(lineas)


def _rotar_dentro_del_tramo(
    antes: List[str], ahora: List[str], recolectados: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Baja la pregunta sin responder, **pero sólo detrás de sus iguales**.

    La versión del bot comercial la mandaba al final de toda la cola, y aquí eso
    abre una trampa que apareció probándolo con JP: a *"¿qué quieres resolver?"*
    respondió *"saber si puedo vivir de esto"*, el extractor se abstuvo con razón
    (no mapeaba a ninguna opción), y `main_goal` —que es **obligatorio**— se fue
    al final detrás de diez preguntas opcionales.

    Consecuencia: la conversación **no podía cerrar nunca**. Seguía preguntando
    hasta agotar los 14 datos, que es exactamente el formulario que esto vino a
    reemplazar, y sin salida visible para la persona.

    Rotando dentro del tramo, un obligatorio cede el turno a otro obligatorio y
    nunca a uno opcional. Si es el único que queda en su tramo, se queda al
    frente y se vuelve a preguntar —reformulado, porque el modelo reacciona a lo
    que la persona acaba de decir—, que es mucho mejor que no terminar jamás.

    `recolectados` es opcional y sólo importa para `grade`: es obligatorio
    SOLO para un estudiante de colegio (`catalogo.OBLIGATORIO_SI_PERFIL`), y
    sin pasarle el perfil actual `catalogo.es_obligatorio` no tiene cómo
    saberlo — se degrada a mirar sólo `catalogo.OBLIGATORIOS`, que es
    exactamente el comportamiento de antes de que existiera la malla de 5
    rutas.
    """
    if not (antes and ahora and antes[0] == ahora[0]):
        return ahora

    cabeza = ahora[0]
    contexto = recolectados or {}
    obligatorio = catalogo.es_obligatorio(cabeza, contexto)
    tramo = [x for x in ahora[1:] if catalogo.es_obligatorio(x, contexto) == obligatorio]
    if not tramo:
        return ahora  # es el único de su tramo · insistir es lo correcto

    resto = [x for x in ahora[1:] if x not in tramo]
    return tramo + [cabeza] + resto


def _bloque_faltantes(pendientes: List[str]) -> str:
    """Lo que falta · **una sola pregunta destacada**, el resto como contexto.

    La primera versión le mostraba al modelo una lista numerada de seis
    pendientes, y probándolo con JP agrupó dos hechos en un mismo mensaje dos
    veces en seis turnos: *"¿cómo te gustaría estudiar? ¿te ves yéndote a otro
    país?"*. Es razonable — al ver seis preguntas trata de ser eficiente.

    Pedirlo en el prompt no basta: ya dice "una sola pregunta por mensaje" y aun
    así lo hizo. Es el mismo aprendizaje que dejó la repetición de preguntas en
    el bot comercial ("mejora el tono pero no alcanza").

    **No puede agrupar lo que no ve.** Se destaca una, y las demás van marcadas
    como "todavía no": le sirven para no cerrar antes de tiempo, no para
    preguntarlas.
    """
    if not pendientes:
        return "(nada · ya tienes todo lo necesario)"

    h = catalogo.get_hecho(pendientes[0])
    if h is None:
        return "(nada · ya tienes todo lo necesario)"

    marca = " · esto se pregunta, no se deduce" if pendientes[0] in catalogo.DUROS else ""
    lineas = [
        f"**Lo único que quieres averiguar ahora:** "
        f"{catalogo.que_averiguar(pendientes[0])}{marca}",
        "",
        # Antes iba aquí el texto literal de la pregunta del formulario, y el
        # modelo lo repetía tal cual: la conversación sonaba idéntica siempre,
        # sin importar lo que la persona hubiera contado. Eran las mismas
        # catorce frases en otro envase.
        "Formula tú la pregunta a partir de lo que acaba de contarte. Nada de "
        "frases prefabricadas: a quien te habló de dibujar se le pregunta por "
        "sus fortalezas de otra forma que a quien te habló de fútbol.",
        "",
        "Una sola pregunta. Si metes dos en el mismo mensaje, esto vuelve a ser "
        "un formulario.",
    ]

    despues = [catalogo.que_averiguar(x) for x in pendientes[1:4]]
    if despues:
        lineas += ["", "Queda para más adelante — **no lo preguntes todavía**:"]
        lineas += [f"- {x}" for x in despues]
    return "\n".join(lineas)


def _bloque_cierre(recolectados: Dict[str, Any], pendientes: List[str]) -> str:
    if not catalogo.listo_para_cerrar(recolectados):
        return ""
    return (
        "## Ya puedes cerrar\n\n"
        "Tienes lo necesario. Cierra en tu próximo mensaje: dile en una o dos "
        "frases lo que entendiste de él —con sus palabras, no con etiquetas— y "
        "que ya puede empezar. No hagas más preguntas."
    )


def primer_mensaje() -> str:
    """Con qué abre la conversación · no lo genera el modelo.

    Es la primera frase que un estudiante lee del producto, y dejarla al modelo
    la volvería distinta en cada sesión y difícil de revisar por la clienta, que
    revisa la copy.
    """
    return SALUDO


_SIN_DINERO = (
    "\n\n**No le preguntas por dinero.** No lo sabe y no le corresponde: eso lo "
    "hablan sus papás con el asesor. Si él lo menciona, lo recibes sin ahondar."
)

# Las 5 rutas de la malla completa (Cimientos, migración 067). Antes esto eran
# dos bloques —colegio y profesional—; la malla le pide cosas distintas a un
# chico de 9° que a uno de 12°, y meterlos en el mismo "colegio" era perder
# justo la diferencia que el cliente pidió: un chico de 13 años necesita un
# tono sin presión, uno de 12° necesita acompañamiento de ejecución.
#
# Cada bloque es SOBRE TODO tono — de qué se habla y de qué no — no una lista
# de preguntas: cuáles preguntas se activan ya lo decide `SOLO_SI_RUTA` en el
# catálogo, esto es cómo *se siente* hablar con cada uno.
_BLOQUE_POR_RUTA = {
    catalogo.RUTA_GRADO_9: (
        "Está en noveno, tiene entre 13 y 15 años, y esto es apenas el arranque "
        "de la conversación sobre su futuro — no el final. **Nada de presión "
        "por decidir.** Tu tono es curioso y ligero: se trata de que se conozca, "
        "no de que resuelva su carrera hoy.\n\n"
        "Pregúntale por lo que le gusta del colegio, a quién admira, qué haría "
        "si nadie le calificara. Todavía no tiene sentido hablarle de "
        "universidades ni de aplicaciones — eso está a años, y mencionarlo "
        "ahora es la misma prisa que un formulario de admisión." + _SIN_DINERO
    ),
    catalogo.RUTA_GRADO_10: (
        "Está en décimo, empezando a sentir que se acerca el momento de elegir "
        "— sin estar ahí todavía. Es un tono intermedio: ya puedes preguntarle "
        "qué materias le gustaría profundizar o qué le pone nervioso de la "
        "decisión, pero sigue siendo exploración, no plan de acción.\n\n"
        "Si te cuenta que le da ansiedad no saber qué quiere, no lo apures a "
        "resolverlo — acompáñalo a nombrarlo." + _SIN_DINERO
    ),
    catalogo.RUTA_GRADO_11: (
        "Está en once. En un colegio de calendario colombiano estándar este es "
        "su último año; en uno bilingüe, IB o americano puede quedarle uno más "
        "— tú no lo sabes todavía, así que no des por hecho cuál de los dos es. "
        "Aquí sí empieza lo concreto: carreras que tiene en mente, si ya "
        "presentó PSAT o SAT, si ha visitado universidades. Puedes hablar de "
        "aplicar y de plazos, pero **nunca prometas que algo va a pasar** — "
        "no sabes cupos ni fechas de nadie." + _SIN_DINERO
    ),
    catalogo.RUTA_GRADO_12: (
        "Está en doce — el último año de un colegio que llega hasta ahí (IB, "
        "americano, bilingüe). Ya no es exploración: es **ejecución**. Puede "
        "estar aplicando ahora mismo o a punto de hacerlo, con fechas límite "
        "reales encima. Pregúntale si ya aplicó y con qué puntajes cuenta, y "
        "trátalo como a alguien que está EN la decisión, no acercándose a "
        "ella.\n\n"
        "El acompañamiento aquí es distinto: menos '¿qué te gustaría?' y más "
        "'¿cómo vas?'. Sigue sin ser quien paga, así que el dinero se recibe si "
        "lo menciona, no se pregunta." + _SIN_DINERO
    ),
    catalogo.RUTA_PROFESIONAL: (
        "Ya está en la universidad o ya pasó por ella: puede estar cursando "
        "una carrera, recién graduado, trabajando, o buscando cambiar de "
        "rumbo. No está decidiendo por primera vez — trae recorrido, y a "
        "veces desencanto con lo que eligió.\n\n"
        "Pregúntale por lo que ya vivió, no por lo que imagina: qué ha "
        "estudiado o trabajado, qué le sirvió de eso y qué no. Tratarlo como "
        "a un chico de 16 es la forma más rápida de perderlo.\n\n"
        "**Con él el dinero sí se habla.** Es quien decide y por lo general "
        "quien paga, así que puedes preguntarle por su presupuesto con "
        "naturalidad. Si no lo tiene claro, lo recibes y sigues."
    ),
}

# Fallback genérico cuando se sabe el perfil (colegio) pero todavía no el
# grado — o cuando ni siquiera se sabe el perfil. Es el mismo bloque de dos
# vías que existía antes de la malla de 5 rutas: sigue siendo lo correcto
# mientras la ruta exacta no se pueda derivar, por el mismo criterio
# conservador que usa `ruta()` — ruta desconocida no se adivina.
_BLOQUE_COLEGIO_GENERICO = (
    "Es un estudiante de colegio, de 9° en adelante, y está frente a la "
    "decisión más grande que ha tomado. Todavía no sabes en qué grado exacto "
    "está, así que no le des un tono de urgencia ni de años por delante: "
    "pregúntaselo pronto, porque de eso depende cómo seguir la conversación."
    + _SIN_DINERO
)

_BLOQUE_SIN_ETAPA = (
    "Todavía no sabes en qué etapa está: puede ser un estudiante de colegio "
    "o alguien que ya pasó por la universidad. Hasta saberlo no des por "
    "hecha su edad ni su experiencia, y no le preguntes por dinero."
)


def _bloque_perfil(recolectados: Dict[str, Any]) -> str:
    """Con quién está hablando · el prompt ya no lo da por hecho.

    Venía clavado en el prompt que la persona tenía "entre 15 y 19 años". Para
    un profesional que ya se graduó eso no es un matiz de tono: le hace hablar
    como si estuviera decidiendo por primera vez, y le prohibe tocar el dinero
    —que en su caso sí le corresponde, porque es quien paga—.

    Ahora hay 5 rutas (malla completa, Cimientos) en vez de 2 perfiles: un
    chico de 9° (tono amigable, sin presión) no recibe el mismo trato que uno
    de 12° (ejecución, fechas límite) ni que un adulto. Mientras la ruta no se
    pueda derivar —porque falta `life_stage`, o porque es colegio pero falta
    `grade`— el bloque lo dice en vez de inventarlo: adivinar sale más caro
    que preguntar.
    """
    r = catalogo.ruta(recolectados)
    if r is not None:
        return _BLOQUE_POR_RUTA[r]

    if catalogo.perfil(recolectados) == catalogo.PERFIL_COLEGIO:
        return _BLOQUE_COLEGIO_GENERICO

    return _BLOQUE_SIN_ETAPA


def responder(
    mensaje: str,
    historial: List[Dict[str, str]],
    recolectados: Dict[str, Any],
    *,
    session_id: str,
    db: Optional[DBSession] = None,
) -> Tuple[str, Dict[str, Any], bool]:
    """Procesa un turno.

    Returns:
        (respuesta, recolectados_actualizados, listo_para_cerrar).
        `recolectados_actualizados` es un dict NUEVO · quien llama decide si lo
        persiste, y así un fallo a mitad de turno no deja el estado a medias.
    """
    # 1 · Qué dijo · lo nuevo pisa lo viejo, que es cómo funcionan las
    # correcciones ("no, en realidad estoy en décimo").
    nuevos, descartados = extraer(
        mensaje, recolectados, session_id=session_id, db=db, catalogo=catalogo,
    )
    actualizados = {**recolectados, **nuevos}

    if descartados:
        logger.info(
            "onboarding · hechos descartados por el extractor",
            extra={"session_id": session_id, "descartados": descartados},
        )

    # Qué falta, y si el bot ya preguntó por lo primero sin obtener respuesta,
    # eso baja: se retoma más adelante, cuando la conversación dé pie.
    #
    # La condición es que la persona **ya haya hablado antes**, no que exista
    # historial: el historial arranca con el saludo, que pregunta por lo que le
    # apasiona. Contándolo, en el primer turno el código creía que ya se había
    # preguntado por la etapa de vida sin obtener respuesta, y la mandaba al
    # final — así que el campo más importante para filtrar (`life_stage`, que
    # decide si se le ofrecen maestrías a alguien de 11°) quedaba postergado
    # SIEMPRE, en toda conversación.
    ya_hablo = any(t.get("role") == "user" for t in (historial or []))
    pendientes = _rotar_dentro_del_tramo(
        catalogo.faltantes(recolectados) if ya_hablo else [],
        catalogo.faltantes(actualizados),
        actualizados,
    )

    plantilla = load_prompt(PROMPT_NAME)
    system = (
        plantilla.replace("{perfil}", _bloque_perfil(actualizados))
        .replace("{recolectado}", _bloque_recolectado(actualizados))
        .replace("{faltantes}", _bloque_faltantes(pendientes))
        .replace("{cierre}", _bloque_cierre(actualizados, pendientes))
    )

    recortado = list(historial or [])[-MAX_HISTORIAL:]
    mensajes = [{"role": t["role"], "content": t["content"]} for t in recortado]
    mensajes.append({"role": "user", "content": mensaje})

    respuesta, meta = call_claude_chat(
        mensajes, system=system, session_id=session_id, feature=FEATURE,
    )

    if db is not None:
        record_ai_usage(
            db,
            provider="anthropic",
            model=meta.get("model"),
            feature=FEATURE,
            tokens_input=meta.get("tokens_input"),
            tokens_output=meta.get("tokens_output"),
            latency_ms=meta.get("latency_ms"),
        )

    if not respuesta:
        # Los hechos extraídos SÍ se conservan aunque la respuesta falle: la
        # persona ya dijo lo que dijo y perderlo la obliga a repetirse.
        logger.warning(
            "onboarding conversacional sin respuesta del modelo",
            extra={"session_id": session_id,
                   "error_kind": meta.get("error_kind")},
        )
        return MENSAJE_FALLBACK, actualizados, catalogo.listo_para_cerrar(actualizados)

    return respuesta, actualizados, catalogo.listo_para_cerrar(actualizados)


def a_onboarding_answers(recolectados: Dict[str, Any]) -> Dict[str, Any]:
    """Lo recolectado, en el formato que guarda `PUT /me/onboarding`.

    **El año de nacimiento se convierte a `YYYY-12-31`**, igual que hacía el
    formulario, y esa fecha no es un detalle: el 31 de diciembre da la edad
    mínima posible para ese año, así que ante la duda la persona se clasifica
    como **menor** y se le pide consentimiento parental. Nunca al revés. Usar
    enero 1 invertiría exactamente esa garantía.

    PENDIENTE fuera del alcance de este archivo: esto deja `grade`,
    `school_reported_last_grade` y `school_reported_accreditation` en
    `User.onboarding_answers` (JSON) — que es lo que ya leen `cv_pdf_service`,
    `pdf_service` y `dossier_service` (leían de un campo que nadie escribía;
    ahora sí lo escribe). Falta el otro lado: copiar esos mismos valores a las
    columnas TIPADAS `User.grade` (int) / `User.school_reported_last_grade` /
    `User.school_reported_accreditation` que trajo Cimientos (migración 067).
    Eso vive en `_persistir()` (`app/api/v1/onboarding_chat.py`) y
    `_sync_onboarding_to_user_columns()` (`app/api/v1/auth.py`) — archivos que
    no son de este agente; mismo patrón que ya hace ese código con
    `birthdate` → `user.birthdate`.
    """
    fuera = catalogo.a_onboarding_answers(recolectados)

    anio = fuera.get("birthdate")
    if isinstance(anio, int):
        fuera["birthdate"] = f"{anio:04d}-12-31"
    elif isinstance(anio, str) and anio.isdigit() and len(anio) == 4:
        fuera["birthdate"] = f"{anio}-12-31"

    return fuera
