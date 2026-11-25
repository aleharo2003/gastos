from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, Index, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Ingreso(Base):
    __tablename__ = 'ingresos'
    __table_args__ = (
        ForeignKeyConstraint(['espacio_id', 'cuenta_id'], ['public.cuentas.espacio_id', 'public.cuentas.id'],
                             name='fk_ingresos_espacio_id_cuenta_id_cuentas'),
        CheckConstraint("moneda IN ('ARS','USD','EUR')", name='ck_ingresos_moneda'),
        CheckConstraint('importe > 0 AND importe < 1000000000000', name='ck_ingresos_importe'),
        CheckConstraint('char_length(btrim(descripcion)) BETWEEN 1 AND 160', name='ck_ingresos_descripcion'),
        CheckConstraint("categoria IS NULL OR categoria ~ '^[a-z0-9_-]{1,36}$'", name='ck_ingresos_categoria'),
        Index('ix_ingresos_espacio_cuenta_fecha', 'espacio_id', 'cuenta_id', 'fecha'),
        Index('ix_ingresos_espacio_fecha', 'espacio_id', 'fecha'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    cuenta_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.perfiles.usuario_id'), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    moneda: Mapped[str] = mapped_column(Text, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    categoria: Mapped[str | None] = mapped_column(Text, nullable=True)
