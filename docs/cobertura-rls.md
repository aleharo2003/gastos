# Cobertura de RLS en CI

> Guía de un paso anterior. Para el estado consolidado del PR y sus pendientes, consultar [Estado de US-007](estado-us-007.md).

US-007 necesita detectar que una tabla privada pierde su protección. Las pruebas de lectura y escritura cubren el comportamiento; este control agrega un inventario explícito de las relaciones de `public`.

`infra/ci/check_rls_coverage.py` reconoce cuatro tablas privadas: `espacios`, `miembros_espacio`, `perfiles` y `cuentas`. Exige que pertenezcan a `app_migrator` y tengan RLS y FORCE activos. `alembic_version` es la única tabla técnica exceptuada de esos dos indicadores: contiene la revisión del esquema, no datos de usuarios.

Una tabla, vista, vista materializada o tabla externa nueva hace fallar el control hasta revisar y clasificar su acceso. Hoy no hay catálogos globales ni vistas aprobadas. No se debe agregar una excepción solo para obtener un resultado verde: hay que definir sus permisos y probarlos. Este inventario no inspecciona funciones, secuencias, privilegios predeterminados ni sustituye las pruebas de grants y de aislamiento.

## Comprobación real

Se ejecuta mediante `python infra/ci/check_database.py`, después de aplicar las migraciones en la base desechable. No recibe una URL por consola ni se utiliza contra desarrollo, test remoto o producción.

Primero verifica el estado correcto. Luego desactiva RLS y retira FORCE por separado en cada una de las cuatro tablas. Cada una de las ocho alteraciones debe producir el error específico esperado. Por último crea una tabla sin clasificar y exige el noveno error. Cada cambio se revierte con rollback y se comprueba nuevamente el estado correcto.

Esto demuestra que el control detecta la ausencia de protección, incluso en tablas vacías. No demuestra por sí solo que las policies estén bien escritas: esas reglas se prueban con usuarios, espacios y operaciones reales en los otros contratos de CI.

No hay una migración nueva en este incremento. La base sigue en `0005`. El próximo trabajo es revisar permisos predeterminados y rutas de acceso por otros objetos; US-007 continúa abierta.
