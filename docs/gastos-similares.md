# Últimos gastos similares

Cada gasto de la lista tiene un botón **Ver gastos similares**. Abre un panel
dentro de esa misma tarjeta, sin navegar a otra pantalla ni modificar el borrador.
**Ocultar similares** cierra el panel. Sólo se consulta al abrirlo; si falla,
aparece un botón para reintentar.

Se muestran hasta cinco **otros** gastos de la misma cuenta, ordenados por fecha
descendente e ID descendente para desempatar. Se excluye siempre el gasto
seleccionado. Se usa todo el historial autorizado de la cuenta, sin aplicar los
filtros de la lista principal; el panel lo indica explícitamente.

Se muestran descripción, fecha, categoría, importe y moneda originales. No se
suman monedas diferentes, no se convierten importes y no se calcula una variación
de precio: las cantidades o productos de dos gastos parecidos pueden diferir.
Los resultados son una ayuda para consultar antecedentes, no un análisis de precios.

## Qué significa similar

Una descripción igual ignorando mayúsculas y tildes es una coincidencia directa.
Para el resto, se comparan palabras significativas, ignorando conectores comunes
como «de» y «con», términos genéricos como «compra» y «pago», números aislados y
repeticiones. Se admiten variantes de escritura y errores de tipeo con las reglas
ya usadas en la búsqueda.

Cada palabra se empareja como máximo una vez. Deben coincidir al menos dos tercios
de las palabras del texto más corto y la mitad de las del más largo. Así, «compra
de cerveza» puede relacionarse con «cerveza artesanal», mientras «seguro auto» y
«seguro casa» no coinciden sólo por compartir «seguro». Los resultados de este
grupo muestran **Descripción parecida**.

Compartir categoría o moneda no alcanza para ser similar. No hay un modelo de
IA ni envío de descripciones a un servicio externo. Las reglas pueden producir
falsos positivos o dejar afuera antecedentes; no modifican ningún dato.

## Acceso y consistencia

La API expone `GET /spaces/{space}/accounts/{account}/expenses/{id}/similar`,
con prefijo `/api` en el BFF. Valida identidad, membresía y cuenta, y comprueba
que el gasto de referencia pertenece a esa cuenta dentro del espacio.
Consulta como `app_runtime` bajo RLS. Los lectores pueden consultar; una membresía
revocada no tiene acceso. No hay nuevos permisos, migraciones, variables o secretos.

Las respuestas incluyen `referencia_id` e `items`. El BFF comprueba la referencia,
el espacio y la cuenta de cada resultado, que haya hasta cinco filas y que no
haya IDs duplicados ni aparezca el original. Se usa `Cache-Control: no-store`.

La consulta recorre candidatos por lotes de 200 hasta encontrar cinco coincidencias
o llegar al final. No se limita a las filas cargadas en el navegador. Esto limita
la memoria, pero una cuenta grande sin coincidencias puede requerir recorrer todo
su historial. Habrá que medir y considerar índices de búsqueda antes de escalar.

Se consulta el estado actual de la base cada vez que se abre el panel. No hay
actualización en tiempo real mientras permanece abierto. Actualizar la lista,
editar o guardar cierra el panel para evitar mostrar antecedentes desactualizados.
Las respuestas pendientes se descartan al destruir el componente.

## Validación

Las pruebas cubren reglas de similitud, exclusión de términos genéricos y cierre
de cursor ante errores. Con PostgreSQL temporal se verifican ocho coincidencias
detrás de 210 registros no relacionados: se devuelven las cinco más recientes,
con importes y monedas intactos, sin el original ni datos de otra cuenta o espacio.
También se comprueban acceso de lector, gasto inexistente y revocación.

El BFF rechaza referencias incorrectas, duplicados, exceso de filas y respuestas
de otra cuenta. Angular verifica estados vacío/error, reintentos, respuestas tardías
y conservación de borrador y filtros al abrir/cerrar.

Prueba manual tras publicar:

1. Elegir un gasto que tenga antecedentes parecidos en la misma cuenta.
2. Pulsar **Ver gastos similares**; verificar fechas, monedas e importes.
3. Confirmar que no aparece el propio gasto seleccionado.
4. Abrir desde una lista filtrada: los antecedentes pueden tener otras fechas o
   categorías porque el panel consulta todo el historial de la cuenta.
5. Cerrar y comprobar que el filtro y el formulario siguen como estaban.

Este incremento sólo permite consultar los antecedentes. No agrega navegación,
edición ni descarga de comprobantes dentro de cada fila del panel.
