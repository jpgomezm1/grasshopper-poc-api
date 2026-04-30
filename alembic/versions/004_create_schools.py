"""Create schools table

Revision ID: 004_create_schools
Revises: 003_add_role_to_users
Create Date: 2026-04-30

GH-S2-DB-02 · table that represents B2B clients (schools) of Grasshopper.
Used for license enforcement, co-branding, B2B reporting and student grouping.

Companion: 005_add_school_id_to_users.py adds the FK from users.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '004_create_schools'
down_revision = '003_add_role_to_users'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not table_exists('schools'):
        op.create_table(
            'schools',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('slug', sa.String(255), nullable=False, unique=True),
            sa.Column('logo_url', sa.String(500), nullable=True),
            sa.Column('license_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
            sa.Column('license_expires_at', sa.DateTime, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column(
                'updated_at',
                sa.DateTime,
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

        op.create_index('ix_schools_slug', 'schools', ['slug'], unique=True)
        op.create_index('ix_schools_name', 'schools', ['name'])


def downgrade() -> None:
    if table_exists('schools'):
        op.drop_index('ix_schools_name', table_name='schools')
        op.drop_index('ix_schools_slug', table_name='schools')
        op.drop_table('schools')
