"""Add saved_ofertas table

Revision ID: 002_saved_ofertas
Revises: 001_add_user_id
Create Date: 2026-03-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '002_saved_ofertas'
down_revision = '001_add_user_id'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not table_exists('saved_ofertas'):
        op.create_table(
            'saved_ofertas',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('oferta_id', sa.String(100), nullable=False),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('status', sa.String(50), nullable=False, server_default='interested'),
            sa.UniqueConstraint('user_id', 'oferta_id', name='uq_user_oferta'),
        )


def downgrade() -> None:
    if table_exists('saved_ofertas'):
        op.drop_table('saved_ofertas')
