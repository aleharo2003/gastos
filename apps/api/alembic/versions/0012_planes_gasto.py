"""Límites globales y presupuesto proyectado, compartidos por espacio."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision='0012'
down_revision='0011'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('planes_gasto',
        sa.Column('espacio_id',sa.Uuid(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('datos',postgresql.JSONB(),nullable=False),
        sa.PrimaryKeyConstraint('espacio_id',name='pk_planes_gasto'),
        sa.ForeignKeyConstraint(['espacio_id'],['public.espacios.id'],name='fk_planes_gasto_espacio_id_espacios'),
        sa.CheckConstraint('version >= 0',name='ck_planes_gasto_version'),
        sa.CheckConstraint("jsonb_typeof(datos) = 'object' AND octet_length(datos::text) <= 32768",name='ck_planes_gasto_datos'),schema='public')
    op.execute('ALTER TABLE public.planes_gasto ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.planes_gasto FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY planes_migrator ON public.planes_gasto TO app_migrator USING (true) WITH CHECK (true)')
    member="""espacio_id = NULLIF(current_setting('app.workspace_id',true),'')::uuid
      AND EXISTS (SELECT 1 FROM public.miembros_espacio m WHERE m.espacio_id=planes_gasto.espacio_id
      AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid {role})"""
    read=member.format(role='')
    write=member.format(role="AND m.rol IN ('owner','editor')")
    op.execute(f'CREATE POLICY planes_read ON public.planes_gasto FOR SELECT TO app_runtime USING ({read})')
    op.execute(f'CREATE POLICY planes_insert ON public.planes_gasto FOR INSERT TO app_runtime WITH CHECK ({write})')
    op.execute(f'CREATE POLICY planes_update ON public.planes_gasto FOR UPDATE TO app_runtime USING ({write}) WITH CHECK ({write})')
    op.execute('REVOKE ALL ON public.planes_gasto FROM PUBLIC, anon, authenticated, service_role')
    op.execute('GRANT SELECT,INSERT ON public.planes_gasto TO app_runtime')
    op.execute('GRANT UPDATE (version,datos) ON public.planes_gasto TO app_runtime')

def downgrade():
    op.drop_table('planes_gasto',schema='public')
