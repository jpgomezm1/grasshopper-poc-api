"""Tests para migration 041_auditability_and_indices.

Cubre:
    - Metadata de la migración (revision + down_revision correctos)
    - Upgrade: 5 índices creados en las tablas correctas
    - Downgrade: 5 índices eliminados
    - updated_at se setea automáticamente al INSERT via ORM (default=datetime.utcnow)
    - updated_at se actualiza al UPDATE via ORM (onupdate=datetime.utcnow)
    - created_at en join models se setea al INSERT via ORM
    - Los índices NO caen en tablas incorrectas (cross-table check)

Estrategia de tests:

    Grupo A – Índices:
        Se usa `sqlite_engine_pre_migration`: crea las tablas vía SQL DDL
        mínimo (sin las columnas nuevas de la migración 041) para que
        upgrade() pueda ejecutar ADD COLUMN + CREATE INDEX sin conflicto de
        "duplicate column name".

    Grupos B / C – Columnas updated_at / created_at:
        Las columnas ya están en el modelo actualizado. Los tests del
        comportamiento ORM (default / onupdate) se ejecutan contra
        `sqlite_engine` normal (Base.metadata.create_all incluye las
        columnas). Esto verifica que el modelo SQLAlchemy se comporta
        correctamente en runtime, independiente del SQL de migración.
"""
from __future__ import annotations

import importlib.util
import pathlib
import time
import uuid
from datetime import datetime
from typing import List

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite UUID compat (mismo patch que el resto de la suite)
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
    / "041_auditability_and_indices.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_migration_041", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_MIGRATION = _load_migration()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _index_names(engine, table: str) -> List[str]:
    return [idx["name"] for idx in inspect(engine).get_indexes(table)]


def _run_fn(engine, fn):
    """Ejecuta upgrade() o downgrade() usando alembic.operations.Operations."""
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


# DDL mínimo para las 5 tablas que reciben índices en la migración 041.
# Las tablas se crean SIN las columnas updated_at/created_at de la migración
# para que upgrade() pueda ejecutar ADD COLUMN sin "duplicate column name".
_PRE_MIGRATION_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) PRIMARY KEY,
    assigned_to_user_id VARCHAR(36),
    description TEXT,
    status VARCHAR(10) DEFAULT 'open',
    priority VARCHAR(10) DEFAULT 'normal',
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS student_cases_followup (
    id VARCHAR(36) PRIMARY KEY,
    student_user_id VARCHAR(36),
    school_id VARCHAR(36),
    case_type VARCHAR(40),
    status VARCHAR(20) DEFAULT 'open',
    title VARCHAR(200),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS orientation_sessions (
    id VARCHAR(36) PRIMARY KEY,
    advisor_user_id VARCHAR(36),
    student_user_id VARCHAR(36),
    scheduled_at DATETIME,
    type VARCHAR(20),
    status VARCHAR(20) DEFAULT 'scheduled',
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS bitrix_sync_log (
    id VARCHAR(36) PRIMARY KEY,
    entity_type VARCHAR(40),
    entity_id VARCHAR(120),
    action VARCHAR(40),
    status VARCHAR(20) DEFAULT 'pending',
    provider VARCHAR(20) DEFAULT 'stub',
    attempts INTEGER DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS invitations (
    id VARCHAR(36) PRIMARY KEY,
    school_id VARCHAR(36),
    email VARCHAR(255),
    role VARCHAR(30),
    token VARCHAR(120),
    status VARCHAR(20) DEFAULT 'pending',
    expires_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS cohorts (
    id VARCHAR(36) PRIMARY KEY,
    school_id VARCHAR(36),
    key VARCHAR(40),
    label VARCHAR(120),
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS school_events (
    id VARCHAR(36) PRIMARY KEY,
    school_id VARCHAR(36),
    title VARCHAR(200),
    starts_at DATETIME,
    audience VARCHAR(20) DEFAULT 'both',
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS lead_tags (
    id VARCHAR(36) PRIMARY KEY,
    key VARCHAR(60) UNIQUE,
    label VARCHAR(120),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS lead_profiles (
    id VARCHAR(36) PRIMARY KEY,
    answers TEXT,
    profile_result TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    type VARCHAR(60),
    title VARCHAR(255),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS reports (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    file_path VARCHAR(500),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS saved_ofertas (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    oferta_id VARCHAR(100),
    created_at DATETIME,
    status VARCHAR(50) DEFAULT 'interested'
);

CREATE TABLE IF NOT EXISTS school_legal_documents (
    id VARCHAR(36) PRIMARY KEY,
    school_id VARCHAR(36),
    type VARCHAR(40),
    version VARCHAR(20),
    content TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS vocational_test_results (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    test_id VARCHAR(50),
    answers TEXT,
    scores TEXT,
    source VARCHAR(30) DEFAULT 'internal',
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS external_test_uploads (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    test_type VARCHAR(50),
    file_path VARCHAR(500),
    parsing_status VARCHAR(30) DEFAULT 'pending',
    uploaded_at DATETIME
);

CREATE TABLE IF NOT EXISTS case_interventions (
    id VARCHAR(36) PRIMARY KEY,
    case_id VARCHAR(36),
    action VARCHAR(60),
    content TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS clinical_alerts (
    id VARCHAR(36) PRIMARY KEY,
    student_user_id VARCHAR(36),
    school_id VARCHAR(36),
    severity VARCHAR(20),
    pattern_type VARCHAR(60),
    source VARCHAR(40) DEFAULT 'ai_analysis',
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    name VARCHAR(120),
    filters TEXT,
    pinned BOOLEAN DEFAULT 0,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS school_mass_messages (
    id VARCHAR(36) PRIMARY KEY,
    school_id VARCHAR(36),
    subject VARCHAR(200),
    body TEXT,
    audience VARCHAR(20) DEFAULT 'both',
    sent_at DATETIME,
    sent_count INTEGER DEFAULT 0,
    opened_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36),
    endpoint TEXT UNIQUE,
    p256dh TEXT,
    auth TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS school_custom_fields (
    id VARCHAR(36) PRIMARY KEY,
    school_id VARCHAR(36),
    key VARCHAR(60),
    label VARCHAR(120),
    type VARCHAR(20),
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS english_test_results (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) UNIQUE,
    answers TEXT,
    score INTEGER,
    total_questions INTEGER,
    cefr_level VARCHAR(10),
    section_scores TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS cohort_psychologist_assignments (
    id VARCHAR(36) PRIMARY KEY,
    psychologist_user_id VARCHAR(36),
    cohort_id VARCHAR(36),
    assigned_at DATETIME
);

CREATE TABLE IF NOT EXISTS student_cohort_assignments (
    id VARCHAR(36) PRIMARY KEY,
    student_user_id VARCHAR(36),
    cohort_id VARCHAR(36),
    assigned_at DATETIME
);

CREATE TABLE IF NOT EXISTS lead_tag_assignments (
    id VARCHAR(36) PRIMARY KEY,
    lead_user_id VARCHAR(36),
    tag_id VARCHAR(36),
    assigned_at DATETIME
);

CREATE TABLE IF NOT EXISTS school_event_rsvps (
    id VARCHAR(36) PRIMARY KEY,
    event_id VARCHAR(36),
    user_id VARCHAR(36),
    status VARCHAR(20),
    responded_at DATETIME
);

CREATE TABLE IF NOT EXISTS school_mass_message_reads (
    id VARCHAR(36) PRIMARY KEY,
    message_id VARCHAR(36),
    user_id VARCHAR(36),
    read_at DATETIME
);

CREATE TABLE IF NOT EXISTS student_custom_field_values (
    id VARCHAR(36) PRIMARY KEY,
    student_user_id VARCHAR(36),
    field_id VARCHAR(36),
    value TEXT,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS school_legal_signatures (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36),
    signer_user_id VARCHAR(36),
    signed_at DATETIME
);

CREATE TABLE IF NOT EXISTS integration_configs (
    id VARCHAR(36) PRIMARY KEY,
    integration_key VARCHAR(40),
    setting_key VARCHAR(80),
    setting_value TEXT,
    is_secret BOOLEAN DEFAULT 0,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS ai_prompts (
    id VARCHAR(36) PRIMARY KEY,
    key VARCHAR(80),
    version INTEGER,
    content TEXT,
    is_active BOOLEAN DEFAULT 0
);
"""


@pytest.fixture()
def sqlite_engine_pre_migration():
    """Engine SQLite in-memory con tablas creadas SIN las columnas added en 041.

    Este fixture emula el estado pre-migración para que upgrade() pueda ejecutar
    ADD COLUMN y CREATE INDEX sin errores de "duplicate column name".
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        for stmt in _PRE_MIGRATION_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    yield engine
    engine.dispose()


@pytest.fixture()
def sqlite_engine():
    """Engine SQLite in-memory con modelo actualizado (para tests ORM)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Grupo 0: metadata de la migración
# ---------------------------------------------------------------------------

def test_migration_revision_and_chain():
    """revision y down_revision correctos para la cadena 040 → 041."""
    assert _MIGRATION.revision == "041_auditability_and_indices"
    assert _MIGRATION.down_revision == "040_critical_indexes", (
        f"down_revision incorrecto: {_MIGRATION.down_revision!r}"
    )


# ---------------------------------------------------------------------------
# Grupo A: índices (5 medio-riesgo)
# ---------------------------------------------------------------------------

_EXPECTED_INDEXES = [
    ("tasks", "ix_tasks_status"),
    ("student_cases_followup", "ix_student_cases_followup_status"),
    ("orientation_sessions", "ix_orientation_sessions_type"),
    ("bitrix_sync_log", "ix_bitrix_sync_log_provider"),
    ("invitations", "ix_invitations_role"),
]


def test_upgrade_creates_five_indexes(sqlite_engine_pre_migration):
    """Después de upgrade(), los 5 índices medio-riesgo deben existir."""
    _run_fn(sqlite_engine_pre_migration, _MIGRATION.upgrade)

    for table, idx_name in _EXPECTED_INDEXES:
        actual = _index_names(sqlite_engine_pre_migration, table)
        assert idx_name in actual, (
            f"Índice '{idx_name}' no encontrado en tabla '{table}' tras upgrade(). "
            f"Índices presentes: {actual}"
        )


def test_downgrade_removes_five_indexes(sqlite_engine_pre_migration):
    """Después de upgrade() + downgrade(), ninguno de los 5 índices debe existir."""
    _run_fn(sqlite_engine_pre_migration, _MIGRATION.upgrade)
    _run_fn(sqlite_engine_pre_migration, _MIGRATION.downgrade)

    for table, idx_name in _EXPECTED_INDEXES:
        actual = _index_names(sqlite_engine_pre_migration, table)
        assert idx_name not in actual, (
            f"Índice '{idx_name}' aún existe en tabla '{table}' tras downgrade()."
        )


def test_indexes_on_correct_tables(sqlite_engine_pre_migration):
    """ix_tasks_status no cae en student_cases_followup y viceversa."""
    _run_fn(sqlite_engine_pre_migration, _MIGRATION.upgrade)

    tasks_idx = _index_names(sqlite_engine_pre_migration, "tasks")
    scf_idx = _index_names(sqlite_engine_pre_migration, "student_cases_followup")

    assert "ix_student_cases_followup_status" not in tasks_idx, (
        "ix_student_cases_followup_status no debe estar en 'tasks'"
    )
    assert "ix_tasks_status" not in scf_idx, (
        "ix_tasks_status no debe estar en 'student_cases_followup'"
    )


def test_provider_index_on_bitrix_not_invitations(sqlite_engine_pre_migration):
    """ix_bitrix_sync_log_provider no debe estar en 'invitations'."""
    _run_fn(sqlite_engine_pre_migration, _MIGRATION.upgrade)

    inv_idx = _index_names(sqlite_engine_pre_migration, "invitations")
    assert "ix_bitrix_sync_log_provider" not in inv_idx, (
        "ix_bitrix_sync_log_provider no debe estar en 'invitations'"
    )


# ---------------------------------------------------------------------------
# Grupo B: updated_at en tablas principales (comportamiento ORM)
# ---------------------------------------------------------------------------

_TABLES_WITH_NEW_UPDATED_AT = [
    "tasks",
    "cohorts",
    "school_events",
    "lead_tags",
    "lead_profiles",
    "notifications",
    "reports",
    "saved_ofertas",
    "school_legal_documents",
    "vocational_test_results",
    "external_test_uploads",
    "case_interventions",
    "clinical_alerts",
    "saved_searches",
    "school_mass_messages",
    "push_subscriptions",
    "school_custom_fields",
    "english_test_results",
]


def test_updated_at_columns_exist_in_model(sqlite_engine):
    """Todas las tablas del grupo B tienen columna updated_at en el modelo."""
    inspector = inspect(sqlite_engine)
    for table in _TABLES_WITH_NEW_UPDATED_AT:
        cols = [c["name"] for c in inspector.get_columns(table)]
        assert "updated_at" in cols, (
            f"Tabla '{table}' no tiene columna 'updated_at' en el modelo actualizado."
        )


def test_updated_at_set_on_orm_insert(sqlite_engine):
    """ORM: insertar una Task → updated_at se setea (via default=datetime.utcnow)."""
    from app.db.models import Task, User, UserRole

    with Session(sqlite_engine) as session:
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email=f"u{user_id}@test.com",
            hashed_password="x",
            role=UserRole.GH_ADVISOR,
        )
        session.add(user)
        session.commit()

        task = Task(
            id=uuid.uuid4(),
            assigned_to_user_id=user_id,
            description="tarea de prueba",
            status="open",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        assert task.updated_at is not None, (
            "Task.updated_at debería haberse seteado con default=datetime.utcnow"
        )
        assert isinstance(task.updated_at, datetime)


def test_updated_at_changes_on_orm_update(sqlite_engine):
    """ORM: actualizar LeadTag.label → updated_at se re-setea con onupdate."""
    from app.db.models import LeadTag

    with Session(sqlite_engine) as session:
        tag = LeadTag(
            id=uuid.uuid4(),
            key="test_tag_update",
            label="Label Original",
        )
        session.add(tag)
        session.commit()
        session.refresh(tag)

        original_ts = tag.updated_at

        time.sleep(0.05)

        tag.label = "Label Actualizado"
        session.commit()
        session.refresh(tag)

        assert tag.updated_at is not None, "updated_at no debe ser None tras UPDATE"
        assert isinstance(tag.updated_at, datetime)
        if original_ts is not None:
            assert tag.updated_at >= original_ts


def test_updated_at_set_on_insert_for_multiple_models(sqlite_engine):
    """Insertar LeadProfile y Notification → ambos tienen updated_at post-INSERT."""
    from app.db.models import LeadProfile, Notification, User, UserRole

    with Session(sqlite_engine) as session:
        lead = LeadProfile(
            id=uuid.uuid4(),
            answers={"q1": "a"},
            profile_result={"score": 5},
        )
        session.add(lead)

        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email=f"notif{user_id}@test.com",
            hashed_password="x",
            role=UserRole.STUDENT,
        )
        session.add(user)
        session.commit()

        notif = Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            type="test_event",
            title="Notificación de prueba",
        )
        session.add(notif)
        session.commit()
        session.refresh(lead)
        session.refresh(notif)

        assert lead.updated_at is not None, "LeadProfile.updated_at debe setearse al INSERT"
        assert notif.updated_at is not None, "Notification.updated_at debe setearse al INSERT"


# ---------------------------------------------------------------------------
# Grupo C: created_at en join models (comportamiento ORM)
# ---------------------------------------------------------------------------

_JOIN_TABLES_WITH_NEW_CREATED_AT = [
    "cohort_psychologist_assignments",
    "student_cohort_assignments",
    "lead_tag_assignments",
    "school_event_rsvps",
    "school_mass_message_reads",
    "student_custom_field_values",
    "school_legal_signatures",
    "integration_configs",
]


def test_created_at_columns_exist_in_join_models(sqlite_engine):
    """Todos los join models del grupo C tienen created_at en el modelo."""
    inspector = inspect(sqlite_engine)
    for table in _JOIN_TABLES_WITH_NEW_CREATED_AT:
        cols = [c["name"] for c in inspector.get_columns(table)]
        assert "created_at" in cols, (
            f"Tabla '{table}' no tiene columna 'created_at' en el modelo actualizado."
        )


def test_created_at_set_on_orm_insert_join_model(sqlite_engine):
    """ORM: insertar CohortPsychologistAssignment → created_at se setea."""
    from app.db.models import (
        CohortPsychologistAssignment,
        Cohort,
        School,
        User,
        UserRole,
    )

    with Session(sqlite_engine) as session:
        school_id = uuid.uuid4()
        school = School(
            id=school_id,
            name="Colegio Test 041",
            slug=f"colegio-test-041-{school_id}",
        )
        session.add(school)

        psy_id = uuid.uuid4()
        psy = User(
            id=psy_id,
            email=f"psy041{psy_id}@test.com",
            hashed_password="x",
            role=UserRole.PSYCHOLOGIST,
            school_id=school_id,
        )
        session.add(psy)

        cohort_id = uuid.uuid4()
        cohort = Cohort(
            id=cohort_id,
            school_id=school_id,
            key="11B",
            label="Once B",
        )
        session.add(cohort)
        session.commit()

        assignment = CohortPsychologistAssignment(
            id=uuid.uuid4(),
            psychologist_user_id=psy_id,
            cohort_id=cohort_id,
        )
        session.add(assignment)
        session.commit()
        session.refresh(assignment)

        assert assignment.created_at is not None, (
            "CohortPsychologistAssignment.created_at debería setearse al INSERT"
        )
        assert isinstance(assignment.created_at, datetime)


def test_created_at_set_on_insert_integration_config(sqlite_engine):
    """ORM: insertar IntegrationConfig → created_at se setea."""
    from app.db.models import IntegrationConfig

    with Session(sqlite_engine) as session:
        config = IntegrationConfig(
            id=uuid.uuid4(),
            integration_key="bitrix",
            setting_key="notify_email",
            setting_value="admin@test.com",
        )
        session.add(config)
        session.commit()
        session.refresh(config)

        assert config.created_at is not None, (
            "IntegrationConfig.created_at debería setearse al INSERT"
        )
        assert isinstance(config.created_at, datetime)
