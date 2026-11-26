"""Deudas fijas finitas: calendario mensual y pagos exactos sin doble gasto."""
from calendar import monthrange
from datetime import date,datetime,timedelta
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID,uuid5
from zoneinfo import ZoneInfo
from fastapi import APIRouter,HTTPException,Request,Response,Query
from pydantic import BaseModel,ConfigDict,Field,StrictInt,field_validator,model_validator
from sqlalchemy import text
from app.adjustment_indices import IndexValueInput
from app.amortization import AmortizationSystem, amortize
from app.accounts import execute,require_member,NO_STORE
from app.expenses import Category,expense_summary,require_account
from app.incomes import IncomeInput,account_balance
from app.planning import get_plan

router=APIRouter()
ARGENTINA_TIMEZONE = ZoneInfo('America/Argentina/Buenos_Aires')


def commitment_local_date(instant: datetime | None = None) -> date:
    return datetime.now(ARGENTINA_TIMEZONE).date() if instant is None else instant.astimezone(ARGENTINA_TIMEZONE).date()


def monthly_due(first,offset):
    month=first.year*12+first.month-1+offset
    year,month=divmod(month,12)
    return date(year,month+1,min(first.day,monthrange(year,month+1)[1]))


class CommitmentInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:UUID
    cuenta_id:UUID
    nombre:str
    moneda:Literal['ARS','USD','EUR']
    importe:Decimal
    variable:bool=Field(default=False,strict=True)
    indice_ajuste: str | None = None
    sistema_amortizacion: AmortizationSystem | None = None
    tna: Decimal | None = None
    categoria:Category|None=None
    primer_vencimiento:date
    total_cuotas:StrictInt|None=Field(ge=1,le=600)

    @field_validator('id','cuenta_id')
    @classmethod
    def identifier(cls,value):return IncomeInput.identifier(value)

    @field_validator('nombre')
    @classmethod
    def name(cls,value):return IncomeInput.description(value)

    @field_validator('importe',mode='before')
    @classmethod
    def amount(cls,value):return IncomeInput.amount(value)

    @field_validator('primer_vencimiento',mode='before')
    @classmethod
    def iso_date(cls,value):return IncomeInput.iso_date(value)

    @field_validator('indice_ajuste')
    @classmethod
    def adjust_index(cls, value):
        return IndexValueInput.validate_index(value) if value is not None else None

    @field_validator('tna', mode='before')
    @classmethod
    def annual_rate(cls, value):
        if value is None:
            return None
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,18}(\.[0-9]{1,8})?', value):
            raise ValueError('La TNA debe ser un porcentaje no negativo con hasta ocho decimales')
        return Decimal(value)

    @model_validator(mode='after')
    def date_range(self):
        if (self.sistema_amortizacion is None) != (self.tna is None):
            raise ValueError('Indicá el sistema de amortización y la TNA juntos')
        if self.sistema_amortizacion is not None and (self.variable or self.indice_ajuste is not None or self.total_cuotas is None):
            raise ValueError('El préstamo amortizado requiere un plazo fijo y una tasa fija')
        if self.indice_ajuste is not None and (self.variable or self.total_cuotas is None):
            raise ValueError('El ajuste por índice requiere un plan con cantidad de cuotas')
        if self.variable and self.total_cuotas is not None:raise ValueError('Un gasto variable debe ser mensual sin fin conocido')
        if self.total_cuotas is not None and self.primer_vencimiento.year*12+self.primer_vencimiento.month-1+self.total_cuotas-1>=10000*12:
            raise ValueError('El calendario supera el rango de fechas')
        return self


class PaymentInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:UUID
    cuenta_id:UUID
    fecha:date
    importe:Decimal

    @field_validator('id','cuenta_id')
    @classmethod
    def identifier(cls,value):return IncomeInput.identifier(value)

    @field_validator('importe',mode='before')
    @classmethod
    def amount(cls,value):return IncomeInput.amount(value)

    @field_validator('fecha',mode='before')
    @classmethod
    def iso_date(cls,value):return IncomeInput.iso_date(value)


def public_commitment(row):
    paid=row['pagado']
    total=row['total_generado']
    return {key:str(row[key]) for key in ('id','espacio_id','cuenta_id')}|{
        'nombre':row['nombre'],'moneda':row['moneda'],'importe':format(row['importe'],'.2f'),
        'categoria':row['categoria'],'primer_vencimiento':row['primer_vencimiento'].isoformat(),
        'total_cuotas':row['total_cuotas'],'cuotas_pagadas':row['cuotas_pagadas'],'cuotas_no_aplican':row.get('cuotas_no_aplican',0),
        'pausado':row['pausado'],'version':row['version'],'variable':row['variable'],
        'total':format(total,'.2f'),'pagado':format(paid,'.2f'),'pendiente':format(total-paid,'.2f'),
        'proximo_vencimiento':row['proximo_vencimiento'].isoformat() if row['proximo_vencimiento'] else None} | (
            {'cuotas_ajustadas': row['cuotas_ajustadas']} if row.get('cuotas_ajustadas') else {}) | (
            {'indice_ajuste': row['indice_ajuste']} if row.get('indice_ajuste') is not None else {}) | (
            {'sistema_amortizacion': row['sistema_amortizacion'], 'tna': format(row['tna'], '.8f').rstrip('0').rstrip('.')}
            if row.get('sistema_amortizacion') is not None else {})


def list_commitments(session,user,space,offset=0,identifier=None,*,page_size=101):
    require_member(session,user,space)
    clause=' AND c.id=:id' if identifier is not None else ''
    rows=session.execute(text("""WITH pagos AS (
        SELECT p.cuota_id,SUM(g.importe) AS pagado FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE p.espacio_id=:s GROUP BY p.cuota_id),
        compromisos_resumidos AS (
        SELECT c.*,COALESCE(SUM(q.importe) FILTER (WHERE NOT q.no_aplica),0) AS total_generado,
            COUNT(*) FILTER (WHERE q.no_aplica) AS cuotas_no_aplican,COUNT(*) FILTER (WHERE COALESCE(p.pagado,0)>=q.importe) AS cuotas_pagadas,
            COUNT(*) FILTER (WHERE NOT q.no_aplica AND NOT c.variable AND c.indice_ajuste IS NULL
                             AND c.sistema_amortizacion IS NULL AND q.importe<>c.importe) AS cuotas_ajustadas,
            COALESCE(SUM(p.pagado),0) AS pagado,
            MIN(q.vencimiento) FILTER (WHERE NOT q.no_aplica AND COALESCE(p.pagado,0)<q.importe) AS proximo_vencimiento
        FROM public.compromisos c LEFT JOIN public.cuotas q ON q.espacio_id=c.espacio_id AND q.compromiso_id=c.id
        LEFT JOIN pagos p ON p.cuota_id=q.id WHERE c.espacio_id=:s"""+clause+"""
        GROUP BY c.id), resumen AS (
            SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.moneda), '[]'::jsonb) AS totales
            FROM (
                SELECT moneda, SUM(total_generado-pagado)::text AS pendiente
                FROM compromisos_resumidos
                GROUP BY moneda HAVING SUM(total_generado-pagado)>0
            ) t
        )
        SELECT pagina.*,resumen.totales FROM resumen LEFT JOIN (
            SELECT * FROM compromisos_resumidos ORDER BY id LIMIT :page_size OFFSET :offset
        ) pagina ON true ORDER BY pagina.id
        """),{'s':space,'id':identifier,'offset':offset,'page_size':page_size}).mappings().all()
    items = [row for row in rows if row['id'] is not None]
    result = {
        'items': [public_commitment(row) for row in items[:100]],
        'next_offset': offset + 100 if len(items) > 100 and offset <= 99900 else None,
    }
    if identifier is None:
        result['totales'] = [
            {'moneda': row['moneda'], 'pendiente': format(Decimal(row['pendiente']), '.2f')}
            for row in rows[0]['totales']
        ]
    return result


def create_commitment(session,user,space,body):
    require_account(session,user,space,body.cuenta_id,write=True)
    params={'id':body.id,'s':space,'a':body.cuenta_id,'u':user,'n':body.nombre,'m':body.moneda,
            'i':body.importe,'c':body.categoria,'f':body.primer_vencimiento,'t':body.total_cuotas,'variable':body.variable,
            'indice':body.indice_ajuste,'sistema':body.sistema_amortizacion,'tna':body.tna}
    inserted=session.execute(text("""INSERT INTO public.compromisos
        (id,espacio_id,cuenta_id,usuario_id,nombre,moneda,importe,categoria,primer_vencimiento,total_cuotas,variable,indice_ajuste,sistema_amortizacion,tna)
        VALUES (:id,:s,:a,:u,:n,:m,:i,:c,:f,:t,:variable,:indice,:sistema,:tna) ON CONFLICT (id) DO NOTHING RETURNING id"""),params).scalar_one_or_none()
    row=session.execute(text('SELECT * FROM public.compromisos WHERE espacio_id=:s AND id=:id'),params).mappings().one_or_none()
    if (row is None or str(row['usuario_id'])!=str(user) or
        any(row[k]!=getattr(body,k) for k in ('cuenta_id','nombre','moneda','importe','categoria','primer_vencimiento','total_cuotas','variable','indice_ajuste','sistema_amortizacion','tna'))):
        raise HTTPException(409,'Identificador usado para otro compromiso',headers=NO_STORE)
    if inserted is not None and body.total_cuotas is None:
        today=commitment_local_date()
        if body.primer_vencimiento.replace(day=1)<today.replace(day=1):
            raise HTTPException(422,'El gasto mensual debe comenzar este mes o en uno futuro',headers=NO_STORE)
        seed_current_installment(session,space,row,today)
    elif inserted is not None and body.indice_ajuste is None:
        insert_finite_installments(session, space, body)
    return list_commitments(session,user,space,identifier=body.id)['items'][0]


def insert_finite_installments(session, space, body):
    amortization = None
    if body.sistema_amortizacion is not None:
        try:
            amortization = amortize(body.importe, body.tna, body.total_cuotas, body.sistema_amortizacion)
        except ValueError as error:
            raise HTTPException(422, str(error), headers=NO_STORE) from None

    rows = []
    for number in range(1, body.total_cuotas + 1):
        quote = amortization[number - 1] if amortization is not None else None
        rows.append({
            'id': uuid5(body.id, str(number)), 'space': space, 'commitment': body.id, 'number': number,
            'due': monthly_due(body.primer_vencimiento, number - 1), 'amount': quote.amount if quote else body.importe,
            'capital': quote.principal if quote else None, 'interest': quote.interest if quote else None,
            'balance': quote.balance if quote else None,
        })
    session.execute(text("""
        INSERT INTO public.cuotas
            (id, espacio_id, compromiso_id, numero, vencimiento, importe, capital, interes, saldo_capital)
        VALUES (:id, :space, :commitment, :number, :due, :amount, :capital, :interest, :balance)
    """), rows)


def require_commitment(session,user,space,identifier):
    require_member(session,user,space)
    if session.execute(text('SELECT id FROM public.compromisos WHERE espacio_id=:s AND id=:id'),
                       {'s':space,'id':identifier}).scalar_one_or_none() is None:
        raise HTTPException(404,'Compromiso no disponible',headers=NO_STORE)


def public_installment(row,day=None):
    day=day or commitment_local_date()
    paid=row['pagado'];skipped=row.get('no_aplica',False)
    remaining=Decimal(0) if skipped else row['importe']-paid
    return {key:str(row[key]) for key in ('id','espacio_id','compromiso_id')}|{
        'numero':row['numero'],'vencimiento':row['vencimiento'].isoformat(),
        'importe':format(row['importe'],'.2f'),'pagado':format(paid,'.2f'),'pendiente':format(remaining,'.2f'),
        'estimado':row.get('estimado',False),'version':row.get('version',1),
        'estado':'no_aplica' if skipped else 'borrador' if row.get('estimado',False) else 'pagada' if remaining==0 else 'parcial' if paid>0 else 'pendiente',
        'vencida':remaining>0 and row['vencimiento']<day} | (
            {'pendiente_ajuste': True} if row.get('pendiente_ajuste') else {}) | (
            {key: format(row[key], '.2f') for key in ('capital','interes','saldo_capital')}
            if row.get('capital') is not None else {})


def list_installments(session,user,space,identifier,offset=0):
    require_commitment(session,user,space,identifier)
    rows=session.execute(text("""SELECT q.*,COALESCE(SUM(g.importe),0) AS pagado FROM public.cuotas q
        LEFT JOIN public.pagos_cuota p ON p.espacio_id=q.espacio_id AND p.cuota_id=q.id
        LEFT JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE q.espacio_id=:s AND q.compromiso_id=:id GROUP BY q.id
        ORDER BY q.numero LIMIT 101 OFFSET :offset"""),{'s':space,'id':identifier,'offset':offset}).mappings().all()
    day = commitment_local_date()
    return {'items':[public_installment(row,day) for row in rows[:100]],'next_offset':offset+100 if len(rows)>100 else None}


def public_payment(row):
    return {key:str(row[key]) for key in ('id','espacio_id','cuota_id','cuenta_id')}|{
        'fecha':row['fecha'].isoformat(),'moneda':row['moneda'],'importe':format(row['importe'],'.2f')}


def require_installment(session,user,space,identifier,write=False):
    require_member(session,user,space,write=write)
    row=session.execute(text("""SELECT q.*,c.nombre,c.moneda,c.categoria,c.cuenta_id,
        c.variable,c.indice_ajuste,c.sistema_amortizacion
        FROM public.cuotas q JOIN public.compromisos c ON c.espacio_id=q.espacio_id AND c.id=q.compromiso_id
        WHERE q.espacio_id=:s AND q.id=:id"""),{'s':space,'id':identifier}).mappings().one_or_none()
    if row is None:raise HTTPException(404,'Cuota no disponible',headers=NO_STORE)
    return row


def pay_installment(session,user,space,identifier,body):
    identifier=UUID(str(identifier))
    row=require_installment(session,user,space,identifier,write=True)
    require_account(session,user,space,body.cuenta_id,write=True)
    # Un solo bloqueo transaccional por cuota serializa pagos sin conceder UPDATE a cuotas.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {'key':f'cuota:{space}:{identifier}'})
    row=require_installment(session,user,space,identifier,write=True)
    if row['no_aplica']:raise HTTPException(409,'La cuota no aplica',headers=NO_STORE)
    if row['pendiente_ajuste']:
        raise HTTPException(409,'Esperá el ajuste del índice antes de pagar',headers=NO_STORE)
    if row['estimado']:raise HTTPException(409,'Confirmar el monto estimado antes de pagar',headers=NO_STORE)
    params={'id':body.id,'s':space,'q':identifier,'a':body.cuenta_id,'u':user,'f':body.fecha,'i':body.importe}
    existing=session.execute(text("""SELECT p.cuota_id,g.* FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id WHERE p.espacio_id=:s AND p.id=:id"""),params).mappings().one_or_none()
    if existing is not None:
        if (existing['cuota_id']!=identifier or str(existing['usuario_id'])!=str(user) or
            any(existing[k]!=getattr(body,k) for k in ('cuenta_id','fecha','importe'))):
            raise HTTPException(409,'Identificador usado para otro pago',headers=NO_STORE)
        return public_payment(existing)
    paid=session.execute(text("""SELECT COALESCE(SUM(g.importe),0) FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE p.espacio_id=:s AND p.cuota_id=:q"""),params).scalar_one()
    if body.importe>row['importe']-paid:
        raise HTTPException(409,'El pago supera el saldo pendiente; actualiza las cuotas',headers=NO_STORE)
    params.update(d=('Cuota '+str(row['numero'])+' · '+row['nombre'])[:160],m=row['moneda'],c=row['categoria'])
    inserted=session.execute(text("""INSERT INTO public.gastos
        (id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe,categoria)
        VALUES (:id,:s,:a,:u,:f,:d,:m,:i,:c) ON CONFLICT (id) DO NOTHING RETURNING id"""),params).scalar_one_or_none()
    if inserted is None:raise HTTPException(409,'Identificador usado para otro gasto',headers=NO_STORE)
    session.execute(text('INSERT INTO public.pagos_cuota(id,espacio_id,cuota_id) VALUES (:id,:s,:q)'),params)
    return public_payment({'id':body.id,'espacio_id':space,'cuota_id':identifier,'cuenta_id':body.cuenta_id,
                           'fecha':body.fecha,'moneda':row['moneda'],'importe':body.importe})


def list_payments(session,user,space,identifier,offset=0):
    require_installment(session,user,space,identifier)
    rows=session.execute(text("""SELECT p.cuota_id,g.* FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE p.espacio_id=:s AND p.cuota_id=:q ORDER BY g.fecha DESC,g.id DESC LIMIT 101 OFFSET :offset"""),
        {'s':space,'q':identifier,'offset':offset}).mappings().all()
    return {'items':[public_payment(row) for row in rows[:100]],'next_offset':offset+100 if len(rows)>100 else None}


def commitment_payment_trend(session, user, space, identifier, day=None):
    require_commitment(session, user, space, identifier)
    month = (day or commitment_local_date()).replace(day=1)
    months = [monthly_due(month, offset) for offset in range(-11, 1)]
    totals = dict(session.execute(text("""
        SELECT to_char(g.fecha, 'YYYY-MM'), SUM(g.importe)
        FROM public.cuotas q
        JOIN public.pagos_cuota p ON p.espacio_id=q.espacio_id AND p.cuota_id=q.id
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE q.espacio_id=:space AND q.compromiso_id=:identifier
          AND g.anulado_en IS NULL AND g.fecha>=:start AND g.fecha<:end
        GROUP BY 1
    """), {'space': space, 'identifier': identifier, 'start': months[0],
           'end': monthly_due(month, 1)}).all())
    periods = [period.isoformat()[:7] for period in months]
    return {'items': [{'mes': period, 'total': format(totals.get(period, 0), '.2f')} for period in periods]}


@router.get('/spaces/{space}/commitments/{identifier}/payment-trend')
def get_commitment_payment_trend(space: UUID, identifier: UUID, request: Request, response: Response):
    return execute(request, response, space,
                   lambda session, user: commitment_payment_trend(session, user, space, identifier))


@router.post('/spaces/{space}/commitments')
def post_commitment(space:UUID,body:CommitmentInput,request:Request,response:Response):
    return execute(request,response,space,lambda s,u:create_commitment(s,u,space,body))


@router.get('/spaces/{space}/commitments')
def get_commitments(space:UUID,request:Request,response:Response,offset:int=Query(default=0,ge=0,le=100000)):
    return execute(request,response,space,lambda s,u:list_commitments(s,u,space,offset))


@router.get('/spaces/{space}/commitments/{identifier}/installments')
def get_installments(space:UUID,identifier:UUID,request:Request,response:Response,offset:int=Query(default=0,ge=0,le=100000)):
    return execute(request,response,space,lambda s,u:list_installments(s,u,space,identifier,offset))


@router.post('/spaces/{space}/installments/{identifier}/payments')
def post_payment(space:UUID,identifier:UUID,body:PaymentInput,request:Request,response:Response):
    return execute(request,response,space,lambda s,u:pay_installment(s,u,space,identifier,body))


@router.get('/spaces/{space}/installments/{identifier}/payments')
def get_payments(space:UUID,identifier:UUID,request:Request,response:Response,offset:int=Query(default=0,ge=0,le=100000)):
    return execute(request,response,space,lambda s,u:list_payments(s,u,space,identifier,offset))

def monthly_installments(session,user,space,month,offset=0,day=None):
    """Cuotas por mes de vencimiento; pagos acumulados aunque se paguen en otro mes."""
    if not isinstance(month,str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])',month) or month.startswith('0000'):
        raise HTTPException(422,'Mes invalido: usar AAAA-MM',headers=NO_STORE)
    year,number=map(int,month.split('-'))
    first=date(year,number,1);last=date(year,number,monthrange(year,number)[1])
    day=day or commitment_local_date()
    require_member(session,user,space)
    # Una sola sentencia: resumen y pagina comparten la misma fotografia de pagos.
    rows=session.execute(text("""WITH pagos AS (
        SELECT p.cuota_id,SUM(g.importe) AS pagado FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE p.espacio_id=:s GROUP BY p.cuota_id),
    del_mes AS (
        SELECT q.*,c.nombre,c.moneda,c.cuenta_id,c.categoria,COALESCE(p.pagado,0) AS pagado
        FROM public.cuotas q JOIN public.compromisos c ON c.espacio_id=q.espacio_id AND c.id=q.compromiso_id
        LEFT JOIN pagos p ON p.cuota_id=q.id
        WHERE q.espacio_id=:s AND q.vencimiento BETWEEN :first AND :last),
    totales AS (
        SELECT moneda,COUNT(*)::int AS cuotas,
            COUNT(*) FILTER (WHERE no_aplica)::int AS no_aplican,
            COUNT(*) FILTER (WHERE pagado=importe)::int AS cuotas_pagadas,
            COUNT(*) FILTER (WHERE estimado)::int AS borradores,
            SUM(CASE WHEN estimado THEN importe ELSE 0 END)::text AS estimado,
            SUM(CASE WHEN no_aplica THEN 0 ELSE importe END)::text AS total,SUM(pagado)::text AS pagado,
            SUM(CASE WHEN no_aplica THEN 0 ELSE importe-pagado END)::text AS pendiente,
            SUM(CASE WHEN NOT no_aplica AND vencimiento<:day THEN importe-pagado ELSE 0 END)::text AS vencido
        FROM del_mes GROUP BY moneda),
    resumen AS (
        SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.moneda),'[]'::jsonb) AS totales FROM totales t)
    SELECT pagina.*,resumen.totales,ultimo.fecha AS ultima_fecha_pago,ultimo.cuenta AS ultima_cuenta_pago
    FROM resumen LEFT JOIN (
        SELECT * FROM del_mes ORDER BY vencimiento,id LIMIT 101 OFFSET :offset
    ) pagina ON true
    LEFT JOIN LATERAL (
        SELECT g.fecha, a.nombre AS cuenta
        FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        JOIN public.cuentas a ON a.espacio_id=g.espacio_id AND a.id=g.cuenta_id
        WHERE p.espacio_id=:s AND p.cuota_id=pagina.id
        ORDER BY g.fecha DESC,g.id DESC LIMIT 1
    ) ultimo ON true
    ORDER BY pagina.vencimiento,pagina.id"""),
        {'s':space,'first':first,'last':last,'day':day,'offset':offset}).mappings().all()
    items=[row for row in rows if row['id'] is not None]
    totals=rows[0]['totales']
    # SUM de cuotas numeric(14,2) conserva escala; normalizar tambien el cero de CASE.
    for total in totals:
        for key in ('total','pagado','pendiente','vencido','estimado'):total[key]=format(Decimal(total[key]),'.2f')
    return {'mes':month,'totales':totals,'items':[
        public_installment(row,day)|{
            'nombre':row['nombre'],'moneda':row['moneda'],'cuenta_id':str(row['cuenta_id']),
            'categoria': row['categoria'],
        } | ({'ultimo_pago': {'fecha': row['ultima_fecha_pago'].isoformat(), 'cuenta': row['ultima_cuenta_pago']}}
             if row['ultima_fecha_pago'] is not None else {})
        for row in items[:100]],'next_offset':offset+100 if len(items)>100 else None}


@router.get('/spaces/{space}/installments')
def get_monthly_installments(space:UUID,request:Request,response:Response,
                             month:str=Query(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'),
                             offset:int=Query(default=0,ge=0,le=100000)):
    return execute(request,response,space,lambda s,u:monthly_installments(s,u,space,month,offset))


@router.get('/spaces/{space}/commitments/{identifier}')
def get_commitment(space:UUID,identifier:UUID,request:Request,response:Response):
    def read(session,user):
        require_commitment(session,user,space,identifier)
        return list_commitments(session,user,space,identifier=identifier)['items'][0]
    return execute(request,response,space,read)


def seed_current_installment(session,space,row,day):
    first=row['primer_vencimiento']
    offset=(day.year-first.year)*12+day.month-first.month
    if offset<0 or row['pausado']:return False
    amount=row['importe']
    if row['variable']:
        previous=session.execute(text('''SELECT importe FROM public.cuotas WHERE espacio_id=:s AND compromiso_id=:c
            AND periodo<:p AND NOT no_aplica ORDER BY periodo DESC LIMIT 1'''),
            {'s':space,'c':row['id'],'p':day.replace(day=1)}).scalar_one_or_none()
        if previous is not None:amount=previous
    inserted = session.execute(text("""INSERT INTO public.cuotas(id,espacio_id,compromiso_id,numero,vencimiento,importe,estimado)
        VALUES (:id,:s,:c,:n,:v,:i,:e) ON CONFLICT (espacio_id,compromiso_id,periodo) DO NOTHING RETURNING id"""),
        {'id':uuid5(UUID(str(row['id'])),str(offset+1)),'s':space,'c':row['id'],'n':offset+1,
         'v':monthly_due(first,offset),'i':amount,'e':row['variable']}).scalar_one_or_none()
    return inserted is not None


def open_installment_month(session, user, space, month):
    require_member(session, user, space, write=True)
    if month.startswith('0000'):
        raise HTTPException(422, 'Mes inválido', headers=NO_STORE)
    start = date.fromisoformat(month + '-01')
    end = start.replace(day=monthrange(start.year, start.month)[1])
    missing = session.execute(text("""
        SELECT c.* FROM public.compromisos c
        WHERE c.espacio_id=:space AND c.total_cuotas IS NULL AND NOT c.pausado
          AND c.primer_vencimiento<=:end AND NOT EXISTS (
            SELECT 1 FROM public.cuotas q
            WHERE q.espacio_id=c.espacio_id AND q.compromiso_id=c.id AND q.periodo=:start
          )
        ORDER BY c.id FOR UPDATE OF c
    """), {'space': space, 'start': start, 'end': end}).mappings().all()
    return {'mes': month, 'creadas': sum(seed_current_installment(session, space, row, start) for row in missing)}


@router.post('/spaces/{space}/installment-months/open')
def post_open_installment_month(space: UUID, request: Request, response: Response,
                                month: str = Query(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')):
    return execute(request, response, space, lambda session, user: open_installment_month(session, user, space, month))


class CommitmentPause(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    pausado:bool
    version:int=Field(ge=1,le=2147483646)


def pause_commitment(session,user,space,identifier,body):
    require_member(session,user,space,write=True)
    row=session.execute(text('SELECT * FROM public.compromisos WHERE espacio_id=:s AND id=:id FOR UPDATE'),
                        {'s':space,'id':identifier}).mappings().one_or_none()
    if row is None:raise HTTPException(404,'Compromiso no disponible',headers=NO_STORE)
    if row['total_cuotas'] is not None:raise HTTPException(409,'La pausa corresponde a gastos mensuales indefinidos',headers=NO_STORE)
    if body.version!=row['version']:
        if not(body.version==row['version']-1 and body.pausado==row['pausado']):
            raise HTTPException(409,'El compromiso cambio en otra sesion; actualiza la lista',headers=NO_STORE)
    elif body.pausado!=row['pausado']:
        session.execute(text('UPDATE public.compromisos SET pausado=:p,version=version+1 WHERE espacio_id=:s AND id=:id'),
                        {'p':body.pausado,'s':space,'id':identifier})
    if not body.pausado:
        seed_current_installment(session,space,dict(row)|{'pausado':False},
                                 commitment_local_date())
    return list_commitments(session,user,space,identifier=identifier)['items'][0]


@router.patch('/spaces/{space}/commitments/{identifier}')
def patch_commitment(space:UUID,identifier:UUID,body:CommitmentPause,request:Request,response:Response):
    return execute(request,response,space,lambda s,u:pause_commitment(s,u,space,identifier,body))


class ConfirmationInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:UUID
    importe:Decimal
    version:StrictInt=Field(ge=1,le=2147483646)

    @field_validator('id')
    @classmethod
    def identifier(cls,value):return IncomeInput.identifier(value)

    @field_validator('importe',mode='before')
    @classmethod
    def amount(cls,value):return IncomeInput.amount(value)


class ConfirmationsInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items:list[ConfirmationInput]=Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def unique(self):
        if len({item.id for item in self.items})!=len(self.items):raise ValueError('Cuotas repetidas')
        return self


def list_drafts(session,user,space,offset=0,month=None):
    require_member(session,user,space)
    if month and month.startswith('0000'):
        raise HTTPException(422, 'Mes inválido', headers=NO_STORE)
    period = date.fromisoformat(month + '-01') if month else None
    rows=session.execute(text("""WITH borradores AS (
        SELECT q.*,c.nombre,c.moneda,c.cuenta_id,0::numeric AS pagado FROM public.cuotas q
        JOIN public.compromisos c ON c.espacio_id=q.espacio_id AND c.id=q.compromiso_id
        WHERE q.espacio_id=:s AND q.estimado), filtrados AS (
        SELECT * FROM borradores WHERE CAST(:period AS date) IS NULL OR periodo=:period)
        SELECT pagina.*,resumen.borradores,resumen.borradores_total
        FROM (SELECT (SELECT COUNT(*)::int FROM filtrados) AS borradores,
                     (SELECT COUNT(*)::int FROM borradores) AS borradores_total) resumen
        LEFT JOIN (SELECT * FROM filtrados ORDER BY vencimiento,id LIMIT 101 OFFSET :offset) pagina ON true
        ORDER BY pagina.vencimiento,pagina.id"""),{'s':space,'offset':offset,'period':period}).mappings().all()
    items=[row for row in rows if row['id'] is not None]
    return {'borradores':rows[0]['borradores'],'items':[
        public_installment(row)|{'nombre':row['nombre'],'moneda':row['moneda'],'cuenta_id':str(row['cuenta_id'])}
        for row in items[:100]],'next_offset':offset+100 if len(items)>100 and offset<=99900 else None} | (
            {'borradores_total': rows[0]['borradores_total']} if month else {})


def confirm_installments(session,user,space,body):
    require_member(session,user,space,write=True)
    ordered=sorted(body.items,key=lambda item:str(item.id))
    # Mismo bloqueo de pagos, siempre en orden UUID para evitar interbloqueos entre lotes.
    for item in ordered:
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                        {'key':f'cuota:{space}:{item.id}'})
    for item in ordered:
        row=require_installment(session,user,space,item.id,write=True)
        if row['no_aplica']:raise HTTPException(409,'La cuota no aplica',headers=NO_STORE)
        if not row['estimado']:
            if row['version']==item.version+1 and row['importe']==item.importe:continue
            raise HTTPException(409,'La cuota ya fue confirmada o cambio en otra sesion',headers=NO_STORE)
        if row['version']!=item.version:raise HTTPException(409,'El estimado cambio en otra sesion',headers=NO_STORE)
        updated=session.execute(text("""UPDATE public.cuotas SET importe=:i,estimado=false,version=version+1
            WHERE espacio_id=:s AND id=:id AND estimado AND version=:v RETURNING id"""),
            {'i':item.importe,'s':space,'id':item.id,'v':item.version}).scalar_one_or_none()
        if updated is None:raise HTTPException(409,'La cuota cambio; revisar el lote',headers=NO_STORE)
    return {'confirmadas':[str(item.id) for item in body.items]}


@router.get('/spaces/{space}/installment-drafts')
def get_drafts(space:UUID,request:Request,response:Response,offset:int=Query(default=0,ge=0,le=100000),
               month: str | None = Query(default=None, pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')):
    return execute(request,response,space,lambda s,u:list_drafts(s,u,space,offset,month))


@router.post('/spaces/{space}/installment-confirmations')
def post_confirmations(space:UUID,body:ConfirmationsInput,request:Request,response:Response):
    return execute(request,response,space,lambda s,u:confirm_installments(s,u,space,body))


class SkipInstallmentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: StrictInt = Field(ge=1, le=2147483646)


class InstallmentAmountInput(SkipInstallmentInput):
    importe: Decimal

    @field_validator('importe', mode='before')
    @classmethod
    def amount(cls, value):
        return IncomeInput.amount(value)


def correct_installment_amount(session, user, space, identifier, body):
    require_member(session, user, space, write=True)
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
                    {'key': f'cuota:{space}:{identifier}'})
    row = require_installment(session, user, space, identifier, write=True)
    if (row['no_aplica'] or row['estimado'] or row['pendiente_ajuste'] or row['variable'] or
            row['indice_ajuste'] is not None or row['sistema_amortizacion'] is not None):
        raise HTTPException(409, 'El importe de esta cuota no se puede corregir', headers=NO_STORE)
    if row['importe'] == body.importe and row['version'] in (body.version, body.version + 1):
        return {'id': str(identifier), 'importe': format(body.importe, '.2f'), 'version': row['version']}
    if row['version'] != body.version:
        raise HTTPException(409, 'La cuota cambió en otra sesión', headers=NO_STORE)
    params = {'space': space, 'id': identifier, 'importe': body.importe, 'version': body.version}
    saved = session.execute(text("""
        UPDATE public.cuotas SET importe=:importe, version=version+1
        WHERE espacio_id=:space AND id=:id AND version=:version
        RETURNING version
    """), params).scalar_one_or_none()
    if saved is None:
        raise HTTPException(409, 'No se puede corregir una cuota con pagos', headers=NO_STORE)
    return {'id': str(identifier), 'importe': format(body.importe, '.2f'), 'version': saved}


@router.post('/spaces/{space}/installments/{identifier}/amount')
def post_installment_amount(space: UUID, identifier: UUID, body: InstallmentAmountInput,
                            request: Request, response: Response):
    return execute(request, response, space,
                   lambda session, user: correct_installment_amount(session, user, space, identifier, body))


def skip_installment(session, user, space, identifier, version):
    require_member(session, user, space, write=True)
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
                    {'key': f'cuota:{space}:{identifier}'})
    row = require_installment(session, user, space, identifier, write=True)
    if row['no_aplica'] and row['version'] == version + 1:
        return {'id': str(identifier), 'estado': 'no_aplica', 'version': row['version']}
    if row['pendiente_ajuste']:
        raise HTTPException(409,'Esperá el ajuste del índice antes de cambiar la cuota',headers=NO_STORE)
    if row['capital'] is not None:
        raise HTTPException(409, 'Las cuotas de un préstamo forman parte del plan de amortización', headers=NO_STORE)
    if row['no_aplica'] or row['version'] != version:
        raise HTTPException(409, 'La cuota cambió en otra sesión', headers=NO_STORE)
    saved = session.execute(text("""UPDATE public.cuotas
        SET no_aplica=true, estimado=false, version=version+1
        WHERE espacio_id=:s AND id=:id AND version=:v RETURNING version"""),
        {'s': space, 'id': identifier, 'v': version}).scalar_one_or_none()
    if saved is None:
        raise HTTPException(409, 'No se puede marcar una cuota con pagos como no aplicable', headers=NO_STORE)
    return {'id': str(identifier), 'estado': 'no_aplica', 'version': saved}


@router.post('/spaces/{space}/installments/{identifier}/skip')
def post_installment_skip(space: UUID, identifier: UUID, body: SkipInstallmentInput,
                          request: Request, response: Response):
    return execute(request, response, space,
                   lambda session, user: skip_installment(session, user, space, identifier, body.version))


def due_overview(session, user, space, today=None, *, include_expenses=False):
    require_member(session, user, space)
    today = today or commitment_local_date()
    week_end = today + timedelta(days=6-today.weekday())
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year,today.month)[1])
    rows = session.execute(text("""
        WITH amounts AS (
            SELECT q.id, q.numero, q.vencimiento, q.estimado, q.pendiente_ajuste, c.nombre, c.moneda,
                q.importe, COALESCE(pay.pagado,0) AS pagado
            FROM public.cuotas q
            JOIN public.compromisos c ON c.id=q.compromiso_id AND c.espacio_id=q.espacio_id
            LEFT JOIN LATERAL (
                SELECT SUM(g.importe) AS pagado FROM public.pagos_cuota p
                JOIN public.gastos g ON g.id=p.id AND g.espacio_id=p.espacio_id
                WHERE p.cuota_id=q.id AND p.espacio_id=q.espacio_id
            ) pay ON true
            WHERE q.espacio_id=:space AND NOT q.no_aplica
              AND q.vencimiento<=GREATEST(:week_end,:month_end)
        ), pending AS (
            SELECT id, numero, vencimiento, estimado, pendiente_ajuste, nombre, moneda,
                NULL::uuid AS cuenta_id, importe-pagado AS pendiente,
                CASE WHEN vencimiento<:today THEN 'vencidas'
                     WHEN vencimiento=:today THEN 'hoy' ELSE 'semana' END AS grupo
            FROM amounts WHERE importe>pagado AND vencimiento<=:week_end
            UNION ALL
            SELECT id, NULL, fecha_vencimiento, false, false, descripcion, moneda, cuenta_id, importe,
                CASE WHEN fecha_vencimiento<:today THEN 'vencidas' WHEN fecha_vencimiento=:today THEN 'hoy'
                     WHEN fecha_vencimiento<=:week_end THEN 'semana' ELSE 'proximos' END
            FROM public.gastos_pendientes WHERE :include_expenses AND espacio_id=:space AND gasto_id IS NULL
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY grupo ORDER BY vencimiento,id) AS rank
            FROM pending
        )
        SELECT 'total' AS type, grupo, moneda, COUNT(*) AS cantidad,
            SUM(pendiente) AS pendiente, NULL::numeric AS pagado, NULL::date AS vencimiento,
            NULL::uuid AS id, NULL::text AS nombre, NULL::int AS numero, NULL::boolean AS estimado,
            NULL::boolean AS pendiente_ajuste, NULL::uuid AS cuenta_id
        FROM pending GROUP BY grupo,moneda
        UNION ALL
        SELECT 'item', grupo, moneda, NULL, pendiente, NULL, vencimiento,id,nombre,numero,estimado,pendiente_ajuste,cuenta_id
        FROM ranked WHERE rank<=20
        UNION ALL
        SELECT 'mes', NULL, moneda, COUNT(*), SUM(importe-pagado), SUM(pagado), NULL,NULL,NULL,NULL,NULL,NULL,NULL
        FROM amounts WHERE vencimiento BETWEEN :month_start AND :month_end GROUP BY moneda
        ORDER BY type,grupo,moneda,vencimiento,id
    """), {'space':space,'today':today,'week_end':week_end,
           'month_start':month_start,'month_end':month_end,'include_expenses':include_expenses}).mappings()
    groups = {key:{'cantidad':0,'totales':[],'items':[]} for key in ('hoy','semana','vencidas')}
    month = []
    for row in rows:
        amount = format(row['pendiente'], '.2f')
        if row['type']=='mes':
            month.append({'moneda':row['moneda'],'pagado':format(row['pagado'],'.2f'),'pendiente':amount})
            continue
        group = groups.setdefault(row['grupo'], {'cantidad':0,'totales':[],'items':[]})
        if row['type']=='total':
            group['cantidad'] += row['cantidad']
            group['totales'].append({'moneda':row['moneda'],'pendiente':amount})
        else:
            group['items'].append({
                'id':str(row['id']),'nombre':row['nombre'],'numero':row['numero'],
                'moneda':row['moneda'],'pendiente':amount,'estimado':row['estimado'],
                'vencimiento':row['vencimiento'].isoformat(),
            } | ({'pendiente_ajuste': True} if row['pendiente_ajuste'] else {})
              | ({'cuenta_id': str(row['cuenta_id'])} if row['cuenta_id'] else {}))
    for group in groups.values():
        group['items'].sort(key=lambda item:(item['vencimiento'],item['id']))
    return {'fecha':today.isoformat(),'fin_semana':week_end.isoformat(),
            'grupos':groups,'resumen_mes':month}


def today_overview(session, user, space, today=None):
    today = today or commitment_local_date()
    result = due_overview(session, user, space, today, include_expenses=True)
    balance = account_balance(session, user, space)
    plan = get_plan(session, user, space)
    usage = expense_summary(session, user, space, day=today)
    debts = {row['moneda']: Decimal(row['pendiente'])
             for row in list_commitments(session, user, space, page_size=0)['totales']}
    pending = session.execute(text("""
        SELECT moneda, SUM(importe) FROM public.gastos_pendientes
        WHERE espacio_id=:space AND gasto_id IS NULL GROUP BY moneda
    """), {'space': space})
    for currency, amount in pending:
        debts[currency] = debts.get(currency, Decimal(0)) + amount
    return {
        **result,
        'saldos': balance,
        'deudas': [{'moneda': currency, 'pendiente': format(amount, '.2f')}
                   for currency, amount in sorted(debts.items()) if amount > 0],
        'presupuesto': {'limites': plan['datos']['limites'], 'gastos': usage['totales']},
    }


@router.get('/spaces/{space}/due-overview')
def get_due_overview(space: UUID, request: Request, response: Response):
    return execute(request,response,space,lambda session,user:today_overview(session,user,space))
