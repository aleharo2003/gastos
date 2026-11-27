from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnvioResumenSemanal(Base):
    __tablename__ = 'envios_resumen_semanal'
    __table_args__ = (
        CheckConstraint("estado IN ('reservado','aceptada','reintento','incierta')", name='ck_envios_resumen_semanal_estado'),
        UniqueConstraint('intento_id', name='uq_envios_resumen_semanal_intento'),
        ForeignKeyConstraint(['usuario_id', 'espacio_id'],
                             ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
                             name='fk_envios_resumen_semanal_miembro', ondelete='CASCADE'),
    )

    usuario_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    semana: Mapped[date] = mapped_column(Date, primary_key=True)
    intento_id: Mapped[UUID] = mapped_column(Uuid)
    estado: Mapped[str] = mapped_column(Text)
