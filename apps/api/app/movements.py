"""Historial de movimientos del espacio con paginación por cursor."""
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import text

from app.accounts import execute, require_member, NO_STORE
from app.movement_categories import ExpenseFilter

router = APIRouter()
Kind = Literal['gasto', 'ingreso', 'transferencia', 'cambio']
VoidKind = Literal['ingreso', 'transferencia']
MOVEMENT_TABLES = {'ingreso': 'ingresos', 'transferencia': 'transferencias'}
Currency = Literal['ARS', 'USD', 'EUR']
PAGE_SIZE = 50

HISTORY = text("""
    WITH movimientos AS (
        SELECT id, fecha, 'gasto' AS tipo, descripcion, moneda, importe,
               cuenta_id AS origen_id, NULL::uuid AS destino_id, categoria, nota, anulado_en IS NOT NULL AS anulado,
               NULL::text AS moneda_destino, NULL::numeric AS importe_destino
        FROM public.gastos WHERE espacio_id=:space
        UNION ALL
        SELECT id, fecha, 'ingreso', descripcion, moneda, importe, NULL::uuid, cuenta_id, categoria, NULL::text, anulado_en IS NOT NULL, NULL, NULL
        FROM public.ingresos WHERE espacio_id=:space
        UNION ALL
        SELECT id, fecha, 'transferencia', descripcion, moneda, importe, origen_id, destino_id, NULL::text, NULL::text, anulado_en IS NOT NULL, NULL, NULL
        FROM public.transferencias WHERE espacio_id=:space
        UNION ALL
        SELECT id, fecha, 'cambio', contraparte,
               CASE WHEN tipo='compra' THEN 'ARS' ELSE 'USD' END,
               CASE WHEN tipo='compra' THEN ars ELSE usd END,
               origen_id, destino_id, NULL, NULL, false,
               CASE WHEN tipo='compra' THEN 'USD' ELSE 'ARS' END,
               CASE WHEN tipo='compra' THEN usd ELSE ars END
        FROM public.ventas_usd WHERE espacio_id=:space
    ), filtrados AS (
        SELECT * FROM movimientos
        WHERE anulado=:anulados
          AND (CAST(:desde AS date) IS NULL OR fecha>=:desde)
          AND (CAST(:hasta AS date) IS NULL OR fecha<=:hasta)
          AND (CAST(:tipo AS text) IS NULL OR tipo=:tipo)
          AND (CAST(:moneda AS text) IS NULL
               OR (moneda=:moneda AND (tipo<>'cambio' OR CAST(:cuenta AS uuid) IS NULL OR origen_id=:cuenta))
               OR (moneda_destino=:moneda AND (CAST(:cuenta AS uuid) IS NULL OR destino_id=:cuenta)))
          AND (CAST(:cuenta AS uuid) IS NULL OR origen_id=:cuenta OR destino_id=:cuenta)
          AND (CAST(:categoria AS text) IS NULL OR (tipo='gasto' AND COALESCE(categoria,'sin_categoria')=:categoria))
          AND (CAST(:categoria_ingreso AS text) IS NULL OR
               (tipo='ingreso' AND COALESCE(categoria,'sin_categoria')=:categoria_ingreso))
          AND (strpos(
              translate(lower(descripcion), 'áéíóúü', 'aeiouu'),
              translate(lower(:texto), 'áéíóúü', 'aeiouu')
          )>0 OR strpos(
              translate(lower(COALESCE(nota, '')), 'áéíóúü', 'aeiouu'),
              translate(lower(:texto), 'áéíóúü', 'aeiouu')
          )>0)
    ), pagina AS (
        SELECT f.id, f.fecha, f.tipo, f.descripcion, f.moneda, f.importe::text AS importe,
               o.nombre AS origen, d.nombre AS destino, f.categoria, f.anulado,
               f.moneda_destino, f.importe_destino::text AS importe_destino
        FROM filtrados f
        LEFT JOIN public.cuentas o ON o.id=f.origen_id AND o.espacio_id=:space
        LEFT JOIN public.cuentas d ON d.id=f.destino_id AND d.espacio_id=:space
        WHERE CAST(:cursor_fecha AS date) IS NULL OR
              (f.fecha, f.tipo, f.id)<(:cursor_fecha, :cursor_tipo, :cursor_id)
        ORDER BY f.fecha DESC, f.tipo DESC, f.id DESC
        LIMIT :limit
    ), apuntes AS (
        SELECT f.tipo, f.origen_id, f.destino_id, a.moneda, a.importe, a.entrada
        FROM filtrados f
        CROSS JOIN LATERAL (VALUES
            (f.moneda, f.importe, f.origen_id, false),
            (f.moneda_destino, f.importe_destino, f.destino_id, true)
        ) a(moneda, importe, cuenta, entrada)
        WHERE NOT f.anulado AND a.moneda IS NOT NULL
          AND (CAST(:moneda AS text) IS NULL OR a.moneda=:moneda)
          AND (f.tipo<>'cambio' OR CAST(:cuenta AS uuid) IS NULL OR a.cuenta=:cuenta)
    ), totales AS (
        SELECT moneda,
               round(COALESCE(sum(importe) FILTER (WHERE tipo='ingreso'),0),2)::text AS ingresos,
               round(COALESCE(sum(importe) FILTER (WHERE tipo='gasto'),0),2)::text AS gastos,
               round(COALESCE(sum(importe) FILTER (WHERE tipo='transferencia'),0),2)::text AS transferencias,
               CASE WHEN bool_or(tipo='cambio') THEN
                   round(COALESCE(sum(importe) FILTER (WHERE tipo='cambio' AND entrada),0),2)::text END AS cambio_entrada,
               CASE WHEN bool_or(tipo='cambio') THEN
                   round(COALESCE(sum(importe) FILTER (WHERE tipo='cambio' AND NOT entrada),0),2)::text END AS cambio_salida,
               CASE WHEN CAST(:cuenta AS uuid) IS NOT NULL THEN round(COALESCE(sum(
                   CASE WHEN tipo='cambio' THEN CASE WHEN entrada THEN importe ELSE -importe END
                        WHEN tipo='ingreso' OR (tipo='transferencia' AND destino_id=:cuenta) THEN importe
                        WHEN tipo='gasto' OR (tipo='transferencia' AND origen_id=:cuenta) THEN -importe
                        ELSE 0 END
               ),0),2)::text END AS variacion_cuenta
        FROM apuntes GROUP BY moneda
    )
    SELECT (SELECT COALESCE(jsonb_agg(p ORDER BY p.fecha DESC,p.tipo DESC,p.id DESC),'[]') FROM pagina p) AS items,
           (SELECT COALESCE(jsonb_agg(jsonb_strip_nulls(to_jsonb(t)) ORDER BY t.moneda),'[]') FROM totales t) AS totales
""")


def list_movements(session, user, space, filters, cursor):
    require_member(session, user, space)
    cursor_date, cursor_kind, cursor_id = cursor or (None, None, None)
    row = session.execute(HISTORY, {
        'categoria': None, 'categoria_ingreso': None, 'anulados': False, **filters, 'space': space, 'limit': PAGE_SIZE + 1,
        'cursor_fecha': cursor_date, 'cursor_tipo': cursor_kind, 'cursor_id': cursor_id,
    }).mappings().one()
    items = row['items'][:PAGE_SIZE]
    for item in items:
        if item['tipo'] != 'cambio':
            item.pop('moneda_destino', None)
            item.pop('importe_destino', None)
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
        if kind not in ('gasto', 'ingreso', 'transferencia', 'cambio'):
            raise ValueError
        return date.fromisoformat(day), kind, UUID(identifier)
    except ValueError:
        raise HTTPException(422, 'Cursor inválido', headers=NO_STORE) from None


@router.get('/spaces/{space}/movements')
def movement_history(space: UUID, request: Request, response: Response,
                     desde: date | None = None, hasta: date | None = None,
                     tipo: Kind | None = None, moneda: Currency | None = None,
                     cuenta: UUID | None = None,
                     categoria: ExpenseFilter | None = None,
                     categoria_ingreso: str | None = Query(default=None, pattern=r'^[a-z0-9_-]{1,36}$'),
                     texto: str = Query(default='', max_length=160, pattern=r'^[^\x00-\x1f\x7f]*$'),
                     anulados: bool = False,
                     cursor: str | None = Query(default=None, max_length=70)):
    if desde and hasta and desde > hasta:
        raise HTTPException(422, 'El rango de fechas es inválido', headers=NO_STORE)
    if categoria is not None and categoria_ingreso is not None:
        raise HTTPException(422, 'Elegí una sola categoría', headers=NO_STORE)
    filters = {'categoria': categoria, 'categoria_ingreso': categoria_ingreso,
               'desde': desde, 'hasta': hasta, 'tipo': tipo, 'moneda': moneda,
               'cuenta': cuenta, 'texto': texto.strip(), 'anulados': anulados}
    after = parse_cursor(cursor)
    return execute(request, response, space, lambda session, user: list_movements(session, user, space, filters, after))


def void_movement(session, user, space, kind, identifier):
    require_member(session, user, space, write=True)
    table = MOVEMENT_TABLES[kind]
    params = {'space': space, 'id': identifier}
    updated = session.execute(text(f"""
        UPDATE public.{table} SET anulado_en=now()
        WHERE espacio_id=:space AND id=:id AND anulado_en IS NULL
        RETURNING id
    """), params).scalar_one_or_none()
    if updated is None:
        voided = session.execute(text(f"""
            SELECT id FROM public.{table}
            WHERE espacio_id=:space AND id=:id AND anulado_en IS NOT NULL
        """), params).scalar_one_or_none()
        if voided is None:
            raise HTTPException(404, 'Movimiento no disponible', headers=NO_STORE)
    return {'id': str(identifier), 'anulado': True}


@router.post('/spaces/{space}/movements/{kind}/{identifier}/void')
def post_void_movement(space: UUID, kind: VoidKind, identifier: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: void_movement(session, user, space, kind, identifier))
