# Gastos

Aplicación de finanzas personales para uso familiar, aprendizaje y enseñanza. El primer incremento conecta Angular, un BFF en NestJS y una API en FastAPI.

## Estado actual

El recorrido funciona en desarrollo con Docker Compose. Todavía faltan la base de datos, autenticación, migraciones, datos iniciales, CI y despliegue remoto.

Los servidores configurados en `Dockerfile.dev` son servidores de desarrollo. La configuración de producción se incorporará por separado.

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

Estos proxies pertenecen al servidor de desarrollo; las rutas del despliegue remoto se configurarán al preparar ese entorno.

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

Los tiempos de espera actuales son para desarrollo local: cinco segundos entre BFF y API y diez segundos desde Angular. Se revisarán al configurar el entorno remoto y sus arranques en frío.

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
infra/       Futura configuración de infraestructura
compose.yml  Arranque conjunto del entorno local
```

## Próximas entregas

- Completar las comprobaciones de recarga y recuperación del entorno local.
- Incorporar CI y registrar sus resultados.
- Incorporar Supabase local, migraciones y datos iniciales conforme a US-005/006/007 y los ADR.
- Desplegar el primer recorrido en el entorno remoto de prueba y comprobarlo desde un celular.

US-005 permanece abierta hasta cumplir sus criterios y la definición de terminado acordada para el primer incremento.
