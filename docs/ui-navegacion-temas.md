# Navegación, temas y listado de gastos

Esta entrega organiza las funciones existentes. Gastos es la sección inicial;
Cuentas reúne la administración de cuentas. Al pasar entre ambas se conserva
el formulario, los filtros y los comprobantes abiertos de la cuenta seleccionada.
Cambiar de cuenta requiere terminar el formulario y cualquier carga de comprobantes.

El formulario de gasto se abre con «Agregar gasto». Editar un gasto lo abre y
lleva el foco a la fecha. Los movimientos tienen fondos alternados y acciones
agrupadas. Las opciones de tema son Claro, Oscuro y Dispositivo; la preferencia
se guarda en este navegador, sin enviar datos al servidor. Dispositivo sigue
los cambios del sistema operativo. Si el navegador bloquea el almacenamiento,
el tema puede cambiarse durante la sesión.

## Alcance financiero

Esta entrega conserva la consulta por cuenta. Todavía no incluye «Todas las
cuentas», totales globales, conversión de referencia, límites, presupuestos ni
gráficos. Esos cálculos se implementarán sobre todos los registros autorizados,
no sobre la página visible. Los límites serán globales del espacio y los
presupuestos serán proyecciones separadas de los gastos reales.

## Validación

- 44 pruebas de Angular aprobadas, incluidas persistencia de tema, navegación
  sin pérdida del borrador y apertura de edición.
- Compilación de producción aprobada.
- No cambia dependencias, contratos HTTP, migraciones ni configuración de Render.

Antes de dar por validada la interfaz en test:

1. Entrar desde computadora y celular; comprobar ancho y legibilidad.
2. Probar Claro, Oscuro y Dispositivo. Recargar y comprobar persistencia.
3. Empezar un gasto, visitar Cuentas y volver: el borrador debe conservarse.
4. Guardar y editar una fecha; confirmar que la fecha corregida persiste.
5. Abrir comprobantes y similares; aplicar filtros y cargar otra página.
6. Cambiar de cuenta con un borrador: debe aparecer un aviso y conservarse
   la cuenta anterior. Terminar el formulario y repetir.

La revisión visual en el navegador desplegado queda pendiente de esta prueba.
