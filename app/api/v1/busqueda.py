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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.v1.auth import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services import areas as areas_mod
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


class ProgramaDetalle(BaseModel):
    """Un programa visto de cerca · sin precio, sin requisitos, sin ranking.

    La ausencia de esos campos no es una carencia por llenar: la tabla
    `programas_investigados` no los tiene, y un detalle que los mostrara vacíos
    invitaría a estimarlos. Una familia no puede tomar una decisión de miles de
    dólares sobre un número que nadie verificó.

    Lo que sí trae es **de dónde salió cada cosa**: el enlace a la página oficial
    de la institución y el código del registro público del país cuando existe.
    Con eso el estudiante lo comprueba él mismo, que es más honesto que un dato
    nuestro sin respaldo.
    """

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
    confianza: Optional[str] = None
    #: De qué va el campo, en palabras de un chico de 16 · migración 078.
    glosa: Optional[str] = None
    #: La ficha del catálogo autorizado, si la institución tiene una.
    ficha: Optional[dict] = None
    #: Si el área le habla a los códigos RIASEC de esta persona.
    area_afin: bool = False
    #: Qué más se estudia en esta institución · ordenado por lo que le encaja.
    otros_de_la_institucion: List[ProgramaEncontrado] = []
    #: El mismo campo, en otras instituciones · "¿dónde más puedo estudiar esto?"
    donde_mas: List[ProgramaEncontrado] = []


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


class ValorDeFaceta(BaseModel):
    """Un valor de un filtro, con cuántos programas hay **de verdad** debajo.

    El conteo es *leave-one-out*: no aplica el filtro de su propia dimensión. Si
    ya elegiste Reino Unido y la lista de países contara aplicándolo, los demás
    saldrían en cero y no podrías añadir Irlanda. Ver `busqueda_programas.facetas`.
    """

    valor: Optional[str] = None
    etiqueta: str
    programas: int
    elegido: bool = False


class Facetas(BaseModel):
    pais: List[ValorDeFaceta] = []
    area: List[ValorDeFaceta] = []
    nivel: List[ValorDeFaceta] = []
    ciudad: List[ValorDeFaceta] = []


class FiltroSugerido(BaseModel):
    """Un filtro que el intérprete dedujo de lo que el estudiante escribió.

    Viaja a la pantalla **para que se vea y se pueda quitar**. Un filtro que el
    modelo aplica sin mostrarlo puede esconder 33.000 programas sin que nadie se
    entere, y eso es inaceptable aunque acierte casi siempre.

    `origen` dice quién lo puso: `"texto"` cuando salió de lo que la persona
    escribió. La pantalla lo usa para pintarlo distinto de un filtro que él
    eligió a mano — no es lo mismo "yo pedí Canadá" que "el sistema entendió
    Canadá".
    """

    tipo: str
    valor: str
    origen: str = "texto"


class Interpretacion(BaseModel):
    """Qué entendió el sistema de lo que la persona escribió."""

    entendi: str = ""
    conceptos: List[str] = []
    filtros_sugeridos: List[FiltroSugerido] = []
    #: Lo que pidió y este catálogo no tiene (precio, becas, requisitos).
    #: Es una LISTA porque puede pedir varias cosas a la vez ("cuánto cuesta y
    #: qué beca hay"). La pantalla responde con honestidad —"no tenemos precios,
    #: cambian por intake y tu asesor tiene tarifas negociadas"— en vez de
    #: devolver una lista vacía que parecería que no hay nada.
    fuera_de_alcance: List[str] = []
    interpretada: bool = False


class Pagina(BaseModel):
    programas: List[ProgramaEncontrado]
    pagina: int
    por_pagina: int
    #: El total REAL del filtro duro · no cuántos se alcanzan a ordenar.
    total: int
    total_paginas: int
    #: Hasta dónde llega el orden por pertinencia · `None` si no aplica. Permite
    #: decir "te muestro los 500 más pertinentes de 3.412" en vez de fingir.
    ranking_hasta: Optional[int] = None
    orden_semantico: bool = False
    #: `None` cuando no había nada que entender (sin texto ni vector).
    entendi_la_consulta: Optional[bool] = None
    mejor_similitud: Optional[float] = None
    facetas: Facetas = Facetas()
    interpretacion: Optional[Interpretacion] = None
    modo: str = "abierta"
    familia: Optional[FamiliaContexto] = None
    senales: List[str] = []


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


#: Corre una consulta síncrona FUERA del event loop.
#
# Los endpoints de abajo son `async` porque esperan al proveedor de embeddings,
# pero las consultas que hacen entre medias son SQLAlchemy síncrono. Ejecutarlas
# dentro de la corrutina **bloquea el event loop entero**: mientras una petición
# espera a Neon, TODAS las demás del servidor se congelan, incluidas las que no
# tienen nada que ver con la búsqueda.
#
# Medido contra `/busqueda/explorar` el 2026-09-20, antes del arreglo:
#
#     1 petición simultánea ....  2,2 s
#     2 ........................  5,3 s
#     4 ........................  7,9 s
#     8 ........................ 15,8 s
#
# Crecimiento lineal perfecto — la firma de la serialización. Con un solo dyno,
# ocho estudiantes navegando a la vez se esperaban unos a otros; y una sola
# pantalla que dispara siete llamadas se autobloqueaba. Explica por completo los
# "40-50 segundos" que reportó JP, que yo no reproducía midiendo una sola
# petición aislada.
#
# `run_in_threadpool` las manda al mismo pool que FastAPI ya usa para los
# endpoints `def`. La sesión de SQLAlchemy se sigue tocando desde un hilo a la
# vez, porque los `await` son secuenciales: no se introduce concurrencia sobre
# ella.
def _correr(corrutina):
    """Corre una corrutina desde un endpoint SÍNCRONO.

    FastAPI ejecuta los `def` en un hilo del pool, y ese hilo no tiene event
    loop propio: `asyncio.run` es lo correcto ahí. Mismo patrón que ya usaba
    `busqueda_programas.vector_del_perfil_sync` desde antes que yo llegara.
    """
    import asyncio

    return asyncio.run(corrutina)


def _lista(v: Optional[str]) -> List[str]:
    """`?pais=Canadá,España` · multi-select sin repetir el parámetro.

    Se parte por coma y no se usa `Query(list)` porque la URL queda mucho más
    corta y compartible, y estas URLs se comparten: el estudiante le manda a su
    mamá el enlace de lo que encontró.
    """
    return [x.strip() for x in (v or "").split(",") if x.strip()]


@router.get("/explorar", response_model=Pagina)
def explorar(
    q: Optional[str] = Query(None, max_length=200,
                             description="Lo que el estudiante escribió, con sus palabras"),
    pais: Optional[str] = None,
    area: Optional[str] = None,
    nivel: Optional[str] = None,
    ciudad: Optional[str] = None,
    institucion: Optional[str] = None,
    familia: Optional[int] = Query(None, ge=0),
    pagina: int = Query(1, ge=1, le=200),
    por_pagina: int = Query(24, ge=1, le=60),
    orden: str = Query("relevancia", pattern="^(relevancia|nombre)$"),
    incluir_no_viables: bool = False,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """El catálogo completo, navegable · texto libre + facetas + paginación.

    ## Por qué existe además de `/programas`

    `/programas` es el recorrido guiado de tres pasos (país → área → programa) y
    devuelve una lista corta sin paginar. Sirve para el paseo, no para buscar:
    con 33.552 programas, alguien que sabe lo que quiere necesita escribirlo.

    El motor para eso ya estaba construido, medido y probado —`buscar_con_texto`,
    `facetas`, `buscar_pagina`, el intérprete con su set de 20 consultas— y
    **no tenía un solo consumidor**. Esto lo conecta. El endpoint viejo se queda
    intacto: lo usan `ProgramasDeLaInstitucion` y el recorrido guiado.

    ## Las tres reglas que no se negocian

    1. **El filtro duro lo decide SQL, nunca el modelo.** Lo que el intérprete
       deduce viaja como sugerencia visible y removible.
    2. **El total es el total real**, no cuántos se alcanzan a ordenar. Por eso
       `ranking_hasta` va aparte.
    3. **Lo que no se sabe se cuenta**: un programa sin ciudad cae en su propio
       bucket con etiqueta, no desaparece.
    """
    from app.services import familias_programas as fam

    perfil = bp.perfil_del_usuario(db, user)

    elegida = fam.familia_por_indice(db, user, familia) if familia is not None else None
    vector_familia = None
    if elegida:
        vector_familia = fam.vector_de_familia_sync(db, user, familia, familia=elegida)
    en_familia = vector_familia is not None
    vector = vector_familia or bp.vector_del_perfil_sync(db, perfil, user)

    f = bp.Filtros(
        paises=_lista(pais), areas=_lista(area), niveles=_lista(nivel),
        ciudades=_lista(ciudad), instituciones=_lista(institucion),
        etapa_de_vida=None if incluir_no_viables else perfil.etapa_de_vida,
    )

    # Dentro de una familia el refuerzo RIASEC se apaga · ver `bp.buscar`.
    peso = 0.0 if en_familia else bp.PESO_AFINIDAD

    if (q or "").strip():
        datos = _correr(bp.buscar_con_texto(
            db, q, vector_perfil=vector, codigos_riasec=perfil.codigos_riasec,
            filtros=f, pagina=pagina, por_pagina=por_pagina,
        ))
    else:
        datos = bp.buscar_pagina(
            db, vector_perfil=vector, codigos_riasec=perfil.codigos_riasec,
            filtros=f, pagina=pagina, por_pagina=por_pagina, orden=orden,
            peso_afinidad=peso,
        )

    # Los filtros que el intérprete dedujo se aplican a las FACETAS también, si
    # no los conteos no corresponderían con la lista que se está viendo.
    interp = datos.get("interpretacion")
    return Pagina(
        programas=[ProgramaEncontrado(**vars(x)) for x in datos["programas"]],
        pagina=datos["pagina"], por_pagina=datos["por_pagina"],
        total=datos["total"], total_paginas=datos["total_paginas"],
        ranking_hasta=datos.get("ranking_hasta"),
        orden_semantico=datos.get("orden_semantico", False),
        entendi_la_consulta=datos.get("entendi_la_consulta"),
        mejor_similitud=datos.get("mejor_similitud"),
        facetas=Facetas(**bp.facetas(db, f)),
        interpretacion=Interpretacion(
            entendi=interp.get("entendi") or "",
            conceptos=[str(c) for c in (interp.get("conceptos") or [])],
            filtros_sugeridos=[
                FiltroSugerido(**x) for x in (interp.get("filtros_sugeridos") or [])
                if isinstance(x, dict) and x.get("tipo") and x.get("valor")
            ],
            fuera_de_alcance=[str(x) for x in (interp.get("fuera_de_alcance") or [])],
            interpretada=bool(interp.get("interpretada")),
        ) if interp else None,
        modo=("familia" if en_familia else "perfil" if vector else "abierta"),
        familia=(FamiliaContexto(indice=familia, **fam.contexto_de_familia(elegida))
                 if en_familia else None),
        senales=perfil.senales,
    )


@router.get("/programa/{programa_id}", response_model=ProgramaDetalle)
def detalle_de_programa(
    programa_id: str,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Un programa, con lo que de verdad sabemos de él.

    ## Lo que NO trae, y es deliberado

    Ni precio, ni requisitos de admisión, ni ranking. `programas_investigados`
    no tiene esas columnas y la ausencia **es la garantía**: un detalle que los
    mostrara vacíos invitaría a rellenarlos con estimaciones, y una familia
    tomaría una decisión de miles de dólares sobre un número que nadie verificó.

    Lo que sí trae es de dónde salió cada cosa: el enlace a la página oficial de
    la institución, el código en el registro público del país cuando existe, y
    qué tan verificable es la fila. Con eso el estudiante puede comprobarlo él
    mismo, que es más honesto que un dato nuestro sin respaldo.
    """
    from app.db.models import ProgramaInvestigado

    try:
        fila = db.query(ProgramaInvestigado).filter(
            ProgramaInvestigado.id == programa_id).first()
    except Exception:
        fila = None
    if fila is None or not fila.activo:
        raise HTTPException(status_code=404, detail="Ese programa no está disponible.")

    ficha = None
    if fila.program_id:
        from app.db.models import Program

        p = db.query(Program).filter(Program.id == fila.program_id).first()
        if p is not None:
            # `Program` NO tiene `website` · el enlace de vuelta es el slug de
            # su página dentro del producto, no un sitio externo.
            ficha = {"slug": p.slug, "nombre": p.name, "pais": p.country,
                     "ciudad": p.city}

    perfil = bp.perfil_del_usuario(db, user)

    # Las dos preguntas que siguen a "me gusta este programa". Los datos ya
    # estaban en la base; lo único que faltaba era preguntárselos. Cada bloque
    # cae solo si falla: un detalle sin vecinos sigue siendo un detalle.
    try:
        otros = bp.otros_de_la_institucion(
            db, str(fila.id), fila.institucion, perfil.codigos_riasec)
    except Exception:
        logger.warning("no se pudo listar el resto de la institución", exc_info=True)
        otros = []
    try:
        donde_mas = bp.donde_mas_esta(db, str(fila.id), fila.institucion)
    except Exception:
        logger.warning("no se pudo buscar dónde más está este programa", exc_info=True)
        donde_mas = []

    return ProgramaDetalle(
        id=str(fila.id), nombre=fila.nombre, institucion=fila.institucion,
        pais=fila.pais, ciudad=fila.ciudad, nivel=fila.nivel, area=fila.area,
        duracion=fila.duracion, codigo_oficial=fila.codigo_oficial,
        url_fuente=fila.url_fuente, confianza=fila.confianza,
        # La glosa es la frase que explica de qué va el campo en palabras de un
        # chico de 16 · se generó para el vector y sirve igual para leerla.
        glosa=(fila.glosa if (fila.glosa or "") != "(sin glosa)" else None),
        ficha=ficha,
        area_afin=bool(fila.area and perfil.codigos_riasec
                       and areas_mod.afinidad(fila.area, perfil.codigos_riasec) > 0),
        otros_de_la_institucion=[ProgramaEncontrado(**vars(x)) for x in otros],
        donde_mas=[ProgramaEncontrado(**vars(x)) for x in donde_mas],
    )


@router.get("/programas", response_model=Resultados)
def buscar_programas(
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
        vector_familia = fam.vector_de_familia_sync(db, user, familia,
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
        vector = bp.vector_del_perfil_sync(db, perfil, user)
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
