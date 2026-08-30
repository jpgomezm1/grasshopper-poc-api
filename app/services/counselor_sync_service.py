"""Counselor Sync · el reporte que el estudiante le manda a su consejera.

Verónica, revisión Sprint 2 (Paso 5 de su flujo):

    "Al finalizar cada etapa, el sistema genera un reporte ejecutivo de
     progreso que el estudiante envía a su consejera antes de su reunión
     presencial."

Y el porqué, que es lo que define qué va dentro:

    "Cuando el alumno se sienta con la consejera, ya sabe QUÉ QUIERE, QUÉ
     OPCIONES REALISTAS TIENE y QUÉ LE FALTA POR HACER."

Esas tres son, literalmente, las tres secciones del reporte. Nada más.

## Ejecutivo quiere decir corto

La tentación es volcar todo lo que sabemos: sería más fácil y se vería más
completo. Pero el documento entero de Verónica gira alrededor de que las
consejeras están saturadas —*"lidiando con la ansiedad de cientos de padres y
alumnos"*— y de que la plataforma les ALIVIE carga. Un volcado de doce
secciones es carga nueva, no alivio.

Por eso: tres bloques, y cada uno con lo mínimo que sirve para preparar una
reunión de media hora.

## Lo que NO entra, a propósito

- **El análisis clínico.** Vive en `clinical_analysis_service` con su propio
  control de acceso (`_require_clinical_role`) y su base legal. Que el
  estudiante pueda mandarle a su colegio su avance NO es una vía para sacar
  datos clínicos por la puerta de atrás.
- **Las reflexiones íntimas del journey.** El propio producto ya le promete a
  la familia que no las ve (ver el panel de acudientes); el colegio tampoco
  las pidió aquí.
- **Interpretaciones psicométricas completas.** Va QUÉ tests hizo y cuándo, no
  el cruce RIASEC/Big Five — eso ya lo sirve `psychometrics_service` a quien
  tiene rol para verlo, y repetirlo aquí sería una segunda copia con otro
  control de acceso.

Lo que va son cosas que el estudiante ya declaró o hizo, y que está eligiendo
compartir.

## De dónde sale el contenido

De `year_memory_service.get_year_comparison`, cuyo bloque `today` ya ensambla
—con el catálogo de opciones traducido a texto legible— exactamente el perfil
declarado, los tests tomados y las rutas activas. Reconstruirlo aquí sería una
segunda fuente de verdad para lo mismo, que es el error que este repo ya pagó
cuatro veces.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DBSession

from app.db.models import CounselorSyncReport, User, VocationalTestResult
from app.services import year_memory_service

logger = logging.getLogger(__name__)


def _que_le_falta(db: DBSession, user: User, comparacion) -> List[str]:
    """Los pendientes del estudiante, en el mismo orden que la guía del producto.

    Es la MISMA escalera que el front dibuja en el mapa del proceso
    (`nextStep.ts`) y que la barra de guía propone: onboarding → primer test →
    inglés → más tests → rutas. Si esta lista dijera otra cosa, el estudiante
    llegaría a la reunión con una consejera que leyó pendientes distintos de
    los que él ve en pantalla — el bug P0-8 de este repo, cruzando roles.
    """
    faltan: List[str] = []

    onboarding_ok = str(getattr(user.onboarding_status, "value", user.onboarding_status) or "")
    if onboarding_ok.lower() != "completed":
        faltan.append("Terminar de contar quién es (onboarding)")

    tests = len(comparacion.today.tests_taken)
    if tests == 0:
        faltan.append("Hacer su primer test de orientación")
    elif tests < 3:
        faltan.append(f"Completar más tests (lleva {tests} de 3)")

    if not bool(getattr(user, "english_test_completed", False)):
        faltan.append("Medir su nivel de inglés")

    if not comparacion.today.active_routes:
        faltan.append("Revisar las rutas que le armamos")

    return faltan


def construir_reporte(db: DBSession, user: User) -> Dict[str, Any]:
    """Arma el reporte · las tres preguntas de Verónica, en ese orden.

    No guarda nada: sirve tanto para la vista previa que el estudiante mira
    antes de decidir si lo manda, como para la foto que se congela al enviar.
    Un solo constructor para los dos usos — si la vista previa y lo enviado se
    armaran por separado, el estudiante mandaría algo distinto de lo que vio.
    """
    comparacion = year_memory_service.get_year_comparison(db, user)
    hoy = comparacion.today

    return {
        "generado_en": datetime.utcnow().isoformat(),
        "estudiante": {
            "nombre": user.name,
            "grado": hoy.grade,
        },
        # 1 · QUÉ QUIERE
        "que_quiere": asdict(hoy.perfil),
        # 2 · QUÉ OPCIONES REALISTAS TIENE
        "sobre_que_decide": {
            "tests_hechos": hoy.tests_taken,
            "rutas_activas": hoy.active_routes,
        },
        # 3 · QUÉ LE FALTA POR HACER
        "que_le_falta": _que_le_falta(db, user, comparacion),
        # Contexto que la consejera agradece y no le cuesta nada: si el
        # estudiante cambió de grado y qué dijo distinto respecto al año
        # pasado. Sale gratis porque `get_year_comparison` ya lo calcula.
        "cambios_desde_el_ano_pasado": comparacion.changed_fields if comparacion.has_memory else [],
    }


def enviar(
    db: DBSession, user: User, nota: Optional[str] = None
) -> CounselorSyncReport:
    """Congela el reporte y lo deja en el panel del colegio.

    Lanza `ValueError` si el estudiante no tiene colegio: un B2C no tiene a
    quién mandárselo, y decir eso claro es mejor que guardar una fila que nadie
    va a leer nunca.
    """
    if getattr(user, "school_id", None) is None:
        raise ValueError("Este estudiante no pertenece a un colegio.")

    reporte = CounselorSyncReport(
        student_user_id=user.id,
        school_id=user.school_id,
        content=construir_reporte(db, user),
        # Se recorta aquí y no en el endpoint para que el límite valga venga de
        # donde venga la llamada.
        student_note=(nota or "").strip()[:2000] or None,
    )
    db.add(reporte)
    db.flush()
    return reporte


def listar_del_colegio(
    db: DBSession, school_id, limite: int = 50
) -> List[CounselorSyncReport]:
    """Lo que le han mandado a este colegio · lo más reciente primero."""
    return (
        db.query(CounselorSyncReport)
        .filter(CounselorSyncReport.school_id == school_id)
        .order_by(CounselorSyncReport.sent_at.desc())
        .limit(limite)
        .all()
    )


def listar_del_estudiante(db: DBSession, user_id, limite: int = 20) -> List[CounselorSyncReport]:
    """Lo que ESTE estudiante ha mandado · para que vea qué compartió y cuándo."""
    return (
        db.query(CounselorSyncReport)
        .filter(CounselorSyncReport.student_user_id == user_id)
        .order_by(CounselorSyncReport.sent_at.desc())
        .limit(limite)
        .all()
    )


def marcar_leido(db: DBSession, reporte: CounselorSyncReport) -> None:
    """La primera vez que alguien del colegio lo abre.

    No se re-marca: interesa "llegó y lo vieron", no cuántas veces. Contar
    aperturas convertiría esto en un cronómetro sobre la consejera, que es lo
    contrario de aliviarle carga.
    """
    if reporte.read_at is None:
        reporte.read_at = datetime.utcnow()
