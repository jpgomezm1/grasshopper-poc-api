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
from typing import Any, Dict, List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Los títulos de las maquetas se cargaron sin tildes ni eñes ("Arquitectura:
# cinco anos y despues que"). Corrección exacta, título por título: solo se
# toca un título que coincide letra por letra con el de la izquierda.
TITULOS: Dict[str, str] = {
    "Un dia en la vida de un desarrollador": "Un día en la vida de un desarrollador",
    "Administracion vs economia: cual me sirve mas": "Administración vs. economía: ¿cuál me sirve más?",
    "Comunicacion social y periodismo hoy": "Comunicación social y periodismo hoy",
    "Como es estudiar salud en el exterior": "Cómo es estudiar salud en el exterior",
    "Musica como carrera: de que se vive": "Música como carrera: ¿de qué se vive?",
    "Un dia en la vida de una analista financiera": "Un día en la vida de una analista financiera",
    "Ingenieria de sistemas no es solo programar": "Ingeniería de sistemas no es solo programar",
    "Ingenieria biomedica: que se hace de verdad": "Ingeniería biomédica: qué se hace de verdad",
    "Enfermeria o medicina: en que se diferencian": "Enfermería o medicina: ¿en qué se diferencian?",
    "Psicologia: mucho mas que consulta": "Psicología: mucho más que consulta",
    "Derecho: como es de verdad el dia a dia": "Derecho: cómo es de verdad el día a día",
    "Civil o mecanica: como elegir entre las dos": "Civil o mecánica: cómo elegir entre las dos",
    "Emprender sin haber estudiado negocios": "Emprender sin haber estudiado negocios",
    "Un dia en la vida de una enfermera": "Un día en la vida de una enfermera",
    "Arquitectura: cinco anos y despues que": "Arquitectura: cinco años, ¿y después qué?",
    "Diseno grafico: del portafolio al primer cliente": "Diseño gráfico: del portafolio al primer cliente",
}


def corregir_titulos(db: Any, *, aplicar: bool) -> List[Tuple[str, str]]:
    """Devuelve (título viejo, título nuevo) de cada video que cambia."""
    from app.db.models import OrientationVideo

    cambios = []
    for v in db.query(OrientationVideo).all():
        nuevo = TITULOS.get(v.title)
        if nuevo and nuevo != v.title:
            cambios.append((v.title, nuevo))
            if aplicar:
                v.title = nuevo
    if aplicar:
        db.commit()
    return cambios


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
        titulos = corregir_titulos(db, aplicar=args.aplicar)
    finally:
        db.close()

    modo = "APLICADO" if args.aplicar else "SIMULACIÓN (nada se escribió · usa --aplicar)"
    print(f"\nVideos de maqueta · {modo}\n")
    print(f"Descripciones «MAQUETA» quitadas: {len(tocados)}")
    for titulo, desc in tocados:
        print(f"  · {titulo}  ←  quitaba: «{desc}»")
    print(f"\nTítulos con tildes: {len(titulos)}")
    for viejo, nuevo in titulos:
        print(f"  · {viejo}  →  {nuevo}")


if __name__ == "__main__":
    main()
