"""Carga los videos de orientación desde un archivo que produce la clienta.

Uso:

    python scripts/cargar_videos.py videos.csv            # simulacro (no escribe)
    python scripts/cargar_videos.py videos.csv --aplicar  # escribe de verdad

## Por qué un script y no un panel

Decisión de AH (2026-08-27): por ahora el equipo carga el contenido. Un panel
para que Verónica cargue sola es lo correcto a futuro y es lo único que la
hace autónoma —cada video nuevo hoy pasa por nosotros—, pero es otro trabajo.

## Lo que este script NO hace, a propósito

**No borra nada.** El repo ya tiene un script (`seed_test_data.py`) cuyo
`--clean` borra cuentas de verdad, y está anotado en el `CLAUDE.md` como algo
que no se corre tal cual. Este no tiene modo destructivo: sólo inserta y
actualiza. Un video que desaparece del archivo se queda en la base — para
retirarlo se pone `publicado=no`, que es reversible.

**No escribe si no se lo pides.** Sin `--aplicar` sólo dice qué haría. Es el
orden inverso al habitual a propósito: el modo peligroso se escribe a mano.

**No inventa datos.** Si una fila no trae duración, se guarda sin duración y
el front no pinta el badge. Poner un número plausible sería exactamente el
tipo de dato inventado por el que ya hubo un reclamo del cliente.

## El archivo

CSV con encabezado, separador coma, UTF-8. Columnas:

    url          obligatoria · enlace de YouTube o Vimeo · identifica la fila
    titulo       obligatoria
    tema         obligatoria · la fila de la galería ("Ingeniería", "Salud"…)
    descripcion  opcional
    miniatura    opcional · si falta, el front la deriva del id de YouTube
    duracion     opcional · segundos, o "m:ss" (p.ej. "6:12")
    riasec       opcional · letras separadas por espacio o coma ("R I")
    momento      opcional · id de un hecho de `journey_chat_hechos`
    ruta         opcional · una de las 5 rutas de la malla
    orden        opcional · entero, para ordenar dentro de su tema
    publicado    opcional · "no" lo deja cargado pero invisible

`url` es la identidad: volver a pasar el mismo archivo actualiza las filas
existentes en vez de duplicarlas.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import OrientationVideo  # noqa: E402

OBLIGATORIAS = ("url", "titulo", "tema")
_RIASEC = set("RIASEC")


def _duracion(valor: str) -> Optional[int]:
    """Segundos desde "372" o "6:12" · None si viene vacío o ilegible.

    None no es un error: significa "no la sabemos", y el front no pinta el
    badge. Es mejor que un cero, que se lee como un video de duración cero.
    """
    v = (valor or "").strip()
    if not v:
        return None
    if v.isdigit():
        return int(v)
    m = re.fullmatch(r"(\d+):([0-5]?\d)", v)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _riasec(valor: str) -> Optional[List[str]]:
    """Letras RIASEC válidas, sin repetir · None si no hay ninguna.

    Se descarta en silencio lo que no sea una de las seis letras: un typo no
    puede convertirse en una categoría fantasma que nadie va a ver nunca.
    """
    crudo = re.split(r"[\s,;]+", (valor or "").strip().upper())
    letras = [c for c in crudo if c in _RIASEC]
    vistas: List[str] = []
    for c in letras:
        if c not in vistas:
            vistas.append(c)
    return vistas or None


def _limpio(valor: Optional[str]) -> Optional[str]:
    v = (valor or "").strip()
    return v or None


def leer(ruta: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Devuelve (filas válidas, problemas)."""
    filas: List[Dict[str, Any]] = []
    problemas: List[str] = []
    vistas_url = set()

    with ruta.open(encoding="utf-8-sig", newline="") as fh:
        lector = csv.DictReader(fh)
        faltan = [c for c in OBLIGATORIAS if c not in (lector.fieldnames or [])]
        if faltan:
            problemas.append(
                "al archivo le faltan columnas obligatorias: %s" % ", ".join(faltan)
            )
            return [], problemas

        for i, cruda in enumerate(lector, start=2):  # 2 = primera fila de datos
            url = (cruda.get("url") or "").strip()
            titulo = (cruda.get("titulo") or "").strip()
            tema = (cruda.get("tema") or "").strip()

            if not url or not titulo or not tema:
                problemas.append(f"linea {i}: falta url, titulo o tema · se salta")
                continue
            if not url.startswith(("http://", "https://")):
                problemas.append(f"linea {i}: la url no parece un enlace · se salta")
                continue
            if url in vistas_url:
                problemas.append(f"linea {i}: url repetida en el archivo · se salta")
                continue
            vistas_url.add(url)

            orden = (cruda.get("orden") or "").strip()
            filas.append(
                {
                    "url": url,
                    "title": titulo[:200],
                    "topic": tema[:60],
                    "description": _limpio(cruda.get("descripcion")),
                    "thumbnail_url": _limpio(cruda.get("miniatura")),
                    "duration_seconds": _duracion(cruda.get("duracion", "")),
                    "riasec_codes": _riasec(cruda.get("riasec", "")),
                    "journey_moment": _limpio(cruda.get("momento")),
                    "journey_route": _limpio(cruda.get("ruta")),
                    "sort_order": int(orden) if orden.isdigit() else 0,
                    "is_published": (cruda.get("publicado") or "").strip().lower()
                    not in ("no", "false", "0"),
                }
            )
    return filas, problemas


def aplicar(filas: List[Dict[str, Any]], escribir: bool) -> Tuple[int, int]:
    """(nuevos, actualizados). Sin `escribir`, sólo cuenta."""
    db = SessionLocal()
    nuevos = actualizados = 0
    try:
        for f in filas:
            existente = (
                db.query(OrientationVideo)
                .filter(OrientationVideo.url == f["url"])
                .first()
            )
            if existente is None:
                nuevos += 1
                if escribir:
                    db.add(OrientationVideo(**f))
            else:
                actualizados += 1
                if escribir:
                    for k, v in f.items():
                        setattr(existente, k, v)
        if escribir:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    return nuevos, actualizados


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archivo", help="CSV con los videos")
    ap.add_argument(
        "--aplicar",
        action="store_true",
        help="escribe en la base · sin esto es un simulacro",
    )
    args = ap.parse_args()

    ruta = Path(args.archivo)
    if not ruta.exists():
        print(f"no existe: {ruta}")
        return 1

    filas, problemas = leer(ruta)
    for p in problemas:
        print(f"  aviso · {p}")
    if not filas:
        print("no hay ninguna fila utilizable · no se escribe nada")
        return 1

    nuevos, actualizados = aplicar(filas, escribir=args.aplicar)
    modo = "ESCRITO" if args.aplicar else "simulacro (no se escribio nada)"
    print(f"\n{len(filas)} filas leidas · {nuevos} nuevos · {actualizados} actualizados")
    print(f"modo: {modo}")
    if not args.aplicar:
        print("para escribir de verdad, repite con --aplicar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
