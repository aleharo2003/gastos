# Inicio de sesión web

La pantalla permite ingresar con un usuario existente de Supabase Auth y cerrar
su sesión en este navegador. No crea perfiles, espacios, membresías ni cuentas.

## Recorrido
1. Angular carga /auth-config.json, con la referencia del proyecto y su Publishable key.
2. El SDK de Supabase envía email y contraseña a Supabase Auth por HTTPS.
3. Angular envía el access token a /api/me del BFF.
4. El BFF y FastAPI validan el token; Angular comprueba que la identidad coincida.
5. La pantalla confirma la sesión. Ante un fallo de conexión permite reintentar.

El SDK conserva y renueva la sesión en localStorage. La contraseña no se guarda
y se limpia del formulario al terminar el intento. Los tokens no se imprimen.
Esto implica que código malicioso ejecutado en el origen podría acceder a la
sesión: evitar HTML no confiable y mantener las dependencias actualizadas.
Cerrar sesión usa scope local; otros dispositivos mantienen sus sesiones.
Un access token ya emitido puede seguir vigente hasta su expiración.

## Render: gastos-test-web
Agregar estas variables al sitio estático:
- SUPABASE_PROJECT_REF: cyxhyfbiacfayixbmotq
- SUPABASE_PUBLISHABLE_KEY: la clave que comienza con sb_publishable_ del proyecto test.

La Publishable key es pública por diseño. No usar service_role, secret key,
contraseñas PostgreSQL ni contraseñas de usuarios en estas variables.
El comando build:test genera auth-config.json en el directorio publicado.
Cambiar las variables requiere volver a compilar y desplegar.
Sin clave, la compilación pasa pero el formulario queda deshabilitado.

Para desarrollo local, exportar las mismas variables en la terminal y ejecutar
npm start desde apps/web. prestart genera public/auth-config.json, ignorado por Git.
El BFF y la API locales necesitan su configuración de autenticación y el mismo
proyecto. No mezclar proyectos entre capas.

## Validación
- npm test -- --watch=false: formulario, errores, identidad, renovación y salida.
- npm run build:test: compilación para el entorno remoto.
- En test: ingresar con el usuario existente, confirmar sesión verificada,
  recargar y comprobar que continúa; cerrar sesión y recargar otra vez.
- Repetir desde el celular.
- Una contraseña incorrecta debe mostrar un error y permitir reintentar.

La verificación de sesión no concede acceso a datos financieros: cada operación
de negocio debe aplicar autorización y contexto transaccional con RLS.
Este incremento no completa el alta de usuario ni el registro de gastos.
