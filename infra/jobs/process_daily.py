"""Ejecuta las tareas diarias de Piggo sin depender de los servicios web."""
import argparse
import os
from pathlib import Path

from generate_month import generate
from mark_overdue import mark_overdue
from refresh_usd_reference import refresh


def run_tasks(tasks, summary_path=None):
    results = []
    for label, task in tasks:
        try:
            count = task()
            result = f'OK ({count})'
            print(f'{label}: {result}', flush=True)
        except Exception:
            # Las excepciones de PostgreSQL y HTTP pueden contener credenciales.
            result = 'Falló'
            print(f'::error::{label}: {result}. Revisá la configuración o reintentá la tarea.', flush=True)
        results.append((label, result))
    if summary_path:
        with Path(summary_path).open('a', encoding='utf-8') as summary:
            summary.write('## Proceso diario de Piggo\n\n')
            summary.writelines(f'- {label}: {result}\n' for label, result in results)
    return int(any(result == 'Falló' for _, result in results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('todo', 'cuotas', 'vencimientos', 'cotizaciones'))
    args = parser.parse_args()
    tasks = {
        'cuotas': ('Generar cuotas del mes', generate),
        'vencimientos': ('Marcar cuotas vencidas', mark_overdue),
        'cotizaciones': ('Actualizar cotizaciones USD', refresh),
    }
    selected = tasks.values() if args.mode == 'todo' else (tasks[args.mode],)
    return run_tasks(selected, os.environ.get('GITHUB_STEP_SUMMARY'))


if __name__ == '__main__':
    raise SystemExit(main())
