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
    # La ficha del catálogo a la que pertenece · con esto el estudiante puede
    # saltar del programa a la institución sin buscarla a mano.
    program_id: Optional[str] = None
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
             "pi.program_id, p.slug AS oferta_slug, p.name AS oferta_nombre")

# `LEFT JOIN` y no `JOIN`: 708 programas no cuelgan de ninguna ficha y deben
# seguir siendo visibles · un JOIN normal los borraría del catálogo en silencio.
_DESDE = ("programas_investigados pi "
          "LEFT JOIN programs p ON p.id = pi.program_id AND p.active")


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
            program_id=str(r["program_id"]) if r["program_id"] else None,
            oferta_slug=r["oferta_slug"], oferta_nombre=r["oferta_nombre"],
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
            p.rutas = [str(x) for x in (datos.get("suggested_career_paths") or [])]
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
    f = filtros or Filtros()
    f = Filtros(paises=(), areas=f.areas, niveles=f.niveles,
                etapa_de_vida=f.etapa_de_vida)
    where, params = _where(f)
    filas = db.execute(text(
        f"SELECT pi.pais AS pais, count(*) AS n FROM programas_investigados pi "
        f"WHERE {where} AND pi.pais IS NOT NULL GROUP BY pi.pais ORDER BY n DESC"
    ), params).mappings().all()
    return [{"pais": r["pais"], "programas": r["n"]} for r in filas]
