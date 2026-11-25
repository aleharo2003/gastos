"""Categorías personalizadas y preferencias de catálogo por espacio."""
from alembic import op
import sqlalchemy as sa

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None

EXPENSE_KEYS = "'alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros'"
CUSTOM_KEY = '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'


def upgrade() -> None:
    op.create_table(
        'categorias_movimientos',
        sa.Column('espacio_id', sa.Uuid(), sa.ForeignKey('public.espacios.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tipo', sa.Text(), primary_key=True),
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('color', sa.Text()),
        sa.Column('activa', sa.Boolean(), nullable=False),
        sa.CheckConstraint("tipo IN ('gasto','ingreso')", name='ck_categorias_tipo'),
        sa.CheckConstraint('char_length(btrim(nombre)) BETWEEN 1 AND 80', name='ck_categorias_nombre'),
        sa.CheckConstraint("color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name='ck_categorias_color'),
        schema='public',
    )
    op.execute('REVOKE ALL ON public.categorias_movimientos FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('ALTER TABLE public.categorias_movimientos ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.categorias_movimientos FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY categorias_migrator ON public.categorias_movimientos FOR ALL TO app_migrator USING (true) WITH CHECK (true)')
    membership = """
        espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id = categorias_movimientos.espacio_id
              AND m.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
              AND m.rol IN ({roles})
        )
    """
    read = membership.format(roles="'owner','editor','lector'")
    write = membership.format(roles="'owner','editor'")
    op.execute(f'CREATE POLICY categorias_lectura ON public.categorias_movimientos FOR SELECT TO app_runtime USING ({read})')
    op.execute(f'CREATE POLICY categorias_insercion ON public.categorias_movimientos FOR INSERT TO app_runtime WITH CHECK ({write})')
    op.execute(f'CREATE POLICY categorias_edicion ON public.categorias_movimientos FOR UPDATE TO app_runtime USING ({write}) WITH CHECK ({write})')
    op.execute('GRANT SELECT, INSERT, UPDATE (nombre, color, activa) ON public.categorias_movimientos TO app_runtime')
    op.drop_constraint('ck_gastos_categoria', 'gastos', type_='check', schema='public')
    op.create_check_constraint('ck_gastos_categoria', 'gastos',
                               f"categoria IS NULL OR categoria IN ({EXPENSE_KEYS}) OR categoria ~ '{CUSTOM_KEY}'", schema='public')


def downgrade() -> None:
    op.drop_constraint('ck_gastos_categoria', 'gastos', type_='check', schema='public')
    op.create_check_constraint('ck_gastos_categoria', 'gastos',
                               f'categoria IS NULL OR categoria IN ({EXPENSE_KEYS})', schema='public')
    op.drop_table('categorias_movimientos', schema='public')
