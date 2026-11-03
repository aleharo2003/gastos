# Diagnostico de conexion runtime

El arranque sigue rechazando conexiones que no cumplen el contrato. Los logs
ahora distinguen etapas y categorias sin imprimir URLs, contraseñas, contenido
del certificado ni mensajes originales del driver.

| Categoria | Siguiente comprobacion |
| --- | --- |
| CONFIGURACION | Variables requeridas y ruta de APP_DB_CA_FILE |
| CERTIFICADO | PEM completo, archivo presente y legible por el usuario del contenedor |
| CONFIGURACION_ROL | APP_DB_USER corresponde a app_runtime |
| AUTENTICACION | Contraseña remota del rol runtime y acceso permitido |
| TLS | Certificado correcto para el proyecto y host correcto |
| DNS | Nombre del servidor configurado |
| TIEMPO_AGOTADO | Disponibilidad de Supabase y conectividad desde Render |
| PERMISOS | Rol efectivo y privilegios exigidos por validate_connection |
| FALLO | La etapa identifica donde investigar; no afirma una causa desconocida |

El PEM se carga antes de intentar la conexion. Esto detecta formato incorrecto
o permisos del archivo; la identidad del servidor se verifica luego al conectar
con sslmode=verify-full. No se reduce la seguridad TLS para depurar.

Algunos errores de libpq no incluyen SQLSTATE. Se reconocen frases conocidas
internamente para elegir una categoria fija. Un error no reconocido conserva
solo la etapa. Los mensajes del driver nunca se copian al log.

Una conexion exitosa desde Ubuntu demuestra que esas credenciales funcionan
desde esa maquina; no demuestra que Render tenga los mismos valores ni que la
validacion completa de permisos haya pasado.

Tras integrar el cambio, el pipeline migra y despliega normalmente. Si falla
el arranque de Render, compartir solo el mensaje `Base runtime: ...`. No hace
falta volver a cambiar contraseñas antes de conocer la categoria del fallo.
