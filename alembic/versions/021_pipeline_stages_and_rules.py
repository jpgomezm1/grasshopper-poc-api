"""Pipeline stages + auto-assign rules + pipeline rules · gh_commercial productivity

Revision ID: 021_pipeline_stages_and_rules
Revises: 020_saved_searches_and_comments
Create Date: 2026-05-03

GH-COMMPROD-B6 + E1 + E2 · Sprint gh_commercial productivity 2026-05-03.

Changes:

    pipeline_stages
        id           UUID PK
        key          VARCHAR(40) NOT NULL UNIQUE  · slug stable
        label        VARCHAR(120) NOT NULL
        color        VARCHAR(20) NULL
        order_index  INTEGER NOT NULL
        is_default   BOOLEAN NOT NULL DEFAULT false
        created_at   TIMESTAMP NOT NULL DEFAULT NOW
        updated_at   TIMESTAMP NOT NULL DEFAULT NOW

    auto_assign_rules
        id           UUID PK
        strategy     VARCHAR(40) NOT NULL  · round_robin|least_loaded|by_country|by_language
        config       JSONB NULL            · strategy params
        is_active    BOOLEAN NOT NULL DEFAULT true
        priority     INTEGER NOT NULL DEFAULT 100
        created_at   TIMESTAMP NOT NULL DEFAULT NOW
        updated_at   TIMESTAMP NOT NULL DEFAULT NOW

    pipeline_rules
        id           UUID PK
        name         VARCHAR(120) NOT NULL
        condition    JSONB NOT NULL  · {when: 'score_gte', value: 80, status: 'pending', hours: 24}
        action       JSONB NOT NULL  · {move_to: 'qualified', notify: true, tag: 'urgente'}
        is_active    BOOLEAN NOT NULL DEFAULT true
        created_at   TIMESTAMP NOT NULL DEFAULT NOW
        updated_at   TIMESTAMP NOT NULL DEFAULT NOW

Default seeds:
    pipeline_stages: pending · contacted · qualified · converted · declined
    pipeline_rules:
        - "Lead caliente sin contactar 24h" → mover qualified + notif
        - "Lead nuevo phase_b" → tag follow-up urgente

Idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '021_pipeline_stages_and_rules'
down_revision = '020_saved_searches_and_comments'
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


SEED_STAGES = (
    ("pending", "Pendiente", "slate", 10),
    ("contacted", "Contactado", "amber", 20),
    ("qualified", "Calificado", "violet", 30),
    ("converted", "Convertido", "lime", 40),
    ("declined", "Descartado", "rose", 50),
)


def upgrade() -> None:
    # 1. pipeline_stages
    if not _table_exists('pipeline_stages'):
        op.create_table(
            'pipeline_stages',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('key', sa.String(40), nullable=False, unique=True),
            sa.Column('label', sa.String(120), nullable=False),
            sa.Column('color', sa.String(20), nullable=True),
            sa.Column('order_index', sa.Integer(), nullable=False),
            sa.Column(
                'is_default',
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
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # 2. auto_assign_rules
    if not _table_exists('auto_assign_rules'):
        op.create_table(
            'auto_assign_rules',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('strategy', sa.String(40), nullable=False),
            sa.Column('config', postgresql.JSONB(), nullable=True),
            sa.Column(
                'is_active',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('true'),
            ),
            sa.Column(
                'priority',
                sa.Integer(),
                nullable=False,
                server_default='100',
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

    # 3. pipeline_rules
    if not _table_exists('pipeline_rules'):
        op.create_table(
            'pipeline_rules',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('condition', postgresql.JSONB(), nullable=False),
            sa.Column('action', postgresql.JSONB(), nullable=False),
            sa.Column(
                'is_active',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('true'),
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

    # Seeds
    bind = op.get_bind()
    import uuid as _uuid

    # Pipeline stages seed
    existing_stages = {r[0] for r in bind.execute(sa.text("SELECT key FROM pipeline_stages")).fetchall()}
    for key, label, color, order_index in SEED_STAGES:
        if key in existing_stages:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO pipeline_stages (id, key, label, color, order_index, is_default, created_at, updated_at) "
                "VALUES (:id, :key, :label, :color, :order_index, true, NOW(), NOW())"
            ),
            {
                "id": str(_uuid.uuid4()),
                "key": key,
                "label": label,
                "color": color,
                "order_index": order_index,
            },
        )

    # Default auto-assign rule (round-robin) only if no rules exist
    existing_rules_count = bind.execute(sa.text("SELECT COUNT(*) FROM auto_assign_rules")).scalar()
    if (existing_rules_count or 0) == 0:
        bind.execute(
            sa.text(
                "INSERT INTO auto_assign_rules (id, strategy, config, is_active, priority, created_at, updated_at) "
                "VALUES (:id, 'round_robin', '{}', true, 100, NOW(), NOW())"
            ),
            {"id": str(_uuid.uuid4())},
        )

    # Default pipeline rules · 2 useful seeds
    import json as _json
    existing_pipe_count = bind.execute(sa.text("SELECT COUNT(*) FROM pipeline_rules")).scalar()
    if (existing_pipe_count or 0) == 0:
        bind.execute(
            sa.text(
                "INSERT INTO pipeline_rules (id, name, condition, action, is_active, created_at, updated_at) "
                "VALUES (:id, :name, CAST(:cond AS JSONB), CAST(:act AS JSONB), true, NOW(), NOW())"
            ),
            {
                "id": str(_uuid.uuid4()),
                "name": "Lead caliente sin contactar 24h",
                "cond": _json.dumps({
                    "score_gte": 80,
                    "status": "pending",
                    "hours_in_status_gte": 24,
                }),
                "act": _json.dumps({
                    "move_to": "contacted",
                    "notify": True,
                }),
            },
        )
        bind.execute(
            sa.text(
                "INSERT INTO pipeline_rules (id, name, condition, action, is_active, created_at, updated_at) "
                "VALUES (:id, :name, CAST(:cond AS JSONB), CAST(:act AS JSONB), true, NOW(), NOW())"
            ),
            {
                "id": str(_uuid.uuid4()),
                "name": "Lead phase_b → tag follow-up urgente",
                "cond": _json.dumps({
                    "phase": "phase_b",
                }),
                "act": _json.dumps({
                    "tag": "followup-urgente",
                    "notify": False,
                }),
            },
        )


def downgrade() -> None:
    if _table_exists('pipeline_rules'):
        op.drop_table('pipeline_rules')
    if _table_exists('auto_assign_rules'):
        op.drop_table('auto_assign_rules')
    if _table_exists('pipeline_stages'):
        op.drop_table('pipeline_stages')
