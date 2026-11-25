from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Gasto(Base):
    __tablename__ = 'gastos'
    __table_args__ = (
        UniqueConstraint('espacio_id','id',name='uq_gastos_espacio_id_id'),
        ForeignKeyConstraint(['espacio_id', 'cuenta_id'], ['public.cuentas.espacio_id', 'public.cuentas.id'],
                             name='fk_gastos_espacio_id_cuenta_id_cuentas'),
        CheckConstraint("moneda IN ('ARS','USD','EUR')", name='ck_gastos_moneda'),
        CheckConstraint('importe > 0 AND importe < 1000000000000', name='ck_gastos_importe'),
        CheckConstraint('char_length(btrim(descripcion)) BETWEEN 1 AND 160', name='ck_gastos_descripcion'),
        CheckConstraint("categoria IS NULL OR categoria IN ('alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros') OR categoria ~ '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'", name='ck_gastos_categoria'),
        CheckConstraint('nota IS NULL OR char_length(nota) BETWEEN 1 AND 500', name='ck_gastos_nota'),
        Index('ix_gastos_espacio_cuenta_fecha', 'espacio_id', 'cuenta_id', 'fecha'),
        Index('ix_gastos_espacio_fecha', 'espacio_id', 'fecha'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    cuenta_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.perfiles.usuario_id'), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    moneda: Mapped[str] = mapped_column(Text, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(Text, nullable=True)
