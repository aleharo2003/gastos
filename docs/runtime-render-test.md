# Conexion de FastAPI a Supabase test

La API comprueba al arrancar que puede conectarse con app_runtime y que su rol
efectivo cumple el contrato de permisos. No ejecuta migraciones ni consulta datos
de negocio. La conexion usa el session pooler, puerto 5432, y TLS verify-full.

## Activacion en Render

Primero integrar este cambio y dejar que CI/CD despliegue la API. Sin variables,
el esqueleto conserva el modo sin base. En los logs aparece `Base runtime:
deshabilitada`. Ese modo es transitorio mientras se prepara la configuracion.

En el servicio **gastos-test-api**, configurar un Secret File llamado
`supabase.crt` con el PEM completo descargado de Supabase. Su ruta en Render debe
ser `/etc/secrets/supabase.crt`. Luego agregar juntas estas variables:

| Variable | Valor |
| --- | --- |
| APP_DB_ENABLED | true |
| APP_DB_HOST | aws-1-us-west-2.pooler.supabase.com |
| APP_DB_USER | app_runtime.cyxhyfbiacfayixbmotq |
| APP_DB_PASSWORD | Contraseña remota de app_runtime |
| APP_DB_CA_FILE | /etc/secrets/supabase.crt |

La contraseña se pega literalmente, sin comillas ni codificacion URI. La URL se
construye con URL.create. No copiar credenciales de app_migrator a Render. No
guardar valores secretos en el repositorio, comandos o capturas compartidas.

Guardar la configuracion y desplegar el mismo commit validado. Este paso inicial
de configuracion no reemplaza el pipeline para futuras entregas de codigo.
Mantener Auto-Deploy desactivado. Antes de activar, confirmar que las migraciones
de ese commit ya finalizaron correctamente en GitHub Actions.

## Evidencia esperada

- Logs de arranque: `Base runtime: app_runtime verificado`.
- `/health` responde 200 y `/version` conserva el commit desplegado.
- El recorrido Angular → BFF → API sigue devolviendo el saludo.

Una configuracion parcial, un rol incorrecto o un fallo de conexion impiden el
arranque; el mensaje publico no incluye detalles del driver ni contraseñas.
La comprobacion verifica identidad y privilegios efectivos, no solo SELECT 1.
Se ejecuta en un thread para no bloquear el event loop durante el arranque.

## Limites

`/health` indica que el proceso atiende; no garantiza disponibilidad continua de
la base. Esta comprobacion es de arranque, no una prueba de consultas de negocio
ni de RLS sobre datos reales. El engine se conserva en app.state.runtime_engine
y se cierra al apagar la API; los futuros endpoints deberan utilizar la unidad
de trabajo con identidad verificada y contexto transaccional. No deben usar una
conexion directa para omitir ese contrato.

La prueba real en Render queda pendiente hasta configurar el servicio y guardar
la evidencia del arranque. No cerrar US-009 solo por agregar estas variables.
