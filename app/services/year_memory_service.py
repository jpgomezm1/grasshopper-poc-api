"""Memoria entre años · comparar "qué dijo el año pasado" con "qué dice hoy".

Fase 2 de 4 de la malla completa (Cimientos fue la fase 1 · migración 067).
Este servicio es el LECTOR de `StudentYearSnapshot` — el cimiento dejó la tabla
y la consulta documentada en su docstring (`app/db/models.py`), pero nada la
escribe todavía. Eso es DELIBERADO y quedó así en el propio cimiento: "quién
escribe esta tabla y cuándo ... es una decisión de producto que no toma esta
fase". Esta fase tampoco la toma — construye el consumidor completo (lectura +
comparación + check-in), listo para el día en que exista un disparador que
guarde snapshots (detectar cambio de grado, cron de año escolar, acción manual
de un asesor). Hasta entonces, `get_year_comparison` es honesto: `has_memory`
sale en `False` para todos los estudiantes, porque no hay ninguna fila que
leer — no se inventa un año anterior que no existe.

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

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    return [{"test_id": r.test_id, "taken_at": r.created_at} for r in resultados]


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
