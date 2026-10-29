"""Estructura minima de cuentas y permisos por espacio y rol."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'cuentas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_cuentas'),
        sa.UniqueConstraint('espacio_id', 'id', name='uq_cuentas_espacio_id_id'),
        sa.ForeignKeyConstraint(['espacio_id'], ['public.espacios.id'], name='fk_cuentas_espacio_id_espacios'),
        schema='public',
    )
    op.execute('REVOKE ALL ON TABLE public.cuentas FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('ALTER TABLE public.cuentas ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.cuentas FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY cuentas_migrator ON public.cuentas FOR ALL TO app_migrator USING (true) WITH CHECK (true)')
    selected_member = """
        espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM public.miembros_espacio AS miembro
            WHERE miembro.espacio_id = cuentas.espacio_id
              AND miembro.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
              AND miembro.rol IN ({roles})
        )
    """
    reader = selected_member.format(roles="'lector', 'editor', 'owner'")
    writer = selected_member.format(roles="'editor', 'owner'")
    # Expresiones fijas de esta revisión, no valores recibidos por la aplicación.
    op.execute(f'CREATE POLICY cuentas_lectura ON public.cuentas FOR SELECT TO app_runtime USING ({reader})')
    op.execute(f'CREATE POLICY cuentas_insercion ON public.cuentas FOR INSERT TO app_runtime WITH CHECK ({writer})')
    op.execute(f'CREATE POLICY cuentas_actualizacion ON public.cuentas FOR UPDATE TO app_runtime USING ({writer}) WITH CHECK ({writer})')
    op.execute(f'CREATE POLICY cuentas_eliminacion ON public.cuentas FOR DELETE TO app_runtime USING ({writer})')
    op.execute('GRANT SELECT, INSERT, DELETE ON TABLE public.cuentas TO app_runtime')
    # Identidad y espacio no se editan: una cuenta no se traslada entre espacios.
    op.execute('GRANT UPDATE (nombre) ON TABLE public.cuentas TO app_runtime')


def downgrade() -> None:
    op.drop_table('cuentas', schema='public')
