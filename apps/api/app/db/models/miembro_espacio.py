from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MiembroEspacio(Base):
    __tablename__ = "miembros_espacio"
    __table_args__ = (
        CheckConstraint("rol IN ('owner', 'editor', 'lector')",
                        name="ck_miembros_espacio_rol"),
        Index("ix_miembros_espacio_espacio_id", "espacio_id"),
    )

    # El perfil de usuario se incorporará en el siguiente paso de identidad.
    # Por ahora se usan UUID ficticios exclusivamente en pruebas.
    usuario_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("public.espacios.id"), primary_key=True,
    )
    rol: Mapped[str] = mapped_column(Text, nullable=False)
