"""Exportación de datos de negocio del espacio en CSV."""
import csv
import io
import json
from decimal import Decimal
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import text

from app.accounts import NO_STORE, execute
from app.movement_categories import list_categories

router = APIRouter()
MAX_CSV_BYTES = 24 * 1024 * 1024
FILENAME = 'piggo-datos.zip'

# Include only explicitly portable fields. Never use SELECT * in an export.
TABLES = (
    ('cuentas', 'id nombre activa tipo moneda saldo_inicial dia_cierre dia_vencimiento fecha_vencimiento tasa_anual', 'id'),
    ('ingresos', 'id cuenta_id fecha descripcion moneda importe categoria anulado_en', 'fecha, id'),
    ('gastos', 'id cuenta_id fecha descripcion moneda importe categoria nota anulado_en '
     'fecha_devengamiento fecha_vencimiento tasa_pago fuente_tasa_pago', 'fecha, id'),
    ('gastos_pendientes', 'id cuenta_id fecha_devengamiento fecha_vencimiento descripcion moneda importe categoria nota gasto_id',
     'fecha_vencimiento, id'),
    ('transferencias', 'id origen_id destino_id fecha descripcion moneda importe anulado_en', 'fecha, id'),
    ('compromisos', 'id cuenta_id nombre moneda importe categoria primer_vencimiento total_cuotas '
     'sistema_amortizacion tna indice_ajuste variable pausado version', 'id'),
    ('cuotas', 'id compromiso_id numero vencimiento periodo importe no_aplica estimado '
     'pendiente_ajuste version capital interes saldo_capital', 'compromiso_id, numero'),
    ('pagos_cuota', 'id cuota_id', 'cuota_id, id'),
    ('variaciones_indice', 'indice periodo variacion', 'indice, periodo'),
    ('metas_ahorro', 'id cuenta_id nombre moneda objetivo fecha_objetivo archivada version', 'id'),
    ('ofertas_usd', 'id ronda fecha contraparte tasa referencia fecha_referencia estado venta_id', 'fecha,id'),
    ('ventas_usd', 'id fecha contraparte origen_id destino_id usd ars tasa referencia fecha_referencia', 'fecha,id'),
    ('preferencias_cotizacion', 'tipo', 'tipo'),
    ('cotizaciones_manuales', 'fecha tasa', 'fecha'),
    ('planes_gasto', 'version datos historial_categoria', 'version'),
    ('comprobantes', 'id gasto_id nombre mime bytes sha256', 'gasto_id, id'),
)
PREFERENCES = 'canal dias_anticipacion hora_local vencimientos vencidas resumen_semanal'
GUIDE = """
Exportación de Piggo, versión de formato 1.

Los CSV usan UTF-8 con BOM, coma como delimitador y punto decimal.
Si Excel interpreta mal las columnas, importar desde Datos > Desde texto/CSV
y seleccionar UTF-8 y separador coma. Para conservar montos con muchos dígitos,
importar las columnas de importes como texto.

Cada archivo representa una entidad. Los identificadores vinculan los CSV.
En pagos_cuota, id también identifica el gasto correspondiente. Una fecha en
anulado_en identifica un movimiento anulado que se conserva como parte del historial.
Piggo antepone un apóstrofo al texto que Excel podría interpretar como fórmula.

Comprobantes incluye los metadatos, sin el contenido de los adjuntos.
El archivo cubre datos del espacio y preferencias del titular. Quedan fuera
las credenciales, los datos técnicos de notificaciones y los ajustes guardados
solamente en el navegador. Las ventas de USD se incluyen en ventas_usd.csv.
""".lstrip()


def csv_value(value):
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if isinstance(value, str) and (value.startswith(('\t', '\n', '\r')) or value.lstrip()[:1] in ('=', '+', '-', '@', '＝', '＋', '－', '＠')):
        return "'" + value
    return value


class CsvSink:
    def __init__(self):
        self.remaining = MAX_CSV_BYTES
        self.output = None

    def write(self, value):
        data = value.encode('utf-8')
        self.remaining -= len(data)
        if self.remaining < 0:
            raise HTTPException(413, 'La exportación supera el tamaño permitido', headers=NO_STORE)
        self.output.write(data)

    def add(self, archive, name, columns, rows):
        with archive.open(name + '.csv', 'w') as self.output:
            self.write('\ufeff')
            writer = csv.writer(self)
            writer.writerow(columns)
            writer.writerows([csv_value(row[field]) for field in columns] for row in rows)


def build_export(session, user, space):
    owner = session.execute(text("""
        SELECT 1 FROM public.miembros_espacio
        WHERE espacio_id=:space AND usuario_id=:user AND rol='owner'
    """), {'space': space, 'user': user}).scalar_one_or_none()
    if owner is None:
        raise HTTPException(403, 'Solo el titular puede exportar los datos del espacio', headers=NO_STORE)

    content = io.BytesIO()
    csv_sink = CsvSink()
    with ZipFile(content, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('LEEME.txt', GUIDE)
        items = list_categories(session, user, space)['items']
        csv_sink.add(archive, 'categorias', ('id', 'tipo', 'nombre', 'activa', 'color'), items)
        for table, column_names, order in TABLES:
            columns = column_names.split()
            query = text(f"SELECT {', '.join(columns)} FROM public.{table} WHERE espacio_id=:space ORDER BY {order}")
            with session.execute(query, {'space': space}, execution_options={'yield_per': 500}) as result:
                csv_sink.add(archive, table, columns, result.mappings())
        columns = PREFERENCES.split()
        prefs = session.execute(text(f"""
            SELECT {', '.join(columns)} FROM public.preferencias_avisos
            WHERE espacio_id=:space AND usuario_id=:user
        """), {'space': space, 'user': user}).mappings()
        csv_sink.add(archive, 'preferencias_avisos', columns, prefs)
    return content.getvalue()


@router.get('/spaces/{space}/export', response_class=Response)
def export_space(space: UUID, request: Request, response: Response):
    content = execute(request, response, space, lambda session, user: build_export(session, user, space),
                      repeatable_read=True)
    return Response(content, media_type='application/zip', headers=NO_STORE | {
        'Content-Disposition': f'attachment; filename="{FILENAME}"',
        'X-Content-Type-Options': 'nosniff',
    })
