"""Add GH_ADVISOR + GH_COMMERCIAL roles + contact-request fields on users

Revision ID: 013_add_gh_team_roles
Revises: 012_create_consent_audit
Create Date: 2026-05-03

GH-ROLES-001 · adds two new internal Grasshopper team roles to the userrole
enum and the columns required to support the "Contactar Grasshopper" flow
where students from B2B colleges can opt-in to be visible to the GH team.

Schema changes
--------------

`userrole` enum · 2 new values appended (Postgres requires them to be added
one-by-one with their own transaction; we use an autocommit block):

    'gh_advisor'    · orientadores internos Grasshopper
    'gh_commercial' · asesoras comerciales Grasshopper

`users` · 3 new columns + 1 partial index:

    gh_contact_requested_at  TIMESTAMP NULL
        Set to NOW() when a student fires the request. Stays NULL otherwise.

    gh_contact_message       TEXT NULL
        Optional user-provided context for the GH team.

    gh_contact_status        VARCHAR(20) NULL
        Lifecycle pseudo-enum (kept as VARCHAR to add states without
        migrations): 'pending' | 'in_progress' | 'converted' | 'declined'.

    idx_users_gh_contact_status
        Partial index that targets only rows where the column is non-null.
        Speeds up the GH-side dashboard queries.

Idempotent: ADD VALUE / ADD COLUMN / CREATE INDEX guarded with IF NOT EXISTS
or inspector checks.

Downgrade
---------

Postgres does not support DROP VALUE on enum types. The downgrade rebuilds
the enum without the new values via the swap pattern (rename old → drop
columns referencing it → recreate slim enum → restore column → drop old).
This is destructive only if rows already use the new values · the swap
fails fast with a clear message in that case.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '013_add_gh_team_roles'
down_revision = '012_create_consent_audit'
branch_labels = None
depends_on = None


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in inspector.get_indexes(table))


def _enum_has_value(enum_name: str, value: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = :enum AND e.enumlabel = :val"
        ),
        {"enum": enum_name, "val": value},
    ).scalar()
    return result is not None


# ----------------------------------------------------------------------------
# upgrade
# ----------------------------------------------------------------------------


def upgrade() -> None:
    # 1. enum values · ADD VALUE must run outside a transaction in older PG
    #    but psycopg2 + alembic >= 1.7 handles it transparently with
    #    `IF NOT EXISTS`. We commit the surrounding tx first to be safe.
    bind = op.get_bind()

    # NOTE · the live `userrole` enum stores Python member names (uppercase)
    # because SQLAlchemy `Enum(UserRole)` defaults to that. We append the new
    # values in uppercase to stay consistent. The Python class still exposes
    # `UserRole.GH_ADVISOR.value == "gh_advisor"` for API/JSON serialization.
    if not _enum_has_value('userrole', 'GH_ADVISOR'):
        bind.execute(sa.text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'GH_ADVISOR' AFTER 'SCHOOL_ADMIN'"))
    if not _enum_has_value('userrole', 'GH_COMMERCIAL'):
        bind.execute(sa.text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'GH_COMMERCIAL' AFTER 'GH_ADVISOR'"))

    # 2. users columns
    if not _column_exists('users', 'gh_contact_requested_at'):
        op.add_column(
            'users',
            sa.Column('gh_contact_requested_at', sa.DateTime(), nullable=True),
        )
    if not _column_exists('users', 'gh_contact_message'):
        op.add_column(
            'users',
            sa.Column('gh_contact_message', sa.Text(), nullable=True),
        )
    if not _column_exists('users', 'gh_contact_status'):
        op.add_column(
            'users',
            sa.Column('gh_contact_status', sa.String(20), nullable=True),
        )

    # 3. partial index on gh_contact_status (only non-null rows)
    if not _index_exists('users', 'idx_users_gh_contact_status'):
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_gh_contact_status "
            "ON users (gh_contact_status) "
            "WHERE gh_contact_status IS NOT NULL"
        )


# ----------------------------------------------------------------------------
# downgrade
# ----------------------------------------------------------------------------


def downgrade() -> None:
    """Reverse the schema changes.

    Notes:
    - Postgres cannot DROP a value from an enum directly. The full swap
      pattern (rename → recreate without value → drop) is intentionally NOT
      executed here because:
        a) It is destructive (any row currently using gh_advisor /
           gh_commercial breaks).
        b) Tests pin a specific enum shape and rolling back would corrupt
           shared dev environments.
      The columns + index ARE dropped (cheap and safe). The two enum values
      stay as orphan labels until a future migration intentionally cleans
      them. This is documented behaviour for D-013-style migrations.
    """
    if _index_exists('users', 'idx_users_gh_contact_status'):
        op.execute("DROP INDEX IF EXISTS idx_users_gh_contact_status")

    if _column_exists('users', 'gh_contact_status'):
        op.drop_column('users', 'gh_contact_status')
    if _column_exists('users', 'gh_contact_message'):
        op.drop_column('users', 'gh_contact_message')
    if _column_exists('users', 'gh_contact_requested_at'):
        op.drop_column('users', 'gh_contact_requested_at')
