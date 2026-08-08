"""Búsqueda de programas (`/v1/busqueda`) · el recorrido país → área → programa.

Tres endpoints que son tres pasos de una misma conversación, no tres consultas
sueltas:

    GET /busqueda/paises              ¿a dónde te quieres ir?
    GET /busqueda/areas?pais=Canadá   ¿qué te gustaría estudiar allá?
    GET /busqueda/programas?...       esto es lo que hay

Cada paso **cuenta lo que hay de verdad** bajo lo ya elegido. Ofrecerle
"Agricultura y Veterinaria" a alguien que eligió Malta, donde no hay ni un
programa de eso, es un callejón sin salida con cara de opción.

El perfil no viaja por parámetro: sale del estudiante autenticado (sus tests, su
etapa de vida, lo que escribió en el journey). Un endpoint que aceptara el perfil
del cliente permitiría pedir recomendaciones "como si fuera otra persona", y
además obligaría al frontend a saber cómo se arma — que es justo la lógica que
vive aquí.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services import busqueda_programas as bp
from app.services import embeddings as emb

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/busqueda", tags=["Búsqueda"])


class PaisConteo(BaseModel):
    pais: str
    programas: int


class AreaSugerida(BaseModel):
    area: str
    programas: int
    # 0.0 cuando la persona no ha hecho el test · el frontend puede entonces
    # ordenar por cantidad y no fingir una afinidad que no existe.
    afinidad: float


class ProgramaEncontrado(BaseModel):
    id: str
    nombre: str
    institucion: str
    pais: Optional[str] = None
    ciudad: Optional[str] = None
    nivel: str
    area: Optional[str] = None
    duracion: Optional[str] = None
    codigo_oficial: Optional[str] = None
    url_fuente: Optional[str] = None
    similitud: float
    afinidad: float
    puntaje: float


class Resultados(BaseModel):
    programas: List[ProgramaEncontrado]
    total_mostrado: int
    # Se dice explícitamente si el orden es semántico o alfabético. Sin esto,
    # nadie puede distinguir "no hay nada mejor" de "el proveedor de embeddings
    # estaba caído y esto salió por orden de institución".
    orden_semantico: bool
    uso_el_test: bool


def _filtros(user: User, perfil: bp.PerfilBusqueda, pais, area, institucion,
             incluir_no_viables: bool) -> bp.Filtros:
    return bp.Filtros(
        paises=[pais] if pais else (),
        areas=[area] if area else (),
        instituciones=[institucion] if institucion else (),
        # `incluir_no_viables` existe para el panel de la agencia: un asesor sí
        # necesita poder ver el catálogo completo. Para el estudiante el valor
        # por defecto esconde lo que no puede cursar todavía.
        etapa_de_vida=None if incluir_no_viables else perfil.etapa_de_vida,
    )


@router.get("/paises", response_model=List[PaisConteo])
def listar_paises(
    incluir_no_viables: bool = False,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paso 1 · los países con oferta para esta persona, con cuántos programas."""
    perfil = bp.perfil_del_usuario(db, user)
    f = _filtros(user, perfil, None, None, None, incluir_no_viables)
    return bp.paises_disponibles(db, f)


@router.get("/areas", response_model=List[AreaSugerida])
def listar_areas(
    pais: Optional[str] = None,
    incluir_no_viables: bool = False,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paso 2 · las áreas afines al perfil, ordenadas por afinidad y con conteo."""
    perfil = bp.perfil_del_usuario(db, user)
    f = _filtros(user, perfil, pais, None, None, incluir_no_viables)
    return bp.areas_sugeridas(db, perfil.codigos_riasec, f)


@router.get("/programas", response_model=Resultados)
async def buscar_programas(
    pais: Optional[str] = None,
    area: Optional[str] = None,
    institucion: Optional[str] = None,
    limite: int = Query(20, ge=1, le=100),
    incluir_no_viables: bool = False,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paso 3 · los programas, ordenados por qué tanto le hablan a esta persona."""
    perfil = bp.perfil_del_usuario(db, user)
    f = _filtros(user, perfil, pais, area, institucion, incluir_no_viables)

    # El vector del perfil se pide al proveedor en cada búsqueda. Si falla —red,
    # cuota, caída— **se sigue sin él**: la búsqueda pierde el orden semántico
    # pero devuelve el mismo conjunto de programas elegibles. Dejar al estudiante
    # sin catálogo porque una API externa no responde sería peor que un orden
    # alfabético.
    vector = None
    texto = emb.texto_de_perfil(
        intereses=perfil.intereses,
        rutas=perfil.rutas,
        areas_afines=[area] if area else [],
        en_sus_palabras=perfil.en_sus_palabras,
    )
    if texto.strip():
        try:
            vector = await emb.embeber_uno(texto)
        except Exception:
            logger.warning(
                "búsqueda sin orden semántico · falló el embedding del perfil",
                exc_info=True, extra={"user_id": str(user.id)},
            )

    encontrados = bp.buscar(
        db, vector_perfil=vector, codigos_riasec=perfil.codigos_riasec,
        filtros=f, limite=limite,
    )
    return Resultados(
        programas=[ProgramaEncontrado(**vars(x)) for x in encontrados],
        total_mostrado=len(encontrados),
        orden_semantico=vector is not None,
        uso_el_test=perfil.hizo_el_test,
    )
