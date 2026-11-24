"""Consulta y guarda las preferencias privadas de recordatorios del miembro autenticado."""
from datetime import time
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy import text

from app.accounts import execute, require_member

router = APIRouter()
DEFAULTS = {
    'canal': 'ninguno', 'dias_anticipacion': 3, 'hora_local': '09:00',
    'vencimientos': True, 'vencidas': False, 'resumen_semanal': False,
}


class ReminderPreferences(BaseModel):
    model_config = ConfigDict(extra='forbid')

    canal: Literal['ninguno', 'email', 'push']
    dias_anticipacion: StrictInt = Field(ge=0, le=30)
    hora_local: time
    vencimientos: StrictBool
    vencidas: StrictBool
    resumen_semanal: StrictBool

    @field_validator('hora_local', mode='before')
    @classmethod
    def local_time(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'([01][0-9]|2[0-3]):[0-5][0-9]', value):
            raise ValueError('Indicá un horario local en formato HH:MM')
        return time.fromisoformat(value)


def public_preferences(row):
    return dict(row) | {'hora_local': row['hora_local'].isoformat(timespec='minutes')}


def read_preferences(session, user, space):
    require_member(session, user, space)
    row = session.execute(text("""
        SELECT canal, dias_anticipacion, hora_local, vencimientos, vencidas, resumen_semanal
        FROM public.preferencias_avisos WHERE usuario_id = :user AND espacio_id = :space
    """), {'user': user, 'space': space}).mappings().one_or_none()
    return public_preferences(row) if row is not None else DEFAULTS.copy()


def save_preferences(session, user, space, body):
    # El rol lector también puede configurar sus propios avisos.
    require_member(session, user, space)
    row = session.execute(text("""
        INSERT INTO public.preferencias_avisos
            (usuario_id, espacio_id, canal, dias_anticipacion, hora_local, vencimientos, vencidas, resumen_semanal)
        VALUES (:user, :space, :canal, :dias_anticipacion, :hora_local, :vencimientos, :vencidas, :resumen_semanal)
        ON CONFLICT (usuario_id, espacio_id) DO UPDATE SET
            canal = EXCLUDED.canal, dias_anticipacion = EXCLUDED.dias_anticipacion, hora_local = EXCLUDED.hora_local,
            vencimientos = EXCLUDED.vencimientos, vencidas = EXCLUDED.vencidas, resumen_semanal = EXCLUDED.resumen_semanal
        RETURNING canal, dias_anticipacion, hora_local, vencimientos, vencidas, resumen_semanal
    """), {'user': user, 'space': space, **body.model_dump()}).mappings().one()
    return public_preferences(row)


@router.get('/spaces/{space}/reminder-preferences')
def get_preferences(space: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: read_preferences(session, user, space))


@router.put('/spaces/{space}/reminder-preferences')
def put_preferences(space: UUID, body: ReminderPreferences, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: save_preferences(session, user, space, body))
