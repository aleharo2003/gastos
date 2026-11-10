from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, Text, Uuid, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Comprobante(Base):
    __tablename__='comprobantes'
    __table_args__=(
        ForeignKeyConstraint(['espacio_id','gasto_id'],['public.gastos.espacio_id','public.gastos.id'],name='fk_comprobantes_espacio_id_gasto_id_gastos'),
        CheckConstraint('bytes > 0 AND bytes <= 5242880',name='ck_comprobantes_bytes'),
        CheckConstraint("mime IN ('image/jpeg','image/png','application/pdf')",name='ck_comprobantes_mime'),
        Index('ix_comprobantes_espacio_gasto','espacio_id','gasto_id'),
    )
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True)
    espacio_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    gasto_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    nombre:Mapped[str]=mapped_column(Text,nullable=False)
    mime:Mapped[str]=mapped_column(Text,nullable=False)
    bytes:Mapped[int]=mapped_column(Integer,nullable=False)
    sha256:Mapped[str]=mapped_column(Text,nullable=False)
    ruta:Mapped[str]=mapped_column(Text,nullable=False)
