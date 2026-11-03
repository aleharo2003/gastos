# Migraciones de Supabase test antes de Render

US-009 incorpora las migraciones remotas al trabajo deploy_test existente. El orden es CI aprobado, comprobación del commit de main, instalación de dependencias, migración y verificación de Supabase, despliegue y verificación de Render.

## Destino y credenciales

El programa infra/cd/migrate_test.py fija el destino del entorno de test:

| Parámetro | Valor |
|---|---|
| Proyecto | cyxhyfbiacfayixbmotq |
| Host | aws-1-us-west-2.pooler.supabase.com |
| Puerto y modo | 5432, pooler de sesión |
| Base | postgres |
| Usuario | app_migrator.cyxhyfbiacfayixbmotq |
| TLS | verify-full con la CA configurada |

Los roles ya deben existir: este programa no ejecuta provisión ni necesita la contraseña de postgres. El environment test de GitHub contiene SUPABASE_MIGRATOR_PASSWORD y SUPABASE_DB_CA_CERT. El primero es la contraseña del rol remoto app_migrator; el segundo contiene el PEM completo del certificado público usado al verificar la conexión. No usar las credenciales locales.

La contraseña se entrega solo al paso de migración, mediante el entorno. URL.create construye la URL sin concatenar o codificar manualmente la contraseña. La CA se valida, se escribe en un archivo temporal con permisos 600 y se elimina al terminar. No se imprimen URLs, secretos ni excepciones completas del driver. Render no recibe estos dos secretos.

El environment test debe seguir restringido a main. El job solo corre en push a main, después de todos sus needs. El script comprueba también los datos del evento y rechaza argumentos; es una protección contra ejecución accidental, no una barrera frente a alguien que ya controle código y secretos del job. Un PR ejecuta pruebas sobre una base desechable y no utiliza los secrets remotos.

## Transacción y concurrencia

El job conserva el grupo render-test con cancel-in-progress false: el turno incluye ahora tanto migración como despliegue. Conserva también la comprobación de main antes de comenzar. Un commit que avanza después de esa comprobación no cancela la entrega iniciada.

El núcleo de migración abre una transacción, verifica el rol efectivo con el contrato existente y toma un advisory lock transaccional. Si otro proceso del mismo flujo tiene ese lock, se detiene. El lock no impide que un administrador u otro cliente que no siga el protocolo ejecute DDL: no realizar migraciones manuales concurrentes.

Alembic recibe la conexión y transacción existentes. upgrade head, alembic check y la comprobación de la revisión final deben aprobar antes del commit. No se usa stamp, downgrade ni db reset. Las migraciones actuales son transaccionales; futuras migraciones con autocommit, COMMIT explícito u operaciones externas requieren revisar esta garantía antes de incorporarlas.

Se exige una sola head. lock_timeout es 30 segundos y statement_timeout es 300 segundos por sentencia. Un timeout o error de migración detiene la entrega; no hay reintentos automáticos de esta etapa. alembic check compara el esquema que soporta autogenerate: no demuestra por sí solo grants o policies correctos. Eso se prueba previamente en CI.

Si falla la migración o el check dentro de la transacción, sus cambios se revierten y no se inicia Render. Si falla Render después de confirmar la migración, la base queda actualizada y puede seguir ejecutándose una versión anterior de la aplicación. Por eso los cambios deben ser compatibles con el código anterior, usando cambios aditivos y retiradas en entregas posteriores. No hay una transacción distribuida ni rollback automático de la base tras publicar.

Si se pierde la conexión al confirmar, no asumir que se revirtió: revisar la revisión real antes de recuperar la entrega. No borrar tablas ni manipular alembic_version para silenciar un fallo.

## Primera entrega

Al integrar este cambio en main, se aplicarán las migraciones pendientes en Supabase test antes del despliegue. Si la base aún no está versionada, el recorrido previsto va desde 0001 hasta 0006. Se detendrá si encuentra tablas incompatibles o revisiones desconocidas. La revisión 0004 exige que no existan membresías previas; si hay datos manuales, requiere un backfill revisado.

La revisión 0006 no tiene downgrade automático. Este incremento no crea usuarios de negocio, no prepara producción ni conecta los endpoints actuales de FastAPI a los datos remotos. La credencial de app_runtime y la integración de acceso de la aplicación son pasos separados.

## Pruebas y operación

Desde Ubuntu, con las dependencias API instaladas, se ejecutan:

```bash
python -m unittest discover -s infra/cd -p 'test_*.py'
python -m unittest discover -s infra/ci -p 'test_*.py'
python infra/ci/check_database.py
```

No ejecutar migrate_test.py manualmente ni proporcionar una URL remota a las pruebas. El test de integración usa únicamente la fixture local desechable: prueba el bloqueo concurrente, provoca drift para exigir rollback de tablas y revisión, aplica head correctamente y repite sin cambios. Después corre todos los contratos existentes de RLS y permisos. Esta prueba no certifica la contraseña, el certificado ni la conectividad del runner de GitHub a Supabase: esos tres puntos se verifican en la primera entrega real.

En Actions, el paso Migrar y comprobar Supabase test debe informar la revisión confirmada antes de comenzar Desplegar y verificar API, BFF y Angular. Si falla, revisar primero el secret correspondiente, el certificado y si Supabase test está disponible. Mantener Auto-Deploy Off en Render para conservar este orden.
