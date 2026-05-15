"""At-rest encryption for clinical_analysis_cache · GH-F1-SECURITY Tarea 4.

Revision ID: 037_encrypt_clinical_analysis
Revises: 036_flags_prompts_configs
Create Date: 2026-05-15

Migration strategy (2-phase):
  FASE A (este migration): agrega columna `clinical_analysis_cache_enc` BYTEA.
    · La columna vieja `clinical_analysis_cache` se deja intacta.
    · NO se migran datos aquí: evita riesgo transaccional y dependencia circular
      con el código de app (importar crypto.py desde Alembic puede fallar si
      FIELD_ENCRYPTION_KEY no está en el entorno de CI/alembic).
    · El servicio lee `_enc` primero y cae a la columna vieja para rows legacy
      (zero downtime, sin data loss).

  FASE B (script manual, correr en prod después de validar FASE A):
    · Ver docs/runbooks/MIGRATION_037_PHASE_B.md para instrucciones completas.
    · El script de migración de datos es:

        python scripts/migrate_clinical_data.py [--dry-run] [--chunk-size 100]

    · El script (ya creado en scripts/) es transaccionalmente seguro:
        - Itera en chunks de 100 rows
        - flush + verificación antes de nullear la columna vieja
        - Rollback por chunk en caso de error (no aborta la migración entera)
        - Resumen final: migrated=X · failed=Y · skipped=Z

  downgrade(): remueve solo la columna _enc. La columna original queda intacta.
"""
from alembic import op
import sqlalchemy as sa


revision = "037_encrypt_clinical_analysis"
down_revision = "036_flags_prompts_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add clinical_analysis_cache_enc BYTEA column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "clinical_analysis_cache_enc",
            sa.LargeBinary(),
            nullable=True,
            comment=(
                "AES-256-GCM encrypted clinical analysis cache. "
                "GH-F1-SECURITY · Tarea 4 · Ley 1581/2012 art.5 + Ley 1090/2006. "
                "Replaces clinical_analysis_cache (JSON/JSONB). "
                "Encrypted by app.core.crypto with FIELD_ENCRYPTION_KEY env var."
            ),
        ),
    )


def downgrade() -> None:
    """Remove clinical_analysis_cache_enc column from users table."""
    op.drop_column("users", "clinical_analysis_cache_enc")
