"""El CV gana destino, apariencia y foto (2026-08-10).

Revision ID: 063_cv_variantes_y_foto
Revises: 062_confianza_del_programa
Create Date: 2026-08-10

Hasta ahora la hoja de vida era **una sola**: un PDF A4, un diseño, sin foto.
Esta migración le da al estudiante tres decisiones que antes no existían:

  * `estandar`  · a dónde va el documento (Estados Unidos · Europa · LatAm).
    Decide el CONTENIDO — si va foto, cuántas páginas, en qué orden salen las
    secciones. Ver `app/services/cv_variants.py`.
  * `estilo`    · cómo se ve. Sólo CSS.
  * `incluir_foto` · si quiere que salga. Ojo: el estándar tiene la última
    palabra, y `us` no la imprime nunca aunque esto esté en `true`.

`users.photo_url` guarda la **ruta relativa** dentro del bucket, no una URL
firmada. Es el patrón de `school_panel.py` y no el de `programs.py`, que
persiste una URL que caduca a las 24 horas y deja imágenes rotas.

Las tres columnas de `share_*` preparan el enlace público, que nace **apagado**:
son menores de edad y encenderlo no es una decisión de ingeniería. Existen aquí
para no tener que migrar el día que la clienta lo autorice.

Todas nullable y con comprobación previa, como el resto de las `05*`.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '063_cv_variantes_y_foto'
down_revision = '062_confianza_del_programa'
branch_labels = None
depends_on = None


def _columnas(bind, tabla: str) -> set:
    """Nombres de columna existentes · vacío si la tabla no está."""
    try:
        inspector = inspect(bind)
        if not inspector.has_table(tabla):
            return set()
        return {c['name'] for c in inspector.get_columns(tabla)}
    except Exception:
        return set()


# (tabla, columna, tipo) · el orden importa sólo para leerlo.
_NUEVAS = [
    ('users', 'photo_url', sa.String(500)),
    ('cv_profiles', 'estandar', sa.String(20)),
    ('cv_profiles', 'estilo', sa.String(20)),
    ('cv_profiles', 'incluir_foto', sa.Boolean()),
    ('cv_profiles', 'share_token', sa.String(64)),
    ('cv_profiles', 'share_habilitado', sa.Boolean()),
    ('cv_profiles', 'share_creado_en', sa.DateTime()),
]


def upgrade() -> None:
    bind = op.get_bind()
    cache = {}

    for tabla, columna, tipo in _NUEVAS:
        if tabla not in cache:
            cache[tabla] = _columnas(bind, tabla)
        if not cache[tabla]:
            # La tabla no existe en esta base (pasa en la rama local, que va
            # atrasada respecto a producción). No es un error: la migración que
            # la crea ya trae las columnas desde el modelo.
            continue
        if columna in cache[tabla]:
            continue
        op.add_column(tabla, sa.Column(columna, tipo, nullable=True))
        cache[tabla].add(columna)

    # El token se busca por igualdad en cada visita al enlace público; sin
    # índice sería un scan de la tabla entera por request anónimo.
    if 'share_token' in cache.get('cv_profiles', set()):
        try:
            op.create_index(
                'ix_cv_profiles_share_token', 'cv_profiles', ['share_token'],
                unique=True,
            )
        except Exception:
            # Ya existía · la migración se corrió antes.
            pass


def downgrade() -> None:
    bind = op.get_bind()

    try:
        op.drop_index('ix_cv_profiles_share_token', table_name='cv_profiles')
    except Exception:
        pass

    for tabla, columna, _ in reversed(_NUEVAS):
        if columna in _columnas(bind, tabla):
            op.drop_column(tabla, columna)
