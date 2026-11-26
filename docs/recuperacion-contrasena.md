# Recuperación de contraseña en Piggo

La recuperación usa Supabase Auth. Configurá cada ambiente por separado antes de probar el correo real.

1. Agregá a las URL de redirección permitidas la URL pública exacta de Piggo con `/?recuperar=1`. Usá una entrada por ambiente y evitá permisos comodín.
2. En la plantilla **Reset password**, usá como destino del enlace `{{ .RedirectTo }}#token_hash={{ .TokenHash }}`. Conservá el resto del contenido de la plantilla del ambiente.
3. Configurá la expiración del OTP en 3600 segundos en Supabase Auth. Si el proyecto comparte ese ajuste con otros flujos de correo, revisá su configuración antes de aplicarlo.
4. Desde un usuario de prueba, pedí el enlace, abrilo en un navegador distinto y guardá una contraseña nueva. Iniciá sesión con ella y confirmá que el mismo enlace ya está usado. Para un correo sin cuenta, comprobá que Piggo muestra el mismo mensaje.

El token se retira de la barra de direcciones en cuanto se abre Piggo. La sesión usada para cambiar la contraseña vive en memoria y se cierra después del cambio. La sesión normal queda en su almacenamiento habitual.

[Plantillas de correo de Supabase](https://supabase.com/docs/guides/auth/auth-email-templates)
