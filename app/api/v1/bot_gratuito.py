"""El bot gratuito · guardar lo que respondió y cómo contactarlo (B-4, Sprint 4).

La pantalla `/perfil` (`BotGratuitoPage.tsx`) hace las 9 preguntas del demo de
Verónica en el navegador y, al final, pide los datos de contacto. Este endpoint
recibe todo junto y lo guarda. Antes de él, lo respondido se perdía al cerrar
la pestaña.

## Por qué en `bot_conversations` y no en una tabla nueva

Esa tabla ya es "un prospecto que llegó por un bot": tiene nombre, correo,
teléfono, `hechos` (JSON), puntaje, banda, ruta, `converted_user_id` y la
sincronización con el CRM. La bandeja del equipo (`GET /bot/leads`) ya la lee.
Una tabla nueva sería una segunda bandeja, que es justo el problema que tenía
`lead_profiles` (se escribía y nadie la leía). Lo propio de este bot va en
`hechos`, marcado con `_fuente = "bot_gratuito"`; el conversacional no lo pone.

## El consentimiento queda guardado, con su texto

Ley 1581/2012: la autorización tiene que ser previa, expresa e informada. Se
guarda la versión y el texto exacto que vio, con la fecha. Si quien responde es
estudiante de colegio, el texto incluye que un adulto responsable autoriza (no
sabemos su edad, y probablemente es menor).

## Endpoint público = puerta abierta

Sin cuenta y sin IA (no gasta tokens), pero igual con tope por IP y validación
estricta: solo las claves del bot, textos cortos, y al menos un medio de
contacto. Si no, cualquiera llena la bandeja del equipo con basura.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.db.models import BotConversation, User
from app.services import aviso_prospectos, bot_gratuito_scoring, bot_gratuito_traspaso

router = APIRouter(prefix="/bot-gratuito", tags=["Bot gratuito"])

FUENTE = "bot_gratuito"
VERSION_CONSENTIMIENTO = "bot-gratuito-v1"

TEXTO_CONSENTIMIENTO = (
    "Autorizo el tratamiento de mis datos personales para que Mentoring me oriente "
    "y un asesor me contacte por WhatsApp o correo. Puedo pedir que los borren cuando quiera."
)
TEXTO_CONSENTIMIENTO_MENOR = (
    " Si soy menor de edad, confirmo que mi papá, mamá o acudiente autoriza compartir estos datos."
)

# Las claves que manda la pantalla (`src/lib/botGratuito.ts`). Lo demás se rechaza.
CLAVES_CERRADAS = ("who", "stage", "spark", "motor", "dest", "budget", "extra")
CLAVES_ABIERTAS = ("materias", "flow")
MAX_CODIGO = 20
MAX_ABIERTA = 300

CUANDO = {
    "now": "Este mes",
    "soon": "En 1 a 3 meses",
    "year": "En 3 a 12 meses",
    "later": "Más adelante",
}


def _rate_limit(request: Request) -> None:
    from app.core.rate_limiter import rate_limit

    return rate_limit(get_settings().rate_limit_bot_turn, scope="bot_gratuito_lead")(request)


# G-5 · Sprint 4 · tope diario por IP, además del de por minuto. El bot no llama
# a la IA (no hay costo por envío): el riesgo es que alguien llene la bandeja
# del equipo con basura. 200 al día deja pasar a un colegio entero detrás de la
# misma IP y frena un script.
TOPE_DIARIO = "200/day"

# G-5 · el mismo contacto con las MISMAS respuestas en este lapso no crea un
# prospecto nuevo (doble clic, recargar, volver atrás y reenviar): se devuelve
# el que ya existe y no se dispara un segundo aviso al equipo. Con respuestas
# distintas sí se crea: un papá o una mamá que llena el bot para dos hijos usa
# el mismo WhatsApp, y el segundo no puede perderse.
VENTANA_DUPLICADO = timedelta(minutes=10)


def _tope_diario(request: Request) -> None:
    from app.core.rate_limiter import rate_limit

    return rate_limit(TOPE_DIARIO, scope="bot_gratuito_lead_dia")(request)


def _reenvio_reciente(
    db: DBSession, email: Optional[str], whatsapp: Optional[str], respuestas: Dict[str, str]
) -> Optional[BotConversation]:
    desde = datetime.utcnow() - VENTANA_DUPLICADO
    candidatos = (
        db.query(BotConversation)
        .filter(BotConversation.created_at >= desde)
        .order_by(BotConversation.created_at.desc())
        .all()
    )
    for c in candidatos:
        if (c.hechos or {}).get("_fuente") != FUENTE:
            continue
        mismo_contacto = (email and (c.email or "").lower() == email) or (whatsapp and c.phone == whatsapp)
        if mismo_contacto and (c.hechos or {}).get("respuestas") == respuestas:
            return c
    return None


class Contacto(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    whatsapp: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=255)
    cuando: str


class LeadRequest(BaseModel):
    respuestas: Dict[str, str]
    contacto: Contacto
    acepta_tratamiento: bool
    utm_source: Optional[str] = Field(default=None, max_length=120)
    utm_medium: Optional[str] = Field(default=None, max_length=120)
    utm_campaign: Optional[str] = Field(default=None, max_length=120)


class LeadResponse(BaseModel):
    lead_id: UUID
    # B-6 · qué botón secundario mostrar en la señal preliminar. Es un código
    # neutro a propósito: la pantalla NUNCA recibe el puntaje ni la banda
    # (caliente/tibio/frío), que son para el equipo.
    siguiente_paso: str


# Ruta del equipo → siguiente paso que se le ofrece a la persona.
SIGUIENTE_PASO = {
    "asesor": "contacto",
    "perfilamiento": "perfilamiento",
    "telemercadeo": "contenido",
}


class AccionRequest(BaseModel):
    accion: str


class AccionResponse(BaseModel):
    ok: bool = True


def texto_consentimiento(respuestas: Dict[str, str]) -> str:
    """El texto exacto que ve la persona · el mismo que muestra la pantalla."""
    if respuestas.get("who") == "colegio":
        return TEXTO_CONSENTIMIENTO + TEXTO_CONSENTIMIENTO_MENOR
    return TEXTO_CONSENTIMIENTO


def _invalido(detalle: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detalle)


def _limpiar_respuestas(respuestas: Dict[str, str]) -> Dict[str, str]:
    desconocidas = set(respuestas) - set(CLAVES_CERRADAS) - set(CLAVES_ABIERTAS)
    if desconocidas:
        raise _invalido(f"Respuestas desconocidas: {sorted(desconocidas)}")
    limpias: Dict[str, str] = {}
    for clave in CLAVES_CERRADAS:
        valor = (respuestas.get(clave) or "").strip()
        if not valor:
            raise _invalido(f"Falta la respuesta '{clave}'.")
        if len(valor) > MAX_CODIGO:
            raise _invalido(f"Respuesta '{clave}' inválida.")
        limpias[clave] = valor
    for clave in CLAVES_ABIERTAS:
        valor = (respuestas.get(clave) or "").strip()
        if valor:
            limpias[clave] = valor[:MAX_ABIERTA]
    return limpias


@router.post(
    "/lead",
    response_model=LeadResponse,
    dependencies=[Depends(_rate_limit), Depends(_tope_diario)],
)
def guardar_lead(
    request: LeadRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
) -> LeadResponse:
    """Guarda las respuestas y el contacto · devuelve el id del prospecto.

    Ese id es el que van a usar la señal preliminar (B-6) y el traspaso a la
    cuenta al registrarse (B-7). El puntaje (B-5) se calcula y se guarda aquí.
    """
    if not request.acepta_tratamiento:
        raise _invalido("Para continuar necesitamos tu autorización de tratamiento de datos.")

    contacto = request.contacto
    whatsapp = (contacto.whatsapp or "").strip() or None
    email = (contacto.email or "").strip().lower() or None
    if not whatsapp and not email:
        raise _invalido("Escribe al menos un medio de contacto: WhatsApp o correo.")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        raise _invalido("Ese correo no parece válido.")
    if contacto.cuando not in CUANDO:
        raise _invalido("Elige cuándo quieres iniciar.")

    respuestas = _limpiar_respuestas(request.respuestas)
    ya = _reenvio_reciente(db, email, whatsapp, respuestas)
    if ya is not None:
        return LeadResponse(lead_id=ya.id, siguiente_paso=SIGUIENTE_PASO[ya.route])

    # B-5 · puntaje y ruta con las reglas del demo. Es para el equipo: no
    # viaja en la respuesta, la pantalla nunca lo ve.
    veredicto = bot_gratuito_scoring.puntuar(respuestas, contacto.cuando)

    lead = BotConversation(
        name=contacto.nombre.strip(),
        email=email,
        phone=whatsapp,
        hechos={
            "_fuente": FUENTE,
            "respuestas": respuestas,
            "cuando": contacto.cuando,
            "_consentimiento": {
                "version": VERSION_CONSENTIMIENTO,
                "texto": texto_consentimiento(respuestas),
                "aceptado_en": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
        },
        # Sin conversación libre: este bot es de opciones. El transcript queda
        # vacío en vez de inventarle mensajes.
        transcript=[],
        is_completed=True,
        score=veredicto.score,
        band=veredicto.banda,
        route=veredicto.ruta,
        alarms=[],
        score_rationale=veredicto.motivos,
        utm_source=request.utm_source,
        utm_medium=request.utm_medium,
        utm_campaign=request.utm_campaign,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    # G-4 · un caliente avisa al equipo de una vez, en segundo plano: la
    # persona no espera a que salga un correo para ver su señal.
    if lead.band == "hot":
        background_tasks.add_task(aviso_prospectos.avisar_caliente_en_segundo_plano, lead.id)
    return LeadResponse(lead_id=lead.id, siguiente_paso=SIGUIENTE_PASO[veredicto.ruta])


@router.post(
    "/lead/{lead_id}/accion",
    response_model=AccionResponse,
    dependencies=[Depends(_rate_limit)],
)
def registrar_accion(
    lead_id: UUID, request: AccionRequest, db: DBSession = Depends(get_db),
) -> AccionResponse:
    """B-6 · la persona tocó el botón secundario de su señal preliminar.

    "Quiero que un counsellor me contacte", "Quiero activar mi perfilamiento" o
    "Recibir contenido útil". Se anota en el prospecto (`hechos.acciones`) para
    que el equipo lo vea en la bandeja. Repetir la misma acción no la duplica.

    Público, como el resto del bot: el id del prospecto es un UUID que solo
    conoce quien acaba de llenarlo. Solo acepta prospectos del bot gratuito y
    solo las tres acciones conocidas.
    """
    if request.accion not in SIGUIENTE_PASO.values():
        raise _invalido("Acción desconocida.")
    lead = db.query(BotConversation).filter(BotConversation.id == lead_id).first()
    if lead is None or (lead.hechos or {}).get("_fuente") != FUENTE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontramos tu registro.")

    hechos = dict(lead.hechos)
    acciones = list(hechos.get("acciones") or [])
    if not any(a.get("accion") == request.accion for a in acciones):
        acciones.append({
            "accion": request.accion,
            "en": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        })
        hechos["acciones"] = acciones
        # JSON de SQLAlchemy no detecta mutaciones internas: se reasigna entero.
        lead.hechos = hechos
        db.commit()
    return AccionResponse()


# ---------------------------------------------------------------------------
# B-7 · al crear la cuenta
# ---------------------------------------------------------------------------


class ImportarRequest(BaseModel):
    # El id que quedó en la pestaña · opcional: sin él se busca por el correo
    # de la cuenta (quien se registró en otro dispositivo).
    lead_id: Optional[UUID] = None


class ImportarResponse(BaseModel):
    importado: bool
    hechos: list


@router.post("/importar", response_model=ImportarResponse)
def importar(
    request: ImportarRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportarResponse:
    """Enlaza el prospecto del bot con la cuenta recién creada y pasa al
    onboarding lo que ya contó, para no volver a preguntárselo.

    Detalle y equivalencias en `app/services/bot_gratuito_traspaso.py`.
    """
    resultado = bot_gratuito_traspaso.traspasar(db, current_user, request.lead_id)
    return ImportarResponse(**resultado)
