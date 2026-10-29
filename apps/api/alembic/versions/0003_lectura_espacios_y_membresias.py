"""Permite a runtime leer sus membresias y espacios, sin administrar acceso."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("REVOKE ALL ON TABLE public.espacios, public.miembros_espacio FROM PUBLIC, anon, authenticated, service_role, app_runtime")
    op.execute("ALTER TABLE public.espacios ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.espacios FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY espacios_migrator ON public.espacios
        FOR ALL TO app_migrator USING (true) WITH CHECK (true)
    """)
    # Comparación directa: no consultar miembros_espacio desde su propia policy.
    op.execute("""
        CREATE POLICY miembros_espacio_lectura_propia ON public.miembros_espacio
        FOR SELECT TO app_runtime
        USING (usuario_id = nullif(current_setting('app.user_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE POLICY espacios_lectura_miembro ON public.espacios
        FOR SELECT TO app_runtime
        USING (EXISTS (
            SELECT 1 FROM public.miembros_espacio AS miembro
            WHERE miembro.espacio_id = espacios.id
              AND miembro.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
        ))
    """)
    op.execute("GRANT SELECT ON TABLE public.espacios, public.miembros_espacio TO app_runtime")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON TABLE public.espacios, public.miembros_espacio FROM app_runtime")
    op.execute("DROP POLICY espacios_lectura_miembro ON public.espacios")
    op.execute("DROP POLICY miembros_espacio_lectura_propia ON public.miembros_espacio")
    op.execute("DROP POLICY espacios_migrator ON public.espacios")
    op.execute("ALTER TABLE public.espacios NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.espacios DISABLE ROW LEVEL SECURITY")
    # No restaurar grants anteriores de Data API/PUBLIC: conservar acceso cerrado.
