"""Quita la descripción de relleno de los videos de maqueta · UI con vida (2026-11-02).

Los 16 videos de orientación que hay en producción son maquetas: los cargó el
equipo con `cargar_videos.py` para que Verónica viera la ruta armada, con la
descripción "MAQUETA · el video real lo sube Verónica". Esa descripción la ven
los estudiantes debajo de cada título.

Decisión de JP (2026-11-02): **dejar los videos visibles como ejemplo de la
ruta, pero sin la palabra MAQUETA.**

## Por qué un script aparte y no `cargar_videos.py`

`cargar_videos.py` actualiza por URL y escribe TODOS los campos de la fila: con
un CSV incompleto pondría en blanco el tema, la etapa, el orden o el momento de
cada video. Este solo toca `description`, y solo de los videos cuya
descripción dice "maqueta".

Uso (lo corre JP en producción):

    heroku run -a grasshopper-api "python scripts/quitar_maqueta_videos.py"            # simula
    heroku run -a grasshopper-api "python scripts/quitar_maqueta_videos.py --aplicar"  # escribe
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def limpiar(db: Any, *, aplicar: bool) -> List[Tuple[str, str]]:
    """Devuelve (título, descripción que tenía) de cada video tocado."""
    from app.db.models import OrientationVideo

    tocados = []
    for v in db.query(OrientationVideo).all():
        if v.description and "maqueta" in v.description.lower():
            tocados.append((v.title, v.description))
            if aplicar:
                v.description = None
    if aplicar:
        db.commit()
    return tocados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aplicar", action="store_true", help="escribir (si no, solo muestra)")
    args = parser.parse_args()

    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        tocados = limpiar(db, aplicar=args.aplicar)
    finally:
        db.close()

    modo = "APLICADO" if args.aplicar else "SIMULACIÓN (nada se escribió · usa --aplicar)"
    print(f"\nVideos de maqueta · {modo} · {len(tocados)} videos\n")
    for titulo, desc in tocados:
        print(f"  · {titulo}  ←  quitaba: «{desc}»")


if __name__ == "__main__":
    main()
