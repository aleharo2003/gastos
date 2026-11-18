"""Variaciones mensuales por indice y espacio."""
import csv
from datetime import date
from decimal import Decimal
from io import StringIO
import json
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import text

from app.accounts import NO_STORE, execute, require_member

router = APIRouter()
PAGE_SIZE = 100
MAX_CSV_BYTES = 32 * 1024
MAX_CSV_ROWS = 500
CSV_COLUMNS = ['indice', 'periodo', 'variacion']

# Los tipos coinciden con el registro individual. Las filas se envían como un parámetro.
CSV_RECORDS = """
    jsonb_to_recordset(CAST(:rows AS jsonb))
        AS entrada(linea integer, indice text, periodo date, variacion numeric)
"""


class IndexValueInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    indice: str
    periodo: date
    variacion: Decimal

    @field_validator('indice')
    @classmethod
    def validate_index(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Indice invalido')
        return value

    @field_validator('periodo', mode='before')
    @classmethod
    def validate_period(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', value):
            raise ValueError('Usar AAAA-MM')
        return date.fromisoformat(value + '-01')

    @field_validator('variacion', mode='before')
    @classmethod
    def validate_rate(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'-?[0-9]{1,6}(\.[0-9]{1,4})?', value):
            raise ValueError('Usar un porcentaje con hasta cuatro decimales')
        rate = Decimal(value)
        if rate <= -100:
            raise ValueError('La variacion debe ser mayor que -100%')
        return rate


def public_value(row):
    return {
        'indice': row['indice'],
        'periodo': row['periodo'].isoformat()[:7],
        'variacion': format(row['variacion'], '.4f'),
    }


def list_index_values(session, user, space, offset):
    require_member(session, user, space)
    rows = session.execute(text("""
        SELECT indice, periodo, variacion FROM public.variaciones_indice
        WHERE espacio_id = :space
        ORDER BY periodo DESC, indice
        LIMIT :limit OFFSET :offset
    """), {'space': space, 'limit': PAGE_SIZE + 1, 'offset': offset}).mappings().all()
    return {
        'items': [public_value(row) for row in rows[:PAGE_SIZE]],
        'next_offset': offset + PAGE_SIZE if len(rows) > PAGE_SIZE and offset <= 100000 - PAGE_SIZE else None,
    }


def save_index_value(session, user, space, value):
    require_member(session, user, space, write=True)
    params = {'space': space, 'indice': value.indice, 'periodo': value.periodo, 'rate': value.variacion}
    session.execute(text("""
        INSERT INTO public.variaciones_indice (espacio_id, indice, periodo, variacion)
        VALUES (:space, :indice, :periodo, :rate)
        ON CONFLICT (espacio_id, indice, periodo) DO NOTHING
    """), params)
    row = session.execute(text("""
        SELECT indice, periodo, variacion FROM public.variaciones_indice
        WHERE espacio_id = :space AND indice = :indice AND periodo = :periodo
    """), params).mappings().one()
    if row['variacion'] != value.variacion:
        raise HTTPException(409, 'El indice ya tiene otra variacion para ese mes', headers=NO_STORE)
    return public_value(row)


@router.get('/spaces/{space}/index-values')
def get_index_values(
    space: UUID, request: Request, response: Response, offset: int = Query(0, ge=0, le=100000),
):
    return execute(request, response, space, lambda session, user: list_index_values(session, user, space, offset))


@router.post('/spaces/{space}/index-values')
def post_index_value(space: UUID, body: IndexValueInput, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: save_index_value(session, user, space, body))


class IndexCsvInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    csv: str


def parse_index_csv(content):
    try:
        size = len(content.encode('utf-8'))
    except UnicodeError:
        raise HTTPException(422, 'El archivo debe estar en UTF-8.', headers=NO_STORE) from None
    if not 0 < size <= MAX_CSV_BYTES:
        raise HTTPException(422, 'El archivo debe tener hasta 32 KiB y contener datos.', headers=NO_STORE)

    content = content.removeprefix('\ufeff')
    header = content.partition('\n')[0].partition('\r')[0]
    reader = csv.reader(StringIO(content, newline=''), delimiter=';' if ';' in header else ',', strict=True)
    rows = []
    seen = set()
    try:
        if [value.strip().lower() for value in next(reader, [])] != CSV_COLUMNS:
            raise HTTPException(422, 'La primera fila debe tener las columnas indice, periodo y variacion.', headers=NO_STORE)
        while True:
            line = reader.line_num + 1
            columns = next(reader, None)
            if columns is None:
                break
            if not columns or all(not value.strip() for value in columns):
                continue
            if len(rows) >= MAX_CSV_ROWS:
                raise HTTPException(422, 'El archivo admite hasta 500 variaciones.', headers=NO_STORE)
            if len(columns) != len(CSV_COLUMNS):
                raise HTTPException(422, f'Fila {line}: se esperaban tres columnas.', headers=NO_STORE)
            index, period, rate = (value.strip() for value in columns)
            try:
                value = IndexValueInput(
                    indice=index, periodo=period, variacion=rate.removesuffix('%').strip().replace(',', '.'),
                )
            except ValidationError as error:
                field = error.errors()[0]['loc'][0]
                raise HTTPException(422, f'Fila {line}: valor inválido en {field}.', headers=NO_STORE) from None
            key = (value.indice, value.periodo)
            if key in seen:
                raise HTTPException(422, f'Fila {line}: índice y período repetidos en el archivo.', headers=NO_STORE)
            seen.add(key)
            rows.append({
                'linea': line,
                'indice': value.indice,
                'periodo': value.periodo.isoformat(),
                'variacion': str(value.variacion),
            })
    except csv.Error:
        raise HTTPException(422, f'CSV inválido cerca de la fila {reader.line_num}.', headers=NO_STORE) from None
    if not rows:
        raise HTTPException(422, 'El archivo debe contener al menos una variación.', headers=NO_STORE)
    return rows


def import_index_values(session, user, space, content):
    require_member(session, user, space, write=True)
    rows = parse_index_csv(content)
    params = {'space': space, 'rows': json.dumps(rows)}
    inserted = session.execute(text(f"""
        WITH inserted AS (
            INSERT INTO public.variaciones_indice (espacio_id, indice, periodo, variacion)
            SELECT :space, indice, periodo, variacion FROM {CSV_RECORDS}
            ORDER BY indice, periodo
            ON CONFLICT (espacio_id, indice, periodo) DO NOTHING
            RETURNING 1
        )
        SELECT count(*) FROM inserted
    """), params).scalar_one()
    # La segunda sentencia ve la fila confirmada si otro importador ganó la inserción.
    conflict = session.execute(text(f"""
        SELECT entrada.linea FROM {CSV_RECORDS}
        JOIN public.variaciones_indice AS guardada
          ON guardada.espacio_id = :space AND guardada.indice = entrada.indice AND guardada.periodo = entrada.periodo
        WHERE guardada.variacion <> entrada.variacion
        ORDER BY entrada.linea
        LIMIT 1
    """), params).scalar_one_or_none()
    if conflict is not None:
        raise HTTPException(
            409, f'Fila {conflict}: el índice ya tiene otra variación para ese mes.', headers=NO_STORE,
        )
    return {'importadas': inserted, 'existentes': len(rows) - inserted}


@router.post('/spaces/{space}/index-values/import')
def post_index_csv(space: UUID, body: IndexCsvInput, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: import_index_values(session, user, space, body.csv))
