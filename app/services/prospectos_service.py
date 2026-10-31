"""Prospectos · las tres fuentes en un solo panel (G-1 / G-2, Sprint 4).

Antes había tres sitios donde caía un prospecto y el equipo comercial solo veía
uno:

- **El bot gratuito** (`/perfil`, B-4): `bot_conversations` con
  `hechos._fuente = "bot_gratuito"`. Es la entrada de la portada desde Sprint 4.
- **El perfilador conversacional** (`/perfil/conversacion`): también
  `bot_conversations`, sin esa marca.
- **El quiz viejo de la landing**: `lead_profiles`. Dejó de recibir prospectos
  cuando la portada pasó al bot gratuito, pero los que hay siguen siendo gente
  que dejó su contacto, y `rescate_lead_quiz` ya documentó que esa tabla "se
  escribe y nadie la lee". Aquí entran, como fuente "quiz".

Cada fila sale con la misma forma, para que el panel y el CSV no sepan de dónde
vino. Lo que no aplica a una fuente queda en None: el quiz no tiene puntaje, y
**no se le inventa uno**.

## El estado

`nuevo · contactado · convertido · descartado`. Se guarda solo cuando el equipo
lo cambia (migración 082). Si nunca se tocó, se deriva: "convertido" si la
persona ya creó cuenta, "nuevo" si no. Un estado puesto a mano manda sobre el
derivado: si el equipo lo descartó y después se registra, sigue descartado
hasta que alguien lo cambie, porque fue una decisión de una persona.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.api.v1.admin_planes import PREFIJO_SOLICITUD  # lo que crea "Quiero activarlo" (D-4)
from app.db.models import BotConversation, LeadProfile, User

FUENTE_BOT_GRATUITO = "bot_gratuito"
FUENTE_PERFILADOR = "perfilador"
FUENTE_QUIZ = "quiz"
FUENTES = (FUENTE_BOT_GRATUITO, FUENTE_PERFILADOR, FUENTE_QUIZ)

ESTADOS = ("nuevo", "contactado", "convertido", "descartado")

# --- etiquetas legibles · las mismas palabras que ve la persona en cada bot ---
_QUIEN_BOT = {
    "colegio": "Estudiante de colegio",
    "uni": "Universitario",
    "padre": "Papá o mamá",
    "pro": "Profesional",
}
_ETAPA_BOT = {
    "9": "9°", "10": "10°", "11": "11°", "12": "12°", "grad": "Ya terminó el colegio",
    "u1": "Primeros semestres", "u2": "Mitad de carrera", "u3": "Último año",
    "u4": "Ya se graduó de la universidad",
    "p1": "1 a 3 años de experiencia", "p2": "4 a 10 años de experiencia",
    "p3": "Más de 10 años de experiencia",
}


def _nombres_bot_gratuito() -> Dict[str, Dict[str, str]]:
    # Se reusan los del puntaje para que el panel y el "porqué" digan lo mismo.
    from app.services import bot_gratuito_scoring as s

    return {
        "destino": s._NOMBRE_DESTINO,
        "presupuesto": s._NOMBRE_PRESUPUESTO,
        "cuando": s._NOMBRE_CUANDO,
    }


def _nombres_perfilador() -> Dict[str, Dict[str, str]]:
    from app.data import perfilador_typeform as t

    return {
        "etapa": t.OCUPACION_A_LIFE_STAGE,
        "presupuesto": t.INVERSION,
        "cuando": t.CUANDO_VIAJAR,
        "paises": t.PAISES,
    }


@dataclass
class Prospecto:
    fuente: str
    id: str
    creado_en: datetime
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    quien: Optional[str] = None
    etapa: Optional[str] = None
    destino: Optional[str] = None
    presupuesto: Optional[str] = None
    cuando: Optional[str] = None
    puntaje: Optional[int] = None
    banda: Optional[str] = None
    ruta: Optional[str] = None
    porque: List[str] = field(default_factory=list)
    acciones: List[str] = field(default_factory=list)
    resumen: Optional[str] = None
    creo_cuenta: bool = False
    pidio_activar_plan: bool = False
    estado: str = "nuevo"
    estado_manual: bool = False
    hechos: Dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Las tres fuentes, a la misma forma
# ---------------------------------------------------------------------------


def _desde_bot(fila: BotConversation) -> Prospecto:
    hechos = dict(fila.hechos or {})
    if hechos.get("_fuente") == FUENTE_BOT_GRATUITO:
        r = dict(hechos.get("respuestas") or {})
        n = _nombres_bot_gratuito()
        p = Prospecto(
            fuente=FUENTE_BOT_GRATUITO,
            id=str(fila.id),
            creado_en=fila.created_at,
            quien=_QUIEN_BOT.get(r.get("who", "")),
            etapa=_ETAPA_BOT.get(r.get("stage", "")),
            destino=n["destino"].get(r.get("dest", "")),
            presupuesto=n["presupuesto"].get(r.get("budget", "")),
            cuando=n["cuando"].get(hechos.get("cuando", "")),
            acciones=[a.get("accion") for a in (hechos.get("acciones") or []) if a.get("accion")],
        )
    else:
        n = _nombres_perfilador()
        destinos = hechos.get("destino_interes") or []
        if isinstance(destinos, str):
            destinos = [destinos]
        p = Prospecto(
            fuente=FUENTE_PERFILADOR,
            id=str(fila.id),
            creado_en=fila.created_at,
            etapa=n["etapa"].get(hechos.get("ocupacion", "")),
            destino=", ".join(n["paises"].get(d, d) for d in destinos) or None,
            presupuesto=n["presupuesto"].get(hechos.get("inversion", "")),
            cuando=n["cuando"].get(hechos.get("cuando_viajar", "")),
            resumen=hechos.get("que_estudiar"),
        )
    p.nombre, p.email, p.telefono = fila.name, fila.email, fila.phone
    p.puntaje, p.banda, p.ruta = fila.score, fila.band, fila.route
    p.porque = [str(m) for m in (fila.score_rationale or [])]
    p.hechos = {k: v for k, v in hechos.items() if not str(k).startswith("_")}
    p.estado = fila.estado or "nuevo"
    p.estado_manual = fila.estado is not None
    return p


def _desde_quiz(fila: LeadProfile) -> Prospecto:
    resultado = fila.profile_result if isinstance(fila.profile_result, dict) else {}
    return Prospecto(
        fuente=FUENTE_QUIZ,
        id=str(fila.id),
        creado_en=fila.created_at,
        nombre=fila.name,
        email=fila.email,
        telefono=fila.phone,
        # El quiz no puntuaba: banda y puntaje quedan vacíos a propósito.
        resumen=str(resultado.get("profile_name") or "").strip() or None,
        hechos=dict(fila.answers or {}) if isinstance(fila.answers, dict) else {},
        creo_cuenta=bool(fila.converted),
        estado=fila.estado or "nuevo",
        estado_manual=fila.estado is not None,
    )


# ---------------------------------------------------------------------------
# Cuenta y solicitud de plan
# ---------------------------------------------------------------------------


def _cuentas(db: DBSession, filas: Iterable[BotConversation], prospectos: List[Prospecto]) -> None:
    """Marca quién ya creó cuenta y quién pidió activar el plan.

    La cuenta se busca por el enlace que deja el traspaso (B-7,
    `converted_user_id`) y, si no lo hay, por el correo: alguien que hizo el
    bot y se registró en otro dispositivo sin traer sus respuestas sigue siendo
    la misma persona para el equipo comercial.
    """
    por_id = {str(f.id): f for f in filas}
    correos = {(p.email or "").strip().lower() for p in prospectos if p.email}
    ids = {f.converted_user_id for f in por_id.values() if f.converted_user_id}
    usuarios: List[User] = []
    if correos or ids:
        q = db.query(User)
        cond = []
        if correos:
            cond.append(func.lower(User.email).in_(correos))
        if ids:
            cond.append(User.id.in_(ids))
        usuarios = q.filter(or_(*cond)).all()
    por_correo = {(u.email or "").lower(): u for u in usuarios}
    por_uid = {u.id: u for u in usuarios}

    for p in prospectos:
        fila = por_id.get(p.id)
        u = None
        if fila is not None and fila.converted_user_id:
            u = por_uid.get(fila.converted_user_id)
        if u is None and p.email:
            u = por_correo.get(p.email.strip().lower())
        if u is not None:
            p.creo_cuenta = True
            p.pidio_activar_plan = (u.gh_contact_message or "").startswith(PREFIJO_SOLICITUD)
        if p.creo_cuenta and not p.estado_manual:
            p.estado = "convertido"


# ---------------------------------------------------------------------------
# Lo público
# ---------------------------------------------------------------------------


def listar(
    db: DBSession,
    *,
    fuente: Optional[str] = None,
    banda: Optional[str] = None,
    ruta: Optional[str] = None,
    estado: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    limite: int = 200,
) -> List[Prospecto]:
    """Los prospectos de las tres fuentes, lo más nuevo arriba.

    Fecha, banda y ruta se filtran en la base; el estado, después, porque el
    "convertido" derivado depende de buscar la cuenta.
    """
    prospectos: List[Prospecto] = []
    filas_bot: List[BotConversation] = []

    if fuente in (None, FUENTE_BOT_GRATUITO, FUENTE_PERFILADOR):
        q = db.query(BotConversation)
        if desde:
            q = q.filter(BotConversation.created_at >= desde)
        if hasta:
            q = q.filter(BotConversation.created_at <= hasta)
        if banda:
            q = q.filter(BotConversation.band == banda)
        if ruta:
            q = q.filter(BotConversation.route == ruta)
        filas_bot = q.order_by(BotConversation.created_at.desc()).limit(limite * 2).all()
        for f in filas_bot:
            p = _desde_bot(f)
            if fuente is None or p.fuente == fuente:
                prospectos.append(p)

    # El quiz no tiene banda ni ruta: si se filtra por cualquiera de las dos, no entra.
    if fuente in (None, FUENTE_QUIZ) and not banda and not ruta:
        q = db.query(LeadProfile)
        if desde:
            q = q.filter(LeadProfile.created_at >= desde)
        if hasta:
            q = q.filter(LeadProfile.created_at <= hasta)
        prospectos += [_desde_quiz(f) for f in q.order_by(LeadProfile.created_at.desc()).limit(limite).all()]

    _cuentas(db, filas_bot, prospectos)
    if estado:
        prospectos = [p for p in prospectos if p.estado == estado]
    prospectos.sort(key=lambda p: p.creado_en or datetime.min, reverse=True)
    return prospectos[:limite]


class ProspectoNoEncontrado(LookupError):
    pass


def cambiar_estado(db: DBSession, *, fuente: str, prospecto_id: Any, estado: str) -> str:
    """Guarda el estado que puso el equipo. Devuelve el anterior (para auditar)."""
    if estado not in ESTADOS:
        raise ValueError(f"estado desconocido: {estado!r}")
    modelo = LeadProfile if fuente == FUENTE_QUIZ else BotConversation
    fila = db.query(modelo).filter(modelo.id == prospecto_id).first()
    if fila is None:
        raise ProspectoNoEncontrado(str(prospecto_id))
    if modelo is BotConversation:
        es_gratuito = (fila.hechos or {}).get("_fuente") == FUENTE_BOT_GRATUITO
        if (fuente == FUENTE_BOT_GRATUITO) != es_gratuito:
            raise ProspectoNoEncontrado(str(prospecto_id))
    anterior = fila.estado or "nuevo"
    fila.estado = estado
    fila.estado_actualizado_en = datetime.utcnow()
    db.commit()
    return anterior


COLUMNAS_CSV = (
    ("creado_en", "Fecha"),
    ("fuente", "Fuente"),
    ("nombre", "Nombre"),
    ("email", "Correo"),
    ("telefono", "Teléfono"),
    ("quien", "Quién"),
    ("etapa", "Etapa o grado"),
    ("destino", "Destino"),
    ("presupuesto", "Presupuesto"),
    ("cuando", "Cuándo empieza"),
    ("puntaje", "Puntaje"),
    ("banda", "Banda"),
    ("ruta", "Ruta"),
    ("porque", "Por qué"),
    ("estado", "Estado"),
    ("creo_cuenta", "Creó cuenta"),
    ("pidio_activar_plan", "Pidió activar plan"),
)


def a_filas_csv(prospectos: List[Prospecto]) -> List[List[str]]:
    filas = [[titulo for _, titulo in COLUMNAS_CSV]]
    for p in prospectos:
        d = p.a_dict()
        fila = []
        for clave, _ in COLUMNAS_CSV:
            v = d.get(clave)
            if isinstance(v, list):
                v = " · ".join(str(x) for x in v)
            elif isinstance(v, bool):
                v = "sí" if v else "no"
            elif isinstance(v, datetime):
                v = v.strftime("%Y-%m-%d %H:%M")
            fila.append("" if v is None else str(v))
        filas.append(fila)
    return filas
