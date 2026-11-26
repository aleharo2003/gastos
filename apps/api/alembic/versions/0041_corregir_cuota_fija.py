"""Permitir corregir el importe de una cuota fija antes de pagarla."""
from alembic import op

revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None

TRIGGER_FUNCTION = """CREATE OR REPLACE FUNCTION public.validar_cambio_cuota() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
    BEGIN
        IF current_user='app_runtime' AND (
            NEW.version<>OLD.version+1 OR
            (NEW.no_aplica AND NEW.importe<>OLD.importe) OR
            (NOT NEW.no_aplica AND NOT OLD.estimado {allow_fixed})
        ) THEN
            RETURN NULL;
        END IF;
        RETURN NEW;
    END
    $fn$"""


def upgrade():
    op.execute(TRIGGER_FUNCTION.format(allow_fixed="""AND NOT (
        NOT NEW.estimado AND NOT OLD.pendiente_ajuste AND OLD.capital IS NULL
        AND EXISTS (
            SELECT 1 FROM public.compromisos c
            WHERE c.espacio_id=OLD.espacio_id AND c.id=OLD.compromiso_id
              AND NOT c.variable AND c.indice_ajuste IS NULL AND c.sistema_amortizacion IS NULL
        )
    )"""))


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (
            SELECT 1 FROM public.cuotas q
            JOIN public.compromisos c ON c.espacio_id=q.espacio_id AND c.id=q.compromiso_id
            WHERE NOT q.no_aplica AND NOT c.variable AND c.indice_ajuste IS NULL
              AND c.sistema_amortizacion IS NULL AND q.importe<>c.importe
        ) THEN
            RAISE EXCEPTION 'Hay cuotas fijas con importe corregido; revisar sus importes antes de volver.';
        END IF;
    END $check$""")
    op.execute(TRIGGER_FUNCTION.format(allow_fixed=''))
