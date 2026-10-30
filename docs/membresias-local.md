# US-007, paso 1: membresías

> Guía de un paso anterior. Para el estado consolidado del PR y sus pendientes, consultar [Estado de US-007](estado-us-007.md).

Una membresía relaciona un usuario con un espacio y le asigna un rol de aplicación.
No es un rol de PostgreSQL: FastAPI continuará conectándose como app_runtime.

| Campo | Significado |
|---|---|
| usuario_id | UUID del usuario; en este incremento solo se usan identidades ficticias de prueba. |
| espacio_id | UUID de un espacio existente. Una clave foránea evita referencias inexistentes. |
| rol | owner, editor o lector; un CHECK rechaza cualquier otro valor. |

La clave primaria compuesta (usuario_id, espacio_id) impide duplicar una membresía.
Su índice sirve también para buscar las membresías de un usuario y consultar la
pareja usuario–espacio requerida por ADR-0002. Un índice separado por espacio_id
ayuda a buscar miembros de un espacio y comprobar su referencia al espacio.
No se añade un UUID artificial para la membresía ni un rol predeterminado.

La eliminación de un espacio con membresías queda bloqueada por la clave foránea.
La baja de espacios y administración de miembros no se implementan aquí.

## Modelo y migración

El modelo describe la estructura esperada. La revisión 0002 crea esa estructura
y configura explícitamente la seguridad de la tabla. No se modifica la revisión 0001.

La tabla nace con RLS habilitado y forzado. Solo la policy de app_migrator permite
operaciones, para preparar pruebas y ejecutar migraciones de datos. Se retiran los
grants de PUBLIC, los roles de Data API y app_runtime sobre esta nueva tabla.
Todavía no se concede lectura ni escritura al runtime. Esto no completa la
política global de grants y defaults de ADR-0002, ni protege otras tablas.

usuario_id todavía no tiene clave foránea a perfiles ni a auth.users: esos modelos
y su ciclo de alta se incorporarán después. Antes de habilitar membresías reales
debe definirse e implementarse ese vínculo. No es un mecanismo de autenticación.

## Verificar en desarrollo

Desde la raíz del repositorio, con el entorno virtual activo y Supabase local iniciado:

```bash
python3 infra/postgres/local_database.py alembic upgrade head
python3 infra/postgres/local_database.py alembic current
python3 infra/postgres/local_database.py alembic check
python3 infra/postgres/local_roles.py check
python3 infra/ci/check_database.py
```

En el paso original se esperaba 0002. Con todas las migraciones de este PR se espera 0006 (head), sin operaciones pendientes y comprobaciones aprobadas.
El último comando reconstruye una base temporal, no el proyecto remoto.
alembic check compara estructura; no demuestra por sí solo que RLS y grants sean correctos.

## Siguiente paso

Incorporar la identidad/perfil y el contexto de usuario por transacción, seguido de
las policies y sus pruebas con app_runtime. También se protegerá espacios.
US-007 sigue abierta. Este incremento no publica endpoints ni modifica Supabase remoto.

Referencia: https://docs.sqlalchemy.org/en/20/core/constraints.html

## Comparación del esquema predeterminado

PostgreSQL refleja las referencias hacia public sin el nombre de esquema cuando
public está en search_path. comparison_metadata prepara una copia del MetaData
para Alembic, representando public como None, después de validate_connection.
Los modelos de la aplicación conservan public explícito y las referencias hacia
esquemas externos conservan sus nombres. No se descartan las claves foráneas:
un cambio real debe seguir apareciendo en alembic check.
