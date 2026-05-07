"""Clinical analysis cache columns on users · gh_advisor clinical toolkit

Revision ID: 024_clinical_analysis_cache
Revises: 023_orientation_sessions_and_notes
Create Date: 2026-05-04

GH-ADVISOR-CLINICAL · Bloque C+D · Sprint advisor clinical 2026-05-04.

Adds two columns on `users` to cache the clinical analysis (narrative +
strengths + growth_areas + risks + session_suggestions + behavioral_patterns).
Cache TTL is 30 days enforced at service layer.

    users
        clinical_analysis_cache       JSONB NULL
        clinical_analysis_cached_at   TIMESTAMP NULL

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '024_clinical_analysis_cache'
down_revision = '023_orientation_sessions_and_notes'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if not _column_exists('users', 'clinical_analysis_cache'):
        op.add_column(
            'users',
            sa.Column(
                'clinical_analysis_cache',
                postgresql.JSONB(),
                nullable=True,
            ),
        )
    if not _column_exists('users', 'clinical_analysis_cached_at'):
        op.add_column(
            'users',
            sa.Column(
                'clinical_analysis_cached_at',
                sa.DateTime(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if _column_exists('users', 'clinical_analysis_cached_at'):
        op.drop_column('users', 'clinical_analysis_cached_at')
    if _column_exists('users', 'clinical_analysis_cache'):
        op.drop_column('users', 'clinical_analysis_cache')
