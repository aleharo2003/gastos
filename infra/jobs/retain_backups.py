"""Conservar ocho semanas de copias de este workflow."""
from datetime import date
import json
import os
import re
import subprocess
import sys

NAME = re.compile(r'piggo-postgres-(\d{4})-W(\d{2})-r\d+')


def deletion_ids(artifacts, current_id: int, keep: int = 8) -> list[int]:
    eligible = []
    for row in artifacts:
        match = NAME.fullmatch(row['name'])
        if match and not row['expired']:
            monday = date.fromisocalendar(int(match[1]), int(match[2]), 1)
            eligible.append((monday, row['id']))
    if not any(identifier == current_id for _, identifier in eligible):
        raise ValueError('No se confirmó el nuevo archivo. Se conserva lo existente.')
    weeks = set()
    delete = []
    for week, identifier in sorted(eligible, reverse=True):
        if week in weeks or len(weeks) >= keep:
            delete.append(identifier)
        else:
            weeks.add(week)
    return delete


def api(route, *flags):
    return subprocess.check_output(['gh', 'api', *flags, route], text=True)


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Repositorio inválido')
    current_id = int(sys.argv[1])
    run = int(os.environ['GITHUB_RUN_ID'])
    root = f'/repos/{repo}/actions'
    route = root + '/workflows/weekly-backup.yml/runs?branch=main&per_page=100'
    runs = [row['id'] for page in json.loads(api(route, '--paginate', '--slurp')) for row in page['workflow_runs']]
    if run not in runs:
        raise ValueError('La ejecución no corresponde al workflow de resguardo')
    artifacts = [
        row for identifier in runs
        for page in json.loads(api(f'{root}/runs/{identifier}/artifacts?per_page=100', '--paginate', '--slurp'))
        for row in page['artifacts']
    ]
    for identifier in deletion_ids(artifacts, current_id):
        api(f'{root}/artifacts/{identifier}', '--method', 'DELETE')


if __name__ == '__main__':
    main()
