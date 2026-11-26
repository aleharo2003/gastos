from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CotizacionMercado(Base):
    __tablename__ = 'cotizaciones_mercado'

    tipo: Mapped[str] = mapped_column(Text, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    tasa: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    actualizada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PreferenciaCotizacion(Base):
    __tablename__ = 'preferencias_cotizacion'

    espacio_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.espacios.id', ondelete='CASCADE'), primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
