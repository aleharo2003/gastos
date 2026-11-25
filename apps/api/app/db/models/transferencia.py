from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Transferencia(Base):
    __tablename__ = 'transferencias'
    __table_args__ = (
        ForeignKeyConstraint(['espacio_id', 'origen_id'], ['public.cuentas.espacio_id', 'public.cuentas.id'],
                             name='fk_transferencias_espacio_id_origen_id_cuentas'),
        ForeignKeyConstraint(['espacio_id', 'destino_id'], ['public.cuentas.espacio_id', 'public.cuentas.id'],
                             name='fk_transferencias_espacio_id_destino_id_cuentas'),
        CheckConstraint('origen_id <> destino_id', name='ck_transferencias_cuentas_distintas'),
        CheckConstraint("moneda IN ('ARS','USD','EUR')", name='ck_transferencias_moneda'),
        CheckConstraint('importe > 0 AND importe < 1000000000000', name='ck_transferencias_importe'),
        CheckConstraint('char_length(btrim(descripcion)) BETWEEN 1 AND 160', name='ck_transferencias_descripcion'),
        Index('ix_transferencias_espacio_origen_fecha', 'espacio_id', 'origen_id', 'fecha'),
        Index('ix_transferencias_espacio_destino_fecha', 'espacio_id', 'destino_id', 'fecha'),
        Index('ix_transferencias_espacio_fecha', 'espacio_id', 'fecha'),
        Index('ix_transferencias_espacio_lote', 'espacio_id', 'lote_importacion',
              postgresql_where=text('lote_importacion IS NOT NULL')),
        Index('uq_transferencias_importacion_vigente', 'espacio_id', 'clave_importacion', unique=True,
              postgresql_where=text('clave_importacion IS NOT NULL AND anulado_en IS NULL')),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    origen_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    destino_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.perfiles.usuario_id'), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    moneda: Mapped[str] = mapped_column(Text, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    lote_importacion: Mapped[UUID | None] = mapped_column(Uuid)
    clave_importacion: Mapped[UUID | None] = mapped_column(Uuid)
    importado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

