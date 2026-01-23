"""Add user_id column to sessions table

Revision ID: 001_add_user_id
Revises:
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '001_add_user_id'
down_revision = None
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add user_id column to sessions table if it doesn't exist
    if not column_exists('sessions', 'user_id'):
        op.add_column(
            'sessions',
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True)
        )

        # Add foreign key constraint
        op.create_foreign_key(
            'fk_sessions_user_id',
            'sessions',
            'users',
            ['user_id'],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade() -> None:
    if column_exists('sessions', 'user_id'):
        op.drop_constraint('fk_sessions_user_id', 'sessions', type_='foreignkey')
        op.drop_column('sessions', 'user_id')
