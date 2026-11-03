"""Dos generaciones del perfil consolidado a la vez · verificación en producción 2026-11-02.

Con `prueba.grado10`, al abrir Mi perfil la pantalla mostró un `UniqueViolation`
de `ix_consolidated_profiles_user_id` con el SQL incluido: dos peticiones vieron
"no hay fila", las dos generaron con la IA y la segunda chocó al guardar.

Protege que:
  1. Si otra petición ya guardó la fila mientras esta generaba, esta la actualiza
     en vez de reventar.
  2. Un error cualquiera del trabajo de fondo no llega crudo a la pantalla.
"""
from __future__ import annotations

from datetime import datetime

from tests.test_ai_usage_tracking_recommender import (  # noqa: F401
    _METADATA_OK, _fake_inputs, _profile, _seed_user, db_session,
)


def test_si_otra_peticion_ya_guardo_la_fila_se_actualiza_sin_reventar(db_session, monkeypatch):
    from app.db.models import ConsolidatedProfileCache
    from app.services import consolidation_service as cs

    user = _seed_user(db_session)
    raw = _profile().model_dump_json()
    monkeypatch.setattr(cs, "gather_user_inputs", lambda db, u: _fake_inputs())
    monkeypatch.setattr(cs, "record_ai_usage", lambda db, **kw: None)

    def ia_lenta(prompt, user_id):
        # Mientras "esta" petición espera a la IA, la "otra" guarda su fila,
        # por fuera de la sesión de esta (como en producción).
        from sqlalchemy.orm import sessionmaker
        otra = sessionmaker(bind=db_session.get_bind())()
        otra.add(ConsolidatedProfileCache(
            user_id=user.id, profile_hash="de-la-otra", profile_data=_profile().model_dump(mode="json"),
            recommendations_data=[], generated_at=datetime.utcnow(),
        ))
        otra.commit()
        otra.close()
        return raw, dict(_METADATA_OK)

    monkeypatch.setattr(cs, "_call_claude_for_consolidation", ia_lenta)

    profile, row, cached = cs.generate_or_get_profile(db_session, user)

    assert cached is False
    assert profile.tests_used == ["holland"]
    filas = db_session.query(ConsolidatedProfileCache).filter_by(user_id=user.id).all()
    assert len(filas) == 1
    assert filas[0].profile_hash == cs.hash_inputs(_fake_inputs())  # quedó el resultado de esta


def test_un_error_cualquiera_del_trabajo_de_fondo_no_llega_crudo(monkeypatch):
    from app.api.v1 import recommendations as rec

    class _Sesion:
        def query(self, *_a, **_k):
            raise RuntimeError('(psycopg2.errors.UniqueViolation) duplicate key ... [SQL: INSERT ...]')

        def close(self):
            pass

    monkeypatch.setattr(rec, "SessionLocal", lambda: _Sesion())
    rec._FAILURES.clear()
    rec._run_generation_bg("00000000-0000-0000-0000-000000000001", 5, False)
    mensaje = rec._FAILURES["00000000-0000-0000-0000-000000000001"]
    assert "SQL" not in mensaje and "psycopg2" not in mensaje
    assert "reintenta" in mensaje
    rec._FAILURES.clear()
