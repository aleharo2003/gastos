"""Alta propia con identidad validada; nunca recibe un usuario desde el cliente."""
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.auth import me
from app.db.unit_of_work import runtime_transaction

router = APIRouter()


@router.post('/personal-space')
def personal_space(request: Request, response: Response):
    identity = me(request, response)
    engine = getattr(request.app.state, 'runtime_engine', None)
    if engine is None:
        raise HTTPException(503, 'Base no disponible', headers={'Cache-Control': 'no-store'})
    try:
        with runtime_transaction(engine, usuario_id=identity['usuario_id']) as session:
            space = session.execute(text('SELECT public.crear_espacio_personal()')).scalar_one()
            name = session.execute(text('SELECT nombre FROM public.espacios WHERE id=:id'), {'id': space}).scalar_one()
        return {**identity, 'espacio_id': str(space), 'nombre': name}
    except SQLAlchemyError as error:
        status = 409 if getattr(getattr(error, 'orig', None), 'sqlstate', None) == '42501' else 503
        detail = 'El espacio requiere revision' if status == 409 else 'No se pudo preparar el espacio'
        raise HTTPException(status, detail, headers={'Cache-Control': 'no-store'}) from None
