# Ingresos y saldos por cuenta

Desde Gastos, elegí una cuenta o Todas las cuentas. El panel Saldo muestra ingresos,
gastos y saldo de todo el historial, separados en ARS, USD y EUR. Incluye fechas futuras.
No aplica cotización ni suma monedas distintas. Un saldo negativo se muestra en rojo
y no impide registrar movimientos.

Abrí «Ingresos · Registrar y consultar» para registrar fecha, descripción, moneda e
importe. Desde Todas las cuentas es obligatorio elegir la cuenta receptora. Se admiten
hasta 12 enteros y dos decimales positivos, sin separador de miles. El historial tiene
páginas de 100; los saldos usan todos los movimientos, incluso los no cargados en pantalla.

Los ingresos se suman y los gastos existentes se restan automáticamente. Editar un gasto
recalcula el saldo sin volver a descontarlo. Actualizar saldo permite refrescar cambios
hechos en otra sesión. Los importes del panel y del historial respetan el ojo de privacidad.

## Empezar con dinero existente

Puede registrarse un ingreso «Saldo inicial». Esta primera versión no distingue
contablemente saldo inicial de otros ingresos. Si ya existen gastos, el importe inicial
debe tenerlos en cuenta para que el saldo final coincida con el dinero real.

Ejemplo: hay gastos por ARS 20.000 y el banco hoy tiene ARS 80.000. Registrar ARS 100.000
como saldo inicial deja ARS 80.000 disponibles. Registrar solo ARS 80.000 dejaría ARS 60.000.
No se deduce un saldo inicial de los datos existentes ni del presupuesto proyectado.

## Contratos

- POST /spaces/{space}/accounts/{account}/incomes
- GET /spaces/{space}/accounts/{account}/incomes?offset=0
- GET /spaces/{space}/incomes?offset=0
- GET /spaces/{space}/account-balance?account={account} (cuenta opcional)

El BFF expone las mismas rutas bajo /api. Se requiere identidad verificada. La API
aplica membresía y RLS con FORCE: owner/editor escriben, lector consulta, ajenos no
acceden. La FK (espacio_id, cuenta_id) impide cuentas de otro espacio. Solo se concede
SELECT/INSERT al runtime. Los ingresos no tienen edición ni eliminación en este incremento.

Cada alta lleva un UUID del cliente. Reintentar el mismo contenido con el mismo UUID
devuelve el registro existente; cambiar su contenido produce 409. La interfaz conserva
UUID y cuenta al reintentar una respuesta perdida. Cambiar de cuenta protege formularios
pendientes; cambiar de sección conserva las instancias.

Los saldos se obtienen en una sola consulta SQL mediante UNION ALL y SUM numeric,
sin límites de página ni acumulación mutable. Los importes viajan como strings decimales.
No se crean gastos, ingresos recurrentes o transferencias a partir del presupuesto.

## Validación

El CI existente ejecuta pruebas de API, BFF y Angular; PostgreSQL incorpora
check_incomes.py con altas concurrentes, idempotencia, decimales, saldos negativos,
monedas separadas, más de 100 ingresos, edición de gastos, cuentas vacías, roles,
aislamiento SQL, FK compuesta y revocación de membresía. El inventario cerrado de RLS
incluye ingresos. Alembic verifica correspondencia del modelo con la migración 0013.

Esta sesión no dispone de entorno local de ejecución: los resultados ejecutados se
informan en el PR. La revisión visual en móvil y escritorio sigue siendo manual.
