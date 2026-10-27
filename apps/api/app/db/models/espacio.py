from uuid import UUID, uuid4

from sqlalchemy import Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Espacio(Base):
    __tablename__ = "espacios"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
