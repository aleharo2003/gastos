# Permisos de objetos actuales y futuros

La migración 0006 cierra los permisos predeterminados de app_migrator para tablas (también vistas), secuencias y funciones. Incluye PUBLIC, anon, authenticated, service_role y app_runtime. Una migración futura debe conceder a runtime solo los permisos que necesite.

Los defaults se ajustan tanto globalmente en esta base como en public. El ajuste global pertenece únicamente a app_migrator; no cambia los defaults de postgres ni de los roles de Supabase. Es necesario porque un REVOKE limitado al esquema no elimina el EXECUTE que las funciones reciben de PUBLIC por defecto. Los defaults globales del creador aplicarían también si en el futuro se le permitiera crear objetos en otro esquema: eso requeriría revisar el ADR.

Los defaults no cambian objetos existentes. Por eso se revocan también los grants de PUBLIC y de los tres roles de Data API en relaciones y rutinas de public cuyo propietario es app_migrator. Se conservan los permisos explícitos existentes de runtime. No se toca un objeto ajeno solo por estar en public, ni se modifica auth o storage.

## Prueba en PostgreSQL

El contrato check_object_privileges.py se ejecuta dentro de la reconstrucción temporal de CI. Inspecciona permisos efectivos (incluidos los heredados de PUBLIC) de Data API sobre relaciones, columnas, secuencias y rutinas propias. Después crea una tabla, vista, secuencia y función SECURITY DEFINER como app_migrator, sin REVOKE específicos: exige que los defaults los mantengan cerrados a Data API y runtime.

Luego concede deliberadamente EXECUTE por defecto a PUBLIC, crea nuevamente los objetos y exige que el control detecte el acceso de runtime a la función. Cada escenario se revierte con rollback; se crean otra vez los objetos para comprobar la restauración de los defaults. No se usan credenciales de Data API ni se invoca PostgREST: se comprueban los privilegios efectivos en PostgreSQL. Esto no verifica la configuración HTTP de Supabase.

La función de prueba podría leer cuentas como su dueño si alguien pudiera ejecutarla. SECURITY DEFINER no la hace pública por sí solo: el contrato comprueba que no recibe EXECUTE. Las funciones futuras necesitan revisar también su código, search_path y permisos explícitos.

## Aplicación y reversión

En desarrollo se aplica con el comando habitual de Alembic como app_migrator; la revisión pasa de 0005 a 0006. No se ejecuta este control de CI directamente contra bases persistentes.

0006 no tiene downgrade automático: no conocemos los grants anteriores de cada entorno y restaurarlos a ciegas podría reabrir el acceso. Su downgrade falla antes de cambiar nada. Una corrección requiere una nueva migración revisada. Esto tampoco elimina datos.

US-007 sigue abierta. Este control no reemplaza RLS, no decide el alta inicial y no prueba todavía relaciones financieras entre espacios mediante claves foráneas compuestas.

Referencia: https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html
