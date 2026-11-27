from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Computed, Date, DateTime, ForeignKeyConstraint, Index, Numeric, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VentaUsd(Base):
    __tablename__ = 'ventas_usd'
    __table_args__ = (
        CheckConstraint("tipo IN ('venta','compra')", name='ck_ventas_usd_tipo'),
        UniqueConstraint('espacio_id','id', name='uq_ventas_usd_espacio_id'),
        ForeignKeyConstraint(['espacio_id','origen_id'], ['public.cuentas.espacio_id','public.cuentas.id'], name='fk_ventas_usd_origen_cuentas'),
        ForeignKeyConstraint(['espacio_id','destino_id'], ['public.cuentas.espacio_id','public.cuentas.id'], name='fk_ventas_usd_destino_cuentas'),
        Index('ix_ventas_usd_espacio_fecha', 'espacio_id', 'fecha', 'id'),
    )

    espacio_id: Mapped[UUID] = mapped_column(Uuid)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    origen_id: Mapped[UUID] = mapped_column(Uuid)
    destino_id: Mapped[UUID] = mapped_column(Uuid)
    fecha: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(Text, server_default='venta')
    contraparte: Mapped[str] = mapped_column(Text)
    usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    ars: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tasa: Mapped[Decimal | None] = mapped_column(Numeric(), Computed('round(ars / NULLIF(usd,0), 4)', persisted=True))
    referencia: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    fecha_referencia: Mapped[date | None] = mapped_column(Date)
    registrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
