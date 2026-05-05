"""Lead tags + assignments · gh_commercial productivity

Revision ID: 019_lead_tags
Revises: 018_lead_assignment_and_tasks
Create Date: 2026-05-03

GH-COMMPROD-D1 · Sprint gh_commercial productivity 2026-05-03.

Changes:

    lead_tags
        id           UUID PK
        key          VARCHAR(60) NOT NULL UNIQUE   · slug stable
        label        VARCHAR(120) NOT NULL
        color        VARCHAR(20) NULL              · token semántico
        created_at   TIMESTAMP NOT NULL DEFAULT NOW

    lead_tag_assignments
        id              UUID PK
        lead_user_id    UUID FK users(id) ON DELETE CASCADE   · idx
        tag_id          UUID FK lead_tags(id) ON DELETE CASCADE · idx
        assigned_by     UUID FK users(id) ON DELETE SET NULL
        assigned_at     TIMESTAMP NOT NULL DEFAULT NOW
        UNIQUE (lead_user_id, tag_id)

Default seed (inserted in upgrade):
    presupuesto-premium · papas-involucrados · decision-rapida ·
    interes-usa · interes-europa · followup-urgente

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '019_lead_tags'
down_revision = '018_lead_assignment_and_tasks'
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


SEED_TAGS = (
    ("presupuesto-premium", "Presupuesto premium", "amber"),
    ("papas-involucrados", "Papás involucrados", "violet"),
    ("decision-rapida", "Decisión rápida", "lime"),
    ("interes-usa", "Interés USA", "blue"),
    ("interes-europa", "Interés Europa", "indigo"),
    ("followup-urgente", "Follow-up urgente", "rose"),
)


def upgrade() -> None:
    if not _table_exists('lead_tags'):
        op.create_table(
            'lead_tags',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('key', sa.String(60), nullable=False, unique=True),
            sa.Column('label', sa.String(120), nullable=False),
            sa.Column('color', sa.String(20), nullable=True),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _table_exists('lead_tag_assignments'):
        op.create_table(
            'lead_tag_assignments',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'lead_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'tag_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('lead_tags.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'assigned_by',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column(
                'assigned_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint('lead_user_id', 'tag_id', name='uq_lead_tag'),
        )

    if not _index_exists('lead_tag_assignments', 'ix_lead_tag_assignments_lead'):
        op.create_index(
            'ix_lead_tag_assignments_lead',
            'lead_tag_assignments',
            ['lead_user_id'],
        )

    if not _index_exists('lead_tag_assignments', 'ix_lead_tag_assignments_tag'):
        op.create_index(
            'ix_lead_tag_assignments_tag',
            'lead_tag_assignments',
            ['tag_id'],
        )

    # Seed default tags · idempotent (skip rows whose key already exists)
    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(sa.text("SELECT key FROM lead_tags")).fetchall()}
    import uuid as _uuid
    for key, label, color in SEED_TAGS:
        if key in existing:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO lead_tags (id, key, label, color, created_at) "
                "VALUES (:id, :key, :label, :color, NOW())"
            ),
            {
                "id": str(_uuid.uuid4()),
                "key": key,
                "label": label,
                "color": color,
            },
        )


def downgrade() -> None:
    for ix in ('ix_lead_tag_assignments_tag', 'ix_lead_tag_assignments_lead'):
        if _index_exists('lead_tag_assignments', ix):
            op.drop_index(ix, table_name='lead_tag_assignments')
    if _table_exists('lead_tag_assignments'):
        op.drop_table('lead_tag_assignments')
    if _table_exists('lead_tags'):
        op.drop_table('lead_tags')
