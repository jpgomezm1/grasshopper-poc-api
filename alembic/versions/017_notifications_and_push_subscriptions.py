"""Notifications + push subscriptions · gh_commercial productivity

Revision ID: 017_notifications_and_push_subscriptions
Revises: 016_crm_pipeline_status_and_ai_cache
Create Date: 2026-05-03

GH-COMMPROD-A1/A2 · Sprint gh_commercial productivity 2026-05-03.

Adds:

    notifications
        id            UUID PK
        user_id       UUID FK users(id) ON DELETE CASCADE   · idx
        type          VARCHAR(60)                             · whitelisted in service
        title         VARCHAR(255)
        body          TEXT NULL
        data          JSONB NULL                              · arbitrary action payload
        read_at       TIMESTAMP NULL                          · NULL = unread
        created_at    TIMESTAMP NOT NULL DEFAULT NOW
        idx (user_id, read_at)                                · feed query path
        idx (user_id, created_at DESC)                        · paginate-by-recency

    push_subscriptions
        id            UUID PK
        user_id       UUID FK users(id) ON DELETE CASCADE     · idx
        endpoint      TEXT NOT NULL UNIQUE                    · web-push URL
        p256dh        TEXT NOT NULL
        auth          TEXT NOT NULL
        user_agent    VARCHAR(255) NULL
        created_at    TIMESTAMP NOT NULL DEFAULT NOW
        last_used_at  TIMESTAMP NULL

Privacy:
    notification.body may contain lead names but never raw journal content.
    push subscriptions hold opaque tokens (no PII).

Idempotent · safe to re-run.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '017_notifications_and_push_subscriptions'
down_revision = '016_crm_pipeline_status_and_ai_cache'
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
    # 1. notifications
    if not _table_exists('notifications'):
        op.create_table(
            'notifications',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('type', sa.String(60), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('body', sa.Text(), nullable=True),
            sa.Column('data', postgresql.JSONB(), nullable=True),
            sa.Column('read_at', sa.DateTime(), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _index_exists('notifications', 'ix_notifications_user_read'):
        op.create_index(
            'ix_notifications_user_read',
            'notifications',
            ['user_id', 'read_at'],
        )

    if not _index_exists('notifications', 'ix_notifications_user_created'):
        op.create_index(
            'ix_notifications_user_created',
            'notifications',
            ['user_id', sa.text('created_at DESC')],
        )

    if not _index_exists('notifications', 'ix_notifications_type'):
        op.create_index(
            'ix_notifications_type',
            'notifications',
            ['type'],
        )

    # 2. push_subscriptions
    if not _table_exists('push_subscriptions'):
        op.create_table(
            'push_subscriptions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('endpoint', sa.Text(), nullable=False, unique=True),
            sa.Column('p256dh', sa.Text(), nullable=False),
            sa.Column('auth', sa.Text(), nullable=False),
            sa.Column('user_agent', sa.String(255), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
        )

    if not _index_exists('push_subscriptions', 'ix_push_subscriptions_user'):
        op.create_index(
            'ix_push_subscriptions_user',
            'push_subscriptions',
            ['user_id'],
        )


def downgrade() -> None:
    if _index_exists('push_subscriptions', 'ix_push_subscriptions_user'):
        op.drop_index('ix_push_subscriptions_user', table_name='push_subscriptions')
    if _table_exists('push_subscriptions'):
        op.drop_table('push_subscriptions')

    for ix in (
        'ix_notifications_type',
        'ix_notifications_user_created',
        'ix_notifications_user_read',
    ):
        if _index_exists('notifications', ix):
            op.drop_index(ix, table_name='notifications')
    if _table_exists('notifications'):
        op.drop_table('notifications')
