# Comprobantes privados de gastos

## Alcance

Un gasto ya guardado permite adjuntar JPG, PNG o PDF, consultar sus archivos, ver fotos y descargar. En móvil hay un selector de cámara y otro de galería/archivos; su presentación depende del navegador. Guardar el gasto no espera la subida del archivo.

Límites de aplicación: 5 MiB por archivo, cinco comprobantes por gasto y 200 MiB de archivos registrados por espacio. No son las cuotas comerciales de Supabase. No hay compresión de fotos ni conversión HEIC: exportar como JPG si el teléfono utiliza ese formato.

Este incremento cubre gastos diarios existentes. No implementa todavía comprobantes de pagos mensuales, eliminación, OCR ni notificaciones. Los pagos mensuales tendrán su propia relación cuando exista ese módulo; no se simulan como gastos diarios para agregarlos aquí.

## Preparación del entorno test

1. En el proyecto Supabase **gastos-test**, abrir Storage y crear un bucket cuyo nombre e ID sean `gastos-comprobantes`.
2. Mantener **Public bucket desactivado**. Configurar límite de archivo de 5 MB (5242880 bytes si solicita bytes) y tipos `image/jpeg`, `image/png`, `application/pdf`.
3. No crear policies para acceso directo de `anon`, `authenticated` o `PUBLIC` a este bucket. Revisar que no exista una policy general de otros buckets que lo habilite. Toda lectura y escritura debe pasar por FastAPI.
4. En configuración de API keys de Supabase, crear una clave secreta para el servidor (prefijo `sb_secret_`). El adaptador admite también la legacy `service_role`; nunca usar la publishable key ni una contraseña de PostgreSQL para esta variable.
5. En Render, servicio **gastos-test-api → Environment**, agregar `APP_STORAGE_SERVICE_KEY` con esa clave. Debe existir también `AUTH_SUPABASE_PROJECT_REF`, ya usado por autenticación. Guardar la configuración sin iniciar un despliegue independiente si el pipeline aún no terminó.
6. No poner la clave en Angular, el BFF, Git, capturas ni en el chat. No es un Secret File. La API es el único servicio que la necesita.
7. Tras el merge, el pipeline aplica `0010` antes de desplegar. No ejecutar DDL manual sobre `public`. La creación del bucket se realiza mediante Storage, no manipulando sus tablas internas.

Si Storage no está configurado, el resto de la aplicación puede arrancar; adjuntar/descargar informa indisponibilidad. Esto no confirma que los comprobantes estén operativos: hay que completar la prueba real.

## Seguridad y datos

La tabla `public.comprobantes` guarda nombre, tipo, tamaño, hash y ruta. La FK compuesta vincula gasto y espacio; RLS y FORCE protegen los metadatos. Owner/editor pueden adjuntar, los miembros con lectura pueden consultar. Cada operación valida el JWT, membresía y pertenencia del gasto. No se entregan URLs públicas ni URLs firmadas reutilizables: el servidor verifica acceso en cada descarga.

El servidor usa una clave elevada solamente para la API de Storage, después de verificar permisos de negocio. Su poder es mayor que el del rol PostgreSQL `app_runtime`; proteger y rotar esta clave de forma independiente. El bucket debe seguir privado. La API rechaza operaciones si encuentra que es público, pero eso no revierte una publicación hecha por un administrador.

La validación identifica firmas de JPG/PNG/PDF y limita bytes en ambos servidores; no es un antivirus ni un análisis completo del documento. Los PDF se descargan, no se incrustan como HTML. Las fotos se muestran con un blob local temporal. Los originales conservan sus metadatos, incluido EXIF cuando exista. Las respuestas llevan `no-store`; las descargas se entregan como adjuntos con nombre generado y `nosniff`.

## Reintentos y consistencia

La interfaz conserva archivo e ID cuando no puede confirmar la subida. Reintentar sin cambiarlo no crea otro registro. Un bloqueo transaccional por espacio serializa la comprobación de límites. Una falla de Storage revierte el alta del metadato y no afecta al gasto ya existente.

PostgreSQL y Storage no comparten una transacción distribuida. Si Storage termina pero falla la confirmación de la base, puede quedar un objeto huérfano privado. Reintentar con el mismo ID y contenido utiliza la misma ruta y permite completar el alta. Si se abandona ese intento, el objeto queda para conciliación operativa. No borrar automáticamente archivos por edad ni modificar `storage.objects` con SQL.

Para conciliar: comparar el inventario del bucket con las rutas de `public.comprobantes`, excluir subidas en curso y verificar los candidatos en una segunda lectura antes de cualquier eliminación mediante la API de Storage. Este paquete no ejecuta limpieza automática ni borrados remotos. La cuota de 200 MiB cuenta metadatos confirmados; revisar también el consumo real del bucket, que puede incluir huérfanos. Respaldar archivos y base por separado y comprobar su restauración conjunta.

El permiso se comprueba al iniciar la operación. Revocarlo bloquea solicitudes posteriores, no borra una copia que alguien ya descargó.

## Validación

Se probaron sin servicios remotos: 88 pruebas API, 68 unitarias BFF, 57 HTTP BFF, 24 Angular y compilaciones de BFF/web. El verificador completo de PostgreSQL temporal pasó migraciones, drift, FK, RLS, permisos, reintentos, límite de cinco archivos, rollback ante falla de Storage y revocación de lectura.

Las pruebas de objetos usan un doble de Storage y HTTP simulado. No prueban credenciales, bucket ni políticas del proyecto remoto. No se modificó el repositorio WSL ni se desplegó desde esta preparación.

Prueba manual después del despliegue:

1. Adjuntar una foto pequeña a un gasto existente. Verla, recargar y descargarla.
2. Repetir con PDF y comprobar su apertura desde el archivo descargado.
3. Verificar que fecha e importe del gasto siguen iguales.
4. Probar una foto desde el celular. Si supera 5 MB, elegir una copia más pequeña.
5. Con una segunda cuenta de otro espacio, solicitar la ruta de descarga autenticándose como esa segunda cuenta: debe rechazarla. No compartir tokens.
6. Probar un archivo no admitido y comprobar que el gasto permanece guardado.

## Referencias

- [Buckets privados de Supabase](https://supabase.com/docs/guides/storage/buckets/fundamentals)
- [Creación y restricciones de buckets](https://supabase.com/docs/guides/storage/buckets/creating-buckets)
- [Claves públicas y secretas](https://supabase.com/docs/guides/getting-started/api-keys)
- [Descargas autenticadas](https://supabase.com/docs/guides/storage/serving/downloads)
