"""Los lugares · el eje que une los dos catálogos.

`GET /v1/lugares` devuelve, por ciudad, cuántas **instituciones autorizadas** y
cuántos **programas por confirmar** hay. Es lo que alimenta el mapa y el
agrupador de la lista de Programas.

## Por qué existe este endpoint y no se agrupa en el navegador

El front tendría que bajarse los dos catálogos enteros (2,9 MB de instituciones
más 15.483 programas) para dibujar unos cientos de puntos. Aquí se agrupa donde
están los datos y viaja sólo el resumen.

## Lo que este endpoint se toma en serio

**Decir qué se queda fuera.** 341 instituciones y 4.332 programas no tienen
ciudad registrada, y otros tantos lugares no se pudieron geocodificar. En un
mapa, todo eso simplemente no aparece — así que la respuesta trae
`sin_ubicacion` con esos conteos, y la pantalla está obligada a mostrarlo.
Es la diferencia entre "no hay nada ahí" y "esto no te lo estoy mostrando".
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.db.database import get_db
from app.db.models import Lugar, Program, ProgramaInvestigado, User
from app.services.auth_service import get_current_user
from app.services.lugares import (
    es_pais_desconocido,
    nombre_de_ciudad,
    pais_canonico,
    resolver_lugar,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lugares", tags=["Lugares"])


class LugarOut(BaseModel):
    clave: str
    ciudad: Optional[str] = None
    pais: str
    pais_iso: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    #: ciudad | region | sin_resolver | None (todavía no geocodificado)
    precision: Optional[str] = None
    instituciones: int = 0
    programas: int = 0


class SinUbicacion(BaseModel):
    """Lo que NO va a salir en el mapa · la pantalla tiene que decirlo."""

    instituciones: int = 0
    programas: int = 0
    #: Lugares con ciudad pero sin coordenadas (no geocodificados o irresolubles).
    lugares_sin_coordenadas: int = 0


class LugaresOut(BaseModel):
    lugares: List[LugarOut]
    sin_ubicacion: SinUbicacion
    #: Valores de país que no reconoce `services/lugares.py`. Debería estar
    #: siempre vacío; si aparece algo, es que llegó data nueva y hay que ampliar
    #: la tabla de equivalencias — mejor verlo aquí que perderlo en el mapa.
    paises_no_reconocidos: List[str] = []
    #: Cuántas filas llegaron al mapa por DEDUCCIÓN y no por dato directo:
    #: `recortado` = el campo traía varias ciudades y se tomó la primera ·
    #: `institucion` = se heredó de dónde queda su institución.
    #: Se expone para poder decirlo en pantalla: un lugar deducido y uno que
    #: puso la agencia no pueden verse igual.
    deducidos: Dict[str, int] = {}


@router.get("", response_model=LugaresOut, summary="Los lugares con oferta, ya cruzados")
def listar_lugares(
    pais: Optional[str] = Query(None, description="Filtra por código ISO (ej. GB)"),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acumulado: Dict[str, LugarOut] = {}
    sin_ubicacion = SinUbicacion()
    no_reconocidos: set[str] = set()
    deducidos = {"recortado": 0, "institucion": 0}

    # Dónde queda cada institución · sirve para rescatar los ~800 programas que
    # no traen ciudad pero cuya institución sí. Se arma una sola vez, con el
    # catálogo AUTORIZADO primero: es el dato que la agencia confirmó, así que
    # manda sobre el que dedujimos nosotros.
    ciudad_por_institucion: Dict[str, str] = {}
    for institucion, ciudad in (
        db.query(ProgramaInvestigado.institucion, ProgramaInvestigado.ciudad)
        .filter(ProgramaInvestigado.ciudad.isnot(None))
        .distinct()
        .all()
    ):
        if institucion and ciudad and ciudad.strip():
            ciudad_por_institucion.setdefault(institucion.strip().lower(), ciudad)
    for institucion, ciudad in (
        db.query(Program.institution, Program.city)
        .filter(Program.active == True, Program.city.isnot(None))  # noqa: E712
        .distinct()
        .all()
    ):
        if institucion and ciudad and ciudad.strip():
            ciudad_por_institucion[institucion.strip().lower()] = ciudad

    def _sumar(
        ciudad_cruda: Optional[str],
        pais_crudo: Optional[str],
        cantidad: int,
        campo: str,
        institucion: Optional[str] = None,
    ) -> None:
        if es_pais_desconocido(pais_crudo):
            no_reconocidos.add(str(pais_crudo))

        clave, origen = resolver_lugar(
            ciudad_cruda,
            pais_crudo,
            ciudad_por_institucion.get((institucion or "").strip().lower()),
        )
        if origen in deducidos:
            deducidos[origen] += cantidad

        if clave is None:
            # Sin país reconocible o sin ciudad · no puede ir al mapa, pero se
            # cuenta para poder decirlo.
            setattr(sin_ubicacion, campo, getattr(sin_ubicacion, campo) + cantidad)
            return

        p = pais_canonico(pais_crudo)
        fila = acumulado.get(clave)
        if fila is None:
            # El nombre sale de la clave (`gb:london` → London) cuando la ciudad
            # se dedujo: mostrar el campo original diría `'Madrid, Valencia,
            # Canarias'` sobre un pin que está en Madrid.
            mostrada = nombre_de_ciudad(ciudad_cruda) if origen == "exacto" else None
            fila = LugarOut(
                clave=clave,
                ciudad=mostrada or clave.split(":", 1)[1].title(),
                pais=p.nombre,
                pais_iso=p.iso,
            )
            acumulado[clave] = fila
        setattr(fila, campo, getattr(fila, campo) + cantidad)

    # --- Instituciones autorizadas ---------------------------------------
    # `order_by` no es cosmético: varias grafías caen en la misma clave
    # (`London` y `Londres` son ambas `gb:london`) y la primera en llegar es la
    # que se queda como nombre a mostrar. Sin un orden fijo, el nombre del lugar
    # cambiaría entre dos llamadas iguales.
    filas = (
        db.query(Program.city, Program.country, func.count(Program.id))
        .filter(Program.active == True)  # noqa: E712
        .group_by(Program.city, Program.country)
        .order_by(Program.city.asc(), Program.country.asc())
        .all()
    )
    for ciudad, pais_crudo, n in filas:
        _sumar(ciudad, pais_crudo, n, "instituciones")

    # --- Programas investigados ------------------------------------------
    filas = (
        db.query(
            ProgramaInvestigado.ciudad,
            ProgramaInvestigado.pais,
            func.count(ProgramaInvestigado.id),
            ProgramaInvestigado.institucion,
        )
        .group_by(
            ProgramaInvestigado.ciudad,
            ProgramaInvestigado.pais,
            ProgramaInvestigado.institucion,
        )
        .order_by(ProgramaInvestigado.ciudad.asc(), ProgramaInvestigado.pais.asc())
        .all()
    )
    for ciudad, pais_crudo, n, institucion in filas:
        _sumar(ciudad, pais_crudo, n, "programas", institucion)

    # --- Coordenadas · de la caché de geocodificación ---------------------
    if acumulado:
        for lugar in db.query(Lugar).filter(Lugar.clave.in_(list(acumulado))).all():
            fila = acumulado.get(lugar.clave)
            if fila is None:
                continue
            fila.lat = lugar.lat
            fila.lng = lugar.lng
            fila.precision = lugar.precision

    lugares = list(acumulado.values())
    if pais:
        lugares = [l for l in lugares if l.pais_iso.lower() == pais.strip().lower()]

    sin_ubicacion.lugares_sin_coordenadas = sum(
        1 for l in lugares if l.lat is None or l.lng is None
    )

    # Más oferta primero · es el orden con el que se leen tanto la lista como
    # el tamaño de los pines.
    lugares.sort(key=lambda l: (-(l.instituciones + l.programas), l.pais, l.ciudad or ""))

    if no_reconocidos:
        logger.warning("lugares · países sin equivalencia: %s", sorted(no_reconocidos))

    return LugaresOut(
        lugares=lugares,
        sin_ubicacion=sin_ubicacion,
        paises_no_reconocidos=sorted(no_reconocidos),
        deducidos=deducidos,
    )
