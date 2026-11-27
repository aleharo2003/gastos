from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKeyConstraint, Numeric, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvisoPresupuesto(Base):
    __tablename__ = 'avisos_presupuesto'
    __table_args__ = (
        ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_avisos_presupuesto_miembro', ondelete='CASCADE',
        ),
        UniqueConstraint('usuario_id', 'espacio_id', 'periodo', 'desde', 'categoria',
                         name='uq_avisos_presupuesto_periodo'),
        CheckConstraint("periodo IN ('diario','semanal','mensual') AND moneda IN ('ARS','USD') AND exceso>0",
                        name='ck_avisos_presupuesto_datos'),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    usuario_id: Mapped[UUID] = mapped_column(Uuid)
    espacio_id: Mapped[UUID] = mapped_column(Uuid)
    periodo: Mapped[str] = mapped_column(Text)
    desde: Mapped[date] = mapped_column(Date)
    categoria: Mapped[str] = mapped_column(Text)
    moneda: Mapped[str] = mapped_column(Text)
    exceso: Mapped[Decimal] = mapped_column(Numeric)
    leida: Mapped[bool] = mapped_column(Boolean, server_default='false')
