"""merge catalog/f006 (046) + f003 (047) heads

Revision ID: aa03aec05374
Revises: 046_human_intervention_notes, 047_programs_scholarships_latam
Create Date: 2026-05-28 15:50:17.751052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa03aec05374'
down_revision: Union[str, None] = ('046_human_intervention_notes', '047_programs_scholarships_latam')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
