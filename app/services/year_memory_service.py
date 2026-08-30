"""Memoria entre años · comparar "qué dijo el año pasado" con "qué dice hoy".

Fase 2 de 4 de la malla completa (Cimientos fue la fase 1 · migración 067).
Este servicio es el LECTOR **y, desde el 2026-08-29, también el ESCRITOR** de
`StudentYearSnapshot`.

## El escritor que faltaba (P1)

El cimiento dejó la tabla y este servicio dejó la lectura completa
—comparación y check-in incluidos— pero **nadie escribía**. Verificado con un
grep: no había un solo constructor de `StudentYearSnapshot` fuera de
`models.py`. Resultado: la tabla vacía para todo el mundo, `has_memory`
siempre `False`, y el "Check-in de Evolución" que pidió Verónica —*"la IA le
recuerda qué le gustaba en 9° y pregunta si algo cambió"*— **no podía
dispararse jamás**, aunque estuviera construido de punta a punta.

El cimiento no eligió el disparador a propósito ("es una decisión de producto
que no toma esta fase"), pero sí dejó escrito el CUÁNDO: *"cuando el
estudiante pasa de año y sus respuestas cambian, ALGUIEN debe copiar el estado
saliente aquí ANTES de sobrescribirlo en `users`"*, y sugirió el cómo: *"al
detectar que `grade` cambió"*.

Eso es lo que hace `guardar_snapshot_saliente`, y por eso se llama desde
`_sync_onboarding_to_user_columns` (`app/api/v1/auth.py`), que es el ÚNICO
sitio del sistema donde `User.grade` cambia. Un solo punto de escritura para
un solo punto de cambio.

Se descartó el otro candidato —la pantalla de cierre de año, que lo pide en su
propio TODO— porque `/cierre-de-ano` es alcanzable en cualquier momento y no
cierra nada: alguien que la abre en marzo congelaría marzo. El cambio de grado
es el momento real en que el año anterior deja de ser vigente.

"MEMORIA SÍ, LLAVE NO" sigue intacto: esto guarda y compara. No bloquea nada.

"MEMORIA SÍ, LLAVE NO": este módulo sólo lee y compara. No bloquea ni
desbloquea nada, y no conoce calendario escolar — `school_year` es sólo la
clave de partición que ya definió el cimiento (año calendario, ej. 2026).

## Por qué "año pasado" no trae tests ni ruta

`StudentYearSnapshot` sólo copia dos cosas por año: `grade` y
`onboarding_answers_snapshot` (ver su docstring). No existe una foto por año
de `VocationalTestResult` ni de `Route` — esas tablas no están versionadas por
año en el cimiento, así que preguntar "¿qué ruta tenía el año pasado?" no tiene
dónde buscarse todavía. Este servicio lo dice explícito en vez de fingir un
dato que no existe (`previous.tests_available` / `previous.route_available`
siempre en `False`): inventar un valor ahí sería el mismo error que ya pagó
este repo con datos huérfanos, sólo que del lado de lectura.

"Hoy" sí trae los tres (intereses, tests, ruta) porque esos viven en tablas
vigentes (`User.onboarding_answers`, `VocationalTestResult`, `Route`) y no
necesitan snapshot: son el estado actual, siempre disponible.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session as DBSession

from app.data.onboarding_hechos import get_hecho
from app.db.models import (
    Route,
    RouteStatus,
    Session as JourneySession,
    StudentYearSnapshot,
    User,
    VocationalTestResult,
)

logger = logging.getLogger(__name__)

# Campos cualitativos del onboarding que tiene sentido comparar año a año.
# Deliberadamente NO incluye los "duros de logística" (passport, modality):
# lo que le importa a un check-in de evolución es la persona (qué le apasiona,
# qué le preocupa, hacia dónde va), no el trámite.
_CAMPOS_COMPARABLES = (
    "voice_passion",
    "voice_hobbies",
    "voice_strengths",
    "main_goal",
    "international_interest",
    "countries",
    "budget",
)

_LABELS_FALLBACK = {
    "voice_passion": "Lo que le apasiona",
    "voice_hobbies": "Sus intereses / tiempo libre",
    "voice_strengths": "Sus fortalezas",
    "main_goal": "Qué busca resolver",
    "international_interest": "Si le interesa el exterior",
    "countries": "Países de interés",
    "budget": "Presupuesto",
}

@dataclass
class PerfilDeclarado:
    """Lo cualitativo que el estudiante contó, en un momento dado.

    Se arma con el MISMO extractor (`_intereses_declarados`) tanto para el
    snapshot del año pasado como para `user.onboarding_answers` de hoy — así
    la comparación es entre manzanas y manzanas, no entre dos formatos.
    """
    pasion: Optional[str] = None
    hobbies: Optional[str] = None
    fortalezas: Optional[str] = None
    objetivo: Optional[str] = None
    interes_exterior: Optional[str] = None
    paises: List[str] = field(default_factory=list)
    presupuesto: Optional[str] = None

    def esta_vacio(self) -> bool:
        return not any(
            (self.pasion, self.hobbies, self.fortalezas, self.objetivo,
             self.interes_exterior, self.paises, self.presupuesto)
        )


@dataclass
class AnioAnterior:
    school_year: int
    grade: Optional[int]
    perfil: PerfilDeclarado
    # Siempre False hoy · ver docstring del módulo ("Por qué 'año pasado' no
    # trae tests ni ruta"). Se dejan como campos explícitos (y no simplemente
    # ausentes) para que quien consuma esto no tenga que adivinar por qué
    # faltan — lo dice el propio dato.
    tests_available: bool = False
    route_available: bool = False


@dataclass
class HoyMismo:
    grade: Optional[int]
    perfil: PerfilDeclarado
    tests_taken: List[Dict[str, Any]] = field(default_factory=list)
    active_routes: List[str] = field(default_factory=list)


@dataclass
class YearComparison:
    has_memory: bool
    is_new_grade: bool
    previous: Optional[AnioAnterior]
    today: HoyMismo
    changed_fields: List[str] = field(default_factory=list)


def _etiqueta_opcion(campo: str, valor: Any) -> Any:
    """Traduce un código de opción (ej. 'intl_yes') a texto legible.

    Se apoya en el catálogo de `onboarding_hechos` (sólo LECTURA, no se
    modifica ese archivo) para no duplicar el vocabulario de opciones y
    arriesgarse a que las dos copias diverjan.
    """
    hecho = get_hecho(campo)
    if not hecho or not hecho.opciones:
        return valor
    if isinstance(valor, list):
        return [hecho.opciones.get(v, v) for v in valor]
    return hecho.opciones.get(valor, valor)


def _intereses_declarados(answers: Optional[Dict[str, Any]]) -> PerfilDeclarado:
    """Extrae lo cualitativo de un dict `onboarding_answers` (vigente o snapshot).

    Ambas fuentes comparten el MISMO shape (así lo dejó el cimiento a
    propósito, ver `StudentYearSnapshot.onboarding_answers_snapshot`), así que
    esta función sirve para las dos sin distinguir de dónde vino el dict.
    """
    a = answers or {}

    paises = a.get("countries") or []
    if isinstance(paises, str):
        paises = [paises]
    paises_legibles = [str(p) for p in _etiqueta_opcion("countries", paises)]

    def _texto(campo: str) -> Optional[str]:
        v = a.get(campo)
        if not v or not isinstance(v, str) or not v.strip():
            return None
        return v.strip()

    def _opcion(campo: str) -> Optional[str]:
        """Etiqueta legible de un campo de opción · soporta selección única
        (`international_interest`, `budget`) Y múltiple (`main_goal`: el
        catálogo lo declara `tipo="multi"` y así lo guardan
        `journey_service`/`ai_service` — una lista, no un string suelto)."""
        v = a.get(campo)
        if v in (None, "", [], {}):
            return None
        legible = _etiqueta_opcion(campo, v)
        if isinstance(legible, list):
            return ", ".join(str(x) for x in legible)
        return str(legible)

    return PerfilDeclarado(
        pasion=_texto("voice_passion"),
        hobbies=_texto("voice_hobbies"),
        fortalezas=_texto("voice_strengths"),
        objetivo=_opcion("main_goal"),
        interes_exterior=_opcion("international_interest"),
        paises=paises_legibles,
        presupuesto=_opcion("budget"),
    )


def _campos_que_cambiaron(
    anterior: Optional[Dict[str, Any]], actual: Optional[Dict[str, Any]]
) -> List[str]:
    """Qué campos cualitativos son distintos entre los dos años (etiquetas legibles).

    Compara los diccionarios CRUDOS (no el `PerfilDeclarado` ya resumido) para
    no perder matices por el resumen — dos frases distintas de "pasión" que el
    resumen recortara igual siguen contando como cambio real.
    """
    anterior = anterior or {}
    actual = actual or {}
    cambios: List[str] = []
    for campo in _CAMPOS_COMPARABLES:
        v_antes = anterior.get(campo)
        v_ahora = actual.get(campo)
        # Normaliza vacíos (None, "", [], {}) para que "no contestó" en los dos
        # lados no cuente como "cambió".
        vacio_antes = v_antes in (None, "", [], {})
        vacio_ahora = v_ahora in (None, "", [], {})
        if vacio_antes and vacio_ahora:
            continue
        if v_antes != v_ahora:
            hecho = get_hecho(campo)
            etiqueta = hecho.pregunta_typeform if hecho else _LABELS_FALLBACK.get(campo, campo)
            cambios.append(etiqueta)
    return cambios


def _respuestas_salientes(user: User) -> Dict[str, Any]:
    """Las respuestas de ANTES de la escritura de este request.

    Los dos sitios que llaman al sync (`PUT /me/onboarding` y el onboarding
    conversacional) hacen `user.onboarding_answers = {**viejas, **nuevas}`
    ANTES de llamarlo. Leer el atributo aquí daría las NUEVAS, y guardaríamos
    como "lo que dijo el año pasado" lo que acaba de decir hoy — justo al revés
    de lo que pide el cimiento.

    SQLAlchemy conserva el valor anterior en el historial de la sesión hasta el
    flush, así que se lee de ahí. Si no hay historial (nadie tocó la columna en
    este request) el valor vigente ES el saliente, y sirve igual.

    Se copia en profundidad: la columna es JSON y quien nos llamó sigue
    trabajando sobre ese dict. Guardar la referencia haría que el snapshot
    cambiara con él.
    """
    try:
        historial = sa_inspect(user).attrs.onboarding_answers.history
        if historial.deleted:
            previo = historial.deleted[0]
            if isinstance(previo, dict):
                return copy.deepcopy(previo)
    except Exception:  # pragma: no cover · defensivo, nunca debe romper el guardado
        logger.warning("No se pudo leer el historial de onboarding_answers", exc_info=True)
    return copy.deepcopy(user.onboarding_answers or {})


def guardar_snapshot_saliente(db: DBSession, user: User) -> bool:
    """Congela el estado que está a punto de dejar de ser vigente.

    Se llama JUSTO ANTES de sobrescribir `User.grade`. Devuelve `True` si
    escribió una fila nueva.

    ## Idempotente, y se queda con la PRIMERA foto del año

    La tabla tiene `UniqueConstraint(user_id, school_year)`. Si ya hay foto de
    este año no se toca: la primera es la que capturó el estado saliente de
    verdad. Sobrescribirla con un segundo cambio de grado en el mismo año —una
    corrección de dato, un ida y vuelta— reemplazaría el recuerdo bueno por
    uno peor.

    ## Best-effort, como el sync que lo llama

    Nunca levanta. Perder un snapshot es una función que no se enciende ese
    año; romper el guardado del onboarding es perderle las respuestas al
    estudiante. El segundo es mucho peor.
    """
    try:
        anio = datetime.utcnow().year
        ya_existe = (
            db.query(StudentYearSnapshot)
            .filter(
                StudentYearSnapshot.user_id == user.id,
                StudentYearSnapshot.school_year == anio,
            )
            .first()
        )
        if ya_existe is not None:
            return False

        db.add(
            StudentYearSnapshot(
                user_id=user.id,
                school_year=anio,
                # El grado SALIENTE · todavía no lo sobrescribió el sync.
                grade=user.grade,
                onboarding_answers_snapshot=_respuestas_salientes(user),
            )
        )
        # Sin commit: quien llama ya lo hace, y meter uno aquí partiría su
        # transacción en dos.
        return True
    except Exception:  # pragma: no cover
        logger.warning("No se pudo guardar el snapshot del año", exc_info=True)
        return False


def _ultimo_snapshot(db: DBSession, user_id) -> Optional[StudentYearSnapshot]:
    """El snapshot más reciente de este estudiante · None si nunca se tomó ninguno.

    Misma consulta documentada en `StudentYearSnapshot` (cimiento) — se repite
    aquí en vez de importarse porque el cimiento la deja como ejemplo de uso en
    un docstring, no como función exportada.
    """
    return (
        db.query(StudentYearSnapshot)
        .filter(StudentYearSnapshot.user_id == user_id)
        .order_by(StudentYearSnapshot.school_year.desc())
        .first()
    )


def _tests_tomados_hoy(db: DBSession, user_id) -> List[Dict[str, Any]]:
    """Qué tests vocacionales tiene tomados HOY, uno por `test_id`.

    `vocational_test_results` fuerza `UniqueConstraint(user_id, test_id)`
    (`uq_user_test`) — repetir un test actualiza la MISMA fila, no crea una
    nueva. Por eso no hace falta deduplicar aquí: la base ya garantiza "una
    fila por tipo de test", y sólo queda ordenar para que el más reciente
    salga primero.

    Deliberadamente NO trae la interpretación psicométrica completa (RIASEC,
    Big Five, cruces...) — eso ya lo sirve `psychometrics_service` para el
    dossier del asesor. Aquí sólo importa "sí tomó este test, cuándo", que es
    lo que un check-in de memoria necesita para decir "ya hiciste tu test de
    intereses" sin repetir análisis que vive en otro lado.
    """
    resultados = (
        db.query(VocationalTestResult)
        .filter(VocationalTestResult.user_id == user_id)
        .order_by(VocationalTestResult.created_at.desc())
        .all()
    )
    # `taken_at` sale en ISO y no como `datetime` crudo porque este dict
    # TERMINA DENTRO DE UN JSON: el reporte que el estudiante le congela a su
    # colegio lo guarda en una columna JSON, y un datetime ahi revienta el
    # INSERT entero. Serializarlo en la fuente y no en cada consumidor evita
    # que el siguiente que guarde esto vuelva a tropezar. El contrato de
    # salida ya era string (`schoolApi.ts:218`) y el schema pydantic
    # (`year_memory.py:35`) parsea el ISO a datetime sin ayuda.
    return [
        {"test_id": r.test_id, "taken_at": r.created_at.isoformat()}
        for r in resultados
    ]


def _rutas_activas_hoy(db: DBSession, user_id) -> List[str]:
    """Nombres de las rutas activas HOY · mismo patrón de join que `me.py` dashboard."""
    rutas = (
        db.query(Route)
        .join(JourneySession, Route.session_id == JourneySession.id)
        .filter(
            JourneySession.user_id == user_id,
            Route.status == RouteStatus.ACTIVE,
        )
        .order_by(Route.created_at.desc())
        .all()
    )
    return [r.name for r in rutas]


def get_year_comparison(db: DBSession, user: User) -> YearComparison:
    """Arma "qué dijo el año pasado" vs "qué dice hoy" para este estudiante.

    Nunca lanza excepción por falta de memoria: si no hay snapshot, devuelve
    `has_memory=False` y `previous=None` — es el caso normal HOY para
    prácticamente todos los estudiantes, porque nada escribe la tabla todavía
    (ver docstring del módulo).
    """
    snapshot = _ultimo_snapshot(db, user.id)

    perfil_hoy = _intereses_declarados(user.onboarding_answers)
    hoy = HoyMismo(
        grade=user.grade,
        perfil=perfil_hoy,
        tests_taken=_tests_tomados_hoy(db, user.id),
        active_routes=_rutas_activas_hoy(db, user.id),
    )

    if snapshot is None:
        return YearComparison(
            has_memory=False,
            is_new_grade=False,
            previous=None,
            today=hoy,
            changed_fields=[],
        )

    perfil_anterior = _intereses_declarados(snapshot.onboarding_answers_snapshot)
    anterior = AnioAnterior(
        school_year=snapshot.school_year,
        grade=snapshot.grade,
        perfil=perfil_anterior,
    )

    # "Volvió en un grado nuevo" es la señal literal que pide el check-in de
    # evolución. Si cualquiera de los dos grados es None no se puede afirmar
    # que cambió (podría ser un perfil profesional en cualquiera de los dos
    # años) — ante la duda, NO se dispara el check-in.
    es_grado_nuevo = (
        snapshot.grade is not None
        and user.grade is not None
        and snapshot.grade != user.grade
    )

    cambios = _campos_que_cambiaron(
        snapshot.onboarding_answers_snapshot, user.onboarding_answers
    )

    return YearComparison(
        has_memory=True,
        is_new_grade=es_grado_nuevo,
        previous=anterior,
        today=hoy,
        changed_fields=cambios,
    )
