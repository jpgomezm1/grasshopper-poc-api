"""Búsqueda de programas para un estudiante · filtro duro + semántica + RIASEC.

El orden de las tres capas no es un detalle de implementación, es lo que separa
una herramienta útil de una que hace daño:

1. **Filtro duro (SQL).** País, nivel académico viable para su etapa de vida.
   Son hechos binarios, no parecidos. Si esto se resolviera por similitud, el
   sistema devolvería encantado el *Practical Nursing* de Niagara —que dice
   textualmente que **no acepta aplicaciones internacionales**— porque su
   descripción se parece mucho a lo que el estudiante pidió. La auditoría del
   catálogo existió justamente para no cometer ese error.

2. **Ranking semántico (pgvector).** Ordena lo que sí es elegible por parecido
   real entre lo que la persona dijo y lo que el programa es. Aquí es donde el
   vector vale: *"me gustan los animales pero también dibujar"* no cae en
   ninguna taxonomía, y es exactamente el tipo de frase que un estudiante de 16
   años escribe.

3. **Refuerzo estructurado (RIASEC → área).** Sube lo afín al código Holland del
   test. El test es, según la propia clienta, la señal más fuerte que tenemos:
   *"el test verdaderamente va a ser el que más nos va a generar información"*.

**Por qué no sólo vectores.** Un embedding no sabe que un colombiano necesita
visa. **Por qué no sólo RIASEC.** Seis letras no distinguen entre 15.483
programas; dentro de "Artes" caben 928.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import academic_level, areas as areas_mod

logger = logging.getLogger(__name__)

# Cuántos candidatos trae la capa semántica antes de reordenar. Se piden más de
# los que se devuelven para que el refuerzo RIASEC tenga sobre qué trabajar: si
# se pidieran justo los que se muestran, reordenar no cambiaría nada.
CANDIDATOS = 120

# Peso del refuerzo estructurado frente al parecido semántico · **calibrado
# contra el catálogo real**, no elegido a ojo.
#
# Las similitudes de coseno de este catálogo se mueven entre 0.25 y 0.40, un
# rango de apenas 0.15. La afinidad RIASEC llega a 2.0, así que el peso decide si
# desempata o si manda:
#
#   0.25 → manda. "Plant Maintenance" (mantenimiento de planta industrial)
#          adelantaba a "Animal Science" para quien preguntaba por animales, y
#          "Emprendimiento para Interioristas" a "Diploma de Cocina".
#   0.10 → desempata. Ambos casos salen correctos.
#   0.00 → sobra la capa, y se nota: sin ella, "me apasiona la cocina" devuelve
#          primero "Diseño de Cocinas", que es diseño de muebles de cocina.
#
# Si cambian los textos que se embeben, hay que recalibrarlo: el número depende
# del rango de similitudes que produzcan.
PESO_AFINIDAD = 0.10

# Cuántas listas del índice IVFFlat escanea cada búsqueda. Postgres usa **1** por
# defecto, que con ~15 listas de mil vectores deja fuera el 93% del catálogo: el
# programa perfecto puede vivir en una lista que nadie mira. Diez es el
# compromiso — recorre casi todo sin perder la ventaja del índice sobre el
# escaneo secuencial.
PROBES = 10


@dataclass
class Resultado:
    id: str
    nombre: str
    institucion: str
    pais: Optional[str]
    ciudad: Optional[str]
    nivel: str
    area: Optional[str]
    duracion: Optional[str]
    codigo_oficial: Optional[str]
    url_fuente: Optional[str]
    # Trazabilidad de por qué salió · sin esto nadie puede depurar una mala
    # recomendación, ni explicarle a un asesor de dónde salió.
    similitud: float = 0.0
    afinidad: float = 0.0
    puntaje: float = 0.0


@dataclass
class Filtros:
    """Lo que restringe de verdad · todo opcional."""
    paises: Sequence[str] = field(default_factory=tuple)
    areas: Sequence[str] = field(default_factory=tuple)
    niveles: Sequence[str] = field(default_factory=tuple)
    etapa_de_vida: Optional[str] = None
    instituciones: Sequence[str] = field(default_factory=tuple)


def niveles_excluidos(etapa: Optional[str]) -> List[str]:
    """Los niveles imposibles para la etapa de vida de la persona.

    Se expresa como **exclusión** y no como lista de permitidos a propósito: la
    lista de permitidos habría que mantenerla aquí, y el día que el catálogo gane
    un nivel nuevo (como pasó con `secundaria`) quedaría fuera en silencio. Con
    la exclusión, un nivel nuevo entra solo salvo que alguien lo prohíba.

    Sale de `academic_level`, el mismo módulo que usa el recomendador, para que
    las dos vías no puedan discrepar: ofrecerle una maestría a quien está en 11°
    es justo el error que A8 vino a arreglar.
    """
    return sorted(academic_level.niveles_fuera_de_alcance(etapa))


def _where(f: Filtros) -> tuple:
    """Las condiciones duras · devuelve (sql, params)."""
    cond = ["activo = true"]
    params: dict = {}

    if f.paises:
        # `Varios destinos` son redes que operan en muchos países y cuyo programa
        # no dice en cuál. Entran siempre que se filtre por país: excluirlas
        # escondería oferta real, y afirmar que están en el país pedido sería
        # inventar. Salen marcadas y el asesor confirma.
        cond.append("(pais = ANY(:paises) OR pais = 'Varios destinos')")
        params["paises"] = list(f.paises)
    if f.areas:
        cond.append("area = ANY(:areas)")
        params["areas"] = list(f.areas)
    if f.instituciones:
        cond.append("institucion = ANY(:instituciones)")
        params["instituciones"] = list(f.instituciones)

    if f.niveles:
        cond.append("nivel = ANY(:niveles)")
        params["niveles"] = list(f.niveles)
    elif f.etapa_de_vida:
        fuera = niveles_excluidos(f.etapa_de_vida)
        if fuera:
            cond.append("NOT (nivel = ANY(:fuera))")
            params["fuera"] = fuera

    return " AND ".join(cond), params


_COLUMNAS = ("id, nombre, institucion, pais, ciudad, nivel, area, duracion, "
             "codigo_oficial, url_fuente")


def buscar(
    db: Session,
    vector_perfil: Optional[Sequence[float]] = None,
    codigos_riasec: Sequence[str] = (),
    filtros: Optional[Filtros] = None,
    limite: int = 20,
) -> List[Resultado]:
    """Programas para este estudiante, el más pertinente primero.

    `vector_perfil` es opcional a propósito: **sin él la búsqueda sigue
    funcionando**, sólo pierde el orden semántico. Que una API externa esté caída
    no puede dejar al estudiante sin catálogo — el mismo criterio que ya rige en
    el resto del producto, donde la IA cae a plantillas deterministas.
    """
    f = filtros or Filtros()
    where, params = _where(f)

    if vector_perfil:
        params["v"] = "[" + ",".join(f"{x:.6f}" for x in vector_perfil) + "]"
        params["n"] = max(CANDIDATOS, limite)
        # `SET LOCAL` sólo dura esta transacción · no cambia la configuración del
        # servidor ni afecta a las demás consultas. Si el parámetro no existe
        # (SQLite en los tests, o Postgres sin pgvector) se sigue igual: la
        # búsqueda funciona, sólo con la recuperación por defecto.
        try:
            db.execute(text(f"SET LOCAL ivfflat.probes = {int(PROBES)}"))
        except Exception:
            logger.debug("no se pudo fijar ivfflat.probes", exc_info=True)
        # `<=>` es distancia coseno en pgvector: 0 idéntico, 2 opuesto. La
        # similitud es 1 - distancia, para que "más alto es mejor" en todo el
        # resto de la función.
        sql = (
            f"SELECT {_COLUMNAS}, 1 - (embedding <=> CAST(:v AS vector)) AS sim "
            f"FROM programas_investigados "
            f"WHERE {where} AND embedding IS NOT NULL "
            f"ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"
        )
    else:
        params["n"] = max(CANDIDATOS, limite)
        sql = (
            f"SELECT {_COLUMNAS}, 0.0 AS sim FROM programas_investigados "
            f"WHERE {where} ORDER BY institucion, nombre LIMIT :n"
        )

    filas = db.execute(text(sql), params).mappings().all()

    salida: List[Resultado] = []
    for r in filas:
        afin = areas_mod.afinidad(r["area"], codigos_riasec) if r["area"] else 0.0
        sim = float(r["sim"] or 0.0)
        salida.append(Resultado(
            id=str(r["id"]), nombre=r["nombre"], institucion=r["institucion"],
            pais=r["pais"], ciudad=r["ciudad"], nivel=r["nivel"], area=r["area"],
            duracion=r["duracion"], codigo_oficial=r["codigo_oficial"],
            url_fuente=r["url_fuente"],
            similitud=round(sim, 4), afinidad=round(afin, 3),
            puntaje=round(sim + PESO_AFINIDAD * afin, 4),
        ))

    salida.sort(key=lambda x: -x.puntaje)
    return salida[:limite]


def areas_sugeridas(
    db: Session,
    codigos_riasec: Sequence[str],
    filtros: Optional[Filtros] = None,
    minimo: int = 1,
) -> List[dict]:
    """Las áreas afines al perfil, **con cuántos programas hay realmente**.

    Este es el segundo paso del recorrido que pidió JP (país → área → programa) y
    la cuenta no es cosmética: sugerirle "Agricultura y Veterinaria" a alguien
    que ya eligió Malta, donde hay cero programas de eso, es un callejón sin
    salida. Sólo se ofrecen áreas que tienen oferta bajo los filtros vigentes.
    """
    f = filtros or Filtros()
    # El área es justo lo que se está eligiendo · no puede filtrar aquí.
    f = Filtros(paises=f.paises, areas=(), niveles=f.niveles,
                etapa_de_vida=f.etapa_de_vida, instituciones=f.instituciones)
    where, params = _where(f)

    filas = db.execute(text(
        f"SELECT area, count(*) AS n FROM programas_investigados "
        f"WHERE {where} AND area IS NOT NULL GROUP BY area"
    ), params).mappings().all()

    cuenta = {r["area"]: r["n"] for r in filas if r["n"] >= minimo}
    fuera = [
        {"area": a, "programas": cuenta[a],
         "afinidad": round(areas_mod.afinidad(a, codigos_riasec), 3)}
        for a in cuenta
    ]
    # Primero lo afín; entre áreas igual de afines, la que tenga más oferta.
    fuera.sort(key=lambda x: (-x["afinidad"], -x["programas"]))
    return fuera


@dataclass
class PerfilBusqueda:
    """Lo que sabemos del estudiante y sirve para buscarle programas."""
    codigos_riasec: List[str] = field(default_factory=list)
    intereses: List[str] = field(default_factory=list)
    rutas: List[str] = field(default_factory=list)
    etapa_de_vida: Optional[str] = None
    en_sus_palabras: str = ""

    @property
    def hizo_el_test(self) -> bool:
        return bool(self.codigos_riasec)


def perfil_del_usuario(db: Session, user) -> PerfilBusqueda:
    """Arma el perfil de búsqueda desde lo que el estudiante ya dejó.

    Todo es opcional: quien no ha hecho el test igual puede buscar, sólo pierde
    el orden por afinidad. **Nada aquí lanza excepción** — que falte un dato del
    perfil no puede dejar a alguien sin catálogo.
    """
    from app.db.models import ConsolidatedProfileCache
    from app.services import recommendation_service

    p = PerfilBusqueda()

    try:
        p.etapa_de_vida = recommendation_service.etapa_de_vida(db, user)
    except Exception:  # pragma: no cover · defensivo
        logger.warning("no se pudo resolver la etapa de vida", exc_info=True)

    fila = (
        db.query(ConsolidatedProfileCache)
        .filter(ConsolidatedProfileCache.user_id == user.id)
        .first()
    )
    datos = (fila.profile_data if fila else None) or {}
    if isinstance(datos, dict):
        # Se leen los campos sueltos y no se reconstruye el `ConsolidatedProfile`
        # completo a propósito: ese schema exige `summary_narrative` de 200+
        # caracteres y tres fortalezas, y un perfil a medio hacer reventaría la
        # búsqueda entera por validación. Aquí sólo hacen falta cuatro campos.
        p.codigos_riasec = [
            (h or {}).get("code", "") for h in (datos.get("holland_codes") or [])
            if isinstance(h, dict)
        ]
        p.codigos_riasec = [c for c in p.codigos_riasec if c]
        p.intereses = [str(x) for x in (datos.get("interests") or [])]
        p.rutas = [str(x) for x in (datos.get("suggested_career_paths") or [])]
        p.en_sus_palabras = str(datos.get("summary_narrative") or "")

    return p


def paises_disponibles(db: Session, filtros: Optional[Filtros] = None) -> List[dict]:
    """Los países con oferta, con su conteo · el primer paso del recorrido."""
    f = filtros or Filtros()
    f = Filtros(paises=(), areas=f.areas, niveles=f.niveles,
                etapa_de_vida=f.etapa_de_vida)
    where, params = _where(f)
    filas = db.execute(text(
        f"SELECT pais, count(*) AS n FROM programas_investigados "
        f"WHERE {where} AND pais IS NOT NULL GROUP BY pais ORDER BY n DESC"
    ), params).mappings().all()
    return [{"pais": r["pais"], "programas": r["n"]} for r in filas]
