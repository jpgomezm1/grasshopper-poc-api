"""Sprint 10 · Bitrix sync log + lead status fields on User

Revision ID: 011_create_bitrix_sync_log
Revises: 010_create_invitations
Create Date: 2026-04-30

GH-S10-DB-01 · Adds the `bitrix_sync_log` table that backs the Bitrix CRM
integration outbound + inbound flows.

Schema (`bitrix_sync_log`):

    id              UUID PK
    entity_type     str(40)  · 'user' | 'consolidated_profile' | 'report' | 'advisor_lead'
    entity_id       str(120) · referenced row id (UUID as string)
    user_id         UUID FK → users.id (SET NULL) · denormalized for filtering
    action          str(40)  · 'create' | 'update' | 'delete' | 'inbound_status'
    payload         JSON     · request payload sent to Bitrix
    bitrix_response JSON     · response (or null on hard failure)
    status          str(20)  · 'success' | 'retry' | 'failed' | 'stub' | 'pending'
    provider        str(20)  · 'bitrix' | 'stub'
    attempts        int      · default 0
    error_message   text     · last error, truncated to 500 chars
    synced_at       DateTime nullable · last successful sync time
    created_at      DateTime · row creation
    updated_at      DateTime · last write

Lead status fields appended to `users` for the inbound webhook
(BE-06 · Bitrix → Hopper):

    bitrix_lead_id              str(120) nullable · external ID of the Bitrix lead/contact
    bitrix_lead_status          str(40)  nullable · 'new' | 'qualified' | 'contacted' | 'lost' | ...
    bitrix_lead_status_at       DateTime nullable · timestamp of last status update

Indexes:
    bitrix_sync_log: (entity_type, entity_id) · (status) · (user_id) · (created_at desc)
    users: bitrix_lead_id (unique sparse) · bitrix_lead_status

Idempotent: uses table_exists / column inspection guards.
Rollback: drops added columns + indexes + table in reverse order.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '011_create_bitrix_sync_log'
down_revision = '010_create_invitations'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    # 1. bitrix_sync_log table
    if not table_exists('bitrix_sync_log'):
        op.create_table(
            'bitrix_sync_log',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('entity_type', sa.String(40), nullable=False),
            sa.Column('entity_id', sa.String(120), nullable=False),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('action', sa.String(40), nullable=False),
            sa.Column('payload', sa.JSON, nullable=True),
            sa.Column('bitrix_response', sa.JSON, nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('provider', sa.String(20), nullable=False, server_default='stub'),
            sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
            sa.Column('error_message', sa.Text, nullable=True),
            sa.Column('synced_at', sa.DateTime, nullable=True),
            sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            'ix_bitrix_sync_log_entity',
            'bitrix_sync_log',
            ['entity_type', 'entity_id'],
        )
        op.create_index('ix_bitrix_sync_log_status', 'bitrix_sync_log', ['status'])
        op.create_index('ix_bitrix_sync_log_user_id', 'bitrix_sync_log', ['user_id'])
        op.create_index(
            'ix_bitrix_sync_log_created_at',
            'bitrix_sync_log',
            ['created_at'],
        )

    # 2. users · bitrix lead status columns (inbound webhook BE-06)
    if not column_exists('users', 'bitrix_lead_id'):
        op.add_column('users', sa.Column('bitrix_lead_id', sa.String(120), nullable=True))
    if not column_exists('users', 'bitrix_lead_status'):
        op.add_column('users', sa.Column('bitrix_lead_status', sa.String(40), nullable=True))
    if not column_exists('users', 'bitrix_lead_status_at'):
        op.add_column(
            'users',
            sa.Column('bitrix_lead_status_at', sa.DateTime, nullable=True),
        )

    if not index_exists('users', 'ix_users_bitrix_lead_id'):
        op.create_index(
            'ix_users_bitrix_lead_id',
            'users',
            ['bitrix_lead_id'],
            unique=False,
        )
    if not index_exists('users', 'ix_users_bitrix_lead_status'):
        op.create_index(
            'ix_users_bitrix_lead_status',
            'users',
            ['bitrix_lead_status'],
            unique=False,
        )


def downgrade() -> None:
    if index_exists('users', 'ix_users_bitrix_lead_status'):
        op.drop_index('ix_users_bitrix_lead_status', table_name='users')
    if index_exists('users', 'ix_users_bitrix_lead_id'):
        op.drop_index('ix_users_bitrix_lead_id', table_name='users')
    if column_exists('users', 'bitrix_lead_status_at'):
        op.drop_column('users', 'bitrix_lead_status_at')
    if column_exists('users', 'bitrix_lead_status'):
        op.drop_column('users', 'bitrix_lead_status')
    if column_exists('users', 'bitrix_lead_id'):
        op.drop_column('users', 'bitrix_lead_id')

    if table_exists('bitrix_sync_log'):
        if index_exists('bitrix_sync_log', 'ix_bitrix_sync_log_created_at'):
            op.drop_index('ix_bitrix_sync_log_created_at', table_name='bitrix_sync_log')
        if index_exists('bitrix_sync_log', 'ix_bitrix_sync_log_user_id'):
            op.drop_index('ix_bitrix_sync_log_user_id', table_name='bitrix_sync_log')
        if index_exists('bitrix_sync_log', 'ix_bitrix_sync_log_status'):
            op.drop_index('ix_bitrix_sync_log_status', table_name='bitrix_sync_log')
        if index_exists('bitrix_sync_log', 'ix_bitrix_sync_log_entity'):
            op.drop_index('ix_bitrix_sync_log_entity', table_name='bitrix_sync_log')
        op.drop_table('bitrix_sync_log')
