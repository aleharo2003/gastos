# Ahorros y transferencias

Primera entrega de ahorros: transferencias entre cuentas del mismo espacio.
Las metas de ahorro y sus porcentajes de progreso corresponden al siguiente incremento.

## Uso

1. Crear una cuenta llamada Ahorros desde Cuentas, si hace falta.
2. Abrir Ahorros, elegir origen y destino, fecha, descripción, moneda e importe.
3. Registrar la transferencia. Para retirar ahorros, invertir origen y destino.
4. Consultar el saldo desde Gastos o «Ver saldo» después de guardar.

Ejemplo: banco ARS 500.000 y ahorros ARS 0. Transferir ARS 100.000 deja
ARS 400.000 y ARS 100.000. El total sigue siendo ARS 500.000.
No se registra ingreso ni gasto y el consumo del presupuesto no cambia.

Las cuentas existentes admiten varias monedas: cada transferencia indica una sola
moneda compartida por ambos lados (ARS, USD o EUR). No hay conversión ni comisiones.
El saldo histórico incluye fechas futuras y permite negativos, igual que los gastos.
No constituye una reserva bancaria ni verifica fondos reales; es un registro manual.

El historial permite filtrar por cualquiera de las dos cuentas antes de paginar.
Hay 100 filas por página; los saldos se calculan con todas. El ojo oculta importes.
Cambiar de sección conserva el formulario. Hay un botón para cargar más cuentas.
Si una cuenta de una fila no está en la página cargada, se muestra su identificador
hasta cargarla. No hay clasificación automática de cuentas por su nombre.

## Integridad y permisos

Un registro en transferencias representa los dos lados; la transacción existente
confirma o revierte la operación completa. Dos FK compuestas por espacio protegen
origen y destino. Una restricción prohíbe transferir a la misma cuenta. El UUID del
cliente permite reintentos idempotentes; otro contenido con el mismo UUID produce 409.
Los importes se transportan como texto decimal y se agregan con numeric en PostgreSQL.

Owner/editor registran y lector consulta. RLS y FORCE aíslan espacios y el creador se
valida contra el contexto autenticado. Runtime solo tiene SELECT/INSERT.
No se editan ni eliminan transferencias en este incremento. Una devolución real se
registra como otra transferencia en sentido inverso, con su descripción y fecha.

## Contratos

- POST /spaces/{space}/transfers
- GET /spaces/{space}/transfers?offset=0&account={cuenta} (cuenta opcional)
- BFF: mismas rutas bajo /api.

Payload: id, origen_id, destino_id, fecha ISO, descripcion, moneda, importe.
El espacio y usuario se obtienen de ruta e identidad, sin aceptar esos campos del cliente.

El saldo agrega ingresos - gastos + transferencias_entrada - transferencias_salida
en una sola sentencia SQL. El resumen global incluye ambos lados y su efecto neto
es cero por moneda. Los resúmenes de consumo y presupuesto siguen usando solo gastos.

La migración 0014 agrega tabla, índices, restricciones y políticas. La migración debe
aplicarse antes de API/BFF/web. El BFF nuevo admite respuestas anteriores sin campos
de transferencias (se consideran cero); el BFF anterior rechaza saldos afectados por
transferencias durante una actualización parcial. El despliegue secuencial conserva
una ventana entre API y BFF; registrar transferencias requiere la nueva interfaz/BFF.

## Validación

CI ejecuta entradas inválidas y autenticación de API, contrato HTTP del BFF y saldos
con transferencias, formularios e idempotencia de Angular, y PostgreSQL real con
concurrencia, rollback, más de 100 transferencias, conservación por moneda,
retiros, aislamiento, restricciones de ambas cuentas y revocación de membresías.
Se mantiene el inventario cerrado de RLS y la comprobación de Alembic contra modelos.
La revisión visual móvil y escritorio se informa por separado en el PR.
