"""Alta atomica del perfil, espacio personal y owner para la identidad actual."""
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION public.crear_espacio_personal() RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
    AS $body$
    DECLARE
        usuario uuid := nullif(current_setting('app.user_id', true), '')::uuid;
    BEGIN
        IF usuario IS NULL OR usuario = '00000000-0000-0000-0000-000000000000'::uuid THEN
            RAISE EXCEPTION 'Identidad requerida' USING ERRCODE = '42501';
        END IF;
        -- Una identidad, un espacio personal. El ID es estable ante reintentos.
        -- El bloqueo dura la transaccion y serializa altas concurrentes del usuario.
        PERFORM pg_advisory_xact_lock(hashtextextended('alta-personal:' || usuario::text, 0));
        IF EXISTS (SELECT 1 FROM public.espacios WHERE id = usuario) THEN
            IF NOT EXISTS (
                SELECT 1 FROM public.miembros_espacio
                WHERE usuario_id = usuario AND espacio_id = usuario AND rol = 'owner'
            ) THEN
                -- No restaurar membresias revocadas ni apropiarse de un espacio.
                RAISE EXCEPTION 'Alta requiere revision' USING ERRCODE = '42501';
            END IF;
            RETURN usuario;
        END IF;
        INSERT INTO public.perfiles(usuario_id, nombre)
        VALUES (usuario, 'Mi perfil') ON CONFLICT (usuario_id) DO NOTHING;
        INSERT INTO public.espacios(id, nombre) VALUES (usuario, 'Mi espacio');
        INSERT INTO public.miembros_espacio(usuario_id, espacio_id, rol)
        VALUES (usuario, usuario, 'owner');
        RETURN usuario;
    END
    $body$;
    """)
    op.execute('REVOKE ALL ON FUNCTION public.crear_espacio_personal() FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('GRANT EXECUTE ON FUNCTION public.crear_espacio_personal() TO app_runtime')


def downgrade():
    op.execute('DROP FUNCTION public.crear_espacio_personal()')
