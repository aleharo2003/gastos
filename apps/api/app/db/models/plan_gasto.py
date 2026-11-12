from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

class PlanGasto(Base):
    __tablename__='planes_gasto'
    __table_args__=(
        CheckConstraint('version >= 0',name='ck_planes_gasto_version'),
        CheckConstraint("jsonb_typeof(datos) = 'object' AND octet_length(datos::text) <= 32768",name='ck_planes_gasto_datos'),
    )
    espacio_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey('public.espacios.id'),primary_key=True)
    version:Mapped[int]=mapped_column(Integer,nullable=False)
    datos:Mapped[dict]=mapped_column(JSONB,nullable=False)
