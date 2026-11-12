# Presupuesto proyectado y límites globales

El espacio tiene un plan compartido, disponible en la pestaña **Presupuesto**.
Configura límites diarios y semanales en ARS o USD y hasta 40 conceptos
semanales o mensuales. Los conceptos empiezan en ARS. Guardar el plan no crea
gastos, pagos, vencimientos ni movimientos de saldo.

## Consumo y proyección

- Los límites suman todas las cuentas y categorías del espacio. Filtrar la
  lista de gastos no modifica el consumo global.
- El día y la semana corresponden a Argentina; la semana va de lunes a domingo.
  Se usa la fecha del gasto. El resumen incluye todos los gastos registrados
  dentro del período, incluso fechas futuras de esa semana o mes.
- Desde el 80% aparece un aviso; superar el 100% muestra cuánto se excedió.
  Los avisos no impiden registrar gastos. No son notificaciones externas.
- La proyección semanal suma los conceptos semanales. El promedio mensual es
  `semanales × 52 ÷ 12 + mensuales`. Por ejemplo, ARS 470.000 semanales equivalen
  a ARS 2.036.666,67 mensuales en promedio, no a cuatro semanas exactas.
- Las barras muestran consumo frente al límite, gasto real del mes frente a
  la proyección y distribución porcentual de los conceptos proyectados.
  El gráfico de gastos reales por categoría corresponde a otra entrega.
- El plan es el actual, sin historial mensual de versiones. Modificarlo cambia
  la referencia mostrada; no cambia los gastos registrados.

## Monedas y privacidad

Los importes originales se conservan. Se puede ver el presupuesto en ARS o USD.
Se reutiliza la cotización manual de Gastos, como referencia actual, sin
reescribir conversiones históricas. Esa cotización sigue guardada en el
navegador: dos dispositivos deben usar la misma para ver las mismas equivalencias.
El presupuesto y los límites sí se guardan en la base compartida.

Si falta una cotización necesaria o hay gastos en una moneda no convertible,
se muestra conversión pendiente. No se presenta una suma parcial como completa.
Los cálculos usan centavos enteros y redondean la conversión al final.
El ojo de Gastos también oculta importes, barras y editor del presupuesto.

## Acceso y guardados simultáneos

`GET/POST /spaces/{space}/spending-plan` se expone a través del BFF.
La identidad se valida en ambos servicios. La migración `0012` crea
`public.planes_gasto`, con RLS y FORCE. Un miembro puede leer; owner/editor
pueden guardar. No se conceden permisos a los roles de la Data API.

Cada guardado envía la versión leída. Se bloquea la fila durante la escritura;
si otra sesión la modificó, responde 409 y el formulario conserva el borrador.
Repetir el mismo contenido devuelve la versión existente sin duplicar cambios.
La configuración se almacena como un documento JSON acotado y validado; no es
una colección de gastos. La tabla tiene una fila por espacio.

## Despliegue y comprobación manual

El pipeline aplica `0012` antes de publicar. No necesita nuevas claves ni
variables de entorno. Primero deben publicarse API y BFF, luego Angular.

1. Abrir Presupuesto y guardar un límite semanal de USD 200.
2. Cargar conceptos semanales y mensuales; comprobar que no aparecen como gastos.
3. Comparar consumo global con Todas las cuentas y luego filtrar una sola cuenta:
   el límite debe mantener el mismo consumo.
4. Configurar la cotización, alternar ARS/USD y comprobar conversiones pendientes
   al quitar una referencia necesaria.
5. Probar el ojo, pantalla pequeña y tema oscuro.
6. Abrir otro dispositivo: el plan debe persistir. Si ambos editan la misma
   versión con valores diferentes, el segundo guardado debe pedir recargar.

La verificación automatizada incluye cálculos, privacidad, validación HTTP,
aislamiento entre espacios, lector sin escritura, revocación, concurrencia,
reintentos y ausencia de gastos creados. La suite de base reconstruye desde cero,
comprueba Alembic y conserva los esquemas externos.
