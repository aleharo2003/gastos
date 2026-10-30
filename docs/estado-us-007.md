# Estado de US-007: aislamiento de datos

Estado al revisar el PR #9, el 30 de octubre de 2026. US-007 continúa abierta. Las guías numeradas describen cómo se construyó cada paso; esta página consolida el resultado para evitar confundir sus pendientes históricos con los actuales.

## Implementado en este PR

- Migraciones 0002 a 0006. La revisión final es **0006**.
- Perfiles privados, membresías y listado de espacios; cuentas con estructura mínima para probar lectura y escritura por espacio.
- Contexto de usuario y espacio local a cada transacción. La sesión se cierra y la conexión puede reutilizarse sin heredar esos valores en el recorrido probado.
- RLS habilitado y forzado, permisos explícitos para runtime y policies de migración para backfills sin contexto.
- Permisos predeterminados cerrados para tablas, vistas, secuencias y funciones creadas por app_migrator. Revocación de acceso Data API a objetos propios existentes.
- Reconstrucción de PostgreSQL desechable y pruebas de aislamiento, revocación, backfill, grants y detección de regresiones.
- Auditoría de FKs entre tablas con espacio_id y demostración con una tabla de prueba transitoria de la necesidad de incluir el espacio en la referencia.

Los modelos de la aplicación mantienen el esquema public explícito. Alembic compara una copia normalizada del metadata para evitar diferencias falsas en referencias hacia el esquema predeterminado.

## Qué evidencia hay

Las pruebas locales de API e infraestructura y la reconstrucción completa aprobaron durante el desarrollo. Las pruebas reales usan roles limitados, consultas sin WHERE y valores de dos espacios; comprueban resultados, no solo ausencia de excepciones.

El resultado de GitHub Actions debe comprobarse para el último commit del PR. Los resultados locales no se presentan como aprobación del CI remoto.

| Contrato | Comprobación |
|---|---|
| Usuario y espacio por transacción | Misma conexión tras commit, excepción, cancelación simulada y error SQL |
| Lectura privada | Perfiles propios, membresías y espacios autorizados |
| Escritura de cuentas | Lector sin escritura; editor/owner con operaciones permitidas en el espacio seleccionado |
| Membresía revocada | Una transacción nueva pierde acceso |
| Backfill | Cantidad y valores de filas de dos espacios comprobados con FORCE activo |
| Configuración de protección | Inventario privado, RLS/FORCE, grants efectivos y defaults de objetos de prueba |
| Integridad compuesta | Inserciones y cambios cruzados rechazados por una FK en una tabla de prueba; una FK simple se detecta y demuestra insuficiente |

## Pendientes para revisar el cierre de US-007

1. Revisar el PR y obtener CI correcto para su último commit.
2. Registrar la comprobación del plan de consulta de membresía y los índices previstos por ADR-0002. Ya existen la PK (usuario_id, espacio_id), el índice adicional de espacio y la clave única de cuentas (espacio_id, id); eso no sustituye observar el plan.
3. Acordar explícitamente el alcance del cierre respecto de repositorios y entidades futuras. Hoy no hay repositorios financieros ni una entidad hija de cuentas: la prueba transitoria no equivale a implementar esas relaciones. Sus stories deberán incluir filtros por espacio, FKs compuestas y pruebas runtime reales.
4. Registrar la aceptación o ajustes de ADR-0002 mediante la decisión del responsable. Abrir o integrar este PR no cambia automáticamente el estado de ese ADR ni de Jira.

No se agregan entidades financieras incompletas solo para cumplir una casilla del backlog. Si los criterios de US-007 exigen esas entidades reales, la story sigue abierta o se divide explícitamente su alcance antes de cerrarla.

## Trabajo separado y límites

- Autenticación y validación JWT: ADR-0003. El contexto transaccional recibe una identidad ya validada; no autentica UUID recibidos del cliente.
- Alta inicial: ADR-0004. Runtime no puede crear perfiles, espacios ni membresías. La correspondencia con Auth es lógica; no existe FK hacia auth.users.
- Cuentas completas y movimientos: stories de negocio. No hay todavía endpoints ni pantallas para operar estas tablas.
- Integración HTTP de la sesión y cancelaciones reales: pendiente cuando se incorporen los endpoints. Una excepción de cancelación simulada no prueba ese recorrido.
- Supabase remoto: este PR no aplica allí migraciones ni configura la conexión de FastAPI. Debe incorporarse la migración remota antes del despliegue que empiece a usar la base.
- La revisión 0004 exige membresías vacías al aplicarse; si existen datos previos requiere un backfill revisado. La revisión 0006 rechaza downgrade: una corrección de permisos se realiza hacia adelante.

## Documentos del resultado

- [Contexto transaccional](contexto-transaccional.md).
- [Perfiles y vínculo de identidad](perfiles-identidad.md).
- [Lectura de espacios y membresías](lectura-rls.md).
- [Cuentas y permisos por rol](cuentas-rls.md).
- [Cobertura de RLS](cobertura-rls.md).
- [Permisos de objetos](permisos-objetos.md).
- [Integridad entre espacios](integridad-espacios.md).
