"""Pre-filtro de catálogo del análisis IA de leads (_select_catalog_for_lead).

Antes filtraba solo por país + presupuesto y, sin esas señales (lead nuevo),
devolvía los primeros N por orden de inserción → candidatos irrelevantes y no
deterministas. Ahora usa las áreas de interés del lead (area/subject/name),
es determinista (order by program_id) y relaja el filtro progresivamente.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import crm_service as crm


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _prog(db, pid, *, country="Canadá", tier="low", area=None, subject=None, name=None):
    from app.db.models import Program
    p = Program(
        program_id=pid, name=name or f"Programa {pid}", slug=pid.lower(),
        country=country, institution="Inst", type="pregrado",
        area=area, subject=subject, budget_tier=tier, active=True,
    )
    db.add(p)
    db.commit()
    return p


_user_seq = [0]


def _user(db, *, countries=None, budget=None):
    from app.db.models import User
    _user_seq[0] += 1
    u = User(
        email=f"lead{_user_seq[0]}@x.com",
        hashed_password="x", name="Lead",
        preferred_countries=countries or [], budget_band=budget,
    )
    db.add(u)
    db.commit()
    return u


def test_uses_interests_when_no_country_or_budget(db):
    """Sin país/presupuesto, prioriza por interés en vez de orden arbitrario."""
    _prog(db, "P-01", area="Arte")
    _prog(db, "P-02", area="Negocios")
    tech = _prog(db, "P-03", area="Tecnología")

    out = crm._select_catalog_for_lead(db, _user(db), max_n=5, interests=["tecnología"])

    assert [p.program_id for p in out] == ["P-03"]
    assert tech.area == "Tecnología"


def test_interest_matches_name_and_subject(db):
    _prog(db, "P-01", area="Otro", name="Ingeniería de Software")
    _prog(db, "P-02", area="Otro", subject="Diseño Gráfico")
    out = crm._select_catalog_for_lead(db, _user(db), interests=["software"])
    assert [p.program_id for p in out] == ["P-01"]


def test_country_and_budget_still_filter(db):
    _prog(db, "P-CA", country="Canadá", tier="low")
    _prog(db, "P-UK", country="Reino Unido", tier="low")
    _prog(db, "P-CA-HI", country="Canadá", tier="high")

    out = crm._select_catalog_for_lead(
        db, _user(db, countries=["Canadá"], budget="bajo"), max_n=5
    )

    ids = {p.program_id for p in out}
    assert ids == {"P-CA"}  # país Canadá Y tier low (bajo→[low])


def test_deterministic_without_signals(db):
    for pid in ["P-03", "P-01", "P-02"]:
        _prog(db, pid)
    out = crm._select_catalog_for_lead(db, _user(db), max_n=2)
    # order by program_id → P-01, P-02 (determinista, no orden de inserción)
    assert [p.program_id for p in out] == ["P-01", "P-02"]


def test_fallback_relaxes_budget_when_tier_empty(db):
    # País con programas pero ninguno en el tier del presupuesto "bajo" (low).
    _prog(db, "P-01", country="Canadá", tier="high")
    _prog(db, "P-02", country="Canadá", tier="premium")

    out = crm._select_catalog_for_lead(
        db, _user(db, countries=["Canadá"], budget="bajo"), max_n=5
    )

    # No hay low → relaja presupuesto pero conserva el país.
    assert {p.program_id for p in out} == {"P-01", "P-02"}


def test_no_interest_match_falls_back_to_pool(db):
    """Si ningún programa matchea el interés, devuelve el pool determinista."""
    _prog(db, "P-02", area="Arte")
    _prog(db, "P-01", area="Negocios")
    out = crm._select_catalog_for_lead(db, _user(db), max_n=5, interests=["astrofísica"])
    assert [p.program_id for p in out] == ["P-01", "P-02"]
