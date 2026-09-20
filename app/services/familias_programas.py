"""La familia profesional como eje para recorrer el catálogo.

El recorrido de siempre es `país → área → programa`: una taxonomía
administrativa. Este módulo permite el otro, que es el de un consejero:

    "Salud y cuidado animal te calza porque [lo suyo]. Así se ve por dentro.
     Esto es lo que conviene mirar antes de decidirte. Y esto es lo que existe."

Las tres primeras frases ya están escritas —las produjo `consolidate_v2` y el
estudiante las leyó en su perfil—. Lo único que faltaba era la cuarta, y para
eso hay que poder preguntarle al catálogo "¿qué hay de esta familia?".

## Por qué por vector y no por `area`

El nombre de la familia lo escribe un LLM y es texto libre: "Salud y cuidado
animal", "Creación y comunicación visual". Cruzarlo por string contra
`programas_investigados.area` —un vocabulario cerrado de 21 valores— fallaría en
la mayoría de los casos y, peor, fallaría en silencio devolviendo cero.

Cruzarlo por vector reusa el motor entero: el mismo espacio donde ya viven los
33.552 programas con su glosa, el mismo índice HNSW, la misma capa de refuerzo
RIASEC. `buscar()` no cambia ni una línea — sólo recibe otro vector.

## Qué se embebe, y qué no

`name` + `careers` + `what_its_like`. **`why_it_fits` se queda fuera**: está
escrito en segunda persona y habla de la PERSONA ("porque contaste que cuidas
perros callejeros"), no del campo. Meterlo metería el vocabulario del estudiante
en un vector que debe representar un área del conocimiento, y acercaría la
familia a programas que hablen de perros en vez de a programas de veterinaria.
Es la misma razón por la que `texto_de_programa` excluye el país.

`careers` va antes que `what_its_like` porque los oficios ("Medicina
veterinaria", "Etología clínica") son lo que de verdad se parece al nombre de un
programa; la descripción del día a día es contexto.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: Tope de familias que se aceptan de un perfil · el schema ya limita a 5, esto
#: protege de un `profile_data` viejo o manipulado que traiga más.
MAX_FAMILIAS = 5


def texto_de_familia(familia: Dict[str, Any]) -> str:
    """El texto que representa a una familia en el espacio vectorial.

    Va en el mismo registro telegráfico que `embeddings.texto_de_programa`
    —frases cortas separadas por puntos— porque dos textos escritos de forma
    parecida se comparan mejor que un párrafo contra una ficha.
    """
    partes: List[str] = []
    nombre = str(familia.get("name") or "").strip()
    if nombre:
        partes.append(nombre)

    oficios = [str(c).strip() for c in (familia.get("careers") or []) if str(c).strip()]
    if oficios:
        partes.append("Carreras y roles: " + ", ".join(oficios))

    como_es = str(familia.get("what_its_like") or "").strip()
    if como_es:
        partes.append(como_es)

    return ". ".join(partes)


def _firma(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:32]


def familias_del_usuario(db: Session, user) -> List[Dict[str, Any]]:
    """Las familias aconsejadas a esta persona, en el orden en que se las dimos.

    Se lee el JSON crudo del perfil cacheado y **no** se reconstruye el
    `ConsolidatedProfile`: ese schema exige `summary_narrative` de 200+
    caracteres y tres fortalezas, y un perfil a medio hacer dejaría al
    estudiante sin navegación por una validación que no le importa. Mismo
    criterio que `busqueda_programas.perfil_del_usuario`.

    Se lee la MISMA fila que pinta la tarjeta del perfil en pantalla, invalidada
    o no, a propósito: si el estudiante ve cinco familias en su perfil y esta
    lista trajera otras, el botón "ver programas de esta familia" llevaría a una
    familia que él no está mirando.

    Devuelve `[]` ante cualquier problema · quedarse sin este eje degrada a la
    búsqueda de siempre, que es lo que hace el producto para quien no tiene
    perfil todavía.
    """
    from app.db.models import ConsolidatedProfileCache

    try:
        fila = (
            db.query(ConsolidatedProfileCache)
            .filter(ConsolidatedProfileCache.user_id == user.id)
            .first()
        )
    except Exception:  # pragma: no cover · defensivo
        logger.warning("no se pudo leer el perfil consolidado", exc_info=True)
        return []

    datos = (fila.profile_data if fila else None) or {}
    if not isinstance(datos, dict):
        return []

    fuera: List[Dict[str, Any]] = []
    for f in (datos.get("career_families") or [])[:MAX_FAMILIAS]:
        if isinstance(f, dict) and str(f.get("name") or "").strip():
            fuera.append(f)
    return fuera


def familia_por_indice(db: Session, user, indice: int) -> Optional[Dict[str, Any]]:
    """La familia que está en esa posición · None si el índice no existe.

    El índice puede llegar de un enlace viejo (el estudiante guardó la URL, el
    perfil se regeneró y ahora tiene cuatro familias en vez de cinco). Devolver
    None y caer a la búsqueda normal es mejor que un 404 sobre una pantalla que
    sí tiene algo que mostrar.
    """
    familias = familias_del_usuario(db, user)
    if indice is None or indice < 0 or indice >= len(familias):
        return None
    return familias[indice]


def contexto_de_familia(familia: Dict[str, Any]) -> Dict[str, Any]:
    """Lo que la cabecera de la pantalla necesita para presentar el conjunto.

    Es **texto ya escrito y validado**: no se genera nada aquí. `why_it_fits`
    va arriba (por qué estás viendo esto) y `watch_out` abajo (qué mirar antes
    de decidirte), que es el orden en que lo diría un consejero.
    """
    return {
        "nombre": str(familia.get("name") or ""),
        "calce": familia.get("fit_level"),
        "por_que_calza": familia.get("why_it_fits"),
        "como_es": familia.get("what_its_like"),
        "oficios": [str(c) for c in (familia.get("careers") or [])],
        "ojo_con": familia.get("watch_out"),
    }


def vector_de_familia_sync(db: Session, user, indice: int,
                           familia: Optional[Dict[str, Any]] = None
                           ) -> Optional[List[float]]:
    """`vector_de_familia` desde código síncrono · mismo patrón que
    `busqueda_programas.vector_del_perfil_sync`, y por la misma razón.

    Los endpoints de búsqueda tienen que ser `def`: FastAPI los corre en un hilo
    aparte, y volverlos `async` mete las consultas bloqueantes dentro del event
    loop, que es de donde se llegó a medir 8 peticiones simultáneas tardando 16
    segundos mientras `/health` se quedaba 14 sin responder.

    Como ese hilo no tiene loop propio, `asyncio.run` es correcto. Si por lo que
    sea ya hubiera uno, no se fuerza: se devuelve None y la pantalla cae al
    vector del perfil. Ordenar peor es mucho mejor que colgar el proceso.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(vector_de_familia(db, user, indice, familia))
    logger.warning("vector_de_familia_sync llamado con un loop activo")
    return None


async def vector_de_familia(db: Session, user, indice: int,
                            familia: Optional[Dict[str, Any]] = None
                            ) -> Optional[List[float]]:
    """El vector de esa familia, generándolo sólo si cambió el texto.

    Devuelve **None** si no hay familia en ese índice o si el proveedor falla:
    la pantalla cae a la búsqueda por perfil, que sigue funcionando.

    ⚠️ La caché usa **su propia sesión**, igual que
    `busqueda_programas.vector_del_perfil` y por la misma razón medida: guardar
    el vector exige un commit, y un commit expira todos los objetos ORM de esa
    sesión. Quien llama ya cargó fichas del catálogo antes de pedir el vector;
    con el commit sobre su sesión, SQLAlchemy las volvería a pedir una por una
    a Neon y la petición se cuelga.
    """
    from app.db.database import SessionLocal
    from app.services import embeddings as emb

    if familia is None:
        familia = familia_por_indice(db, user, indice)
    if not familia:
        return None

    texto = texto_de_familia(familia)
    if not texto.strip():
        return None
    firma = _firma(texto)

    def _parsear(crudo):
        if not crudo:
            return None
        return [float(x) for x in crudo.strip("[]").split(",") if x]

    guardado = None
    propia = SessionLocal()
    try:
        try:
            guardado = propia.execute(text(
                "SELECT firma, embedding::text AS emb FROM familias_vectores "
                "WHERE user_id = :u AND indice = :i"
            ), {"u": str(user.id), "i": int(indice)}).mappings().first()
        except Exception:  # pragma: no cover · la caché es optimización
            logger.debug("no se pudo leer el vector de la familia", exc_info=True)

        if guardado and guardado["firma"] == firma and guardado["emb"]:
            return _parsear(guardado["emb"])

        try:
            vector = await emb.embeber_uno(texto)
        except Exception:
            logger.warning("no se pudo generar el vector de la familia",
                           exc_info=True,
                           extra={"user_id": str(user.id), "indice": indice})
            # Uno viejo ordena mucho mejor que ningún orden.
            return _parsear(guardado["emb"]) if guardado else None

        try:
            crudo = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
            propia.execute(text(
                "INSERT INTO familias_vectores (user_id, indice, firma, actualizado, embedding)"
                " VALUES (:u, :i, :f, now(), :v)"
                " ON CONFLICT (user_id, indice) DO UPDATE SET firma = EXCLUDED.firma,"
                " actualizado = now(), embedding = EXCLUDED.embedding"
            ), {"u": str(user.id), "i": int(indice), "f": firma, "v": crudo})
            propia.commit()
        except Exception:  # pragma: no cover · guardar es optimización
            logger.warning("no se pudo guardar el vector de la familia", exc_info=True)
            propia.rollback()

        return vector
    finally:
        propia.close()
