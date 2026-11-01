"""F-2/F-4 · Sprint 4 · el programa de prueba (recorridos 2026-11-01).

`scripts/sembrar_programa_de_prueba.py` crea una organización tipo programa con
un coordinador y seis participantes, porque en producción no había ninguna y
nadie había podido ver ese panel. Estos tests protegen que:

 1. Sin `--aplicar` no se escribe nada.
 2. La organización es de tipo `programa`, y coordinador y participantes quedan
    enlazados a ella con su rol.
 3. Son al menos 5 participantes: menos, y el tablero anónimo no muestra nada.
 4. Correrlo dos veces no duplica; `--desactivar` apaga sin borrar.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, School, User, UserRole

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "sembrar_programa_de_prueba.py"
_spec = importlib.util.spec_from_file_location("sembrar_programa_de_prueba", _RUTA)
script = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = script
_spec.loader.exec_module(script)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    sesion = sessionmaker(bind=engine)()
    try:
        yield sesion
    finally:
        sesion.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sin_aplicar_no_escribe_nada(db):
    informe = script.sembrar(db, aplicar=False)
    assert db.query(School).count() == 0
    assert db.query(User).count() == 0
    assert all(f["accion"] == "crear" for f in informe)
    assert not any("clave" in f for f in informe)


def test_crea_el_programa_con_su_coordinador_y_participantes(db):
    informe = script.sembrar(db, aplicar=True)
    org = db.query(School).one()
    assert org.tipo == "programa" and org.license_active

    coordinador = db.query(User).filter(User.email == script.COORDINADOR).one()
    assert coordinador.role == UserRole.SCHOOL_ADMIN
    assert coordinador.school_id == org.id

    participantes = db.query(User).filter(User.role == UserRole.STUDENT).all()
    assert len(participantes) >= 5  # mínimo del tablero anónimo
    assert all(p.school_id == org.id for p in participantes)
    # No se sincronizan con el CRM ni reciben correos.
    assert all(p.consent_crm_sync_at is None for p in participantes)
    assert all(p.consent_communications_at is None for p in participantes)

    # Una clave por cuenta creada, y ninguna repetida.
    claves = [f["clave"] for f in informe if "clave" in f]
    assert len(claves) == 1 + len(participantes)
    assert len(set(claves)) == len(claves)


def test_dos_veces_no_duplica_y_desactivar_apaga_sin_borrar(db):
    script.sembrar(db, aplicar=True)
    segunda = script.sembrar(db, aplicar=True)
    assert db.query(School).count() == 1
    assert not any("clave" in f for f in segunda)

    script.sembrar(db, aplicar=True, desactivar=True)
    assert db.query(School).one().license_active is False
    cuentas = db.query(User).all()
    assert cuentas and all(u.is_active is False for u in cuentas)
