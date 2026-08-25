"""El copy para postularse a un trabajo · mini app 2 de "Herramientas".

Pedido de JP en la reunión del 2026-08-24 (minuto 11:03):

    "una herramienta donde yo pongo la postulación a un trabajo y él me devuelve
     el copy para postularme"

y "es para el perfil adulto sobre todo" — *sobre todo*, no exclusivamente: un
estudiante de once que busca su primer trabajo de medio tiempo también lo usa,
así que aquí no se filtra por perfil. Lo que cambia según quién sea es de dónde
sale el insumo, no si se le deja entrar.

## Qué reutiliza · y por qué no se reescribió nada

* **El import de LinkedIn** (`linkedin_import_service`) ya estructura el perfil
  profesional y lo deja guardado en `onboarding_answers["career_linkedin_profile"]`.
  Aquí no se vuelve a pedir ni a parsear: se lee lo que ya está.
* **El análisis de brecha** (`career_gap_service`) ya calculó qué de su perfil
  encaja con el puesto al que apunta. `describir_perfil_actual()` de ese módulo
  es exactamente el serializador que necesita este prompt, así que se llama tal
  cual — si algún día ese perfil cambia de forma, este servicio se entera solo.
* **La hoja de vida** (`cv_tailor_service.describir_cv`) para quien tenga CV
  armado pero no LinkedIn (el caso del estudiante de colegio).

## Una sola llamada al modelo, a propósito

Se podría encadenar `cv_target_service.parsear()` (entender la vacante) y
después redactar, que es lo que hace el flujo de convocatorias del CV. Aquí no:
son dos llamadas secuenciales y este endpoint responde de forma síncrona, con
lo que dos llamadas rozan el timeout de 30s del router de Heroku (el mismo H12
que ya obligó a poner background + polling en las convocatorias). El aviso va
crudo dentro del prompt y `requisitos_detectados` devuelve lo que el modelo
entendió, que es la parte del parseo que la persona necesita ver para verificar
que leímos bien el aviso.

## Las garantías anti-invención

Las mismas tres de siempre, y ninguna depende de que el modelo obedezca:

1. Lo que NO cumple viaja en `no_cumples`, **separado del mensaje** — es la
   garantía estructural que `cv_tailor_service` ya usa para los faltantes.
2. `tools_guardrails.redactar_cifras` borra cualquier salario o porcentaje que
   se cuele, y el corchete que deja termina en `que_debes_completar`.
3. `disclaimer` lo pone este módulo, siempre, no el modelo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services import tools_guardrails as guard

logger = logging.getLogger(__name__)


class JobPitchError(RuntimeError):
    """No se pudo escribir el copy de la postulación."""


# Se reusan los límites de la convocatoria del CV: es el mismo gesto de la
# persona (pegar un aviso) y no tiene sentido que un texto que allá cabe, aquí
# no. Import diferido dentro de las funciones para no acoplar el arranque.
MIN_VACANTE = 120
MAX_VACANTE = 15000
MAX_NOTAS = 1500


@dataclass(frozen=True)
class Formato:
    """El canal por el que se manda · decide LARGO y TONO, no cosmética.

    Los tres son textos distintos de verdad, no el mismo con otro título: un
    mensaje de LinkedIn que ocupa una carta de presentación no se lee, y una
    carta formal escrita como un mensaje de chat se descarta. El límite se le
    dice al modelo (`instruccion`) y se le informa a la persona
    (`limite_caracteres`) para que vea cuánto le sobra.
    """

    clave: str
    nombre: str
    limite_caracteres: int
    lleva_asunto: bool
    instruccion: str


FORMATOS: Dict[str, Formato] = {
    "mensaje": Formato(
        clave="mensaje",
        nombre="Mensaje directo (LinkedIn o WhatsApp)",
        limite_caracteres=700,
        lleva_asunto=False,
        instruccion=(
            "Un mensaje directo para el reclutador, de los que se leen en el "
            "celular. Máximo 700 caracteres en total, 2 o 3 párrafos cortos. "
            "Directo desde la primera línea: quién es y por qué escribe. Sin "
            "encabezados ni despedidas largas. NO devuelvas asunto."
        ),
    ),
    "correo": Formato(
        clave="correo",
        nombre="Correo de postulación",
        limite_caracteres=1800,
        lleva_asunto=True,
        instruccion=(
            "Un correo de postulación. Devuelve también `asunto`: máximo 80 "
            "caracteres, con el nombre del cargo. El cuerpo, entre 3 y 4 "
            "párrafos, máximo 1800 caracteres en total. Cierra ofreciendo una "
            "conversación, sin rogar."
        ),
    ),
    "carta": Formato(
        clave="carta",
        nombre="Carta de presentación (cover letter)",
        limite_caracteres=3000,
        lleva_asunto=False,
        instruccion=(
            "Una carta de presentación formal, de las que se adjuntan junto a "
            "la hoja de vida. Entre 4 y 5 párrafos, máximo 3000 caracteres. "
            "Tono profesional y sobrio. NO devuelvas asunto."
        ),
    ),
}

FORMATO_POR_DEFECTO = "mensaje"

DISCLAIMER = (
    "Este texto lo escribió una inteligencia artificial con la información que "
    "nos diste. Revísalo antes de enviarlo: no digas nada que no puedas "
    "sostener en una entrevista, y ajusta el tono a la empresa. Lo que la "
    "vacante pide y hoy no tienes está aparte, en \"lo que no cumples\": no lo "
    "escondimos dentro del mensaje a propósito."
)


def obtener_formato(clave: Optional[str]) -> Formato:
    """Devuelve el formato pedido · cae al por defecto en vez de reventar."""
    return FORMATOS.get((clave or "").strip().lower(), FORMATOS[FORMATO_POR_DEFECTO])


def catalogo_formatos() -> List[Dict[str, Any]]:
    """Lo que la pantalla necesita para pintar el selector de formato."""
    return [
        {
            "clave": f.clave,
            "nombre": f.nombre,
            "limite_caracteres": f.limite_caracteres,
            "lleva_asunto": f.lleva_asunto,
        }
        for f in FORMATOS.values()
    ]


ESQUEMA_PITCH: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "asunto": {
            "type": "string",
            "description": "Sólo para el formato correo. Máximo 80 caracteres.",
        },
        "parrafos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "El cuerpo del mensaje, un párrafo por elemento.",
        },
        "requisitos_detectados": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Qué entendiste que pide la vacante. Frases cortas.",
        },
        "puntos_usados": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Datos concretos de su perfil que usaste en el texto.",
        },
        "no_cumples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "que": {"type": "string"},
                    "que_hacer": {
                        "type": "string",
                        "description": "Qué puede hacer al respecto, realista.",
                    },
                },
                "required": ["que"],
            },
            "description": "Lo que la vacante pide y ella hoy no tiene. NUNCA va en el mensaje.",
        },
        "que_debes_completar": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Cada corchete que dejaste en el texto, explicado.",
        },
    },
    "required": ["parrafos"],
}


def describir_perfil(
    *,
    perfil_linkedin: Optional[Dict[str, Any]] = None,
    current_role: Optional[str] = None,
    gap_analysis: Optional[Dict[str, Any]] = None,
    cv: Any = None,
) -> str:
    """Junta en un solo texto todo lo cierto que sabemos de la persona.

    Las tres fuentes son las que ya existen, en orden de cuánto pesan para una
    postulación laboral: LinkedIn (lo profesional), el análisis de brecha (lo
    que ya sabemos que encaja) y la hoja de vida (para quien no tiene LinkedIn,
    típicamente alguien de colegio).

    De la brecha se toman sólo `fortalezas_alineadas` y el resumen. Las brechas
    NO se pasan al prompt: son lo que le falta, y meterlas en el mismo texto que
    "esto es lo cierto sobre ella" es cómo un modelo termina escribiendo "estoy
    trabajando en mi nivel de inglés" en un mensaje a un reclutador sin que
    nadie se lo pidiera.
    """
    from app.services import career_gap_service, cv_tailor_service

    bloques: List[str] = []

    if perfil_linkedin or current_role:
        bloques.append(
            career_gap_service.describir_perfil_actual(
                perfil_linkedin, current_role=current_role
            )
        )

    if gap_analysis:
        lineas: List[str] = []
        resumen = (gap_analysis.get("resumen") or "").strip()
        if resumen:
            lineas.append(f"Resumen de su análisis de carrera: {resumen}")
        fortalezas = gap_analysis.get("fortalezas_alineadas") or []
        if fortalezas:
            lineas.append(
                "Fortalezas que ya le reconocimos: "
                + ", ".join(str(f) for f in fortalezas)
            )
        if lineas:
            bloques.append("\n".join(lineas))

    if cv is not None:
        bloques.append("--- Su hoja de vida ---\n" + cv_tailor_service.describir_cv(cv))

    if not bloques:
        # Decirlo explícito · si no, el modelo asume que se le olvidó pasarlo.
        return "(no hay ningún dato de perfil registrado todavía)"

    return "\n\n".join(bloques)


def hay_con_que_postularse(
    *, perfil_linkedin: Optional[Dict[str, Any]] = None, cv: Any = None
) -> bool:
    """¿Hay algo cierto con lo que redactar, o el texto sería invención pura?

    Se comparte con el catálogo de `/me/tools` para que lo que la pantalla dice
    que falta sea EXACTAMENTE lo que el endpoint exige. Dos predicados
    parecidos en dos sitios distintos es cómo se llega a un botón habilitado
    que devuelve 409.
    """
    if perfil_linkedin:
        return True
    from app.services import sop_service

    return cv is not None and sop_service.hay_con_que_escribir(cv)


def _no_cumples(valor: Any) -> List[Dict[str, Optional[str]]]:
    """Igual que los `faltantes` de `cv_tailor_service`: tolera strings sueltos."""
    if not isinstance(valor, list):
        return []
    salida: List[Dict[str, Optional[str]]] = []
    for item in valor:
        if not isinstance(item, dict):
            texto = guard.texto(item, 240)
            if texto:
                salida.append({"que": texto, "que_hacer": None})
            continue
        que = guard.texto(item.get("que"), 240)
        if not que:
            continue
        salida.append({"que": que, "que_hacer": guard.texto(item.get("que_hacer"), 300)})
    return salida[:6]


def normalizar(bruto: Dict[str, Any], *, formato: Formato) -> Dict[str, Any]:
    """Acota, redacta cifras y añade SIEMPRE el disclaimer.

    Mismo orden que en `sop_service`: recortar → redactar cifras → recoger
    corchetes, para que el hueco que deja una cifra redactada también salga en
    la lista de pendientes.
    """
    crudos = guard.parrafos(bruto.get("parrafos"), max_parrafos=6, max_chars=2000)
    parrafos = [p for p in (guard.redactar_cifras(c) for c in crudos) if p]

    asunto = None
    if formato.lleva_asunto:
        asunto = guard.redactar_cifras(guard.texto(bruto.get("asunto"), 120))

    texto_completo = "\n\n".join(parrafos)
    declarados = guard.lista_texto(bruto.get("que_debes_completar"), 10, 240)
    pendientes = list(declarados)
    for encontrado in guard.marcadores([asunto or ""] + parrafos):
        if not any(encontrado.lower() in d.lower() for d in pendientes):
            pendientes.append(encontrado)

    return {
        "formato": formato.clave,
        "formato_nombre": formato.nombre,
        "asunto": asunto,
        "parrafos": parrafos,
        # Listo para copiar · es la acción principal de esta pantalla.
        "texto": texto_completo,
        "caracteres": len(texto_completo),
        # Se informa el límite del canal para que la pantalla pueda mostrar
        # "820 / 700" en vez de recortar la frase a la mitad por su cuenta.
        "limite_caracteres": formato.limite_caracteres,
        "requisitos_detectados": guard.lista_texto(
            bruto.get("requisitos_detectados"), 10, 220
        ),
        "puntos_usados": guard.lista_texto(bruto.get("puntos_usados"), 12, 240),
        "no_cumples": _no_cumples(bruto.get("no_cumples")),
        "que_debes_completar": pendientes[:15],
        "disclaimer": DISCLAIMER,
    }


def redactar(
    *,
    vacante: str,
    perfil: str,
    formato: str = FORMATO_POR_DEFECTO,
    notas: Optional[str] = None,
    session_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Escribe el copy. Devuelve ``(pitch, metadata_de_ia)``.

    ``perfil`` llega ya serializado (ver :func:`describir_perfil`): este módulo
    no toca la base de datos, igual que `cv_target_service` y
    `career_gap_service`.
    """
    vacante = (vacante or "").strip()
    if len(vacante) < MIN_VACANTE:
        raise JobPitchError(
            "Pega un poco más del aviso de la vacante: con tan poco texto no "
            "puedo saber qué están buscando."
        )
    vacante = vacante[:MAX_VACANTE]
    fmt = obtener_formato(formato)

    from app.core.ai_client import call_claude_tool, load_prompt

    prompt = load_prompt("job_pitch").format(
        formato_instruccion=fmt.instruccion,
        vacante=vacante,
        perfil=perfil,
        notas=(notas or "").strip()[:MAX_NOTAS]
        or "(no escribió nada · no lo inventes)",
    )

    datos, meta = call_claude_tool(
        prompt,
        tool_name="escribir_postulacion",
        tool_description=(
            "Escribe el texto con el que una persona se postula a una vacante, "
            "usando sólo su experiencia real y dejando aparte lo que no cumple."
        ),
        input_schema=ESQUEMA_PITCH,
        session_id=session_id,
        feature="job_pitch",
        max_tokens=2500,
        # Algo de variación ayuda a que no suene a plantilla, pero menos que en
        # el ensayo: aquí manda la precisión sobre los requisitos.
        temperature=0.4,
    )

    if not datos:
        raise JobPitchError(
            "No pude escribir tu postulación en este momento. Intenta de nuevo."
        )

    resultado = normalizar(datos, formato=fmt)
    if not resultado["parrafos"]:
        raise JobPitchError(
            "No pude escribir tu postulación en este momento. Intenta de nuevo."
        )
    return resultado, meta
