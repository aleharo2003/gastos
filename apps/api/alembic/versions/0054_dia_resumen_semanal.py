"""Día elegido para el resumen semanal del piloto."""
from alembic import op
import sqlalchemy as sa

revision = '0054'
down_revision = '0053'
branch_labels = None
depends_on = None


def set_reservation(*, check_weekday):
    weekday = 'AND p.dia_resumen_semanal=EXTRACT(ISODOW FROM ahora)' if check_weekday else ''
    op.execute(f"""
        CREATE OR REPLACE FUNCTION public.reservar_resumen_semanal_piloto(usuario uuid, espacio uuid, instante timestamptz, intento uuid)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        DECLARE
            ahora timestamp := instante AT TIME ZONE 'America/Argentina/Buenos_Aires';
        BEGIN
            PERFORM public.comprobar_piloto_avisos_email(usuario, espacio);
            IF NOT EXISTS (
                SELECT FROM public.preferencias_avisos p
                WHERE p.usuario_id=usuario AND p.espacio_id=espacio
                    AND p.canal='email' AND p.resumen_semanal AND p.hora_local<=ahora::time {weekday}
            ) THEN RETURN false; END IF;

            INSERT INTO public.envios_resumen_semanal AS e(usuario_id,espacio_id,semana,intento_id,estado)
            VALUES (usuario,espacio,date_trunc('week',ahora)::date-7,intento,'reservado')
            ON CONFLICT (usuario_id,espacio_id,semana) DO UPDATE
            SET intento_id=EXCLUDED.intento_id, estado='reservado'
            WHERE e.estado='reintento';
            RETURN FOUND;
        END
        $fn$;
    """)


def upgrade():
    op.add_column('preferencias_avisos', sa.Column('dia_resumen_semanal', sa.SmallInteger(), nullable=False,
                                                  server_default='1'), schema='public')
    op.create_check_constraint('ck_preferencias_avisos_dia_resumen', 'preferencias_avisos',
                               'dia_resumen_semanal BETWEEN 1 AND 7', schema='public')
    op.execute('GRANT UPDATE (dia_resumen_semanal) ON public.preferencias_avisos TO app_runtime')
    set_reservation(check_weekday=True)


def downgrade():
    set_reservation(check_weekday=False)
    op.drop_constraint('ck_preferencias_avisos_dia_resumen', 'preferencias_avisos', type_='check', schema='public')
    op.drop_column('preferencias_avisos', 'dia_resumen_semanal', schema='public')
