from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Cuenta(Base):
    """Estructura de aislamiento; los atributos financieros llegan con US-010."""
    __tablename__ = 'cuentas'
    __table_args__ = (
        UniqueConstraint('espacio_id', 'id', name='uq_cuentas_espacio_id_id'),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.espacios.id'), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
