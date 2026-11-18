"""Limita el ejecutor de prueba de recordatorios a una sola membresía."""
from alembic import op
import sqlalchemy as sa

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


FUNCTIONS = {
    'comprobar_piloto_avisos_email(uuid,uuid)': """
        CREATE FUNCTION public.comprobar_piloto_avisos_email(usuario uuid, espacio uuid)
        RETURNS void LANGUAGE plpgsql STABLE SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM public.piloto_avisos_email
                WHERE usuario_id = usuario AND espacio_id = espacio
            ) THEN
                RAISE EXCEPTION 'Membresía no habilitada para el piloto' USING ERRCODE = '42501';
            END IF;
        END
        $fn$
    """,
    'previsualizar_avisos_email_piloto(uuid,uuid,timestamptz)': """
        CREATE FUNCTION public.previsualizar_avisos_email_piloto(usuario uuid, espacio uuid, instante timestamptz)
        RETURNS bigint LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $fn$
        BEGIN
            PERFORM public.comprobar_piloto_avisos_email(usuario, espacio);
            RETURN (SELECT count(*) FROM public.candidatos_avisos_email(instante) c
                    WHERE c.usuario_id = usuario AND c.espacio_id = espacio);
        END
        $fn$
    """,
    'encolar_avisos_email_piloto(uuid,uuid,timestamptz)': """
        CREATE FUNCTION public.encolar_avisos_email_piloto(usuario uuid, espacio uuid, instante timestamptz)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $fn$
        BEGIN
            PERFORM public.comprobar_piloto_avisos_email(usuario, espacio);
            INSERT INTO public.avisos_email (usuario_id, espacio_id, cuota_id, evento, fecha_aviso)
            SELECT c.usuario_id, c.espacio_id, c.cuota_id, c.evento, c.fecha_aviso
            FROM public.candidatos_avisos_email(instante) c
            WHERE c.usuario_id = usuario AND c.espacio_id = espacio
            ORDER BY c.cuota_id, c.evento, c.fecha_aviso
            ON CONFLICT DO NOTHING;
        END
        $fn$
    """,
    'preparar_avisos_email_piloto(uuid,uuid,timestamptz)': """
        CREATE FUNCTION public.preparar_avisos_email_piloto(usuario uuid, espacio uuid, instante timestamptz)
        RETURNS TABLE (
            usuario_id uuid, espacio_id uuid, cuota_id uuid, fecha_aviso date,
            evento text, vencimiento date, nombre text, numero integer, moneda text,
            pendiente numeric, estimado boolean, pendiente_ajuste boolean
        ) LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $fn$
        BEGIN
            PERFORM public.comprobar_piloto_avisos_email(usuario, espacio);
            RETURN QUERY SELECT c.* FROM public.avisos_email_para_preparar(instante) c
            WHERE c.usuario_id = usuario AND c.espacio_id = espacio;
        END
        $fn$
    """,
    'reservar_entrega_aviso_email_piloto(uuid,uuid,timestamptz)': """
        CREATE FUNCTION public.reservar_entrega_aviso_email_piloto(usuario uuid, espacio uuid, instante timestamptz)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $fn$
        BEGIN
            PERFORM public.comprobar_piloto_avisos_email(usuario, espacio);
            RETURN public.reservar_entrega_aviso_email(usuario, espacio, instante);
        END
        $fn$
    """,
    'resolver_entrega_aviso_email_piloto(uuid,text,text)': """
        CREATE FUNCTION public.resolver_entrega_aviso_email_piloto(intento uuid, resultado text, referencia text)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM public.entregas_avisos_email e
                JOIN public.piloto_avisos_email p USING (usuario_id, espacio_id)
                WHERE e.intento_id = intento
            ) THEN RETURN false; END IF;
            RETURN public.resolver_entrega_aviso_email(intento, resultado, referencia);
        END
        $fn$
    """,
}


def upgrade():
    op.create_table(
        'piloto_avisos_email',
        sa.Column('id', sa.SmallInteger(), nullable=False, autoincrement=False),
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_piloto_avisos_email'),
        sa.CheckConstraint('id = 1', name='ck_piloto_avisos_email_unico'),
        sa.ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_piloto_avisos_email_miembro', ondelete='CASCADE',
        ),
        schema='public',
    )
    table = 'public.piloto_avisos_email'
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY piloto_avisos_email_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    for signature, definition in FUNCTIONS.items():
        op.execute(definition)
        op.execute(f'REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role, app_runtime')


def downgrade():
    for signature in reversed(FUNCTIONS):
        op.execute(f'DROP FUNCTION public.{signature}')
    op.drop_table('piloto_avisos_email', schema='public')
