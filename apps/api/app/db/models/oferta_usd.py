from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, ForeignKeyConstraint, Index, Numeric, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OfertaUsd(Base):
    __tablename__ = 'ofertas_usd'
    __table_args__ = (
        ForeignKeyConstraint(['espacio_id','venta_id'], ['public.ventas_usd.espacio_id','public.ventas_usd.id'],
                             name='fk_ofertas_usd_espacio_venta'),
        Index('ix_ofertas_usd_espacio_ronda', 'espacio_id','ronda'),
        Index('uq_ofertas_usd_aceptada', 'espacio_id','ronda', unique=True, postgresql_where=text("estado='aceptada'")),
    )

    espacio_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.espacios.id', ondelete='CASCADE'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    ronda: Mapped[UUID] = mapped_column(Uuid)
    contraparte: Mapped[str] = mapped_column(Text)
    fecha: Mapped[date] = mapped_column(Date)
    tasa: Mapped[Decimal] = mapped_column(Numeric(12,4))
    referencia: Mapped[Decimal | None] = mapped_column(Numeric(12,4))
    fecha_referencia: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Text, server_default='vigente')
    venta_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
