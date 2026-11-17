from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Boolean,CheckConstraint,Date,ForeignKey,ForeignKeyConstraint,Index,Integer,Numeric,Text,Uuid,text
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class MetaAhorro(Base):
    __tablename__='metas_ahorro'
    __table_args__=(
        ForeignKeyConstraint(['espacio_id','cuenta_id'],['public.cuentas.espacio_id','public.cuentas.id'],name='fk_metas_ahorro_espacio_id_cuenta_id_cuentas'),
        CheckConstraint("moneda IN ('ARS','USD','EUR')",name='ck_metas_ahorro_moneda'),
        CheckConstraint('objetivo > 0 AND objetivo < 1000000000000',name='ck_metas_ahorro_objetivo'),
        CheckConstraint('char_length(btrim(nombre)) BETWEEN 1 AND 160',name='ck_metas_ahorro_nombre'),
        CheckConstraint('version >= 0',name='ck_metas_ahorro_version'),
        Index('uq_metas_ahorro_activa','espacio_id','cuenta_id','moneda',unique=True,postgresql_where=text('NOT archivada')),
    )
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True)
    espacio_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    cuenta_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    usuario_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey('public.perfiles.usuario_id'),nullable=False)
    nombre:Mapped[str]=mapped_column(Text,nullable=False)
    moneda:Mapped[str]=mapped_column(Text,nullable=False)
    objetivo:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False)
    fecha_objetivo:Mapped[date|None]=mapped_column(Date,nullable=True)
    archivada:Mapped[bool]=mapped_column(Boolean,nullable=False)
    version:Mapped[int]=mapped_column(Integer,nullable=False)
