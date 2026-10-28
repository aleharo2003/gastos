# Validación de US-006

Fecha: 27 de octubre de 2026. Estado: pendiente de integrar y aprobar el refuerzo final de CI.

## Evidencias disponibles

- [PR #7](https://github.com/aleharo2003/gastos/pull/7) integrado en main, commit 8afa58734ad9c70dd83f6b0866b0c68609bce204.
- [CI y CD de main](https://github.com/aleharo2003/gastos/actions/runs/40550549776): aprobados los trabajos de web, BFF, API, integración HTTP, PostgreSQL y despliegue de test.
- La validación de PostgreSQL reconstruye una base temporal, provisiona roles, aplica Alembic como app_migrator, comprueba diferencias y conserva estructura externa y datos centinela.
- Las pruebas de filtros cubren objetos reflejados y MetaData explícito, esquema predeterminado y referencias desde public hacia tablas externas.
- Alejandro ejecutó las conexiones remotas individuales descritas abajo y compartió sus resultados.

## Conexiones remotas

Proyecto gastos-test, referencia cyxhyfbiacfayixbmotq, región Oregon (us-west-2).
Servidor aws-1-us-west-2.pooler.supabase.com, puerto 5432, base postgres, PostgreSQL 17.11.

Las conexiones usaron el pooler en modo sesión, sslmode=verify-full y el certificado CA descargado del proyecto. La contraseña se ingresó en el prompt de psql. Primero se provisionaron los roles con el script versionado; luego se abrió una conexión independiente con cada rol y se ejecutó infra/postgres/check-roles.sql.

| Comprobación | app_migrator | app_runtime |
|---|---|---|
| session_user y current_user | app_migrator | app_runtime |
| LOGIN, CONNECT y USAGE public | true | true |
| CREATE en public | true | false |
| CREATE de esquemas | false | false |
| SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS | false | false |
| Membresías en otros roles | 0 | 0 |

El usuario de conexión del pooler lleva el sufijo del proyecto; dentro de PostgreSQL la identidad efectiva es el nombre del rol sin ese sufijo. Estas pruebas confirman autenticación y los permisos consultados; no prueban todavía políticas RLS ni operaciones de negocio.

## Refuerzo final y cierre

El refuerzo añade el caso exacto del criterio de aceptación: un cambio de modelo sin revisión debe ser detectado por Alembic. Conserva también la prueba de una tabla pública extra y mejora el mensaje del fallo para indicar la migración pendiente.

Antes de marcar US-006 terminada:
1. Integrar este refuerzo mediante PR.
2. Confirmar el trabajo database aprobado en GitHub Actions y enlazar la ejecución a la story.
3. Registrar estas evidencias en Jira.

## Alcance que continúa después

No se aplicaron migraciones a la base remota durante estas comprobaciones. La API publicada todavía devuelve el saludo sin consultar datos de negocio. Antes de desplegar código que dependa del esquema remoto, el pipeline deberá migrarlo con app_migrator antes del despliegue.

US-007 cubre contexto transaccional, grants, RLS y migraciones de datos con FORCE RLS. El alta inicial depende de ADR-0004. alembic check no certifica por sí solo policies, funciones, triggers ni grants.
