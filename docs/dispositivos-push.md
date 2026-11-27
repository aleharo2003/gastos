# Registrar un dispositivo para Web Push

En el BFF del entorno, configurar `PIGGO_VAPID_PUBLIC_KEY` con la clave
pública del par VAPID en base64url sin relleno. Aplicar las migraciones 0055 y 0056
antes de desplegar la API. La clave privada queda reservada para el ejecutor
de entregas.

En Piggo, abrí **Avisos**, elegí **Notificaciones push** como canal y guardá.
Pulsá **Activar en este dispositivo** y aceptá el permiso del navegador.
Para probar la baja, pulsá **Desactivar en este dispositivo**.

El alta vincula el endpoint a una persona, espacio y dispositivo. El estado
devuelto al navegador no incluye el endpoint ni las claves de suscripción.
Si el proveedor devuelve 404 o 410, se elimina esa suscripción. Al tocar el
aviso se abre **Hoy**. El aviso aparece con un texto genérico en la pantalla
bloqueada.

## Probar la entrega en test

El workflow **Avisos push de vencimientos test** consulta cada hora las cuotas
que entran en la ventana de anticipación y respeta el horario de Argentina.
Agrupa los avisos por dispositivo y día. Para habilitarlo, configurá la variable
de repositorio `PIGGO_PUSH_ENABLED=true`. En el entorno `test`, configurá
`PIGGO_VAPID_PRIVATE_KEY` como secreto con la clave privada VAPID de 32 bytes
codificada en base64url sin relleno, y `PIGGO_VAPID_CONTACT` como variable con
un contacto `mailto:`. El ejecutor reutiliza `JOBS_DATABASE_URL`.

Desde **Avisos**, guardá el canal push, un horario que ya haya pasado y una
anticipación que incluya alguna cuota pendiente. Activá el dispositivo y
ejecutá el workflow manualmente para comprobar la recepción. La clave pública
del BFF y la privada del ejecutor deben pertenecer al mismo par.
