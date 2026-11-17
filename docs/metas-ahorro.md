# Metas de ahorro

Completa el alcance acordado de ahorros: transferir, crear una meta, consultar el
objetivo y su progreso, aportar, retirar, editar, archivar y reactivar.

## Regla de producto

Cada meta vincula una cuenta y una moneda (ARS, USD o EUR). Su progreso usa el
saldo completo registrado de esa cuenta/moneda, incluido el dinero anterior a
la creación de la meta. Se recomienda una cuenta dedicada por objetivo.
Una restricción única parcial permite solo una meta activa por cuenta/moneda.
Varias metas pueden compartir cuenta si usan distintas monedas.

Saldo = ingresos - gastos + transferencias recibidas - enviadas.
Acumulado = máximo entre saldo y cero; faltante = máximo entre objetivo - acumulado y cero.
El progreso se trunca a una décima y se limita a 100%, conservando el acumulado
real aunque supere el objetivo. Alcanzada requiere acumulado >= objetivo.
Una fecha objetivo anterior a hoy (Buenos Aires) marca vencida si está activa e incompleta.

No hay aportes manuales que dupliquen transferencias. Preparar aporte/retiro
prellena el formulario de transferencias sin guardarlo: se elige la otra cuenta y
el importe y se revisa antes de registrar. Los gastos y retiros reducen el progreso.
Se mantienen las fechas futuras y saldos negativos del registro histórico existente.
Crear, editar, archivar o reactivar una meta no cambia movimientos ni saldos.

Editar permite nombre, objetivo y fecha opcional. Cuenta y moneda quedan fijas.
Archivar libera la combinación para otra meta y no mueve dinero. Las archivadas se
ocultan inicialmente; su progreso sigue siendo el saldo actual, no una foto histórica.
Reactivar requiere que no exista otra meta activa para esa cuenta y moneda.
El archivo sirve para conservar el registro sin permitir borrados accidentales.

## API, integridad y seguridad

- GET /spaces/{space}/savings-goals?offset=0&archived=false (true incluye archivadas).
- POST /spaces/{space}/savings-goals: id, cuenta_id, nombre, moneda, objetivo, fecha_objetivo.
- PATCH /spaces/{space}/savings-goals/{id}: nombre, objetivo, fecha_objetivo, archivada, version.
- BFF: mismas rutas bajo /api.

Objetivo positivo como string decimal, hasta 12 enteros y dos decimales. Fechas ISO
o null. El creador viene de identidad verificada. Owner/editor escriben, lector
consulta. RLS/FORCE y FK compuesta aíslan espacios. Runtime solo puede actualizar
campos editables y versión. El alta conserva UUID al reintentar. La edición usa
bloqueo y versión: un reintento idéntico de la edición inmediatamente anterior
devuelve lo guardado; una versión vieja con otros datos da 409. El índice único
protege tanto altas como reactivaciones concurrentes.

La lectura paginada calcula progreso en una sola consulta y agrega todos los
movimientos de las cuentas de esa página. DISTINCT en cuenta/moneda evita
multiplicar saldos cuando se muestran varias metas archivadas de la misma cuenta.
No se suman monedas ni se crean reservas bancarias reales.

## Criterios de aceptación y validación

- Crear, editar, archivar/reactivar y listar metas con permisos existentes.
- Objetivo, acumulado, faltante, fecha opcional, estado y progreso derivados.
- Refrescar progreso tras ingresos, gastos o transferencias sin perder borradores.
- Privacidad para importes/progreso y formularios de objetivos; tokens claros/oscuros.
- Preparar aporte/retiro sin sobrescribir una transferencia pendiente.
- Pruebas de dinero exacto, límites de progreso, idempotencia, conflictos, >100
  movimientos/metas, múltiples monedas, unicidad concurrente, RLS y FK.
- Migración 0015 antes del despliegue; no se modifican contratos de transferencias
  ni el esquema de ingresos/gastos existente.

## Siguiente etapa acordada

Después de ahorros: deudas/cuotas y obligaciones de gastos mensuales, distinguiendo
planificación de pagos y gastos reales. La especificación Piggo menciona obligaciones,
vencimientos, estados y recordatorios. El backlog aportado es:
https://aleharo.atlassian.net/jira/software/c/projects/CTAS/boards/34/backlog

El backlog CTAS ya pudo consultarse para la etapa de deudas. El alcance y la cobertura
parcial de CTAS-38, CTAS-43 y CTAS-45 se documentan en compromisos-fijos.md.
Esta entrega de ahorros no cierra esas stories.
