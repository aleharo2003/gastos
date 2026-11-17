"""Compromisos finitos, cuotas mensuales y pagos ligados a gastos."""
from alembic import op
import sqlalchemy as sa
revision='0016'
down_revision='0015'
branch_labels=None
depends_on=None


def secure(table,extra='true'):
    op.execute(f'REVOKE ALL ON public.{table} FROM PUBLIC,anon,authenticated,service_role,app_runtime')
    op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY {table}_migrator ON public.{table} TO app_migrator USING (true) WITH CHECK (true)')
    member=f"""espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT 1 FROM public.miembros_espacio m WHERE m.espacio_id={table}.espacio_id
        AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND m.rol IN ({{roles}}))"""
    read=member.format(roles="'owner','editor','lector'")
    write=member.format(roles="'owner','editor'")
    op.execute(f'CREATE POLICY {table}_read ON public.{table} FOR SELECT TO app_runtime USING ({read})')
    op.execute(f'CREATE POLICY {table}_insert ON public.{table} FOR INSERT TO app_runtime WITH CHECK ({write} AND ({extra}))')
    op.execute(f'GRANT SELECT,INSERT ON public.{table} TO app_runtime')


def upgrade():
    op.create_table('compromisos',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('espacio_id',sa.Uuid(),nullable=False),
        sa.Column('cuenta_id',sa.Uuid(),nullable=False),
        sa.Column('usuario_id',sa.Uuid(),nullable=False),
        sa.Column('nombre',sa.Text(),nullable=False),
        sa.Column('moneda',sa.Text(),nullable=False),
        sa.Column('importe',sa.Numeric(14,2),nullable=False),
        sa.Column('categoria',sa.Text(),nullable=True),
        sa.Column('primer_vencimiento',sa.Date(),nullable=False),
        sa.Column('total_cuotas',sa.Integer(),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_compromisos'),
        sa.UniqueConstraint('espacio_id','id',name='uq_compromisos_espacio_id_id'),
        sa.ForeignKeyConstraint(['espacio_id','cuenta_id'],['public.cuentas.espacio_id','public.cuentas.id'],name='fk_compromisos_espacio_id_cuenta_id_cuentas'),
        sa.ForeignKeyConstraint(['usuario_id'],['public.perfiles.usuario_id'],name='fk_compromisos_usuario_id_perfiles'),
        sa.CheckConstraint("moneda IN ('ARS','USD','EUR')",name='ck_compromisos_moneda'),
        sa.CheckConstraint('importe > 0 AND importe < 1000000000000',name='ck_compromisos_importe'),
        sa.CheckConstraint('char_length(btrim(nombre)) BETWEEN 1 AND 160',name='ck_compromisos_nombre'),
        sa.CheckConstraint('total_cuotas BETWEEN 1 AND 600',name='ck_compromisos_total_cuotas'),
        sa.CheckConstraint("categoria IS NULL OR categoria IN ('alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros')",name='ck_compromisos_categoria'),schema='public')
    op.create_table('cuotas',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('espacio_id',sa.Uuid(),nullable=False),
        sa.Column('compromiso_id',sa.Uuid(),nullable=False),
        sa.Column('numero',sa.Integer(),nullable=False),
        sa.Column('vencimiento',sa.Date(),nullable=False),
        sa.Column('importe',sa.Numeric(14,2),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_cuotas'),
        sa.UniqueConstraint('espacio_id','id',name='uq_cuotas_espacio_id_id'),
        sa.UniqueConstraint('espacio_id','compromiso_id','numero',name='uq_cuotas_compromiso_numero'),
        sa.ForeignKeyConstraint(['espacio_id','compromiso_id'],['public.compromisos.espacio_id','public.compromisos.id'],name='fk_cuotas_espacio_id_compromiso_id_compromisos'),
        sa.CheckConstraint('numero BETWEEN 1 AND 600',name='ck_cuotas_numero'),
        sa.CheckConstraint('importe > 0 AND importe < 1000000000000',name='ck_cuotas_importe'),schema='public')
    op.create_index('ix_cuotas_espacio_vencimiento','cuotas',['espacio_id','vencimiento'],schema='public')
    op.create_table('pagos_cuota',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('espacio_id',sa.Uuid(),nullable=False),
        sa.Column('cuota_id',sa.Uuid(),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_pagos_cuota'),
        sa.ForeignKeyConstraint(['espacio_id','id'],['public.gastos.espacio_id','public.gastos.id'],name='fk_pagos_cuota_espacio_id_id_gastos'),
        sa.ForeignKeyConstraint(['espacio_id','cuota_id'],['public.cuotas.espacio_id','public.cuotas.id'],name='fk_pagos_cuota_espacio_id_cuota_id_cuotas'),schema='public')
    op.create_index('ix_pagos_cuota_espacio_cuota','pagos_cuota',['espacio_id','cuota_id'],schema='public')
    secure('compromisos',"usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid")
    secure('cuotas')
    secure('pagos_cuota',"""EXISTS (SELECT 1 FROM public.gastos g WHERE g.espacio_id=pagos_cuota.espacio_id
        AND g.id=pagos_cuota.id AND g.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    # Impide alterar un pago indirectamente desde la edicion general de gastos.
    protected="""NOT EXISTS (SELECT 1 FROM public.pagos_cuota p
        WHERE p.espacio_id=gastos.espacio_id AND p.id=gastos.id)"""
    op.execute(f'CREATE POLICY gastos_pago_inmutable ON public.gastos AS RESTRICTIVE FOR UPDATE TO app_runtime USING ({protected}) WITH CHECK ({protected})')


def downgrade():
    op.execute('DROP POLICY gastos_pago_inmutable ON public.gastos')
    op.drop_table('pagos_cuota',schema='public')
    op.drop_table('cuotas',schema='public')
    op.drop_table('compromisos',schema='public')
