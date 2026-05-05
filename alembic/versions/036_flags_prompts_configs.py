"""Feature flags + AI prompts versioning + integration configs.

Revision ID: 036_flags_prompts_configs
Revises: 035_ai_usage_and_error_log
Create Date: 2026-05-05

GH-SUPERADMIN-EXPERIENCE · Bloque M (flags) + N (prompts) + O (integrations).

Tables:
    feature_flags
        id              UUID PRIMARY KEY
        key             VARCHAR(80) NOT NULL UNIQUE
        name            VARCHAR(255) NOT NULL
        description     TEXT NULL
        enabled         BOOLEAN NOT NULL DEFAULT FALSE
        enabled_for_roles    JSON NOT NULL DEFAULT []   · array of UserRole strings
        enabled_for_school_ids JSON NOT NULL DEFAULT [] · array of school UUIDs
        created_at      TIMESTAMP NOT NULL
        updated_at      TIMESTAMP NOT NULL
        created_by_user_id UUID NULL FK → users.id

    ai_prompts
        id              UUID PRIMARY KEY
        key             VARCHAR(80) NOT NULL                 · ej. clinical_analysis · hop_system
        version         INTEGER NOT NULL                     · monotonically increasing per key
        content         TEXT NOT NULL
        is_active       BOOLEAN NOT NULL DEFAULT FALSE       · only one row per key has is_active=true
        created_at      TIMESTAMP NOT NULL
        created_by_user_id UUID NULL FK → users.id
        notes           TEXT NULL
        UNIQUE (key, version)

    integration_configs
        id              UUID PRIMARY KEY
        integration_key VARCHAR(40) NOT NULL                 · bitrix | anthropic | openai | s3
        setting_key     VARCHAR(80) NOT NULL
        setting_value   TEXT NULL                            · NEVER stores secrets · only metadata
        is_secret       BOOLEAN NOT NULL DEFAULT FALSE       · if true, value is the env var NAME
        description     TEXT NULL
        updated_at      TIMESTAMP NOT NULL
        updated_by_user_id UUID NULL FK → users.id
        UNIQUE (integration_key, setting_key)

SECURITY (Bloque O · gh-security-reviewer):
  - is_secret=true rows have setting_value = env var NAME (e.g. "BITRIX_WEBHOOK_URL")
  - actual secret values STAY in env. We never copy them into DB.
  - service layer enforces this contract.

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '036_flags_prompts_configs'
down_revision = '035_ai_usage_and_error_log'
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    insp = inspect(bind)
    return name in insp.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    UUID = sa.dialects.postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)
    JSON_TYPE = sa.dialects.postgresql.JSONB if is_pg else sa.JSON

    if not _has_table(bind, "feature_flags"):
        op.create_table(
            "feature_flags",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("key", sa.String(80), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("enabled_for_roles", JSON_TYPE, nullable=False, server_default=sa.text("'[]'::jsonb" if is_pg else "'[]'")),
            sa.Column("enabled_for_school_ids", JSON_TYPE, nullable=False, server_default=sa.text("'[]'::jsonb" if is_pg else "'[]'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )

    if not _has_table(bind, "ai_prompts"):
        op.create_table(
            "ai_prompts",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("key", sa.String(80), nullable=False, index=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.UniqueConstraint("key", "version", name="uq_ai_prompts_key_version"),
        )

    if not _has_table(bind, "integration_configs"):
        op.create_table(
            "integration_configs",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("integration_key", sa.String(40), nullable=False, index=True),
            sa.Column("setting_key", sa.String(80), nullable=False),
            sa.Column("setting_value", sa.Text(), nullable=True),
            sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("integration_key", "setting_key", name="uq_integration_configs_key_setting"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "integration_configs"):
        op.drop_table("integration_configs")
    if _has_table(bind, "ai_prompts"):
        op.drop_table("ai_prompts")
    if _has_table(bind, "feature_flags"):
        op.drop_table("feature_flags")
