# Proceso diario de Piggo en test

GitHub Actions ejecuta el proceso desde `main`, con el entorno `test`.
Las tareas se conectan a PostgreSQL con `JOBS_DATABASE_URL`. La actualización
de cotizaciones también consulta DolarApi.

- A las 01:29 de Buenos Aires genera las cuotas del mes que faltan, marca las
  cuotas vencidas y actualiza las cotizaciones.
- A las 19:42 refresca las cotizaciones después de la jornada.
- En **Actions → Proceso diario de Piggo → Run workflow**, se pueden ejecutar
  todas las tareas o elegir una por separado.

Si una tarea falla, se ejecutan las restantes y el resultado general queda
en rojo. El resumen identifica cada tarea fallida. Se puede reintentar la
ejecución completa o la tarea afectada. Los reintentos conservan las cuotas
ya generadas y la fecha de vencimiento registrada.

Para recibir un correo de fallo en el entorno `test`, configurá los secretos
`PIGGO_DAILY_ALERT_EMAIL` y `RESEND_API_KEY`, más la variable
`PIGGO_DAILY_FROM_EMAIL` con un remitente verificado. El correo incluye el
enlace a la ejecución. GitHub también puede avisar de fallos según las
[preferencias de notificación de Actions](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs).

El [piloto de recordatorios por correo](piloto-correo.md) se sigue ejecutando
manualmente con una sesión válida de la cuenta de prueba.
