"""Tracking M-001 en el pipeline del recomendador (pendiente post-deploy R1).

Una recomendación fresca dispara DOS llamadas a Claude (perfil consolidado +
recomendación); hasta ahora solo el chat de Hop registraba en `ai_usage_log`,
así que el panel de auditoría subestimaba el costo real. Cubre:

  (a) generate_recommendations registra feature="recommend_programs"
      (éxito Y error · igual que hop_chat: el intento fallido va con
      tokens None para que el panel vea errores).
  (b) generate_or_get_profile registra feature="consolidate_profile"
      (éxito Y error).

SQLite in-memory · patrón de fixture de tests/test_recommendation_catalog_c1.py
y de spy de tests/test_hop_chat.py.
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
        email="tracking.test@grasshopper.dev",
        hashed_password="x",
        name="Tracking Test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_program(db):
    from app.db.models import Program

    p = Program(
        program_id="P-TRACK", name="Ingenieria de Datos", slug="p-track",
        country="Canadá", city="Toronto", institution="Uni Toronto",
        type="pregrado", duration_months=48, cost_total=4000,
        currency="USD", budget_tier="low", active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _profile():
    from app.schemas.consolidated_profile import ConsolidatedProfile

    return ConsolidatedProfile(
        summary_narrative="Perfil de prueba para el tracking del recomendador. " * 6,
        strengths=["Análisis", "Curiosidad", "Persistencia"],
        interests=["datos", "tecnología", "investigación"],
    )


def _seed_cache_row(db, user, profile):
    from app.db.models import ConsolidatedProfileCache

    row = ConsolidatedProfileCache(
        user_id=user.id,
        profile_hash="hash-test",
        profile_data=profile.model_dump(mode="json"),
        recommendations_data=[],
        generated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


_METADATA_OK = {
    "model": "claude-sonnet-4-5",
    "tokens_input": 1200,
    "tokens_output": 300,
    "latency_ms": 950,
}


def _raw_recommendation(program_uuid: str) -> str:
    return json.dumps({
        "recommendations": [{
            "program_id": program_uuid,
            "program_name": "Ingenieria de Datos",
            "why_match": (
                "Tu interés por los datos y tu perfil analítico encajan "
                "directamente con este programa."
            ),
            "match_score": 88,
            "budget_fit": "match",
        }]
    })


# ---------------------------------------------------------------------------
# (a) recomendador · feature="recommend_programs"
# ---------------------------------------------------------------------------

def test_recommender_records_ai_usage(db_session, monkeypatch):
    from app.services import recommendation_service as rs

    user = _seed_user(db_session)
    program = _seed_program(db_session)
    profile = _profile()
    cache_row = _seed_cache_row(db_session, user, profile)

    monkeypatch.setattr(
        rs, "generate_or_get_profile",
        lambda db, u, force_refresh=False: (profile, cache_row, False),
    )
    monkeypatch.setattr(
        rs, "_call_claude_for_recommendations",
        lambda prompt, user_id, **kw: (_raw_recommendation(str(program.id)), dict(_METADATA_OK)),
    )

    calls = []
    monkeypatch.setattr(rs, "record_ai_usage", lambda db, **kw: calls.append(kw))

    _, recs, _, cached = rs.generate_recommendations(db_session, user)

    assert cached is False
    assert len(recs) == 1
    assert len(calls) == 1
    assert calls[0]["feature"] == "recommend_programs"
    assert calls[0]["provider"] == "anthropic"
    assert calls[0]["model"] == "claude-sonnet-4-5"
    assert calls[0]["tokens_input"] == 1200
    assert calls[0]["tokens_output"] == 300
    assert calls[0]["latency_ms"] == 950
    assert calls[0]["user_id"] == user.id


def test_recommender_records_ai_usage_on_error_too(db_session, monkeypatch):
    from app.services import recommendation_service as rs

    user = _seed_user(db_session)
    _seed_program(db_session)
    profile = _profile()
    cache_row = _seed_cache_row(db_session, user, profile)

    monkeypatch.setattr(
        rs, "generate_or_get_profile",
        lambda db, u, force_refresh=False: (profile, cache_row, False),
    )
    monkeypatch.setattr(
        rs, "_call_claude_for_recommendations",
        lambda prompt, user_id, **kw: (None, {"model": "claude-sonnet-4-5", "error": "boom"}),
    )

    calls = []
    monkeypatch.setattr(rs, "record_ai_usage", lambda db, **kw: calls.append(kw))

    with pytest.raises(rs.RecommendationFailure):
        rs.generate_recommendations(db_session, user)

    assert len(calls) == 1
    assert calls[0]["feature"] == "recommend_programs"
    assert calls[0]["tokens_input"] is None
    assert calls[0]["tokens_output"] is None


def test_recommender_cache_hit_does_not_record(db_session, monkeypatch):
    """Cache HIT = cero llamadas a la IA = cero filas en ai_usage_log."""
    from app.services import recommendation_service as rs

    user = _seed_user(db_session)
    program = _seed_program(db_session)
    profile = _profile()
    cache_row = _seed_cache_row(db_session, user, profile)
    cache_row.recommendations_data = json.loads(_raw_recommendation(str(program.id)))["recommendations"]
    db_session.commit()

    monkeypatch.setattr(
        rs, "generate_or_get_profile",
        lambda db, u, force_refresh=False: (profile, cache_row, True),
    )

    calls = []
    monkeypatch.setattr(rs, "record_ai_usage", lambda db, **kw: calls.append(kw))

    _, recs, _, cached = rs.generate_recommendations(db_session, user)

    assert cached is True
    assert calls == []


# ---------------------------------------------------------------------------
# (b) perfil consolidado · feature="consolidate_profile"
# ---------------------------------------------------------------------------

def _fake_inputs():
    return {
        "demographic": {"life_stage": "explorando"},
        "tests": [{"test_id": "holland", "source": "interno", "scores": {"I": 80}}],
        "journey_answers": {},
    }


def test_consolidation_records_ai_usage(db_session, monkeypatch):
    from app.services import consolidation_service as cs

    user = _seed_user(db_session)
    raw = _profile().model_dump_json()

    monkeypatch.setattr(cs, "gather_user_inputs", lambda db, u: _fake_inputs())
    monkeypatch.setattr(
        cs, "_call_claude_for_consolidation",
        lambda prompt, user_id: (raw, dict(_METADATA_OK)),
    )

    calls = []
    monkeypatch.setattr(cs, "record_ai_usage", lambda db, **kw: calls.append(kw))

    _, _, cached = cs.generate_or_get_profile(db_session, user)

    assert cached is False
    assert len(calls) == 1
    assert calls[0]["feature"] == "consolidate_profile"
    assert calls[0]["provider"] == "anthropic"
    assert calls[0]["tokens_input"] == 1200
    assert calls[0]["user_id"] == user.id


def test_consolidation_records_ai_usage_on_error_too(db_session, monkeypatch):
    from app.services import consolidation_service as cs

    user = _seed_user(db_session)

    monkeypatch.setattr(cs, "gather_user_inputs", lambda db, u: _fake_inputs())
    monkeypatch.setattr(
        cs, "_call_claude_for_consolidation",
        lambda prompt, user_id: (None, {"model": "claude-sonnet-4-5", "error": "boom"}),
    )

    calls = []
    monkeypatch.setattr(cs, "record_ai_usage", lambda db, **kw: calls.append(kw))

    with pytest.raises(cs.ConsolidationFailure):
        cs.generate_or_get_profile(db_session, user)

    assert len(calls) == 1
    assert calls[0]["feature"] == "consolidate_profile"
    assert calls[0]["tokens_input"] is None
