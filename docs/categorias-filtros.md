# Categorías y filtros de gastos

La categoría es opcional al registrar o editar un gasto. Los gastos anteriores
quedan **Sin categoría**; no se reclasifican automáticamente ni cambian sus
importes, fechas, monedas o comprobantes.

El catálogo inicial incluye Alimentos, Transporte, Vivienda, Servicios, Salud,
Educación, Ocio, Impuestos, Auto, Bancario, Ropa y Otros. Son identificadores
estables compartidos por API, BFF y web, protegidos por una restricción SQL.
Todavía no hay administración de categorías personalizadas.

## Uso

En una cuenta, abrir **Filtrar gastos**. Se pueden combinar:

- Desde y Hasta, ambos inclusive, sobre la fecha del gasto.
- Categoría, incluida la opción Sin categoría.
- Moneda original, sin conversiones.
- Texto en la descripción, con coincidencias aproximadas opcionales.

**Aplicar filtros** vuelve a la primera página. **Ver más gastos** conserva los
filtros aplicados, aunque se haya modificado el formulario sin aplicarlo.
**Limpiar filtros** restablece la consulta completa de esa cuenta.
El contador indica resultados cargados, no el total de toda la consulta.

Los filtros de fecha, categoría, moneda y cuenta se aplican en PostgreSQL,
manteniendo los controles de espacio y RLS. La API aplica la búsqueda de texto
antes de paginar las coincidencias (100 registros por página). Se usan parámetros
SQL; `%` y `_` se interpretan como texto literal. Un rango invertido se rechaza.

Después de guardar con filtros activos se vuelve a consultar la primera página.
El gasto puede quedar fuera de los resultados; el acceso para adjuntarle un
comprobante sigue disponible. Editar la categoría mantiene el ID y los archivos.

## Migración y compatibilidad

`0011_categorias_gastos` agrega una columna nullable y su CHECK en `public.gastos`.
Amplía únicamente el permiso UPDATE de `app_runtime` a esa columna. Mantiene las
políticas existentes: lector consulta; owner/editor modifican dentro de su espacio.
Alembic debe ejecutarse antes de desplegar la API, como ya hace el pipeline.
No hacen falta nuevas variables, secretos ni cambios en Storage.

Un cliente anterior que omite `categoria` en una edición conserva la categoría
existente. Un cliente nuevo envía el original para detectar cambios concurrentes
y puede enviar null explícitamente para quitar la categoría.
El downgrade elimina la clasificación; no debe usarse para revertir sólo la UI.

## Verificación

Las pruebas cubren categorías permitidas, búsqueda literal, validación de filtros,
transporte por el BFF, rangos inclusivos, paginación filtrada de más de 100 filas,
aislamiento por espacio/cuenta, permisos de lector, edición con clientes antiguos
y conservación de los filtros al paginar en Angular.

Comprobación manual después del despliegue:

1. Editar un gasto existente con comprobante y asignar Alimentos.
2. Buscar parte de su descripción y su fecha exacta con Desde y Hasta iguales.
3. Combinar categoría y moneda; comprobar que aparece.
4. Cambiar la categoría a Ocio; comprobar que sale del filtro Alimentos.
5. Limpiar filtros, abrir el gasto y verificar su comprobante.
6. Repetir en el celular; el filtro queda plegado al entrar y no impide cargar gastos.

## Próximos incrementos

La búsqueda tolerante a errores ya está disponible; ver [Búsqueda aproximada](busqueda-aproximada.md). Las [sugerencias de categoría](sugerencias-categoria.md) ya están disponibles. Siguen pendientes los gastos similares y la vista de gastos de todas las cuentas. Los gráficos y las exportaciones se implementarán en otros incrementos.

Se conserva la paginación por offset existente: si otra sesión agrega registros
entre páginas, puede ser necesario actualizar la lista. No es una instantánea
contable para exportar. Para volúmenes mayores habrá que medir el plan de consulta
de texto y evaluar un índice específico.
