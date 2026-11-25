from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CategoriaMovimiento(Base):
    __tablename__ = 'categorias_movimientos'
    __table_args__ = (
        CheckConstraint("tipo IN ('gasto','ingreso')", name='ck_categorias_tipo'),
        CheckConstraint('char_length(btrim(nombre)) BETWEEN 1 AND 80', name='ck_categorias_nombre'),
        CheckConstraint("color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name='ck_categorias_color'),
    )

    espacio_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('public.espacios.id', ondelete='CASCADE'), primary_key=True)
    tipo: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(Text)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False)
