"""Historial de movimientos del espacio con paginación por cursor."""
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import text

from app.accounts import execute, require_member, NO_STORE
from app.expenses import CATEGORIES

router = APIRouter()
Kind = Literal['gasto', 'ingreso', 'transferencia']
Currency = Literal['ARS', 'USD', 'EUR']
PAGE_SIZE = 50

HISTORY = text("""
    WITH movimientos AS (
        SELECT id, fecha, 'gasto' AS tipo, descripcion, moneda, importe,
               cuenta_id AS origen_id, NULL::uuid AS destino_id, categoria
        FROM public.gastos WHERE espacio_id=:space
        UNION ALL
        SELECT id, fecha, 'ingreso', descripcion, moneda, importe, NULL::uuid, cuenta_id, NULL::text
        FROM public.ingresos WHERE espacio_id=:space
        UNION ALL
        SELECT id, fecha, 'transferencia', descripcion, moneda, importe, origen_id, destino_id, NULL::text
        FROM public.transferencias WHERE espacio_id=:space
    ), filtrados AS (
        SELECT * FROM movimientos
        WHERE (CAST(:desde AS date) IS NULL OR fecha>=:desde)
          AND (CAST(:hasta AS date) IS NULL OR fecha<=:hasta)
          AND (CAST(:tipo AS text) IS NULL OR tipo=:tipo)
          AND (CAST(:moneda AS text) IS NULL OR moneda=:moneda)
          AND (CAST(:cuenta AS uuid) IS NULL OR origen_id=:cuenta OR destino_id=:cuenta)
          AND (CAST(:categoria AS text) IS NULL OR (tipo='gasto' AND COALESCE(categoria,'sin_categoria')=:categoria))
          AND strpos(lower(descripcion), lower(:texto))>0
    ), pagina AS (
        SELECT f.id, f.fecha, f.tipo, f.descripcion, f.moneda, f.importe::text AS importe,
               o.nombre AS origen, d.nombre AS destino, f.categoria
        FROM filtrados f
        LEFT JOIN public.cuentas o ON o.id=f.origen_id AND o.espacio_id=:space
        LEFT JOIN public.cuentas d ON d.id=f.destino_id AND d.espacio_id=:space
        WHERE CAST(:cursor_fecha AS date) IS NULL OR
              (f.fecha, f.tipo, f.id)<(:cursor_fecha, :cursor_tipo, :cursor_id)
        ORDER BY f.fecha DESC, f.tipo DESC, f.id DESC
        LIMIT :limit
    ), totales AS (
        SELECT moneda,
               round(COALESCE(sum(importe) FILTER (WHERE tipo='ingreso'),0),2)::text AS ingresos,
               round(COALESCE(sum(importe) FILTER (WHERE tipo='gasto'),0),2)::text AS gastos,
               round(COALESCE(sum(importe) FILTER (WHERE tipo='transferencia'),0),2)::text AS transferencias
        FROM filtrados GROUP BY moneda
    )
    SELECT (SELECT COALESCE(jsonb_agg(p ORDER BY p.fecha DESC,p.tipo DESC,p.id DESC),'[]') FROM pagina p) AS items,
           (SELECT COALESCE(jsonb_agg(t ORDER BY t.moneda),'[]') FROM totales t) AS totales
""")


def list_movements(session, user, space, filters, cursor):
    require_member(session, user, space)
    cursor_date, cursor_kind, cursor_id = cursor or (None, None, None)
    row = session.execute(HISTORY, {
        'categoria': None, **filters, 'space': space, 'limit': PAGE_SIZE + 1,
        'cursor_fecha': cursor_date, 'cursor_tipo': cursor_kind, 'cursor_id': cursor_id,
    }).mappings().one()
    items = row['items'][:PAGE_SIZE]
    next_cursor = None
    if len(row['items']) > PAGE_SIZE:
        last = items[-1]
        next_cursor = f"{last['fecha']}/{last['tipo']}/{last['id']}"
    return {'items': items, 'totales': row['totales'], 'next_cursor': next_cursor}


def parse_cursor(value):
    if value is None:
        return None
    try:
        day, kind, identifier = value.split('/')
        if kind not in ('gasto', 'ingreso', 'transferencia'):
            raise ValueError
        return date.fromisoformat(day), kind, UUID(identifier)
    except ValueError:
        raise HTTPException(422, 'Cursor inválido', headers=NO_STORE) from None


@router.get('/spaces/{space}/movements')
def movement_history(space: UUID, request: Request, response: Response,
                     desde: date | None = None, hasta: date | None = None,
                     tipo: Kind | None = None, moneda: Currency | None = None,
                     cuenta: UUID | None = None,
                     categoria: str | None = Query(default=None, max_length=32),
                     texto: str = Query(default='', max_length=160, pattern=r'^[^\x00-\x1f\x7f]*$'),
                     cursor: str | None = Query(default=None, max_length=70)):
    if desde and hasta and desde > hasta:
        raise HTTPException(422, 'El rango de fechas es inválido', headers=NO_STORE)
    if categoria is not None and categoria not in (*CATEGORIES, 'sin_categoria'):
        raise HTTPException(422, 'Categoría inválida', headers=NO_STORE)
    filters = {'categoria': categoria, 'desde': desde, 'hasta': hasta, 'tipo': tipo, 'moneda': moneda,
               'cuenta': cuenta, 'texto': texto.strip()}
    after = parse_cursor(cursor)
    return execute(request, response, space, lambda session, user: list_movements(session, user, space, filters, after))
