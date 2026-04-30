"""Add role enum column to users (4 roles: student, psychologist, school_admin, super_admin)

Revision ID: 003_add_role_to_users
Revises: 002_saved_ofertas
Create Date: 2026-04-30

GH-S2-DB-01 · adds the role discriminator that drives auth multi-rol across
the platform. Default 'student' so existing users keep backwards-compatible
behaviour. Companion migrations:
  - 004_create_schools.py        · School model
  - 005_add_school_id_to_users.py · FK from users to schools
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '003_add_role_to_users'
down_revision = '002_saved_ofertas'
branch_labels = None
depends_on = None


USER_ROLE_VALUES = ('student', 'psychologist', 'school_admin', 'super_admin')


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def enum_exists(enum_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": enum_name},
    ).scalar()
    return result is not None


def upgrade() -> None:
    # Create the enum type if it does not exist (idempotent)
    if not enum_exists('userrole'):
        user_role_enum = sa.Enum(*USER_ROLE_VALUES, name='userrole')
        user_role_enum.create(op.get_bind(), checkfirst=True)

    # Add the role column with default 'student' for existing rows
    if not column_exists('users', 'role'):
        op.add_column(
            'users',
            sa.Column(
                'role',
                sa.Enum(*USER_ROLE_VALUES, name='userrole', create_type=False),
                nullable=False,
                server_default='student',
            ),
        )

        # Drop server_default after backfill so application code controls
        # the value going forward (avoids silent inserts without explicit role)
        op.alter_column('users', 'role', server_default=None)


def downgrade() -> None:
    if column_exists('users', 'role'):
        op.drop_column('users', 'role')

    if enum_exists('userrole'):
        sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
