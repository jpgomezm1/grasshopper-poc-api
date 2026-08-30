"""La escala del GPA de admisión del programa · el dato que faltaba para comparar.

`programs.avg_admitted_gpa` es un `Float` **sin escala**, y eso es una bomba de
tiempo: un 4.2 sobre 5.0 (Colombia) traducido es 3.36 y está POR DEBAJO de un
3.8 sobre 4.0 (EE. UU.) — pero comparados crudos, 4.2 > 3.8. El clasificador
Reach/Match/Safety comparaba exactamente así.

Hoy es inofensivo porque `classify()` nunca recibe el GPA del estudiante. Deja
de serlo el día que se cargue el Excel de admisión de la clienta: ahí el badge
empezaría a decir "safety" donde debía decir "reach", en silencio y en la
pantalla que más pesa de 11°.

La columna es la mitad que faltaba. La ficha del estudiante ya guarda SIEMPRE
`gpa` junto a `gpa_scale` (migración 072) precisamente por esto; el programa no
tenía dónde declarar la suya.

Additiva y nullable: los 2.562 programas actuales quedan con `NULL`, que
significa "no sabemos en qué escala está ese promedio" — y el clasificador
prefiere no usar esa señal antes que inventarse la equivalencia.

Revision ID: 074_escala_gpa_programa
Revises: 073_presupuesto_familiar
"""
from alembic import op
import sqlalchemy as sa


revision = '074_escala_gpa_programa'
down_revision = '073_presupuesto_familiar'
branch_labels = None
depends_on = None


def upgrade() -> None:
    columnas = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('programs')}
    if 'avg_admitted_gpa_scale' not in columnas:
        op.add_column(
            'programs',
            sa.Column('avg_admitted_gpa_scale', sa.Float(), nullable=True),
        )


def downgrade() -> None:
    columnas = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('programs')}
    if 'avg_admitted_gpa_scale' in columnas:
        op.drop_column('programs', 'avg_admitted_gpa_scale')
