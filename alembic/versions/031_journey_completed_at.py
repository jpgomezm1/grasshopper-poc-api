"""Add users.journey_completed_at + schools.branding_primary_color

Revision ID: 031_journey_completed_at
Revises: 030_cases_followup_branding_messages
Create Date: 2026-05-05

GH-STUDENT-EXPERIENCE · Bloque J + A · Sprint student-facing 2026-05-05.

Adds:

    users
        + journey_completed_at TIMESTAMP NULL    · stamped once when student
                                                   crosses the completion
                                                   criteria (onboarding +
                                                   3 tests + 2 routes).

    schools
        + branding_primary_color VARCHAR(20) NULL  · alias-friendly primary
                                                     brand color (the existing
                                                     `secondary_color` keeps
                                                     its meaning · this is the
                                                     dedicated chip/banner hue
                                                     surfaced to students).

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '031_journey_completed_at'
down_revision = '030_cases_followup_branding_messages'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if not _column_exists('users', 'journey_completed_at'):
        op.add_column(
            'users',
            sa.Column('journey_completed_at', sa.DateTime(), nullable=True),
        )

    if not _column_exists('schools', 'branding_primary_color'):
        op.add_column(
            'schools',
            sa.Column('branding_primary_color', sa.String(20), nullable=True),
        )


def downgrade() -> None:
    if _column_exists('schools', 'branding_primary_color'):
        op.drop_column('schools', 'branding_primary_color')
    if _column_exists('users', 'journey_completed_at'):
        op.drop_column('users', 'journey_completed_at')
