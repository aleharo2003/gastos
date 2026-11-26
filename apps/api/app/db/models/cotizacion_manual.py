from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CotizacionManual(Base):
    __tablename__ = 'cotizaciones_manuales'
    __table_args__ = (CheckConstraint('tasa > 0 AND tasa < 100000000', name='ck_cotizaciones_manuales_tasa'),)

    espacio_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey('public.espacios.id', ondelete='CASCADE'), primary_key=True,
    )
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    tasa: Mapped[Decimal] = mapped_column(Numeric(12, 4))
