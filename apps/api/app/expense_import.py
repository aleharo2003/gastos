"""Importar gastos históricos con vista previa y anulación por lote."""
from collections import Counter
from hashlib import sha256
import json
from typing import Annotated
from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from app.accounts import NO_STORE, execute
from app.expenses import ExpenseInput, require_account

router = APIRouter()


class CsvExpense(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fecha: str
    descripcion: str
    moneda: str
    importe: str


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filas: Annotated[list[CsvExpense], Field(min_length=1, max_length=1000)]
    lote: UUID | None = None
    revision: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')] | None = None
    incluir_coincidencias_manuales: bool = Field(default=False, strict=True)


def lock_import(session, space):
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('expense_import:' || CAST(:s AS text),0))"),
                    {'s': space})


def normalized_rows(space, account, values):
    seen = Counter()
    for position, value in enumerate(values, start=1):
        try:
            row = ExpenseInput(id=space, **value.model_dump())
        except ValidationError:
            raise HTTPException(422, f'La fila válida número {position} tiene datos inválidos', headers=NO_STORE) from None
        identity = json.dumps((str(account), row.fecha.isoformat(), row.descripcion, row.moneda,
                               format(row.importe, '.2f')), ensure_ascii=False)
        seen[identity] += 1
        yield uuid5(space, identity + '#' + str(seen[identity])), row


def match_manual_rows(session, params, rows, imported):
    candidates = [row.model_dump(mode='json', include={'fecha', 'descripcion', 'moneda', 'importe'})
                  for key, row in rows if key not in imported]
    if not candidates:
        return []
    matches = session.execute(text('''
        WITH candidatos AS (
            SELECT DISTINCT fecha, descripcion, moneda, importe
            FROM jsonb_to_recordset(CAST(:candidates AS jsonb))
                AS r(fecha date, descripcion text, moneda text, importe numeric)
        )
        SELECT g.fecha, g.descripcion, g.moneda, g.importe, count(*) AS cantidad
        FROM public.gastos g JOIN candidatos c USING (fecha, descripcion, moneda, importe)
        WHERE g.espacio_id=:s AND g.cuenta_id=:a AND g.anulado_en IS NULL AND g.clave_importacion IS NULL
          AND NOT EXISTS (SELECT 1 FROM public.pagos_cuota p WHERE p.espacio_id=g.espacio_id AND p.id=g.id)
        GROUP BY g.fecha, g.descripcion, g.moneda, g.importe
    '''), params | {'candidates': json.dumps(candidates)}).mappings()
    counts = {(row['fecha'], row['descripcion'], row['moneda'], row['importe']): row['cantidad'] for row in matches}
    duplicates = []
    for position, (key, row) in enumerate(rows):
        identity = (row.fecha, row.descripcion, row.moneda, row.importe)
        if key not in imported and counts.get(identity, 0) > 0:
            duplicates.append(position)
            counts[identity] -= 1
    return duplicates


def import_rows(session, user, space, account, body, *, commit):
    require_account(session, user, space, account, write=True)
    if commit and (body.lote is None or not body.lote.int or body.revision is None):
        raise HTTPException(422, 'Confirmá la vista previa del lote', headers=NO_STORE)
    if commit:
        lock_import(session, space)
    params = {'s': space, 'a': account, 'lote': body.lote}
    if commit:
        previous = session.execute(text('''
            SELECT count(*) AS total, bool_and(usuario_id=:u AND cuenta_id=:a) AS mismo
            FROM public.gastos WHERE espacio_id=:s AND lote_importacion=:lote
        '''), params | {'u': user}).mappings().one()
        if previous['total']:
            if not previous['mismo']:
                raise HTTPException(409, 'El identificador ya se usó', headers=NO_STORE)
            return {'lote': body.lote, 'importadas': previous['total']}
    if not session.execute(text('SELECT activa FROM public.cuentas WHERE espacio_id=:s AND id=:a'), params).scalar_one():
        raise HTTPException(409, 'La cuenta está inactiva', headers=NO_STORE)
    rows = list(normalized_rows(space, account, body.filas))
    existing = set(session.execute(text('''
        SELECT clave_importacion FROM public.gastos WHERE espacio_id=:s
          AND clave_importacion=ANY(CAST(:keys AS uuid[])) AND anulado_en IS NULL
    '''), params | {'keys': [key for key, _ in rows]}).scalars())
    manual = match_manual_rows(session, params, rows, existing)
    excluded_manual = set() if body.incluir_coincidencias_manuales else set(manual)
    fresh = [(key, row) for position, (key, row) in enumerate(rows)
             if key not in existing and position not in excluded_manual]
    revision = sha256(b''.join(key.bytes for key, _ in fresh)).hexdigest()
    if not commit:
        duplicates = [position for position, (key, _) in enumerate(rows) if key in existing]
        return {'nuevas': len(fresh), 'duplicadas': duplicates, 'coincidencias_manuales': manual, 'revision': revision}
    if not fresh or revision != body.revision:
        raise HTTPException(409, 'Volvé a revisar los duplicados', headers=NO_STORE)
    session.execute(text('''
        INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe,lote_importacion,clave_importacion,importado_en)
        VALUES (:id,:s,:a,:u,:fecha,:descripcion,:moneda,:importe,:lote,:clave,now())
    '''), [params | {'id': uuid5(body.lote, str(key)), 'u': user, 'fecha': row.fecha,
                     'descripcion': row.descripcion, 'moneda': row.moneda, 'importe': row.importe, 'clave': key}
           for key, row in fresh])
    return {'lote': body.lote, 'importadas': len(fresh)}


def recent_batches(session, user, space, account):
    require_account(session, user, space, account, write=True)
    rows = session.execute(text('''
        SELECT lote_importacion AS lote, count(*) AS gastos, min(importado_en) AS fecha
        FROM public.gastos WHERE espacio_id=:s AND cuenta_id=:a
          AND lote_importacion IS NOT NULL AND anulado_en IS NULL
        GROUP BY lote_importacion ORDER BY fecha DESC, lote_importacion LIMIT 50
    '''), {'s': space, 'a': account}).mappings()
    return {'items': [dict(row) for row in rows]}


def cancel_batch(session, user, space, account, batch):
    require_account(session, user, space, account, write=True)
    lock_import(session, space)
    result = session.execute(text('''
        UPDATE public.gastos SET anulado_en=now()
        WHERE espacio_id=:s AND cuenta_id=:a AND lote_importacion=:lote AND anulado_en IS NULL
    '''), {'s': space, 'a': account, 'lote': batch})
    return {'anuladas': result.rowcount}


BASE = '/spaces/{space}/accounts/{account}/expense-import'


@router.get(BASE)
def read_batches(space: UUID, account: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: recent_batches(session, user, space, account))


@router.post(BASE + '/preview')
def preview_batch(space: UUID, account: UUID, body: ImportRequest, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: import_rows(session, user, space, account, body, commit=False))


@router.post(BASE)
def commit_batch(space: UUID, account: UUID, body: ImportRequest, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: import_rows(session, user, space, account, body, commit=True))


@router.post(BASE + '/{batch}/void')
def void_batch(space: UUID, account: UUID, batch: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: cancel_batch(session, user, space, account, batch))
