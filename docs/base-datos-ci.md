# Reconstrucción de PostgreSQL en CI

El trabajo `database` comprueba que un checkout del repositorio alcanza para reconstruir el esquema de la aplicación. Usa Python 3.14.4, las dependencias de `apps/api/requirements.txt`, Docker y Supabase CLI 2.121.0.

Corre en las ramas y PR que ya activan el workflow. El despliegue de test requiere que aprueben `web`, `bff`, `api`, `integration` y `database`. Aprobar esta prueba no aplica migraciones sobre una base remota: esa etapa deberá incorporarse antes de desplegar código que dependa de ella.

## Qué se ejecuta

1. Crear una carpeta temporal y copiar únicamente `supabase/config.toml`. La copia recibe un `project_id` aleatorio con prefijo `gastos-ci-`, puertos disponibles y semillas desactivadas. La configuración del repositorio se conserva.
2. Ejecutar `supabase start`, excluyendo los servidores HTTP y servicios auxiliares. Se usa el PostgreSQL distribuido por Supabase; esta prueba no ejercita los servidores de Auth, Storage o la Data API.
3. Ejecutar `supabase db reset --local --no-seed` exclusivamente sobre ese proyecto temporal. No hay proyecto enlazado ni URL remota.
4. Generar dos contraseñas en memoria, provisionar los roles con `infra/postgres/provision-roles.sql` y comprobar conexiones TCP y permisos efectivos. No se carga `.env.roles.local`.
5. Crear datos centinela administrativos en `auth`, `storage` y un esquema externo de prueba. Son fixtures para comprobar los filtros; no son usuarios ni datos iniciales de negocio.
6. Ejecutar `alembic upgrade head` con `app_migrator`, verificar las revisiones aplicadas y la propiedad de `espacios`.
7. Repetir la provisión para comprobar que sigue funcionando con tablas y objetos internos TOAST. Exigir que `alembic check` termine correctamente.
8. Crear una tabla de prueba en `public` que no figura en los modelos. Exigir que `alembic check` falle específicamente por esa diferencia. Un error de conexión no cuenta como detección de drift. Retirar la tabla y volver a exigir un `check` correcto.
9. Comprobar que `app_runtime` no puede crear tablas en `public` y comparar la estructura externa y sus datos centinela con el estado anterior a las migraciones.
10. En el bloque de limpieza, detener solo el proyecto temporal y eliminar sus volúmenes con `supabase stop --no-backup`. Si GitHub termina el runner por fuerza, sus recursos se descartan con la máquina.

El programa no genera revisiones, no modifica los modelos y no corrige automáticamente el drift. Tampoco usa migraciones de aplicación desde `supabase/migrations/`: las de `public` siguen en Alembic.

## Repetir la prueba en Ubuntu/WSL

Requiere Docker disponible, Node según `.nvmrc` y el entorno virtual de la API con sus dependencias instaladas. Puede convivir con Supabase de desarrollo porque crea otro proyecto y elige otros puertos.

Desde la raíz del repositorio:

```bash
cd ~/projects/gastos
nvm use
source apps/api/.venv/bin/activate

python -m unittest discover -s infra/ci -p 'test_*.py'
python infra/ci/check_database.py
```

El primer comando de Python ejecuta controles sin Docker ni conexiones. El segundo ejecuta la prueba real y muestra ocho fases, la limpieza y una línea final `OK`. La primera ejecución puede tardar más por la descarga del CLI o de la imagen PostgreSQL.

El programa no recibe una URL ni un nombre de proyecto. Siempre crea su propio destino temporal. Los comandos de `reset` y eliminación de volúmenes pertenecen a ese procedimiento; no hace falta ejecutarlos a mano sobre el proyecto de desarrollo.

## Qué permite concluir

La prueba comprueba la reconstrucción y la comparación de objetos que Alembic reconoce con nuestros filtros. También deja una comprobación real de que una tabla pública ajena a los modelos continúa siendo visible: no se oculta para conseguir un resultado verde.

`alembic check` no certifica todas las policies, grants, funciones, triggers ni reglas de negocio. La comparación externa cubre relaciones, columnas y datos centinela; no es una auditoría completa de Supabase. Los filtros tampoco impiden que una migración escrita a mano intente ejecutar SQL incorrecto, por eso cada revisión sigue requiriendo lectura.

Las pruebas de RLS, contexto transaccional y migraciones de datos con `FORCE ROW LEVEL SECURITY` corresponden a US-007. Este incremento no concede CRUD a runtime.

Para cerrar US-006 todavía falta observar este trabajo aprobado en GitHub Actions y comprobar las conexiones remotas de ambos roles mediante el pooler de sesión, con TLS y validación del certificado.

Referencia: [Supabase CLI](https://supabase.com/docs/reference/cli/supabase-db-reset) documenta el alcance de `--local`, `--no-seed` y la gestión del proyecto local.
