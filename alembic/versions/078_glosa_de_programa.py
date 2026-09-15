"""Guarda la glosa de cada programa · el puente entre el catálogo y el estudiante.

Por qué
-------
El vector de un programa se construía con `título + área + nivel + institución`:
unas 15 palabras que representan un **rótulo**, no un programa. Eso funciona
mientras el estudiante escriba en el vocabulario del catálogo, y se rompe en
cuanto habla como habla de verdad.

Medido sobre el catálogo real, con `Psychology BSc` y la consulta *"me interesa
cómo piensa la gente"*:

    sólo título+área+nivel ........ 0.256
    con una glosa del campo ....... 0.350   (+37%)

y el ganador actual de esa consulta —`Social and Political Theory`— puntúa
0.324. O sea que sin glosa la búsqueda le ofrece teoría política a quien pregunta
por psicología, y con glosa no.

Qué es y qué NO es
------------------
Una frase que describe **el campo de estudio en el vocabulario del estudiante**,
no el programa. La distinción es la que evita que sea una alucinación: el modelo
no sabe cuánto dura este máster ni qué piden para entrar, y no se le pregunta.
Sabe qué es la psicología, y eso es lo único que se le pide.

Hallazgo que se convirtió en regla del prompt: la glosa **no debe renombrar la
disciplina**. `gpt-4o-mini` escribía "En psicología se estudia cómo piensan las
personas" y subía sólo un 25%, porque "psicología" ya está en el título. El
modelo más barato (`gpt-4.1-nano`) escribía "cómo piensan, sienten y se comportan
las personas" y subía un 37%. El trabajo de la glosa es tender el puente, no
repetir la orilla.

Nullable, y no se rellena aquí: se genera con `scripts/generar_glosas.py`, que
es reanudable. Un programa sin glosa se embebe como hasta ahora.

Revision ID: 078_glosa_de_programa
Revises: 077_indices_busqueda
"""
from alembic import op
import sqlalchemy as sa

revision = '078_glosa_de_programa'
down_revision = '077_indices_busqueda'
branch_labels = None
depends_on = None


def _tiene_columna(nombre: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return nombre in {c["name"] for c in insp.get_columns("programas_investigados")}


def upgrade() -> None:
    if not _tiene_columna("glosa"):
        op.add_column(
            "programas_investigados",
            sa.Column("glosa", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _tiene_columna("glosa"):
        op.drop_column("programas_investigados", "glosa")
