"""Gastos con importes decimales, moneda explicita y pertenencia al espacio."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from app.accounts import execute, require_member, NO_STORE
from app.expense_search import ExpenseSearch
from app.category_suggestions import suggest_category
from app.movement_categories import ExpenseFilter, ExpenseKey, category_rows, lock_catalog, require_active_category
from app.similar_expenses import similarity

router = APIRouter()
AMOUNT = re.compile(r'(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?')

Category = Literal['alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros']
CATEGORIES = ['alimentos', 'transporte', 'vivienda', 'servicios', 'salud', 'educacion', 'ocio', 'impuestos', 'auto', 'bancario', 'ropa', 'otros']


class ExpenseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    fecha: date
    descripcion: str
    moneda: Literal['ARS','USD','EUR']
    importe: Decimal
    categoria: ExpenseKey | None = None
    nota: str | None = None

    @field_validator('nota')
    @classmethod
    def note(cls, value):
        if value is None:
            return None
        value = value.strip()
        if len(value) > 500 or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('Nota de hasta 500 caracteres sin controles')
        return value or None

    @field_validator('id')
    @classmethod
    def identifier(cls, value):
        if value.int == 0: raise ValueError('Identificador invalido')
        return value

    @field_validator('fecha', mode='before')
    @classmethod
    def iso_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError('Usar fecha ISO')
        return value

    @field_validator('descripcion')
    @classmethod
    def description(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 160 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Descripcion de 1 a 160 caracteres sin controles')
        return value

    @field_validator('importe', mode='before')
    @classmethod
    def amount(cls, value):
        # JSON string: nunca convertir un float binario a dinero.
        if not isinstance(value, str) or not AMOUNT.fullmatch(value) or Decimal(value) <= 0:
            raise ValueError('Importe positivo, hasta 12 enteros y dos decimales, como texto')
        return Decimal(value)


def require_account(session, user, space, account, write=False):
    require_member(session, user, space, write)
    found = session.execute(text('SELECT id FROM public.cuentas WHERE espacio_id=:s AND id=:a'),
                            {'s':space,'a':account}).scalar_one_or_none()
    if found is None:
        raise HTTPException(404, 'Cuenta no disponible', headers=NO_STORE)


class ExpenseEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    original: ExpenseInput
    nuevo: ExpenseInput


def edit_expense(session, user, space, account, expense_id, body):
    require_account(session, user, space, account, write=True)
    if session.execute(text('SELECT id FROM public.pagos_cuota WHERE espacio_id=:s AND id=:id'),{'s':space,'id':expense_id}).scalar_one_or_none() is not None:
        raise HTTPException(409,'Este gasto corresponde a un pago de cuota y no puede editarse desde gastos',headers=NO_STORE)
    if body.original.id != expense_id or body.nuevo.id != expense_id:
        raise HTTPException(422, 'Identificador inconsistente', headers=NO_STORE)
    params = {'id':expense_id, 's':space, 'a':account}
    if body.nuevo.categoria is not None:
        lock_catalog(session, space)
    row = session.execute(text('''SELECT * FROM public.gastos
        WHERE id=:id AND espacio_id=:s AND cuenta_id=:a FOR UPDATE'''), params).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, 'Gasto no disponible', headers=NO_STORE)
    if row['anulado_en'] is not None:
        raise HTTPException(409, 'El gasto está anulado', headers=NO_STORE)

    def matches(value):
        return (all(row[key] == getattr(value, key) for key in ('fecha','descripcion','moneda','importe'))
                and ('categoria' not in value.model_fields_set or row['categoria'] == value.categoria)
                and ('nota' not in value.model_fields_set or row['nota'] == value.nota))
    # A retry after a lost response returns the already saved state.
    if matches(body.nuevo):
        return public_expense(row)
    if not matches(body.original):
        raise HTTPException(409, 'El gasto cambio; actualiza la lista antes de editar', headers=NO_STORE)
    if 'categoria' in body.nuevo.model_fields_set and body.nuevo.categoria != row['categoria']:
        require_active_category(session, space, 'gasto', body.nuevo.categoria)
    params.update(f=body.nuevo.fecha, d=body.nuevo.descripcion, m=body.nuevo.moneda, i=body.nuevo.importe,
                  c=body.nuevo.categoria if 'categoria' in body.nuevo.model_fields_set else row['categoria'],
                  nota=body.nuevo.nota if 'nota' in body.nuevo.model_fields_set else row['nota'])
    updated = session.execute(text('''UPDATE public.gastos SET fecha=:f, descripcion=:d, moneda=:m, importe=:i, categoria=:c, nota=:nota
        WHERE id=:id AND espacio_id=:s AND cuenta_id=:a RETURNING *'''),params).mappings().one_or_none()
    if updated is None:
        raise HTTPException(403, 'Sin permiso para editar', headers=NO_STORE)
    return public_expense(updated)


@router.patch('/spaces/{space}/accounts/{account}/expenses/{expense_id}')
def patch_expense(space: UUID, account: UUID, expense_id: UUID, body: ExpenseEdit, request: Request, response: Response):
    return execute(request,response,space,lambda session,user: edit_expense(session,user,space,account,expense_id,body))


def void_expense(session, user, space, account, expense_id):
    require_account(session, user, space, account, write=True)
    params = {'id': expense_id, 's': space, 'a': account}
    row = session.execute(text('''
        SELECT * FROM public.gastos
        WHERE id=:id AND espacio_id=:s AND cuenta_id=:a FOR UPDATE
    '''), params).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, 'Gasto no disponible', headers=NO_STORE)
    if row['anulado_en'] is None:
        payment = session.execute(text('''
            SELECT id FROM public.pagos_cuota WHERE espacio_id=:s AND id=:id
        '''), params).scalar_one_or_none()
        if payment is not None:
            raise HTTPException(409, 'El gasto corresponde a un pago de cuota', headers=NO_STORE)
        updated = session.execute(text('''
            UPDATE public.gastos SET anulado_en=now()
            WHERE id=:id AND espacio_id=:s AND cuenta_id=:a RETURNING id
        '''), params).scalar_one_or_none()
        if updated is None:
            raise HTTPException(403, 'Sin permiso para anular', headers=NO_STORE)
    return {'id': str(expense_id), 'anulado': True}


@router.post('/spaces/{space}/accounts/{account}/expenses/{expense_id}/void')
def post_void_expense(space: UUID, account: UUID, expense_id: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: void_expense(session, user, space, account, expense_id))


def public_expense(row):
    result = {'id':str(row['id']), 'espacio_id':str(row['espacio_id']), 'cuenta_id':str(row['cuenta_id']),
            'fecha':row['fecha'].isoformat(), 'descripcion':row['descripcion'], 'moneda':row['moneda'],
            'importe':format(row['importe'], '.2f'), 'categoria':row['categoria']} | ({'cuenta_nombre':row['cuenta_nombre']} if 'cuenta_nombre' in row else {})
    if row.get('nota') is not None:
        result['nota'] = row['nota']
    if row.get('pago_cuota'):
        result['pago_cuota'] = True
    return result


class ExpenseFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    desde: date | None = None
    hasta: date | None = None
    categoria: ExpenseFilter | None = None
    moneda: Literal['ARS','USD','EUR'] | None = None
    texto: str = ''
    aproximada: bool = True

    @field_validator('texto')
    @classmethod
    def search(cls, value):
        value = value.strip()
        if len(value) > 160 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Texto invalido')
        return value


def list_expenses(session, user, space, account, offset=0, filters=None):
    if account is None: require_member(session, user, space)
    else: require_account(session, user, space, account)
    filters = filters or ExpenseFilters()
    if filters.desde and filters.hasta and filters.desde > filters.hasta:
        raise HTTPException(422, 'La fecha desde no puede superar hasta', headers=NO_STORE)
    conditions = ['espacio_id=:s', 'anulado_en IS NULL']
    if account is not None: conditions.append('cuenta_id=:a')
    params = {'s':space,'a':account,'offset':offset}
    for field, operator in [('desde','>='), ('hasta','<=')]:
        value = getattr(filters, field)
        if value:
            conditions.append(f'fecha {operator} :{field}')
            params[field] = value
    if filters.categoria == 'sin_categoria':
        conditions.append('categoria IS NULL')
    elif filters.categoria:
        conditions.append('categoria=:categoria'); params['categoria'] = filters.categoria
    if filters.moneda:
        conditions.append('moneda=:moneda'); params['moneda'] = filters.moneda
    statement = '''SELECT *,
        (SELECT nombre FROM public.cuentas WHERE id=public.gastos.cuenta_id AND espacio_id=public.gastos.espacio_id) AS cuenta_nombre,
        EXISTS (SELECT 1 FROM public.pagos_cuota p WHERE p.id=public.gastos.id
                AND p.espacio_id=public.gastos.espacio_id) AS pago_cuota
        FROM public.gastos WHERE ''' + ' AND '.join(conditions) + ' ORDER BY fecha DESC, id DESC'
    if not filters.texto:
        rows = session.execute(text(statement + ' LIMIT 101 OFFSET :offset'), params).mappings().all()
        return {'items':[public_expense(row) for row in rows[:100]],
                'next_offset':offset + 100 if len(rows) > 100 else None}

    # Filtrar antes de paginar: nunca buscar solo en los primeros 100 gastos.
    # El cursor se mantiene dentro de la transaccion runtime y se cierra siempre.
    search = ExpenseSearch(filters.texto, filters.aproximada)
    result = session.execute(text(statement), params, execution_options={'yield_per':200})
    found = 0
    items = []
    try:
        for row in result.mappings():
            kind = search.match(row['descripcion'])
            if not kind:
                continue
            found += 1
            if found <= offset:
                continue
            if len(items) == 100:
                return {'items':items,'next_offset':offset+100}
            items.append(public_expense(row) | {'coincidencia_aproximada':kind == 2})
    finally:
        result.close()
    return {'items':items,'next_offset':None}


def create_expense(session, user, space, account, body):
    require_account(session, user, space, account, write=True)
    params = {'id':body.id,'s':space,'a':account,'u':user,'f':body.fecha,
              'd':body.descripcion,'m':body.moneda,'i':body.importe,'c':body.categoria,'nota':body.nota}
    if body.categoria is not None:
        lock_catalog(session, space)
        existing = session.execute(text('SELECT id FROM public.gastos WHERE id=:id AND espacio_id=:s AND cuenta_id=:a'),
                                   params).scalar_one_or_none()
        if existing is None:
            require_active_category(session, space, 'gasto', body.categoria)
    session.execute(text('''INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe,categoria,nota)
                            VALUES (:id,:s,:a,:u,:f,:d,:m,:i,:c,:nota) ON CONFLICT (id) DO NOTHING'''),params)
    row = session.execute(text('SELECT * FROM public.gastos WHERE id=:id AND espacio_id=:s AND cuenta_id=:a'),
                          params).mappings().one_or_none()
    if (row is None or str(row['usuario_id']) != str(user) or row['fecha'] != body.fecha or
        row['descripcion'] != body.descripcion or row['moneda'] != body.moneda or row['importe'] != body.importe or row['categoria'] != body.categoria or row['nota'] != body.nota):
        raise HTTPException(409, 'Identificador usado para otro gasto', headers=NO_STORE)
    return public_expense(row)


@router.get('/spaces/{space}/accounts/{account}/expenses')
def get_expenses(space: UUID, account: UUID, request: Request, response: Response,
                 offset: int = Query(default=0, ge=0, le=100000),
                 desde: date | None = None, hasta: date | None = None,
                 categoria: ExpenseFilter | None = None,
                 moneda: Literal['ARS','USD','EUR'] | None = None,
                 texto: str = Query(default='', max_length=160, pattern=r'^[^\x00-\x1f\x7f]*$'),
                 aproximada: bool = True):
    return execute(request,response,space,lambda session,user: list_expenses(session,user,space,account,offset,
        ExpenseFilters(desde=desde,hasta=hasta,categoria=categoria,moneda=moneda,texto=texto,aproximada=aproximada)))


@router.post('/spaces/{space}/accounts/{account}/expenses')
def post_expense(space: UUID, account: UUID, body: ExpenseInput, request: Request, response: Response):
    return execute(request,response,space,lambda session,user: create_expense(session,user,space,account,body))


def category_suggestion(session, user, space, account, description):
    require_account(session, user, space, account)
    rows = session.execute(text('''SELECT descripcion, categoria FROM public.gastos
        WHERE espacio_id=:s AND cuenta_id=:a AND anulado_en IS NULL AND categoria IS NOT NULL
        ORDER BY fecha DESC, id DESC LIMIT 500'''), {'s':space,'a':account}).mappings().all()
    available = {key for (kind, key), category in category_rows(session, space).items()
                 if kind == 'gasto' and category['activa']}
    return suggest_category(description, (row for row in rows if row['categoria'] in available))


@router.get('/spaces/{space}/accounts/{account}/expenses/category-suggestion')
def get_category_suggestion(space: UUID, account: UUID, request: Request, response: Response,
                            descripcion: str = Query(min_length=4,max_length=160,pattern=r'^[^\x00-\x1f\x7f]*$')):
    return execute(request,response,space,lambda session,user: category_suggestion(session,user,space,account,descripcion))


def list_similar_expenses(session,user,space,account,expense_id):
    require_account(session,user,space,account)
    params={'s':space,'a':account,'id':expense_id}
    source=session.execute(text('SELECT descripcion FROM public.gastos WHERE espacio_id=:s AND cuenta_id=:a AND id=:id AND anulado_en IS NULL'),params).scalar_one_or_none()
    if source is None:
        raise HTTPException(404,'Gasto no disponible',headers=NO_STORE)
    result=session.execute(text('SELECT * FROM public.gastos WHERE espacio_id=:s AND cuenta_id=:a AND id<>:id AND anulado_en IS NULL ORDER BY fecha DESC, id DESC'),params,execution_options={'yield_per':200})
    items=[]
    try:
        for row in result.mappings():
            kind=similarity(source,row['descripcion'])
            if not kind:
                continue
            items.append(public_expense(row)|{'coincidencia_aproximada':kind==2})
            if len(items)==5:
                break
    finally:
        result.close()
    return {'referencia_id':str(expense_id),'items':items}


@router.get('/spaces/{space}/accounts/{account}/expenses/{expense_id}/similar')
def get_similar_expenses(space:UUID,account:UUID,expense_id:UUID,request:Request,response:Response):
    return execute(request,response,space,lambda session,user:list_similar_expenses(session,user,space,account,expense_id))

@router.get('/spaces/{space}/expenses')
def get_all_expenses(space: UUID, request: Request, response: Response,
                 offset: int = Query(default=0, ge=0, le=100000),
                 desde: date | None = None, hasta: date | None = None,
                     categoria: ExpenseFilter | None = None,
                 moneda: Literal['ARS','USD','EUR'] | None = None,
                 texto: str = Query(default='', max_length=160, pattern=r'^[^\x00-\x1f\x7f]*$'),
                 aproximada: bool = True):
    return execute(request,response,space,lambda session,user: list_expenses(session,user,space,None,offset,
        ExpenseFilters(desde=desde,hasta=hasta,categoria=categoria,moneda=moneda,texto=texto,aproximada=aproximada)))



def expense_summary(session, user, space, account=None, day=None):
    if account is None: require_member(session, user, space)
    else: require_account(session, user, space, account)
    day = day or datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    first = day.replace(day=1)
    until = date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)
    week = day - timedelta(days=day.weekday())
    week_end = week + timedelta(days=7)
    account_filter = ' AND cuenta_id=:a' if account is not None else ''
    rows = session.execute(text("""SELECT moneda,
        COALESCE(SUM(importe) FILTER (WHERE fecha=:d),0) AS dia,
        COALESCE(SUM(importe) FILTER (WHERE fecha>=:f AND fecha<:u),0) AS mes,
        COALESCE(SUM(importe) FILTER (WHERE fecha>=:w AND fecha<:we),0) AS semana FROM public.gastos
        WHERE espacio_id=:s AND anulado_en IS NULL AND fecha>=LEAST(:f,:w) AND fecha<GREATEST(:u,:we)""" + account_filter + ' GROUP BY moneda'),
        {'s':space,'a':account,'d':day,'f':first,'u':until,'w':week,'we':week_end}).mappings().all()
    return {'fecha':day.isoformat(), 'mes':day.strftime('%Y-%m'),'semana_desde':week.isoformat(),'semana_hasta':(week_end-timedelta(days=1)).isoformat(),
            'totales':[{'moneda':r['moneda'],'dia':format(r['dia'],'.2f'),'mes':format(r['mes'],'.2f'),'semana':format(r['semana'],'.2f')} for r in rows]}


@router.get('/spaces/{space}/expense-summary')
def get_expense_summary(space: UUID, request: Request, response: Response, account: UUID | None = None):
    return execute(request,response,space,lambda session,user: expense_summary(session,user,space,account))


def expense_category_summary(session, user, space, account=None, day=None):
    if account is None:
        require_member(session, user, space)
    else:
        require_account(session, user, space, account)

    day = day or datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    start = day.replace(day=1)
    end = date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)
    account_filter = ' AND cuenta_id=:account' if account is not None else ''
    rows = session.execute(text("""
        SELECT moneda, categoria, SUM(importe) AS total
        FROM public.gastos
        WHERE espacio_id=:space AND anulado_en IS NULL AND fecha>=:start AND fecha<:end
    """ + account_filter + """
        GROUP BY moneda, categoria
        ORDER BY moneda, total DESC, categoria NULLS LAST
    """), {'space': space, 'start': start, 'end': end, 'account': account}).mappings().all()

    return {
        'desde': start.isoformat(),
        'hasta': (end - timedelta(days=1)).isoformat(),
        'items': [
            {'moneda': row['moneda'], 'categoria': row['categoria'], 'total': format(row['total'], '.2f')}
            for row in rows
        ],
    }


@router.get('/spaces/{space}/expense-category-summary')
def get_expense_category_summary(space: UUID, request: Request, response: Response, account: UUID | None = None,
                                 mes: str | None = Query(default=None, pattern=r'^(19[0-9]{2}|20[0-9]{2})-(0[1-9]|1[0-2])$')):
    day = date.fromisoformat(mes + '-01') if mes is not None else None
    return execute(request, response, space, lambda session, user: expense_category_summary(session, user, space, account, day))


def expense_trend(session, user, space, account=None, day=None):
    if account is None:
        require_member(session, user, space)
    else:
        require_account(session, user, space, account)
    day = day or datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    latest = day.year * 12 + day.month - 1
    months = [date(number // 12, number % 12 + 1, 1) for number in range(latest - 11, latest + 2)]
    rows = session.execute(text("""
        SELECT to_char(fecha, 'YYYY-MM') AS mes, moneda, categoria, SUM(importe) AS total
        FROM public.gastos
        WHERE espacio_id=:space AND anulado_en IS NULL AND fecha>=:start AND fecha<:end
          AND (CAST(:account AS uuid) IS NULL OR cuenta_id=:account)
        GROUP BY 1, moneda, categoria ORDER BY 1, moneda, categoria
    """), {'space': space, 'start': months[0], 'end': months[-1], 'account': account}).mappings().all()
    return {
        'meses': [month.isoformat()[:7] for month in months[:-1]],
        'items': [{'mes': row['mes'], 'moneda': row['moneda'], 'categoria': row['categoria'],
                   'total': format(row['total'], '.2f')} for row in rows],
    }


@router.get('/spaces/{space}/expense-trend')
def get_expense_trend(space: UUID, request: Request, response: Response, account: UUID | None = None):
    return execute(request, response, space, lambda session, user: expense_trend(session, user, space, account))
