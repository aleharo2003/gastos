"""Marca las cuotas confirmadas vencidas desde el proceso diario."""
import sys

from generate_month import run_jobs_count


def main():
    try:
        count = run_jobs_count('SELECT public.marcar_cuotas_vencidas()')
    except Exception:
        # Evitar que errores de conexión o SQL muestren credenciales.
        print('ERROR: no se confirmó el marcado de cuotas vencidas.', file=sys.stderr)
        return 1
    print(f'OK: cuotas marcadas como vencidas={count}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
