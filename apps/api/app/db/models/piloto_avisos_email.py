from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, SmallInteger, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PilotoAvisosEmail(Base):
    __tablename__ = 'piloto_avisos_email'
    __table_args__ = (
        CheckConstraint('id = 1', name='ck_piloto_avisos_email_unico'),
        ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_piloto_avisos_email_miembro', ondelete='CASCADE',
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    usuario_id: Mapped[UUID] = mapped_column(Uuid)
    espacio_id: Mapped[UUID] = mapped_column(Uuid)
