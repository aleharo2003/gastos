# Despliegue del entorno de prueba en Render

La API y el BFF ya están publicados. Esta entrega prepara Angular como sitio estático, configura su acceso al BFF e incorpora las comprobaciones correspondientes en CI. La creación del sitio y su prueba desde el celular se harán después de integrar el PR y comprobar el CI de `main`.

Este entorno ejecuta un saludo de prueba. Supabase, autenticación y datos financieros pertenecen a los siguientes incrementos. US-005 y US-009 conservan sus criterios de aceptación pendientes.

## Estado del entorno

| Componente | Estado |
|---|---|
| API | Publicada en `https://gastos-test-api.onrender.com`. |
| BFF | Publicado en `https://gastos-test-bff.onrender.com`. |
| Angular | Configuración preparada en este incremento; sitio pendiente de creación. |
| CI | Comprueba aplicaciones, imágenes de ejecución, comunicación HTTP y configuración del build de prueba de Angular. |
| CD | Pendiente. Los despliegues actuales se controlan manualmente. |
| Base de datos y autenticación | Pendientes de sus stories y ADR. |

La primera publicación de la API ejecutó el commit `619037c`, comprobado contra su [CI de main](https://github.com/aleharo2003/gastos/actions/runs/39335126642). El BFF se publicó con `015cfd4`, también con [CI aprobado](https://github.com/aleharo2003/gastos/actions/runs/39339009294). Son registros de esas entregas; cada despliegue siguiente debe comprobar su propio SHA.

En la comprobación del BFF se observó un primer HTTP 502. Luego, una consulta directa a FastAPI tardó aproximadamente 23 segundos y el siguiente recorrido desde el BFF devolvió HTTP 200 con el mensaje esperado. Es compatible con un arranque en frío; esa observación por sí sola no determina la causa del primer error.

## Orden de despliegue

1. Trabajar en una rama y comprobar el cambio localmente.
2. Subirlo, revisar el PR y esperar CI.
3. Integrarlo en `main` y esperar el CI del commit integrado.
4. Desplegar ese commit y comprobar salud, versión y recorrido HTTP.
5. Si es la primera publicación de Angular, registrar su URL real y configurarla como origen permitido en el BFF.
6. Probar la aplicación desde el navegador y desde el celular.

Mantener Auto-Deploy en Off en los servicios. Al crear un servicio o un sitio nuevo, Render inicia su primer despliegue; por eso se crea después de los pasos de revisión y CI. Para los siguientes despliegues manuales, elegir el SHA aprobado mediante **Manual Deploy → Deploy a specific commit**. Comprobar la versión publicada al terminar.

Cuando exista la base, el orden ordinario será **CI, migraciones, despliegue y verificación**. El saludo actual no requiere migraciones.

## API y BFF: configuración de ejecución

| Campo | API | BFF |
|---|---|---|
| Tipo | Web Service | Web Service |
| Repositorio | `aleharo2003/gastos` | `aleharo2003/gastos` |
| Nombre | `gastos-test-api` | `gastos-test-bff` |
| Rama | `main` | `main` |
| Runtime / Language | Docker | Docker |
| Root Directory | Vacío | Vacío |
| Dockerfile Path | `apps/api/Dockerfile` | `apps/bff/Dockerfile` |
| Docker Build Context Directory | `apps/api` | `apps/bff` |
| Docker Command | Vacío: usa el Dockerfile | Vacío: usa el Dockerfile |
| Instance Type | Free | Free |
| Health Check Path | `/health` | `/health` |
| Auto-Deploy | Off | Off |

Los servidores escuchan en `0.0.0.0` y usan `PORT`, proporcionado por Render. Las imágenes incluyen el código y arrancan sin recarga automática, con usuarios sin privilegios de administrador. La imagen del BFF compila TypeScript en una etapa y copia el resultado a la etapa de ejecución.

| Variable del BFF | Valor o función |
|---|---|
| `API_BASE_URL` | `https://gastos-test-api.onrender.com` |
| `API_TIMEOUT_MS` | `120000`: límite de espera de su consulta a FastAPI. Localmente, el predeterminado es `5000`. |
| `FRONTEND_ORIGIN` | URL de origen real de Angular. Se configura después de crear el sitio. |
| `PORT` | Puerto del proceso, proporcionado por Render. |
| `RENDER_GIT_COMMIT` | SHA proporcionado por Render; el BFF lo publica en `/version`. |

`API_TIMEOUT_MS` debe ser un entero positivo. `FRONTEND_ORIGIN`, si está definida, debe ser un origen HTTP(S) completo, sin ruta, credenciales, parámetros ni barra final. Un valor inválido impide arrancar y permite detectar la configuración incorrecta durante el despliegue.

El BFF permite leer sus respuestas desde el origen configurado y admite los métodos GET y HEAD de este incremento. No habilita credenciales CORS. Si la variable está ausente, no habilita CORS. El desarrollo local sigue usando el proxy, que no requiere ese permiso entre orígenes.

CORS lo aplica el navegador; no reemplaza autenticación ni autorización. La conexión entre el BFF y FastAPI es una consulta entre servidores y no necesita CORS.

## Angular: configuración del build

| Archivo o comando | Responsabilidad |
|---|---|
| `src/environments/environment.ts` | Dirección relativa del BFF y espera local de 10 segundos. |
| `src/environments/environment.remote.ts` | Dirección pública `https://gastos-test-bff.onrender.com` y espera de 180 segundos. |
| `npm run build:test` | Aplica las configuraciones `production,test` y luego genera `version.json`. |
| `infra/build/write-web-version.mjs` | Comprueba la salida del build y escribe el SHA de Render, el de GitHub Actions o `null`. |

El componente importa el archivo base y el build de prueba lo reemplaza. `production` indica opciones de compilación; el entorno de despliegue sigue siendo **test**. Los proxies del servidor de desarrollo no se ejecutan en el sitio estático publicado.

Las direcciones de los servicios, los tiempos de espera y el SHA del build son datos públicos. No incluir contraseñas, claves privadas ni secretos de los servidores en los archivos de Angular o en su build.

## Angular: configuración prevista en Render

Crear un **Static Site**, después de integrar este cambio y comprobar el CI de `main`.

| Campo | Valor |
|---|---|
| Repositorio | `aleharo2003/gastos` |
| Nombre sugerido | `gastos-test-web`, sujeto a disponibilidad |
| Rama | `main` |
| Root Directory | Vacío |
| Build Command | `npm --prefix apps/web ci --include=dev && npm --prefix apps/web run build:test` |
| Publish Directory | `apps/web/dist/gastos-web/browser` |
| Auto-Deploy | Off |

La raíz vacía permite usar `.nvmrc`, que fija Node `24.22.0`, y acceder al generador de versión dentro de `infra/build/`. La carpeta publicada es la que contiene `index.html`. El comando instala también las herramientas de compilación, porque Angular las necesita durante el build.

Agregar la variable de build `SKIP_INSTALL_DEPS=true`. Así Render deja la instalación de dependencias a nuestro `npm ci` y evitamos una instalación automática adicional. `RENDER_GIT_COMMIT` lo proporciona Render; no hay que escribirlo manualmente.

En **Redirects/Rewrites**, agregar:

| Source | Destination | Action |
|---|---|---|
| `/*` | `/index.html` | Rewrite |

Esto entrega la aplicación al recargar futuras rutas del navegador. No cambia el destino del BFF: la configuración de prueba de Angular ya usa su dirección HTTPS pública.

En **Headers**, agregar:

| Path | Header | Value |
|---|---|---|
| `/version.json` | `Cache-Control` | `no-store` |

El encabezado evita conservar la respuesta de versión en caché cuando comprobamos un despliegue. El resto de los archivos conserva el comportamiento de caché de la plataforma.

Si Auto-Deploy no aparece en el formulario inicial, establecer Off desde Settings después de crear el sitio. Elegir el servicio de sitio estático gratuito y revisar los importes que muestre la cuenta antes de confirmar una opción adicional.

## Registrar el origen de Angular y publicar el BFF

1. Esperar a que el sitio termine su primer despliegue y copiar la URL real asignada por Render.
2. En las variables del BFF, asignar esa dirección a `FRONTEND_ORIGIN`, sin barra final. No utilizar un nombre supuesto ni `*`.
3. Elegir **Save only** para guardar la variable y después usar **Manual Deploy → Deploy a specific commit** con el SHA aprobado en CI. La variable se aplicará en ese despliegue.
4. Mantener Auto-Deploy en Off y comprobar `/version` del BFF después del despliegue.
5. Entrar al sitio de Angular y pulsar el botón para verificar el recorrido.

La configuración CORS nueva debe estar en el BFF desplegado para que `FRONTEND_ORIGIN` tenga efecto. No basta con agregar la variable a la versión anterior del BFF.

## Comprobaciones de cada entrega

La API y el BFF tienen `/health` y `/version`. Salud devuelve `{"status":"ok"}` cuando ese proceso atiende solicitudes; no comprueba todas sus dependencias. Versión devuelve el SHA ejecutado y solicita no guardar la respuesta en caché. La salud del BFF no consulta ni despierta FastAPI.

El sitio estático publica `/version.json`. Comparar su SHA con el commit que terminó CI y fue desplegado. Abrirlo en el navegador no comprueba que Angular funcione: también hay que pulsar el botón y observar el resultado.

La prueba del recorrido completo debe verificar:

- Carga de Angular por HTTPS y versión esperada del sitio.
- Botón, espera visible y mensaje `Hola desde FastAPI`.
- Solicitud al BFF real, con permiso CORS para el origen del sitio.
- Acceso desde el celular.
- Comportamiento después del reposo y posibilidad de volver a consultar después de un error.

Las pruebas locales y CI usan servicios aislados. No envían solicitudes periódicas a Render para evitar el reposo.

## Límites de Free y trabajo pendiente

Render Free suspende los servicios web después de 15 minutos sin tráfico. Despertar un servicio puede requerir aproximadamente un minuto; el BFF y FastAPI duermen por separado. El sitio estático se distribuye por CDN y no utiliza esos procesos para servir sus archivos.

La consulta de Angular admite hasta tres minutos, y la llamada del BFF a FastAPI hasta dos. Son límites de espera, no una promesa de éxito del primer acceso. El BFF valida estado HTTP y contenido de FastAPI; errores de red, timeout, HTTP de error o contenido inválido producen su HTTP 502 controlado. El usuario puede volver a consultar; no se agregan reintentos automáticos en este incremento.

Las 750 horas gratuitas de los servicios web se comparten en el workspace. No mantenerlos despiertos mediante pings. BFF y API usan HTTPS público porque las instancias Free no reciben tráfico privado. El sitio estático consume las cuotas de transferencia y de construcción de la cuenta.

Faltan la publicación del sitio, las verificaciones de navegador y celular, el CD desde GitHub y los criterios restantes de las stories. Este entorno de prueba no determina todavía el alojamiento final de producción.

## Referencias

- [Configuraciones y archivos de entorno de Angular](https://angular.dev/tools/cli/environments).
- [Publicación de Angular y rutas del navegador](https://angular.dev/tools/cli/deployment).
- [Sitios estáticos de Render](https://render.com/docs/static-sites).
- [Instalación de dependencias en sitios estáticos](https://render.com/docs/static-sites#dependency-installation).
- [Node en Render](https://render.com/docs/node-version).
- [Rutas de monorepos](https://render.com/docs/monorepo-support).
- [Redirects y rewrites](https://render.com/docs/redirects-rewrites).
- [Encabezados de sitios estáticos](https://render.com/docs/static-site-headers).
- [CORS en Nest](https://docs.nestjs.com/security/cors).
- [Variables de Render](https://render.com/docs/environment-variables).
- [Guardar variables y elegir cuándo desplegarlas](https://render.com/changelog/specify-deploy-behavior-when-modifying-environment-variables).
- [Límites de Free](https://render.com/docs/free).
- [Despliegues de Render](https://render.com/docs/deploys).
