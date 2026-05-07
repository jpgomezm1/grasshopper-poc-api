"""Saved searches + lead comments · gh_commercial productivity

Revision ID: 020_saved_searches_and_comments
Revises: 019_lead_tags
Create Date: 2026-05-03

GH-COMMPROD-D3 + F1 · Sprint gh_commercial productivity 2026-05-03.

Changes:

    saved_searches
        id          UUID PK
        user_id     UUID FK users(id) ON DELETE CASCADE   · idx
        name        VARCHAR(120) NOT NULL
        filters     JSONB NOT NULL
        pinned      BOOLEAN NOT NULL DEFAULT false
        created_at  TIMESTAMP NOT NULL DEFAULT NOW
        UNIQUE (user_id, name)

    lead_comments
        id              UUID PK
        lead_user_id    UUID FK users(id) ON DELETE CASCADE       · idx
        author_user_id  UUID FK users(id) ON DELETE SET NULL
        body            TEXT NOT NULL
        mentions        JSONB NULL                                 · array of UUIDs
        parent_id       UUID FK lead_comments(id) ON DELETE CASCADE · NULL = root
        created_at      TIMESTAMP NOT NULL DEFAULT NOW
        edited_at       TIMESTAMP NULL

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '020_saved_searches_and_comments'
down_revision = '019_lead_tags'
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
    # 1. saved_searches
    if not _table_exists('saved_searches'):
        op.create_table(
            'saved_searches',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('filters', postgresql.JSONB(), nullable=False),
            sa.Column(
                'pinned',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint('user_id', 'name', name='uq_saved_search_per_user'),
        )

    if not _index_exists('saved_searches', 'ix_saved_searches_user'):
        op.create_index(
            'ix_saved_searches_user',
            'saved_searches',
            ['user_id'],
        )

    # 2. lead_comments
    if not _table_exists('lead_comments'):
        op.create_table(
            'lead_comments',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'lead_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'author_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('mentions', postgresql.JSONB(), nullable=True),
            sa.Column(
                'parent_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('lead_comments.id', ondelete='CASCADE'),
                nullable=True,
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('edited_at', sa.DateTime(), nullable=True),
        )

    if not _index_exists('lead_comments', 'ix_lead_comments_lead_created'):
        op.create_index(
            'ix_lead_comments_lead_created',
            'lead_comments',
            ['lead_user_id', sa.text('created_at DESC')],
        )

    if not _index_exists('lead_comments', 'ix_lead_comments_parent'):
        op.create_index(
            'ix_lead_comments_parent',
            'lead_comments',
            ['parent_id'],
            postgresql_where=sa.text('parent_id IS NOT NULL'),
        )


def downgrade() -> None:
    for ix in ('ix_lead_comments_parent', 'ix_lead_comments_lead_created'):
        if _index_exists('lead_comments', ix):
            op.drop_index(ix, table_name='lead_comments')
    if _table_exists('lead_comments'):
        op.drop_table('lead_comments')

    if _index_exists('saved_searches', 'ix_saved_searches_user'):
        op.drop_index('ix_saved_searches_user', table_name='saved_searches')
    if _table_exists('saved_searches'):
        op.drop_table('saved_searches')
