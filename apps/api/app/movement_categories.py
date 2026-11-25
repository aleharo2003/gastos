"""Categorías iniciales de movimientos."""
from uuid import UUID

from fastapi import APIRouter, Request, Response

from app.accounts import execute, require_member

router = APIRouter()

DEFAULT_CATEGORIES = {
    'gasto': (
        ('alimentos', 'Alimentos'), ('transporte', 'Transporte'),
        ('vivienda', 'Vivienda'), ('servicios', 'Servicios'),
        ('salud', 'Salud'), ('educacion', 'Educación'), ('ocio', 'Ocio'),
        ('impuestos', 'Impuestos'), ('auto', 'Auto'), ('bancario', 'Bancario'),
        ('ropa', 'Ropa'), ('otros', 'Otros'),
    ),
    'ingreso': (
        ('sueldo', 'Sueldo'), ('honorarios', 'Honorarios'), ('venta', 'Venta'),
        ('regalo', 'Regalo'), ('reintegro', 'Reintegro'), ('otros_ingresos', 'Otros ingresos'),
    ),
}


def list_categories(session, user, space):
    require_member(session, user, space)
    return {'items': [
        {'id': category, 'tipo': kind, 'nombre': name, 'activa': True}
        for kind, entries in DEFAULT_CATEGORIES.items()
        for category, name in entries
    ]}


@router.get('/spaces/{space}/categories')
def get_categories(space: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: list_categories(session, user, space))
