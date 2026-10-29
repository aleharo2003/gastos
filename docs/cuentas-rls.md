# US-007, paso 5: cuentas por espacio y permiso

Esta es la estructura mínima de cuentas para probar el aislamiento. Solo contiene
id, espacio_id y nombre. No implementa US-010: faltan tipos de cuenta, monedas,
apertura, datos específicos de tarjetas/inversiones, endpoints y pantallas. No se
agrega un saldo editable ni se decide cómo se contabilizan movimientos.

## Estructura

id es UUID, con valor generado por Python cuando se crea un objeto ORM. espacio_id
referencia un espacio existente y nombre es obligatorio. La clave única
(espacio_id, id) prepara el destino de futuras FK compuestas de movimientos y
sirve como índice para filtrar cuentas por espacio. No basta por sí sola para
impedir referencias cruzadas: cada relación futura debe declarar la FK compuesta.

## Lectura y escritura

| Operación | lector | editor | owner |
|---|---|---|---|
| Leer cuentas del espacio seleccionado | Sí | Sí | Sí |
| Insertar en ese espacio | No | Sí | Sí |
| Cambiar nombre | No | Sí | Sí |
| Eliminar una cuenta | No | Sí | Sí |
| Cambiar id o espacio_id | No | No | No |

Cada policy exige coincidencia con app.workspace_id, usuario válido en app.user_id
y membresía actual con el rol permitido. Pertenecer a varios espacios no mezcla
sus datos: se opera en uno a la vez. La pertenencia se lee de la base; no se toma
el rol de un campo del cliente ni del token.

SELECT usa USING. INSERT usa WITH CHECK. UPDATE usa ambos, para restringir tanto
filas existentes como su resultado. DELETE usa USING. Se concede UPDATE solo sobre
nombre; el resto de las columnas permanece inmutable para runtime. La restricción
de columnas agrega una barrera a la prohibición de trasladar cuentas entre espacios.

Las policies son específicas para app_runtime. app_migrator tiene su policy de
migración sin contexto, con FORCE activo. Los roles de Data API y PUBLIC no reciben
acceso a cuentas. Esta revisión no sustituye el trabajo pendiente sobre privilegios
predeterminados de objetos futuros.

## Casos que prueba CI

- Consultas sin WHERE devuelven solo las cuentas del espacio seleccionado.
- Un owner de dos espacios no ve ambos al seleccionar uno.
- Sin espacio, sin usuario o sin membresía no se ven cuentas.
- Editor y owner pueden insertar, renombrar y eliminar en su espacio.
- Un lector no inserta ni modifica ni elimina filas.
- Un INSERT con un espacio distinto se rechaza aunque el usuario pertenezca a ambos.
- UPDATE y DELETE hacia el espacio no seleccionado afectan cero filas.
- Los cambios de id/espacio_id y TRUNCATE se rechazan por permisos.
- Retirar membresía impide leer y escribir en una transacción nueva.
- Migrator sin contexto completa un backfill de dos espacios; se comprueban cantidad y valores.

Un UPDATE o DELETE sin filas autorizadas puede terminar normalmente con rowcount=0.
Por eso las pruebas no consideran suficiente que el comando no arroje un error.
La capa de aplicación deberá comprobar el resultado al implementar los casos de uso.

Las fixtures se crean y eliminan únicamente en PostgreSQL temporal de CI. No hay
un endpoint nuevo ni se cargan cuentas en desarrollo o Supabase remoto.

## Límites y próximos pasos

Los repositorios de operaciones reales deberán filtrar explícitamente por espacio,
aunque RLS agregue esta segunda barrera. Este incremento prueba directamente SQL;
no entrega todavía repositorios, API ni autenticación.

La baja de cuentas con movimientos y sus reglas financieras se definirá con las
stories correspondientes; hoy no hay movimientos ni relaciones hacia cuentas.
No usar esta estructura mínima como una aplicación financiera terminada.

US-007 sigue abierta: faltan relaciones entre entidades de espacios distintos,
contrato global de grants/defaults y comprobaciones restantes. US-010 tampoco se cierra.
El downgrade de 0005 elimina cuentas y sus datos; no ejecutarlo sobre datos a conservar.

Referencia: [RLS de PostgreSQL](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
