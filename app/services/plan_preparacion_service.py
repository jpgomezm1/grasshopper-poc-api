"""El plan de preparación de 11° y 12° · E (entregable de 11°), Sprint 4.

El demo de Verónica pide para 11° un "plan de preparación 11–12": qué hacer y
cuándo para llegar a aplicar. Aquí se arma, sin IA, con lo que ya sabemos de
la persona: su grado, hasta qué grado llega su colegio, si se ve estudiando
afuera (y dónde), su inglés, sus tests y sus rutas.

## Fechas relativas, nunca oficiales

Las etapas van contra SU graduación ("ahora", "en 12°", "antes de aplicar"),
no contra un calendario. Las fechas de los exámenes y de cada universidad no
son nuestras y cambian cada año; publicarlas sería el mismo error que el
banco de práctica evita al no dar escalas oficiales (`exam_prep.py`). El plan
lo dice al final: confirmar siempre en la fuente oficial.

## Una sola fuente

El plan se calcula aquí y el front solo lo pinta. Los candados salen de
`permisos_service`, la misma matriz que usa el resto de la plataforma: si cada
pantalla decidiera por su cuenta qué está con candado, es el P0-8 de este repo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.data.onboarding_hechos import RUTA_GRADO_11, RUTA_GRADO_12

INTL_SI = "intl_yes"
INTL_QUIZAS = "intl_maybe"
INTL_NO = "intl_no"

AVISO = (
    "Orientativo: las fechas y los requisitos los pone cada universidad y cada "
    "examinador. Confírmalos siempre en la fuente oficial."
)


def _paso(
    id: str,
    titulo: str,
    *,
    detalle: Optional[str] = None,
    hecho: bool = False,
    ruta: Optional[str] = None,
    cta: Optional[str] = None,
    funcion: Optional[str] = None,
    con_candado: bool = False,
) -> Dict[str, Any]:
    return {
        "id": id,
        "titulo": titulo,
        "detalle": detalle,
        "hecho": hecho,
        "ruta": ruta,
        "cta": cta,
        # La función del plan que abre el paso · el muro de pago dice cuál falta.
        "funcion": funcion,
        "con_candado": con_candado,
    }


def _rutas_activas(db: Any, user: Any) -> int:
    from app.db.models import Route, RouteStatus
    from app.db.models import Session as JourneySession

    return (
        db.query(Route)
        .join(JourneySession, Route.session_id == JourneySession.id)
        .filter(JourneySession.user_id == user.id, Route.status == RouteStatus.ACTIVE)
        .count()
    )


def _ultimo_grado_del_colegio(user: Any) -> Optional[int]:
    valor = getattr(user, "school_reported_last_grade", None)
    if valor is None:
        valor = (user.onboarding_answers or {}).get("school_reported_last_grade")
    try:
        return int(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None  # "unknown" ("No sé")


def armar(db: Any, user: Any) -> Dict[str, Any]:
    from app.data import permisos as matriz
    from app.db.models import VocationalTestResult
    from app.services import permisos_service

    p = permisos_service.permisos(db, user)
    respuestas = user.onboarding_answers or {}
    interes = respuestas.get("international_interest")
    paises = respuestas.get("countries") or []
    if not isinstance(paises, list):
        paises = [paises]

    afuera = interes in (INTL_SI, INTL_QUIZAS) or interes is None
    # "Quizás" y "no lo ha dicho" ven los pasos de afuera, pero condicionados:
    # quitárselos sería decidir por la persona; dárselos como obligatorios,
    # también.
    si_decides = "" if interes == INTL_SI else "Si decides estudiar afuera: "

    def candado(funcion: str) -> bool:
        acceso = p.funciones.get(funcion)
        return bool(acceso and acceso.motivo == "plan")

    # ¿Le queda un año más de colegio? Solo si va en 11° y su colegio llega a
    # 12°. Con "No sé" se asume que este es su último año: llegar antes a las
    # aplicaciones no hace daño; llegar tarde, sí.
    queda_12 = p.tramo == RUTA_GRADO_11 and _ultimo_grado_del_colegio(user) == 12
    if p.tramo == RUTA_GRADO_12 or (p.tramo == RUTA_GRADO_11 and not queda_12):
        encabezado = "Este es tu último año de colegio"
    elif queda_12:
        encabezado = "Te quedan 11° y 12°"
    else:
        encabezado = None

    # --- Ahora ---------------------------------------------------------------
    de_su_grado = matriz.TESTS_POR_TRAMO.get(p.tramo, ()) if p.tramo else ()
    hechos = {
        r.test_id
        for r in db.query(VocationalTestResult.test_id)
        .filter(VocationalTestResult.user_id == user.id)
        .all()
    }
    ahora: List[Dict[str, Any]] = []
    if de_su_grado:
        listos = len([t for t in de_su_grado if t in hechos])
        ahora.append(_paso(
            "tests", "Haz los tests de tu grado",
            detalle=f"{listos} de {len(de_su_grado)}",
            hecho=listos == len(de_su_grado),
            ruta="/tests", cta="Ir a los tests",
            funcion="tests", con_candado=candado("tests"),
        ))
    ahora.append(_paso(
        "ingles", "Mide tu nivel de inglés",
        detalle=(
            f"Tu nivel: {user.english_cefr_level}" if user.english_test_completed
            and user.english_cefr_level else None
        ),
        hecho=bool(user.english_test_completed),
        ruta="/english-test", cta="Hacer el test",
        funcion="ingles", con_candado=p.ingles.motivo == "plan",
    ))
    if interes is None:
        ahora.append(_paso(
            "decidir_donde", "Piensa si te ves estudiando en Colombia, afuera o en los dos",
            detalle="Cambia qué te toca preparar. Puedes contárselo a Hopper.",
        ))
    # E-3 · lo que hace viable (o no) cada opción. Va antes de elegir rutas.
    from app.services import estilo_de_vida_service as estilo

    ahora.append(_paso(
        "estilo_de_vida", "Cuéntanos tu estilo de vida y tu presupuesto",
        detalle="Respóndelo con tu familia: así te mostramos opciones que sí sean posibles.",
        hecho=estilo.respondido(respuestas),
        ruta="/estilo-de-vida", cta="Responder",
        funcion="estilo_de_vida", con_candado=candado("estilo_de_vida"),
    ))
    ahora.append(_paso(
        "rutas", "Elige 2 o 3 rutas que te convenzan",
        hecho=_rutas_activas(db, user) >= 2,
        ruta="/routes", cta="Ver mis rutas",
    ))

    # --- Después (este año o 12°) ---------------------------------------------
    despues: List[Dict[str, Any]] = [_paso(
        "programas", "Arma tu lista de programas",
        detalle="Con tus rutas en la mano, elige los programas concretos que te interesan.",
        ruta="/programas", cta="Ver programas",
        funcion="programas", con_candado=candado("programas"),
    )]
    if interes != INTL_SI:
        despues.append(_paso(
            "saber_11", "Prepárate para el Saber 11",
            detalle=(
                "Lo presentas en tu último año de colegio y muchas universidades "
                "del país lo piden para admitirte."
            ),
            # I-5 · ya existe la práctica: el paso lleva a ella.
            ruta="/practica-examenes/saber11", cta="Ir a la práctica",
            funcion="practica_examenes", con_candado=candado("practica_examenes"),
        ))
    if afuera:
        despues.append(_paso(
            "practica_ingles", "Practica para el examen de inglés (IELTS o TOEFL)",
            detalle=si_decides + "casi siempre te pedirán demostrar tu nivel de inglés.",
            ruta="/practica-examenes/ielts", cta="Ir a la práctica",
            funcion="practica_examenes", con_candado=candado("practica_examenes"),
        ))
        if "usa" in paises:
            despues.append(_paso(
                "practica_sat", "Practica para el SAT",
                detalle="Porque te interesa Estados Unidos, donde muchas universidades lo piden.",
                ruta="/practica-examenes/sat", cta="Ir a la práctica",
                funcion="practica_examenes", con_candado=candado("practica_examenes"),
            ))
        despues.append(_paso(
            "examen_oficial", "Presenta el examen oficial con tiempo para repetirlo",
            detalle=si_decides + "si el puntaje no te alcanza, así tienes margen.",
        ))
        despues.append(_paso(
            "cartas", "Pide tus cartas de recomendación con unos 2 meses de anticipación",
            detalle="A profesores que te conozcan bien.",
        ))

    # --- Antes de aplicar -----------------------------------------------------
    antes: List[Dict[str, Any]] = []
    if afuera:
        antes.append(_paso(
            "carta_motivacion", "Escribe tu carta de motivación",
            detalle=si_decides + "la mayoría de universidades afuera la piden.",
            ruta="/me/tools/sop", cta="Carta de motivación",
            funcion="carta_motivacion", con_candado=candado("carta_motivacion"),
        ))
    # E-4 · el kit de aplicación es donde se hace este paso: una lista por
    # universidad, con la fecha límite que le dieron y avisos cuando se acerca.
    antes.append(_paso(
        "requisitos", "Revisa requisitos y fechas de inscripción con cada universidad",
        detalle="Arma el kit de cada universidad y te avisamos cuando se acerque su fecha.",
        ruta="/aplicaciones", cta="Abrir mi kit",
        funcion="kit_aplicacion", con_candado=candado("kit_aplicacion"),
    ))
    # E-4 · muchas universidades entrevistan, afuera y en el país.
    antes.append(_paso(
        "entrevista", "Practica tu entrevista de admisión",
        detalle="Hopper te hace las preguntas típicas y te dice qué funcionó y qué mejorar.",
        ruta="/entrevista", cta="Practicar",
        funcion="entrevista_admision", con_candado=candado("entrevista_admision"),
    ))
    # E-3 · si depende de una beca o un crédito, se lo dice (lo respondió en
    # el cuestionario de estilo de vida); si no, el paso genérico.
    depende = respuestas.get("financiacion") in ("beca", "credito", "mezcla")
    antes.append(_paso(
        "financiacion", "Becas y financiación: háblalo con tu familia y tu asesor",
        detalle=(
            "Como cuentas con una beca o un crédito, búscalos con tiempo: suelen "
            "cerrar antes que las admisiones." if depende else None
        ),
    ))

    etapas = [
        {"id": "ahora", "titulo": "Ahora", "pasos": ahora},
        {
            "id": "despues",
            "titulo": "En 12°" if queda_12 else "En los próximos meses",
            "pasos": despues,
        },
        {"id": "antes_de_aplicar", "titulo": "Antes de aplicar", "pasos": antes},
    ]
    return {"encabezado": encabezado, "etapas": etapas, "aviso": AVISO}
