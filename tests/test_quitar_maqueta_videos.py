"""El script que quita "MAQUETA" de la descripción de los videos de muestra.

Protege que: sin `--aplicar` no escribe; solo toca la descripción de los videos
que dicen "maqueta", y deja intactos el resto de campos y los demás videos.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, OrientationVideo

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "quitar_maqueta_videos.py"
_spec = importlib.util.spec_from_file_location("quitar_maqueta_videos", _RUTA)
script = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = script
_spec.loader.exec_module(script)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        OrientationVideo(url="https://youtu.be/a", title="Psicología", topic="Salud", stage="Descubre",
                         description="MAQUETA · el video real lo sube Verónica", is_published=True),
        OrientationVideo(url="https://youtu.be/b", title="Derecho", topic="Leyes",
                         description="Un día en un juzgado.", is_published=True),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sin_aplicar_no_escribe(db):
    assert [t for t, _ in script.limpiar(db, aplicar=False)] == ["Psicología"]
    assert db.query(OrientationVideo).filter_by(title="Psicología").one().description.startswith("MAQUETA")


def test_aplicar_solo_quita_la_descripcion_de_la_maqueta(db):
    script.limpiar(db, aplicar=True)
    psico = db.query(OrientationVideo).filter_by(title="Psicología").one()
    assert psico.description is None
    assert (psico.topic, psico.stage, psico.is_published) == ("Salud", "Descubre", True)
    assert db.query(OrientationVideo).filter_by(title="Derecho").one().description == "Un día en un juzgado."


def test_corrige_solo_los_titulos_que_coinciden_exacto(db):
    db.add(OrientationVideo(url="https://youtu.be/c", title="Arquitectura: cinco anos y despues que", topic="Arte"))
    db.commit()
    cambios = script.corregir_titulos(db, aplicar=True)
    assert cambios == [("Arquitectura: cinco anos y despues que", "Arquitectura: cinco años, ¿y después qué?")]
    # Lo que no está en la lista no se toca.
    assert db.query(OrientationVideo).filter_by(url="https://youtu.be/b").one().title == "Derecho"
