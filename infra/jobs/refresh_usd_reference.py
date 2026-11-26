"""Descarga diaria del precio vendedor publicado por DolarApi."""
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
import os
import sys
from urllib.request import urlopen

import psycopg
from psycopg.types.json import Jsonb

from generate_month import verify_jobs_role

URL = 'https://dolarapi.com/v1/dolares'
TYPES = {'oficial', 'blue', 'bolsa', 'contadoconliqui', 'mayorista', 'cripto', 'tarjeta'}


def normalize(payload):
    if not isinstance(payload, list):
        raise ValueError('Formato de cotizaciones inválido')
    result = {}
    for row in payload:
        if not isinstance(row, dict) or row.get('casa') not in TYPES or row.get('moneda') != 'USD':
            continue
        try:
            value = Decimal(str(row['venta'])).quantize(Decimal('0.0001'))
            updated = datetime.fromisoformat(row['fechaActualizacion'])
            if not Decimal('0') < value < Decimal('100000000') or updated.tzinfo is None or updated > datetime.now(UTC):
                continue
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        previous = result.get(row['casa'])
        if previous is None or updated > datetime.fromisoformat(previous['actualizada_en']):
            result[row['casa']] = {'tipo': row['casa'], 'tasa': str(value), 'actualizada_en': updated.isoformat()}
    if not result:
        raise ValueError('La fuente no devolvió cotizaciones utilizables')
    return list(result.values())


def refresh():
    dsn = os.environ.get('JOBS_DATABASE_URL')
    if not dsn:
        raise RuntimeError('Falta JOBS_DATABASE_URL')
    with urlopen(URL, timeout=12) as reply:
        data = reply.read(65537)
    if len(data) > 65536:
        raise ValueError('Respuesta demasiado grande')
    rates = normalize(json.loads(data, parse_float=Decimal))
    with psycopg.connect(dsn, connect_timeout=10) as connection, connection.cursor() as cursor:
        verify_jobs_role(cursor)
        cursor.execute("SET LOCAL statement_timeout='30s'")
        cursor.execute('SELECT public.guardar_cotizaciones_mercado(%s)', (Jsonb(rates),))
    return len(rates)


if __name__ == '__main__':
    try:
        print(f'OK: cotizaciones validadas={refresh()}')
    except Exception:
        print('ERROR: no se actualizó la cotización. Revisar DolarApi, la migración 0045 y app_jobs.', file=sys.stderr)
        sys.exit(1)
