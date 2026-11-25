# Resguardo semanal de Piggo

El workflow **Resguardo semanal de Piggo** genera una copia cifrada de
PostgreSQL para un espacio los lunes a las 05:23 UTC. Usa un rol de solo
lectura limitado al espacio por políticas RLS, y conserva una copia por
semana para las ocho semanas disponibles más recientes. La depuración
empieza después de confirmar la copia nueva.

El archivo preserva filas, relaciones, identificadores y valores exactos.
Incluye los metadatos de comprobantes. Los binarios alojados en Supabase
Storage, las credenciales de Supabase Auth y las preferencias guardadas
solo en el navegador requieren resguardo por separado. El workflow no tiene
permisos sobre esos sistemas. El archivo es un respaldo PostgreSQL y
complementa la descarga CSV desde Piggo.

## Preparar y activar

1. Configurar un entorno de GitHub llamado `backup`, con despliegues
   limitados a `main`. En la base, ejecutar primero
   `infra/postgres/provision-backup.sql` como administrador mediante
   `psql -X --file`. Después ejecutar `infra/postgres/grant-backup.sql`
   como `app_migrator` con `-v backup_space_id=<uuid-del-espacio>`.
   El workflow usa exclusivamente la conexión de `app_backup`.
2. Configurar en el entorno los secretos `PIGGO_BACKUP_DATABASE_URL`,
   `PIGGO_BACKUP_DB_CA` (PEM), `PIGGO_BACKUP_KEY` (clave Fernet),
   `PIGGO_BACKUP_ALERT_EMAIL` (correo del titular), `RESEND_API_KEY`
   y las variables `PIGGO_BACKUP_SPACE_ID` y `PIGGO_BACKUP_FROM_EMAIL`.
   Para generar la clave usar `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   y guardar otra copia fuera de GitHub en un gestor de secretos.
3. Ejecutar el workflow manualmente con un espacio de prueba y restaurar
   su copia en una base desechable. Con la programación todavía apagada,
   verificar el correo provocando un fallo con una configuración de
   prueba reversible del entorno. Verificar recepción y volver a los
   valores válidos antes de repetir la ejecución exitosa.
4. Confirmar que el repositorio admite 90 días de retención de artefactos.
   Los artefactos expiran según la política de GitHub. Una interrupción
   prolongada puede dejar menos de ocho copias. Después de la prueba
   manual, la variable de repositorio `PIGGO_BACKUP_ENABLED=true`
   habilita el horario. Un fallo al enviar el aviso queda registrado
   como un job fallido en GitHub Actions.

## Recuperar una copia

Descargar el artefacto y extraer `piggo-backup.enc`. Iniciar una
instancia local y vacía de Supabase, aplicar Alembic hasta la revisión de
la copia y configurar `PIGGO_RESTORE_DATABASE_URL` con la conexión
local del migrador y `PIGGO_BACKUP_KEY` con la clave de esa copia.
Ejecutar `python infra/jobs/backup_space.py restore piggo-backup.enc`.
El comando requiere loopback y rechaza una base con datos de espacios o
perfiles. Conserva los UUID originales. Para utilizar la copia desde
la aplicación, el acceso de los usuarios y los adjuntos se recuperan
por separado.

El CI realiza una restauración con datos sintéticos sobre un PostgreSQL
desechable y verifica el importe exacto, una cuenta inactiva y que el rol
no lea un segundo espacio ni pueda escribir datos.
