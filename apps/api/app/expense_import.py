"""Importar movimientos históricos con vista previa y anulación por lote."""
from collections import Counter
from hashlib import sha256
import json
from typing import Annotated, Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from app.accounts import NO_STORE, execute
from app.expenses import ExpenseInput, require_account
from app.incomes import IncomeInput

router = APIRouter()
Kind = Literal['gasto', 'ingreso', 'transferencia']
TABLES = {'gasto': 'gastos', 'ingreso': 'ingresos', 'transferencia': 'transferencias'}


def account_filter(kind: Kind) -> str:
    return 'origen_id=:a AND destino_id=:destination' if kind == 'transferencia' else 'cuenta_id=:a'


def require_import_accounts(session, user, space, account, destination, kind):
    if kind == 'transferencia':
        if destination is None or account == destination:
            raise HTTPException(422, 'Elegí dos cuentas distintas', headers=NO_STORE)
        require_account(session, user, space, destination, write=True)
    elif destination is not None:
        raise HTTPException(422, 'El destino se usa en transferencias', headers=NO_STORE)
    require_account(session, user, space, account, write=True)


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


def normalized_rows(space, account, values, kind, destination):
    seen = Counter()
    model = ExpenseInput if kind == 'gasto' else IncomeInput
    for position, value in enumerate(values, start=1):
        try:
            row = model(id=space, **value.model_dump())
        except ValidationError:
            raise HTTPException(422, f'La fila válida número {position} tiene datos inválidos', headers=NO_STORE) from None
        fields = (str(account), row.fecha.isoformat(), row.descripcion, row.moneda, format(row.importe, '.2f'))
        if destination is not None:
            fields += (str(destination),)
        identity = json.dumps(fields, ensure_ascii=False)
        seen[identity] += 1
        yield uuid5(space, identity + '#' + str(seen[identity])), row


def match_manual_rows(session, params, rows, imported, kind):
    candidates = [row.model_dump(mode='json', include={'fecha', 'descripcion', 'moneda', 'importe'})
                  for key, row in rows if key not in imported]
    if not candidates:
        return []
    payment_filter = ('AND NOT EXISTS (SELECT 1 FROM public.pagos_cuota p WHERE p.espacio_id=g.espacio_id AND p.id=g.id)'
                      if kind == 'gasto' else '')
    matches = session.execute(text(f'''
        WITH candidatos AS (
            SELECT DISTINCT fecha, descripcion, moneda, importe
            FROM jsonb_to_recordset(CAST(:candidates AS jsonb))
                AS r(fecha date, descripcion text, moneda text, importe numeric)
        )
        SELECT g.fecha, g.descripcion, g.moneda, g.importe, count(*) AS cantidad
        FROM public.{TABLES[kind]} g JOIN candidatos c USING (fecha, descripcion, moneda, importe)
        WHERE g.espacio_id=:s AND {account_filter(kind)} AND g.anulado_en IS NULL AND g.clave_importacion IS NULL
          {payment_filter}
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


def import_rows(session, user, space, account, body, *, commit, kind: Kind = 'gasto', destination=None):
    require_import_accounts(session, user, space, account, destination, kind)
    if commit and (body.lote is None or not body.lote.int or body.revision is None):
        raise HTTPException(422, 'Confirmá la vista previa del lote', headers=NO_STORE)
    if commit:
        lock_import(session, space)
    params = {'s': space, 'a': account, 'lote': body.lote, 'destination': destination}
    table = TABLES[kind]
    if commit:
        previous = session.execute(text(f'''
            SELECT count(*) AS total, bool_and(usuario_id=:u AND {account_filter(kind)}) AS mismo
            FROM public.{table} WHERE espacio_id=:s AND lote_importacion=:lote
        '''), params | {'u': user}).mappings().one()
        if previous['total']:
            if not previous['mismo']:
                raise HTTPException(409, 'El identificador ya se usó', headers=NO_STORE)
            return {'lote': body.lote, 'importadas': previous['total']}
    accounts = [account] if destination is None else [account, destination]
    currencies = session.execute(text("""
        SELECT moneda FROM public.cuentas WHERE espacio_id=:s AND id=ANY(CAST(:accounts AS uuid[])) AND activa
    """), {'s': space, 'accounts': accounts}).scalars().all()
    if len(currencies) != len(accounts):
        raise HTTPException(409, 'Elegí cuentas activas', headers=NO_STORE)
    rows = list(normalized_rows(space, account, body.filas, kind, destination))
    for position, (_, row) in enumerate(rows, start=1):
        if any(currency is not None and currency != row.moneda for currency in currencies):
            raise HTTPException(422, f'La moneda de la fila {position} no coincide con la cuenta', headers=NO_STORE)
    existing = set(session.execute(text(f'''
        SELECT clave_importacion FROM public.{table} WHERE espacio_id=:s
          AND clave_importacion=ANY(CAST(:keys AS uuid[])) AND anulado_en IS NULL
    '''), params | {'keys': [key for key, _ in rows]}).scalars())
    manual = match_manual_rows(session, params, rows, existing, kind)
    excluded_manual = set() if body.incluir_coincidencias_manuales else set(manual)
    fresh = [(key, row) for position, (key, row) in enumerate(rows)
             if key not in existing and position not in excluded_manual]
    revision = sha256(b''.join(key.bytes for key, _ in fresh)).hexdigest()
    if not commit:
        duplicates = [position for position, (key, _) in enumerate(rows) if key in existing]
        return {'nuevas': len(fresh), 'duplicadas': duplicates, 'coincidencias_manuales': manual, 'revision': revision}
    if not fresh or revision != body.revision:
        raise HTTPException(409, 'Volvé a revisar los duplicados', headers=NO_STORE)
    columns, values = ('origen_id,destino_id', ':a,:destination') if kind == 'transferencia' else ('cuenta_id', ':a')
    session.execute(text(f'''
        INSERT INTO public.{table}(id,espacio_id,{columns},usuario_id,fecha,descripcion,moneda,importe,lote_importacion,clave_importacion,importado_en)
        VALUES (:id,:s,{values},:u,:fecha,:descripcion,:moneda,:importe,:lote,:clave,now())
    '''), [params | {'id': uuid5(body.lote, str(key)), 'u': user, 'fecha': row.fecha,
                     'descripcion': row.descripcion, 'moneda': row.moneda, 'importe': row.importe, 'clave': key}
           for key, row in fresh])
    return {'lote': body.lote, 'importadas': len(fresh)}


def recent_batches(session, user, space, account, kind: Kind = 'gasto', destination=None):
    require_import_accounts(session, user, space, account, destination, kind)
    rows = session.execute(text(f'''
        SELECT lote_importacion AS lote, count(*) AS gastos, min(importado_en) AS fecha
        FROM public.{TABLES[kind]} WHERE espacio_id=:s AND {account_filter(kind)}
          AND lote_importacion IS NOT NULL AND anulado_en IS NULL
        GROUP BY lote_importacion ORDER BY fecha DESC, lote_importacion LIMIT 50
    '''), {'s': space, 'a': account, 'destination': destination}).mappings()
    return {'items': [dict(row) for row in rows]}


def cancel_batch(session, user, space, account, batch, kind: Kind = 'gasto', destination=None):
    require_import_accounts(session, user, space, account, destination, kind)
    lock_import(session, space)
    result = session.execute(text(f'''
        UPDATE public.{TABLES[kind]} SET anulado_en=now()
        WHERE espacio_id=:s AND {account_filter(kind)} AND lote_importacion=:lote AND anulado_en IS NULL
    '''), {'s': space, 'a': account, 'lote': batch, 'destination': destination})
    return {'anuladas': result.rowcount}


BASE = '/spaces/{space}/accounts/{account}/expense-import'


@router.get(BASE)
def read_batches(space: UUID, account: UUID, request: Request, response: Response, tipo: Kind = 'gasto', destino: UUID | None = None):
    return execute(request, response, space, lambda session, user: recent_batches(session, user, space, account, tipo, destino))


@router.post(BASE + '/preview')
def preview_batch(space: UUID, account: UUID, body: ImportRequest, request: Request, response: Response,
                  tipo: Kind = 'gasto', destino: UUID | None = None):
    return execute(request, response, space,
                   lambda session, user: import_rows(session, user, space, account, body, commit=False, kind=tipo, destination=destino))


@router.post(BASE)
def commit_batch(space: UUID, account: UUID, body: ImportRequest, request: Request, response: Response,
                 tipo: Kind = 'gasto', destino: UUID | None = None):
    return execute(request, response, space,
                   lambda session, user: import_rows(session, user, space, account, body, commit=True, kind=tipo, destination=destino))


@router.post(BASE + '/{batch}/void')
def void_batch(space: UUID, account: UUID, batch: UUID, request: Request, response: Response,
               tipo: Kind = 'gasto', destino: UUID | None = None):
    return execute(request, response, space, lambda session, user: cancel_batch(session, user, space, account, batch, tipo, destino))
