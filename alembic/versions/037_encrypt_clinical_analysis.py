"""At-rest encryption for clinical_analysis_cache · GH-F1-SECURITY Tarea 4.

Revision ID: 037_encrypt_clinical_analysis
Revises: 036_flags_prompts_configs
Create Date: 2026-05-15

Migration strategy:
  · Add `clinical_analysis_cache_enc` BYTEA column (nullable).
  · Existing data in `clinical_analysis_cache` JSON column is NOT migrated
    here because:
      1. clinical_analysis_cache data is regenerable (30d TTL).
      2. We cannot safely encrypt with FIELD_ENCRYPTION_KEY inside Alembic
         without importing app code (creates circular-dependency risk).
      3. The service reads _enc first and falls back to the plaintext column
         for legacy rows, so no data is lost.
  · To explicitly migrate existing rows, run after deploying:
      python -c "
      from app.db.database import SessionLocal
      from app.db.models import User
      db = SessionLocal()
      for u in db.query(User).filter(User.clinical_analysis_cache.isnot(None)).all():
          u.clinical_analysis_cache_enc = u.clinical_analysis_cache
          u.clinical_analysis_cache = None
      db.commit(); db.close()
      print('Done')
      "
    This will encrypt existing rows using the current FIELD_ENCRYPTION_KEY.

  · downgrade() removes the new column. The original column is untouched.
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
