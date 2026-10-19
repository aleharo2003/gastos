# Primer despliegue de prueba en Render

Estado: preparación del primer servicio. La API todavía no se ha publicado. BFF, frontend y el CD automático se incorporarán en los siguientes pasos.

Se aplica a US-005 y la primera entrega de US-009. El primer despliegue remoto usa datos ficticios y no incorpora todavía Supabase, autenticación o datos financieros.

## Orden del trabajo

1. Preparar y comprobar la imagen de FastAPI localmente.
2. Subir el cambio, comprobar CI y fusionar el PR en main.
3. Crear el servicio web gratuito de FastAPI desde ese main validado.
4. Configurar y desplegar BFF y Angular.
5. Automatizar los despliegues desde GitHub sobre el commit validado y probar desde celular.

El paso 3 es el bootstrap inicial del hosting. El CD automático aún no está implementado. Crear el servicio en Render ya inicia su primer build y despliegue; por eso el código debe estar preparado y validado antes.

Cuando exista la base, el orden ordinario será CI, migraciones, despliegue y verificación. El saludo actual no requiere migraciones.

## Cuenta y acceso

Crear una cuenta desde [Render](https://dashboard.render.com/register). Se puede usar el inicio de sesión con GitHub. Al conectar el repositorio, limitar el acceso al proyecto `aleharo2003/gastos` si el formulario ofrece la selección de repositorios.

El objetivo es usar un servicio con cómputo `Free`. El plan del workspace y el tipo de instancia son conceptos distintos: elegir un workspace gratuito no garantiza que una instancia elegida sea gratuita. Verificar el costo de los recursos en el formulario.

La cuenta puede prepararse mientras se revisa el PR. El servicio se crea cuando el commit de main ya pasó CI.

## Archivos de esta entrega

| Archivo | Responsabilidad |
|---|---|
| `apps/api/Dockerfile` | Imagen para ejecutar FastAPI sin recarga automática. |
| `apps/api/app/main.py` | Conserva el saludo y agrega salud y versión. |
| `.github/workflows/ci.yml` | Amplía el trabajo de API para construir y probar esa imagen. |
| `infra/ci/check-stack.py` | Mantiene sus comprobaciones y utiliza un mensaje de éxito válido tanto para el proxy como para una API directa. |
| `README.md` | Instrucciones de prueba local. |
| `docs/despliegue-test.md` | Esta configuración y el orden del primer despliegue. |

La configuración de Compose y los Dockerfiles de desarrollo mantienen su función de desarrollo local.

## Preparación guiada en Ubuntu

Partiendo de main sincronizada y sin cambios pendientes:

```bash
cd ~/projects/gastos
git status --short --branch
git switch -c feature/us-009-api-render
mkdir -p docs

archivos_api="/mnt/c/Users/nalej/.codex/.chatgpt-projects/g-p-694076bb76ec81918d25a317c59f198a/output/us-009-api"

cp "$archivos_api/Dockerfile" apps/api/Dockerfile
cp "$archivos_api/main.py" apps/api/app/main.py
cp "$archivos_api/ci.yml" .github/workflows/ci.yml
cp "$archivos_api/check-stack.py" infra/ci/check-stack.py
cp "$archivos_api/README.md" README.md
cp "$archivos_api/despliegue-test.md" docs/despliegue-test.md
```

La variable `archivos_api` contiene la carpeta de los archivos preparados. No contiene credenciales.

Leer los archivos y seguir la prueba de imagen que aparece en el README. Al guardar `main.py`, la API de desarrollo puede recargarse por el montaje de Compose; el saludo permanece igual.

La imagen nueva se prueba separada, en `localhost:18010`, para conservar los puertos habituales de desarrollo.

## Qué hace el Dockerfile

- Parte de la misma versión de Python utilizada en desarrollo.
- Instala las dependencias fijadas en `requirements.txt`.
- Copia el código dentro de la imagen.
- Crea y utiliza un usuario sin privilegios de administrador.
- Inicia Uvicorn con el puerto indicado por `PORT`.

`Dockerfile.dev` usa el servidor con recarga para programar. El nuevo `Dockerfile` ejecuta el código que se incorporó a la imagen y no monta fuentes del equipo.

En `CMD`, `sh` permite expandir `PORT` al iniciar el contenedor y `exec` hace que Uvicorn reciba directamente las señales de apagado.

## Qué significan los endpoints nuevos

- `/health`: responde HTTP 200 con `{"status":"ok"}`. Hoy indica que la API atiende solicitudes. Se revisará cuando tenga dependencias como PostgreSQL.
- `/version`: responde el valor de `RENDER_GIT_COMMIT`. Permite comparar el código esperado con el despliegue observado. Solo devuelve ese identificador; no expone las demás variables del servicio.

En una ejecución local sin esa variable, la versión devuelve `null`. En la prueba local se asigna `prueba-local` deliberadamente. Render proporciona el SHA del despliegue cuando el servicio se construye desde Git.

## Qué verifica ahora el CI

El trabajo de API conserva la instalación, `pip check` y la comprobación de sintaxis. Además:

1. Construye `apps/api/Dockerfile`.
2. Inicia un contenedor en el puerto de prueba 18000, sin montar el checkout.
3. Comprueba el saludo.
4. Consulta `/health` y `/version` con `curl`.
5. Valida el JSON con `jq`, incluyendo que la versión coincida con el SHA del workflow.
6. Muestra logs y retira el contenedor.

El runner Ubuntu 24.04 incluye `curl` y `jq`. El shell Bash explícito del trabajo utiliza `pipefail`, para que un fallo de `curl` no quede oculto por el comando siguiente de la tubería.

El trabajo de integración con los tres servicios sigue comprobando el recorrido de desarrollo y la caída y recuperación de FastAPI.

## Guardar y subir

Después de completar la prueba local y retirar el contenedor de prueba:

```bash
git diff --check
git add apps/api/Dockerfile apps/api/app/main.py .github/workflows/ci.yml infra/ci/check-stack.py README.md docs/despliegue-test.md
git diff --cached --check
git diff --cached --stat
git commit -m "feat: prepara FastAPI para el entorno de prueba en Render"
git push -u origin feature/us-009-api-render
```

Comprobar los cuatro trabajos en GitHub y abrir un PR hacia main. El trabajo de API ahora se llama `API - dependencias, sintaxis e imagen`.

## Configuración prevista del primer servicio

Esta tabla registra la configuración; todavía no crea recursos. Los valores finales se comprueban en el formulario de Render antes de crear el servicio.

| Campo | Valor |
|---|---|
| Tipo | Web Service |
| Origen | Git Provider conectado a GitHub |
| Repositorio | `aleharo2003/gastos` |
| Nombre propuesto | `gastos-test-api` |
| Rama | `main` |
| Runtime / Language | Docker |
| Root Directory | Vacío: raíz del repositorio |
| Dockerfile Path | `apps/api/Dockerfile` |
| Docker Build Context Directory | `apps/api` |
| Compute / Instance Type | Free |
| Health Check Path | `/health` |
| Auto-Deploy | Off |
| Variables adicionales de aplicación | Ninguna en este paso |

La URL pública la asignará Render; registrar la dirección real, sin asumir que el nombre propuesto estará disponible.

El arranque usa `PORT`, que Render proporciona con valor predeterminado 10000. En el primer despliegue se verifican `/`, `/health` y `/version`, y se compara el commit con el de main que pasó CI.

## Límites del entorno gratuito

Render Free suspende servicios tras 15 minutos sin tráfico; el siguiente acceso puede tardar aproximadamente un minuto en despertarlos. Las 750 horas gratuitas se comparten entre los servicios del workspace.

BFF y API se comunicarán por HTTPS público, porque los servicios Free no reciben tráfico privado. Los tiempos de espera locales actuales se ajustarán al preparar BFF y Angular para sus posibles arranques en frío consecutivos.

Este primer paso no habilita producción ni completa US-005/009. El recorrido remoto completo y la prueba en celular permanecen pendientes.

## Referencias

- [Crear un servicio web y configurar el puerto](https://render.com/docs/web-services).
- [Variables de Render, incluido RENDER_GIT_COMMIT](https://render.com/docs/environment-variables).
- [Health checks](https://render.com/docs/health-checks).
- [Límites de Free](https://render.com/docs/free).
- [Herramientas del runner Ubuntu 24.04](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md).
