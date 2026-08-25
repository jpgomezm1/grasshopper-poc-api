"""Statement of Purpose · el ensayo para postularse a una universidad.

Pedido literal de la clienta (reunión del 2026-08-24, minuto 12:57):

    "Necesito eso mismo pero postulación a una universidad, o sea que él me haga
     el Statement of Purpose, que es como la carta, que es un ensayo donde yo digo
     quiero aplicar a la Universidad de Manchester a este pregrado, y tú ya me
     conoces, pues ya tienes mi hoja de vida, pues ya tienes mis test."

Ese *"ya me conoces"* es la especificación entera: el ensayo se escribe con lo
que la plataforma YA tiene de la persona —perfil consolidado, resultados de los
tests, actividades y logros— y con nada más. Por eso este servicio no recibe un
formulario largo: recibe el `CVData` que ya se arma para la hoja de vida (la
misma que ella edita y descarga) y lo serializa con
`cv_tailor_service.describir_cv`, que ya existía y ya sabe decir explícitamente
"actividades: ninguna registrada" para que el modelo no asuma que se le olvidó
pasarlas y se las invente.

## Las tres garantías, y por qué son estructurales

**El disclaimer de los detectores de IA.** También lo pidió ella, explícito
(13:14): *"que uno le ponga un disclaimer, pues tú sí, modifícalo porque las
universidades tienen software"*. Se refiere a los detectores de texto generado
por IA. `DISCLAIMER` es un texto FIJO que pone este módulo — nunca se le pide al
modelo que se acuerde de avisar, y `normalizar()` lo escribe siempre, venga lo
que venga en la respuesta.

**Lo que no sabemos, se marca; no se inventa.** El modelo no conoce el ranking
de la universidad, ni sus profesores, ni sus materias, ni sus fechas. El prompt
le obliga a dejar `[corchetes]` en su lugar y `_completar()` los **recoge del
texto final** y los devuelve como lista de pendientes. Es un circuito cerrado:
un hueco que la persona podría no ver leyendo por encima termina siendo un ítem
de una lista en pantalla.

**Ninguna cifra sobrevive.** `tools_guardrails.redactar_cifras` sustituye
cualquier cosa con forma de dinero o de porcentaje —el ranking, la beca, el
"top 5%"— por un corchete, que a su vez cae en la lista de pendientes por el
punto anterior. La regla del proyecto es que la IA nunca inventa datos duros, y
aquí no depende de que el modelo obedezca el prompt.

## Qué NO hace

No persiste nada. No hay tabla para esto y crear una migración estaba fuera del
alcance de la tarea; meterlo en `user.onboarding_answers` —donde sí vive el
análisis de brecha— sería peor: ese JSON lo leen los prompts del journey, y un
ensayo de 600 palabras ahí dentro se cuela en llamadas que no lo pidieron. El
ensayo se devuelve, la persona lo copia. Que un borrador con datos personales de
un menor no quede almacenado sin política de retención es, además, la opción
prudente con Habeas Data.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services import tools_guardrails as guard

logger = logging.getLogger(__name__)


class SOPError(RuntimeError):
    """No se pudo escribir el borrador del Statement of Purpose."""


MIN_UNIVERSIDAD = 2
MAX_UNIVERSIDAD = 160
MAX_PROGRAMA = 160
MAX_PAIS = 80
MAX_MOTIVACION = 1500

#: Idiomas en los que se puede pedir el ensayo. El copy de la app es siempre
#: español, pero el ensayo NO es copy de la app: es un documento que va a un
#: comité de admisiones, y a Manchester se manda en inglés.
IDIOMAS = ("es", "en")
IDIOMA_POR_DEFECTO = "es"

_INSTRUCCION_IDIOMA = {
    "es": (
        "Escribe el ensayo en ESPAÑOL neutro. Conserva en su idioma original "
        "los nombres propios de universidades, programas y ciudades."
    ),
    "en": (
        "Write the essay in ENGLISH. Todo lo demás que devuelvas "
        "(`puntos_usados`, `que_debes_completar`) va en ESPAÑOL: eso lo lee la "
        "persona, no el comité de admisiones."
    ),
}

# El texto que ella pidió. Va completo y arriba en la respuesta · no en letra
# chica. Dice QUÉ hacer y POR QUÉ, que es lo que hace que alguien haga caso.
DISCLAIMER = (
    "Este es un BORRADOR escrito por una inteligencia artificial con la "
    "información que tenemos tuya. No lo envíes tal cual: muchas universidades "
    "revisan los ensayos con software que detecta texto generado por IA, y un "
    "texto que no suena a ti puede costarte la admisión. Reescríbelo con tus "
    "palabras, cambia el orden de las ideas, agrega los detalles que sólo tú "
    "conoces y verifica que cada frase sea verdad. Este ensayo va a llevar tu "
    "nombre."
)

# Pasos concretos · el disclaimer explica el porqué, esto dice qué hacer.
COMO_USARLO = (
    "Léelo completo en voz alta y quita todo lo que no suene a ti.",
    "Reemplaza cada [corchete] con datos que hayas verificado tú en la página "
    "de la universidad. Nosotros no los conocemos y no los inventamos.",
    "Reescribe al menos el primer y el último párrafo con tus propias palabras: "
    "son los que más se notan.",
    "Contrasta cada logro que menciona contra lo que de verdad hiciste.",
    "Revisa el límite de palabras y el formato exacto que pide la universidad; "
    "esa información no la tenemos.",
    "Pídele a alguien que te conozca que lo lea y te diga si suena a ti.",
)


ESQUEMA_SOP: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "parrafos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Entre 4 y 6 párrafos. Uno por elemento, sin numerar.",
        },
        "puntos_usados": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Los datos concretos del perfil de la persona que usaste, tal "
                "como aparecen en su perfil. Sirve para que ella verifique."
            ),
        },
        "que_debes_completar": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Cada corchete que dejaste en el texto, explicado: qué dato "
                "tiene que buscar ella y dónde va."
            ),
        },
    },
    "required": ["parrafos"],
}


def _instruccion_idioma(idioma: Optional[str]) -> str:
    return _INSTRUCCION_IDIOMA.get(
        (idioma or "").strip().lower(), _INSTRUCCION_IDIOMA[IDIOMA_POR_DEFECTO]
    )


def normalizar_idioma(idioma: Optional[str]) -> str:
    limpio = (idioma or "").strip().lower()
    return limpio if limpio in IDIOMAS else IDIOMA_POR_DEFECTO


def describir_destino(
    *,
    universidad: str,
    programa: str,
    pais: Optional[str] = None,
) -> str:
    """El bloque del prompt con a dónde se postula · sólo lo que ella escribió.

    No se enriquece con nada del catálogo de programas a propósito: hay una
    decisión de producto pendiente sobre qué universidades se quedan, y cruzar
    ese catálogo aquí ataría el ensayo a una tabla que va a cambiar.
    """
    lineas = [f"Universidad: {universidad}", f"Programa al que se postula: {programa}"]
    if pais:
        lineas.append(f"País: {pais}")
    lineas.append(
        "No tienes ningún otro dato sobre esta universidad ni sobre este "
        "programa. Todo lo que necesites de ellos va entre corchetes."
    )
    return "\n".join(lineas)


def _completar(parrafos: List[str], declarados: List[str]) -> List[str]:
    """Une lo que el modelo declaró como pendiente con lo que hay en el texto.

    El texto manda: si el modelo dejó un corchete y se le olvidó anotarlo, el
    corchete entra igual. Al revés también vale —un pendiente declarado que no
    dejó hueco sigue siendo información útil— pero lo que garantiza que no se
    escape nada es leer el texto final, no la buena memoria del modelo.
    """
    pendientes = list(declarados)
    for encontrado in guard.marcadores(parrafos):
        # Comparación laxa: el modelo suele anotar el pendiente con otras
        # palabras que el corchete. Sólo se añade si no está ya cubierto.
        if not any(encontrado.lower() in d.lower() for d in pendientes):
            pendientes.append(encontrado)
    return pendientes[:15]


def normalizar(
    bruto: Dict[str, Any],
    *,
    universidad: str,
    programa: str,
    pais: Optional[str],
    idioma: str,
) -> Dict[str, Any]:
    """Acota, redacta cifras y añade SIEMPRE el disclaimer.

    El orden importa: primero se recortan los párrafos, después se redactan las
    cifras y **al final** se recogen los corchetes — así los corchetes que puso
    la propia redacción de cifras también terminan en la lista de pendientes.
    """
    crudos = guard.parrafos(bruto.get("parrafos"), max_parrafos=8, max_chars=2500)
    parrafos = [p for p in (guard.redactar_cifras(c) for c in crudos) if p]

    texto_completo = "\n\n".join(parrafos)

    return {
        "universidad": universidad,
        "programa": programa,
        "pais": pais,
        "idioma": idioma,
        "parrafos": parrafos,
        # El texto ya unido es lo que la persona copia y pega · la acción
        # principal de esta pantalla es "copiar", no "leer".
        "texto": texto_completo,
        # Se cuenta en Python: los límites de palabras de una convocatoria son
        # duros y un modelo contando sus propias palabras se equivoca.
        "palabras": guard.contar_palabras(texto_completo),
        "puntos_usados": guard.lista_texto(bruto.get("puntos_usados"), 12, 240),
        "que_debes_completar": _completar(
            parrafos, guard.lista_texto(bruto.get("que_debes_completar"), 10, 240)
        ),
        "disclaimer": DISCLAIMER,
        "como_usarlo": list(COMO_USARLO),
    }


def hay_con_que_escribir(cv: Any) -> bool:
    """¿Tenemos algo cierto de esta persona con lo que fundamentar un ensayo?

    Si no hay ni perfil, ni tests, ni actividades, el modelo no tendría de dónde
    sacar nada y el ensayo sería invención pura. Preferimos no generarlo: es la
    misma postura de `cv_tailor_service` (lo que falta se dice, no se rellena).
    """
    return bool(
        (getattr(cv, "summary", None) or "").strip()
        or getattr(cv, "strengths", None)
        or getattr(cv, "interests", None)
        or getattr(cv, "test_highlights", None)
        or getattr(cv, "activities", None)
    )


def escribir(
    *,
    cv: Any,
    universidad: str,
    programa: str,
    pais: Optional[str] = None,
    idioma: str = IDIOMA_POR_DEFECTO,
    motivacion: Optional[str] = None,
    session_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Escribe el borrador. Devuelve ``(sop, metadata_de_ia)``.

    Valida ANTES de gastar la llamada, igual que `career_gap_service`: sin
    universidad y programa no hay nada que escribir.
    """
    universidad = (universidad or "").strip()
    programa = (programa or "").strip()
    if len(universidad) < MIN_UNIVERSIDAD or len(programa) < MIN_UNIVERSIDAD:
        raise SOPError(
            "Dinos a qué universidad y a qué programa te vas a postular: sin eso "
            "no puedo escribir tu carta."
        )
    universidad = universidad[:MAX_UNIVERSIDAD]
    programa = programa[:MAX_PROGRAMA]
    pais = (pais or "").strip()[:MAX_PAIS] or None
    idioma = normalizar_idioma(idioma)

    if not hay_con_que_escribir(cv):
        raise SOPError(
            "Todavía no tenemos con qué escribir tu carta. Completa al menos un "
            "test o registra tus actividades y logros, y vuelve."
        )

    # Import diferido · igual que el resto de servicios de IA de este repo: deja
    # el módulo importable sin credenciales y no penaliza el arranque.
    from app.core.ai_client import call_claude_tool, load_prompt
    from app.services import cv_tailor_service

    prompt = load_prompt("sop_universidad").format(
        idioma_instruccion=_instruccion_idioma(idioma),
        destino=describir_destino(
            universidad=universidad, programa=programa, pais=pais
        ),
        motivacion=(motivacion or "").strip()[:MAX_MOTIVACION]
        or "(no escribió nada · no lo inventes, apóyate sólo en su perfil)",
        # Se reutiliza el serializador de la hoja de vida en vez de escribir
        # otro: si el CV cambia de forma, el ensayo se entera solo. Es también
        # la única fuente que ya sabe decir "actividades: ninguna registrada".
        hoja_de_vida=cv_tailor_service.describir_cv(cv),
    )

    datos, meta = call_claude_tool(
        prompt,
        tool_name="escribir_statement_of_purpose",
        tool_description=(
            "Escribe el borrador de un Statement of Purpose usando SÓLO el "
            "perfil real de la persona, sin inventar datos sobre ella ni sobre "
            "la universidad."
        ),
        input_schema=ESQUEMA_SOP,
        session_id=session_id,
        feature="sop_universidad",
        max_tokens=3000,
        # Más alta que el resto del repo (0-0.2) a propósito: aquí la variación
        # SÍ agrega valor. Un ensayo a temperatura 0 suena a plantilla, que es
        # justo lo que los detectores de las universidades marcan. La garantía
        # anti-invención no vive en la temperatura, vive en `normalizar()`.
        temperature=0.6,
    )

    if not datos:
        raise SOPError(
            "No pude escribir tu carta en este momento. Intenta de nuevo en un rato."
        )

    resultado = normalizar(
        datos,
        universidad=universidad,
        programa=programa,
        pais=pais,
        idioma=idioma,
    )
    if not resultado["parrafos"]:
        raise SOPError(
            "No pude escribir tu carta en este momento. Intenta de nuevo en un rato."
        )
    return resultado, meta
