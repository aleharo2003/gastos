from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Boolean,Computed,CheckConstraint,Date,ForeignKey,ForeignKeyConstraint,Index,Integer,Numeric,Text,UniqueConstraint,Uuid
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class Compromiso(Base):
    __tablename__='compromisos'
    __table_args__=(
        UniqueConstraint('espacio_id','id',name='uq_compromisos_espacio_id_id'),
        ForeignKeyConstraint(['espacio_id','cuenta_id'],['public.cuentas.espacio_id','public.cuentas.id'],name='fk_compromisos_espacio_id_cuenta_id_cuentas'),
        CheckConstraint("moneda IN ('ARS','USD','EUR')",name='ck_compromisos_moneda'),
        CheckConstraint('importe > 0 AND importe < 1000000000000',name='ck_compromisos_importe'),
        CheckConstraint('char_length(btrim(nombre)) BETWEEN 1 AND 160',name='ck_compromisos_nombre'),
        CheckConstraint('total_cuotas BETWEEN 1 AND 600',name='ck_compromisos_total_cuotas'),
        CheckConstraint('version >= 1',name='ck_compromisos_version'),
        CheckConstraint('NOT variable OR total_cuotas IS NULL',name='ck_compromisos_variable'),
        CheckConstraint("categoria IS NULL OR categoria IN ('alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros')",name='ck_compromisos_categoria'),
    )
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True)
    espacio_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    cuenta_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    usuario_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey('public.perfiles.usuario_id'),nullable=False)
    nombre:Mapped[str]=mapped_column(Text,nullable=False)
    moneda:Mapped[str]=mapped_column(Text,nullable=False)
    importe:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False)
    categoria:Mapped[str|None]=mapped_column(Text,nullable=True)
    primer_vencimiento:Mapped[date]=mapped_column(Date,nullable=False)
    total_cuotas:Mapped[int|None]=mapped_column(Integer,nullable=True)
    variable:Mapped[bool]=mapped_column(Boolean,nullable=False,server_default='false')
    pausado:Mapped[bool]=mapped_column(Boolean,nullable=False,server_default='false')
    version:Mapped[int]=mapped_column(Integer,nullable=False,server_default='1')


class Cuota(Base):
    __tablename__='cuotas'
    __table_args__=(
        UniqueConstraint('espacio_id','id',name='uq_cuotas_espacio_id_id'),
        UniqueConstraint('espacio_id','compromiso_id','numero',name='uq_cuotas_compromiso_numero'),
        UniqueConstraint('espacio_id','compromiso_id','periodo',name='uq_cuotas_compromiso_periodo'),
        ForeignKeyConstraint(['espacio_id','compromiso_id'],['public.compromisos.espacio_id','public.compromisos.id'],name='fk_cuotas_espacio_id_compromiso_id_compromisos'),
        CheckConstraint('numero BETWEEN 1 AND 119988',name='ck_cuotas_numero'),
        CheckConstraint('version >= 1',name='ck_cuotas_version'),
        CheckConstraint('importe > 0 AND importe < 1000000000000',name='ck_cuotas_importe'),
        Index('ix_cuotas_espacio_vencimiento','espacio_id','vencimiento'),
    )
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True)
    espacio_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    compromiso_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    no_aplica:Mapped[bool]=mapped_column(Boolean,nullable=False,server_default='false')
    estimado:Mapped[bool]=mapped_column(Boolean,nullable=False,server_default='false')
    version:Mapped[int]=mapped_column(Integer,nullable=False,server_default='1')
    numero:Mapped[int]=mapped_column(Integer,nullable=False)
    vencimiento:Mapped[date]=mapped_column(Date,nullable=False)
    periodo:Mapped[date]=mapped_column(Date,Computed("vencimiento - (EXTRACT(day FROM vencimiento)::integer - 1)",persisted=True),nullable=False)
    importe:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False)


class PagoCuota(Base):
    __tablename__='pagos_cuota'
    __table_args__=(
        ForeignKeyConstraint(['espacio_id','id'],['public.gastos.espacio_id','public.gastos.id'],name='fk_pagos_cuota_espacio_id_id_gastos'),
        ForeignKeyConstraint(['espacio_id','cuota_id'],['public.cuotas.espacio_id','public.cuotas.id'],name='fk_pagos_cuota_espacio_id_cuota_id_cuotas'),
        Index('ix_pagos_cuota_espacio_cuota','espacio_id','cuota_id'),
    )
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True)
    espacio_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    cuota_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
