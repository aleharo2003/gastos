# Gastos

Aplicación de finanzas personales para uso familiar, aprendizaje y enseñanza. El primer incremento conecta Angular, un BFF en NestJS y una API en FastAPI.

## Estado actual

El recorrido funciona en desarrollo con Docker Compose. El CI ejecuta las pruebas y compilaciones de Angular y BFF, comprueba dependencias y sintaxis de Python, y construye los contenedores para probar la comunicación HTTP, la caída de FastAPI y la recuperación.

El entorno de prueba está publicado en Render: [Angular](https://gastos-test-web.onrender.com), [BFF](https://gastos-test-bff.onrender.com) y [API](https://gastos-test-api.onrender.com). El recorrido también se comprobó desde un celular. La [primera ejecución real de CD](https://github.com/aleharo2003/gastos/actions/runs/39502412899) publicó y verificó el mismo commit en los tres servicios. US-006 incorpora ahora Supabase local y prepara los roles de acceso; faltan la persistencia de la aplicación, autenticación, migraciones y datos iniciales.

Los archivos `Dockerfile.dev` sirven para programar. FastAPI y BFF disponen además de un `Dockerfile` para ejecutar imágenes sin recarga automática. El CI prueba esas imágenes sin montar el código del equipo.

## Requisitos

- Docker con el complemento Docker Compose.
- En Windows: WSL 2 con Ubuntu y Docker Desktop iniciado, con la integración de Ubuntu habilitada.
- Repositorio guardado en el sistema de archivos de Linux, por ejemplo `~/projects/gastos`.
- Conexión a Internet para descargar imágenes y dependencias durante la primera construcción.

Las imágenes utilizan Node.js 24.22.0 y Python 3.14.4. Las dependencias se instalan dentro de las imágenes usando `package-lock.json` y `requirements.txt`. Para este arranque se utiliza Docker, sin activar la `.venv` ni instalar dependencias en el host.

## Iniciar el entorno

Desde Ubuntu, en la raíz del repositorio:

```bash
cd ~/projects/gastos
docker compose config --quiet
docker compose up --build
```

Si la comprobación de configuración informa un error, corregirlo antes de ejecutar `up`. La primera construcción descarga las imágenes e instala dependencias.

Esperar los mensajes de inicio de los tres servicios. `depends_on` establece el orden de arranque, pero no comprueba que cada servidor esté listo.

| Componente | Dirección desde el navegador |
|---|---|
| Aplicación | http://localhost:4200/ |
| Recorrido completo a través del proxy | http://localhost:4200/api/hello |
| BFF | http://localhost:3000/ |
| BFF consultando la API | http://localhost:3000/api/hello |
| FastAPI | http://localhost:8000/ |
| Documentación de FastAPI | http://localhost:8000/docs |

Los puertos se publican en `127.0.0.1`, para acceder desde el equipo de desarrollo. Detener los servidores nativos que estén usando esos puertos antes de iniciar los contenedores.

## Recorrido de una petición

1. El servidor `web` entrega Angular al navegador, donde se ejecuta la aplicación.
2. El botón «Consultar mensaje» hace un GET a `/api/hello` sobre el origen del frontend.
3. El proxy del servidor de desarrollo reenvía la petición a `http://bff:3000/api/hello`.
4. NestJS consulta `http://api:8000/` y valida la respuesta.
5. El BFF devuelve el mensaje y Angular lo muestra.

`api`, `bff` y `web` son nombres de servicio en la red de Compose. El navegador utiliza `localhost`, mientras que los contenedores se comunican por esos nombres.

El BFF recibe `API_BASE_URL=http://api:8000` mediante `compose.yml`. Angular utiliza `src/proxy.docker.conf.json` al arrancar dentro de Docker. El archivo `src/proxy.conf.json` conserva la dirección del BFF para ejecutar Angular directamente en Ubuntu.

Estos proxies pertenecen al servidor de desarrollo. En el sitio publicado, Angular consulta la URL HTTPS del BFF configurada en el build de test.

## Comprobar el funcionamiento

Abrir la aplicación y pulsar «Consultar mensaje». Debe aparecer el mensaje generado por FastAPI.

Para probar la recuperación, abrir otra terminal en la raíz del repositorio:

```bash
docker compose stop api
```

Volver a pulsar el botón. El BFF debe responder con HTTP 502 y Angular debe mostrar un aviso de error.

```bash
docker compose start api
```

Esperar que FastAPI termine de iniciar y repetir la consulta. Debe recuperarse sin reiniciar Angular ni el BFF.

## Prueba HTTP de integración

El script `infra/ci/check-stack.py` utiliza solo la biblioteca estándar de Python. Desde otra terminal en la raíz del repositorio, con los contenedores iniciados:

```bash
python3 infra/ci/check-stack.py success
docker compose stop api
python3 infra/ci/check-stack.py unavailable
docker compose start api
python3 infra/ci/check-stack.py success
```

Ejecutar los comandos uno por uno. Si falla una comprobación, revisar el mensaje y los logs antes de continuar. Si FastAPI quedó detenido durante la prueba, iniciarlo otra vez con `docker compose start api`.

La primera y última comprobación reintentan durante aproximadamente 120 segundos para que el recorrido responda HTTP 200 con el mensaje de FastAPI. Una solicitud en curso puede tardar hasta diez segundos adicionales. La comprobación intermedia exige el HTTP 502 y el JSON de error que genera el BFF; no acepta cualquier error del proxy.

El script devuelve código de salida 0 cuando la comprobación pasa y 1 cuando falla. GitHub utiliza ese resultado para decidir si el paso pasó o falló. La dirección predeterminada es `http://127.0.0.1:4200/api/hello`; se puede cambiar con `--url`.

El trabajo `Integracion HTTP con Docker` repite este recorrido en una máquina temporal de CI. Al finalizar muestra los logs y elimina sus contenedores y red con `docker compose down`.

Esta prueba comprueba HTTP a través del servidor web, su proxy, el BFF y FastAPI. No ejecuta Angular en un navegador ni pulsa el botón. Las pruebas del navegador se incorporarán por separado.

## Editar y comprobar la recarga

Editar desde VS Code conectado a WSL. Los montajes son de solo lectura para el contenedor; los archivos se editan normalmente desde Ubuntu.

| Servicio | Código montado | Comprobación manual |
|---|---|---|
| `api` | `apps/api/app` | Cambiar el mensaje de FastAPI y volver a consultar desde Angular. |
| `bff` | `apps/bff/src` | Cambiar temporalmente el saludo de `getHello()` y consultar el puerto 3000. Restaurar `Hello World!` al terminar, porque las pruebas iniciales lo esperan. |
| `web` | `apps/web/src` y `apps/web/public` | Cambiar el párrafo de `app.html` y comprobar la actualización en el navegador. |

Los cambios de dependencias, Dockerfiles o configuración copiada requieren reconstruir las imágenes. Detener Compose con Ctrl+C y volver a ejecutar:

```bash
docker compose up --build
```

Después de modificar el proxy de Docker, reiniciar el servidor de Angular:

```bash
docker compose restart web
```

El BFF utiliza cinco segundos por defecto para consultar FastAPI. `API_TIMEOUT_MS` permite cambiar ese límite sin recompilar. Angular conserva diez segundos en desarrollo y utiliza tres minutos en el build de test para dar margen a los arranques en frío.

## Imagen de FastAPI para el entorno remoto de prueba

Construir la imagen desde la raíz:

```bash
docker build -t gastos-api-runtime:local -f apps/api/Dockerfile apps/api
```

Probarla en otro puerto, sin montar carpetas del repositorio:

```bash
docker run --detach --name gastos-api-runtime-local \
  --env PORT=10000 \
  --env RENDER_GIT_COMMIT=prueba-local \
  --publish 127.0.0.1:18010:10000 \
  gastos-api-runtime:local

python3 infra/ci/check-stack.py success --url http://127.0.0.1:18010/
```

El mensaje de éxito del script es ahora `OK: HTTP 200 y mensaje de FastAPI correctos.`; puede comprobar el proxy completo o una API directa según la URL que se indique.

Abrir las siguientes direcciones:

| URL local | Respuesta esperada |
|---|---|
| `http://localhost:18010/` | `{"message":"Hola desde FastAPI"}` |
| `http://localhost:18010/health` | `{"status":"ok"}` |
| `http://localhost:18010/version` | `{"commit":"prueba-local"}` |

`/health` comprueba que FastAPI responde; todavía no hay base de datos que verificar. `/version` devuelve solo el identificador del despliegue y desactiva su almacenamiento en caché.

`prueba-local` es un valor de prueba, no un SHA del código. Al ejecutar en Render desde Git, el proveedor asigna `RENDER_GIT_COMMIT`. Si la variable no existe localmente, `commit` es `null`.

El puerto se toma de `PORT`, con 8000 como valor predeterminado. El servidor escucha en `0.0.0.0` dentro del contenedor. El usuario de ejecución tiene UID 10001 y no es root.

Después de la prueba:

```bash
docker stop gastos-api-runtime-local
docker rm gastos-api-runtime-local
```

El trabajo de API del CI también construye esta imagen, la inicia sin montajes y verifica el saludo, la salud y el commit. Usa `curl` y `jq` del runner para validar los dos últimos JSON.

La configuración de Render y el orden del despliegue están en [la guía de test](docs/despliegue-test.md).

## Imágenes de API y BFF para el entorno de prueba

El archivo `infra/ci/compose.runtime.yml` construye y ejecuta las dos imágenes para despliegue. No monta fuentes ni inicia servidores con recarga. Este archivo prueba los backends; Angular sigue en el entorno de desarrollo.

Desde la raíz:

```bash
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml config --quiet
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml up --detach --build
python3 infra/ci/check-stack.py success --url http://127.0.0.1:18001/api/hello
```

Usa otro proyecto de Compose y otros puertos, de modo que puede convivir con el entorno habitual:

| Dirección | Comprobación |
|---|---|
| `http://localhost:18000/` | Mensaje directo de FastAPI. |
| `http://localhost:18001/` | Saludo inicial del BFF: `Hello World!`. |
| `http://localhost:18001/api/hello` | BFF consultando FastAPI. |
| `http://localhost:18001/health` | BFF activo: `{"status":"ok"}`. |
| `http://localhost:18001/version` | Commit del BFF, o `null` sin la variable de despliegue. |

El BFF usa `PORT=10000` en esta prueba. En su imagen se ejecuta como el usuario `node`, con dependencias de ejecución y el código compilado. Las herramientas de compilación quedan en la primera etapa del Dockerfile.

Para comprobar caída y recuperación, ejecutar uno por uno:

```bash
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml stop api
python3 infra/ci/check-stack.py unavailable --url http://127.0.0.1:18001/api/hello
curl --fail http://127.0.0.1:18001/health

docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml start api
python3 infra/ci/check-stack.py success --url http://127.0.0.1:18001/api/hello
```

Con FastAPI detenida, `/api/hello` devuelve el 502 controlado y `/health` del BFF sigue respondiendo 200. La salud del BFF indica que ese proceso atiende solicitudes; el recorrido completo se comprueba por separado.

Al terminar:

```bash
docker compose --project-name gastos-runtime-local --file infra/ci/compose.runtime.yml down
```

El trabajo de BFF en CI ejecuta estas comprobaciones, valida su commit y conserva sus pruebas unitarias, HTTP y compilación. Las pruebas cubren también respuestas incorrectas de FastAPI y el vencimiento del tiempo de espera.

La red interna de Compose utiliza HTTP. En Render los servicios Free se comunicarán por HTTPS público. Esta prueba local no comprueba TLS del proveedor ni los arranques tras reposo real.

Para Render se prevé `API_TIMEOUT_MS=120000`. Es un límite de espera de dos minutos para la consulta del BFF, y no garantiza que todo arranque en frío termine con éxito. Si FastAPI devuelve HTML durante el despertar o falla la conexión, el BFF conserva su error controlado. El build de test de Angular amplía la espera del navegador. CORS se habilita en el BFF con `FRONTEND_ORIGIN`, usando el origen real del sitio una vez creado.

## Angular como sitio estático de prueba

Los archivos de configuración separan la ejecución local del entorno remoto:

| Configuración | Dirección del BFF | Límite de espera |
|---|---|---|
| `src/environments/environment.ts` | Relativa: conserva `/api/hello` y el proxy local. | 10 segundos. |
| `src/environments/environment.remote.ts` | `https://gastos-test-bff.onrender.com`. | 180 segundos. |

Desde la carpeta del frontend, ejecutar cada comando por separado:

```bash
cd ~/projects/gastos/apps/web
npm ci
npm test -- --watch=false
npm run build
npm run build:test
cat dist/gastos-web/browser/version.json
cd ../..
```

`build:test` aplica las configuraciones `production,test`, en ese orden. Conserva las opciones optimizadas y reemplaza el archivo de entorno por el de test. La configuración Angular llamada `production` describe la compilación; el entorno que publicamos aquí sigue siendo test. El alojamiento de producción del proyecto todavía está pendiente.

El sitio a publicar está en `apps/web/dist/gastos-web/browser`. Después del build, `infra/build/write-web-version.mjs` genera `version.json` con `RENDER_GIT_COMMIT`, `GITHUB_SHA` o `null` si ninguna variable existe. CI comprueba que coincida con el SHA del workflow.

El JavaScript y `version.json` son públicos. Las direcciones y los tiempos de espera pueden estar allí; las credenciales de los servidores se configuran fuera del frontend.

El navegador conserva el aviso de error y permite repetir la consulta. El margen de tres minutos no garantiza que un servicio dormido responda correctamente en el primer intento.

### Acceso desde el sitio publicado

El BFF habilita CORS cuando se configura `FRONTEND_ORIGIN` con el origen exacto del sitio: esquema, host y puerto si corresponde, sin ruta ni barra final. No usa comodines ni permite credenciales en este incremento. Si falta la variable, CORS permanece desactivado y el desarrollo local sigue utilizando su proxy.

CORS controla qué respuestas puede leer el navegador desde otro origen. La autenticación y la autorización de usuarios se incorporarán en sus stories.

Angular está publicado en `https://gastos-test-web.onrender.com`. Ese origen está configurado en el BFF. Los campos del Static Site y las variables de los servidores están en [la guía de despliegue de test](docs/despliegue-test.md).

## Despliegue continuo de test

El trabajo de despliegue publica en Render después de que aprueben Angular, BFF, API, integración HTTP y reconstrucción de PostgreSQL. Solo se ejecuta ante un `push` a `main`; los PR y las ramas de trabajo conservan las comprobaciones sin publicar.

La entrega usa el mismo SHA validado para API, BFF y Angular, en ese orden. Espera cada despliegue y comprueba salud, versión y respuestas públicas antes de continuar. Si `main` avanzó durante CI, omite la entrega anterior antes de modificar Render. Una publicación que ya comenzó conserva su SHA hasta terminar o fallar.

Para activarlo, configurar el environment `test` en GitHub con la API key y los tres identificadores de servicio. Mantener Auto-Deploy en Off en Render. La configuración, las pruebas y la recuperación ante una entrega parcial están en [CD de test](docs/cd-test.md).

Las pruebas del programa no publican servicios y usan solo Python:

```bash
python3 -m unittest discover -s infra/cd -p 'test_*.py'
```

Este flujo todavía no ejecuta migraciones ni publica producción. Cada entrega reconstruye el commit en Render y puede dejar versiones distintas si falla a mitad de la secuencia; el resumen de Actions permite revisar qué se publicó.

## Supabase y roles de desarrollo

Supabase local se inicia con su CLI, junto a los tres servicios de Compose. La configuración está en `supabase/config.toml`; se utiliza la CLI 2.121.0. Los pasos de provisión y comprobación se describen en [Roles de PostgreSQL local](docs/roles-postgresql-local.md).

La herramienta `infra/postgres/local_roles.py` usa Python y el cliente `psql` del contenedor. Prepara `app_migrator` y `app_runtime`, comprueba conexiones TCP con contraseña y verifica sus permisos efectivos. Las credenciales locales se guardan en `.env.roles.local`, excluido de Git. El bootstrap local de ambos roles ya fue comprobado y puede repetirse. Esta herramienta opera sobre el contenedor local del proyecto.

El primer modelo de SQLAlchemy representa `public.espacios`, con UUID y nombre. Su revisión inicial se genera y revisa mediante Alembic antes de aplicarla. El procedimiento está en [Alembic local](docs/alembic-local.md).

`infra/postgres/local_database.py check` comprueba ambas conexiones mediante SQLAlchemy. Su subcomando `alembic` entrega solo la URL del migrator a Alembic, sin guardar contraseñas en `alembic.ini`. Los filtros admiten `public` y el esquema predeterminado únicamente después de comprobar que este sea `public`; excluyen esquemas externos y la tabla interna `alembic_version`.

Los endpoints actuales siguen atendiendo el saludo sin consultas de negocio. La provisión y esta primera migración no implementan RLS ni habilitan CRUD para runtime. Las policies, los grants sobre datos y el contexto transaccional corresponden a US-007. El trabajo `database` reconstruye una base Supabase desechable, provisiona ambos roles y aplica las migraciones. Exige que `alembic check` pase con el esquema correcto y falle ante una tabla pública sin migración; también compara objetos externos y sus datos centinela. El procedimiento está en [Base de datos en CI](docs/base-datos-ci.md). Las conexiones del entorno remoto siguen pendientes dentro de US-006.

## Consultar y detener los servicios

Desde otra terminal en la raíz:

```bash
docker compose ps
docker compose logs --tail=100
docker compose logs --follow bff
```

Ctrl+C en una terminal de `logs --follow` deja de mostrar los logs. Ctrl+C en la terminal de `compose up` detiene los servicios de ese arranque.

Para detener y eliminar los contenedores y la red del proyecto:

```bash
docker compose down
```

## Estructura

```text
apps/web/    Angular y sus proxies de desarrollo
apps/bff/    NestJS: recibe las consultas del frontend
apps/api/    FastAPI: API y futuras reglas financieras
docs/        Documentación del proyecto
infra/       Comprobaciones de CI y configuración de infraestructura
compose.yml  Arranque conjunto del entorno local
```

## Próximas entregas

- Completar las comprobaciones de recarga y recuperación del entorno local.
- Ampliar CI con análisis de calidad, detección de secretos y pruebas en un navegador.
- Incorporar Supabase local, migraciones y datos iniciales conforme a US-005/006/007 y los ADR.
- Confirmar el nuevo trabajo de base de datos en GitHub Actions y completar las conexiones remotas de ambos roles para US-006.
- Completar la prueba de primer acceso tras reposo y preparar producción cuando corresponda.

US-005 y US-008 permanecen abiertas hasta cumplir sus criterios pendientes y la definición de terminado acordada para el primer incremento.
