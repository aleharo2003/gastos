# Búsqueda tolerante a errores en gastos

En **Filtrar gastos**, el campo de descripción incluye la opción
**Incluir coincidencias aproximadas**, activada inicialmente. Por ejemplo,
`cervesa`, `cerbeza` y `serbesa` encuentran una descripción con `cerveza`.
Los resultados que no contienen literalmente el texto normalizado llevan
la etiqueta **Coincidencia aproximada**.

Se conservan todos los filtros de fecha, categoría, moneda, cuenta y espacio.
Los resultados siguen ordenados por fecha descendente, no por relevancia.
La búsqueda no modifica las descripciones ni asigna categorías.

## Reglas

- En ambos modos se ignoran mayúsculas y marcas diacríticas: `CAFE` encuentra `Café`.
- Desactivando la opción, se busca la frase como fragmento continuo, sin corregirla.
- En modo aproximado, una consulta de varias palabras exige encontrar cada una,
  aunque estén separadas o en otro orden. No se eliminan palabras como «de» o «y».
- Las palabras de cuatro o más letras admiten variantes b/v, z/s y c delante de e/i.
- También se admiten inserciones, omisiones, sustituciones o transposiciones
  adyacentes: una edición por palabra, o hasta dos si la palabra buscada tiene
  ocho o más letras. Estas reglas pueden producir falsos positivos; por eso se
  muestran como aproximados y existe la opción de desactivarlas.
- Las palabras cortas y los números no reciben correcciones. Se conserva la
  búsqueda por fragmentos: `cer` sigue encontrando `cerveza`.
- Las consultas con signos se buscan literalmente; `%` y `_` no son comodines.

No es una búsqueda semántica: no infiere sinónimos ni conoce marcas, comercios
o categorías. No requiere una API de IA ni envía descripciones a terceros.

## Implementación y alcance

PostgreSQL selecciona las filas de la cuenta que cumplen los filtros y las
políticas RLS. La API compara las descripciones y pagina las coincidencias,
leyendo en lotes de 200 con un cursor dentro de la transacción runtime.
El cursor se cierra incluso si ocurre un error o se completa una página.
No se recorta la búsqueda a los primeros 100 gastos: se recorren tantos
candidatos como sea necesario para encontrar la página y una fila adicional.

Esto limita el uso de memoria, pero no el número total de filas que puede
recorrer una búsqueda sin coincidencias. Su costo crece con el historial filtrado.
Es una solución inicial para uso personal; antes de escalar se debe medir la
latencia con historiales representativos y evaluar una búsqueda indexada.
La caché de palabras está limitada a 512 combinaciones por consulta y no se
comparte entre usuarios. No cambia la paginación por offset ni sus límites
ante modificaciones concurrentes del listado.

No hay migración, dependencia, secreto ni variable nueva. Requiere el incremento
de categorías y filtros ya integrado. El endpoint agrega `aproximada=true|false`
y cada resultado de búsqueda incluye `coincidencia_aproximada` como booleano.
Los listados sin texto y los payloads de creación/edición mantienen su contrato.

Referencia técnica: [SQLAlchemy 2.0, lectura por lotes con yield_per](https://docs.sqlalchemy.org/en/20/core/connections.html#streaming-with-a-fixed-buffer-via-yield-per).

## Pruebas

Las pruebas automatizadas verifican los tres errores de escritura pedidos,
tildes compuestas, transposición, rechazo de términos no relacionados, varias
palabras, modo literal y cierre del cursor ante errores. La prueba con PostgreSQL
comprueba más de 100 coincidencias detrás de otros registros, filtros combinados,
acceso de lector, rechazo de otro espacio y conservación de IDs entre páginas.
El BFF valida el parámetro y la etiqueta; Angular conserva el modo aplicado al
paginar, aunque se modifique el formulario sin volver a aplicar.

Después de publicar en test:

1. Buscar `serbesa` teniendo un gasto cuya descripción incluya `cerveza`.
2. Confirmar que aparece con la etiqueta de coincidencia aproximada.
3. Desactivar la opción y volver a aplicar: ese gasto ya no debe aparecer,
   salvo que su descripción realmente contenga `serbesa`.
4. Buscar `cerveza` y comprobar que el resultado literal no lleva la etiqueta.
5. Combinar fecha, categoría y moneda; comprobar que siguen restringiendo resultados.

Las [sugerencias de categoría](sugerencias-categoria.md) ya están disponibles.
También están disponibles los [últimos gastos similares](gastos-similares.md) al consultar uno.
