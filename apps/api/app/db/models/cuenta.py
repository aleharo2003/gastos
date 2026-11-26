from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Cuenta(Base):
    """Cuenta de un espacio, con datos de apertura opcionales para cuentas anteriores."""
    __tablename__ = 'cuentas'
    __table_args__ = (
        UniqueConstraint('espacio_id', 'id', name='uq_cuentas_espacio_id_id'),
        CheckConstraint("""
            CASE WHEN tipo IS NULL THEN
                moneda IS NULL AND saldo_inicial IS NULL AND dia_cierre IS NULL
                AND dia_vencimiento IS NULL AND fecha_vencimiento IS NULL AND tasa_anual IS NULL
            ELSE
                tipo IN ('efectivo', 'banco', 'tarjeta_credito', 'billetera', 'inversion')
                AND moneda IS NOT NULL AND moneda IN ('ARS', 'USD', 'EUR')
                AND saldo_inicial IS NOT NULL AND saldo_inicial <> 'NaN'::numeric
                AND CASE WHEN tipo = 'tarjeta_credito'
                    THEN dia_cierre IS NOT NULL AND dia_cierre BETWEEN 1 AND 31
                         AND dia_vencimiento IS NOT NULL AND dia_vencimiento BETWEEN 1 AND 31
                    ELSE dia_cierre IS NULL AND dia_vencimiento IS NULL END
                AND CASE WHEN tipo = 'inversion'
                    THEN fecha_vencimiento IS NOT NULL AND tasa_anual IS NOT NULL
                         AND tasa_anual >= 0 AND tasa_anual <> 'NaN'::numeric AND saldo_inicial > 0
                    ELSE fecha_vencimiento IS NULL AND tasa_anual IS NULL END
            END
            """, name='ck_cuentas_datos'),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.espacios.id'), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    activa: Mapped[bool] = mapped_column(nullable=False, server_default=true())
    tipo: Mapped[str | None] = mapped_column(Text)
    moneda: Mapped[str | None] = mapped_column(String(3))
    saldo_inicial: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    dia_cierre: Mapped[int | None] = mapped_column(SmallInteger)
    dia_vencimiento: Mapped[int | None] = mapped_column(SmallInteger)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date)
    tasa_anual: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
