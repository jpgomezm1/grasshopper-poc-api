"""El kit de aplicación de 12° · E-4, Sprint 4.

El demo de Verónica pide para 12° un checklist de lo que hay que reunir para
aplicar a cada universidad. La persona agrega sus universidades (con la fecha
límite que le dio cada una) y va marcando lo que ya tiene; Mentoring le avisa
cuando una fecha se acerca (`scripts/avisar_fechas_aplicacion.py`).

## Lo que se sabe y lo que no

La lista de documentos es la que casi siempre se pide según el destino. Los
requisitos exactos y las fechas son de cada universidad y cambian cada año: por
eso la fecha la escribe la persona (no la inventamos) y cada kit lleva el aviso
de confirmarlos en la fuente oficial. Lo que depende de la universidad va
marcado "si la universidad lo pide", en vez de afirmar que siempre hace falta.

La lista vive aquí y no en la base: se corrige sin migrar, y lo único que se
guarda por aplicación son los ids de lo que ya está listo.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

COLOMBIA = "colombia"
# Mismas claves que `countries` del onboarding (`app/data/onboarding_hechos.py`), más Colombia.
PAISES = {
    COLOMBIA: "Colombia",
    "usa": "Estados Unidos",
    "canada": "Canadá",
    "spain": "España",
    "uk": "Reino Unido",
    "germany": "Alemania",
    "australia": "Australia",
    "other": "Otro país",
}

MAX_APLICACIONES = 20

AVISO = (
    "Es la lista que casi siempre se pide. Los requisitos y las fechas los pone "
    "cada universidad: confírmalos siempre en su página oficial."
)

# (id, título, a qué destinos aplica, ruta de Mentoring que ayuda o None)
#   "todos" · "colombia" · "afuera" · "usa"
DOCUMENTOS = (
    ("formulario", "Formulario de aplicación de la universidad", "todos", None),
    ("documento_identidad", "Documento de identidad", "colombia", None),
    ("pasaporte", "Pasaporte vigente", "afuera", None),
    ("notas", "Certificado de notas del colegio", "todos", None),
    ("diploma", "Diploma o acta de grado (o constancia de que cursas el último año)", "todos", None),
    ("saber_11", "Resultado del Saber 11", "colombia", None),
    ("ingles", "Puntaje del examen de inglés (IELTS o TOEFL)", "afuera", "/practica-examenes/ielts"),
    ("sat", "Puntaje del SAT, si la universidad lo pide", "usa", "/practica-examenes/sat"),
    ("carta_motivacion", "Carta de motivación o ensayo", "afuera", "/me/tools/sop"),
    ("recomendaciones", "Cartas de recomendación de tus profesores", "afuera", None),
    ("traducciones", "Traducción oficial de notas y diploma, si el país lo pide", "afuera", None),
    ("hoja_de_vida", "Hoja de vida, si la universidad la pide", "afuera", "/me/tools"),
    ("pago_inscripcion", "Pago de la inscripción", "todos", None),
)


def documentos_para(pais: str) -> List[Dict[str, Any]]:
    """Los documentos que corresponden a un destino, en orden."""
    afuera = pais != COLOMBIA
    fuera: List[Dict[str, Any]] = []
    for doc_id, titulo, para, ruta in DOCUMENTOS:
        if (
            para == "todos"
            or (para == "colombia" and not afuera)
            or (para == "afuera" and afuera)
            or (para == "usa" and pais == "usa")
        ):
            fuera.append({"id": doc_id, "titulo": titulo, "ruta": ruta})
    return fuera


def ids_validos(pais: str) -> set:
    return {d["id"] for d in documentos_para(pais)}


def serializar(a: Any, hoy: Optional[date] = None) -> Dict[str, Any]:
    hoy = hoy or date.today()
    listos = set(a.listos or [])
    docs = [{**d, "listo": d["id"] in listos} for d in documentos_para(a.pais)]
    hechos = sum(1 for d in docs if d["listo"])
    dias = (a.fecha_limite - hoy).days if a.fecha_limite else None
    return {
        "id": str(a.id),
        "universidad": a.universidad,
        "programa": a.programa,
        "pais": a.pais,
        "pais_nombre": PAISES.get(a.pais, a.pais),
        "fecha_limite": a.fecha_limite.isoformat() if a.fecha_limite else None,
        "dias_restantes": dias,
        "documentos": docs,
        "listos": hechos,
        "total": len(docs),
    }


def _orden(a: Any) -> tuple:
    # Primero las que tienen fecha, de la más urgente a la más lejana (una
    # vencida queda arriba: pide una decisión, ¿ya aplicó o la borra?). Las que
    # no tienen fecha van al final.
    return (a.fecha_limite is None, a.fecha_limite or date.max, a.creado_en)


def listar(db: Any, user: Any) -> Dict[str, Any]:
    from app.db.models import AplicacionUniversidad

    filas = db.query(AplicacionUniversidad).filter(AplicacionUniversidad.user_id == user.id).all()
    return {
        "aplicaciones": [serializar(a) for a in sorted(filas, key=_orden)],
        "paises": [{"id": k, "nombre": v} for k, v in PAISES.items()],
        "aviso": AVISO,
        "maximo": MAX_APLICACIONES,
    }
