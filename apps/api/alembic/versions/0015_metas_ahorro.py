"""Metas vinculadas al saldo de una cuenta y moneda, sin duplicar dinero."""
from alembic import op
import sqlalchemy as sa
revision='0015'
down_revision='0014'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('metas_ahorro',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('espacio_id',sa.Uuid(),nullable=False),
        sa.Column('cuenta_id',sa.Uuid(),nullable=False),
        sa.Column('usuario_id',sa.Uuid(),nullable=False),
        sa.Column('nombre',sa.Text(),nullable=False),
        sa.Column('moneda',sa.Text(),nullable=False),
        sa.Column('objetivo',sa.Numeric(14,2),nullable=False),
        sa.Column('fecha_objetivo',sa.Date(),nullable=True),
        sa.Column('archivada',sa.Boolean(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_metas_ahorro'),
        sa.ForeignKeyConstraint(['espacio_id','cuenta_id'],['public.cuentas.espacio_id','public.cuentas.id'],name='fk_metas_ahorro_espacio_id_cuenta_id_cuentas'),
        sa.ForeignKeyConstraint(['usuario_id'],['public.perfiles.usuario_id'],name='fk_metas_ahorro_usuario_id_perfiles'),
        sa.CheckConstraint("moneda IN ('ARS','USD','EUR')",name='ck_metas_ahorro_moneda'),
        sa.CheckConstraint('objetivo > 0 AND objetivo < 1000000000000',name='ck_metas_ahorro_objetivo'),
        sa.CheckConstraint('char_length(btrim(nombre)) BETWEEN 1 AND 160',name='ck_metas_ahorro_nombre'),
        sa.CheckConstraint('version >= 0',name='ck_metas_ahorro_version'),schema='public')
    op.create_index('uq_metas_ahorro_activa','metas_ahorro',['espacio_id','cuenta_id','moneda'],unique=True,postgresql_where=sa.text('NOT archivada'),schema='public')
    op.execute('REVOKE ALL ON public.metas_ahorro FROM PUBLIC,anon,authenticated,service_role,app_runtime')
    op.execute('ALTER TABLE public.metas_ahorro ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.metas_ahorro FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY metas_migrator ON public.metas_ahorro TO app_migrator USING (true) WITH CHECK (true)')
    member="""espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT 1 FROM public.miembros_espacio m WHERE m.espacio_id=metas_ahorro.espacio_id
        AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND m.rol IN ({roles}))"""
    read=member.format(roles="'owner','editor','lector'")
    write=member.format(roles="'owner','editor'")
    op.execute(f'CREATE POLICY metas_read ON public.metas_ahorro FOR SELECT TO app_runtime USING ({read})')
    op.execute(f"""CREATE POLICY metas_insert ON public.metas_ahorro FOR INSERT TO app_runtime
        WITH CHECK ({write} AND usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    op.execute(f'CREATE POLICY metas_update ON public.metas_ahorro FOR UPDATE TO app_runtime USING ({write}) WITH CHECK ({write})')
    op.execute('GRANT SELECT,INSERT ON public.metas_ahorro TO app_runtime')
    op.execute('GRANT UPDATE (nombre,objetivo,fecha_objetivo,archivada,version) ON public.metas_ahorro TO app_runtime')


def downgrade():
    op.drop_table('metas_ahorro',schema='public')
