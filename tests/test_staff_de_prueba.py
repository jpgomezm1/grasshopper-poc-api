"""Las cuentas de prueba del staff · auditoría de producción (2026-11-02).

Protege que:
 1. Sin `--aplicar` no se escribe nada.
 2. Cada cuenta queda con su rol; las de colegio, enlazadas al colegio de prueba
    (tipo colegio); y el acudiente, ligado al estudiante.
 3. Correrlo dos veces no duplica; `--desactivar` apaga sin borrar.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, ParentRelationship, School, User, UserRole

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "sembrar_staff_de_prueba.py"
_spec = importlib.util.spec_from_file_location("sembrar_staff_de_prueba", _RUTA)
script = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = script
_spec.loader.exec_module(script)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    sesion = sessionmaker(bind=engine)()
    try:
        yield sesion
    finally:
        sesion.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _u(db, usuario):
    return db.query(User).filter(User.email == f"prueba.{usuario}@grasshopper.dev").first()


def test_sin_aplicar_no_escribe(db):
    informe = script.sembrar(db, aplicar=False)
    assert db.query(User).count() == 0 and db.query(School).count() == 0
    assert all(f["accion"] == "crear" for f in informe)


def test_crea_cada_rol_y_el_colegio(db):
    informe = script.sembrar(db, aplicar=True)
    assert all(f.get("clave", "Prueba-").startswith("Prueba-") for f in informe)
    colegio = db.query(School).filter(School.slug == script.SLUG).one()
    assert colegio.tipo == "colegio" and colegio.license_active
    roles = {
        "admin": UserRole.SUPER_ADMIN, "comercial": UserRole.GH_COMMERCIAL, "asesor": UserRole.GH_ADVISOR,
        "colegio.admin": UserRole.SCHOOL_ADMIN, "psicologa": UserRole.PSYCHOLOGIST,
        "acudiente": UserRole.PARENT, "colegio.estudiante": UserRole.STUDENT,
    }
    for usuario, rol in roles.items():
        u = _u(db, usuario)
        assert u is not None and u.role == rol, usuario
    for usuario in ("colegio.admin", "psicologa", "colegio.estudiante"):
        assert _u(db, usuario).school_id == colegio.id, usuario
    for usuario in ("admin", "comercial", "asesor"):
        assert _u(db, usuario).school_id is None, usuario
    rel = db.query(ParentRelationship).one()
    assert rel.parent_user_id == _u(db, "acudiente").id
    assert rel.student_user_id == _u(db, "colegio.estudiante").id
    assert _u(db, "colegio.estudiante").grade == 11


def test_dos_veces_no_duplica_y_desactivar_apaga(db):
    script.sembrar(db, aplicar=True)
    total = db.query(User).count()
    segunda = script.sembrar(db, aplicar=True)
    assert db.query(User).count() == total
    assert not any(f.get("clave") for f in segunda)
    script.sembrar(db, aplicar=True, desactivar=True)
    assert db.query(User).filter(User.is_active.is_(True)).count() == 0
    assert db.query(User).count() == total
    assert not db.query(School).filter(School.slug == script.SLUG).one().license_active


def test_solo_agencia_deja_activo_el_colegio_de_prueba(db):
    script.sembrar(db, aplicar=True)
    script.sembrar(db, aplicar=True, desactivar=True, solo_agencia=True)
    for usuario in ("admin", "comercial", "asesor"):
        assert not _u(db, usuario).is_active, usuario
    for usuario in ("colegio.admin", "psicologa", "acudiente", "colegio.estudiante"):
        assert _u(db, usuario).is_active, usuario
    assert db.query(School).filter(School.slug == script.SLUG).one().license_active
