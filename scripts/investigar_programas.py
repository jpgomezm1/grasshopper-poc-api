"""Rutina de investigación de programas · las instituciones que aún no tienen ninguno.

Por qué existe
--------------
El catálogo autorizado (`import_catalogo_autorizado.py`) dice **qué instituciones**
se le muestran al estudiante y **qué niveles** puede vender la agencia en cada una.
Lo que no dice —ni puede— es qué programas concretos existen ahí. Eso es lo que la
clienta pidió con todas las letras:

    "el Excel solo me va a decir: de FIU Miami solo puedes vender todos los
     pregrados; ya al sistema con IA le toca ir a buscar todos los pregrados que
     hay para internacionales y cuál se acomoda a mi perfil según mis tests"

Los 15.483 programas que ya existen se produjeron a mano, con un agente leyendo
lotes en JSON y escribiendo .txt (ver `data/catalogo/README.md` y
`PROMPT_EXTRACCION.md`). Esta rutina automatiza ese mismo proceso, con las mismas
reglas, para las ~363 instituciones autorizadas que quedaron sin un solo programa.

Las tres reglas que NO se negocian
----------------------------------
Están heredadas del piloto del 07-08 y cada una nació de un error real:

1. **Sólo el dominio oficial de la institución.** Se comprobó buscando "Brisbane
   School of Beauty" sin ancla: los tres primeros resultados fueron competidores,
   con precios entre AUD 4.500 y 19.900, y el sitio real no apareció nunca. Aquí
   la restricción no se le pide al modelo por buena fe — va en `allowed_domains`
   de la herramienta de búsqueda, que la aplica la API.

2. **Nunca un precio, ni fechas, ni becas.** El precio cambia por intake y por
   nacionalidad, y la agencia tiene tarifas negociadas: un precio de web puesto en
   el catálogo es una promesa que un asesor no puede sostener frente a una familia.

3. **El código oficial es el ancla, no la URL.** Se inventó una ruta que no existe
   (`burlingtonschool.co.uk/…/curso-inventado-de-control.html`) y el sitio la
   respondió con contenido: varios sirven la portada para cualquier ruta. Una URL
   que responde 200 no prueba que el programa exista; un CRICOS inventado no está
   en el registro nacional. De ahí sale `confianza`.

Uso
---
    python scripts/investigar_programas.py                     # plan · no llama a la IA
    python scripts/investigar_programas.py --piloto 3          # 3 instituciones, mide costo
    python scripts/investigar_programas.py --lote 25 --commit  # investiga y escribe
    python scripts/investigar_programas.py --pais Australia --lote 40 --commit

Reanudable: sólo toma instituciones que no tengan ningún programa, así que
volver a correrlo continúa donde quedó en vez de repetir.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import ProgramaInvestigado  # noqa: E402
from app.services import areas as areas_mod  # noqa: E402
from app.services.ai_usage_service import record_ai_usage  # noqa: E402
from scripts.import_catalogo_autorizado import (  # noqa: E402
    NIVEL_AUTORIZADO_A_INVESTIGADO,
)

# El vocabulario que entiende el producto · cualquier otro valor se descarta.
# Es el mismo de PROMPT_EXTRACCION.md; si aquí y allá se separan, el cargador
# empieza a botar filas en silencio.
NIVELES_VALIDOS = (
    "secundaria",
    "pregrado",
    "bachelor",
    "maestria",
    "mba",
    "doctorado",
    "posgrado",
    "especializacion",
    "diplomado",
    "curso_corto",
    "vacacional",
    "intercambio",
    "bootcamp",
)

# El vocabulario cerrado de areas del producto · es lo que cruza con los tests.
# Se lee de `app.services.areas` en vez de repetirse aqui: dos listas que se
# separan hacen que el cargador descarte programas buenos en silencio.
AREAS_VALIDAS = tuple(
    x["nombre"] if isinstance(x, dict) else str(x) for x in areas_mod.AREAS
)

MAX_BUSQUEDAS_POR_INSTITUCION = 8
MAX_PROGRAMAS_POR_INSTITUCION = 60


PROMPT = """Eres un investigador de catálogos académicos. Extrae los programas de estudio \
que ofrece UNA institución, para el catálogo de una agencia colombiana de estudios en el exterior.

INSTITUCIÓN
  nombre  : {nombre}
  país    : {pais}
  ciudad  : {ciudad}
  dominio : {dominio}
  la agencia está autorizada a vender aquí: {autorizado}

LO PRIMERO, Y ES OBLIGATORIO: **BUSCA EN EL SITIO.**

Usa la herramienta de búsqueda web antes de escribir una sola línea, y vuelve a usarla
cuantas veces necesites para cubrir el catálogo. **No respondas de memoria.** Lo que
recuerdes de una institución pequeña es justo donde se inventan programas que no existen,
y este catálogo lo lee un estudiante —muchos menores— para decidir qué estudiar.
Una respuesta sin ninguna búsqueda se descarta entera, así que no tiene sentido darla.

Tu herramienta está restringida al dominio de arriba. No intentes salir de él: ya se
comprobó que una búsqueda genérica devuelve competidores con nombres parecidos, y
atribuirle a esta institución los programas de otra termina en un asesor diciéndoselo a una familia.

QUÉ SACAR DE CADA PROGRAMA

- `nombre`: exacto como aparece en el sitio. No lo traduzcas ni lo resumas.
- `nivel`: UNO de estos y sólo estos:
    {niveles}
  Mapeos frecuentes: Certificate I-IV australiano → curso_corto · Diploma / Advanced
  Diploma → diplomado · Graduate Diploma → posgrado · Foundation / Pre-master / Pathway
  → curso_corto · ELICOS / General English → curso_corto · campamentos y cursos de
  verano → vacacional · bachillerato completo (Year 7-12, boarding, high school diploma)
  → secundaria.
  **La primaria NO va.** Si ves Primary Years, Junior School, Elementary o JK-5, exclúyelo
  y dilo en `notas`. Un JK-5 no es bachillerato y el estudiante que lo vea recomendado no
  es el que la agencia atiende.
- `area`: **Es el dato más importante** — es lo que se cruza con los tests vocacionales del
  estudiante. Tiene que ser EXACTAMENTE una de estas, copiada tal cual:
    {areas}
  Elige la más cercana; no inventes una etiqueta nueva ni combines dos. Un área fuera de
  esta lista hace que el programa se descarte al cargar.
- `duracion`: como la diga el sitio ("6 meses", "79 semanas"). Si no la dice, null.
- `codigo_oficial`: CRICOS, RTO, código nacional (SHB30416, BSB50120, 092334E). Es lo que
  hace verificable el dato. Si no hay, null. **No lo inventes jamás**: un código falso se
  contrasta contra el registro nacional y nos deja mintiendo.
- `url_fuente`: la URL exacta donde lo viste.

QUÉ NO SE EXTRAE, Y NO ES NEGOCIABLE

**Precio · fechas de inicio · becas.** Aunque estén a la vista. El precio cambia por intake
y por nacionalidad y la agencia tiene tarifas negociadas propias. Si el sitio los publica,
puedes decirlo en `notas`, sin transcribir ninguna cifra.

REGLAS

1. Una URL que responde no prueba que el programa exista: varios sitios devuelven la
   portada para cualquier ruta. Si la página no describe el programa que dices, no lo incluyas.
2. No completes por analogía. Si el sitio no lista programas, devuelve `programas: []` y
   explícalo en `notas`. **"No encontrado" es un resultado correcto** y prefiero eso a una
   lista inventada.
3. Filtra lo que no se puede cursar: "Currently Not Accepting Enrolments", programas sólo
   para residentes locales (apprenticeships australianos), y servicios que no son programas
   (consultoría, capacitación in-company, alquiler de salas).
4. Máximo {max_programas} programas. Si hay más, quédate con los de los niveles que la
   agencia puede vender.

RESPONDE EXCLUSIVAMENTE con este JSON, sin texto antes ni después y sin markdown:

{{
  "institucion_encontrada": true,
  "nombre_real": "<el nombre como aparece en su propio sitio, o null>",
  "programas": [
    {{"nombre": "...", "nivel": "...", "area": "...", "duracion": null,
      "codigo_oficial": null, "url_fuente": "https://..."}}
  ],
  "notas": "<lo que el revisor deba saber · o null>"
}}
"""


def _dominio(website: Optional[str]) -> Optional[str]:
    """El host del sitio, sin esquema ni www · es lo que se le pasa a allowed_domains."""
    if not website:
        return None
    s = website.strip()
    if not s:
        return None
    if "//" not in s:
        s = "https://" + s
    host = (urlparse(s).netloc or "").lower().strip()
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _confianza(codigo: Optional[str], url: Optional[str], dominio: str) -> str:
    """El mismo vocabulario que ya usan las 15.483 filas cargadas a mano.

    `verificable` es el único que se puede contrastar contra un registro externo;
    los otros dos dicen, con honestidad, hasta dónde llega la evidencia.
    """
    if codigo:
        return "verificable"
    if url and dominio and dominio in url.lower():
        return "publicado"
    return "indicativo"


def _extraer_json(texto: str) -> Optional[dict]:
    t = (texto or "").strip()
    for candidato in (t, ):
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        try:
            return json.loads(t[i : j + 1])
        except json.JSONDecodeError:
            return None
    return None


def _pendientes(db, pais: Optional[str], limite: int) -> List[dict]:
    """Instituciones autorizadas, con sitio, y sin un solo programa investigado."""
    sql = """
        select ic.id, ic.name, ic.country, ic.city, ic.website, ic.niveles_autorizados
        from institutions_catalog ic
        where ic.active
          and coalesce(ic.website, '') <> ''
          and not exists (
                select 1 from programas_investigados pi
                where lower(pi.institucion) = lower(ic.name)
          )
    """
    params: Dict[str, Any] = {}
    if pais:
        sql += " and ic.country = :pais"
        params["pais"] = pais
    # Primero las que declaran nivel: de esas sabemos qué buscar y qué se puede
    # vender, así que su resultado entra completo al catálogo en vez de a medias.
    sql += """
        order by (ic.niveles_autorizados is null
                  or ic.niveles_autorizados::text = '[]') asc,
                 ic.country, ic.name
        limit :limite
    """
    params["limite"] = limite
    filas = []
    for r in db.execute(text(sql), params):
        filas.append(
            {
                "id": r[0],
                "nombre": r[1],
                "pais": r[2],
                "ciudad": r[3],
                "website": r[4],
                "niveles": list(r[5] or []),
            }
        )
    return filas


def _niveles_permitidos(autorizados: List[str]) -> set:
    """Qué niveles de programa quedan habilitados · vacío = sin restricción."""
    if not autorizados or "todos" in autorizados:
        return set()
    permitidos: set = set()
    for n in autorizados:
        permitidos.update(NIVEL_AUTORIZADO_A_INVESTIGADO.get(n, ()))
    return permitidos


def investigar_una(
    cliente, inst: dict, modelo: str, max_busquedas: int = MAX_BUSQUEDAS_POR_INSTITUCION
) -> Tuple[Optional[dict], dict]:
    """Una llamada · devuelve (payload, metadatos de consumo)."""
    dominio = _dominio(inst["website"])
    autorizado = ", ".join(inst["niveles"]) or "no lo dice el archivo del cliente"
    prompt = PROMPT.format(
        nombre=inst["nombre"],
        pais=inst["pais"] or "no indicado",
        ciudad=inst["ciudad"] or "no indicada",
        dominio=dominio,
        autorizado=autorizado,
        niveles=" · ".join(NIVELES_VALIDOS),
        areas=" · ".join(AREAS_VALIDAS),
        max_programas=MAX_PROGRAMAS_POR_INSTITUCION,
    )

    t0 = time.time()
    resp = cliente.messages.create(
        model=modelo,
        max_tokens=8000,
        temperature=0,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                # La restricción vive aquí, no en la buena fe del modelo.
                "allowed_domains": [dominio],
                "max_uses": max_busquedas,
            }
        ],
        # Obliga a que el primer turno sea una busqueda. Sin esto el modelo
        # respondia de memoria: en el primer piloto devolvio 38 programas de tres
        # instituciones con CERO busquedas. Pedirselo en el prompt no alcanzo —
        # con un "responde solo JSON" delante, contesta directo.
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": prompt}],
    )
    latencia = int((time.time() - t0) * 1000)

    texto = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    meta = {
        "tokens_input": getattr(resp.usage, "input_tokens", None),
        "tokens_output": getattr(resp.usage, "output_tokens", None),
        "latency_ms": latencia,
        "busquedas": getattr(
            getattr(resp.usage, "server_tool_use", None), "web_search_requests", 0
        )
        or 0,
    }
    return _extraer_json(texto), meta


def normalizar_programas(inst: dict, payload: dict) -> Tuple[List[dict], Counter]:
    """Valida y normaliza · devuelve (filas listas, motivos de descarte)."""
    descartes: Counter = Counter()
    listos: List[dict] = []
    if not payload:
        descartes["respuesta ilegible"] += 1
        return listos, descartes

    dominio = _dominio(inst["website"]) or ""
    permitidos = _niveles_permitidos(inst["niveles"])
    vistos: set = set()

    for p in payload.get("programas") or []:
        if not isinstance(p, dict):
            descartes["fila no es un objeto"] += 1
            continue
        nombre = (p.get("nombre") or "").strip()
        if not nombre:
            descartes["sin nombre"] += 1
            continue
        nivel = (p.get("nivel") or "").strip().lower()
        if nivel not in NIVELES_VALIDOS:
            descartes[f"nivel fuera del vocabulario: {nivel or '(vacío)'}"] += 1
            continue
        area = areas_mod.normalizar(p.get("area"))
        if not area:
            descartes[f"area sin mapear: {p.get('area')}"] += 1
            continue

        clave = (nombre.lower(), nivel)
        if clave in vistos:
            descartes["repetido en la misma respuesta"] += 1
            continue
        vistos.add(clave)

        codigo = (p.get("codigo_oficial") or "").strip()
        codigo = None if codigo in ("", "-", "?", "null", "N/A") else codigo[:80]
        url = (p.get("url_fuente") or "").strip() or None

        # El nivel autorizado decide si se muestra, no si se guarda: si mañana la
        # clienta amplía lo que puede vender ahí, el dato ya está investigado.
        activo = (not permitidos) or (nivel in permitidos)

        listos.append(
            dict(
                id=uuid.uuid4(),
                institucion=inst["nombre"][:255],
                nombre=nombre[:500],
                pais=inst["pais"],
                ciudad=(inst["ciudad"] or "")[:160] or None,
                nivel=nivel,
                area=area,
                area_cruda=(p.get("area") or "")[:160] or None,
                duracion=(p.get("duracion") or "")[:120] or None,
                codigo_oficial=codigo,
                url_fuente=url,
                dominio=dominio[:160] or None,
                confianza=_confianza(codigo, url, dominio),
                activo=activo,
            )
        )
    return listos, descartes


def main() -> int:
    ap = argparse.ArgumentParser(description="Investiga programas de las instituciones pendientes")
    ap.add_argument("--lote", type=int, default=10, help="Cuántas instituciones investigar")
    ap.add_argument("--piloto", type=int, help="Atajo · corre N y reporta costo, sin escribir")
    ap.add_argument("--pais", help="Limitar a un país (valor de institutions_catalog.country)")
    ap.add_argument("--commit", action="store_true", help="Escribe en la DB")
    ap.add_argument("--etiqueta", default=None, help="Valor de `lote` para trazar esta corrida")
    # La palanca de costo. Cada busqueda inyecta el contenido de las paginas al
    # contexto: medido, ~240k tokens de entrada por institucion con 8 busquedas.
    # Bajarlo abarata en proporcion casi lineal, a cambio de cubrir menos catalogo.
    ap.add_argument(
        "--max-busquedas",
        type=int,
        default=MAX_BUSQUEDAS_POR_INSTITUCION,
        help=f"Busquedas web por institucion (defecto {MAX_BUSQUEDAS_POR_INSTITUCION})",
    )
    args = ap.parse_args()

    if args.piloto:
        args.lote = args.piloto
        args.commit = False

    db = SessionLocal()
    pendientes = _pendientes(db, args.pais, args.lote)

    total_pendientes = db.execute(
        text(
            """
            select count(*) from institutions_catalog ic
            where ic.active and coalesce(ic.website,'') <> ''
              and not exists (select 1 from programas_investigados pi
                              where lower(pi.institucion) = lower(ic.name))
            """
        )
    ).scalar()
    sin_sitio = db.execute(
        text(
            """
            select count(*) from institutions_catalog ic
            where ic.active and coalesce(ic.website,'') = ''
              and not exists (select 1 from programas_investigados pi
                              where lower(pi.institucion) = lower(ic.name))
            """
        )
    ).scalar()

    print("=" * 72)
    print("INVESTIGACION DE PROGRAMAS ·", "ESCRIBE" if args.commit else "SIMULACRO")
    print("=" * 72)
    print(f"Autorizadas sin programas, CON sitio : {total_pendientes}  <- investigables")
    print(f"Autorizadas sin programas, SIN sitio : {sin_sitio}  <- hay que pedirle el dominio al cliente")
    print(f"En esta corrida                      : {len(pendientes)}")
    print()

    if not pendientes:
        print("No hay nada pendiente con los filtros dados.")
        db.close()
        return 0

    if not args.commit and not args.piloto:
        print("PLAN · estas se investigarian (no se llamo a la IA):")
        for i in pendientes:
            print(f"  {(i['pais'] or '?')[:12]:14} {i['nombre'][:40]:42} {_dominio(i['website'])}")
        print()
        print("Correr con --piloto N para medir costo, o --lote N --commit para aplicar.")
        db.close()
        return 0

    import anthropic

    settings = get_settings()
    cliente = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    modelo = settings.ai_model
    etiqueta = args.etiqueta or f"auto{int(time.time()) % 100000}"

    resumen = Counter()
    descartes_todos: Counter = Counter()
    tokens_in = tokens_out = busquedas = 0

    for n, inst in enumerate(pendientes, 1):
        dominio = _dominio(inst["website"])
        if not dominio:
            resumen["sin dominio utilizable"] += 1
            continue
        print(f"[{n}/{len(pendientes)}] {inst['nombre'][:44]:46} {dominio}")
        try:
            payload, meta = investigar_una(cliente, inst, modelo, args.max_busquedas)
        except Exception as exc:  # pragma: no cover · red
            print(f"      fallo la llamada: {exc}")
            resumen["llamada fallida"] += 1
            continue

        tokens_in += meta["tokens_input"] or 0
        tokens_out += meta["tokens_output"] or 0
        busquedas += meta["busquedas"]

        # La regla que el piloto obligo a poner: en la primera corrida el modelo
        # devolvio 38 programas de tres instituciones SIN hacer una sola busqueda
        # — los escribio de memoria. La instruccion sola no basta; esto lo hace
        # verificable. Sin busqueda no hay evidencia, y sin evidencia no entra.
        if meta["busquedas"] == 0:
            print("      DESCARTADO · respondio sin buscar en el sitio (0 busquedas)")
            resumen["descartado por no buscar"] += 1
            continue

        filas, descartes = normalizar_programas(inst, payload)
        descartes_todos.update(descartes)

        if payload and payload.get("institucion_encontrada") is False:
            print("      el sitio no permitio confirmar la institucion")
            resumen["institucion no confirmada"] += 1
        if not filas:
            print(f"      0 programas  ·  {(payload or {}).get('notas') or 'sin notas'}")
            resumen["sin programas"] += 1
            continue

        verificables = sum(1 for f in filas if f["confianza"] == "verificable")
        activos = sum(1 for f in filas if f["activo"])
        print(
            f"      {len(filas)} programas · {verificables} con codigo oficial · "
            f"{activos} visibles segun lo autorizado"
        )
        resumen["instituciones con programas"] += 1
        resumen["programas"] += len(filas)

        if args.commit:
            for f in filas:
                db.add(ProgramaInvestigado(lote=etiqueta[:8], **f))
            db.commit()
            record_ai_usage(
                db,
                provider="anthropic",
                model=modelo,
                feature="investigar_programas",
                tokens_input=meta["tokens_input"],
                tokens_output=meta["tokens_output"],
                latency_ms=meta["latency_ms"],
            )

    print()
    print("=" * 72)
    for k, v in resumen.most_common():
        print(f"  {v:5}  {k}")
    if descartes_todos:
        print("\n  descartados al normalizar:")
        for m, c in descartes_todos.most_common(8):
            print(f"    {c:5}  {m}")
    print()
    print(f"  tokens entrada {tokens_in} · salida {tokens_out} · busquedas web {busquedas}")
    # Precio de referencia de Sonnet + la busqueda como server tool. Es una
    # estimacion para dimensionar la corrida completa, no una factura.
    costo = tokens_in / 1e6 * 3.0 + tokens_out / 1e6 * 15.0 + busquedas * 0.01
    hechas = resumen["instituciones con programas"] + resumen["sin programas"]
    print(f"  costo estimado de esta corrida: USD {costo:.2f}")
    if hechas:
        print(
            f"  ~USD {costo / hechas:.2f} por institucion -> "
            f"USD {costo / hechas * total_pendientes:.0f} por las {total_pendientes} pendientes"
        )
    if args.commit:
        print(f"  ESCRITO · etiqueta de lote '{etiqueta}'")
        print(f"  Quedan {total_pendientes - resumen['instituciones con programas']} "
              "instituciones investigables.")
    else:
        print("  SIMULACRO · no se escribio nada.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
