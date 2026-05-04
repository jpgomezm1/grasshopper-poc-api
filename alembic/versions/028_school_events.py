"""School events + RSVPs

Revision ID: 028_school_events
Revises: 027_admin_notes_custom_fields
Create Date: 2026-05-04

GH-SCHOOL-ADMIN · Bloque E+G · Sprint school_admin 2026-05-04.

    school_events
        id              UUID PK
        school_id       UUID FK schools(id) ON DELETE CASCADE  · idx
        title           VARCHAR(200) NOT NULL
        description     TEXT NULL
        starts_at       TIMESTAMP NOT NULL · idx
        ends_at         TIMESTAMP NULL
        location        VARCHAR(200) NULL
        audience        VARCHAR(20) NOT NULL    · 'students'|'parents'|'both'
        created_by      UUID FK users(id) ON DELETE SET NULL
        created_at      TIMESTAMP
        archived_at     TIMESTAMP NULL

    school_event_rsvps
        id              UUID PK
        event_id        UUID FK school_events(id) ON DELETE CASCADE
        user_id         UUID FK users(id) ON DELETE CASCADE
        status          VARCHAR(20) NOT NULL    · 'going'|'maybe'|'declined'
        responded_at    TIMESTAMP
        UNIQUE (event_id, user_id)

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = '028_school_events'
down_revision = '027_admin_notes_custom_fields'
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
    if not _table_exists('school_events'):
        op.create_table(
            'school_events',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'school_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('schools.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('title', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('starts_at', sa.DateTime(), nullable=False),
            sa.Column('ends_at', sa.DateTime(), nullable=True),
            sa.Column('location', sa.String(200), nullable=True),
            sa.Column('audience', sa.String(20), nullable=False, server_default='both'),
            sa.Column(
                'created_by',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column('archived_at', sa.DateTime(), nullable=True),
        )

    if not _index_exists('school_events', 'ix_school_events_school_id'):
        op.create_index('ix_school_events_school_id', 'school_events', ['school_id'])

    if not _index_exists('school_events', 'ix_school_events_starts_at'):
        op.create_index('ix_school_events_starts_at', 'school_events', ['starts_at'])

    if not _table_exists('school_event_rsvps'):
        op.create_table(
            'school_event_rsvps',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'event_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('school_events.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column(
                'responded_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint('event_id', 'user_id', name='uq_event_rsvp_user'),
        )


def downgrade() -> None:
    if _table_exists('school_event_rsvps'):
        op.drop_table('school_event_rsvps')
    if _table_exists('school_events'):
        op.drop_table('school_events')
