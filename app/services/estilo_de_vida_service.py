"""El cuestionario de estilo de vida y presupuesto · E-3 (11°), Sprint 4.

El demo de Verónica pide para 11° un "cuestionario de estilo de vida y
presupuesto: estudiar fuera, finanzas familiares y becas", para cruzar los
deseos con la realidad.

## Quién responde la plata

JP decidió el 2026-10-31 que lo responde **el estudiante con su familia** (la
pantalla lo dice). Revierte, solo para este cuestionario, la regla del
2026-08-09 de no preguntarle el presupuesto a un estudiante de colegio ("él no
sabe, pagan los papás"), que sigue vigente en el onboarding conversacional
(`SOLO_PERFIL` en `onboarding_hechos.py`). Por eso aquí la opción "todavía no
lo hemos hablado" está a la par de las demás: no saber es una respuesta válida.

## Dónde se guarda, y lo que a propósito NO toca

En `onboarding_answers`, que es lo que leen los prompts
(`ai_service.format_onboarding_context`, y con él las rutas, el perfil
consolidado y el chat de Hopper). El destino y los países reutilizan las
claves del onboarding (`international_interest`, `countries`): las leen ya el
plan de preparación, la práctica de exámenes y el recomendador.

El presupuesto va en una clave PROPIA (`presupuesto_familiar`) y no en
`budget`: `budget` se copia a `user.budget_band`, y esa columna se sincroniza
con Bitrix, el CRM del cliente (`auth._sync_onboarding_to_user_columns`). Mandar al CRM
lo que una familia dijo que puede pagar es una decisión comercial y de datos
personales que no se toma de rebote.

## Sin IA, a propósito

Las preguntas son fijas y la lectura del final es determinista: no inventa
costos de ningún país. La IA usa estas respuestas después, donde ya estaba
(rutas, Hopper), para no proponer lo que no es viable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

INTL_NO = "intl_no"


def _opciones_de_hecho(hecho_id: str) -> Dict[str, str]:
    """Las opciones de un hecho del onboarding · una sola fuente, no se copian."""
    from app.data.onboarding_hechos import HECHOS

    return dict(next(h for h in HECHOS if h.id == hecho_id).opciones)


def preguntas_base() -> List[Dict[str, Any]]:
    return [
        {
            "id": "international_interest",
            "pregunta": "¿Dónde te ves estudiando?",
            "tipo": "opcion",
            "opciones": _opciones_de_hecho("international_interest"),
        },
        {
            "id": "countries",
            "pregunta": "¿Qué países te atraen?",
            "tipo": "multi",
            "opciones": _opciones_de_hecho("countries"),
            # No se le pregunta a quien solo se ve en Colombia (mismo criterio
            # que `onboarding_hechos.aplica()`).
            "solo_si_no": {"international_interest": INTL_NO},
        },
        {
            "id": "estilo_vivienda",
            "pregunta": "¿Cómo te imaginas viviendo mientras estudias?",
            "tipo": "opcion",
            "opciones": {
                "con_familia": "Con mi familia",
                "independiente": "Por mi cuenta o con compañeros",
                "residencia": "En una residencia universitaria",
                "no_se": "Todavía no lo sé",
            },
        },
        {
            "id": "estilo_ciudad",
            "pregunta": "¿En qué tipo de ciudad te gustaría estudiar?",
            "tipo": "opcion",
            "opciones": {
                "grande": "Una ciudad grande",
                "mediana": "Una ciudad intermedia",
                "pequena": "Un lugar pequeño y tranquilo",
                "igual": "Me da igual",
            },
        },
        {
            "id": "presupuesto_familiar",
            "pregunta": "Con tu familia: ¿cuánto podrían invertir al año en tus estudios (matrícula y vida)?",
            "tipo": "opcion",
            "opciones": {
                "hasta_10k": "Hasta USD 10.000 al año",
                "10k_25k": "Entre USD 10.000 y 25.000 al año",
                "mas_25k": "Más de USD 25.000 al año",
                "no_hablado": "Todavía no lo hemos hablado",
            },
        },
        {
            "id": "financiacion",
            "pregunta": "¿Cómo lo financiarían?",
            "tipo": "opcion",
            "opciones": {
                "familia": "Con recursos de la familia",
                "beca": "Dependo de una beca",
                "credito": "Con un crédito educativo",
                "mezcla": "Una mezcla de las anteriores",
                "no_hablado": "Todavía no lo hemos hablado",
            },
        },
        {
            "id": "trabajar_estudiando",
            "pregunta": "¿Piensas trabajar mientras estudias?",
            "tipo": "opcion",
            "opciones": {
                "si": "Sí",
                "tal_vez": "Tal vez",
                "no": "No",
            },
        },
    ]


CLAVES = tuple(p["id"] for p in preguntas_base())
# Las que hacen falta para darlo por respondido (los países dependen del destino).
OBLIGATORIAS = tuple(c for c in CLAVES if c != "countries")


def _aplica(pregunta: Dict[str, Any], respuestas: Dict[str, Any]) -> bool:
    for clave, valor in (pregunta.get("solo_si_no") or {}).items():
        if respuestas.get(clave) == valor:
            return False
    return True


def respondido(respuestas: Dict[str, Any]) -> bool:
    return all(respuestas.get(c) for c in OBLIGATORIAS)


def validar(nuevas: Dict[str, Any]) -> Dict[str, Any]:
    """Solo claves conocidas y valores de sus opciones · ValueError si no."""
    limpias: Dict[str, Any] = {}
    por_id = {p["id"]: p for p in preguntas_base()}
    for clave, valor in nuevas.items():
        p = por_id.get(clave)
        if p is None:
            raise ValueError(f"Pregunta desconocida: {clave}")
        if p["tipo"] == "multi":
            if not isinstance(valor, list) or any(v not in p["opciones"] for v in valor):
                raise ValueError(f"Respuesta no válida para {clave}")
            limpias[clave] = list(dict.fromkeys(valor))
        else:
            if valor not in p["opciones"]:
                raise ValueError(f"Respuesta no válida para {clave}")
            limpias[clave] = valor
    if limpias.get("international_interest") == INTL_NO:
        # Quien solo se ve en Colombia no tiene países de afuera.
        limpias["countries"] = []
    return limpias


def lectura(r: Dict[str, Any]) -> List[str]:
    """Lo que esto cambia para la persona · sin cifras de costos inventadas."""
    if not respondido(r):
        return []
    afuera = r.get("international_interest") in ("intl_yes", "intl_maybe")
    fuera: List[str] = []
    if r.get("presupuesto_familiar") == "no_hablado" or r.get("financiacion") == "no_hablado":
        fuera.append(
            "Hablen en familia de cuánto podrían invertir y cómo: cambia qué opciones "
            "te conviene mirar. Si quieres, tu asesor puede acompañar esa conversación."
        )
    if r.get("financiacion") in ("beca", "credito", "mezcla"):
        fuera.append(
            "Como cuentas con una beca o un crédito, empieza a buscarlos con tiempo: "
            "cada uno tiene sus requisitos y sus fechas, y suelen cerrar antes que las "
            "admisiones."
        )
    if afuera and r.get("presupuesto_familiar") == "hasta_10k":
        fuera.append(
            "Para estudiar afuera con ese presupuesto, revisa con tu asesor qué destinos "
            "y programas te calzan: los costos cambian mucho de un país a otro y de una "
            "universidad pública a una privada."
        )
    if afuera and r.get("trabajar_estudiando") in ("si", "tal_vez"):
        fuera.append(
            "Si piensas trabajar mientras estudias afuera, confirma las reglas del país: "
            "la visa de estudiante no siempre lo permite, o pone límites de horas."
        )
    fuera.append(
        "Hopper y tus rutas van a tener esto en cuenta para mostrarte opciones que sí "
        "sean posibles para ti. Puedes cambiar tus respuestas cuando quieras."
    )
    return fuera


def estado(user: Any) -> Dict[str, Any]:
    respuestas = user.onboarding_answers or {}
    actuales = {c: respuestas.get(c) for c in CLAVES if respuestas.get(c) not in (None, "", [])}
    return {
        "preguntas": [
            {**p, "aplica": _aplica(p, actuales)} for p in preguntas_base()
        ],
        "respuestas": actuales,
        "respondido": respondido(actuales),
        "lectura": lectura(actuales),
    }


def guardar(db: Any, user: Any, nuevas: Dict[str, Any]) -> Dict[str, Any]:
    from sqlalchemy.orm.attributes import flag_modified

    limpias = validar(nuevas)
    # Dict nuevo: la columna JSON no rastrea mutaciones in-place.
    respuestas = dict(user.onboarding_answers or {})
    respuestas.update(limpias)
    user.onboarding_answers = respuestas
    flag_modified(user, "onboarding_answers")
    db.commit()
    db.refresh(user)
    return estado(user)


ETIQUETAS_PROMPT = {
    "estilo_vivienda": "Cómo se imagina viviendo mientras estudia",
    "estilo_ciudad": "Tipo de ciudad donde le gustaría estudiar",
    "presupuesto_familiar": "Presupuesto anual que la familia podría invertir (lo respondió con su familia)",
    "financiacion": "Cómo lo financiarían",
    "trabajar_estudiando": "Si piensa trabajar mientras estudia",
}


def lineas_para_prompt(respuestas: Dict[str, Any]) -> List[str]:
    """Las respuestas en palabras, para `ai_service.format_onboarding_context`."""
    por_id = {p["id"]: p for p in preguntas_base()}
    lineas = []
    for clave, etiqueta in ETIQUETAS_PROMPT.items():
        valor: Optional[str] = respuestas.get(clave)
        texto = por_id[clave]["opciones"].get(valor) if valor else None
        if texto:
            lineas.append(f"- {etiqueta}: {texto}")
    return lineas
