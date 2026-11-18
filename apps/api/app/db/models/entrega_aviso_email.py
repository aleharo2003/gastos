from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKeyConstraint, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntregaAvisoEmail(Base):
    __tablename__ = 'entregas_avisos_email'
    __table_args__ = (
        ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_entregas_avisos_email_miembro', ondelete='CASCADE',
        ),
        UniqueConstraint('intento_id', name='uq_entregas_avisos_email_intento'),
        CheckConstraint("estado IN ('reservada', 'aceptada', 'reintento', 'incierta')", name='ck_entregas_avisos_email_estado'),
        CheckConstraint("(estado = 'aceptada' AND referencia_proveedor IS NOT NULL AND char_length(btrim(referencia_proveedor)) BETWEEN 1 AND 255) OR (estado <> 'aceptada' AND referencia_proveedor IS NULL)", name='ck_entregas_avisos_email_referencia'),
    )

    usuario_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    fecha_aviso: Mapped[date] = mapped_column(Date, primary_key=True)
    intento_id: Mapped[UUID] = mapped_column(Uuid)
    reservado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(Text)
    referencia_proveedor: Mapped[str | None] = mapped_column(Text, nullable=True)
