"""Deudas fijas finitas: calendario mensual y pagos exactos sin doble gasto."""
from calendar import monthrange
from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID,uuid5
from zoneinfo import ZoneInfo
from fastapi import APIRouter,HTTPException,Request,Response,Query
from pydantic import BaseModel,ConfigDict,Field,StrictInt,field_validator,model_validator
from sqlalchemy import text
from app.accounts import execute,require_member,NO_STORE
from app.expenses import Category,require_account
from app.incomes import IncomeInput

router=APIRouter()


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

    @model_validator(mode='after')
    def date_range(self):
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
    total=row['importe']*row['total_cuotas'] if row['total_cuotas'] is not None else row['total_generado']
    return {key:str(row[key]) for key in ('id','espacio_id','cuenta_id')}|{
        'nombre':row['nombre'],'moneda':row['moneda'],'importe':format(row['importe'],'.2f'),
        'categoria':row['categoria'],'primer_vencimiento':row['primer_vencimiento'].isoformat(),
        'total_cuotas':row['total_cuotas'],'cuotas_pagadas':row['cuotas_pagadas'],
        'pausado':row['pausado'],'version':row['version'],'variable':row['variable'],
        'total':format(total,'.2f'),'pagado':format(paid,'.2f'),'pendiente':format(total-paid,'.2f'),
        'proximo_vencimiento':row['proximo_vencimiento'].isoformat() if row['proximo_vencimiento'] else None}


def list_commitments(session,user,space,offset=0,identifier=None):
    require_member(session,user,space)
    clause=' AND c.id=:id' if identifier is not None else ''
    rows=session.execute(text("""WITH pagos AS (
        SELECT p.cuota_id,SUM(g.importe) AS pagado FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE p.espacio_id=:s GROUP BY p.cuota_id)
        SELECT c.*,COALESCE(SUM(q.importe),0) AS total_generado,COUNT(*) FILTER (WHERE COALESCE(p.pagado,0)>=q.importe) AS cuotas_pagadas,
            COALESCE(SUM(p.pagado),0) AS pagado,
            MIN(q.vencimiento) FILTER (WHERE COALESCE(p.pagado,0)<q.importe) AS proximo_vencimiento
        FROM public.compromisos c LEFT JOIN public.cuotas q ON q.espacio_id=c.espacio_id AND q.compromiso_id=c.id
        LEFT JOIN pagos p ON p.cuota_id=q.id WHERE c.espacio_id=:s"""+clause+"""
        GROUP BY c.id ORDER BY c.id LIMIT 101 OFFSET :offset"""),{'s':space,'id':identifier,'offset':offset}).mappings().all()
    return {'items':[public_commitment(r) for r in rows[:100]],'next_offset':offset+100 if len(rows)>100 else None}


def create_commitment(session,user,space,body):
    require_account(session,user,space,body.cuenta_id,write=True)
    params={'id':body.id,'s':space,'a':body.cuenta_id,'u':user,'n':body.nombre,'m':body.moneda,
            'i':body.importe,'c':body.categoria,'f':body.primer_vencimiento,'t':body.total_cuotas,'variable':body.variable}
    inserted=session.execute(text("""INSERT INTO public.compromisos
        (id,espacio_id,cuenta_id,usuario_id,nombre,moneda,importe,categoria,primer_vencimiento,total_cuotas,variable)
        VALUES (:id,:s,:a,:u,:n,:m,:i,:c,:f,:t,:variable) ON CONFLICT (id) DO NOTHING RETURNING id"""),params).scalar_one_or_none()
    row=session.execute(text('SELECT * FROM public.compromisos WHERE espacio_id=:s AND id=:id'),params).mappings().one_or_none()
    if (row is None or str(row['usuario_id'])!=str(user) or
        any(row[k]!=getattr(body,k) for k in ('cuenta_id','nombre','moneda','importe','categoria','primer_vencimiento','total_cuotas','variable'))):
        raise HTTPException(409,'Identificador usado para otro compromiso',headers=NO_STORE)
    if inserted is not None and body.total_cuotas is None:
        today=datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
        if body.primer_vencimiento.replace(day=1)<today.replace(day=1):
            raise HTTPException(422,'El gasto mensual debe comenzar este mes o en uno futuro',headers=NO_STORE)
        seed_current_installment(session,space,row,today)
    elif inserted is not None:
        session.execute(text("""INSERT INTO public.cuotas(id,espacio_id,compromiso_id,numero,vencimiento,importe)
            VALUES (:id,:s,:c,:n,:v,:i)"""),[
            {'id':uuid5(body.id,str(n)),'s':space,'c':body.id,'n':n,'v':monthly_due(body.primer_vencimiento,n-1),'i':body.importe}
            for n in range(1,body.total_cuotas+1)])
    return list_commitments(session,user,space,identifier=body.id)['items'][0]


def require_commitment(session,user,space,identifier):
    require_member(session,user,space)
    if session.execute(text('SELECT id FROM public.compromisos WHERE espacio_id=:s AND id=:id'),
                       {'s':space,'id':identifier}).scalar_one_or_none() is None:
        raise HTTPException(404,'Compromiso no disponible',headers=NO_STORE)


def public_installment(row,day=None):
    day=day or datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    paid=row['pagado'];remaining=row['importe']-paid
    return {key:str(row[key]) for key in ('id','espacio_id','compromiso_id')}|{
        'numero':row['numero'],'vencimiento':row['vencimiento'].isoformat(),
        'importe':format(row['importe'],'.2f'),'pagado':format(paid,'.2f'),'pendiente':format(remaining,'.2f'),
        'estimado':row.get('estimado',False),'version':row.get('version',1),
        'estado':'borrador' if row.get('estimado',False) else 'pagada' if remaining==0 else 'parcial' if paid>0 else 'pendiente',
        'vencida':remaining>0 and row['vencimiento']<day}


def list_installments(session,user,space,identifier,offset=0):
    require_commitment(session,user,space,identifier)
    rows=session.execute(text("""SELECT q.*,COALESCE(SUM(g.importe),0) AS pagado FROM public.cuotas q
        LEFT JOIN public.pagos_cuota p ON p.espacio_id=q.espacio_id AND p.cuota_id=q.id
        LEFT JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE q.espacio_id=:s AND q.compromiso_id=:id GROUP BY q.id
        ORDER BY q.numero LIMIT 101 OFFSET :offset"""),{'s':space,'id':identifier,'offset':offset}).mappings().all()
    return {'items':[public_installment(row) for row in rows[:100]],'next_offset':offset+100 if len(rows)>100 else None}


def public_payment(row):
    return {key:str(row[key]) for key in ('id','espacio_id','cuota_id','cuenta_id')}|{
        'fecha':row['fecha'].isoformat(),'moneda':row['moneda'],'importe':format(row['importe'],'.2f')}


def require_installment(session,user,space,identifier,write=False):
    require_member(session,user,space,write=write)
    row=session.execute(text("""SELECT q.*,c.nombre,c.moneda,c.categoria,c.cuenta_id
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
    import re
    if not isinstance(month,str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])',month) or month.startswith('0000'):
        raise HTTPException(422,'Mes invalido: usar AAAA-MM',headers=NO_STORE)
    year,number=map(int,month.split('-'))
    first=date(year,number,1);last=date(year,number,monthrange(year,number)[1])
    day=day or datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    require_member(session,user,space)
    # Una sola sentencia: resumen y pagina comparten la misma fotografia de pagos.
    rows=session.execute(text("""WITH pagos AS (
        SELECT p.cuota_id,SUM(g.importe) AS pagado FROM public.pagos_cuota p
        JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
        WHERE p.espacio_id=:s GROUP BY p.cuota_id),
    del_mes AS (
        SELECT q.*,c.nombre,c.moneda,c.cuenta_id,COALESCE(p.pagado,0) AS pagado
        FROM public.cuotas q JOIN public.compromisos c ON c.espacio_id=q.espacio_id AND c.id=q.compromiso_id
        LEFT JOIN pagos p ON p.cuota_id=q.id
        WHERE q.espacio_id=:s AND q.vencimiento BETWEEN :first AND :last),
    totales AS (
        SELECT moneda,COUNT(*)::int AS cuotas,
            COUNT(*) FILTER (WHERE pagado=importe)::int AS cuotas_pagadas,
            COUNT(*) FILTER (WHERE estimado)::int AS borradores,
            SUM(CASE WHEN estimado THEN importe ELSE 0 END)::text AS estimado,
            SUM(importe)::text AS total,SUM(pagado)::text AS pagado,
            SUM(importe-pagado)::text AS pendiente,
            SUM(CASE WHEN vencimiento<:day THEN importe-pagado ELSE 0 END)::text AS vencido
        FROM del_mes GROUP BY moneda),
    resumen AS (
        SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.moneda),'[]'::jsonb) AS totales FROM totales t)
    SELECT pagina.*,resumen.totales FROM resumen LEFT JOIN (
        SELECT * FROM del_mes ORDER BY vencimiento,id LIMIT 101 OFFSET :offset
    ) pagina ON true ORDER BY pagina.vencimiento,pagina.id"""),
        {'s':space,'first':first,'last':last,'day':day,'offset':offset}).mappings().all()
    items=[row for row in rows if row['id'] is not None]
    totals=rows[0]['totales']
    # SUM de cuotas numeric(14,2) conserva escala; normalizar tambien el cero de CASE.
    for total in totals:
        for key in ('total','pagado','pendiente','vencido','estimado'):total[key]=format(Decimal(total[key]),'.2f')
    return {'mes':month,'totales':totals,'items':[
        public_installment(row,day)|{'nombre':row['nombre'],'moneda':row['moneda'],'cuenta_id':str(row['cuenta_id'])}
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
    if offset<0 or row['pausado']:return
    amount=row['importe']
    if row['variable']:
        previous=session.execute(text('''SELECT importe FROM public.cuotas WHERE espacio_id=:s AND compromiso_id=:c
            AND periodo<:p ORDER BY periodo DESC LIMIT 1'''),
            {'s':space,'c':row['id'],'p':day.replace(day=1)}).scalar_one_or_none()
        if previous is not None:amount=previous
    session.execute(text("""INSERT INTO public.cuotas(id,espacio_id,compromiso_id,numero,vencimiento,importe,estimado)
        VALUES (:id,:s,:c,:n,:v,:i,:e) ON CONFLICT (espacio_id,compromiso_id,periodo) DO NOTHING"""),
        {'id':uuid5(UUID(str(row['id'])),str(offset+1)),'s':space,'c':row['id'],'n':offset+1,
         'v':monthly_due(first,offset),'i':amount,'e':row['variable']})


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
                                 datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date())
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


def list_drafts(session,user,space,offset=0):
    require_member(session,user,space)
    rows=session.execute(text("""WITH borradores AS (
        SELECT q.*,c.nombre,c.moneda,c.cuenta_id,0::numeric AS pagado FROM public.cuotas q
        JOIN public.compromisos c ON c.espacio_id=q.espacio_id AND c.id=q.compromiso_id
        WHERE q.espacio_id=:s AND q.estimado)
        SELECT pagina.*,resumen.borradores FROM (SELECT COUNT(*)::int AS borradores FROM borradores) resumen
        LEFT JOIN (SELECT * FROM borradores ORDER BY vencimiento,id LIMIT 101 OFFSET :offset) pagina ON true
        ORDER BY pagina.vencimiento,pagina.id"""),{'s':space,'offset':offset}).mappings().all()
    items=[row for row in rows if row['id'] is not None]
    return {'borradores':rows[0]['borradores'],'items':[
        public_installment(row)|{'nombre':row['nombre'],'moneda':row['moneda'],'cuenta_id':str(row['cuenta_id'])}
        for row in items[:100]],'next_offset':offset+100 if len(items)>100 else None}


def confirm_installments(session,user,space,body):
    require_member(session,user,space,write=True)
    ordered=sorted(body.items,key=lambda item:str(item.id))
    # Mismo bloqueo de pagos, siempre en orden UUID para evitar interbloqueos entre lotes.
    for item in ordered:
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                        {'key':f'cuota:{space}:{item.id}'})
    for item in ordered:
        row=require_installment(session,user,space,item.id,write=True)
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
def get_drafts(space:UUID,request:Request,response:Response,offset:int=Query(default=0,ge=0,le=100000)):
    return execute(request,response,space,lambda s,u:list_drafts(s,u,space,offset))


@router.post('/spaces/{space}/installment-confirmations')
def post_confirmations(space:UUID,body:ConfirmationsInput,request:Request,response:Response):
    return execute(request,response,space,lambda s,u:confirm_installments(s,u,space,body))
