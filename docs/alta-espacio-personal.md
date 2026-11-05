# Alta del espacio personal

## Comportamiento
Después de verificar su sesión, el usuario pulsa **Crear mi espacio**.
Se crean su perfil, un espacio llamado **Mi espacio** y su membresía **owner**.
No se registra un nuevo usuario en Supabase Auth: se usa el usuario existente.

La web envía POST /api/personal-space al BFF. El BFF valida el token y lo
reenvía a POST /personal-space de FastAPI, que lo valida de nuevo.
FastAPI establece app.user_id dentro de runtime_transaction y ejecuta la
función de alta. El cliente no elige usuario, espacio ni rol.

La operación devuelve usuario_id, espacio_id y nombre. Repetirla devuelve el
mismo espacio, incluso cuando llegan dos solicitudes a la vez.
Tras recargar, el botón puede aparecer de nuevo; repetirlo no duplica datos.
La carga automática de cuentas y espacios se incorporará con la próxima pantalla.

## Decisión propuesta para ADR-0004
Usar una función SECURITY DEFINER, versionada con Alembic y propiedad de
app_migrator, exclusivamente para el alta propia. Runtime solo recibe EXECUTE
sobre esta función; no recibe INSERT/UPDATE/DELETE sobre las tres tablas.
La API sigue conectando como app_runtime, nunca con credenciales de migración.

La función no acepta parámetros. Lee la identidad del contexto transaccional,
fija search_path en pg_catalog y usa nombres de tabla completos.
Las policies de app_migrator permiten las inserciones sin desactivar RLS ni FORCE.
PUBLIC y los roles de Data API no tienen permiso de ejecutar la función.

El espacio personal usa el mismo UUID que el usuario, en una tabla distinta.
Es una convención explícita para identificar su único espacio personal sin una
tabla adicional. No concede permisos por conocer ese ID: sigue aplicándose RLS.
Los espacios compartidos futuros tendrán otro mecanismo de creación.

Un bloqueo transaccional por identidad serializa reintentos. Perfil, espacio y
membresía se confirman juntos o se revierten juntos. Un perfil previo conserva
su nombre. Si ya existe el espacio pero falta la membresía owner, la operación
falla: no recupera permisos revocados ni toma posesión de un espacio preexistente.

La confianza sigue estando en el backend: alguien que comprometiera las
credenciales runtime podría falsificar app.user_id. Esta función no sustituye
la validación del JWT ni protege frente a un backend comprometido.

Alternativas: un trigger en auth.users acoplaría el alta a un esquema de Supabase;
dar escritura directa a runtime ampliaría permisos; usar el rol migrator en
requests rompería la separación vigente. Una función limitada mantiene el alta
bajo Alembic con una superficie de permisos concreta.
Revisar esta decisión si hacen falta varios espacios personales, invitaciones,
transferencia de propiedad o un rol separado para funciones elevadas.

## Pruebas y despliegue
La migración 0007 se aplica mediante el pipeline existente, antes del despliegue.
No requiere nuevas claves, variables de entorno ni cambios manuales en Supabase.

CI verifica:
- Alta repetida y simultánea: una fila por entidad.
- Reversión de las tres inserciones ante una excepción.
- RLS: otro usuario no ve el espacio.
- Ausencia de contexto rechazada y permisos de la función cerrados.
- Membresía revocada no restaurada.
- JWT requerido, identidad del cuerpo ignorada y POST permitido por CORS.
- Respuesta tardía del alta ignorada después de cerrar sesión en la web.

Para probar en test, iniciar sesión y pulsar Crear mi espacio. Debe aparecer
**Mi espacio**. Recargar y repetir: debe volver al mismo espacio.
El siguiente incremento agrega una cuenta dentro de este espacio.
Este paso no incluye registro público, invitaciones ni movimientos de dinero.
