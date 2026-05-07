"""Add school_mass_message_reads · per-recipient read receipts.

Revision ID: 032_parent_message_reads
Revises: 031_journey_completed_at
Create Date: 2026-05-05

GH-PARENT-EXPERIENCE · Sprint parent-experience 2026-05-05 · Bloque B.

A read receipt table is needed because `school_mass_messages` represents one
broadcast row per send, while parents (and eventually students) consume the
same row independently. The `opened_count` aggregate stays untouched so the
school_admin metrics are not affected.

Schema:
    school_mass_message_reads
        id           UUID PRIMARY KEY
        message_id   UUID NOT NULL FK → school_mass_messages(id) ON DELETE CASCADE
        user_id      UUID NOT NULL FK → users(id) ON DELETE CASCADE
        read_at      TIMESTAMP NOT NULL DEFAULT NOW()
        UNIQUE (message_id, user_id)        · idempotent mark-as-read

Indexes are in the unique constraint + a single-column user_id idx for the
unread-count query.

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '032_parent_message_reads'
down_revision = '031_journey_completed_at'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists('school_mass_message_reads'):
        return
    op.create_table(
        'school_mass_message_reads',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, nullable=False),
        sa.Column('message_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('school_mass_messages.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('message_id', 'user_id',
                            name='uq_mass_msg_reads_msg_user'),
    )
    op.create_index(
        'ix_mass_msg_reads_user',
        'school_mass_message_reads',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    if not _table_exists('school_mass_message_reads'):
        return
    op.drop_index('ix_mass_msg_reads_user', table_name='school_mass_message_reads')
    op.drop_table('school_mass_message_reads')
