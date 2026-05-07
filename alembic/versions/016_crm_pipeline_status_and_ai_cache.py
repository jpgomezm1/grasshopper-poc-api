"""CRM enriched · pipeline status + AI analysis cache on users

Revision ID: 016_crm_pipeline_status_and_ai_cache
Revises: 015_extend_programs_editorial
Create Date: 2026-05-03

GH-CRM-001 · Sprint CRM enriquecido 2026-05-03 · último issue de
BITACORA_TESTING.md (`[HIGH · CRM module · renombrar + enriquecer]`).

Adds 4 columns to `users` to support the CRM pipeline view:

    lead_pipeline_status      VARCHAR(20)  · pseudo-enum
        {pending, contacted, qualified, converted, declined}
        NULL = no pipeline action yet (default for every user)
    lead_pipeline_status_at   TIMESTAMP    · last status change
    ai_analysis_cache         JSONB        · cached AI output for the lead
        shape · {rationale: str, program_matches: [{...}], next_actions: [{...}]}
    ai_analysis_cached_at     TIMESTAMP    · cache freshness · TTL 7 days
        (decision lives in service · not enforced at DB level)

Privacy notes:
    The cache stores synthesized recommendations · NOT raw journal
    content (D-025 staff privacy). Rebuilding only requires demographics
    + scoring + program catalog so the cache is not a sensitive surface.

Idempotent · safe to re-run.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '016_crm_pipeline_status_and_ai_cache'
down_revision = '015_extend_programs_editorial'
branch_labels = None
depends_on = None


# ----------------------------------------------------------------------------
# helpers (same pattern as 014/015)
# ----------------------------------------------------------------------------


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def _constraint_exists(table: str, constraint: str) -> bool:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :c"
        ),
        {"t": table, "c": constraint},
    ).fetchall()
    return bool(rows)


ALLOWED_PIPELINE_STATUSES = (
    "pending",
    "contacted",
    "qualified",
    "converted",
    "declined",
)


# ----------------------------------------------------------------------------
# upgrade
# ----------------------------------------------------------------------------


def upgrade() -> None:
    # 1. lead_pipeline_status · short string (no DB enum to stay consistent
    #    with the existing gh_contact_status pattern)
    if not _column_exists('users', 'lead_pipeline_status'):
        op.add_column(
            'users',
            sa.Column('lead_pipeline_status', sa.String(20), nullable=True),
        )

    # 2. lead_pipeline_status_at · last transition timestamp
    if not _column_exists('users', 'lead_pipeline_status_at'):
        op.add_column(
            'users',
            sa.Column('lead_pipeline_status_at', sa.DateTime(), nullable=True),
        )

    # 3. ai_analysis_cache · JSONB payload (rationale + program_matches + next_actions)
    if not _column_exists('users', 'ai_analysis_cache'):
        op.add_column(
            'users',
            sa.Column('ai_analysis_cache', postgresql.JSONB(), nullable=True),
        )

    # 4. ai_analysis_cached_at · cache freshness · TTL enforced in service
    if not _column_exists('users', 'ai_analysis_cached_at'):
        op.add_column(
            'users',
            sa.Column('ai_analysis_cached_at', sa.DateTime(), nullable=True),
        )

    # 5. CHECK constraint on lead_pipeline_status · idempotent
    if not _constraint_exists('users', 'ck_users_lead_pipeline_status'):
        op.create_check_constraint(
            'ck_users_lead_pipeline_status',
            'users',
            "lead_pipeline_status IS NULL OR lead_pipeline_status IN ({allowed})".format(
                allowed=", ".join(f"'{s}'" for s in ALLOWED_PIPELINE_STATUSES)
            ),
        )

    # 6. partial index on lead_pipeline_status (non-null) · the CRM list filters
    #    by status frequently so this keeps the query plan small
    if not _index_exists('users', 'ix_users_lead_pipeline_status'):
        op.create_index(
            'ix_users_lead_pipeline_status',
            'users',
            ['lead_pipeline_status'],
            postgresql_where=sa.text('lead_pipeline_status IS NOT NULL'),
        )


# ----------------------------------------------------------------------------
# downgrade
# ----------------------------------------------------------------------------


def downgrade() -> None:
    if _index_exists('users', 'ix_users_lead_pipeline_status'):
        op.drop_index('ix_users_lead_pipeline_status', table_name='users')

    if _constraint_exists('users', 'ck_users_lead_pipeline_status'):
        op.drop_constraint(
            'ck_users_lead_pipeline_status', 'users', type_='check'
        )

    for col in (
        'ai_analysis_cached_at',
        'ai_analysis_cache',
        'lead_pipeline_status_at',
        'lead_pipeline_status',
    ):
        if _column_exists('users', col):
            op.drop_column('users', col)
