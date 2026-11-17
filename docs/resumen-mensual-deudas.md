# Resumen mensual de cuotas

Incremento posterior al PR #33. Aporta el total mensual comprometido de
[CTAS-43](https://aleharo.atlassian.net/browse/CTAS-43) para las deudas fijas finitas
existentes. No completa las stories de recurrencia variable ni generación automática.

## Interpretación

Se elige un mes de vencimiento. Se listan las cuotas del espacio que vencen en ese mes,
ordenadas por fecha e identificador. Los totales se muestran separados por moneda:

- Comprometido: suma del importe de las cuotas del mes.
- Pagado: todos los pagos vinculados a esas cuotas, aunque tengan fecha en otro mes.
- Pendiente: comprometido menos pagado.
- Vencido: parte del pendiente cuyo vencimiento es anterior a hoy en Buenos Aires.
- Cuotas completas: cantidad de cuotas con saldo cero.

Vencido es un subconjunto de pendiente; no se suman entre sí.
Las cuotas vencidas de meses anteriores se consultan eligiendo ese mes.
No es un informe de flujo de caja: para saber lo efectivamente gastado en un mes,
usar las fechas de los gastos en Movimientos.

Ejemplo: una cuota de 100000 ARS que vence en noviembre con un pago de
30000 ARS fechado en diciembre muestra 70000 ARS pendientes al consultar noviembre.
El gasto se registra en diciembre. No se crea un segundo gasto por mostrar el resumen.

Los totales incluyen todas las cuotas del mes, aunque solo se hayan cargado las primeras
100 filas. Una única sentencia SQL entrega resumen y página con la misma fotografía
de los pagos. Se admite una página vacía con totales completos.

## Interfaz

La sección Deudas permite consultar mes, recorrer sus cuotas y abrir directamente
el plan y su página de cuotas para registrar un pago con el flujo existente.
Esto funciona aunque el plan no esté cargado en la primera página del listado general.
Después de crear una deuda o registrar un pago se actualiza el resumen.
El mes de los datos visibles se indica explícitamente: editar el selector no
reetiqueta datos anteriores ni cambia la paginación antes de consultar.
Una respuesta tardía de otro mes/espacio no sustituye los datos actuales.
Se conservan los borradores de pago y se ocultan importes con el control de privacidad.

## Contratos y validación

- GET /spaces/{space}/installments?month=AAAA-MM&offset=0.
- GET /spaces/{space}/commitments/{id}.
- BFF: mismas rutas bajo /api. Cache-Control: no-store.
- Owner/editor/lector consultan según membresía; RLS mantiene el aislamiento.
- Años 0001 a 9999, meses 01 a 12; páginas de hasta 100.
- Sin migraciones nuevas. Requiere la migración 0016 del PR #33.
- Pruebas de API, BFF, Angular y PostgreSQL: calendario, pagos fuera del mes,
  saldo parcial, monedas separadas, páginas de más de 100 filas, permisos,
  respuestas tardías, privacidad y navegación al pago.

## Próximos incrementos

CTAS-38: compromisos fijos indefinidos y pausa.
CTAS-39: importes variables con borradores estimados.
CTAS-46 y CTAS-59: generación mensual automática e independiente de los servicios web.
Este resumen no sustituye esos procesos ni genera cuotas al abrir la pantalla.
