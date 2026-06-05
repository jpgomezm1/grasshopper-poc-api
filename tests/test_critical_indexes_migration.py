"""Tests para migration 040_critical_indexes · F7.1.

Verifica que upgrade() crea los 4 índices esperados y que downgrade()
los elimina correctamente. Usa SQLAlchemy reflection sobre SQLite in-memory.

El test carga el módulo de migración via importlib para evitar restricciones
del nombre de archivo que comienza con dígito (incompatible con import directo).

Decisión de alcance:
    No se ejecuta alembic CLI upgrade/downgrade (requeriría Postgres vivo).
    En cambio se ejecutan las funciones upgrade()/downgrade() directamente
    contra SQLite usando alembic.operations.Operations, que es el mismo objeto
    subyacente que usa el CLI. Esta estrategia es estándar en la suite.
"""
from __future__ import annotations

import importlib.util
import pathlib
from typing import List

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Patch SQLite para tipos UUID (mismo patrón que otros tests del proyecto)
# ---------------------------------------------------------------------------
try:
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler as _STC

    if not hasattr(_STC, "visit_UUID"):
        def _visit_UUID(self, type_, **kw):  # noqa: N802
            return "VARCHAR(36)"
        _STC.visit_UUID = _visit_UUID  # type: ignore[attr-defined]
except Exception:
    pass


# ---------------------------------------------------------------------------
# Carga dinámica del módulo de migración
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    pathlib.Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "040_critical_indexes.py"
)


def _load_migration():
    """Carga 040_critical_indexes.py como módulo Python."""
    spec = importlib.util.spec_from_file_location("_migration_040", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_MIGRATION = _load_migration()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_engine():
    """Motor SQLite in-memory con todas las tablas del proyecto creadas."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


def _index_names(engine, table: str) -> List[str]:
    """Devuelve la lista de nombres de índices de una tabla."""
    return [idx["name"] for idx in inspect(engine).get_indexes(table)]


def _run_fn(engine, fn):
    """Ejecuta upgrade() o downgrade() contra el engine dado via alembic.Operations.

    Usa _install_proxy() / _remove_proxy() que son la API correcta en
    alembic >= 1.9 para enlazar el proxy de módulo `alembic.op` a un
    contexto de conexión específico.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        op._install_proxy()
        try:
            fn()
        finally:
            op._remove_proxy()


# ---------------------------------------------------------------------------
# Test 1: metadata de la migración
# ---------------------------------------------------------------------------


def test_migration_revision_and_chain():
    """El archivo tiene revision y down_revision correctos para la cadena F7.

    Nota: cuando se escribió este test, 040 colgaba de "037_pipeline_status_version".
    Después se insertaron 038_pipeline_status_version y 039_webhook_nonces, así que
    la cadena real es 037→038→039→040. El down_revision correcto de 040 es
    "039_webhook_nonces" (verificado: `alembic upgrade head` llega a un único head).
    """
    assert _MIGRATION.revision == "040_critical_indexes"
    assert _MIGRATION.down_revision == "039_webhook_nonces", (
        f"down_revision incorrecto: {_MIGRATION.down_revision!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: upgrade() crea los 4 índices
# ---------------------------------------------------------------------------


def test_upgrade_creates_four_indexes(sqlite_engine):
    """Después de upgrade(), los 4 índices deben existir en sus tablas."""
    _run_fn(sqlite_engine, _MIGRATION.upgrade)

    expected = [
        ("users", "ix_users_role"),
        ("users", "ix_users_is_active"),
        ("licenses", "ix_licenses_status"),
        ("ai_prompts", "ix_ai_prompts_is_active"),
    ]
    for table, idx_name in expected:
        actual = _index_names(sqlite_engine, table)
        assert idx_name in actual, (
            f"Índice '{idx_name}' no encontrado en tabla '{table}' tras upgrade(). "
            f"Índices presentes: {actual}"
        )


# ---------------------------------------------------------------------------
# Test 3: downgrade() elimina los 4 índices
# ---------------------------------------------------------------------------


def test_downgrade_removes_four_indexes(sqlite_engine):
    """Después de upgrade() + downgrade(), ninguno de los 4 índices debe existir."""
    _run_fn(sqlite_engine, _MIGRATION.upgrade)
    _run_fn(sqlite_engine, _MIGRATION.downgrade)

    for table, idx_name in [
        ("users", "ix_users_role"),
        ("users", "ix_users_is_active"),
        ("licenses", "ix_licenses_status"),
        ("ai_prompts", "ix_ai_prompts_is_active"),
    ]:
        actual = _index_names(sqlite_engine, table)
        assert idx_name not in actual, (
            f"Índice '{idx_name}' aún existe en tabla '{table}' tras downgrade()."
        )


# ---------------------------------------------------------------------------
# Test 4: tablas correctas (los índices no caen en tablas incorrectas)
# ---------------------------------------------------------------------------


def test_indexes_on_correct_tables(sqlite_engine):
    """ix_licenses_status no debe estar en 'users' · ix_users_role no en 'licenses'."""
    _run_fn(sqlite_engine, _MIGRATION.upgrade)

    users_indexes = _index_names(sqlite_engine, "users")
    licenses_indexes = _index_names(sqlite_engine, "licenses")

    assert "ix_licenses_status" not in users_indexes, (
        "ix_licenses_status no debe estar en 'users'"
    )
    assert "ix_users_role" not in licenses_indexes, (
        "ix_users_role no debe estar en 'licenses'"
    )
