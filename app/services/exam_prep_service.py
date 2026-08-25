"""Práctica para exámenes de admisión · a quién se le ofrece y en qué nivel arranca.

El banco de ejercicios y sus avisos legales viven en `app/data/exam_prep.py`.
Aquí está todo lo que depende de QUIÉN es el estudiante: a quién tiene sentido
ofrecérselo, en qué nivel empieza y cómo se lee una sesión resuelta. Es el mismo
reparto que ya usa la pareja `data/habilidades_blandas.py` +
`services/habilidades_blandas_service.py`.

## Tres decisiones que no son obvias

### 1. Se conecta con el diagnóstico de inglés que YA existe · no se duplica

El repo ya mide inglés con el examen de ubicación de AMES (60 ítems,
`app/data/english_test_questions.py`, resultado persistido en
`EnglishTestResult` y en `user.english_cefr_level`). Construir aquí un segundo
diagnóstico habría sido pedirle a la misma persona que demuestre lo mismo dos
veces — la queja de fatiga de cuestionarios que la clienta ya hizo.

Entonces: **si ya sabemos su nivel, la práctica arranca ahí**. El CEFR que la
app ya usa para todo lo demás decide el nivel de los ejercicios de lengua. Si el
estudiante todavía no hizo el diagnóstico, no se le inventa un nivel: la sesión
sale con niveles mezclados y se le dice que hacer el diagnóstico la afina.

La equivalencia IELTS aproximada sólo se muestra cuando el resultado es del
examen de 60 preguntas, con la misma salvedad (y por la misma razón) que
documenta `app/api/v1/english_test.py`: un 15/20 del banco viejo leído contra la
tabla de 60 diría un nivel que no es.

### 2. El nivel de MATEMÁTICAS no sale del inglés

Sería trivial usar el CEFR para graduar también los ejercicios de álgebra, y
sería inventarse una relación que nadie midió. No hay diagnóstico de matemáticas
en el repo, así que esas habilidades salen con niveles mezclados y el `porque`
lo dice. Preferimos decir "no lo sabemos" a fabricar un dato.

### 3. Se RECOMIENDA, no se bloquea

La regla de producto es "SAT a grado 11 y 12; IELTS a quien declaró interés
internacional o lo necesita por nivel de inglés". Eso se implementa como
recomendación (`recomendado` + `motivo`), no como llave: el material sigue
accesible para quien entre por su cuenta.

Es la misma decisión que ya tomó el repo en `vocational_tests.submit_test`
—*"MEMORIA SÍ, LLAVE NO"*— y evita el absurdo de que un chico de 10° con
curiosidad reciba un 404. La única señal fuerte es el `intl_no`: a quien dijo
explícitamente que quiere quedarse en Colombia no se le empuja práctica de
IELTS, con el mismo criterio con el que `onboarding_hechos.aplica()` deja de
preguntarle por el pasaporte.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.data import exam_prep as banco
from app.data.english_test_questions import ENGLISH_TEST_QUESTIONS, placement_for
from app.data.exam_prep import (
    EXAMEN_IELTS,
    EXAMEN_SAT,
    NIVEL_AVANZADO,
    NIVEL_FUNDAMENTOS,
    NIVEL_INTERMEDIO,
    NIVELES,
)
from app.data.onboarding_hechos import (
    RUTA_GRADO_11,
    RUTA_GRADO_12,
    RUTA_POR_GRADO,
    RUTA_PROFESIONAL,
    perfil,
    PERFIL_PROFESIONAL,
)
from app.services import vocational_bank_selector

# Los grados a los que el SAT le cae en el momento útil · se derivan de la tabla
# canónica de las 5 rutas de la malla (`RUTA_POR_GRADO`) y NO de una tupla
# propia, por el mismo motivo por el que `vocational_bank_selector.GRADOS_JUNIOR`
# se deriva de ahí: dos sitios decidiendo lo mismo es el error que este repo ya
# se cobró cuatro veces.
GRADOS_SAT = tuple(
    sorted(
        int(grado)
        for grado, ruta in RUTA_POR_GRADO.items()
        if ruta in (RUTA_GRADO_11, RUTA_GRADO_12)
    )
)

# Traducción CEFR → nivel de nuestros ejercicios. Las franjas que produce la
# tabla de AMES son A2, B1 y B2; las otras están para resultados guardados con
# el banco viejo (que sí emitía C1) y para no reventar si alguna vez cambia.
NIVEL_POR_CEFR: Dict[str, str] = {
    "A1": NIVEL_FUNDAMENTOS,
    "A2": NIVEL_FUNDAMENTOS,
    "B1": NIVEL_INTERMEDIO,
    "B2": NIVEL_AVANZADO,
    "C1": NIVEL_AVANZADO,
    "C2": NIVEL_AVANZADO,
}

# Por debajo de estas franjas se considera que hay margen de refuerzo antes de
# presentar un examen internacional. Es NUESTRO criterio para decidir a quién le
# ofrecemos práctica, no un requisito de admisión de nadie: los puntajes que pide
# cada programa los define cada institución y aquí no se afirman.
CEFR_CON_MARGEN_DE_REFUERZO = ("A1", "A2", "B1")

# Códigos del hecho `international_interest` (ver `onboarding_hechos`).
INTL_SI = "intl_yes"
INTL_QUIZAS = "intl_maybe"
INTL_NO = "intl_no"

# Dónde está el diagnóstico que NO se duplica. Se manda al front para que el
# botón lleve al sitio correcto sin que nadie tenga que acordarse de la ruta.
ENDPOINT_DIAGNOSTICO_INGLES = "/api/v1/english-test/questions"

MAX_EJERCICIOS_POR_SESION = 30


# ---------------------------------------------------------------------------
# El diagnóstico de inglés que ya existe
# ---------------------------------------------------------------------------

def _respuestas_onboarding(user: Any) -> Dict[str, Any]:
    respuestas = getattr(user, "onboarding_answers", None) or {}
    return respuestas if isinstance(respuestas, dict) else {}


def _cefr(user: Any) -> Optional[str]:
    """El CEFR que la app ya usa para este estudiante, normalizado."""
    valor = getattr(user, "english_cefr_level", None)
    if not isinstance(valor, str) or not valor.strip():
        return None
    return valor.strip().upper()


def diagnostico_de_ingles(db: Any, user: Any) -> Dict[str, Any]:
    """Qué sabemos hoy del inglés de este estudiante, y qué implica para la práctica.

    No mide nada nuevo: lee lo que dejó el examen de ubicación de AMES.
    """
    cefr = _cefr(user)
    nivel = NIVEL_POR_CEFR.get(cefr or "")

    info: Dict[str, Any] = {
        "completed": bool(getattr(user, "english_test_completed", False)) or cefr is not None,
        "cefrLevel": cefr,
        "practiceLevel": nivel,
        "instrument": None,
        "ieltsEquivalent": None,
        "classPlacement": None,
        "endpoint": ENDPOINT_DIAGNOSTICO_INGLES,
    }

    resultado = _resultado_de_ingles(db, user)
    if resultado is not None:
        info["completed"] = True
        # Misma salvedad que `english_test.get_result`: la tabla de equivalencia
        # sólo aplica al examen de 60. Un resultado del banco viejo de 20
        # preguntas leído contra ella daría una equivalencia falsa.
        if resultado.total_questions == len(ENGLISH_TEST_QUESTIONS):
            ubicacion = placement_for(resultado.score)
            info["instrument"] = "AMES English Placement Test"
            info["ieltsEquivalent"] = ubicacion["ielts_equivalent"]
            info["classPlacement"] = ubicacion["class_placement"]

    if info["completed"] and nivel:
        info["message"] = (
            f"Ya hiciste el diagnóstico de inglés y quedaste en {cefr}, así que "
            f"la práctica de lengua arranca en nivel {nivel} en vez de empezar "
            "desde cero."
        )
    elif info["completed"]:
        info["message"] = (
            "Hiciste el diagnóstico de inglés, pero no tenemos un nivel que "
            "podamos traducir a la práctica, así que los ejercicios salen con "
            "niveles mezclados."
        )
    else:
        info["message"] = (
            "Todavía no has hecho el diagnóstico de inglés. Si lo haces, la "
            "práctica arranca en tu nivel en vez de mezclar dificultades."
        )
    return info


def _resultado_de_ingles(db: Any, user: Any):
    """La fila de `EnglishTestResult` del estudiante, o None.

    Tolera `db=None` (hay llamadas donde sólo interesa el CEFR ya persistido) y
    cualquier fallo de consulta: la práctica nunca debe caerse porque el
    diagnóstico no se pueda leer.
    """
    if db is None:
        return None
    try:
        from app.db.models import EnglishTestResult

        return (
            db.query(EnglishTestResult)
            .filter(EnglishTestResult.user_id == user.id)
            .first()
        )
    except Exception:  # pragma: no cover · degradar, nunca romper la práctica
        return None


# ---------------------------------------------------------------------------
# A quién se le ofrece cada examen
# ---------------------------------------------------------------------------

def ruta_del_estudiante(user: Any) -> Optional[str]:
    """Cuál de las 5 rutas de la malla le corresponde, o None si no se sabe.

    Se apoya en las dos piezas que ya existen: `perfil()` (colegio o
    profesional, derivado de `life_stage`) y el resolvedor de grado de
    `vocational_bank_selector`, que además de la columna `user.grade` sabe leer
    el espejo en JSON y el grado escrito con palabras.
    """
    respuestas = _respuestas_onboarding(user)
    if perfil(respuestas) == PERFIL_PROFESIONAL:
        return RUTA_PROFESIONAL
    grado = vocational_bank_selector.grado_del_estudiante(user)
    if grado is None:
        return None
    return RUTA_POR_GRADO.get(str(grado))


def _recomendacion_sat(user: Any) -> Dict[str, Any]:
    grado = vocational_bank_selector.grado_del_estudiante(user)
    if grado in GRADOS_SAT:
        return {
            "recommended": True,
            "reasonCode": "grade",
            "reason": (
                f"Vas en {grado}°, que es cuando esta preparación cae en el "
                "momento útil."
            ),
        }
    if ruta_del_estudiante(user) == RUTA_PROFESIONAL:
        return {
            "recommended": False,
            "reasonCode": "professional_track",
            "reason": (
                "El SAT se usa sobre todo en admisiones de pregrado. Si estás "
                "mirando un posgrado, un curso corto o un cambio de carrera, "
                "esto probablemente no es tu prioridad — pero puedes practicar "
                "si quieres."
            ),
        }
    if grado is None:
        return {
            "recommended": False,
            "reasonCode": "grade_unknown",
            "reason": (
                "Todavía no sabemos en qué grado vas. Cuéntanoslo y te decimos "
                "si esta preparación te sirve ahora o más adelante."
            ),
        }
    return {
        "recommended": False,
        "reasonCode": "grade_too_early",
        "reason": (
            f"Vas en {grado}° y esta preparación se aprovecha mejor en "
            f"{GRADOS_SAT[0]}° y {GRADOS_SAT[-1]}°. Puedes mirarla, sin afán."
        ),
    }


def _recomendacion_ielts(user: Any, diagnostico: Dict[str, Any]) -> Dict[str, Any]:
    interes = _respuestas_onboarding(user).get("international_interest")
    cefr = diagnostico.get("cefrLevel")
    con_margen = cefr in CEFR_CON_MARGEN_DE_REFUERZO

    # El "no" explícito manda. Mismo criterio que `onboarding_hechos.aplica()`,
    # que deja de preguntar por países y pasaporte a quien dijo intl_no.
    if interes == INTL_NO:
        return {
            "recommended": False,
            "reasonCode": "not_international",
            "reason": (
                "Nos dijiste que te ves estudiando en Colombia, así que no te "
                "insistimos con esto. Si cambias de idea, aquí está."
            ),
        }

    if interes in (INTL_SI, INTL_QUIZAS):
        return {
            "recommended": True,
            "reasonCode": "international_interest",
            "reason": (
                "Nos dijiste que te interesa estudiar fuera del país, y en ese "
                "camino casi siempre hay que demostrar el nivel de inglés."
            ),
        }

    if con_margen:
        clase = diagnostico.get("classPlacement")
        ubicacion = f" ({clase})" if clase else ""
        return {
            "recommended": True,
            "reasonCode": "english_level",
            "reason": (
                f"Tu diagnóstico de inglés te ubicó en {cefr}{ubicacion}. Si en "
                "algún momento presentas un examen internacional, practicar "
                "desde ahora te deja llegar más preparado."
            ),
        }

    return {
        "recommended": False,
        "reasonCode": "not_yet",
        "reason": (
            "Todavía no nos has dicho si te interesa estudiar fuera del país. "
            "Cuéntanoslo y te decimos si esta práctica te sirve."
        ),
    }


def recomendacion(
    db: Any,
    user: Any,
    exam_id: str,
    *,
    diagnostico: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """¿Le tiene sentido este examen a este estudiante, y por qué?

    Nunca bloquea: devuelve una recomendación con su motivo. Ver decisión 3 del
    docstring del módulo.

    `diagnostico` se puede pasar ya calculado para no repetir la consulta cuando
    quien llama va a resolver los dos exámenes seguidos (`catalogo`).
    """
    if exam_id == EXAMEN_SAT:
        # El SAT se decide sólo por el grado · no se toca la base por gusto.
        return _recomendacion_sat(user)
    if exam_id == EXAMEN_IELTS:
        if diagnostico is None:
            diagnostico = diagnostico_de_ingles(db, user)
        return _recomendacion_ielts(user, diagnostico)
    raise ValueError(f"examen desconocido: {exam_id!r}")


# ---------------------------------------------------------------------------
# Armar una sesión de práctica
# ---------------------------------------------------------------------------

def _nivel_para(habilidad: Dict[str, Any], diagnostico: Dict[str, Any]) -> Dict[str, Any]:
    """Nivel de arranque de una habilidad + el porqué, en lenguaje del estudiante."""
    if not habilidad["dependsOnEnglish"]:
        return {
            "level": None,
            "why": (
                "Esta parte no depende de tu inglés y no tenemos un diagnóstico "
                "de matemáticas, así que los ejercicios salen con dificultades "
                "mezcladas."
            ),
        }
    nivel = diagnostico.get("practiceLevel")
    if nivel:
        return {
            "level": nivel,
            "why": (
                f"Arranca en nivel {nivel} porque tu diagnóstico de inglés te "
                f"ubicó en {diagnostico.get('cefrLevel')}."
            ),
        }
    return {
        "level": None,
        "why": (
            "Salen con dificultades mezcladas porque todavía no hiciste el "
            "diagnóstico de inglés. Hacerlo afina la práctica."
        ),
    }


def _ordenar_pool(items: List[Dict[str, Any]], nivel: Optional[str]) -> List[Dict[str, Any]]:
    """Los ejercicios ordenados por cercanía al nivel objetivo.

    Con nivel objetivo: primero ese nivel, después el vecino más cercano. Con
    nivel desconocido: se alternan los tres niveles (fundamentos, intermedio,
    avanzado, fundamentos…) para que una sesión mezclada no sean diez ejercicios
    fáciles seguidos.

    En los dos casos el orden es determinista: dos estudiantes con el mismo
    perfil ven la misma sesión y los tests no dependen de un `random`.
    """
    if nivel:
        objetivo = NIVELES.index(nivel)
        # `orden` desempata por la posición original en el banco · sin él, el
        # resultado dependería de la estabilidad de `sorted` sobre dicts y sería
        # más difícil de razonar en un test.
        return [
            items[orden]
            for _, orden in sorted(
                (abs(NIVELES.index(i["level"]) - objetivo), n)
                for n, i in enumerate(items)
            )
        ]

    por_nivel: Dict[str, List[Dict[str, Any]]] = {n: [] for n in NIVELES}
    for i in items:
        por_nivel[i["level"]].append(i)
    mezclado: List[Dict[str, Any]] = []
    while any(por_nivel.values()):
        for n in NIVELES:
            if por_nivel[n]:
                mezclado.append(por_nivel[n].pop(0))
    return mezclado


def sesion(
    db: Any,
    user: Any,
    exam_id: str,
    *,
    skill_id: Optional[str] = None,
    limite: int = banco.TAMANO_SESION,
    ronda: int = 1,
) -> Dict[str, Any]:
    """Una tanda de ejercicios para este estudiante, sin las respuestas.

    NO se persiste nada. Es deliberado y tiene dos motivos: esta tarea no puede
    crear migraciones, y —más de fondo— hoy nadie leería un puntaje de práctica
    guardado. Un campo que nadie lee es el defecto que este repo documenta como
    el más repetido; cuando alguien necesite el histórico (el asesor, el PDF),
    se agrega la tabla y su lector en el mismo cambio.
    """
    examen = banco.get_examen(exam_id)
    if examen is None:
        raise ValueError(f"examen desconocido: {exam_id!r}")

    habilidades = banco.habilidades_de(exam_id)
    if skill_id is not None:
        habilidades = [h for h in habilidades if h["id"] == skill_id]
        if not habilidades:
            raise ValueError(f"habilidad desconocida para {exam_id}: {skill_id!r}")

    limite = max(1, min(int(limite), MAX_EJERCICIOS_POR_SESION))
    ronda = max(1, int(ronda))

    diagnostico = diagnostico_de_ingles(db, user)

    # Un pool ordenado por habilidad · después se intercalan para que una sesión
    # de examen completo no sean seis ejercicios de gramática y ninguno de
    # lectura.
    pools: List[List[Dict[str, Any]]] = []
    niveles_usados: List[Dict[str, Any]] = []
    for h in habilidades:
        decision = _nivel_para(h, diagnostico)
        niveles_usados.append({"skill": h["id"], **decision})
        pool = _ordenar_pool(banco.items(exam_id=exam_id, skill_id=h["id"]), decision["level"])
        # La ronda corre la ventana dentro del pool de ESA habilidad, de forma
        # circular: la ronda 2 empieza donde terminó la 1 y nunca se queda sin
        # ejercicios.
        #
        # El corrimiento se mide en ejercicios POR HABILIDAD, no en el tamaño de
        # la sesión: como después se intercalan las habilidades, de cada una
        # salen ~limite/nº de habilidades por ronda. Correr el pool entero por
        # `limite` haría que la ronda 2 repitiera casi todo (probado: repetía 5
        # de 6).
        if pool:
            por_habilidad = -(-limite // len(habilidades))  # techo de la división
            corrimiento = ((ronda - 1) * por_habilidad) % len(pool)
            pool = pool[corrimiento:] + pool[:corrimiento]
        pools.append(pool)

    seleccion: List[Dict[str, Any]] = []
    vistos = set()
    indice = 0
    while len(seleccion) < limite and any(indice < len(p) for p in pools):
        for pool in pools:
            if len(seleccion) >= limite:
                break
            if indice < len(pool):
                item = pool[indice]
                if item["id"] not in vistos:
                    vistos.add(item["id"])
                    seleccion.append(item)
        indice += 1

    return {
        "exam": exam_id,
        "skill": skill_id,
        "round": ronda,
        "items": [banco.item_publico(i) for i in seleccion],
        "levels": niveles_usados,
        "englishDiagnostic": diagnostico,
        "disclaimer": banco.AVISO_NO_OFICIAL,
        "trademark": banco.MARCAS[exam_id],
    }


# ---------------------------------------------------------------------------
# Leer una tanda resuelta
# ---------------------------------------------------------------------------

def evaluar(exam_id: str, respuestas: Dict[str, Any]) -> Dict[str, Any]:
    """Corrige los ejercicios respondidos y devuelve la explicación de cada uno.

    La explicación viaja SIEMPRE, se haya acertado o no: es lo único que
    convierte esto en práctica en vez de en un marcador.
    """
    examen = banco.get_examen(exam_id)
    if examen is None:
        raise ValueError(f"examen desconocido: {exam_id!r}")

    respuestas = respuestas or {}
    resultados: List[Dict[str, Any]] = []
    por_habilidad: Dict[str, Dict[str, int]] = {}
    # Ids que el cliente mandó y no existen en este examen. Se reportan en vez
    # de ignorarse en silencio: si el front manda mal el id, un contador en cero
    # no dice dónde está el error.
    ignorados: List[str] = []

    for item_id, elegida in respuestas.items():
        item = banco.get_item(str(item_id))
        if item is None or item["exam"] != exam_id:
            ignorados.append(str(item_id))
            continue

        acerto = elegida == item["correct"]
        resumen = por_habilidad.setdefault(
            item["skill"], {"correct": 0, "answered": 0}
        )
        resumen["answered"] += 1
        if acerto:
            resumen["correct"] += 1

        resultados.append(
            {
                "id": item["id"],
                "skill": item["skill"],
                "level": item["level"],
                "yourAnswer": elegida,
                "correctAnswer": item["correct"],
                "isCorrect": acerto,
                "explanation": item["explanation"],
            }
        )

    # Orden estable por el banco, no por el orden en que llegó el JSON.
    orden = {i["id"]: n for n, i in enumerate(banco.EXAM_PREP_ITEMS)}
    resultados.sort(key=lambda r: orden[r["id"]])

    respondidos = len(resultados)
    correctos = sum(1 for r in resultados if r["isCorrect"])

    for resumen in por_habilidad.values():
        resumen["percentage"] = (
            round(resumen["correct"] / resumen["answered"] * 100)
            if resumen["answered"]
            else 0
        )

    return {
        "exam": exam_id,
        "answered": respondidos,
        "correct": correctos,
        # Es el porcentaje de ESTOS ejercicios, y `note` lo dice explícito.
        # Nunca se convierte a una escala del examen ni se llama "puntaje".
        "percentage": round(correctos / respondidos * 100) if respondidos else 0,
        "results": resultados,
        "bySkill": por_habilidad,
        "ignored": ignorados,
        "note": banco.NOTA_DE_RESULTADO,
        "disclaimer": banco.AVISO_NO_OFICIAL,
        "trademark": banco.MARCAS[exam_id],
    }


# ---------------------------------------------------------------------------
# Catálogo para el front
# ---------------------------------------------------------------------------

def catalogo(db: Any, user: Any) -> Dict[str, Any]:
    """Los exámenes disponibles, cada uno con su recomendación para ESTE usuario."""
    diagnostico = diagnostico_de_ingles(db, user)
    examenes = []
    for examen in banco.EXAMENES:
        ficha = {
            k: v
            for k, v in examen.items()
            if k not in ("formato", "no_cubierto")
        }
        ficha["recommendation"] = recomendacion(
            db, user, examen["id"], diagnostico=diagnostico
        )
        ficha["disclaimer"] = banco.AVISO_NO_OFICIAL
        ficha["trademark"] = banco.MARCAS[examen["id"]]
        examenes.append(ficha)
    return {
        "exams": examenes,
        "englishDiagnostic": diagnostico,
        "disclaimer": banco.AVISO_NO_OFICIAL,
    }


def detalle(db: Any, user: Any, exam_id: str) -> Dict[str, Any]:
    """La ficha completa de un examen: habilidades, formato y lo que NO cubre."""
    examen = banco.get_examen(exam_id)
    if examen is None:
        raise ValueError(f"examen desconocido: {exam_id!r}")

    diagnostico = diagnostico_de_ingles(db, user)
    habilidades = []
    for h in banco.habilidades_de(exam_id):
        entrada = dict(h)
        entrada["startsAt"] = _nivel_para(h, diagnostico)
        habilidades.append(entrada)

    ficha = dict(examen)
    ficha["skills"] = habilidades
    ficha["recommendation"] = recomendacion(db, user, exam_id, diagnostico=diagnostico)
    ficha["englishDiagnostic"] = diagnostico
    ficha["disclaimer"] = banco.AVISO_NO_OFICIAL
    ficha["trademark"] = banco.MARCAS[exam_id]
    ficha["examinerNotice"] = banco.REMISION_AL_EXAMINADOR
    return ficha
