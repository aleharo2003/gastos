"""Categorías iniciales de movimientos."""
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import text

from app.accounts import NO_STORE, execute, require_member

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

Kind = Literal['gasto', 'ingreso']
CUSTOM_KEY = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
EXPENSE_OPTIONS = '|'.join(key for key, _ in DEFAULT_CATEGORIES['gasto']) + '|' + CUSTOM_KEY
ExpenseKey = Annotated[str, StringConstraints(pattern=r'^(?:' + EXPENSE_OPTIONS + r')$')]
ExpenseFilter = Annotated[str, StringConstraints(pattern=r'^(?:' + EXPENSE_OPTIONS + r'|sin_categoria)$')]

class CategoryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    nombre: str
    color: Annotated[str, StringConstraints(pattern=r'^#[0-9a-f]{6}$')] | None = None

    @field_validator('nombre')
    @classmethod
    def clean_name(cls, value):
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('Nombre inválido')
        name = ' '.join(value.split())
        if not 1 <= len(name) <= 80:
            raise ValueError('Nombre de 1 a 80 caracteres')
        return name


class CategoryCreate(CategoryInput):
    id: Annotated[str, StringConstraints(pattern='^' + CUSTOM_KEY + '$')]
    tipo: Kind


class CategoryUpdate(CategoryInput):
    activa: bool


def category_rows(session, space):
    categories = {
        (kind, category): {'id': category, 'tipo': kind, 'nombre': name, 'activa': True, 'color': None}
        for kind, entries in DEFAULT_CATEGORIES.items()
        for category, name in entries
    }
    rows = session.execute(text('''
        SELECT id, tipo, nombre, activa, color FROM public.categorias_movimientos WHERE espacio_id=:space
    '''), {'space': space}).mappings()
    categories.update({(row['tipo'], row['id']): dict(row) for row in rows})
    return categories


def list_categories(session, user, space):
    require_member(session, user, space)
    categories = category_rows(session, space).values()
    return {'items': sorted(categories, key=lambda row: (row['tipo'], not row['activa'], row['nombre'].casefold(), row['id']))}


def lock_catalog(session, space):
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('movement_categories:' || CAST(:space AS text), 0))"),
                    {'space': space})


def require_active_category(session, space, kind, category):
    if category is None:
        return
    lock_catalog(session, space)
    item = category_rows(session, space).get((kind, category))
    if not item or not item['activa']:
        raise HTTPException(422, 'Elegí una categoría activa de este espacio', headers=NO_STORE)


def normalized_name(value):
    return ''.join(value.casefold().split())


def save_category(session, user, space, kind, category, body, *, create):
    require_member(session, user, space, write=True)
    lock_catalog(session, space)
    categories = category_rows(session, space)
    current = categories.get((kind, category))
    if create and current:
        if current['nombre'] == body.nombre and current['color'] == body.color:
            return current
        raise HTTPException(409, 'Identificador de categoría en uso', headers=NO_STORE)
    if not create and not current:
        raise HTTPException(404, 'Categoría no disponible', headers=NO_STORE)
    if create and len(categories) >= 100:
        raise HTTPException(422, 'Se alcanzó el límite de categorías', headers=NO_STORE)
    name = normalized_name(body.nombre)
    if any(key != (kind, category) and key[0] == kind and normalized_name(row['nombre']) == name
           for key, row in categories.items()):
        raise HTTPException(409, 'Ya existe una categoría con ese nombre', headers=NO_STORE)

    row = {'id': category, 'tipo': kind, 'nombre': body.nombre,
           'color': body.color, 'activa': True if create else body.activa}
    session.execute(text('''
        INSERT INTO public.categorias_movimientos (espacio_id, id, tipo, nombre, color, activa)
        VALUES (:space, :id, :tipo, :nombre, :color, :activa)
        ON CONFLICT (espacio_id, tipo, id) DO UPDATE
        SET nombre=EXCLUDED.nombre, color=EXCLUDED.color, activa=EXCLUDED.activa
    '''), row | {'space': space})
    return row


@router.get('/spaces/{space}/categories')
def get_categories(space: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: list_categories(session, user, space))


@router.post('/spaces/{space}/categories')
def post_category(space: UUID, body: CategoryCreate, request: Request, response: Response):
    return execute(request, response, space,
                   lambda session, user: save_category(session, user, space, body.tipo, body.id, body, create=True))


@router.patch('/spaces/{space}/categories/{kind}/{category}')
def patch_category(space: UUID, kind: Kind, category: str, body: CategoryUpdate, request: Request, response: Response):
    if not re.fullmatch(r'[a-z0-9_-]{1,36}', category):
        raise HTTPException(422, 'Identificador inválido', headers=NO_STORE)
    return execute(request, response, space,
                   lambda session, user: save_category(session, user, space, kind, category, body, create=False))
