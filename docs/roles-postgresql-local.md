# Roles de PostgreSQL en desarrollo local

Este incremento de US-006 prepara las identidades que usarán las migraciones y FastAPI. Requiere Supabase local iniciado y `supabase/config.toml` en el repositorio. No crea tablas de la aplicación ni implementa RLS o autenticación de usuarios.

## Base, esquema y rol

PostgreSQL es el motor. La base local que usamos se llama `postgres`. Dentro de una base hay esquemas, que agrupan objetos como tablas; `public` es el esquema de nuestra aplicación. Un rol es una identidad de PostgreSQL con permisos para conectarse o ejecutar operaciones.

La base `postgres` y el rol `postgres` son objetos distintos. En Supabase, el rol administrativo `postgres` tiene `BYPASSRLS` aunque no sea superusuario: puede omitir las políticas de filtrado de filas. Se reserva a la preparación administrativa; FastAPI no lo usa.

| Rol | Uso | Permisos iniciales |
|---|---|---|
| `app_migrator` | Futuras migraciones de Alembic. | Conectarse a la base, usar `public` y crear objetos allí. |
| `app_runtime` | Futuras consultas de FastAPI. | Conectarse a la base y usar `public`, sin permiso para crear objetos allí. |

Ninguno de los dos es superusuario, tiene `BYPASSRLS`, puede administrar roles o crear bases. No son miembros de otros roles. Este bootstrap no concede permisos de lectura o escritura sobre tablas de la aplicación: esos grants se incorporarán mediante Alembic cuando existan los objetos.

## Por qué se provisionan fuera de Alembic

Los roles son objetos de PostgreSQL fuera del esquema `public`. Además, Alembic necesita autenticarse como `app_migrator` antes de ejecutar su primera migración. Por eso `infra/postgres/provision-roles.sql` se ejecuta antes de Alembic, con una identidad administrativa.

ADR-0001 mantiene a Alembic como autoridad sobre los objetos de la aplicación en `public`. ADR-0002 establece este bootstrap y la separación entre migración y ejecución. El script no cambia la configuración de los esquemas de Supabase.

## Preparación y comprobación

Ejecutar desde la raíz del repositorio, en Ubuntu/WSL, con Supabase local iniciado:

```bash
python3 -m unittest discover -s infra/postgres -p 'test_*.py'
python3 infra/postgres/local_roles.py init
git check-ignore .env.roles.local
stat -c '%a %n' .env.roles.local
python3 infra/postgres/local_roles.py provision
python3 infra/postgres/local_roles.py check
```

`init` genera dos contraseñas distintas en `.env.roles.local`, con permisos `600`: lectura y escritura solo para su dueño en Linux. Git debe ignorar ese archivo. No se versiona, comparte ni usa en servicios remotos. Si ya existe, `init` lo conserva y termina indicando que no lo sobrescribió.

El helper admite también `APP_MIGRATOR_PASSWORD` y `APP_RUNTIME_PASSWORD` como variables de entorno; si se usan, deben estar ambas presentes y ser distintas. El archivo local es la opción de este procedimiento. Las contraseñas no aparecen en los argumentos de los comandos ni se imprimen como parte de la verificación.

`provision` obtiene el nombre del contenedor desde `project_id` en `supabase/config.toml`. Usa el cliente `psql` del propio contenedor, de modo que Python no necesita una biblioteca de PostgreSQL adicional. Las contraseñas se entregan por la entrada estándar al comando `\password` de `psql`, que las cifra en el cliente antes de enviarlas al servidor. El SQL contiene instrucciones propias de `psql`: no se pega en Supabase Studio ni en el editor SQL.

La provisión crea los roles si faltan y verifica los atributos de los existentes. Concede `CONNECT`, `USAGE` sobre `public` y `CREATE` sobre `public` únicamente al migrator; fija `public` como esquema predeterminado de ambos. Si detecta atributos, membresías o permisos incompatibles, falla para que se revise la configuración. No intenta corregirlos ampliando privilegios ni eliminando objetos.

Después de provisionar, el helper comprueba conexiones TCP con cada rol. Antes intenta una contraseña incorrecta: si esa conexión funciona, rechaza la configuración de autenticación y no considera válido el resultado.

La comprobación correcta devuelve:

```text
OK: app_migrator, TCP autenticado, public CREATE=True, BYPASSRLS=False.
OK: app_runtime, TCP autenticado, public CREATE=False, BYPASSRLS=False.
```

`check-roles.sql` consulta identidad y permisos efectivos: `session_user`, `current_user`, base, esquema predeterminado, atributos administrativos, membresías y privilegios. No modifica datos.

Para comprobar que la provisión puede repetirse:

```bash
python3 infra/postgres/local_roles.py provision
python3 infra/postgres/local_roles.py check
```

El segundo intento debe conservar las identidades y volver a pasar ambas comprobaciones. Si algún comando falla, conservar el mensaje de error sin publicar las credenciales. No usar una conexión de FastAPI como `postgres` para evitar un error de permisos.

## Alcance y siguiente incremento

Esta comprobación acredita únicamente el bootstrap y las conexiones de la base local. No prueba RLS, aislamiento entre usuarios, consultas financieras, migraciones ni acceso remoto.

US-006 continúa con SQLAlchemy, Alembic, `include_name`/`include_object`, una primera migración y reconstrucción en CI. También queda pendiente verificar las conexiones remotas de ambos roles mediante el pooler en modo sesión y TLS, antes de desarrollar RLS en US-007. El alta inicial del usuario y su espacio corresponde a ADR-0004 y US-001.

La provisión remota requiere un procedimiento propio con credenciales del entorno correspondiente. El helper de este documento está limitado al contenedor de Supabase local y no recibe una URL de base remota.
