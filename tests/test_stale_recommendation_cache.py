"""Cache stale de recomendaciones (pendiente post-deploy R1).

El cache de recomendaciones vive en consolidated_profiles y solo se invalida
cuando cambian los inputs del estudiante — un cambio de CATÁLOGO no lo toca.
Tras C1 (catálogo real), los usuarios con recomendaciones generadas sobre el
demo las seguían viendo hasta force_refresh. Ahora el cache-hit valida que
cada program_id cacheado resuelva a un programa ACTIVO del catálogo vigente:

  (a) cache con ids demo (slugs) + catálogo real cargado → STALE → regenera.
  (b) cache con UUIDs reales activos → HIT (no llama a la IA).
  (c) cache apuntando a un programa desactivado después → STALE → regenera.
  (d) modo demo (tabla programs vacía) · ids del catálogo estático → HIT.

SQLite in-memory · patrón de tests/test_recommendation_catalog_c1.py.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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

def _seed_user(db):
    from app.db.models import User

    user = User(
        email="stale.cache@grasshopper.dev",
        hashed_password="x",
        name="Stale Cache Test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_program(db, *, active=True, program_id="P-STALE", slug="p-stale"):
    from app.db.models import Program

    p = Program(
        program_id=program_id, name="Ingenieria de Datos", slug=slug,
        country="Canadá", city="Toronto", institution="Uni Toronto",
        type="pregrado", duration_months=48, cost_total=4000,
        currency="USD", budget_tier="low", active=active,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _profile():
    from app.schemas.consolidated_profile import ConsolidatedProfile

    return ConsolidatedProfile(
        summary_narrative="Perfil de prueba para el cache stale del recomendador. " * 5,
        strengths=["Análisis", "Curiosidad", "Persistencia"],
        interests=["datos", "tecnología", "investigación"],
    )


def _rec_dict(program_id: str) -> dict:
    return {
        "program_id": program_id,
        "program_name": "Programa Cacheado",
        "why_match": (
            "Tu perfil analítico y tus intereses encajan directamente con "
            "este programa de prueba."
        ),
        "match_score": 90,
        "budget_fit": "match",
    }


def _seed_cache_row(db, user, profile, rec_program_ids):
    from app.db.models import ConsolidatedProfileCache

    row = ConsolidatedProfileCache(
        user_id=user.id,
        profile_hash="hash-test",
        profile_data=profile.model_dump(mode="json"),
        recommendations_data=[_rec_dict(pid) for pid in rec_program_ids],
        generated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _setup(db, monkeypatch, rec_program_ids, fresh_program_uuid=None):
    """Monta el pipeline con perfil cacheado + spy sobre la llamada IA.

    Devuelve (rs, user, calls) — calls acumula 1 entrada por llamada a la IA.
    La IA fake recomienda fresh_program_uuid (necesario solo si el test espera
    regeneración).
    """
    from app.services import recommendation_service as rs

    user = _seed_user(db)
    profile = _profile()
    cache_row = _seed_cache_row(db, user, profile, rec_program_ids)

    monkeypatch.setattr(
        rs, "generate_or_get_profile",
        lambda db_, u, force_refresh=False: (profile, cache_row, True),
    )

    calls = []

    def _fake_ai(prompt, user_id, **kw):
        calls.append(user_id)
        raw = json.dumps({"recommendations": [_rec_dict(str(fresh_program_uuid))]})
        return raw, {"model": "claude-sonnet-4-5"}

    monkeypatch.setattr(rs, "_call_claude_for_recommendations", _fake_ai)
    return rs, user, calls


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------

def test_demo_ids_with_real_catalog_regenerate(db_session, monkeypatch):
    """(a) Cache del catálogo demo (slugs) + tabla Program cargada → regenera."""
    program = _seed_program(db_session)
    rs, user, calls = _setup(
        db_session, monkeypatch,
        rec_program_ids=["seed-administracion-de-empresas-041"],
        fresh_program_uuid=program.id,
    )

    _, recs, _, cached = rs.generate_recommendations(db_session, user)

    assert cached is False
    assert len(calls) == 1
    assert recs[0].program_id == str(program.id)


def test_valid_real_ids_cache_hit(db_session, monkeypatch):
    """(b) Cache con UUIDs reales activos → HIT sin llamada IA."""
    program = _seed_program(db_session)
    rs, user, calls = _setup(
        db_session, monkeypatch,
        rec_program_ids=[str(program.id)],
    )

    _, recs, _, cached = rs.generate_recommendations(db_session, user)

    assert cached is True
    assert calls == []
    assert recs[0].program_id == str(program.id)


def test_deactivated_program_regenerates(db_session, monkeypatch):
    """(c) El programa cacheado fue desactivado → STALE → regenera."""
    retired = _seed_program(db_session, active=False, program_id="P-OLD", slug="p-old")
    fresh = _seed_program(db_session, program_id="P-NEW", slug="p-new")
    rs, user, calls = _setup(
        db_session, monkeypatch,
        rec_program_ids=[str(retired.id)],
        fresh_program_uuid=fresh.id,
    )

    _, recs, _, cached = rs.generate_recommendations(db_session, user)

    assert cached is False
    assert len(calls) == 1
    assert recs[0].program_id == str(fresh.id)


def test_demo_mode_demo_ids_cache_hit(db_session, monkeypatch):
    """(d) Tabla programs vacía (modo demo) · ids del catálogo estático → HIT."""
    from app.data.ofertas import get_all_ofertas

    demo_id = get_all_ofertas()[0]["id"]
    rs, user, calls = _setup(
        db_session, monkeypatch,
        rec_program_ids=[demo_id],
    )

    _, recs, _, cached = rs.generate_recommendations(db_session, user)

    assert cached is True
    assert calls == []
    assert recs[0].program_id == demo_id
