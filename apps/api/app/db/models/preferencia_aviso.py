from datetime import time
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Integer, Text, Time, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PreferenciaAviso(Base):
    __tablename__ = 'preferencias_avisos'
    __table_args__ = (
        ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_preferencias_avisos_miembro', ondelete='CASCADE',
        ),
        CheckConstraint("canal IN ('ninguno', 'email', 'push')", name='ck_preferencias_avisos_canal'),
        CheckConstraint("dias_anticipacion BETWEEN 0 AND 30", name='ck_preferencias_avisos_anticipacion'),
        CheckConstraint("hora_local < TIME '24:00' AND EXTRACT(SECOND FROM hora_local) = 0", name='ck_preferencias_avisos_hora'),
    )

    usuario_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    espacio_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    canal: Mapped[str] = mapped_column(Text)
    dias_anticipacion: Mapped[int] = mapped_column(Integer)
    hora_local: Mapped[time] = mapped_column(Time)
    vencimientos: Mapped[bool] = mapped_column(Boolean)
    vencidas: Mapped[bool] = mapped_column(Boolean)
    resumen_semanal: Mapped[bool] = mapped_column(Boolean)
    exceso_presupuesto: Mapped[bool] = mapped_column(Boolean, server_default='false')
