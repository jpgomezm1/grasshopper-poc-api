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
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import academic_level, areas as areas_mod, lugares

logger = logging.getLogger(__name__)

# Cuántos candidatos trae la capa semántica antes de reordenar. Se piden más de
# los que se devuelven para que el refuerzo RIASEC tenga sobre qué trabajar: si
# se pidieran justo los que se muestran, reordenar no cambiaría nada.
CANDIDATOS = 120

# Cuántos candidatos se traen cuando hay que paginar por relevancia.
#
# `CANDIDATOS` alcanza para devolver una sola página, pero no para paginar: la
# página 3 necesitaría 360 candidatos, y como el reordenamiento ocurre en Python
# sobre lo que trajo pgvector, pedir más candidatos **cambia el orden de las
# páginas anteriores**. Se fija una ventana y se pagina dentro de ella.
#
# 500 no es un número redondo elegido a ojo: con 24 resultados por página son 21
# páginas, muy por encima de lo que nadie recorre, y el coste de traerlos es una
# sola consulta. Lo importante no es el número sino **decirlo**: la respuesta
# lleva `ranking_hasta` y el total real del filtro, para que la pantalla pueda
# escribir "te muestro los 500 que más te hablan de 3.412" en vez de fingir que
# hay 3.412 ordenados por pertinencia.
VENTANA_RANKING = 500

# Por debajo de esta similitud, el sistema NO entendió la consulta.
#
# No es una intuición: las consultas que resuelve bien y las que no **no se
# solapan**, y el hueco se mide con `scripts/evaluar_busqueda.py --umbral`.
# Medido el 2026-09-14, con el catálogo completo, índice HNSW y las glosas:
#
#     resuelve bien ..... 0.439 – 0.661   ("psicología clínica", "ser enfermera",
#                                          "no sé qué quiero estudiar")
#     no entiende ....... 0.240 – 0.355   ("no quiero estar en una oficina",
#                                          "hola", ruido)
#
# 0.40 va en medio del hueco: lo más lejos posible de equivocarse en cualquiera
# de las dos direcciones.
#
# Ojo con un error que ya se cometió al calibrarlo. La primera medición dio 0.47
# porque el índice HNSW devolvía cero filas para las consultas vagas —ver
# `EF_SEARCH`— y "no sé qué quiero estudiar" contaba como fallo. Arreglado el
# índice, esa consulta devuelve `Exploratory/Undecided Program`, que es la
# respuesta correcta. **El umbral se calibra contra la calidad de la respuesta,
# no contra el puntaje**: mover casos de lado para ensanchar el hueco es
# exactamente la trampa que el set de evaluación existe para evitar.
#
# **Esto no filtra nada.** Los resultados se devuelven igual; lo que cambia es
# que la respuesta dice que no está segura, para que la pantalla pueda preguntar
# en vez de presentar un resultado dudoso con cara de certeza. Enterrar lo que
# cae por debajo sería peor: "no sé qué quiero estudiar" es una frase legítima de
# alguien de 16 años y merece una conversación, no una lista vacía.
#
# Hay que re-medirlo cada vez que cambie lo que se embebe: antes de las glosas
# el corte limpio estaba en 0.45.
UMBRAL_CONFIANZA = 0.40

# Peso del refuerzo estructurado frente al parecido semántico · **calibrado
# contra el catálogo real**, no elegido a ojo.
#
# ## Cómo se eligió (catálogo de 15.483, sólo 5.086 embebidos)
#
# Las similitudes se movían entre 0.25 y 0.40, un rango de apenas 0.15. La
# afinidad RIASEC llega a 2.0, así que el peso decidía si desempata o si manda:
#
#   0.25 → manda. "Plant Maintenance" (mantenimiento de planta industrial)
#          adelantaba a "Animal Science" para quien preguntaba por animales, y
#          "Emprendimiento para Interioristas" a "Diploma de Cocina".
#   0.10 → desempata. Ambos casos salen correctos.
#   0.00 → sobra la capa, y se nota: sin ella, "me apasiona la cocina" devuelve
#          primero "Diseño de Cocinas", que es diseño de muebles de cocina.
#
# ## Qué cambió (2026-09-14 · catálogo de 33.552, el 100% embebido)
#
# Este comentario avisaba de que el número depende del corpus, y el corpus se
# duplicó. Medido con `scripts/evaluar_busqueda.py` sobre el catálogo completo:
#
#   * **El rango de similitudes pasó de 0.15 a 0.355** (0.28–0.635). O sea que
#     0.10 pesa hoy, en términos relativos, menos de la mitad de lo que pesaba.
#   * **Y aun así ya no cambia nada.** Con los dos casos que justificaron el
#     valor —animales+dibujar, cocina— el top-3 es **idéntico** con 0.00, 0.10,
#     0.24 y 0.40. Con el catálogo denso, los primeros resultados de una
#     consulta temática ya son todos del área afín: el refuerzo no tiene qué
#     reordenar.
#
# No se cambia el número, y es deliberado: subirlo "para compensar el rango"
# sería adivinar. El refuerzo sigue teniendo sentido donde de verdad se usa —el
# vector difuso del PERFIL, no una consulta temática— y ese caso las 20
# consultas del set de evaluación no lo cubren. Para recalibrarlo con evidencia
# haría falta un set construido con vectores de perfil reales.
PESO_AFINIDAD = 0.10

# Cuántas listas del índice IVFFlat escanea cada búsqueda. Postgres usa **1** por
# defecto, que con ~15 listas de mil vectores deja fuera el 93% del catálogo: el
# programa perfecto puede vivir en una lista que nadie mira. Diez es el
# compromiso — recorre casi todo sin perder la ventaja del índice sobre el
# escaneo secuencial.
#
# ⚠️ **Desde 2026-09-14 el índice es HNSW, no IVFFlat, y esto ya no se usa.**
# Se conserva junto al `SET LOCAL` que lo aplica porque ese `SET` está dentro de
# un `try/except`: si la base volviera a tener un índice IVFFlat, el parámetro
# vuelve a hacer falta y el valor ya está razonado.
#
# El cambio no fue por velocidad. IVFFlat calcula sus centroides al construirse,
# así que **caduca cada vez que el catálogo crece** —uno calculado sobre 5.086
# vectores no representa a 33.552— y se degrada en silencio: sigue devolviendo
# resultados, sólo que peores. Es la misma clase de fallo que el
# `embedding IS NOT NULL` que escondía el 86% del catálogo. HNSW es incremental
# y su parámetro de búsqueda no depende del número de filas.
PROBES = 10

# Cuántos candidatos explora HNSW antes de quedarse con los mejores. Postgres
# usa 40 por defecto, y 40 es poco aquí por una razón que no es obvia:
#
# **HNSW post-filtra.** Saca `ef_search` candidatos del índice y recién después
# aplica el `WHERE`. Si el filtro descarta la mayoría de esos candidatos, el
# resultado sale corto o vacío — sin error, sin aviso. Medido antes del índice
# parcial: una búsqueda sin filtro devolvía **9 programas de 33.552**, porque las
# filas ocultas se llevaban los candidatos.
#
# El índice parcial (`WHERE activo`) resuelve el caso grande; esto cubre el
# resto, porque los filtros de país, área y nivel siguen post-filtrando. 200 es
# el compromiso: suficiente para que un filtro estrecho no vacíe la página, y
# muy por debajo del punto donde deja de compensar frente al escaneo.
#
# Se pide `CANDIDATOS`(120) o `VENTANA_RANKING`(500) según el caso, así que este
# número tiene que ser del mismo orden o el índice devuelve menos de lo pedido.
EF_SEARCH = 200


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
    # La ficha del catálogo a la que pertenece · con esto el estudiante puede
    # saltar del programa a la institución sin buscarla a mano.
    program_id: Optional[str] = None
    # `verificable` | `publicado` | `indicativo` · ver migración 062.
    #
    # **No entra en el puntaje**, y es deliberado: bajar lo `indicativo`
    # enterraría un tercio del catálogo por una corazonada, y hoy no hay forma
    # de medir si eso mejora o empeora la recomendación. Se muestra para que
    # quien decide sepa sobre qué está decidiendo. Cuando exista el set de
    # evaluación se podrá probar si ponderarlo ayuda de verdad.
    confianza: Optional[str] = None
    oferta_slug: Optional[str] = None
    oferta_nombre: Optional[str] = None
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
    # La ficha del catálogo autorizado · es lo que permite que la página de una
    # institución muestre SUS programas en vez de repetir el catálogo entero.
    program_id: Optional[str] = None
    # Para el panel de la agencia: poder ver sólo lo confirmable en un registro
    # público. Al estudiante no se le filtra — se le marca.
    confianzas: Sequence[str] = field(default_factory=tuple)
    ciudades: Sequence[str] = field(default_factory=tuple)
    # Sólo lo que la agencia tiene autorizado vender en esa institución, según
    # `institutions_catalog.niveles_autorizados`.
    #
    # La migración 075 creó ese campo **para esta búsqueda** —su propio texto
    # dice que existe para "que la búsqueda de programas sepa que la maestría de
    # esa universidad NO se puede vender"— y hasta hoy nadie lo consultaba. Es
    # el error nº1 del `CLAUDE.md`: un campo que se escribe y nadie lee.
    #
    # Va apagado por defecto y es del asesor, no del estudiante. Encendido
    # esconde oferta real que quizá sí se puede tramitar por otra vía, y esa es
    # una decisión comercial que toma quien conoce el contrato, no el producto.
    solo_vendible: bool = False


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


def _sql_autorizan_este_nivel() -> str:
    """`CASE` que, para el nivel de cada programa, da qué autorizaciones lo cubren.

    Los dos catálogos hablan vocabularios distintos y eso no es un descuido: la
    ficha dice lo que la agencia **vende** (`pregrado`, `posgrado`, `idiomas`,
    `pathway`) y el programa dice lo que la institución **ofrece** (`bachelor`,
    `maestria`, `curso_corto`). El puente ya existe y vive en el importador —
    `NIVEL_AUTORIZADO_A_INVESTIGADO`— así que se invierte aquí en vez de
    escribirlo otra vez: duplicarlo garantizaría que un día discrepen.

    Se genera SQL y no se pasa como parámetro porque la respuesta depende de la
    fila (`pi.nivel`), no de la consulta.
    """
    from scripts.import_catalogo_autorizado import (  # noqa: E402
        NIVEL_AUTORIZADO_A_INVESTIGADO,
    )

    inverso: dict = {}
    for autorizado, investigados in NIVEL_AUTORIZADO_A_INVESTIGADO.items():
        for nivel in investigados:
            inverso.setdefault(nivel, []).append(autorizado)

    ramas = []
    for nivel, autorizados in sorted(inverso.items()):
        lista = ", ".join(f"'{a}'" for a in sorted(autorizados))
        ramas.append(f"WHEN '{nivel}' THEN ARRAY[{lista}]")
    # Un nivel que no esté en el puente no lo autoriza nada: es más seguro
    # esconderlo del filtro "solo vendible" que asumir que se puede vender.
    return "(CASE pi.nivel " + " ".join(ramas) + " ELSE ARRAY[]::text[] END)"


_SQL_AUTORIZAN_ESTE_NIVEL = _sql_autorizan_este_nivel()


def _where(f: Filtros) -> tuple:
    """Las condiciones duras · devuelve (sql, params)."""
    cond = ["pi.activo = true"]
    params: dict = {}

    if f.paises:
        # `Varios destinos` son redes que operan en muchos países y cuyo programa
        # no dice en cuál. Entran siempre que se filtre por país: excluirlas
        # escondería oferta real, y afirmar que están en el país pedido sería
        # inventar. Salen marcadas y el asesor confirma.
        cond.append("(pi.pais = ANY(:paises) OR pi.pais = 'Varios destinos')")
        params["paises"] = list(f.paises)
    if f.areas:
        cond.append("pi.area = ANY(:areas)")
        params["areas"] = list(f.areas)
    if f.instituciones:
        cond.append("pi.institucion = ANY(:instituciones)")
        params["instituciones"] = list(f.instituciones)
    if f.confianzas:
        cond.append("pi.confianza = ANY(:confianzas)")
        params["confianzas"] = list(f.confianzas)
    if f.ciudades:
        cond.append("pi.ciudad = ANY(:ciudades)")
        params["ciudades"] = list(f.ciudades)
    if f.solo_vendible:
        # El cruce con la ficha es por NOMBRE y no por `program_id`: 708
        # programas no cuelgan de ninguna ficha, y con un join por id se
        # esconderían aunque su institución sí esté autorizada. El nombre es lo
        # que usan los scripts del catálogo para lo mismo.
        #
        # `niveles_autorizados` vacío o nulo **no autoriza nada**, igual que en
        # el cargador: el Excel no dice qué se puede vender ahí, y eso es un dato
        # que falta, no un permiso. Y `sin_oferta_vendible` marca las fichas que
        # se investigaron y no tienen nada colocable (Guildford no acepta
        # solicitudes internacionales, Aspasia sólo da formación subvencionada).
        cond.append(
            "EXISTS (SELECT 1 FROM institutions_catalog ic "
            "         WHERE lower(ic.name) = lower(pi.institucion) "
            "           AND ic.active "
            "           AND ic.sin_oferta_vendible IS NULL "
            "           AND ic.niveles_autorizados IS NOT NULL "
            "           AND (ic.niveles_autorizados::jsonb @> '\"todos\"'::jsonb "
            f"                OR ic.niveles_autorizados::jsonb ?| {_SQL_AUTORIZAN_ESTE_NIVEL}))"
        )
    if f.program_id:
        # `CAST` explícito: la columna es UUID y el parámetro llega como texto.
        # Sin el casteo Postgres responde `operator does not exist: uuid = text`
        # — ya pasó una vez con los ids del catálogo, y como la excepción se
        # capturaba, el filtro fallaba en silencio.
        cond.append("pi.program_id = CAST(:program_id AS uuid)")
        params["program_id"] = str(f.program_id)

    if f.niveles:
        cond.append("pi.nivel = ANY(:niveles)")
        params["niveles"] = list(f.niveles)
    elif f.etapa_de_vida:
        fuera = niveles_excluidos(f.etapa_de_vida)
        if fuera:
            cond.append("NOT (pi.nivel = ANY(:fuera))")
            params["fuera"] = fuera

    return " AND ".join(cond), params


# Se leen con prefijo `pi.` porque la consulta une con `programs` para traer el
# slug de la ficha: sin el slug, el estudiante puede ver que un programa
# pertenece a una institución pero no puede llegar a ella — que es justo la
# relación que faltaba entre los dos catálogos.
_COLUMNAS = ("pi.id, pi.nombre, pi.institucion, pi.pais, pi.ciudad, pi.nivel, "
             "pi.area, pi.duracion, pi.codigo_oficial, pi.url_fuente, "
             "pi.program_id, pi.confianza, p.slug AS oferta_slug, p.name AS oferta_nombre")

# `LEFT JOIN` y no `JOIN`: 708 programas no cuelgan de ninguna ficha y deben
# seguir siendo visibles · un JOIN normal los borraría del catálogo en silencio.
_DESDE = ("programas_investigados pi "
          "LEFT JOIN programs p ON p.id = pi.program_id AND p.active")


def _a_resultado(r, codigos_riasec: Sequence[str],
                 peso_afinidad: float = PESO_AFINIDAD) -> Resultado:
    """Una fila de Postgres a `Resultado`, con su puntaje.

    Está extraída porque la usan las dos vías —el ranking semántico y el listado
    paginado— y tenerla duplicada era la forma segura de que un día el puntaje
    se calculara distinto según por dónde entrara la consulta.

    `peso_afinidad` se puede bajar a 0 para **no aplicar** el refuerzo RIASEC
    sin dejar de reportarlo: `afinidad` sigue viajando al frontend, que es la
    trazabilidad que un asesor necesita para explicar un resultado. Lo usa la
    navegación por familia · ver `buscar`.
    """
    afin = areas_mod.afinidad(r["area"], codigos_riasec) if r["area"] else 0.0
    sim = float(r["sim"] or 0.0)
    return Resultado(
        id=str(r["id"]), nombre=r["nombre"], institucion=r["institucion"],
        pais=r["pais"], ciudad=r["ciudad"], nivel=r["nivel"], area=r["area"],
        duracion=r["duracion"], codigo_oficial=r["codigo_oficial"],
        url_fuente=r["url_fuente"],
        program_id=str(r["program_id"]) if r["program_id"] else None,
        confianza=r["confianza"],
        oferta_slug=r["oferta_slug"], oferta_nombre=r["oferta_nombre"],
        similitud=round(sim, 4), afinidad=round(afin, 3),
        puntaje=round(sim + peso_afinidad * afin, 4),
    )


def buscar(
    db: Session,
    vector_perfil: Optional[Sequence[float]] = None,
    codigos_riasec: Sequence[str] = (),
    filtros: Optional[Filtros] = None,
    limite: int = 20,
    peso_afinidad: float = PESO_AFINIDAD,
) -> List[Resultado]:
    """Programas para este estudiante, el más pertinente primero.

    `vector_perfil` es opcional a propósito: **sin él la búsqueda sigue
    funcionando**, sólo pierde el orden semántico. Que una API externa esté caída
    no puede dejar al estudiante sin catálogo — el mismo criterio que ya rige en
    el resto del producto, donde la IA cae a plantillas deterministas.

    ## `peso_afinidad = 0` · cuando el vector YA es la señal estructurada

    El refuerzo RIASEC existe para desempatar cuando las similitudes vienen
    aplastadas en un rango de 0.15 (ver `PESO_AFINIDAD`). Navegando por una
    familia profesional no se cumple ninguna de las dos cosas: las similitudes
    se abren (0.51–0.63 medido) y la familia ya es una señal estructurada
    fuerte. Aplicar encima el RIASEC global **cuenta dos veces a la persona y
    le gana a la familia que ella eligió**. Medido el 2026-09-19 sobre la
    familia "Salud y cuidado animal" de un perfil Social-dominante:

        con refuerzo ... Animal and Veterinary Science · Veterinary Medicine ·
                         Veterinary Technology · **Care, Health and Society** ·
                         **BSc/MD Dual Degree** · **Medicine Academy**
        sin refuerzo ... Animal and Veterinary Science · Veterinary Medicine ·
                         Veterinary Medical Assistant · Veterinary Assistant ·
                         Veterinary Technology · Pre-Veterinary Medicine

    Tres de los seis primeros se volvían medicina HUMANA dentro de la familia
    ANIMAL, porque el código Social del estudiante premia el área "Salud y
    Medicina" (3ª de su lista) por encima de "Agricultura y Veterinaria", que
    sólo es afín al código Realista y por tanto puntúa 0. Y es peor en las
    familias marcadas "a explorar", que existen justamente para mirar fuera del
    código dominante: reforzar por ese código empuja en contra de su propósito.

    `afinidad` se sigue reportando · sólo deja de pesar.
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
            db.execute(text(f"SET LOCAL hnsw.ef_search = {int(EF_SEARCH)}"))
        except Exception:
            logger.debug("no se pudo fijar el parametro del indice", exc_info=True)
        # `<=>` es distancia coseno en pgvector: 0 idéntico, 2 opuesto. La
        # similitud es 1 - distancia, para que "más alto es mejor" en todo el
        # resto de la función.
        sql = (
            f"SELECT {_COLUMNAS}, 1 - (pi.embedding <=> CAST(:v AS vector)) AS sim "
            f"FROM {_DESDE} "
            f"WHERE {where} AND pi.embedding IS NOT NULL "
            f"ORDER BY pi.embedding <=> CAST(:v AS vector) LIMIT :n"
        )
    else:
        params["n"] = max(CANDIDATOS, limite)
        sql = (
            f"SELECT {_COLUMNAS}, 0.0 AS sim FROM {_DESDE} "
            f"WHERE {where} ORDER BY pi.institucion, pi.nombre LIMIT :n"
        )

    filas = list(db.execute(text(sql), params).mappings().all())

    # ── Los que todavía no tienen vector no desaparecen ─────────────────────
    #
    # La rama semántica exige `pi.embedding IS NOT NULL`, y eso tenía un efecto
    # que nadie había medido: con el catálogo a 33.907 programas y sólo 5.086
    # embebidos, **un estudiante que hizo el test veía el 14% del catálogo y uno
    # que no hizo nada veía el 100%** (esta función, rama `else`). Entre más
    # señal daba la persona, más pequeño se le volvía el catálogo, en silencio.
    #
    # El backfill arregla la causa, pero el filtro seguiría siendo una trampa:
    # cualquier tanda de extracción nueva vuelve a dejar filas sin vector
    # durante horas o días. Así que se rellena: lo que no se pudo ordenar por
    # parecido entra igual, con `similitud = 0`, y queda **detrás** de todo lo
    # que sí se pudo ordenar. Se degrada por fila, no por catálogo.
    if vector_perfil and len(filas) < params["n"]:
        faltan = params["n"] - len(filas)
        sin_vector = db.execute(
            text(f"SELECT {_COLUMNAS}, 0.0 AS sim FROM {_DESDE} "
                 f"WHERE {where} AND pi.embedding IS NULL "
                 f"ORDER BY pi.institucion, pi.nombre LIMIT :faltan"),
            {**params, "faltan": faltan},
        ).mappings().all()
        filas.extend(sin_vector)

    salida = [_a_resultado(r, codigos_riasec, peso_afinidad) for r in filas]
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
    # El área es justo lo que se está eligiendo · no puede filtrar aquí.
    #
    # Se usa `replace` y no se reconstruye campo por campo: la versión anterior
    # enumeraba cinco campos y **descartaba en silencio** los demás, así que al
    # añadir `ciudades`, `confianzas` o `solo_vendible` los conteos habrían
    # dejado de respetarlos sin que nada fallara. Con `replace`, un campo nuevo
    # se hereda solo.
    f = replace(filtros or Filtros(), areas=())
    where, params = _where(f)

    filas = db.execute(text(
        f"SELECT pi.area AS area, count(*) AS n FROM programas_investigados pi "
        f"WHERE {where} AND pi.area IS NOT NULL GROUP BY pi.area"
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


# Cuántas anotaciones del journal entran al perfil, de la más reciente hacia
# atrás. El journal crece sin techo y las primeras entradas de alguien que lleva
# meses ya no lo describen: metidas todas, el perfil se vuelve un promedio de
# quien fue, no de quien es.
JOURNAL_RECIENTES = 15

# Los tipos de anotación que dicen algo sobre QUÉ quiere estudiar. `constraint`
# ("no quiero irme lejos de mi familia") y `decision` describen el marco del
# viaje, no el campo de estudio, y meterlas empuja la búsqueda hacia programas
# que hablan de familia o de plazos.
JOURNAL_UTILES = ("interest", "reflection", "manual")


@dataclass
class PerfilBusqueda:
    """Lo que sabemos del estudiante y sirve para buscarle programas.

    Crece con el uso: los tests aportan los códigos RIASEC, el journey aporta lo
    que la persona escribió, el journal aporta lo que fue anotando, y lo que
    guardó aporta preferencia revelada. Cada señal nueva mejora la búsqueda sin
    que nadie tenga que rellenar un formulario.
    """
    codigos_riasec: List[str] = field(default_factory=list)
    intereses: List[str] = field(default_factory=list)
    rutas: List[str] = field(default_factory=list)
    etapa_de_vida: Optional[str] = None
    en_sus_palabras: str = ""
    # De dónde salió cada cosa · para poder explicarle a un asesor por qué el
    # sistema recomendó lo que recomendó.
    senales: List[str] = field(default_factory=list)

    @property
    def hizo_el_test(self) -> bool:
        return bool(self.codigos_riasec)

    @property
    def firma(self) -> str:
        """Huella de las señales · cambia sólo si cambió algo que afecta la
        búsqueda. Es lo que permite cachear el vector sin quedarse pegado a un
        perfil viejo."""
        import hashlib

        crudo = "|".join([
            ",".join(self.codigos_riasec), ",".join(self.intereses),
            ",".join(self.rutas), self.etapa_de_vida or "", self.en_sus_palabras,
        ])
        return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:32]


def _texto_del_journey(db: Session, user) -> List[str]:
    """Lo que la persona escribió a mano en el journey.

    Sólo respuestas de texto libre: las de opción múltiple ya viajan por el
    filtro duro (etapa de vida, país) y repetirlas aquí sesga el vector hacia el
    vocabulario del formulario en vez del de la persona.
    """
    from app.db.models import Session as SesionJourney

    fuera: List[str] = []
    sesiones = (
        db.query(SesionJourney)
        .filter(SesionJourney.user_id == user.id)
        .order_by(SesionJourney.updated_at.desc())
        .limit(3)
        .all()
    )
    for s in sesiones:
        for valor in (s.answers or {}).values():
            if isinstance(valor, str) and len(valor.strip()) > 25:
                fuera.append(valor.strip())
    return fuera


def _texto_del_journal(db: Session, user) -> List[str]:
    """Lo que la persona fue anotando · la señal que más crece con el uso."""
    from app.db.models import JournalEntry, Session as SesionJourney

    filas = (
        db.query(JournalEntry)
        .join(SesionJourney, JournalEntry.session_id == SesionJourney.id)
        .filter(SesionJourney.user_id == user.id)
        .order_by(JournalEntry.created_at.desc())
        .limit(JOURNAL_RECIENTES * 3)  # holgura: se filtra por tipo después
        .all()
    )
    fuera = []
    for f in filas:
        tipo = getattr(f.entry_type, "value", f.entry_type)
        if tipo in JOURNAL_UTILES and (f.content or "").strip():
            fuera.append(f.content.strip())
        if len(fuera) >= JOURNAL_RECIENTES:
            break
    return fuera


def _rutas_del_perfil(datos: dict) -> List[str]:
    """Los caminos profesionales del perfil · familias **y** sus oficios.

    `suggested_career_paths` son los nombres de las familias y nada más:
    "Salud y cuidado animal", "Producto digital". Como vocabulario para buscar
    en un catálogo son pobres — ningún programa se llama así. Los oficios que
    viven dentro de cada familia (`career_families[].careers`) sí se parecen a
    los nombres reales: "Veterinaria", "Zootecnia", "Diseño de interacción".

    Medir importa más que argumentar, pero el mecanismo es claro: el vector del
    estudiante se construye con este texto (`embeddings.texto_de_perfil`) y se
    compara contra el nombre del programa, su área y su glosa. Acercarlo al
    vocabulario del catálogo es exactamente para lo que se escribió la glosa —
    el mismo puente, desde el otro lado.

    Las familias se generan desde `consolidate_v2` (2026-09-08); los perfiles
    anteriores no las traen y caen a la lista suelta de siempre. El orden
    conserva el del modelo (la primera familia es la de mayor calce) y se
    deduplica sin distinguir mayúsculas, porque el nombre de la familia suele
    repetirse dentro de sus propios oficios.
    """
    fuera: List[str] = []
    vistos: set = set()

    def _sumar(valor) -> None:
        texto = str(valor or "").strip()
        if texto and texto.lower() not in vistos:
            vistos.add(texto.lower())
            fuera.append(texto)

    for familia in (datos.get("career_families") or []):
        if not isinstance(familia, dict):
            continue
        _sumar(familia.get("name"))
        for oficio in (familia.get("careers") or []):
            _sumar(oficio)

    # Siempre, no sólo como fallback: `suggested_career_paths` debería ser el
    # espejo de los `name` (lo exige el prompt), pero si un perfil viejo o una
    # respuesta incompleta lo desalinea, perder un camino es peor que repetirlo
    # — y el dedupe de arriba se encarga de que repetirlo no cueste nada.
    for ruta in (datos.get("suggested_career_paths") or []):
        _sumar(ruta)

    return fuera


def perfil_del_usuario(db: Session, user) -> PerfilBusqueda:
    """Arma el perfil de búsqueda desde lo que el estudiante ya dejó.

    Todo es opcional: quien no ha hecho el test igual puede buscar, sólo pierde
    el orden por afinidad. **Nada aquí lanza excepción** — que falte una señal no
    puede dejar a alguien sin catálogo, y son cinco consultas distintas donde
    cualquiera puede fallar.
    """
    from app.db.models import ConsolidatedProfileCache
    from app.services import recommendation_service

    p = PerfilBusqueda()
    # Se inicializa fuera del `try` porque más abajo se vuelve a leer: si la
    # consulta falla, sin esto el bloque siguiente revienta con NameError — y
    # todo este método existe precisamente para que ninguna señal ausente deje a
    # un estudiante sin catálogo.
    fila = None

    try:
        p.etapa_de_vida = recommendation_service.etapa_de_vida(db, user)
    except Exception:  # pragma: no cover · defensivo
        logger.warning("no se pudo resolver la etapa de vida", exc_info=True)

    try:
        fila = (
            db.query(ConsolidatedProfileCache)
            .filter(ConsolidatedProfileCache.user_id == user.id)
            .first()
        )
        datos = (fila.profile_data if fila else None) or {}
        if isinstance(datos, dict) and datos:
            # Se leen los campos sueltos y no se reconstruye el
            # `ConsolidatedProfile` completo a propósito: ese schema exige
            # `summary_narrative` de 200+ caracteres y tres fortalezas, y un
            # perfil a medio hacer reventaría la búsqueda entera por validación.
            p.codigos_riasec = [
                c for c in (
                    (h or {}).get("code", "")
                    for h in (datos.get("holland_codes") or [])
                    if isinstance(h, dict)
                ) if c
            ]
            p.intereses = [str(x) for x in (datos.get("interests") or [])]
            p.rutas = _rutas_del_perfil(datos)
            if p.codigos_riasec or p.intereses:
                p.senales.append("tests")
    except Exception:  # pragma: no cover · defensivo
        logger.warning("no se pudo leer el perfil consolidado", exc_info=True)

    # El texto libre se ordena de lo más propio de la persona a lo más elaborado
    # por la IA: lo que ella escribió pesa más que el resumen que le hicimos.
    partes: List[str] = []
    for fuente, nombre in ((_texto_del_journal, "journal"),
                           (_texto_del_journey, "journey")):
        try:
            trozos = fuente(db, user)
        except Exception:  # pragma: no cover · defensivo
            logger.warning("no se pudo leer %s", nombre, exc_info=True)
            continue
        if trozos:
            partes.extend(trozos)
            p.senales.append(nombre)

    try:
        resumen = str(((fila.profile_data if fila else None) or {}).get(
            "summary_narrative") or "")
    except Exception:  # pragma: no cover
        resumen = ""
    if resumen:
        partes.append(resumen)

    p.en_sus_palabras = " ".join(partes)[:4000]
    return p


async def vector_del_perfil(db: Session, perfil: PerfilBusqueda,
                            user) -> Optional[List[float]]:
    """El vector del estudiante, generándolo sólo si cambió algo.

    El perfil crece cada vez que la persona usa la app, pero entre visita y
    visita no cambia nada: pedirle un embedding al proveedor en cada búsqueda
    sería meter una dependencia de red en el camino crítico para recalcular lo
    mismo. Se guarda con la firma de las señales que lo produjeron y se regenera
    cuando esa firma deja de coincidir.

    Devuelve **None** si no hay nada que embeber o si el proveedor falla: la
    búsqueda sigue funcionando sin orden semántico.
    """
    from app.services import embeddings as emb

    texto = emb.texto_de_perfil(
        intereses=perfil.intereses, rutas=perfil.rutas,
        en_sus_palabras=perfil.en_sus_palabras,
    )
    if not texto.strip():
        return None

    firma = perfil.firma

    # ⚠️ La caché usa **su propia sesión**, no la del que llama.
    #
    # Guardar el vector exige un commit, y un commit expira todos los objetos
    # ORM de esa sesión. `/ofertas` carga las 2.511 fichas del catálogo ANTES de
    # pedir el vector: si el commit fuera sobre su sesión, al ordenarlas y
    # mapearlas después SQLAlchemy las volvería a pedir **una por una** a Neon.
    # Medido: la petición pasaba de menos de un segundo a colgarse.
    #
    # Además es lo correcto conceptualmente: esto es una caché, y no tiene por
    # qué participar de la transacción de quien la consulta ni arrastrarla si
    # falla.
    from app.db.database import SessionLocal

    def _parsear(crudo):
        if not crudo:
            return None
        return [float(x) for x in crudo.strip("[]").split(",") if x]

    guardado = None
    propia = SessionLocal()
    try:
        try:
            guardado = propia.execute(text(
                "SELECT firma, embedding::text AS emb FROM perfil_vectores "
                "WHERE user_id = :u"
            ), {"u": str(user.id)}).mappings().first()
        except Exception:  # pragma: no cover · la caché es optimización
            logger.debug("no se pudo leer el vector guardado", exc_info=True)

        if guardado and guardado["firma"] == firma and guardado["emb"]:
            return _parsear(guardado["emb"])

        try:
            vector = await emb.embeber_uno(texto)
        except Exception:
            logger.warning("no se pudo generar el vector del perfil",
                           exc_info=True, extra={"user_id": str(user.id)})
            # Si hay uno viejo, se usa: un perfil de ayer ordena mucho mejor que
            # ningún orden.
            return _parsear(guardado["emb"]) if guardado else None

        try:
            crudo = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"

            propia.execute(text(
                "INSERT INTO perfil_vectores (user_id, firma, actualizado, embedding)"
                " VALUES (:u, :f, now(), :v)"
                " ON CONFLICT (user_id) DO UPDATE SET firma = EXCLUDED.firma,"
                " actualizado = now(), embedding = EXCLUDED.embedding"
            ), {"u": str(user.id), "f": firma, "v": crudo})
            propia.commit()
        except Exception:  # pragma: no cover · guardar es optimización
            logger.warning("no se pudo guardar el vector del perfil", exc_info=True)
            propia.rollback()

        return vector
    finally:
        propia.close()


def vector_del_perfil_sync(db: Session, perfil: PerfilBusqueda,
                           user) -> Optional[List[float]]:
    """`vector_del_perfil` desde código síncrono · para `/ofertas`.

    El listado del catálogo es un endpoint síncrono y debe seguir siéndolo:
    FastAPI corre los síncronos en un hilo aparte, y pasarlo a `async` metería
    consultas bloqueantes de 2.511 filas dentro del event loop. Como ese hilo no
    tiene loop propio, `asyncio.run` es correcto aquí.

    Si por lo que sea ya hay un loop corriendo en este hilo, **no se fuerza**: se
    devuelve None y el catálogo conserva su orden de siempre. Ordenar peor es
    mucho mejor que colgar el proceso.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # lo esperado · no hay loop, se puede correr
    else:
        logger.debug("hay un loop corriendo · el catálogo va sin orden personal")
        return None

    try:
        return asyncio.run(vector_del_perfil(db, perfil, user))
    except Exception:  # pragma: no cover · defensivo
        logger.warning("no se pudo obtener el vector del perfil", exc_info=True)
        return None


# Cuánto vale un punto de prioridad comercial (1-10) frente a la similitud.
# 0.02 × 10 = 0.20 en el tope, sobre similitudes que se mueven en un rango de
# ~0.15: una ficha con las cinco estrellas de Verónica adelanta a casi cualquier
# otra, pero no aparece por encima de algo que le calza al estudiante y ella no
# priorizó. Es el compromiso entre el negocio de la agencia y el criterio del
# alumno, y está en una constante para que se pueda mover sin tocar la lógica.
PESO_PRIORIDAD = 0.02


def orden_personal_del_catalogo(
    db: Session,
    vector_perfil: Optional[Sequence[float]],
) -> dict:
    """Puntaje de afinidad de cada ficha del catálogo autorizado con el perfil.

    Devuelve `{id: puntaje}` para que quien llama ordene · no ordena él mismo
    porque `/ofertas` ya aplica sus propios filtros y paginación, y devolver un
    orden cerrado obligaría a rehacerlos aquí.

    **Puntúa el catálogo activo entero** (2.511 fichas, ~1.6 s) en vez de recibir
    los ids en pantalla. La primera versión los recibía y fallaba siempre con
    `operator does not exist: uuid = text`: los ids llegaban como strings y la
    columna es UUID. Como la excepción se capturaba, el catálogo se servía sin
    orden personal **sin que nada lo dijera**. Puntuarlo todo cuesta lo mismo,
    quita el casteo y no puede volver a fallar por el tipo de un parámetro.

    Vacío si no hay vector: sin perfil, el catálogo conserva el orden de siempre
    (prioridad comercial y luego nombre), que es exactamente lo que pidió la
    clienta y lo que ve alguien que acaba de registrarse.
    """
    if not vector_perfil:
        return {}
    try:
        db.execute(text(f"SET LOCAL ivfflat.probes = {int(PROBES)}"))
    except Exception:
        logger.debug("no se pudo fijar ivfflat.probes", exc_info=True)

    try:
        filas = db.execute(text(
            "SELECT id, 1 - (embedding <=> CAST(:v AS vector)) AS sim,"
            " COALESCE(priority, 0) AS prioridad "
            "FROM programs WHERE active AND embedding IS NOT NULL"
        ), {
            "v": "[" + ",".join(f"{x:.6f}" for x in vector_perfil) + "]",
        }).mappings().all()
    except Exception:
        logger.warning("no se pudo ordenar el catálogo por perfil", exc_info=True)
        return {}

    return {
        str(r["id"]): float(r["sim"]) + PESO_PRIORIDAD * float(r["prioridad"] or 0)
        for r in filas
    }


def paises_disponibles(db: Session, filtros: Optional[Filtros] = None) -> List[dict]:
    """Los países con oferta, con su conteo · el primer paso del recorrido."""
    # Mismo criterio que en `areas_sugeridas`: el país es la dimensión que se
    # está eligiendo, así que no filtra aquí, pero todo lo demás sí. `replace`
    # en vez de reconstruir: la versión anterior enumeraba cuatro campos y
    # descartaba los demás en silencio, así que `ciudades`, `confianzas` o
    # `solo_vendible` no se habrían respetado en el conteo sin que nada fallara.
    f = replace(filtros or Filtros(), paises=())
    where, params = _where(f)
    filas = db.execute(text(
        f"SELECT pi.pais AS pais, count(*) AS n FROM programas_investigados pi "
        f"WHERE {where} AND pi.pais IS NOT NULL GROUP BY pi.pais ORDER BY n DESC"
    ), params).mappings().all()
    return [{"pais": r["pais"], "programas": r["n"]} for r in filas]


def contar(db: Session, filtros: Optional[Filtros] = None) -> int:
    """Cuántos programas cumplen el filtro duro · el total honesto.

    Va aparte de `buscar()` a propósito. `buscar` devuelve como mucho una
    ventana ordenada por pertinencia; este es el tamaño real del conjunto. Sin
    los dos números la pantalla no puede distinguir "esto es todo lo que hay" de
    "esto es lo que te alcancé a ordenar", y esa diferencia es la que le dice al
    estudiante si vale la pena afinar los filtros.
    """
    where, params = _where(filtros or Filtros())
    return db.execute(
        text(f"SELECT count(*) FROM programas_investigados pi WHERE {where}"),
        params,
    ).scalar() or 0


def buscar_pagina(
    db: Session,
    vector_perfil: Optional[Sequence[float]] = None,
    codigos_riasec: Sequence[str] = (),
    filtros: Optional[Filtros] = None,
    pagina: int = 1,
    por_pagina: int = 24,
    orden: str = "relevancia",
    peso_afinidad: float = PESO_AFINIDAD,
) -> dict:
    """Una página de resultados, con el total real y hasta dónde llega el orden.

    Dos modos, y la respuesta dice cuál ocurrió:

    * **relevancia** (hay vector) · se trae la ventana de `VENTANA_RANKING`,
      se reordena con el refuerzo RIASEC y se corta la página **dentro de la
      ventana**. Más allá de la ventana no se pagina: no se puede sin recalcular
      el orden entero, y fingir que se puede daría páginas que cambian solas.
    * **listado** (sin vector, o `orden` explícito) · `LIMIT`/`OFFSET` normal
      sobre un orden estable. Aquí sí se pagina el conjunto completo.

    El estudiante nunca ve "no hay más": ve cuántos hay y que afinando llega.
    """
    f = filtros or Filtros()
    pagina = max(1, pagina)
    desde = (pagina - 1) * por_pagina
    total = contar(db, f)

    semantico = bool(vector_perfil) and orden == "relevancia"
    if semantico:
        ventana = buscar(db, vector_perfil=vector_perfil,
                         codigos_riasec=codigos_riasec, filtros=f,
                         limite=VENTANA_RANKING, peso_afinidad=peso_afinidad)
        pagina_items = ventana[desde:desde + por_pagina]
        alcance = len(ventana)
    else:
        where, params = _where(f)
        params["n"] = por_pagina
        params["off"] = desde
        orden_sql = {
            "nombre": "pi.nombre, pi.institucion",
            "institucion": "pi.institucion, pi.nombre",
        }.get(orden, "pi.institucion, pi.nombre")
        filas = db.execute(
            text(f"SELECT {_COLUMNAS}, 0.0 AS sim FROM {_DESDE} "
                 f"WHERE {where} ORDER BY {orden_sql} LIMIT :n OFFSET :off"),
            params,
        ).mappings().all()
        pagina_items = [_a_resultado(r, codigos_riasec, peso_afinidad)
                        for r in filas]
        alcance = total

    # Las páginas que de verdad devuelven algo. En modo relevancia el orden sólo
    # existe dentro de la ventana, así que ofrecer páginas más allá sería ofrecer
    # páginas vacías: con 1.335 resultados y ventana de 500, `total / por_pagina`
    # da 267 páginas de las que 167 no traen nada. `total` sigue siendo el número
    # honesto y va aparte — es lo que le dice al estudiante que afinar sirve.
    alcanzable = min(total, alcance) if semantico else total

    # ¿Entendimos lo que pidió? · se mira el MEJOR resultado de la ventana, no
    # el de esta página: la página 4 tiene similitudes bajas por definición y no
    # dice nada sobre si la consulta se entendió.
    mejor = max((x.similitud for x in (ventana if semantico else pagina_items)),
                default=0.0)

    return {
        "programas": pagina_items,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "total_paginas": max(1, -(-alcanzable // por_pagina)),
        # `None` sin orden semántico: sin vector no hay similitud que juzgar, y
        # devolver `False` haría creer que la consulta se entendió mal cuando en
        # realidad no se intentó entenderla.
        "entendi_la_consulta": (mejor >= UMBRAL_CONFIANZA) if semantico else None,
        "mejor_similitud": round(mejor, 4) if semantico else None,
        # Hasta dónde llega el orden por pertinencia · `None` cuando se pagina
        # el conjunto entero y la pregunta no aplica.
        "ranking_hasta": alcance if semantico else None,
        "orden_semantico": semantico,
    }


#: Las dimensiones que se cuentan a la vez. `institucion` NO está: son 534
#: valores y multiplicaría el cubo sin que nadie los recorra en una lista. Va
#: por su propio camino, con buscador.
_DIMENSIONES = ("pais", "area", "nivel", "ciudad")

#: Cómo se llama en pantalla el bucket de los que no tienen el dato. Escritas a
#: mano y no generadas con f-string porque el género no se deduce: "Sin ciudad
#: registrado" es lo que salía, y una etiqueta mal escrita en la faceta más
#: visible del producto se lee como descuido de todo lo demás.
_SIN_DATO = {
    "pais": "Sin país registrado",
    "area": "Sin área registrada",
    "nivel": "Sin nivel registrado",
    "ciudad": "Sin ciudad registrada",
}


def facetas(db: Session, filtros: Optional[Filtros] = None,
            tope_por_faceta: int = 40) -> dict:
    """Los conteos de cada filtro, en **una sola consulta**.

    ## Por qué "leave-one-out"

    El conteo que sirve para decidir es el que **no aplica el filtro de su
    propia dimensión**. Si el usuario ya eligió Reino Unido y la lista de países
    contara aplicando ese filtro, todos los demás países saldrían en cero y el
    multi-select sería inútil: no podría añadir Irlanda porque parecería vacía.

    ## Por qué un cubo y no cinco consultas

    Lo directo es una consulta por faceta, cada una con su dimensión quitada.
    Son cinco ida-y-vuelta a Neon **por cada tecleo** del usuario. En vez de eso
    se trae un `GROUP BY` de las cuatro dimensiones a la vez con el filtro duro
    **sin ninguna de ellas**, y los cinco estados se agregan en memoria. Una
    consulta, conteos exactos, y todas las combinaciones a la vez.

    ## Lo que no se sabe también se cuenta

    Un programa sin ciudad no desaparece: cae en un bucket con `valor = None` y
    su etiqueta. Es el mismo criterio del mapa, que cuenta en pantalla las
    opciones sin ubicación en vez de dejarlas fuera sin avisar — y es justo lo
    que evita que el 12% del catálogo se esfume porque nadie le puso el dato.
    """
    f = filtros or Filtros()
    # El cubo se calcula con el filtro duro SIN las dimensiones facetadas: son
    # las que se van a contar en todos sus estados.
    base = replace(f, paises=(), areas=(), niveles=(), ciudades=())
    where, params = _where(base)

    cols = ", ".join(f"pi.{d}" for d in _DIMENSIONES)
    filas = db.execute(text(
        f"SELECT {cols}, count(*) AS n FROM programas_investigados pi "
        f"WHERE {where} GROUP BY {cols}"
    ), params).mappings().all()

    elegido = {
        "pais": set(f.paises), "area": set(f.areas),
        "nivel": set(f.niveles), "ciudad": set(f.ciudades),
    }

    salida: dict = {}
    for dim in _DIMENSIONES:
        # Las demás dimensiones sí filtran; la propia no. Una celda cuenta para
        # esta faceta sólo si cumple todo lo elegido en las otras tres.
        otras = [d for d in _DIMENSIONES if d != dim]
        cuenta: dict = {}
        for r in filas:
            if any(elegido[d] and r[d] not in elegido[d] for d in otras):
                continue
            cuenta[r[dim]] = cuenta.get(r[dim], 0) + r["n"]
        ordenado = sorted(cuenta.items(), key=lambda kv: (-kv[1], str(kv[0])))
        salida[dim] = [
            {
                "valor": v,
                "programas": n,
                # El `None` necesita nombre: en pantalla "Sin ciudad registrada"
                # con su conteo es honesto; una fila en blanco no lo es.
                "etiqueta": v if v is not None else _SIN_DATO[dim],
                "elegido": v in elegido[dim],
            }
            for v, n in ordenado[:tope_por_faceta]
        ]
    return salida


def instituciones_disponibles(db: Session, filtros: Optional[Filtros] = None,
                              texto: Optional[str] = None,
                              limite: int = 50) -> List[dict]:
    """Las instituciones con oferta bajo el filtro · con buscador.

    Aparte del cubo porque son 534: nadie recorre esa lista con la vista, se
    busca por nombre. El `texto` acota sin tildes —"catolica" encuentra
    "Católica"— apoyado en el índice trigram de la migración 077.
    """
    f = replace(filtros or Filtros(), instituciones=())
    where, params = _where(f)
    if texto:
        where += " AND inmutable_unaccent(lower(pi.institucion)) LIKE :q_inst"
        # `_plano` de `lugares` ya hace lo mismo que el índice de la
        # migración 077: minúsculas, sin tildes, espacios colapsados.
        params["q_inst"] = f"%{lugares._plano(texto)}%"
    filas = db.execute(text(
        f"SELECT pi.institucion AS institucion, count(*) AS n "
        f"FROM programas_investigados pi WHERE {where} "
        f"GROUP BY pi.institucion ORDER BY n DESC, pi.institucion LIMIT :lim"
    ), {**params, "lim": limite}).mappings().all()
    return [
        {"valor": r["institucion"], "programas": r["n"],
         "etiqueta": r["institucion"],
         "elegido": r["institucion"] in set((filtros or Filtros()).instituciones)}
        for r in filas
    ]


def mezclar_por_concepto(listas: List[List[Resultado]], limite: int) -> List[Resultado]:
    """Une los resultados de varios conceptos sin que uno se coma al otro.

    ## El problema

    "Me gustan los animales pero también dibujar" son dos intereses. Buscarlos
    con un solo vector promedia los dos y no se parece bien a ninguno —medido,
    similitud 0.347 contra 0.45-0.48 buscando cada concepto por separado— y el
    resultado son diez programas de dibujo y cero de animales.

    ## Por qué intercalar y no ordenar por puntaje

    Ordenar la unión por similitud parece lo natural y **reproduce el problema**:
    "dibujar" tiene 2.041 programas en el catálogo y "animales" 312, así que el
    concepto con más oferta copa las primeras posiciones igual. Lo que la persona
    pidió son las dos cosas, y lo honesto es darle de las dos.

    Se intercala por rondas —el mejor de cada concepto, luego el segundo de cada
    uno— así que con dos conceptos la primera página trae mitad y mitad, y el
    orden dentro de cada mitad sigue siendo por pertinencia.
    """
    vistos: set = set()
    salida: List[Resultado] = []
    for ronda in range(max((len(x) for x in listas), default=0)):
        for lista in listas:
            if ronda >= len(lista):
                continue
            r = lista[ronda]
            if r.id in vistos:
                continue
            vistos.add(r.id)
            salida.append(r)
            if len(salida) >= limite:
                return salida
    return salida


async def _sin_bloquear(fn, *args, **kwargs):
    """Corre una consulta síncrona FUERA del event loop.

    ## Por qué existe

    `buscar_con_texto` es `async` porque necesita esperar al proveedor de
    embeddings. Pero las consultas que hace entre medias son SQLAlchemy
    síncrono, y ejecutarlas directamente dentro de una corrutina **bloquea el
    event loop entero**: mientras una petición espera a Neon, todas las demás
    del servidor se quedan congeladas, incluidas las que no tienen nada que ver.

    Medido el 2026-09-20 contra este mismo endpoint, antes del arreglo:

        1 petición simultánea ....  2,2 s
        2 ........................  5,3 s
        4 ........................  7,9 s
        8 ........................ 15,8 s

    Crecimiento lineal perfecto, que es la firma de la serialización. Con un
    solo dyno en Heroku eso significa que ocho estudiantes navegando a la vez se
    esperan unos a otros — y que una sola pantalla que dispare siete llamadas se
    autobloquea.

    `run_in_threadpool` las manda al pool de hilos que FastAPI ya usa para los
    endpoints `def` normales. La sesión de SQLAlchemy se sigue usando desde un
    hilo a la vez (los `await` son secuenciales), así que no se introduce
    concurrencia sobre ella.
    """
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(fn, *args, **kwargs)


async def buscar_con_texto(
    db: Session,
    consulta: str,
    vector_perfil: Optional[Sequence[float]] = None,
    codigos_riasec: Sequence[str] = (),
    filtros: Optional[Filtros] = None,
    pagina: int = 1,
    por_pagina: int = 24,
) -> dict:
    """Una búsqueda escrita por el estudiante, con sus palabras.

    Junta las tres piezas en el orden que importa:

    1. **Interpretar** lo que escribió (`interprete_busqueda`). De ahí salen los
       conceptos a buscar y, si los pidió explícitamente, filtros. Los filtros
       que propone el modelo **se marcan con su origen** y viajan a la pantalla
       para que el estudiante los vea y los pueda quitar: un filtro invisible
       puede esconder 33.000 programas sin que nadie se entere.
    2. **Buscar cada concepto por separado** y mezclar. Promediar dos intereses
       en un vector no se parece bien a ninguno — medido, 0.346 contra 0.618.
    3. **El filtro duro no se toca.** Sigue siendo SQL y sigue decidiendo qué es
       elegible. La interpretación ordena y sugiere; no abre la puerta.

    Sin texto, o si el intérprete falla, cae a `buscar_pagina` con el vector del
    perfil: exactamente el comportamiento anterior.
    """
    from app.services import embeddings as emb, interprete_busqueda as ib

    f = filtros or Filtros()
    texto = (consulta or "").strip()
    if not texto:
        return {**await _sin_bloquear(buscar_pagina, db, vector_perfil, codigos_riasec, f,
                                pagina, por_pagina),
                "interpretacion": None}

    interp = await ib.interpretar(texto)

    # Los filtros que propuso el modelo se SUMAN a los que el estudiante ya
    # eligió; nunca los reemplazan. Y sólo se aplican donde él no había elegido
    # nada — si ya marcó "Canadá" y el texto dice "Londres", manda lo que marcó.
    f = replace(
        f,
        paises=tuple(f.paises) or tuple(interp.paises),
        areas=tuple(f.areas) or tuple(interp.areas),
        niveles=tuple(f.niveles) or tuple(interp.niveles),
        ciudades=tuple(f.ciudades) or tuple(interp.ciudades),
    )

    sugeridos = [
        {"tipo": tipo, "valor": v, "origen": "texto"}
        for tipo, valores in (("pais", interp.paises), ("area", interp.areas),
                              ("nivel", interp.niveles), ("ciudad", interp.ciudades))
        for v in valores
    ]

    if not interp.conceptos:
        # Sin conceptos no hay nada que buscar por texto: se cae al perfil, que
        # es la mejor señal disponible. Pasa con "hola" y con "no sé qué quiero
        # estudiar" — y en el segundo caso el perfil es justo lo que hace falta.
        r = await _sin_bloquear(buscar_pagina, db, vector_perfil, codigos_riasec, f,
                                pagina, por_pagina)
    else:
        listas = []
        for c in interp.conceptos:
            try:
                vc = await emb.embeber_uno(c)
            except Exception:
                logger.warning("no se pudo embeber el concepto %r", c, exc_info=True)
                continue
            listas.append(await _sin_bloquear(
                buscar, db, vector_perfil=vc, codigos_riasec=codigos_riasec,
                                 filtros=f, limite=VENTANA_RANKING))
        if not listas:
            r = await _sin_bloquear(buscar_pagina, db, vector_perfil, codigos_riasec, f,
                                pagina, por_pagina)
        else:
            ventana = mezclar_por_concepto(listas, limite=VENTANA_RANKING)
            desde = (max(1, pagina) - 1) * por_pagina
            total = await _sin_bloquear(contar, db, f)
            alcanzable = min(total, len(ventana))
            mejor = max((x.similitud for x in ventana), default=0.0)
            r = {
                "programas": ventana[desde:desde + por_pagina],
                "pagina": max(1, pagina), "por_pagina": por_pagina,
                "total": total,
                "total_paginas": max(1, -(-alcanzable // por_pagina)),
                "ranking_hasta": len(ventana),
                "orden_semantico": True,
                "entendi_la_consulta": mejor >= UMBRAL_CONFIANZA,
                "mejor_similitud": round(mejor, 4),
            }

    r["interpretacion"] = {
        "conceptos": interp.conceptos,
        "entendi": interp.entendi,
        # Lo que este catálogo no tiene · la pantalla escribe el mensaje. Es
        # mejor decir "no tenemos precios, tu asesor tiene tarifas negociadas"
        # que devolver resultados como si la pregunta se hubiera respondido.
        "fuera_de_alcance": interp.fuera_de_alcance,
        "filtros_sugeridos": sugeridos,
        "interpretada": interp.interpretada,
    }
    return r
