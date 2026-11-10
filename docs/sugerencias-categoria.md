# Sugerencias de categoría al registrar gastos

Al terminar de escribir la descripción y salir del campo, la aplicación busca
antecedentes en la cuenta seleccionada. Si encuentra evidencia suficiente, muestra
una propuesta como **Usar Alimentos**, junto con la cantidad de gastos comparables.
La categoría sólo cambia cuando la persona pulsa ese botón. Después puede elegir
otra categoría y guardar normalmente.

## Qué se consulta

La API revisa hasta los últimos 500 gastos **con categoría** de la misma cuenta,
ordenados por fecha del gasto e ID descendentes. No mezcla cuentas, espacios ni
historiales de usuarios que no tengan acceso al espacio. En una cuenta compartida,
usa los gastos de esa cuenta que la persona está autorizada a consultar, sin
limitarse a los que creó ella misma. La moneda no limita la clasificación.

Las descripciones se comparan con las reglas de búsqueda existentes: mayúsculas,
tildes y errores comunes. La propuesta no usa servicios externos ni un modelo de
IA; es una regla explicable sobre las categorías que ya se guardaron.

## Cuándo se propone una categoría

Se priorizan los antecedentes en este orden:

1. Descripción igual, ignorando mayúsculas y tildes.
2. Descripción que contiene el texto buscado.
3. Coincidencia aproximada de las palabras buscadas.

Se utiliza sólo el primer grupo que tenga coincidencias. Dentro de ese grupo,
la categoría ganadora debe aparecer al menos dos veces y representar como mínimo
dos tercios de los antecedentes. Si no se cumple, no hay propuesta. Por ejemplo,
dos gastos en Alimentos y uno en Ocio permiten sugerir Alimentos; dos y dos no.
Una coincidencia exacta aislada no se reemplaza por muchas aproximadas.

No se consulta con menos de cuatro caracteres ni se sugieren categorías para
una descripción formada sólo por números. No se adivinan categorías a partir de
un diccionario de productos. Si todavía no hay gastos categorizados, se muestra
un mensaje y se permite elegir manualmente.

## Comportamiento del formulario

- Sólo se sugieren categorías para gastos nuevos que todavía no tengan una elegida.
- La consulta se inicia al salir del campo descripción, no con cada tecla.
- Cambiar la descripción o la categoría descarta las respuestas anteriores.
- Al editar un gasto existente no se propone reemplazar su clasificación.
- Una consulta lenta o fallida no bloquea el guardado ni altera el importe.
- La sugerencia no se guarda por separado: la categoría se persiste con el gasto
  cuando se pulsa **Registrar gasto**. Las ediciones posteriores del historial
  afectan las próximas consultas de sugerencias.

## API y permisos

`GET /spaces/{space}/accounts/{account}/expenses/category-suggestion?descripcion=...`
está disponible a través del BFF con el prefijo `/api`. Requiere identidad validada,
membresía vigente y acceso a la cuenta. Se consulta como `app_runtime` bajo RLS;
no se agregan permisos, migraciones ni secretos. Las respuestas usan `no-store`.

La respuesta contiene `categoria`, `coincidencias` y `total`. Sin propuesta,
se devuelve categoría null y ambos contadores en cero. El BFF valida el catálogo,
los contadores y la proporción antes de entregar la respuesta al navegador.

## Validación

Las pruebas cubren historial insuficiente, predominancia y empate, tildes,
errores de escritura, prioridad de coincidencias exactas, identidad requerida,
aislamiento entre cuentas y espacios y acceso de lector. Angular comprueba la
confirmación explícita, respuestas fuera de orden, cambios manuales mientras
espera, destrucción del componente y guardado ante un fallo de la sugerencia.

Prueba manual después de publicar:

1. Elegir dos gastos existentes de la misma cuenta con descripción igual o similar
   y asignarles la misma categoría. No hace falta crear gastos ficticios.
2. En un gasto nuevo, escribir esa descripción y pasar al campo siguiente.
3. Comprobar que aparece **Usar [categoría]** y que el selector sigue Sin categoría.
4. Pulsar la propuesta, verificar el selector y guardar sólo si el gasto es real.
5. Cambiar la categoría manualmente y comprobar que ninguna respuesta la reemplaza.

La revisión de 500 antecedentes limita el costo y también la evidencia disponible:
un patrón más antiguo puede no generar propuesta. Las coincidencias aproximadas
pueden equivocarse; siempre requieren confirmación. Los últimos gastos similares
al consultar un gasto se implementarán en el siguiente incremento.
