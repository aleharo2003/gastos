# Piloto de Piggo en Cloud Run

NestJS recibe las solicitudes HTTPS. FastAPI corre en el mismo servicio, en otro contenedor, y NestJS lo consulta por `127.0.0.1:8000`. Cloud Run comprueba `/health` de FastAPI antes de arrancar NestJS. FastAPI comprueba la conexión y el rol de PostgreSQL antes de empezar a servir solicitudes.

El piloto empieza con facturación por solicitud, cero instancias mínimas y un máximo de dos. El primer acceso después de escalar a cero puede tardar más. Si la latencia medida lo justifica, estimar el costo de mantener una instancia mínima con **ambos** contenedores antes de habilitarla.

## Preparar la revisión

1. Elegir un proyecto de Google Cloud con facturación vinculada y una región cercana al PostgreSQL de Supabase. Habilitar Cloud Run, Cloud Build, Artifact Registry y Secret Manager.
2. Crear un repositorio Docker en Artifact Registry. Preparar una cuenta de servicio dedicada para el runtime. Darle `roles/secretmanager.secretAccessor` sobre los tres secretos del manifiesto. La identidad de Cloud Build debe poder escribir en Artifact Registry y la identidad que despliega debe poder usar la cuenta de runtime.
3. Crear la versión `1` de los secretos `piggo-db-password`, `piggo-storage-service-key` y `piggo-supabase-ca`. Usar las credenciales del entorno de prueba, la clave de Storage que espera FastAPI y el mismo certificado PEM de Supabase que verifica PostgreSQL. Si los secretos ya existen, ajustar la plantilla a las versiones elegidas. Cargar los valores directamente en Secret Manager.
4. Desde un checkout limpio, construir los dos Dockerfiles existentes enviando por separado los directorios `apps/bff` y `apps/api` a Cloud Build. Etiquetar ambas imágenes con el SHA que se va a probar y usar sus referencias por digest en la plantilla.

```powershell
$piggoProject = 'ID_DEL_PROYECTO'
$piggoRegion = 'REGION'
$piggoRepository = 'REPOSITORIO_DOCKER'
$piggoCommit = git rev-parse HEAD
$piggoImages = "${piggoRegion}-docker.pkg.dev/${piggoProject}/${piggoRepository}"

gcloud builds submit apps/bff --project $piggoProject --region $piggoRegion --tag "${piggoImages}/bff:${piggoCommit}"
gcloud builds submit apps/api --project $piggoProject --region $piggoRegion --tag "${piggoImages}/api:${piggoCommit}"
```

5. Copiar `service.yaml` a `service.local.yaml` fuera del repositorio. Reemplazar todos los valores `PIGGO_*` con las referencias a las imágenes, la cuenta de runtime, el origen exacto del frontend de prueba, el project ref de Supabase, el SHA y el host y usuario actuales de PostgreSQL. El origen es una URL sin ruta ni barra final. Mantener el rol de runtime de alcance limitado y la verificación TLS.
6. Validar la especificación antes de desplegar. Tras verificar que Cloud Run reporta la revisión lista, habilitar la invocación pública del servicio de prueba para Angular. Los endpoints de usuario conservan la autenticación de Piggo y FastAPI sigue accesible por la red local de la instancia.

```powershell
gcloud run services replace service.local.yaml --project $piggoProject --region $piggoRegion --dry-run
gcloud run services replace service.local.yaml --project $piggoProject --region $piggoRegion
gcloud run services update piggo-pilot --project $piggoProject --region $piggoRegion --no-invoker-iam-check
gcloud run services describe piggo-pilot --project $piggoProject --region $piggoRegion --format 'value(status.url)'
```

## Validar antes de cambiar Angular en Render

- Apuntar una compilación de prueba de Angular a la URL del piloto mediante `apps/web/src/environments/environment.remote.ts`. Configurar el origen de esa compilación en Cloud Run y verificar que Supabase Auth permite su URL de retorno.
- Confirmar HTTP 200 en `/health` y `/api/hello`, el SHA esperado en `/version` y HTTP 401 en `/api/me` sin sesión.
- Con una cuenta de prueba, iniciar sesión, cargar el espacio, registrar un gasto y comprobar que aparece en Movimientos. Verificar también un comprobante de prueba.
- Repetir la prueba inicial tras un período sin tráfico y confirmar en los logs si arrancó una instancia nueva. Medir la primera respuesta y la siguiente. Si falla, revisar el inicio de FastAPI, su conexión a Supabase y la solicitud autenticada en los logs de la misma revisión.
- Cuando las pruebas pasen, configurar el origen habitual de Angular en Cloud Run y publicar el cambio de URL en Angular. Para revertir, volver a publicar Angular con la URL del BFF de Render. Mantener disponible el despliegue de Render hasta terminar la verificación.

Referencias: [servicios con varios contenedores](https://docs.cloud.google.com/run/docs/deploying#sidecars), [Secret Manager en Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets) y [precios de Cloud Run](https://cloud.google.com/run/pricing).
