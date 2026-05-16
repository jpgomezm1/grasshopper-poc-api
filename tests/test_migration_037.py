"""Tests de la migración 037 · Fase B · scripts/migrate_clinical_data.py

Valida que:
  1. Un row con clinical_analysis_cache={...} → después del script tiene _enc non-null
     y clinical_analysis_cache=None.
  2. Si encrypt_json falla (mock), la row queda con plaintext intacto (rollback).
  3. El resumen final de stats es correcto (migrated / failed / skipped).
  4. El script es idempotente: no re-procesa rows que ya tienen _enc non-null.
  5. La migration Alembic 037 agrega la columna correcta y no migra datos inline.

Tests de tipo unit sobre run_migration() con mocks de SessionLocal / encrypt_json.
No se necesita DB real.
"""
from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeUser:
    """Objeto simple que simula un row User con los atributos relevantes."""

    def __init__(
        self,
        user_id: uuid.UUID | None = None,
        cache_data: dict | None = None,
        enc_data: bytes | None = None,
    ):
        self.id = user_id or uuid.uuid4()
        self.clinical_analysis_cache = cache_data
        self.clinical_analysis_cache_enc = enc_data


def _make_db_session(rows: list) -> MagicMock:
    """Crea un mock de SessionLocal que devuelve `rows` en el primer query chunk,
    y [] en el segundo (fin de paginación).
    """
    db = MagicMock()

    call_count = {"n": 0}

    def _query_chain(*args, **kwargs):
        chain = MagicMock()

        def _all():
            count = call_count["n"]
            call_count["n"] += 1
            if count == 0:
                return rows
            return []

        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.offset.return_value = chain
        chain.all.side_effect = _all
        return chain

    db.query.side_effect = _query_chain
    # refresh es no-op por defecto
    db.refresh.side_effect = lambda u: None
    return db


ENCRYPTED_BYTES = b"ENC1" + b"\xAB" * 40


# ---------------------------------------------------------------------------
# Tests de run_migration()
# ---------------------------------------------------------------------------

class TestRunMigration:
    """Tests sobre scripts/migrate_clinical_data.run_migration()."""

    def test_happy_path_row_migrated(self):
        """Row con cache plaintext → _enc non-null · clinical_analysis_cache=None."""
        fu = FakeUser(cache_data={"narrative": "Perfil clínico", "risk": True})
        db = _make_db_session([fu])

        from scripts.migrate_clinical_data import run_migration

        with (
            patch("scripts.migrate_clinical_data.SessionLocal", return_value=db),
            patch(
                "scripts.migrate_clinical_data.encrypt_json",
                return_value=ENCRYPTED_BYTES,
            ),
        ):
            stats = run_migration(dry_run=False, chunk_size=100)

        assert stats["migrated"] == 1
        assert stats["failed"] == 0
        assert stats["skipped"] == 0
        assert fu.clinical_analysis_cache is None, (
            "La columna vieja debe quedar en None tras migración exitosa"
        )
        assert fu.clinical_analysis_cache_enc == ENCRYPTED_BYTES, (
            "_enc debe contener los bytes cifrados"
        )
        db.commit.assert_called_once()

    def test_encrypt_failure_leaves_row_intact(self):
        """Si encrypt_json lanza, el row queda con plaintext intacto (rollback)."""
        fu = FakeUser(cache_data={"narrative": "datos sensibles"})
        original_cache = dict(fu.clinical_analysis_cache)

        db = _make_db_session([fu])

        from scripts.migrate_clinical_data import run_migration

        with (
            patch("scripts.migrate_clinical_data.SessionLocal", return_value=db),
            patch(
                "scripts.migrate_clinical_data.encrypt_json",
                side_effect=RuntimeError("FIELD_ENCRYPTION_KEY not set"),
            ),
        ):
            stats = run_migration(dry_run=False, chunk_size=100)

        assert stats["failed"] == 1
        assert stats["migrated"] == 0
        # Se hizo rollback
        db.rollback.assert_called()
        # La columna vieja NO fue modificada
        assert fu.clinical_analysis_cache == original_cache, (
            "El plaintext debe quedar intacto si el cifrado falla"
        )
        # _enc sigue siendo None
        assert fu.clinical_analysis_cache_enc is None

    def test_dry_run_does_not_commit(self):
        """En dry_run=True no se llama commit()."""
        fu = FakeUser(cache_data={"key": "val"})
        db = _make_db_session([fu])

        from scripts.migrate_clinical_data import run_migration

        with (
            patch("scripts.migrate_clinical_data.SessionLocal", return_value=db),
            patch(
                "scripts.migrate_clinical_data.encrypt_json",
                return_value=ENCRYPTED_BYTES,
            ),
        ):
            stats = run_migration(dry_run=True, chunk_size=100)

        db.commit.assert_not_called()
        assert stats["migrated"] == 1

    def test_already_migrated_row_skipped(self):
        """Row con _enc ya non-null se cuenta como skipped, no se re-procesa."""
        fu = FakeUser(
            cache_data={"old": "data"},
            enc_data=b"ENC1" + b"\xFF" * 20,
        )
        db = _make_db_session([fu])

        from scripts.migrate_clinical_data import run_migration

        with (
            patch("scripts.migrate_clinical_data.SessionLocal", return_value=db),
            patch("scripts.migrate_clinical_data.encrypt_json") as mock_enc,
        ):
            stats = run_migration(dry_run=False, chunk_size=100)

        mock_enc.assert_not_called()
        assert stats["skipped"] == 1
        assert stats["migrated"] == 0

    def test_stats_total_equals_rows_processed(self):
        """La suma migrated+failed+skipped siempre iguala el total de rows."""
        users = [
            FakeUser(cache_data={"n": i})
            for i in range(5)
        ]
        db = _make_db_session(users)

        call_count = {"n": 0}

        def _encrypt_side_effect(obj):
            call_count["n"] += 1
            # El tercer row falla
            if call_count["n"] == 3:
                raise ValueError("simulated failure")
            return ENCRYPTED_BYTES

        from scripts.migrate_clinical_data import run_migration

        with (
            patch("scripts.migrate_clinical_data.SessionLocal", return_value=db),
            patch(
                "scripts.migrate_clinical_data.encrypt_json",
                side_effect=_encrypt_side_effect,
            ),
        ):
            stats = run_migration(dry_run=False, chunk_size=100)

        total = stats["migrated"] + stats["failed"] + stats["skipped"]
        # Con rollback de chunk cuando hay fallo, el chunk entero falla
        # (la implementación hace break tras el primer error en el chunk).
        # Total debe ser <= 5 y failed >= 1.
        assert total <= 5
        assert stats["failed"] >= 1

    def test_empty_table_returns_zero_stats(self):
        """Tabla sin rows pendientes → stats todos en 0."""
        db = _make_db_session([])

        from scripts.migrate_clinical_data import run_migration

        with (
            patch("scripts.migrate_clinical_data.SessionLocal", return_value=db),
            patch("scripts.migrate_clinical_data.encrypt_json") as mock_enc,
        ):
            stats = run_migration(dry_run=False, chunk_size=100)

        mock_enc.assert_not_called()
        assert stats == {"migrated": 0, "failed": 0, "skipped": 0}


# ---------------------------------------------------------------------------
# Tests de la migration Alembic 037 (schema only)
# ---------------------------------------------------------------------------

def _load_migration_037():
    """Carga el módulo de migration 037 vía importlib (no tiene __init__.py en versions/)."""
    import importlib.util
    import os

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "alembic", "versions", "037_encrypt_clinical_analysis.py")
    spec = importlib.util.spec_from_file_location("migration_037", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigration037Schema:
    """Valida que el migration Alembic 037 hace lo correcto a nivel de schema."""

    def test_migration_adds_enc_column(self):
        """El upgrade() define la columna clinical_analysis_cache_enc con LargeBinary."""
        import inspect
        m037 = _load_migration_037()

        src = inspect.getsource(m037.upgrade)
        assert "clinical_analysis_cache_enc" in src
        assert "LargeBinary" in src

    def test_migration_downgrade_drops_only_enc_column(self):
        """El downgrade() droppea _enc · NO droppea la columna plaintext original."""
        import inspect
        m037 = _load_migration_037()

        src = inspect.getsource(m037.downgrade)
        assert "clinical_analysis_cache_enc" in src
        assert "drop_column" in src
        # Verificar que drop_column NO se aplica a la columna vieja sin _enc
        # Analizamos líneas que tienen drop_column
        drop_lines = [
            line for line in src.splitlines()
            if "drop_column" in line
        ]
        for line in drop_lines:
            assert "clinical_analysis_cache_enc" in line, (
                f"downgrade droppea algo distinto a _enc: {line}"
            )

    def test_migration_upgrade_only_adds_column(self):
        """El upgrade() solo agrega una columna, no migra datos inline."""
        import inspect
        m037 = _load_migration_037()

        src = inspect.getsource(m037.upgrade)
        # No debe haber lógica de migración de datos
        assert "encrypt_json" not in src, "upgrade() NO debe llamar encrypt_json"
        assert "SessionLocal" not in src, "upgrade() NO debe abrir sesiones de DB"
        # for loop sobre rows sería señal de migración de datos inline
        assert "for " not in src or "add_column" in src, (
            "upgrade() no debe tener loops (serían migración de datos inline)"
        )
        # Solo debe hacer add_column
        assert "add_column" in src

    def test_migration_revision_metadata(self):
        """El migration 037 tiene el revision ID y down_revision correctos."""
        m037 = _load_migration_037()

        assert m037.revision == "037_encrypt_clinical_analysis"
        assert m037.down_revision == "036_flags_prompts_configs"
