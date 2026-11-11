# Todas las cuentas y totales de referencia

Gastos abre en «Todas las cuentas». El listado conserva sus filtros, búsqueda
aproximada y paginación. Cada fila muestra su cuenta; editar, comprobantes y
similares siguen apuntando a esa cuenta. Al registrar un gasto desde la vista
global, se elige explícitamente dónde se pagó. ARS sigue siendo la moneda inicial.

## Qué muestran los totales

- Día actual y mes calendario actual, con fecha de Argentina.
- Todas las cuentas del espacio, o la cuenta seleccionada.
- No cambian al filtrar la lista por texto, categoría, fechas o moneda.
- PostgreSQL suma todos los registros autorizados, no sólo la página visible.
- El mes incluye los gastos registrados con fecha dentro de ese mes, incluso
  si se cargó una fecha posterior a hoy. Las proyecciones no son gastos.
- Se actualizan al guardar, editar, cambiar de cuenta o actualizar la lista.
  Una pestaña abierta comprueba el cambio de día cada minuto cuando está visible.
- El botón para ocultar elimina los importes y el desglose de la vista; la
  preferencia se conserva en este navegador. Los importes individuales de las
  filas siguen visibles.

## ARS y USD

La moneda de referencia inicial es USD. En «Cotización y desglose» se puede
introducir cuántos pesos equivalen a un dólar, con hasta cuatro decimales.
La fecha indica cuándo se aplicó esa referencia. Esta primera versión la guarda
por espacio **en este navegador**, sin sincronizarla con otros dispositivos.

La conversión aplica la referencia actual a los agregados del período. No
cambia importes originales ni representa el tipo de cambio histórico de cada
gasto. Se suman decimales en PostgreSQL; la conversión usa enteros en el navegador
y redondea al centavo una sola vez por total, con mitades hacia arriba.

Si falta la referencia necesaria, o hay EUR en ese período, se muestra
«Conversión pendiente». El desglose conserva los totales originales por moneda.
Una falla de conexión muestra un error y permite reintentar; nunca aparece como cero.

## Contratos y permisos

- `GET /spaces/{space}/expenses`: listado global con los mismos filtros y tamaño
  de página que el listado por cuenta. Incluye `cuenta_id` y `cuenta_nombre`.
- `GET /spaces/{space}/expense-summary?account=<uuid>`: cuenta opcional; devuelve
  fecha, mes y totales originales por moneda como cadenas decimales.
- BFF publica los mismos recorridos bajo `/api` y valida identidad y respuestas.
- Ambos requieren membresía y usan la transacción runtime con RLS. No se crea
  una ruta de escritura global: cada escritura necesita una cuenta concreta.
- No se requieren migraciones, dependencias ni variables de Render nuevas.

## Validación automatizada

110 pruebas API, 68 unitarias BFF, 72 HTTP BFF y 52 Angular aprobadas; compilaciones
de BFF y Angular aprobadas. La base temporal verificó más de 100 registros,
dos cuentas, febrero bisiesto, lector y rechazo de otro espacio. También pasó
el chequeo completo de reconstrucción, roles, migraciones, drift y RLS.

## Prueba en test después de publicar

1. Entrar: debe aparecer «Todas las cuentas», con movimientos de distintas cuentas.
2. Aplicar una cotización propia, alternar ARS/USD y revisar el desglose.
3. Filtrar la lista: los totales diarios/mensuales deben conservarse.
4. Elegir una cuenta: listado y totales deben limitarse a esa cuenta.
5. Ocultar, recargar y mostrar: la preferencia debe conservarse.
6. Desde la vista global, crear y editar un gasto; abrir su comprobante.
7. En el celular, comprobar que el resumen permanece visible al desplazar la lista.

La revisión visual en el dispositivo real queda pendiente de estos pasos.
Los límites globales, presupuestos y gráficos son el siguiente incremento.
