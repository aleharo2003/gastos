"""Crea membresias; runtime permanece sin acceso hasta incorporar sus policies."""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "miembros_espacio",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("espacio_id", sa.Uuid(), nullable=False),
        sa.Column("rol", sa.Text(), nullable=False),
        sa.CheckConstraint("rol IN ('owner', 'editor', 'lector')",
                           name="ck_miembros_espacio_rol"),
        sa.ForeignKeyConstraint(["espacio_id"], ["public.espacios.id"],
                                name="fk_miembros_espacio_espacio_id_espacios"),
        sa.PrimaryKeyConstraint("usuario_id", "espacio_id",
                                name="pk_miembros_espacio"),
        schema="public",
    )
    op.create_index("ix_miembros_espacio_espacio_id", "miembros_espacio",
                    ["espacio_id"], schema="public")
    # Autogenerate no reemplaza la escritura y revisión explícita de RLS/grants.
    op.execute("REVOKE ALL ON TABLE public.miembros_espacio FROM PUBLIC, anon, authenticated, service_role, app_runtime")
    op.execute("ALTER TABLE public.miembros_espacio ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.miembros_espacio FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY miembros_espacio_migrator
        ON public.miembros_espacio FOR ALL TO app_migrator
        USING (true) WITH CHECK (true)
    """)


def downgrade() -> None:
    # DROP TABLE también elimina su índice, constraints y policy.
    op.drop_table("miembros_espacio", schema="public")
