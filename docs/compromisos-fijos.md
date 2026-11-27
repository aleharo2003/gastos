# Deudas fijas con cuotas finitas

Primer incremento de deudas, después de completar ahorros (PR #32).

## Alcance y stories

Se contrastó con el backlog CTAS el 17 de noviembre de 2026. Cobertura parcial:

| Story | Incluido | Pendiente |
| --- | --- | --- |
| [CTAS-38](https://aleharo.atlassian.net/browse/CTAS-38) | Compromiso fijo con cuenta, categoría opcional, moneda, primer vencimiento y cantidad de cuotas | Compromisos indefinidos y pausa |
| [CTAS-43](https://aleharo.atlassian.net/browse/CTAS-43) | Listado y detalle, cuotas pagadas/total, importe pagado, restante y próximo vencimiento | Resumen mensual global |
| [CTAS-45](https://aleharo.atlassian.net/browse/CTAS-45) | Pago completo/parcial con fecha y cuenta, gasto único, saldo restante y comprobantes | Conversión de monedas y notificaciones |

Estas stories no quedan terminadas con este incremento. Las obligaciones variables,
indexadas, créditos con intereses, generación mensual automática, pausa y confirmación
por lotes requieren PRs posteriores (CTAS-39 a CTAS-42, CTAS-44 y CTAS-46 a CTAS-49).
La generación programada también depende de CTAS-59.

## Reglas

Un plan tiene de 1 a 600 cuotas mensuales de importe fijo, en ARS, USD o EUR.
Se genera el calendario finito completo en la misma transacción de creación.
Crear la deuda no registra un gasto ni descuenta dinero.

Los vencimientos conservan el día original: 31 de enero, último día de febrero,
31 de marzo. El fin de mes no desplaza los meses siguientes.
El estado vencida se calcula al consultar, con la fecha de Buenos Aires; no hay
un proceso programado que cambie estados.

Cada pago genera exactamente un gasto y un enlace a su cuota, atómicamente.
Ejemplo: cuota de 100000 ARS y pago de 30000 ARS dejan 70000 ARS pendientes
y descuentan solo 30000 ARS de la cuenta elegida.
La cuota cuenta como pagada cuando su saldo llega a cero. No se admite sobrepago.
Se puede pagar desde otra cuenta del mismo espacio, en la moneda de la deuda.
No se realiza conversión de monedas; los saldos negativos siguen las reglas existentes.

Los totales se calculan desde todos los pagos, sin limitarse a la página visible.
El gasto integra Movimientos, balances, presupuestos y progreso de ahorros, usando
los mecanismos existentes. No se debe registrar nuevamente el mismo pago como gasto.
Los comprobantes usan el almacenamiento privado y las rutas de recibos del gasto.

El plan y los pagos son inmutables en esta entrega. No se admite editar un pago desde
Gastos; la API y una política restrictiva de PostgreSQL protegen el vínculo.
Correcciones, anulaciones, edición y cancelación de deudas necesitan un flujo posterior
que preserve el historial.

## Contratos y seguridad

- GET/POST /spaces/{space}/commitments.
- GET /spaces/{space}/commitments/{id}/installments.
- GET/POST /spaces/{space}/installments/{id}/payments.
- BFF: mismas rutas bajo /api. Páginas de 100 con next_offset.

Dinero decimal en texto, aritmética Decimal/BigInt y columnas numeric; sin floats.
Owner/editor crean y pagan; lector consulta. RLS/FORCE, contexto transaccional
y claves foráneas compuestas aíslan espacios. Runtime recibe SELECT e INSERT
en las tablas nuevas, sin UPDATE ni DELETE.

La creación y cada pago conservan su UUID al reintentar con los mismos datos.
Reutilizar un UUID para otra operación devuelve 409. Un bloqueo transaccional por
cuota serializa pagos simultáneos y vuelve a calcular el saldo antes de insertar.
La migración 0016 debe ejecutarse antes de desplegar los servicios.

## Marcado diario de vencimientos

En test, GitHub Actions ejecuta el [proceso diario](proceso-diario.md) a las
01:29 de Buenos Aires. La tarea usa `JOBS_DATABASE_URL` del rol dedicado, guarda la
fecha del primer marcado para cada cuota confirmada con saldo pendiente y
se puede ejecutar manualmente desde Actions. La migración 0051 concede el
permiso al rol de tareas ya habilitado para generar cuotas.

Una cuota que vence hoy entra al proceso a partir del día siguiente en
Argentina. Los pagos parciales conservan el saldo vencido. Al pagar toda la
cuota, Piggo la muestra como pagada y conserva la fecha de marcado en el
historial exportable. La pantalla calcula el vencimiento por fecha aun si
una ejecución se demora.

## Validación

Pruebas de API, BFF y Angular; PostgreSQL comprueba reintentos concurrentes,
sobrepago concurrente, rollback, permisos, aislamiento, inmutabilidad,
calendario de fin de mes y paginación de más de 100 cuotas/pagos.
Consultar los resultados ejecutados en el CI del PR.
La revisión visual móvil/escritorio y la verificación del SHA desplegado son independientes.
