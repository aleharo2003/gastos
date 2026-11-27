from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, Text, Uuid, UniqueConstraint, text
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
        Index('ix_gastos_espacio_lote', 'espacio_id', 'lote_importacion',
              postgresql_where=text('lote_importacion IS NOT NULL')),
        Index('uq_gastos_importacion_vigente', 'espacio_id', 'clave_importacion', unique=True,
              postgresql_where=text('clave_importacion IS NOT NULL AND anulado_en IS NULL')),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    cuenta_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.perfiles.usuario_id'), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_devengamiento: Mapped[date | None] = mapped_column(Date)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    moneda: Mapped[str] = mapped_column(Text, nullable=False)
    tasa_pago: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    fuente_tasa_pago: Mapped[str | None] = mapped_column(Text)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lote_importacion: Mapped[UUID | None] = mapped_column(Uuid)
    clave_importacion: Mapped[UUID | None] = mapped_column(Uuid)
    importado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(Text, nullable=True)


class GastoPendiente(Base):
    __tablename__ = 'gastos_pendientes'
    __table_args__ = (
        ForeignKeyConstraint(['espacio_id', 'cuenta_id'], ['public.cuentas.espacio_id', 'public.cuentas.id']),
        ForeignKeyConstraint(['espacio_id', 'gasto_id'], ['public.gastos.espacio_id', 'public.gastos.id']),
        CheckConstraint('gasto_id IS NULL OR gasto_id=id', name='ck_gastos_pendientes_pago'),
        CheckConstraint("moneda IN ('ARS','USD','EUR')", name='ck_gastos_pendientes_moneda'),
        CheckConstraint('importe > 0 AND importe < 1000000000000', name='ck_gastos_pendientes_importe'),
        CheckConstraint('char_length(btrim(descripcion)) BETWEEN 1 AND 160', name='ck_gastos_pendientes_descripcion'),
        CheckConstraint('nota IS NULL OR char_length(nota) BETWEEN 1 AND 500', name='ck_gastos_pendientes_nota'),
        Index('ix_gastos_pendientes_espacio_vencimiento', 'espacio_id', 'fecha_vencimiento', 'id',
              postgresql_where=text('gasto_id IS NULL')),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid)
    cuenta_id: Mapped[UUID] = mapped_column(Uuid)
    usuario_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.perfiles.usuario_id'))
    fecha_devengamiento: Mapped[date | None] = mapped_column(Date)
    fecha_vencimiento: Mapped[date] = mapped_column(Date)
    descripcion: Mapped[str] = mapped_column(Text)
    moneda: Mapped[str] = mapped_column(Text)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    categoria: Mapped[str | None] = mapped_column(Text)
    nota: Mapped[str | None] = mapped_column(Text)
    gasto_id: Mapped[UUID | None] = mapped_column(Uuid)
