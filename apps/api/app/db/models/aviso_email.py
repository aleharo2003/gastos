from datetime import date
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvisoEmail(Base):
    __tablename__ = 'avisos_email'
    __table_args__ = (
        ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_avisos_email_miembro', ondelete='CASCADE',
        ),
        ForeignKeyConstraint(
            ['espacio_id', 'cuota_id'],
            ['public.cuotas.espacio_id', 'public.cuotas.id'],
            name='fk_avisos_email_cuota', ondelete='CASCADE',
        ),
        CheckConstraint("evento IN ('vencimiento', 'vencida')", name='ck_avisos_email_evento'),
    )

    usuario_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    cuota_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    evento: Mapped[str] = mapped_column(Text, primary_key=True)
    fecha_aviso: Mapped[date] = mapped_column(Date, primary_key=True)
