"""Lead assignment + tasks · gh_commercial productivity

Revision ID: 018_lead_assignment_and_tasks
Revises: 017_notifications_and_push_subscriptions
Create Date: 2026-05-03

GH-COMMPROD-B2/B3 · Sprint gh_commercial productivity 2026-05-03.

Changes:

    users
        + assigned_to_user_id  UUID NULL FK users(id) ON DELETE SET NULL
              · only meaningful for users that act as a lead (student / B2C)
              · target user MUST be gh_commercial / gh_advisor (enforced
                in service · NOT a DB constraint to keep enum-agnostic)
        + assigned_at          TIMESTAMP NULL
        idx (assigned_to_user_id) · partial WHERE NOT NULL

    tasks
        id                    UUID PK
        assigned_to_user_id   UUID FK users(id) ON DELETE CASCADE   · idx
        lead_user_id          UUID FK users(id) ON DELETE SET NULL  · idx · nullable
        description           TEXT NOT NULL
        due_at                TIMESTAMP NULL                          · idx
        priority              VARCHAR(10) NOT NULL DEFAULT 'normal'   · low|normal|high
        status                VARCHAR(10) NOT NULL DEFAULT 'open'     · open|done|cancelled
        created_by_user_id    UUID FK users(id) ON DELETE SET NULL    · audit
        created_at            TIMESTAMP NOT NULL DEFAULT NOW
        completed_at          TIMESTAMP NULL
        notified_due_at       TIMESTAMP NULL · stamp when "1h before" notif fired

Idempotent · safe to re-run.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '018_lead_assignment_and_tasks'
down_revision = '017_notifications_and_push_subscriptions'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


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


def _constraint_exists(table: str, constraint: str) -> bool:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :c"
        ),
        {"t": table, "c": constraint},
    ).fetchall()
    return bool(rows)


ALLOWED_PRIORITIES = ("low", "normal", "high")
ALLOWED_TASK_STATUSES = ("open", "done", "cancelled")


def upgrade() -> None:
    # 1. users.assigned_to_user_id
    if not _column_exists('users', 'assigned_to_user_id'):
        op.add_column(
            'users',
            sa.Column(
                'assigned_to_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )

    if not _column_exists('users', 'assigned_at'):
        op.add_column(
            'users',
            sa.Column('assigned_at', sa.DateTime(), nullable=True),
        )

    if not _index_exists('users', 'ix_users_assigned_to'):
        op.create_index(
            'ix_users_assigned_to',
            'users',
            ['assigned_to_user_id'],
            postgresql_where=sa.text('assigned_to_user_id IS NOT NULL'),
        )

    # 2. tasks
    if not _table_exists('tasks'):
        op.create_table(
            'tasks',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'assigned_to_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column(
                'lead_user_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('due_at', sa.DateTime(), nullable=True),
            sa.Column(
                'priority',
                sa.String(10),
                nullable=False,
                server_default='normal',
            ),
            sa.Column(
                'status',
                sa.String(10),
                nullable=False,
                server_default='open',
            ),
            sa.Column(
                'created_by_user_id',
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
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('notified_due_at', sa.DateTime(), nullable=True),
        )

    # CHECK constraints (idempotent)
    if not _constraint_exists('tasks', 'ck_tasks_priority'):
        op.create_check_constraint(
            'ck_tasks_priority',
            'tasks',
            "priority IN ({allowed})".format(
                allowed=", ".join(f"'{p}'" for p in ALLOWED_PRIORITIES)
            ),
        )

    if not _constraint_exists('tasks', 'ck_tasks_status'):
        op.create_check_constraint(
            'ck_tasks_status',
            'tasks',
            "status IN ({allowed})".format(
                allowed=", ".join(f"'{s}'" for s in ALLOWED_TASK_STATUSES)
            ),
        )

    # Indexes
    if not _index_exists('tasks', 'ix_tasks_assigned_status'):
        op.create_index(
            'ix_tasks_assigned_status',
            'tasks',
            ['assigned_to_user_id', 'status'],
        )

    if not _index_exists('tasks', 'ix_tasks_lead'):
        op.create_index(
            'ix_tasks_lead',
            'tasks',
            ['lead_user_id'],
            postgresql_where=sa.text('lead_user_id IS NOT NULL'),
        )

    if not _index_exists('tasks', 'ix_tasks_due_open'):
        op.create_index(
            'ix_tasks_due_open',
            'tasks',
            ['due_at'],
            postgresql_where=sa.text("status = 'open' AND due_at IS NOT NULL"),
        )


def downgrade() -> None:
    for ix in ('ix_tasks_due_open', 'ix_tasks_lead', 'ix_tasks_assigned_status'):
        if _index_exists('tasks', ix):
            op.drop_index(ix, table_name='tasks')

    if _constraint_exists('tasks', 'ck_tasks_status'):
        op.drop_constraint('ck_tasks_status', 'tasks', type_='check')
    if _constraint_exists('tasks', 'ck_tasks_priority'):
        op.drop_constraint('ck_tasks_priority', 'tasks', type_='check')

    if _table_exists('tasks'):
        op.drop_table('tasks')

    if _index_exists('users', 'ix_users_assigned_to'):
        op.drop_index('ix_users_assigned_to', table_name='users')

    if _column_exists('users', 'assigned_at'):
        op.drop_column('users', 'assigned_at')
    if _column_exists('users', 'assigned_to_user_id'):
        op.drop_column('users', 'assigned_to_user_id')
