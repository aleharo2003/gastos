from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VariacionIndice(Base):
    __tablename__ = 'variaciones_indice'
    __table_args__ = (
        CheckConstraint("length(btrim(indice)) BETWEEN 1 AND 80", name='ck_variaciones_indice_nombre'),
        CheckConstraint(
            "periodo BETWEEN DATE '0001-01-01' AND DATE '9999-12-01' AND EXTRACT(DAY FROM periodo) = 1",
            name='ck_variaciones_indice_periodo',
        ),
        CheckConstraint(
            "variacion > -100 AND variacion <= 999999.9999", name='ck_variaciones_indice_variacion',
        ),
    )

    espacio_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey('public.espacios.id', ondelete='CASCADE'), primary_key=True,
    )
    indice: Mapped[str] = mapped_column(Text, primary_key=True)
    periodo: Mapped[date] = mapped_column(Date, primary_key=True)
    variacion: Mapped[Decimal] = mapped_column(Numeric(10, 4))
