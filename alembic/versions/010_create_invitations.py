"""Sprint 9 · Invitations table for school onboarding (students + psychologists)

Revision ID: 010_create_invitations
Revises: 009_create_sprint8_super_admin
Create Date: 2026-04-30

GH-S9 · Adds the `invitations` table that backs the panel B2B flow.

Schema:

    id              UUID PK
    school_id       UUID FK → schools.id (CASCADE)
    email           str(255) · invitee email · normalized lowercase
    role            str(30) · 'student' | 'psychologist'
    token           str(120) · URL-safe random · unique
    status          str(20) · 'pending' | 'accepted' | 'expired' | 'revoked'
    expires_at      DateTime · default +14d at creation time
    accepted_at     DateTime nullable
    accepted_user   UUID FK → users.id (SET NULL) · created when accepted
    invited_by      UUID FK → users.id (SET NULL) · school_admin / psychologist
    created_at      DateTime
    updated_at      DateTime

Indexes:
    - (school_id, status) · the panel paginates these
    - token (unique) · accept flow lookup
    - email + status (helps avoid duplicate pending invites)

Idempotent: uses table_exists guards.
Rollback: drops table + indexes in reverse order.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '010_create_invitations'
down_revision = '009_create_sprint8_super_admin'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if table_exists('invitations'):
        return

    op.create_table(
        'invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'school_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('schools.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('role', sa.String(30), nullable=False),
        sa.Column('token', sa.String(120), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('expires_at', sa.DateTime, nullable=False),
        sa.Column('accepted_at', sa.DateTime, nullable=True),
        sa.Column(
            'accepted_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'invited_by_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            'updated_at',
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_invitations_school_id', 'invitations', ['school_id'])
    op.create_index('ix_invitations_token', 'invitations', ['token'], unique=True)
    op.create_index('ix_invitations_email', 'invitations', ['email'])
    op.create_index('ix_invitations_status', 'invitations', ['status'])
    op.create_index(
        'ix_invitations_school_status',
        'invitations',
        ['school_id', 'status'],
    )


def downgrade() -> None:
    if not table_exists('invitations'):
        return
    op.drop_index('ix_invitations_school_status', table_name='invitations')
    op.drop_index('ix_invitations_status', table_name='invitations')
    op.drop_index('ix_invitations_email', table_name='invitations')
    op.drop_index('ix_invitations_token', table_name='invitations')
    op.drop_index('ix_invitations_school_id', table_name='invitations')
    op.drop_table('invitations')
