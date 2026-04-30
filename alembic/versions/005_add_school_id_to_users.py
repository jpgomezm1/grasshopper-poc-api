"""Add school_id FK to users (nullable)

Revision ID: 005_add_school_id_to_users
Revises: 004_create_schools
Create Date: 2026-04-30

GH-S2-DB-03 · associates users (psychologists / school_admins / students)
with their school. Nullable because students can register without a school
(B2C path) and super_admin users belong to Grasshopper directly.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '005_add_school_id_to_users'
down_revision = '004_create_schools'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not column_exists('users', 'school_id'):
        op.add_column(
            'users',
            sa.Column(
                'school_id',
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            'fk_users_school_id',
            'users',
            'schools',
            ['school_id'],
            ['id'],
            ondelete='SET NULL',
        )
        op.create_index('ix_users_school_id', 'users', ['school_id'])


def downgrade() -> None:
    if column_exists('users', 'school_id'):
        op.drop_index('ix_users_school_id', table_name='users')
        op.drop_constraint('fk_users_school_id', 'users', type_='foreignkey')
        op.drop_column('users', 'school_id')
