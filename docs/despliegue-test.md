# Despliegue de prueba en Render

La API ya está publicada. Esta entrega prepara la imagen del BFF y sus comprobaciones; el servicio del BFF se creará después de integrar el cambio y verificar CI en `main`. Angular y el CD automático siguen pendientes.

Se aplica a US-005 y la primera entrega de US-009. El entorno todavía usa un saludo de prueba, sin Supabase, autenticación ni datos financieros.

## Estado del entorno

| Componente | Estado |
|---|---|
| API | Publicada en `https://gastos-test-api.onrender.com`. |
| BFF | Imagen y configuración preparadas en esta entrega. Pendiente de publicación. |
| Angular | Pendiente de preparación y publicación. |
| CI | Comprueba cada cambio; esta entrega incorpora la imagen del BFF y el recorrido entre las imágenes de ejecución. |
| CD | Pendiente. Los despliegues actuales se controlan manualmente. |
| Base de datos y autenticación | Pendientes de sus stories y ADR correspondientes. |

En la primera publicación de la API se comprobaron `/`, `/health` y `/version`. La versión observada fue `619037c`, coincidente con el commit de `main` validado por [GitHub Actions](https://github.com/aleharo2003/gastos/actions/runs/39335126642). Es un registro de esa entrega: los siguientes despliegues tendrán su propio SHA.

El servicio `gastos-test-api` tiene Auto-Deploy en Off. Un servicio activo continúa atendiendo solicitudes aunque se desactive el despliegue automático.

## Orden del trabajo

1. Sincronizar la copia local con `main` y crear una rama para el BFF.
2. Ejecutar las pruebas del BFF y construir las imágenes de ejecución de API y BFF.
3. Probar respuesta, caída de la API y recuperación usando esas imágenes, sin montajes del código local.
4. Subir el cambio, comprobar CI y fusionar el PR en `main`.
5. Esperar el CI de ese commit de `main` y recién entonces crear el servicio Free del BFF.
6. Comprobar salud, versión y comunicación con la API publicada.
7. Preparar Angular y probar el recorrido remoto completo, incluido el acceso desde celular y el comportamiento después del reposo.
8. Incorporar el despliegue automático desde GitHub para un commit validado.

Crear un servicio en Render inicia su primer build y despliegue. Por eso el nuevo servicio se crea cuando el código ya está en `main` y su CI pasó. Configurar Auto-Deploy en Off evita que los siguientes cambios se publiquen por fuera del orden acordado.

Cuando exista la base, el orden ordinario será CI, migraciones, despliegue y verificación. El saludo actual no requiere migraciones.

## Imágenes para ejecutar la aplicación

`Dockerfile.dev` conserva la recarga automática para programar. Los nuevos `Dockerfile` incluyen el código dentro de la imagen y arrancan los servidores sin recarga.

La imagen del BFF se construye en dos etapas. La primera instala las dependencias y compila TypeScript. La segunda instala las dependencias necesarias para ejecutar el programa y copia el resultado compilado. Arranca con Node y un usuario sin privilegios de administrador.

El BFF escucha en `0.0.0.0` y utiliza el puerto indicado por `PORT`. Render proporciona esa variable; la aplicación conserva el puerto local predeterminado para desarrollo.

## Configuración del BFF

| Variable | Uso |
|---|---|
| `API_BASE_URL` | Dirección de FastAPI a la que consulta el BFF. En Render usa la URL HTTPS pública de la API. |
| `API_TIMEOUT_MS` | Límite de espera de la llamada a FastAPI, en milisegundos. El valor predeterminado local es 5000; en Render se configura 120000. |
| `PORT` | Puerto del servidor. Lo proporciona Render. |
| `RENDER_GIT_COMMIT` | Commit que devuelve `/version`. Lo proporciona Render cuando construye desde Git. |

`API_TIMEOUT_MS` debe ser un entero positivo. El arranque debe señalar un valor inválido para poder corregir la configuración. No contiene una credencial.

El BFF valida el estado HTTP y el contenido de la respuesta de FastAPI. Un error de red, un timeout, un HTTP de error o un contenido inválido se convierten en su error controlado HTTP 502. Ampliar el tiempo de espera no garantiza que toda llamada durante un arranque en frío termine correctamente.

El BFF no reintenta automáticamente la solicitud en esta entrega. Si falla, el usuario puede volver a consultar cuando los servicios estén disponibles.

## Salud y versión

Ambos servidores exponen:

- `/health`: devuelve HTTP 200 con `{"status":"ok"}` cuando ese proceso atiende solicitudes.
- `/version`: devuelve el commit que informa `RENDER_GIT_COMMIT`. Sin esa variable, devuelve `{"commit":null}`. No publica las demás variables del servicio y solicita no guardar la respuesta en caché.

La salud del BFF no consulta FastAPI. Esto permite distinguir un BFF funcionando de una API que está dormida o caída. La comunicación entre ambos se verifica por separado mediante `/api/hello`.

## Prueba local de las imágenes de ejecución

Ejecutar desde la raíz del repositorio:

```bash
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml config --quiet
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml up --detach --build

python3 infra/ci/check-stack.py success --url http://127.0.0.1:18001/api/hello

curl --fail --silent --show-error http://127.0.0.1:18001/health
curl --fail --silent --show-error http://127.0.0.1:18001/version
```

Esta configuración utiliza API en `127.0.0.1:18000` y BFF en `127.0.0.1:18001`, con puertos diferentes de los servicios habituales de desarrollo. No incluye Angular ni monta el código local. La primera consulta espera a que el recorrido HTTP esté listo; tener un contenedor iniciado no significa que ya atienda solicitudes.

Sin `RENDER_GIT_COMMIT`, la versión local es `null`. En CI se asigna el SHA del workflow a ambos servicios para comprobar la versión ejecutada.

Probar la caída y la recuperación:

```bash
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml stop api
python3 infra/ci/check-stack.py unavailable --url http://127.0.0.1:18001/api/hello

docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml start api
python3 infra/ci/check-stack.py success --url http://127.0.0.1:18001/api/hello
```

La prueba de indisponibilidad pasa cuando recibe el error esperado HTTP 502 del BFF. La recuperación debe funcionar sin reiniciar el BFF.

Para retirar únicamente este entorno de prueba:

```bash
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml down
```

Si una comprobación falla, revisar los logs de este mismo proyecto y volver a iniciar la API antes de repetirla:

```bash
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml logs --tail=100
```

## Configuración de los servicios en Render

La API ya existe. La tabla del BFF registra lo que deberá usarse después de integrar este incremento; no implica que el servicio ya esté creado.

| Campo | API existente | BFF por crear |
|---|---|---|
| Tipo | Web Service | Web Service |
| Origen | Git Provider | Git Provider |
| Repositorio | `aleharo2003/gastos` | `aleharo2003/gastos` |
| Nombre | `gastos-test-api` | `gastos-test-bff`, sujeto a disponibilidad |
| Rama | `main` | `main` |
| Runtime / Language | Docker | Docker |
| Root Directory | Vacío | Vacío |
| Dockerfile Path | `apps/api/Dockerfile` | `apps/bff/Dockerfile` |
| Docker Build Context Directory | `apps/api` | `apps/bff` |
| Instance Type | Free | Free |
| Health Check Path | `/health` | `/health` |
| Auto-Deploy | Off | Off |
| Docker Command | Vacío: usa el Dockerfile | Vacío: usa el Dockerfile |
| `API_BASE_URL` | No aplica | `https://gastos-test-api.onrender.com` |
| `API_TIMEOUT_MS` | No aplica | `120000` |

Elegir el tipo de instancia Free y revisar el costo que muestra el formulario. El plan del workspace y el cómputo de un servicio son conceptos distintos.

Registrar la URL real que Render asigne al BFF. Comprobar `/health`, `/version` y `/api/hello`; comparar el SHA con el commit validado de `main`. La ruta `/` conserva el saludo propio del BFF y por sí sola no demuestra comunicación con FastAPI.

## Límites y trabajo pendiente

Render Free suspende cada servicio tras 15 minutos sin tráfico. El siguiente acceso puede requerir aproximadamente un minuto para despertarlo. Con BFF y API dormidos, las esperas pueden acumularse. Las 750 horas gratuitas se comparten entre los servicios del workspace; no se agrega un ping para mantenerlos activos.

BFF y API se comunican mediante HTTPS público, porque los servicios Free no reciben tráfico por la red privada. La conexión del BFF a la API no necesita CORS.

Angular todavía utiliza un tiempo de espera local de 10 segundos y su proxy de desarrollo. Antes de publicarlo deben resolverse su dirección de BFF, el acceso entre orígenes si corresponde y el tiempo de espera del recorrido completo. Este incremento no habilita CORS general ni garantiza que el primer acceso tras el reposo funcione sin reintentar.

Las comprobaciones HTTP no abren un navegador ni ejecutan el botón de Angular. La publicación del frontend, la prueba desde celular y el CD siguen pendientes. US-005 y US-009 conservan sus criterios de aceptación restantes.

## Referencias

- [Servicios web y configuración del puerto](https://render.com/docs/web-services).
- [Rutas de Docker en un monorepo](https://render.com/docs/monorepo-support#root-relative-settings).
- [Variables de Render](https://render.com/docs/environment-variables).
- [Health checks](https://render.com/docs/health-checks).
- [Límites de Free](https://render.com/docs/free).
- [Configuración de Auto-Deploy](https://render.com/docs/deploys#configuring-auto-deploys).
