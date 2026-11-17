# Gastos variables y confirmacion de estimados

Incremento de CTAS-39 y CTAS-47, basado en el PR #33 que ya integra #34 y #35.
La activacion del ejecutor de test sigue los pasos de gastos-mensuales-fijos.md.

## Regla de producto

Un gasto variable es mensual y sin cantidad final de cuotas. El importe inicial
positivo sirve de estimado para el primer mes. Cada nueva cuota toma el importe
de la cuota del mes anterior. Si no hubo cuota en ese mes (por ejemplo, una pausa),
usa la ultima cuota anterior disponible; sin historial usa el importe inicial.
Se conserva siempre la marca de monto estimado hasta confirmarlo, incluso si el
valor anterior ya estaba confirmado. No se copian pagos ni comprobantes.

El generador diario de 0017 se actualiza en 0018; su funcion conserva nombre, firma,
propietario y permisos existentes mediante CREATE OR REPLACE. No se agrega acceso
directo a tablas al rol app_jobs. La reactivacion usa la misma regla de estimacion.

El estado borrador se distingue de pendiente y pago parcial. El resumen mensual
incluye estimados en comprometido/pendiente y muestra su cantidad e importe por
moneda. Son proyecciones, no pagos ni gastos reales.
Las cuotas estimadas vencidas siguen mostrando vencimiento y marca de estimado.
Los recordatorios de producto siguen pendientes.

## Revision y confirmacion

Al entrar al espacio aparece un aviso con el total de cuotas por confirmar,
incluidos otros meses y paginas. La seccion Deudas muestra las cuotas en borrador,
con fecha, moneda, importe editable y seleccion para confirmar hasta 100 por lote.
La paginacion no limita el contador global.

Se puede confirmar sin cambiar el importe. Todo el lote se valida y guarda en una
transaccion. Un conflicto o una cuota no disponible revierte el lote entero.
Se usa version por cuota y bloqueo transaccional compartido con el pago, en orden
UUID para evitar interbloqueos entre lotes. Reintentar los mismos datos de la
confirmacion inmediatamente anterior devuelve los mismos IDs confirmados.
Los importes y versiones del formulario se conservan tras un error.
Descartar y actualizar vuelve a leer los valores del servidor.

Confirmar convierte el borrador en pendiente y no descuenta dinero. Antes de
confirmar no se permite pagar. Despues se reutilizan los pagos parciales/completos
y los comprobantes existentes. La cuota confirmada queda inmutable: no se puede
cambiar el monto despues de pagar ni desde UPDATE de runtime.
Corregir confirmaciones requiere un flujo posterior de anulacion/revision; no esta
incluido en este incremento.

## Contratos y seguridad

- POST commitments incorpora variable booleano opcional (por defecto false).
  variable true requiere total_cuotas null.
- GET /spaces/{space}/installment-drafts?offset=0 devuelve borradores, items y next_offset.
- POST /spaces/{space}/installment-confirmations recibe items con id, importe y version.
  Respuesta: confirmadas, IDs en el orden solicitado.
- BFF expone las mismas rutas bajo /api; sin cache.
- Las cuotas incorporan estimado y version; los totales mensuales incorporan
  borradores y estimado (importe provisional incluido en el pendiente).
- Owner/editor confirman; lector consulta. UUID y claves compuestas preservan espacios.
- Dinero decimal en texto; no se aceptan floats, cero, duplicados ni lotes vacios.
- Migracion 0018 antes de desplegar API, BFF y web. No requiere otro secreto de jobs.

RLS limita UPDATE de cuotas a borrador sin pagos que pasa a confirmado. Runtime
solo recibe UPDATE de importe/estimado/version; no puede cambiar fecha, plan o espacio.
El pago vuelve a leer la cuota despues de tomar su bloqueo para respetar una
confirmacion concurrente.

## Validacion y pendientes

Pruebas de API, BFF, Angular y PostgreSQL: validacion estricta, mas de 100 borradores,
contador global, versionado, reintentos concurrentes, conflicto de montos, rollback
del lote, conservacion de formularios, lector/aislamiento, copia del importe previo,
bloqueo de pagos de estimados e inmutabilidad posterior.
Consultar CI del PR para resultados ejecutados.
Revision visual y ejecucion remota programada se verifican por separado.
No incluye recordatorios, intereses/indexacion ni marcar una cuota como no aplica.
