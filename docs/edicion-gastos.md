# Edición de gastos

Cada gasto de la lista permite editar fecha, descripción, moneda e importe en el formulario existente. Se conserva el identificador, la cuenta, el espacio y el usuario que lo registró. Cancelar solicita confirmación y no envía cambios.

El navegador envía PATCH con los valores originales y nuevos. FastAPI valida identidad y rol, bloquea la fila dentro de la transacción y compara los campos originales. Si cambiaron, devuelve 409 y el formulario conserva el trabajo del usuario. Si el estado actual ya coincide con lo solicitado, devuelve el gasto sin aplicar otra escritura; permite reintentar una respuesta perdida. Se detectan diferencias de contenido, no cambios intermedios que terminaron restaurando exactamente los valores anteriores.

La migración 0009 agrega la policy UPDATE para owner/editor y concede edición únicamente de las cuatro columnas permitidas. No habilita cambiar la cuenta, la pertenencia o el autor; mantiene FORCE RLS. Un lector sigue sin escritura. Las migraciones se ejecutan antes de desplegar, siguiendo el pipeline existente.

Validación realizada en copia temporal del código:

- API: 82 pruebas existentes aprobadas.
- Angular: 21 pruebas, incluidas edición y conservación del formulario ante conflicto; compilación aprobada.
- BFF: 68 pruebas unitarias y 52 HTTP; preflight PATCH, validación de ID y contrato; compilación aprobada.
- Base Supabase temporal: migraciones, edición como editor, reintento, conflicto, rechazo a lector y otro espacio, columnas protegidas, drift y verificadores existentes aprobados.

No se desplegó ni se modificó el checkout del usuario. Falta la comprobación manual en celular y contra el entorno test después del merge.

Prueba manual: editar la fecha de un gasto, guardar, actualizar la lista y comprobar que sigue siendo un solo gasto. Abrirlo en dos pestañas, guardar valores distintos desde una y luego desde la otra: la segunda debe advertir el conflicto. Cancelar una edición debe conservar la fila original.

Los comprobantes están acordados para esta versión, pero no se incluyen en este incremento. La siguiente entrega deberá incorporar almacenamiento privado, permisos por espacio, límites y validación de archivos, subida independiente del guardado y consulta/descarga autorizada. No se presenta un botón de adjunto hasta que ese circuito esté implementado.
