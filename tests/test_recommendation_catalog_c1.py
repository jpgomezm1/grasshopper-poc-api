"""Fase C/C1 · recomendador IA sobre el catálogo real (tabla Program).

Cubre la migración del recomendador del catálogo DEMO estático
(`app/data/ofertas.py`) a la tabla real `programs` (2.511 en prod, con
cost_total/duration_months/budget_tier NULL = "a confirmar"):

  (a) get_catalog_for_recommender: solo activos, shape de oferta demo
      (countries lista, category mapeada, cost None-safe, tier es→None).
  (b) _budget_match_kind: costo + tier NULL → 'unknown' (ni barato ni caro).
  (c) filter_catalog con catálogo real no explota; costo NULL recibe score
      neutro (0.7 · entre under=0.5 y match=1.0) vía hint 'unknown'.
  (d) _format_catalog_block: NULL → "a confirmar", jamás "None-None USD".
  (e) Fallback al demo estático con DB vacía (con warning).
  (f) Mapeo RIASEC corregido: puntúa categorías REALES (voluntariado para S
      estaba muerto antes — comparaba contra 'volunteer'/'language' que no
      existen; work_travel para R sigue vivo).
  (g) F-003 · scholarships_for_latam fluye columna → catálogo → slim dict.
  (h) validate_against_catalog normaliza budget_fit='unknown' → 'match'
      (el schema solo acepta under|match|stretch).

SQLite in-memory (sin Postgres) · patrón de fixture derivado de
tests/test_programs_import_scholarships_f003.py (sin TestClient: se
testean los servicios directo).
"""
from __future__ import annotations

import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Fixture · SQLite in-memory + Session directa (sin TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(monkeypatch):
    sqlite_url = "sqlite:///:memory:"
    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setenv("DATABASE_URL", sqlite_url)

    from app.db.models import Base
    Base.metadata.create_all(bind=engine)

    # El catálogo real se cachea módulo-level (TTL 5 min) · resetear para que
    # cada test vea SU DB y no la del test anterior.
    from app.services.catalog_service import invalidate_catalog_cache
    invalidate_catalog_cache()

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        invalidate_catalog_cache()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_programs(db):
    """5 activos variados + 1 inactivo. Algunos con financieros NULL."""
    from app.db.models import Program

    rows = [
        # Completo · pregrado (→ carrera_completa) · tier low → bajo
        Program(
            program_id="P-FULL", name="Ingenieria Ambiental", slug="p-full",
            country="Canadá", city="Toronto", institution="Uni Toronto",
            type="pregrado", duration_months=48, cost_total=4000,
            currency="USD", budget_tier="low",
            language_requirement="IELTS 6.5 (B2 intermedio)",
            tags=["ambiental"], active=True,
        ),
        # Financieros NULL ("a confirmar") · intercambio (→ semestre_academico)
        Program(
            program_id="P-NULLS", name="Semestre en Berlin", slug="p-nulls",
            country="Alemania", city="Berlin", institution="Uni Berlin",
            type="intercambio", duration_months=None, cost_total=None,
            budget_tier=None, language_requirement=None,
            tags=None, scholarships_for_latam=None, active=True,
        ),
        # F-003 · beca LatAm curada en True · maestria (→ carrera_completa)
        Program(
            program_id="P-BECA", name="Maestria en Datos", slug="p-beca",
            country="España", city="Madrid", institution="Uni Madrid",
            type="maestria", duration_months=18, cost_total=12000,
            currency="USD", budget_tier="medium",
            scholarships_for_latam=True, active=True,
        ),
        # Tier premium (→ alto) · diplomado (→ certificacion_corta)
        Program(
            program_id="P-PREMIUM", name="Diplomado Finanzas", slug="p-premium",
            country="Suiza", city="Zurich", institution="Inst Zurich",
            type="diplomado", duration_months=6, cost_total=30000,
            currency="USD", budget_tier="premium", active=True,
        ),
        # Vacacional (→ curso_idiomas) · costo bajo
        Program(
            program_id="P-IDIOMA", name="Frances Intensivo", slug="p-idioma",
            country="Francia", city="Lyon", institution="Alliance Lyon",
            type="vacacional", duration_months=2, cost_total=1500,
            currency="USD", budget_tier="low", active=True,
        ),
        # Inactivo · NO debe salir
        Program(
            program_id="P-INACTIVE", name="Programa Retirado", slug="p-inactive",
            country="Chile", institution="Uni X",
            type="pregrado", cost_total=2000, active=False,
        ),
    ]
    db.add_all(rows)
    db.commit()
    return rows


def _user(**kw):
    """User NO persistido · filter_catalog solo lee atributos."""
    from app.db.models import User

    defaults = dict(
        budget_band=None, budget_max_usd=None,
        preferred_countries=[], english_cefr_level=None,
    )
    defaults.update(kw)
    return User(**defaults)


def _profile(holland=None, interests=None):
    from app.schemas.consolidated_profile import ConsolidatedProfile, HollandCode

    labels = {"R": "Realista", "I": "Investigador", "A": "Artístico",
              "S": "Social", "E": "Emprendedor", "C": "Convencional"}
    return ConsolidatedProfile(
        summary_narrative=(
            "Perfil de prueba para el recomendador C1. " * 6
        ),
        strengths=["Análisis", "Curiosidad", "Persistencia"],
        # Tokens que no matchean nada del catálogo (aislar el scoring RIASEC)
        interests=interests or ["Zetaxia", "Yumbral", "Wolframio"],
        holland_codes=[
            HollandCode(code=c, label=labels[c], score=80.0)
            for c in (holland or [])
        ],
    )


def _demo_oferta(oid, category):
    """Oferta shape demo · neutral en todo menos category."""
    return {
        "id": oid, "slug": oid, "name": f"Programa {oid}",
        "shortDescription": "", "category": category, "tags": [],
        "countries": ["España"],
        "duration": {"min": 1, "max": 2, "type": "meses"},
        "cost": {"min": 1000, "max": 1000, "currency": "USD"},
        "budgetTier": "medio",
        "eligibility": {"languageRequirement": "ninguno"},
        "scholarshipsForLatam": False, "active": True,
    }


# ---------------------------------------------------------------------------
# (a) get_catalog_for_recommender · solo activos + shape
# ---------------------------------------------------------------------------

def test_catalog_only_active_with_demo_shape(db_session):
    from app.services.catalog_service import get_catalog_for_recommender

    _seed_programs(db_session)
    catalog = get_catalog_for_recommender(db_session, use_cache=False)

    by_pid = {c["program_id"]: c for c in catalog}
    assert len(catalog) == 5
    assert "P-INACTIVE" not in by_pid

    full = by_pid["P-FULL"]
    # countries SIEMPRE lista (shape demo)
    assert full["countries"] == ["Canadá"]
    assert full["category"] == "carrera_completa"          # pregrado →
    assert full["budgetTier"] == "bajo"                     # low →
    assert full["cost"] == {"min": 4000, "max": 4000, "currency": "USD"}
    assert full["duration"] == {"min": 48, "max": 48, "type": "meses"}
    # heurística de idioma (texto libre → nivel)
    assert full["eligibility"]["languageRequirement"] == "intermedio"
    assert full["active"] is True

    nulls = by_pid["P-NULLS"]
    assert nulls["category"] == "semestre_academico"        # intercambio →
    # NULL = "a confirmar" → None honesto, sin inventar
    assert nulls["cost"]["min"] is None and nulls["cost"]["max"] is None
    assert nulls["cost"]["currency"] == "USD"               # default columna
    assert nulls["duration"]["min"] is None
    assert nulls["budgetTier"] is None
    assert nulls["eligibility"]["languageRequirement"] == "ninguno"
    assert nulls["tags"] == []                              # JSON NULL → []
    assert nulls["scholarshipsForLatam"] is False           # None → False

    assert by_pid["P-PREMIUM"]["budgetTier"] == "alto"      # premium →
    assert by_pid["P-PREMIUM"]["category"] == "certificacion_corta"
    assert by_pid["P-IDIOMA"]["category"] == "curso_idiomas"


# ---------------------------------------------------------------------------
# (b) _budget_match_kind · NULL → 'unknown'
# ---------------------------------------------------------------------------

def test_budget_match_kind_unknown_when_cost_and_tier_null():
    from app.services.recommendation_service import _budget_match_kind

    oferta_null = {
        "cost": {"min": None, "max": None, "currency": "USD"},
        "budgetTier": None,
    }
    # Con techo numérico, sin techo y sin band: siempre 'unknown'
    assert _budget_match_kind(oferta_null, None, 5000) == "unknown"
    assert _budget_match_kind(oferta_null, "bajo", None) == "unknown"
    assert _budget_match_kind(oferta_null, None, None) == "unknown"

    # Costo NULL pero tier curado → compara por tier (no 'unknown')
    oferta_tier = {
        "cost": {"min": None, "max": None, "currency": "USD"},
        "budgetTier": "medio",
    }
    assert _budget_match_kind(oferta_tier, "medio", None) == "match"
    assert _budget_match_kind(oferta_tier, "alto", None) == "under"

    # Costo conocido sigue siendo numérico
    oferta_cost = {"cost": {"min": 4000, "max": 4000, "currency": "USD"}}
    assert _budget_match_kind(oferta_cost, None, 5000) == "match"
    assert _budget_match_kind(oferta_cost, None, 2000) == "stretch"


# ---------------------------------------------------------------------------
# (c) filter_catalog con catálogo real · costo NULL = score neutro
# ---------------------------------------------------------------------------

def test_filter_catalog_real_catalog_null_cost_is_neutral(db_session):
    from app.services.catalog_service import get_catalog_for_recommender
    from app.services.recommendation_service import filter_catalog

    _seed_programs(db_session)
    catalog = get_catalog_for_recommender(db_session, use_cache=False)

    user = _user(budget_max_usd=5000)
    slim = filter_catalog(user, _profile(), catalog=catalog)
    by_name = {s["program_name"]: s for s in slim}

    # No explota y los NULL llegan con hint honesto 'unknown'
    assert by_name["Semestre en Berlin"]["_budget_fit_hint"] == "unknown"
    # match (1.0) ordena por encima de unknown (0.7): neutro, no premiado
    names = [s["program_name"] for s in slim]
    assert names.index("Ingenieria Ambiental") < names.index("Semestre en Berlin")
    # ... pero unknown NO se castiga como stretch (sigue en la lista)
    assert "Semestre en Berlin" in by_name


# ---------------------------------------------------------------------------
# (d) _format_catalog_block · "a confirmar", jamás "None"
# ---------------------------------------------------------------------------

def test_format_catalog_block_renders_a_confirmar(db_session):
    from app.services.catalog_service import get_catalog_for_recommender
    from app.services.recommendation_service import (
        _format_catalog_block,
        filter_catalog,
    )

    _seed_programs(db_session)
    catalog = get_catalog_for_recommender(db_session, use_cache=False)
    slim = filter_catalog(_user(), _profile(), catalog=catalog)
    block = _format_catalog_block(slim)

    assert "None" not in block
    # P-NULLS: costo + duración + tier a confirmar
    nulls_line = next(l for l in block.splitlines() if "Semestre en Berlin" in l)
    assert "costo=a confirmar" in nulls_line
    assert "duración=a confirmar" in nulls_line
    assert "budget_tier=a confirmar" in nulls_line
    # Los completos siguen renderizando números
    full_line = next(l for l in block.splitlines() if "Ingenieria Ambiental" in l)
    assert "costo=4000-4000 USD" in full_line
    assert "duración=48-48 meses" in full_line


# ---------------------------------------------------------------------------
# (e) Fallback al demo estático con DB vacía
# ---------------------------------------------------------------------------

def test_fallback_to_demo_catalog_when_db_empty(db_session, caplog):
    from app.services.recommendation_service import _get_catalog_source

    with caplog.at_level(logging.WARNING, logger="app.services.recommendation_service"):
        catalog = _get_catalog_source(db_session)

    # Demo estático · ids "oferta-N"
    assert len(catalog) > 0
    assert all(str(o["id"]).startswith("oferta-") for o in catalog)
    assert any("fallback al catálogo demo" in r.message for r in caplog.records)


def test_no_fallback_when_db_seeded(db_session, caplog):
    from app.services.recommendation_service import _get_catalog_source

    _seed_programs(db_session)
    with caplog.at_level(logging.WARNING, logger="app.services.recommendation_service"):
        catalog = _get_catalog_source(db_session)

    assert len(catalog) == 5
    assert not any("fallback" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# (f) Mapeo RIASEC corregido · categorías reales
# ---------------------------------------------------------------------------

def test_riasec_social_scores_voluntariado(db_session):
    """S → voluntariado estaba MUERTO antes (comparaba contra 'volunteer').

    Dos ofertas idénticas salvo category; el voluntariado va segundo en el
    input para que solo el bonus RIASEC pueda ponerlo primero (sort estable).
    """
    from app.services.recommendation_service import filter_catalog

    catalog = [
        _demo_oferta("of-carrera", "carrera_completa"),
        _demo_oferta("of-volun", "voluntariado"),
    ]
    slim = filter_catalog(_user(), _profile(holland=["S"]), catalog=catalog)
    assert [s["program_id"] for s in slim] == ["of-volun", "of-carrera"]

    # Control: sin código S, el empate respeta el orden de entrada
    slim_neutral = filter_catalog(_user(), _profile(), catalog=catalog)
    assert [s["program_id"] for s in slim_neutral] == ["of-carrera", "of-volun"]


def test_riasec_realista_scores_work_travel(db_session):
    from app.services.recommendation_service import filter_catalog

    catalog = [
        _demo_oferta("of-idiomas", "curso_idiomas"),
        _demo_oferta("of-wt", "work_travel"),
    ]
    slim = filter_catalog(_user(), _profile(holland=["R"]), catalog=catalog)
    assert slim[0]["program_id"] == "of-wt"


def test_riasec_investigador_scores_carrera_completa(db_session):
    """I → carrera_completa/semestre_academico (antes: 'academic', muerto)."""
    from app.services.recommendation_service import filter_catalog

    catalog = [
        _demo_oferta("of-wt", "work_travel"),
        _demo_oferta("of-carrera", "carrera_completa"),
    ]
    slim = filter_catalog(_user(), _profile(holland=["I"]), catalog=catalog)
    assert slim[0]["program_id"] == "of-carrera"


# ---------------------------------------------------------------------------
# (g) F-003 · becas LatAm fluye columna → slim dict
# ---------------------------------------------------------------------------

def test_scholarships_flag_flows_to_slim_dict(db_session):
    from app.services.catalog_service import get_catalog_for_recommender
    from app.services.recommendation_service import filter_catalog

    _seed_programs(db_session)
    catalog = get_catalog_for_recommender(db_session, use_cache=False)

    beca = next(c for c in catalog if c["program_id"] == "P-BECA")
    assert beca["scholarshipsForLatam"] is True

    slim = filter_catalog(_user(), _profile(), catalog=catalog)
    slim_beca = next(s for s in slim if s["program_name"] == "Maestria en Datos")
    assert slim_beca["scholarships_for_latam"] is True
    # y las demás no inventan beca
    slim_full = next(s for s in slim if s["program_name"] == "Ingenieria Ambiental")
    assert slim_full["scholarships_for_latam"] is False


# ---------------------------------------------------------------------------
# (h) validate_against_catalog · hint 'unknown' no rompe el schema
# ---------------------------------------------------------------------------

def test_validate_normalizes_unknown_budget_fit():
    from app.services.recommendation_service import validate_against_catalog

    catalog_slim = [{
        "program_id": "uuid-1", "program_slug": "p-1",
        "program_name": "Semestre en Berlin",
        "countries": ["Alemania"], "budget_tier": None,
        "_budget_fit_hint": "unknown",
    }]
    raw = [{
        "program_id": "uuid-1",
        "program_name": "Semestre en Berlin",
        "why_match": "Tu perfil investigador encaja con el semestre académico en Berlín.",
        "match_score": 78,
        # La IA copió el hint tal cual · el schema solo acepta under|match|stretch
        "budget_fit": "unknown",
        "matching_dimensions": ["Investigador"],
    }]
    valid, dropped = validate_against_catalog(raw, catalog_slim)
    assert dropped == []
    assert len(valid) == 1
    assert valid[0].budget_fit == "match"
