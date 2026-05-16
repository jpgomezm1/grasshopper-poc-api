"""Add pipeline_status_version to users for optimistic locking.

Revision ID: 038_pipeline_status_version
Revises: 037_encrypt_clinical_analysis
Create Date: 2026-05-15

QA-AUD-072 · Race condition fix.

Agrega `pipeline_status_version` (Integer, default 1) a la tabla `users`.
Permite implementar compare-and-swap atómico en update_pipeline_status:
el UPDATE solo se ejecuta si la versión en DB coincide con la que el
cliente tenía al momento de leer el registro.

Si el UPDATE afecta 0 filas → la versión cambió por una escritura concurrente
→ el servicio lanza StaleOpportunityError (409 Conflict al cliente).

downgrade(): DROP COLUMN pipeline_status_version (reversible limpio).
"""
from alembic import op
import sqlalchemy as sa


revision = "038_pipeline_status_version"
down_revision = "037_encrypt_clinical_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable=True + server_default para que el ALTER no requiera rewrite
    # de toda la tabla en Postgres. El servicio siempre provee el valor.
    op.add_column(
        "users",
        sa.Column(
            "pipeline_status_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "pipeline_status_version")
