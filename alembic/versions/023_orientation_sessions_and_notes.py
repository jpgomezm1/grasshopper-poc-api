"""Orientation sessions + session notes · gh_advisor clinical toolkit

Revision ID: 023_orientation_sessions_and_notes
Revises: 022_student_dossier_notes
Create Date: 2026-05-04

GH-ADVISOR-CLINICAL · Bloque E · Sprint advisor clinical 2026-05-04.

Changes:

    orientation_sessions
        id               UUID PK
        advisor_user_id  UUID FK users(id) ON DELETE CASCADE  · idx
        student_user_id  UUID FK users(id) ON DELETE CASCADE  · idx
        scheduled_at     TIMESTAMP NOT NULL                    · idx
        duration_min     INTEGER NULL
        type             VARCHAR(20) NOT NULL  · enum string
                         · first_contact | exploration | deepening
                         · decision | followup
        status           VARCHAR(20) NOT NULL DEFAULT 'scheduled'
                         · scheduled | completed | cancelled | no_show
        summary          TEXT NULL
        created_at       TIMESTAMP NOT NULL DEFAULT NOW
        updated_at       TIMESTAMP NOT NULL DEFAULT NOW

    session_notes
        id              UUID PK
        session_id      UUID FK orientation_sessions(id) ON DELETE CASCADE  · idx
        advisor_user_id UUID FK users(id) ON DELETE SET NULL                · idx
        content         TEXT NOT NULL
        privacy         VARCHAR(20) NOT NULL DEFAULT 'private'
                        · private | shared_supervisor | shared_team
        created_at      TIMESTAMP NOT NULL DEFAULT NOW
        updated_at      TIMESTAMP NOT NULL DEFAULT NOW

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '023_orientation_sessions_and_notes'
down_revision = '022_student_dossier_notes'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return name in inspector.get_table_names()


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    if not _table_exists('orientation_sessions'):
        op.create_table(
            'orientation_sessions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'advisor_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'student_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('scheduled_at', sa.DateTime(), nullable=False),
            sa.Column('duration_min', sa.Integer(), nullable=True),
            sa.Column('type', sa.String(20), nullable=False),
            sa.Column(
                'status',
                sa.String(20),
                nullable=False,
                server_default='scheduled',
            ),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    for col in ('advisor_user_id', 'student_user_id', 'scheduled_at', 'status'):
        idx_name = f'ix_orientation_sessions_{col}'
        if not _index_exists('orientation_sessions', idx_name):
            op.create_index(idx_name, 'orientation_sessions', [col])

    if not _table_exists('session_notes'):
        op.create_table(
            'session_notes',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'session_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('orientation_sessions.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'advisor_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column(
                'privacy',
                sa.String(20),
                nullable=False,
                server_default='private',
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    for col in ('session_id', 'advisor_user_id', 'privacy'):
        idx_name = f'ix_session_notes_{col}'
        if not _index_exists('session_notes', idx_name):
            op.create_index(idx_name, 'session_notes', [col])


def downgrade() -> None:
    if _table_exists('session_notes'):
        for col in ('privacy', 'advisor_user_id', 'session_id'):
            idx_name = f'ix_session_notes_{col}'
            if _index_exists('session_notes', idx_name):
                op.drop_index(idx_name, table_name='session_notes')
        op.drop_table('session_notes')
    if _table_exists('orientation_sessions'):
        for col in ('status', 'scheduled_at', 'student_user_id', 'advisor_user_id'):
            idx_name = f'ix_orientation_sessions_{col}'
            if _index_exists('orientation_sessions', idx_name):
                op.drop_index(idx_name, table_name='orientation_sessions')
        op.drop_table('orientation_sessions')
