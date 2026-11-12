"""Configuración compartida de límites y proyecciones; nunca crea gastos."""
import json
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import text
from app.accounts import execute, require_member, NO_STORE
from app.expenses import AMOUNT

router=APIRouter()

class Money(BaseModel):
    model_config=ConfigDict(extra='forbid')
    moneda: Literal['ARS','USD']
    importe: Decimal
    @field_validator('importe',mode='before')
    @classmethod
    def amount(cls,value):
        if not isinstance(value,str) or not AMOUNT.fullmatch(value) or Decimal(value)<=0:
            raise ValueError('Importe positivo como texto, hasta dos decimales')
        return Decimal(value).quantize(Decimal('0.01'))

class Concept(Money):
    id: UUID
    concepto: str
    frecuencia: Literal['semana','mes']
    @field_validator('concepto')
    @classmethod
    def label(cls,value):
        value=value.strip()
        if not 1<=len(value)<=80 or any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError('Concepto de 1 a 80 caracteres sin controles')
        return value

class Limits(BaseModel):
    model_config=ConfigDict(extra='forbid')
    diario: Money | None = None
    semanal: Money | None = None

class Plan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    limites: Limits
    conceptos: list[Concept]=Field(max_length=40)
    @model_validator(mode='after')
    def unique(self):
        if len({row.id for row in self.conceptos})!=len(self.conceptos):raise ValueError('Conceptos duplicados')
        return self

class PlanUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version: int=Field(strict=True,ge=0,le=2147483646)
    datos: Plan

EMPTY={'limites':{'diario':None,'semanal':None},'conceptos':[]}

def get_plan(session,user,space):
    require_member(session,user,space)
    row=session.execute(text('SELECT version,datos FROM public.planes_gasto WHERE espacio_id=:s'),{'s':space}).mappings().one_or_none()
    return dict(row) if row else {'version':0,'datos':EMPTY}

def save_plan(session,user,space,body):
    require_member(session,user,space,write=True)
    # Create the empty configuration if absent, then lock it. Concurrent first
    # writers use the same row; a stale editor cannot overwrite another plan.
    session.execute(text('INSERT INTO public.planes_gasto(espacio_id,version,datos) VALUES (:s,0,CAST(:d AS jsonb)) ON CONFLICT (espacio_id) DO NOTHING'),{'s':space,'d':json.dumps(EMPTY)})
    row=session.execute(text('SELECT version,datos FROM public.planes_gasto WHERE espacio_id=:s FOR UPDATE'),{'s':space}).mappings().one()
    desired=body.datos.model_dump(mode='json')
    if row['datos']==desired:return dict(row)
    if row['version']!=body.version:raise HTTPException(409,'El presupuesto cambió en otra sesión',headers=NO_STORE)
    result=session.execute(text('UPDATE public.planes_gasto SET datos=CAST(:d AS jsonb),version=version+1 WHERE espacio_id=:s RETURNING version,datos'),{'s':space,'d':json.dumps(desired)}).mappings().one()
    return dict(result)

@router.get('/spaces/{space}/spending-plan')
def read_plan(space:UUID,request:Request,response:Response):
    return execute(request,response,space,lambda session,user:get_plan(session,user,space))

@router.post('/spaces/{space}/spending-plan')
def write_plan(space:UUID,body:PlanUpdate,request:Request,response:Response):
    return execute(request,response,space,lambda session,user:save_plan(session,user,space,body))
