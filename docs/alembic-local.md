# Primer modelo y migración local con Alembic

Este tramo de US-006 prepara el modelo `Espacio`, la configuración de Alembic y una primera migración generada por el desarrollador. Usa los roles locales creados en el incremento anterior. No habilita acceso a datos desde FastAPI ni conecta una base remota.

## Qué hace cada herramienta

| Pieza | Responsabilidad |
|---|---|
| PostgreSQL | Guarda los datos y aplica las restricciones y permisos de la base. |
| Psycopg 3 | Permite que Python abra una conexión PostgreSQL y envíe operaciones. |
| SQLAlchemy 2.0 | Describe tablas mediante modelos Python y utiliza Psycopg para comunicarse con PostgreSQL. |
| Alembic | Genera y ejecuta archivos versionados que describen cambios de estructura. |

Cambiar una clase Python no cambia automáticamente una tabla. La secuencia de trabajo es: modificar el modelo, generar una revisión, leer sus operaciones y aplicar la migración. No se utiliza `Base.metadata.create_all()`: las tablas de aplicación se crean con Alembic.

`app_migrator` ejecuta las migraciones y será propietario de los objetos que cree. `app_runtime` es la identidad prevista para FastAPI; en este incremento solo se comprueba su conexión. Todavía no recibe permisos de lectura o escritura sobre `espacios`.

## Primer modelo

`Espacio` representa un conjunto de datos financieros que luego podrá compartirse mediante membresías. Este primer recorte contiene solamente:

| Columna | Tipo | Restricción |
|---|---|---|
| `id` | UUID | Clave primaria, obligatorio. |
| `nombre` | Texto | Obligatorio. |

No se decide todavía unicidad de nombres, moneda base, alta del espacio ni administración de miembros. Un espacio con estructura persistente no equivale a un usuario registrado ni a una operación autorizada.

No se incorpora `Perfil` en esta primera migración. Su futura referencia a `auth.users.id` requiere preparar los permisos necesarios sobre esa identidad externa. La tabla `auth.users` seguirá siendo administrada por Supabase; Alembic no debe crearla ni modificarla.

## Conexiones locales y credenciales

Ejecutar desde la raíz del repositorio, en Ubuntu/WSL, usando el entorno virtual de la API y con Supabase local iniciado. El helper local utiliza la configuración de ese proyecto y las credenciales locales preparadas anteriormente. No hace falta copiar contraseñas a `alembic.ini` ni escribir una URL con contraseña en la terminal.

```bash
python3 infra/postgres/local_database.py check
```

Este comando verifica conexiones mediante SQLAlchemy con ambas identidades. No consulta información financiera ni crea tablas. Las credenciales locales siguen en un archivo ignorado por Git; no se incluyen en los archivos de migración ni se comparten como evidencia.

El helper conecta con `127.0.0.1` y el puerto `db.port` de `supabase/config.toml`, usando la base `postgres`. Esta conexión local usa `sslmode=disable`; no es la configuración que se utilizará para Supabase remoto, donde deben verificarse TLS y certificado. No utiliza las claves de la Data API de Supabase.

## Generar, revisar y aplicar

Consultar primero el estado de la base:

```bash
python3 infra/postgres/local_database.py alembic current
```

En la primera ejecución no habrá una revisión aplicada. Generar luego la primera revisión:

```bash
python3 infra/postgres/local_database.py alembic revision --autogenerate --rev-id 0001 -m "crea espacios"
```

`revision --autogenerate` compara el modelo con la base y escribe un archivo en `apps/api/alembic/versions/`. Generarlo no aplica el cambio. Leer el archivo antes de continuar: `upgrade()` debe crear únicamente `public.espacios`, con sus dos columnas y clave primaria. No debe contener operaciones sobre esquemas externos ni eliminar tablas ajenas.

No ejecutar de nuevo el comando de generación si el archivo ya existe. Revisar primero el archivo y el estado de las revisiones; duplicar la revisión no resuelve una diferencia de configuración.

Cuando el contenido esperado esté comprobado:

```bash
python3 infra/postgres/local_database.py alembic upgrade head
python3 infra/postgres/local_database.py alembic current
python3 infra/postgres/local_database.py alembic check
```

`upgrade head` aplica las migraciones pendientes hasta la última revisión. `current` debe identificar `0001` como revisión actual. `check` vuelve a comparar los modelos con la estructura y falla si encuentra operaciones pendientes dentro del alcance configurado.

La tabla `public.alembic_version` permite a Alembic registrar la revisión aplicada. Es infraestructura de migraciones, no una entidad del negocio.

El bootstrap de roles contempla también los objetos internos TOAST y sus índices que PostgreSQL puede crear para columnas de texto. Solo admite los vinculados a tablas propias de `public`; no habilita gestionar tablas externas. Así la provisión puede repetirse después de crear `espacios`.

No se utiliza `reset` ni `downgrade` como parte de este procedimiento. Los escenarios de reconstrucción y reversión se probarán por separado en entornos desechables.

## Cómo se limita el autogenerate

ADR-0001 establece una lista blanca con `public` como único esquema propio:

- `include_name` limita los esquemas que Alembic refleja desde PostgreSQL.
- `include_object` también excluye objetos externos declarados en el `MetaData` de SQLAlchemy y respeta el esquema de la tabla a la que pertenece cada objeto.

Alembic puede representar con `None` el esquema predeterminado de la conexión. Por eso no alcanza con admitir `None` en un filtro: la conexión de migraciones debe comprobar que el esquema predeterminado efectivo sea `public`.

Los filtros no deben ocultar una tabla de `public` solamente porque no exista en los modelos. Detectar esa diferencia permite revisar una eliminación legítima o un cambio manual inesperado.

La excepción puntual es `alembic_version`, que pertenece al control interno de Alembic. Se excluye en ambos filtros, también cuando `public` se refleja como esquema predeterminado, para no generar operaciones contra el propio registro de versiones.

Una clave foránea de una tabla propia puede referenciar una tabla externa. Excluir la tabla externa no debe convertirla en un objeto propio ni excluir automáticamente la clave foránea de la tabla de `public`. Las pruebas de filtros cubren este caso sin incorporar todavía perfiles al modelo de la aplicación.

## Qué demuestra `alembic check`

Sobre una base recién migrada, un resultado correcto demuestra coherencia entre modelos y migraciones para las diferencias que soporta autogenerate y que permiten los filtros. No inspecciona producción ni garantiza ausencia de todo cambio manual.

El autogenerate estándar no compara de forma general policies de RLS, grants, funciones ni triggers. Esos objetos requerirán migraciones explícitas y comprobaciones específicas. Los filtros tampoco impiden escribir manualmente una migración que modifique un esquema externo: sigue siendo necesario revisar cada archivo.

La aplicación todavía no tiene endpoints de espacios, permisos CRUD de runtime ni políticas RLS. Solo se usan datos ficticios. Antes de habilitar operaciones privadas, US-007 debe implementar y probar su contrato de acceso.

## Validación de US-006

La reconstrucción desechable, las migraciones y los filtros ya se ejecutaron en GitHub Actions. También se comprobaron las conexiones remotas de ambos roles mediante pooler de sesión y TLS con validación del certificado.

La comprobación de CI incluye un cambio de modelo sin migración y una tabla pública extra. El registro de evidencias y el paso pendiente para cerrar la story están en [Validación de US-006](validacion-us-006.md).

US-007 incorporará contexto transaccional, grants, RLS e índices. El alta inicial del usuario y su espacio sigue dependiendo de ADR-0004.

Las decisiones de referencia son ADR-0001 y ADR-0002, conservadas en `D:\HB\Cuentas`; DAT-01 muestra el modelo conceptual de espacios e identidad. Sus diagramas no sustituyen una migración ejecutable ni las pruebas de permisos.
