"""Create consolidated_profiles + add budget/country preferences to users

Revision ID: 007_create_consolidated_profiles
Revises: 006_create_external_test_uploads
Create Date: 2026-04-30

GH-S6-DB-01 · Sprint 6 (AI Analysis Engine cruzado).

What this migration does:

  1. Creates `consolidated_profiles` to cache the IA-generated cross-test
     analysis (ConsolidatedProfile + RecommendedProgram[] bundle).

     Cache key strategy:
       - One row per user (user_id is unique).
       - `profile_hash` is the SHA-256 of the canonical JSON of input
         (vocational_test_results + relevant user fields).
       - On hit (same hash · generated_at within TTL · invalidated_at NULL),
         reuse · otherwise regenerate.

     Invalidation:
       - When a new vocational_test_result is inserted/updated, the cached
         row is marked invalidated_at = NOW() (logic en `services/
         consolidation_service.py`).

  2. Extends `users` with `budget_band`, `budget_max_usd`, `preferred_countries`
     so the pre-IA filter (BE-05) can scope the catalog before the prompt.

Idempotent: uses table_exists / column_exists guards.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "007_create_consolidated_profiles"
down_revision = "006_create_external_test_uploads"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # 1) consolidated_profiles
    if not table_exists("consolidated_profiles"):
        op.create_table(
            "consolidated_profiles",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
                index=True,
            ),
            # Hash sha256 hex (64 chars) of the canonical input
            sa.Column("profile_hash", sa.String(64), nullable=False, index=True),
            # JSONB payload of ConsolidatedProfile
            sa.Column("profile_data", postgresql.JSONB, nullable=False),
            # JSONB payload of RecommendedProgram[]
            sa.Column(
                "recommendations_data",
                postgresql.JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            # Metadata
            sa.Column("model_used", sa.String(100), nullable=True),
            sa.Column("prompt_version", sa.String(50), nullable=True),
            sa.Column("tokens_input", sa.Integer, nullable=True),
            sa.Column("tokens_output", sa.Integer, nullable=True),
            sa.Column("latency_ms", sa.Integer, nullable=True),
            # TTL / invalidation
            sa.Column(
                "generated_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Set when a new test arrives · forces regen even if hash collides
            sa.Column("invalidated_at", sa.DateTime, nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_consolidated_profiles_hash",
            "consolidated_profiles",
            ["user_id", "profile_hash"],
        )

    # 2) users · presupuesto + país preferido (S6-FE-03 / FE-04)
    if not column_exists("users", "budget_band"):
        op.add_column(
            "users",
            sa.Column("budget_band", sa.String(20), nullable=True),
        )

    if not column_exists("users", "budget_max_usd"):
        op.add_column(
            "users",
            sa.Column("budget_max_usd", sa.Integer, nullable=True),
        )

    if not column_exists("users", "preferred_countries"):
        op.add_column(
            "users",
            sa.Column(
                "preferred_countries",
                postgresql.JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    if column_exists("users", "preferred_countries"):
        op.drop_column("users", "preferred_countries")
    if column_exists("users", "budget_max_usd"):
        op.drop_column("users", "budget_max_usd")
    if column_exists("users", "budget_band"):
        op.drop_column("users", "budget_band")

    if table_exists("consolidated_profiles"):
        op.drop_index(
            "ix_consolidated_profiles_hash", table_name="consolidated_profiles"
        )
        op.drop_table("consolidated_profiles")
