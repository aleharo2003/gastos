# US-007, paso 4: perfiles y membresías

La cadena implementada es:

```text
Identidad autenticada (UUID) -> perfil propio -> membresías
                             vínculo lógico     clave foránea
```

Perfil contiene usuario_id (el UUID de Auth, sin generar otro) y nombre. No contiene
contraseñas ni tokens. La FK de miembros_espacio.usuario_id exige un perfil existente.
No existe una FK desde perfiles a auth.users en esta implementación.

## Hallazgo de permisos y decisión de este incremento

La prueba de una FK hacia auth.users con app_migrator falló con SQLSTATE 42501,
permission denied for schema auth. GRANT USAGE desde postgres no resolvió el acceso.
La documentación de Supabase explica que postgres no tiene grant option sobre auth
y recomienda una tabla propia de usuarios/perfiles para este caso.

Se conserva el migrator limitado y se crea perfiles en public. No se modifican los
roles, grants ni objetos de auth; no se agrega membresía en authenticated ni se usa
supabase_admin para ejecutar las migraciones de la aplicación. ADR-0001 permite
referencias externas, pero no exige una FK a Auth cuando el rol no puede crearla.

El mapa DAT-01 es conceptual: su FK hacia identidad externa no se implementa aquí.
La correspondencia perfil/Auth debe garantizarla el mecanismo de alta con identidad
validada de ADR-0004. Antes de cerrar ese ADR deben decidirse también reconciliación
y baja: eliminar una identidad de Auth no eliminará ni bloqueará automáticamente
su perfil por una restricción SQL. Un migrator de confianza puede crear un perfil
con un UUID que no exista en Auth; runtime no tiene ese permiso. Esta limitación no
se presenta como integridad garantizada contra Auth.

## Lectura y seguridad

perfiles nace con ENABLE y FORCE RLS. app_migrator dispone de su policy de migración;
app_runtime tiene solo SELECT con usuario_id igual al usuario del contexto. No
hace falta seleccionar espacio. Un usuario con perfil y sin membresías puede leer
su perfil, pero no espacios. Se retiran grants de PUBLIC y los roles de Data API
sobre la nueva tabla; el control global de defaults sigue pendiente.

No se habilita edición ni alta de perfiles. El usuario del contexto debe provenir
de autenticación confiable; la función de contexto no verifica tokens. Los perfiles
de las pruebas se crean como fixtures, no mediante un flujo público de registro.

No se usa ON DELETE CASCADE en la FK de membresías: eliminar un perfil con miembros
queda bloqueado. El procedimiento de baja se decidirá explícitamente.

## Datos anteriores

0004 requiere miembros_espacio vacío al aplicarse. Las pruebas anteriores creaban
sus datos en una base temporal y los eliminaban. Si hay membresías manuales en
desarrollo, la migración se detiene antes de crear perfiles. Hace falta un backfill
revisado; no se borran membresías ni se inventan perfiles para forzar el avance.

El downgrade elimina perfiles y su FK desde membresías: perdería los perfiles
existentes. Se prueba solo en bases desechables.

## Validación

CI crea perfiles y membresías ficticios como app_migrator únicamente en PostgreSQL
temporal. No crea filas en auth.users ni prueba registro/login. La limpieza elimina
membresías, espacios y perfiles de la prueba.

Se verifica perfil propio con SELECT sin WHERE, lectura vacía sin contexto o para
un usuario desconocido, escrituras runtime denegadas, rechazo de membresías sin
perfil y rechazo de eliminar un perfil con membresías. Se conservan las pruebas de
contexto, lectura de espacios, revocación y backfill. alembic check compara modelos
y estructura, pero no certifica policies.

US-007 continúa abierta. ADR-0004 sigue pendiente y este incremento no resuelve
registro, login ni aislamiento de tablas financieras.

Referencia: [Permisos de roles personalizados sobre Auth, Supabase](https://supabase.com/kb/troubleshooting/permission-errors-when-granting-custom-roles-access-to-the-auth-schema).
