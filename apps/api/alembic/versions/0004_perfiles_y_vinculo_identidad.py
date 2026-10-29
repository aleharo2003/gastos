"""Perfiles privados y membresias vinculadas a un perfil existente."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No inventar identidades/perfiles ni borrar membresías existentes.
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM public.miembros_espacio)')).scalar_one():
        raise RuntimeError('Hay membresias previas: preparar un backfill de identidad revisado antes de aplicar 0004. No se borraron datos.')
    op.create_table(
        'perfiles',
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('usuario_id', name='pk_perfiles'),
        schema='public',
    )
    op.execute('REVOKE ALL ON TABLE public.perfiles FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('ALTER TABLE public.perfiles ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.perfiles FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY perfiles_migrator ON public.perfiles FOR ALL TO app_migrator USING (true) WITH CHECK (true)')
    op.execute("""CREATE POLICY perfiles_lectura_propia ON public.perfiles
                  FOR SELECT TO app_runtime
                  USING (usuario_id = nullif(current_setting('app.user_id', true), '')::uuid)""")
    op.execute('GRANT SELECT ON TABLE public.perfiles TO app_runtime')
    op.create_foreign_key('fk_miembros_espacio_usuario_id_perfiles', 'miembros_espacio', 'perfiles',
                          ['usuario_id'], ['usuario_id'], source_schema='public', referent_schema='public')


def downgrade() -> None:
    op.drop_constraint('fk_miembros_espacio_usuario_id_perfiles', 'miembros_espacio', schema='public', type_='foreignkey')
    op.drop_table('perfiles', schema='public')
