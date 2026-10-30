"""K-1 · Sprint 4 · las cuentas de prueba por grado.

Verónica no tenía cómo revisar lo que cambia entre grados: las cuentas
sembradas no tenían grado. `scripts/sembrar_cuentas_por_grado.py` crea una por
ruta (con el onboarding hecho) y tres nuevas. Estos tests protegen que:

 1. Sin `--aplicar` no se escribe nada (la base local es la de producción).
 2. Cada cuenta cae en la ruta que dice, y su onboarding está completo según el
    propio catálogo (si no, la app la mandaría a terminarlo).
 3. No se sincronizan con el CRM ni reciben comunicaciones.
 4. Correrlo dos veces no duplica ni pisa lo que alguien ya hizo con ellas.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import onboarding_hechos as catalogo
from app.db.models import Base, OnboardingStatus, User

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "sembrar_cuentas_por_grado.py"
_spec = importlib.util.spec_from_file_location("sembrar_cuentas_por_grado", _RUTA)
script = importlib.util.module_from_spec(_spec)
# Registrado antes de ejecutarlo: `@dataclass` busca el módulo en sys.modules.
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


def _por_email(db):
    return {u.email: u for u in db.query(User).filter(User.email.like("prueba.%")).all()}


def test_sin_aplicar_no_escribe_nada(db):
    informe = script.sembrar(db, aplicar=False)
    assert {f["accion"] for f in informe} == {"crear"}
    assert _por_email(db) == {}


def test_crea_las_nueve(db):
    script.sembrar(db, aplicar=True)
    assert len(_por_email(db)) == len(script.CUENTAS) == 9


@pytest.mark.parametrize(
    "usuario, ruta_esperada",
    [
        ("grado9", catalogo.RUTA_POR_GRADO["9"]),
        ("grado10", catalogo.RUTA_POR_GRADO["10"]),
        ("grado11", catalogo.RUTA_POR_GRADO["11"]),
        ("grado12", catalogo.RUTA_POR_GRADO["12"]),
        ("profesional", catalogo.RUTA_PROFESIONAL),
        ("universitario", catalogo.RUTA_PROFESIONAL),
    ],
)
def test_cada_cuenta_cae_en_su_ruta_con_el_onboarding_completo(db, usuario, ruta_esperada):
    script.sembrar(db, aplicar=True)
    u = _por_email(db)[f"prueba.{usuario}@grasshopper.dev"]
    respuestas = u.onboarding_answers

    assert catalogo.ruta(respuestas) == ruta_esperada
    assert u.onboarding_status == OnboardingStatus.COMPLETED
    # Lo obligatorio del catálogo está todo: si faltara algo, la app la
    # devolvería a terminar el onboarding.
    obligatorios_pendientes = [
        h for h in catalogo.faltantes(respuestas) if catalogo.es_obligatorio(h, respuestas)
    ]
    assert obligatorios_pendientes == []
    # Las respuestas usan códigos que existen en el catálogo, no texto inventado.
    for clave, valor in respuestas.items():
        h = catalogo.get_hecho(clave)
        if h and h.opciones and isinstance(valor, str):
            assert valor in h.opciones, (clave, valor)


def test_el_grado_queda_en_la_columna_y_no_solo_en_el_json(db):
    script.sembrar(db, aplicar=True)
    cuentas = _por_email(db)
    for grado in (9, 10, 11, 12):
        assert cuentas[f"prueba.grado{grado}@grasshopper.dev"].grade == grado


def test_las_nuevas_arrancan_sin_onboarding(db):
    script.sembrar(db, aplicar=True)
    for n in (1, 2, 3):
        u = _por_email(db)[f"prueba.nuevo{n}@grasshopper.dev"]
        assert u.onboarding_status == OnboardingStatus.NOT_STARTED
        assert u.onboarding_answers == {}


def test_no_van_al_crm_ni_reciben_comunicaciones(db):
    script.sembrar(db, aplicar=True)
    for u in _por_email(db).values():
        assert u.consent_crm_sync_at is None
        assert u.consent_communications_at is None
        assert u.consent_data_processing_at is not None


def test_los_menores_no_quedan_detenidos_en_el_permiso_parental(db):
    script.sembrar(db, aplicar=True)
    for grado in (9, 10, 11, 12):
        u = _por_email(db)[f"prueba.grado{grado}@grasshopper.dev"]
        assert u.consent_parental_at is not None


def test_correrlo_dos_veces_no_duplica_ni_pisa(db):
    script.sembrar(db, aplicar=True)
    u = _por_email(db)["prueba.grado11@grasshopper.dev"]
    u.onboarding_answers = {**u.onboarding_answers, "voice_passion": "lo que escribió quien probó"}
    db.commit()

    informe = script.sembrar(db, aplicar=True)
    assert {f["accion"] for f in informe} == {"ya existe (no se toca)"}
    assert len(_por_email(db)) == 9
    u = _por_email(db)["prueba.grado11@grasshopper.dev"]
    assert u.onboarding_answers["voice_passion"] == "lo que escribió quien probó"


def test_reiniciar_las_devuelve_a_su_estado_inicial(db):
    script.sembrar(db, aplicar=True)
    u = _por_email(db)["prueba.nuevo1@grasshopper.dev"]
    u.onboarding_status = OnboardingStatus.COMPLETED
    u.onboarding_answers = {"life_stage": "working"}
    db.commit()

    script.sembrar(db, aplicar=True, reiniciar=True)
    u = _por_email(db)["prueba.nuevo1@grasshopper.dev"]
    assert u.onboarding_status == OnboardingStatus.NOT_STARTED
    assert u.onboarding_answers == {}
