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
    # La ficha del catálogo autorizado a la que pertenece · null cuando la
    # institución no tiene ficha (redes que se descompusieron en sus miembros).
    program_id: Optional[str] = None
    # Qué tan verificable es esta fila · `verificable` publica un código oficial
    # confirmable en un registro público del país; `indicativo` es lo más flojo.
    confianza: Optional[str] = None
    # El slug de esa ficha · es lo que permite el enlace de vuelta desde un
    # programa a la pagina de su institucion.
    oferta_slug: Optional[str] = None
    oferta_nombre: Optional[str] = None
    similitud: float
    afinidad: float
    puntaje: float


class FamiliaContexto(BaseModel):
    """Una familia profesional aconsejada · texto ya escrito, nada generado aquí.

    Es lo que el estudiante YA leyó en su perfil. Se devuelve otra vez para que
    la cabecera del catálogo pueda decirle por qué está viendo estos programas,
    en vez de soltarle 340 resultados sin explicación.
    """

    indice: int
    nombre: str
    calce: Optional[str] = None
    por_que_calza: Optional[str] = None
    como_es: Optional[str] = None
    oficios: List[str] = []
    ojo_con: Optional[str] = None


class Resultados(BaseModel):
    programas: List[ProgramaEncontrado]
    total_mostrado: int
    # Se dice explícitamente si el orden es semántico o alfabético. Sin esto,
    # nadie puede distinguir "no hay nada mejor" de "el proveedor de embeddings
    # estaba caído y esto salió por orden de institución".
    orden_semantico: bool
    uso_el_test: bool
    # De dónde salió el perfil que ordenó esto ("tests", "journal", "journey").
    # El estudiante puede ver que entre más usa la app, mejor le responde; y un
    # asesor puede explicar por qué salió lo que salió.
    senales: List[str] = []
    # Qué está ordenando esto · "familia" · "perfil" · "abierta".
    #
    # Los tres son estados legítimos, no un éxito y dos fallos, y la pantalla
    # tiene que poder decir en cuál está: quien todavía no hizo el test merece
    # saber que está viendo el catálogo sin ordenar, no creer que eso es lo que
    # le recomendamos.
    modo: str = "abierta"
    # La familia que ordenó estos resultados · null salvo en modo "familia".
    familia: Optional[FamiliaContexto] = None


def _filtros(user: User, perfil: bp.PerfilBusqueda, pais, area, institucion,
             incluir_no_viables: bool, program_id=None) -> bp.Filtros:
    return bp.Filtros(
        paises=[pais] if pais else (),
        areas=[area] if area else (),
        instituciones=[institucion] if institucion else (),
        program_id=program_id,
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


@router.get("/familias", response_model=List[FamiliaContexto])
def listar_familias(
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Las familias profesionales que ya le aconsejamos · el eje del catálogo.

    Devuelve lista vacía para quien todavía no tiene perfil con familias (los
    perfiles anteriores a `consolidate_v2` no las traen), y eso **no es un
    error**: la pantalla cae al recorrido país → área, que es lo que había.

    A diferencia de `/paises` y `/areas`, aquí NO se devuelve un conteo de
    programas, y la omisión es deliberada: una familia no filtra el catálogo,
    lo **ordena**. Todas tendrían el mismo número —el catálogo elegible
    entero— y ese número parecería decir algo que no dice.
    """
    from app.services import familias_programas as fam

    return [
        FamiliaContexto(indice=i, **fam.contexto_de_familia(f))
        for i, f in enumerate(fam.familias_del_usuario(db, user))
    ]


@router.get("/programas", response_model=Resultados)
async def buscar_programas(
    pais: Optional[str] = None,
    area: Optional[str] = None,
    institucion: Optional[str] = None,
    # Los programas de UNA ficha del catálogo · es lo que usa la página de una
    # institución para mostrar su oferta real en vez de mandar al estudiante a
    # buscarla otra vez en otro sitio.
    program_id: Optional[str] = None,
    # La familia profesional por la que está navegando · su posición en
    # `/busqueda/familias`. Ordena el catálogo por parecido con ESE campo en vez
    # de con el perfil entero, que es la diferencia entre "lo que te pega en
    # general" y "lo que hay de esto que te aconsejamos".
    familia: Optional[int] = Query(None, ge=0),
    limite: int = Query(20, ge=1, le=100),
    incluir_no_viables: bool = False,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paso 3 · los programas, ordenados por qué tanto le hablan a esta persona."""
    from app.services import familias_programas as fam

    perfil = bp.perfil_del_usuario(db, user)
    f = _filtros(user, perfil, pais, area, institucion, incluir_no_viables,
                 program_id=program_id)

    # El vector sale de la caché y sólo se regenera cuando el estudiante aportó
    # algo nuevo. Si el proveedor falla **se sigue sin él**: la búsqueda pierde
    # el orden semántico pero devuelve el mismo conjunto de programas elegibles.
    # Dejar a alguien sin catálogo porque una API externa no responde sería peor
    # que un orden alfabético.
    #
    # Con `familia`, el vector es el de ESA familia y reemplaza al del perfil.
    # No se promedian: el perfil ya está dentro de la familia (el modelo la
    # escribió leyéndolo), y promediar aplanaría justo lo que distingue a una
    # familia de las otras cuatro del mismo estudiante.
    elegida = fam.familia_por_indice(db, user, familia) if familia is not None else None
    vector_familia = None
    if elegida:
        vector_familia = await fam.vector_de_familia(db, user, familia,
                                                     familia=elegida)

    # `en_familia` mira el vector de la FAMILIA, no el que terminó ordenando.
    # Si el proveedor se cayó y caímos al perfil, la cabecera NO puede seguir
    # diciendo "programas de Salud y cuidado animal" sobre una lista que ya no
    # está ordenada por eso: sería una promesa que la lista no cumple.
    en_familia = vector_familia is not None

    vector = vector_familia
    if vector is None:
        # Sin familia, con un índice que ya no existe, o con el proveedor caído:
        # se cae al perfil. Nunca a una pantalla vacía.
        vector = await bp.vector_del_perfil(db, perfil, user)
        if elegida:
            logger.info("familia sin vector · se ordena por perfil",
                        extra={"user_id": str(user.id), "familia": familia})

    encontrados = bp.buscar(
        db, vector_perfil=vector, codigos_riasec=perfil.codigos_riasec,
        filtros=f, limite=limite,
        # Navegando por familia, el refuerzo RIASEC se apaga: la familia ya es
        # la señal estructurada, y el código global del estudiante le ganaba
        # —medido— metiendo medicina humana dentro de "Salud y cuidado animal".
        # `afinidad` se sigue reportando; sólo deja de pesar. Ver `bp.buscar`.
        peso_afinidad=0.0 if en_familia else bp.PESO_AFINIDAD,
    )
    return Resultados(
        programas=[ProgramaEncontrado(**vars(x)) for x in encontrados],
        total_mostrado=len(encontrados),
        orden_semantico=vector is not None,
        uso_el_test=perfil.hizo_el_test,
        senales=perfil.senales,
        modo=("familia" if en_familia
              else "perfil" if vector is not None
              else "abierta"),
        familia=(FamiliaContexto(indice=familia, **fam.contexto_de_familia(elegida))
                 if en_familia else None),
    )
