from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SuscripcionPush(Base):
    __tablename__ = 'suscripciones_push'
    __table_args__ = (
        UniqueConstraint('endpoint', name='uq_suscripciones_push_endpoint'),
        ForeignKeyConstraint(['usuario_id', 'espacio_id'],
                             ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
                             name='fk_suscripciones_push_miembro', ondelete='CASCADE'),
    )
    usuario_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    dispositivo_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
