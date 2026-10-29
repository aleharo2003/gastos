# US-007, paso 3: lectura de membresías y espacios

La revisión 0003 habilita SELECT para app_runtime sobre espacios y miembros_espacio.
El permiso permite ejecutar SELECT; las policies deciden qué filas devuelve.

| Tabla | Filas visibles |
|---|---|
| miembros_espacio | Solo las que tienen usuario_id igual al usuario del contexto. |
| espacios | Solo espacios con una membresía del usuario del contexto. |

No se exige app.workspace_id para estas dos lecturas: el usuario debe poder listar
sus espacios antes de seleccionar uno. Seleccionar un espacio ajeno no concede
acceso. La restricción al espacio seleccionado se aplicará a los datos financieros.

La policy de membresías compara directamente usuario_id, sin consultar de nuevo
la misma tabla. La policy de espacios consulta las membresías, que también están
protegidas por RLS. Esto evita una dependencia circular entre policies.

## Contexto y permisos

La expresión nullif(current_setting('app.user_id', true), '')::uuid maneja un
parámetro ausente o vacío sin convertir la cadena vacía a UUID. Sin usuario, el
SELECT devuelve cero filas. Con un valor malformado, PostgreSQL rechaza la consulta.
El helper de Python valida el UUID antes de abrir la operación.

Esta validación no autentica usuarios: un backend comprometido puede establecer
otra identidad. El usuario debe provenir de un token validado, nunca de un campo
libre del cliente. En estas pruebas solo se usan UUID ficticios; el vínculo con
perfiles sigue pendiente.

Ambas tablas tienen RLS y FORCE. Cada una conserva una policy específica para
app_migrator, que permite trabajar sin contexto durante migraciones de datos.
Runtime recibe únicamente SELECT: no puede crear espacios, insertar membresías,
cambiar roles, eliminar miembros ni ejecutar TRUNCATE. owner es un rol de negocio,
no un permiso administrativo de PostgreSQL.

Se retiran los grants de PUBLIC, anon, authenticated y service_role sobre ambas
tablas. Este paso no completa los defaults para objetos futuros ni una auditoría
de funciones o vistas: son verificaciones pendientes del contrato completo.

## Pruebas reales en CI

La fase 7 de check_database.py invoca check_read_rls.py sobre su PostgreSQL temporal.
Prepara dos usuarios con un espacio propio cada uno y un tercero compartido. Las
consultas de lectura se hacen deliberadamente SIN WHERE para comprobar la barrera
de PostgreSQL, independientemente de filtros del repositorio.

Se comprueba:

- Cada usuario ve sus membresías y sus espacios, incluido el compartido.
- Un usuario sin membresías no ve filas.
- Sin contexto, o con contexto vacío, no hay filas; un UUID inválido produce error.
- Elegir un espacio ajeno no permite verlo.
- Runtime no puede escribir ni asumir app_migrator.
- Después de retirar una membresía y confirmar la transacción, una nueva operación ya no ve ese espacio.
- RLS y FORCE están activos y los grants consultados son los esperados.
- Un backfill como migrator sin contexto actualiza exactamente dos espacios y sus valores son correctos; runtime conserva su aislamiento.

Los datos ficticios se eliminan al terminar. La base temporal se retira con el
procedimiento de CI. No se usan ni alteran datos del proyecto remoto.

## Reversión y límites

El downgrade a 0002 retira la lectura de runtime, sus policies y la protección de
espacios introducida por 0003; miembros_espacio conserva la protección de 0002.
No restaura grants previos de PUBLIC/Data API: la reversión conserva esos accesos
cerrados. No elimina tablas ni filas.

US-007 continúa abierta: faltan perfiles y su integridad, tablas financieras,
policies de escritura, relaciones entre espacios, defaults de privilegios y
validaciones restantes. Todavía no se conectó esta lectura a un endpoint público.

Referencia: [RLS en PostgreSQL 17](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
