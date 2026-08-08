"""RM-1 · El acompañamiento periódico · dónde se quedó cada persona.

Verónica, reunión del 21-07: *"Periódicamente él debe escribirte: hola, ¿cómo vas
con tu proyecto? ¿tomaste el curso de inglés?… él se vuelve tu amigo, como decir:
Claudio, mi asistente"*.

La frase importante de ese pedido no es "periódicamente" — es **"¿tomaste el
curso de inglés?"**. Lo que describe no es un boletín cada quince días: es
alguien que sabe en qué punto te quedaste y te habla de eso. Por eso este módulo
detecta **el siguiente paso pendiente de cada persona**, y si no hay ninguno, no
se le escribe. Un mensaje que no dice nada específico entrena a la gente a
ignorar los que sí.

## Por qué es determinista

La IA redacta (`outreach_message.txt`), pero **no decide a quién se le escribe ni
por qué**. Esa decisión se toma con consultas a la base de datos, se puede probar
sin llamar al modelo, y se puede explicar en el panel cuando alguien pregunte por
qué recibió un correo. Un modelo eligiendo destinatarios es algo que nadie puede
auditar — y aquí hay menores de edad.

## Lo que NO se detecta

No hay forma de saber si alguien **abrió** sus rutas: `Route` no tiene marca de
vista. Se evaluó como motivo y se descartó en vez de aproximarlo con
`last_login_at`, que respondería otra pregunta ("entró a la plataforma") y
produciría mensajes falsos ("vi que no has mirado tus rutas" a quien sí las miró).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session as DBSession

from app.db.models import Route, Session, User, UserRole

logger = logging.getLogger(__name__)


# Días sin actividad antes de considerar que alguien "se quedó" en un punto.
# No es un número mágico: por debajo de una semana se le estaría escribiendo a
# quien simplemente no ha entrado el fin de semana.
DIAS_PARA_CONSIDERAR_ESTANCADO = 7

# Ningún motivo se repite antes de esto, y a nadie se le escribe dos veces en
# este plazo aunque cambie de motivo. "Se vuelve tu amigo" deja de ser cierto
# cuando escribe cada tres días.
DIAS_ENTRE_MENSAJES = 14

# Niveles de inglés que dan pie a la pregunta que ella puso de ejemplo.
CEFR_BAJO = {"A1", "A2", "B1"}


@dataclass(frozen=True)
class Motivo:
    """Por qué se le va a escribir a esta persona.

    `clave` es estable y se guarda en `OutreachLog` — es lo que permite no
    repetir el mismo mensaje. `asunto` y `contexto` alimentan al redactor.
    """

    clave: str
    asunto: str
    contexto: str
    destino: str  # a dónde lo manda el CTA


# Orden de evaluación = orden del recorrido de la persona. Se devuelve el
# PRIMER motivo aplicable, que es el más temprano de su camino: no tiene sentido
# hablarle del inglés a quien todavía no ha hecho un test.
_ORDEN = ("sin_tests", "journey_a_medias", "sin_rutas", "ingles_pendiente")


def _sesion_mas_reciente(db: DBSession, user: User) -> Optional[Session]:
    return (
        db.query(Session)
        .filter(Session.user_id == user.id)
        .order_by(desc(Session.updated_at))
        .first()
    )


def _lleva_quieto(referencia: Optional[datetime], ahora: datetime) -> bool:
    """¿Pasó suficiente tiempo sin actividad como para escribirle?

    Sin referencia devuelve False: no sabemos cuándo fue la última vez, y ante
    la duda no se escribe.
    """
    if referencia is None:
        return False
    return (ahora - referencia) >= timedelta(days=DIAS_PARA_CONSIDERAR_ESTANCADO)


def detectar_motivo(
    db: DBSession, user: User, *, ahora: Optional[datetime] = None
) -> Optional[Motivo]:
    """El siguiente paso pendiente de esta persona · None si no hay ninguno.

    Devolver None es un resultado normal y deseable: a quien está al día no se
    le escribe.
    """
    ahora = ahora or datetime.utcnow()

    # Sólo estudiantes. Al asesor ya le llegan sus resúmenes de CRM
    # (`build_daily_summary`), que son otra cosa.
    if user.role != UserRole.STUDENT:
        return None

    from app.services.recommendation_service import user_has_tests

    sesion = _sesion_mas_reciente(db, user)
    tiene_tests = user_has_tests(db, user)

    # 1 · Ni un test. Es la señal que la propia clienta considera la más fuerte:
    # "el test verdaderamente va a ser el que más nos va a generar información".
    if not tiene_tests:
        referencia = sesion.updated_at if sesion else user.created_at
        if _lleva_quieto(referencia, ahora):
            return Motivo(
                clave="sin_tests",
                asunto="Tu perfil está a un test de distancia",
                contexto=(
                    "Todavía no ha presentado ningún test vocacional. Es lo que "
                    "más cambia lo que la plataforma puede decirle."
                ),
                destino="/tests",
            )
        return None

    # 2 · Hizo tests pero dejó el journey a medias · el caso exacto de Verónica.
    if sesion is not None and not sesion.is_completed:
        if _lleva_quieto(sesion.updated_at, ahora):
            return Motivo(
                clave="journey_a_medias",
                asunto="Retomemos donde lo dejaste",
                contexto=(
                    "Ya presentó tests, pero dejó su recorrido a medias y no lo "
                    "ha retomado. Sus respuestas siguen guardadas."
                ),
                destino="/journey",
            )
        return None

    # 3 · Terminó el recorrido y no tiene rutas generadas.
    if sesion is not None:
        tiene_rutas = (
            db.query(Route.id).filter(Route.session_id == sesion.id).first() is not None
        )
        if not tiene_rutas and _lleva_quieto(sesion.updated_at, ahora):
            return Motivo(
                clave="sin_rutas",
                asunto="Tus rutas ya se pueden generar",
                contexto=(
                    "Tiene tests y terminó su recorrido, pero todavía no se le "
                    "han generado rutas profesionales."
                ),
                destino="/routes",
            )

    # 4 · El inglés · la pregunta que ella puso de ejemplo, literal.
    nivel = (user.english_cefr_level or "").upper().strip()
    if not user.english_test_completed or nivel in CEFR_BAJO:
        return Motivo(
            clave="ingles_pendiente",
            asunto="¿Cómo vas con el inglés?",
            contexto=(
                "No ha presentado el examen de inglés."
                if not user.english_test_completed
                else f"Su nivel medido es {nivel}, que limita a qué programas puede aplicar."
            ),
            destino="/tests/ingles",
        )

    # Al día · no se le escribe. Es un resultado válido, no un fallo.
    return None


def ya_se_le_escribio_hace_poco(
    db: DBSession, user: User, *, ahora: Optional[datetime] = None
) -> bool:
    """Tope de frecuencia · aplica a la persona, no al motivo.

    Se mira el último mensaje SEA CUAL SEA su motivo: alternar motivos para
    escribir cada semana es exactamente lo que convierte a un asistente en spam.

    ⚠️ **Sólo cuentan los mensajes que de verdad SALIERON.** `OutreachLog`
    guarda también los no-envíos (`simulacro` del preview, `apagado` cuando el
    interruptor está cerrado, `sin_consentimiento`, `fallo_envio`), y contarlos
    aquí silenciaba el producto sin que nada se viera roto:

      - El despliegue previsto es agendar el cron con el interruptor APAGADO
        para verlo correr sin que salga nada. Eso llenaba la tabla de filas
        `apagado` y, al prender el interruptor, **nadie recibía nada durante 14
        días** — justo cuando la clienta está mirando.
      - Revisar el preview con ella dejaba sin mensaje a la gente del preview.
      - Y a quien daba el permiso hoy había que esperarlo dos semanas, porque su
        no-envío de ayer contaba como envío.
    """
    from app.db.models import OutreachLog

    ahora = ahora or datetime.utcnow()
    ultimo = (
        db.query(OutreachLog)
        .filter(
            OutreachLog.user_id == user.id,
            OutreachLog.resultado == "enviado",
        )
        .order_by(desc(OutreachLog.created_at))
        .first()
    )
    if ultimo is None:
        return False
    return (ahora - ultimo.created_at) < timedelta(days=DIAS_ENTRE_MENSAJES)


def candidatos(
    db: DBSession, *, limite: int = 200, ahora: Optional[datetime] = None
) -> List[tuple]:
    """(usuario, motivo) de todos los que hoy recibirían un mensaje.

    Aplica, en este orden: sólo estudiantes activos → tope de frecuencia →
    motivo detectado. **NO aplica el gate de consentimiento**: eso lo hace quien
    envía, a propósito, para que el preview del panel pueda mostrar "a esta
    persona le escribiríamos, pero no dio permiso" en vez de esconderla.

    ⚠️ `limite` topa **los mensajes de esta corrida**, no los usuarios que se
    miran. La primera versión hacía `.limit()` sobre la consulta de usuarios,
    sin orden ni rotación: quien quedara fuera del primer bloque **no habría
    recibido un mensaje nunca**, y el defecto era invisible porque la corrida
    reportaba "revisados=N" y se veía sana.

    El orden es por antigüedad del último envío (los que llevan más sin recibir
    nada van primero) y luego por fecha de registro, para que la rotación sea
    estable y no dependa del orden físico de las filas.
    """
    ahora = ahora or datetime.utcnow()

    # Se recorren TODOS los estudiantes activos y se corta al llegar al tope de
    # mensajes. La consulta trae sólo lo necesario para ordenar; el trabajo caro
    # (detectar motivo) se hace de a uno y se para apenas se llena el cupo.
    usuarios = (
        db.query(User)
        .filter(User.role == UserRole.STUDENT, User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .all()
    )

    salida = []
    for u in usuarios:
        if len(salida) >= limite:
            break
        if ya_se_le_escribio_hace_poco(db, u, ahora=ahora):
            continue
        motivo = detectar_motivo(db, u, ahora=ahora)
        if motivo is not None:
            salida.append((u, motivo))
    return salida
