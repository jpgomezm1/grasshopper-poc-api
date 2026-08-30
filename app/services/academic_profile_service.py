"""La ficha académica · leer, guardar y normalizar.

Verónica (Paso 3 · College List): *"para construir esto es importante
preguntarle al estudiante su GPA (promedio acumulado) y su sistema de colegio
… ¿tienes AP? ¿cuántas? ¿qué puntajes? ¿tienes SAT?"*.

## El trabajo de verdad de este módulo es NO dejar entrar basura

Una ficha académica alimenta decisiones de admisión. Un GPA de 42, un SAT de
95 o un IB de 60 no son "datos imperfectos": son números que harían que el
producto le dijera a alguien que una universidad es alcanzable cuando no lo
es. Por eso todo lo que entra se valida, y lo que no pasa se rechaza con un
mensaje que dice qué está mal — no se recorta ni se "arregla" en silencio.

## Por qué la escala viaja pegada al GPA

Un 4.2 sobre 5.0 y un 3.8 sobre 4.0 son el mismo número en dos idiomas: el 4.2
traducido es 3.36, y está POR DEBAJO del 3.8. Comparar los dos crudos
clasifica al revés.

`Program.avg_admitted_gpa` arrastra ese defecto —un `Float` sin escala— y hoy
es inofensivo sólo porque el GPA del estudiante siempre llega `None`. Aquí la
escala es obligatoria si hay número, y además se expone `gpa_porcentaje`, que
es la única forma comparable entre sistemas.

## Lo que este módulo NO hace todavía

**No clasifica nada.** Verificado el 2026-08-30 contra el catálogo: de 2.562
programas, CERO tienen `acceptance_rate`, `avg_admitted_gpa`, `min_sat` o
`avg_sat`. Sin esos datos `admission_fit_service.classify()` devuelve `None`
para todos, tenga o no métricas el estudiante.

Así que la ficha se guarda, se muestra y le sirve a quien la lee hoy (el
estudiante, su hoja de vida, el Counselor Sync, el asesor). El badge
Reach/Target/Safety se enciende el día que el catálogo tenga con qué comparar
— y ese dato es el Excel a nivel programa que se le viene pidiendo a la
clienta desde julio.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.db.models import StudentAcademicProfile, User

logger = logging.getLogger(__name__)

# Las escalas que existen de verdad en los sistemas que toca este producto.
# Una lista cerrada y no un rango: "sobre 7.3" no es una escala, es un error de
# dedo, y aceptarla haría que el porcentaje normalizado saliera plausible pero
# falso.
ESCALAS_VALIDAS = (4.0, 5.0, 7.0, 10.0, 20.0, 100.0)

SAT_MIN, SAT_MAX = 400, 1600
AP_MIN, AP_MAX = 1, 5
IB_MIN, IB_MAX = 0, 45


class DatoInvalido(ValueError):
    """Algo que el estudiante escribió no puede ser cierto · se le dice cuál."""


def _validar_gpa(gpa: Optional[float], escala: Optional[float]) -> None:
    if gpa is None and escala is None:
        return
    if gpa is None or escala is None:
        raise DatoInvalido(
            "El promedio y su escala van juntos: un 4.2 no significa nada sin "
            "saber si es sobre 5.0 o sobre 4.0."
        )
    if float(escala) not in ESCALAS_VALIDAS:
        raise DatoInvalido(
            f"Escala no reconocida. Las que manejamos: "
            f"{', '.join(str(e) for e in ESCALAS_VALIDAS)}."
        )
    if not (0 <= float(gpa) <= float(escala)):
        raise DatoInvalido(f"El promedio tiene que estar entre 0 y {escala}.")


def _validar_sat(puntaje: Optional[int]) -> None:
    if puntaje is None:
        return
    if not (SAT_MIN <= int(puntaje) <= SAT_MAX):
        raise DatoInvalido(f"El SAT va de {SAT_MIN} a {SAT_MAX}.")


def _validar_ib(total: Optional[int]) -> None:
    if total is None:
        return
    if not (IB_MIN <= int(total) <= IB_MAX):
        raise DatoInvalido(f"El total del Diploma IB va de {IB_MIN} a {IB_MAX}.")


def _validar_ap(materias: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """Deja la lista en su forma canónica, o explica qué está mal.

    Se descartan las filas sin materia: una entrada vacía que el estudiante
    abrió y no llenó no es un dato, y guardarla ensuciaría el CV y el reporte
    al colegio con líneas en blanco.
    """
    if not materias:
        return None
    limpias: List[Dict[str, Any]] = []
    for fila in materias:
        if not isinstance(fila, dict):
            continue
        materia = str(fila.get("materia") or "").strip()[:120]
        if not materia:
            continue
        puntaje = fila.get("puntaje")
        if puntaje is not None:
            try:
                puntaje = int(puntaje)
            except (TypeError, ValueError):
                raise DatoInvalido(f"El puntaje de «{materia}» tiene que ser un número.")
            if not (AP_MIN <= puntaje <= AP_MAX):
                raise DatoInvalido(f"Los AP se califican de {AP_MIN} a {AP_MAX}.")
        limpias.append({"materia": materia, "puntaje": puntaje})
    return limpias or None


def obtener(db: DBSession, user: User) -> Optional[StudentAcademicProfile]:
    return (
        db.query(StudentAcademicProfile)
        .filter(StudentAcademicProfile.user_id == user.id)
        .first()
    )


def guardar(db: DBSession, user: User, datos: Dict[str, Any]) -> StudentAcademicProfile:
    """Crea o actualiza la ficha · valida TODO antes de tocar la fila.

    Se valida primero y se escribe después a propósito: si el SAT es válido
    pero el IB no, no puede quedar medio guardado. O entra entera o no entra.
    """
    gpa = datos.get("gpa")
    escala = datos.get("gpa_scale")
    _validar_gpa(gpa, escala)
    _validar_sat(datos.get("sat_score"))
    _validar_ib(datos.get("ib_predicted_total"))
    ap = _validar_ap(datos.get("ap_scores"))

    ficha = obtener(db, user)
    if ficha is None:
        ficha = StudentAcademicProfile(user_id=user.id)
        db.add(ficha)

    ficha.gpa = gpa
    ficha.gpa_scale = escala
    ficha.sat_score = datos.get("sat_score")
    ficha.sat_taken_on = datos.get("sat_taken_on")
    ficha.ap_scores = ap
    ficha.ib_predicted_total = datos.get("ib_predicted_total")
    ficha.updated_at = datetime.utcnow()

    db.flush()
    return ficha


def gpa_porcentaje(ficha: Optional[StudentAcademicProfile]) -> Optional[float]:
    """El promedio como 0-100 · la única forma comparable entre sistemas.

    No se guarda en la base: es una derivada exacta de dos columnas que ya
    están ahí, y guardarla sería una segunda fuente de verdad que puede
    desincronizarse (el error #1 de este repo).
    """
    if ficha is None or ficha.gpa is None or not ficha.gpa_scale:
        return None
    return round((float(ficha.gpa) / float(ficha.gpa_scale)) * 100, 1)


def a_diccionario(ficha: Optional[StudentAcademicProfile]) -> Dict[str, Any]:
    """La forma que ve el cliente · con el vacío explícito, no ausente.

    Devolver las claves en `None` en vez de omitirlas deja claro que la ficha
    existe y está sin llenar, que es distinto de "esto no aplica".
    """
    return {
        "gpa": ficha.gpa if ficha else None,
        "gpa_scale": ficha.gpa_scale if ficha else None,
        "gpa_porcentaje": gpa_porcentaje(ficha),
        "sat_score": ficha.sat_score if ficha else None,
        "sat_taken_on": (
            ficha.sat_taken_on.isoformat() if ficha and ficha.sat_taken_on else None
        ),
        "ap_scores": (ficha.ap_scores if ficha else None) or [],
        "ib_predicted_total": ficha.ib_predicted_total if ficha else None,
        "updated_at": (ficha.updated_at.isoformat() if ficha else None),
        # Lo que falta para que la College List pueda clasificar. Se dice aquí
        # y no en la pantalla para que front y back no discrepen sobre qué es
        # "estar completo".
        "listo_para_clasificar": bool(
            ficha and ficha.gpa is not None and ficha.gpa_scale
        ),
    }
