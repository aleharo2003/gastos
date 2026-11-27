# Piloto de correo en test

La migración 0028 agrega un ejecutor limitado a una membresía de prueba. El workflow manual **Piloto de correo de Piggo** corre desde `main` y usa el entorno `test`.

1. Aplicá la migración 0028 en la base de test. Como administrador de PostgreSQL, ejecutá `psql -X --file infra/postgres/provision-email-pilot.sql` conectado a esa base. El script pide la contraseña del rol `app_email_jobs` de forma interactiva.
2. Conectado como `app_migrator`, ejecutá `infra/postgres/grant-email-pilot.sql` y configurá la membresía de la cuenta que recibirá la prueba. Usá los UUID de esa cuenta y de su espacio de test.

   ```sql
   INSERT INTO public.piloto_avisos_email (id, usuario_id, espacio_id)
   VALUES (1, '<UUID del usuario>', '<UUID del espacio>')
   ON CONFLICT (id) DO UPDATE SET
       usuario_id = EXCLUDED.usuario_id, espacio_id = EXCLUDED.espacio_id;
   ```

3. En el entorno `test` de GitHub Actions, configurá las variables `PILOT_SUPABASE_PROJECT_REF`, `PILOT_SUPABASE_PUBLISHABLE_KEY`, `PILOT_USER_ID`, `PILOT_SPACE_ID`, `PILOT_APP_URL` y `PILOT_FROM_EMAIL`. Agregá los secretos `PILOT_DATABASE_URL` del rol dedicado, `PILOT_SUPABASE_ACCESS_TOKEN` de la sesión vigente de esa cuenta, `PILOT_EMAIL` del correo confirmado y `RESEND_API_KEY` del remitente de prueba. Usá TLS para el DSN.
4. En Piggo test, configurá correo como canal en **Avisos** y comprobá que haya una cuota elegible según los días de anticipación y el horario argentino. Ejecutá primero `preview` para ver la cantidad. Cuando quieras enviar un único recordatorio de prueba, ejecutá `send`.

La vista previa no crea registros ni contacta a Resend. El resultado `aceptada` confirma que Resend recibió el pedido. Comprobá la llegada en la bandeja del correo configurado.

## Resumen semanal

Aplicá las migraciones 0053 y 0054. En **Avisos**, elegí correo, activá **Resumen semanal** y elegí el día. El día inicial es lunes.
`preview-weekly` comprueba que el resumen se puede preparar y registra el estado
sin publicar importes en Actions. `send-weekly` usa el día y la hora argentinos que guardaste
en **Avisos** y permite probar el envío para la misma cuenta y espacio del piloto.

El correo reúne los gastos de lunes a domingo de la última semana cerrada,
compara con el límite semanal vigente y lista los próximos siete días. Se
reserva un envío por semana. Una respuesta definitiva de límite de solicitudes
permite reintentar. Una respuesta incierta conserva la reserva para evitar
duplicados. El envío programado queda pendiente de la validación del piloto.
