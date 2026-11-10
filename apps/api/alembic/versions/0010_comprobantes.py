"""Metadatos de comprobantes privados; objetos gestionados por Storage API."""
from alembic import op
import sqlalchemy as sa
revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None


def upgrade():
    op.create_unique_constraint('uq_gastos_espacio_id_id','gastos',['espacio_id','id'],schema='public')
    op.create_table('comprobantes',
        sa.Column('id',sa.Uuid(),nullable=False),sa.Column('espacio_id',sa.Uuid(),nullable=False),
        sa.Column('gasto_id',sa.Uuid(),nullable=False),sa.Column('nombre',sa.Text(),nullable=False),
        sa.Column('mime',sa.Text(),nullable=False),sa.Column('bytes',sa.Integer(),nullable=False),
        sa.Column('sha256',sa.Text(),nullable=False),sa.Column('ruta',sa.Text(),nullable=False),
        sa.PrimaryKeyConstraint('id',name='pk_comprobantes'),
        sa.ForeignKeyConstraint(['espacio_id','gasto_id'],['public.gastos.espacio_id','public.gastos.id'],name='fk_comprobantes_espacio_id_gasto_id_gastos'),
        sa.CheckConstraint('bytes > 0 AND bytes <= 5242880',name='ck_comprobantes_bytes'),
        sa.CheckConstraint("mime IN ('image/jpeg','image/png','application/pdf')",name='ck_comprobantes_mime'),schema='public')
    op.create_index('ix_comprobantes_espacio_gasto','comprobantes',['espacio_id','gasto_id'],schema='public')
    op.execute('REVOKE ALL ON public.comprobantes FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('ALTER TABLE public.comprobantes ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.comprobantes FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY comprobantes_migrator ON public.comprobantes FOR ALL TO app_migrator USING (true) WITH CHECK (true)')
    membership="""espacio_id = nullif(current_setting('app.workspace_id',true),'')::uuid
      AND EXISTS (SELECT 1 FROM public.miembros_espacio m WHERE m.espacio_id=comprobantes.espacio_id
      AND m.usuario_id=nullif(current_setting('app.user_id',true),'')::uuid AND m.rol IN ({roles}))"""
    read=membership.format(roles="'owner','editor','lector'")
    write=membership.format(roles="'owner','editor'")
    op.execute(f'CREATE POLICY comprobantes_lectura ON public.comprobantes FOR SELECT TO app_runtime USING ({read})')
    op.execute(f'CREATE POLICY comprobantes_alta ON public.comprobantes FOR INSERT TO app_runtime WITH CHECK ({write})')
    op.execute('GRANT SELECT, INSERT ON public.comprobantes TO app_runtime')


def downgrade():
    op.drop_table('comprobantes',schema='public')
    op.drop_constraint('uq_gastos_espacio_id_id','gastos',schema='public',type_='unique')
