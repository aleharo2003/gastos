# Registrar un dispositivo para Web Push

En el BFF del entorno, configurar `PIGGO_VAPID_PUBLIC_KEY` con la clave
pública del par VAPID en base64url sin relleno. Aplicar la migración 0055
antes de desplegar la API. La clave privada queda reservada para el ejecutor
de entregas.

En Piggo, abrí **Avisos**, elegí **Notificaciones push** como canal y guardá.
Pulsá **Activar en este dispositivo** y aceptá el permiso del navegador.
Para probar la baja, pulsá **Desactivar en este dispositivo**.

El alta vincula el endpoint a una persona, espacio y dispositivo. El estado
devuelto al navegador no incluye el endpoint ni las claves de suscripción.
La recepción de avisos, la apertura de Hoy y la limpieza automática de
suscripciones vencidas quedan para la etapa de entrega.
