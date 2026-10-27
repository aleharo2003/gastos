# Despliegue del entorno de prueba en Render

Angular, el BFF y la API están publicados en Render. El recorrido «Consultar mensaje» se comprobó en el navegador y desde un celular. Este documento conserva la configuración de los servicios; [CD de test](cd-test.md) explica cómo GitHub automatiza las siguientes entregas.

Este entorno ejecuta un saludo de prueba. Supabase, autenticación y datos financieros pertenecen a los siguientes incrementos. US-005 y US-009 conservan sus criterios de aceptación pendientes.

## Estado del entorno

| Componente | Estado |
|---|---|
| API | Publicada en `https://gastos-test-api.onrender.com`. |
| BFF | Publicado en `https://gastos-test-bff.onrender.com`. |
| Angular | Publicado en `https://gastos-test-web.onrender.com`. |
| CI | Comprueba aplicaciones, imágenes de ejecución, comunicación HTTP y configuración del build de prueba de Angular. |
| CD | Configuración incorporada; primera ejecución real pendiente de configurar GitHub e integrar el cambio. |
| Base de datos y autenticación | Pendientes de sus stories y ADR. |

La primera publicación de la API ejecutó el commit `619037c`, comprobado contra su [CI de main](https://github.com/aleharo2003/gastos/actions/runs/39335126642). Al publicar Angular y habilitar CORS se comprobó `aff2bbee` en el sitio y el BFF, con [CI aprobado](https://github.com/aleharo2003/gastos/actions/runs/39483975917). Son registros de esas entregas; cada despliegue siguiente debe comprobar su propio SHA.

Durante las comprobaciones se observó un primer HTTP 502 y una consulta posterior correcta. Es compatible con un arranque en frío; esa observación por sí sola no determina la causa del primer error. El éxito posterior y la prueba desde el celular no completan la validación controlada del primer acceso tras reposo.

## Orden de despliegue

1. Trabajar en una rama, comprobar el cambio localmente y abrir el PR.
2. Revisar el cambio y esperar CI antes de integrarlo en `main`.
3. GitHub repite CI sobre el commit integrado y habilita la entrega de test cuando aprueban los cinco trabajos de comprobación, incluida la reconstrucción de la base desechable.
4. El trabajo de despliegue comprueba `main` y los destinos, publica API, BFF y Angular con ese SHA y verifica cada uno antes de continuar.
5. Revisar el resumen de Actions y probar la aplicación en el navegador; repetir desde el celular cuando cambie la experiencia de uso.

Antes de la primera ejecución automática, configurar el environment `test`, sus variables y su secreto según [CD de test](cd-test.md). Mantener Auto-Deploy en Off en los tres servicios. La recuperación manual usa **Manual Deploy → Deploy a specific commit**, eligiendo un SHA aprobado y comprobando el conjunto de versiones; no ejecutarla mientras haya una entrega automática activa.

Si se recrea un servicio, Render inicia su primer despliegue al crearlo. Preparar esa configuración después de revisión y CI, actualizar su ID en GitHub y volver a verificar la conexión entre los componentes.

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
| `FRONTEND_ORIGIN` | `https://gastos-test-web.onrender.com`, sin barra final. |
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

## Angular: configuración en Render

El sitio existente es un **Static Site**. Estos valores permiten revisar su configuración o recrearlo cuando corresponda.

| Campo | Valor |
|---|---|
| Repositorio | `aleharo2003/gastos` |
| Nombre | `gastos-test-web` |
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

## Cambios del origen de Angular

Si cambia el dominio del sitio, actualizar `FRONTEND_ORIGIN` en el BFF, sin barra final. Actualizar también la URL de web en `infra/cd/render-test.json` y el enlace del environment en el workflow. Revisar los campos de CORS de CI si cambia ese contrato.

Guardar la variable con **Save only** y coordinar la siguiente entrega del SHA aprobado para que se aplique. La comprobación pública exige ese origen exacto. Cambiar una variable de Render no modifica el código del repositorio ni garantiza por sí solo que se haya desplegado.

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

Faltan la primera ejecución real de CD desde GitHub, la comprobación controlada tras reposo y los criterios restantes de las stories. Las verificaciones HTTP del despliegue no ejecutan Angular en un navegador. Este entorno de prueba no determina todavía el alojamiento final de producción.

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
