from uuid import UUID

from sqlalchemy import Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Perfil(Base):
    __tablename__ = 'perfiles'

    # Mismo UUID de Auth; el alta confiable queda en ADR-0004. No generar otro UUID.
    usuario_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
