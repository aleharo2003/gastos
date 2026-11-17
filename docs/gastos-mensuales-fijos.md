# Gastos mensuales fijos sin fecha final

Primer incremento de recurrencia fija, basado en los PR #33 y #34.
Cubre el alta indefinida de CTAS-38 y la pausa del plan de CTAS-44.
La generacion mensual aporta una parte de CTAS-46 y CTAS-59.
No completa esas stories: quedan importes estimados/borradores, recordatorios,
cotizaciones, alertas de producto y marcar una cuota puntual como no aplica.
Los gastos variables (CTAS-39 y CTAS-47) siguen en el siguiente incremento.

## Reglas de producto

Al marcar gasto mensual sin cantidad final, total_cuotas es null.
Nombre, cuenta, moneda, importe fijo y dia de vencimiento quedan definidos al crear.
El primer vencimiento debe pertenecer al mes actual o uno futuro (Buenos Aires).
Si empieza este mes, se crea su cuota inicial; si empieza mas adelante, permanece
visible con total generado cero hasta que llegue ese periodo.
Los planes finitos existentes mantienen su calendario completo y sus pagos.

Cada mes aparece una cuota, con el dia original limitado al ultimo dia del mes:
31 de enero, ultimo dia de febrero, 31 de marzo. Un indice unico por
espacio/compromiso/periodo impide duplicados aunque cambien UUID o numero de cuota.

El total de un gasto indefinido significa **total generado hasta ahora**. No existe
un total futuro conocido. Pagado y pendiente se derivan de las cuotas generadas.
Pagar una cuota no detiene los meses siguientes y crear o pausar no genera gastos.

Pausar deja de generar cuotas nuevas y conserva historial y saldos pendientes;
las cuotas existentes se pueden seguir pagando. Reactivar prepara la cuota del
mes actual si corresponde y falta. No rellena los meses pausados ni crea cuotas
de monto cero. El numero corresponde al mes desde el inicio y puede saltar periodos.
La pausa se limita a planes indefinidos; no cancela cuotas finitas ya planificadas.

El proceso prepara solo el mes actual. Los reintentos diarios recuperan fallos dentro
de ese mes. Si falta una ejecucion exitosa durante un mes entero, se debe revisar
ese periodo: no hay reconstruccion automatica de meses anteriores.

Los importes fijos se usan como conocidos y sus cuotas quedan pendientes.
Los borradores estimados y su confirmacion pertenecen al incremento de montos variables.
El resumen mensual y los comprobantes usan las cuotas y pagos existentes.

## Contratos

POST /spaces/{space}/commitments acepta total_cuotas: null ademas de 1..600.
Las lecturas incorporan pausado y version.
PATCH /spaces/{space}/commitments/{id}: pausado booleano, version entera positiva.
Un reintento del cambio inmediatamente anterior devuelve el estado guardado.
Una version vieja incompatible devuelve 409; leer el estado antes de reintentar.
Owner/editor escriben, lector consulta; no se habilita editar importe ni cuenta.

## Decision del ejecutor

Se propone GitHub Actions como ejecutor de esta primera tarea, reutilizando la
infraestructura del repositorio. Workflow separado del despliegue, diario a las
01:17 de Buenos Aires y con ejecucion manual en main. No llama a API ni BFF.
Los limites, retrasos y notificaciones dependen de la configuracion de GitHub Actions;
el cron no garantiza una hora exacta. Habilitar avisos de fallos para quien opere
el workflow. No se afirma entrega de alertas o recordatorios de producto.

El usuario app_jobs es LOGIN, NOINHERIT y NOBYPASSRLS, sin membresias, DDL ni
permisos directos sobre tablas. Solo ejecuta public.generar_cuotas_mes(), sin
parametros ni resultados financieros: devuelve cantidad de cuotas creadas.
La funcion SECURITY DEFINER pertenece a app_migrator y usa search_path=pg_catalog,
tablas public calificadas y la policy explicita del migrador bajo FORCE RLS.
El contrato permite insertar exclusivamente las cuotas fijas del periodo actual
de planes indefinidos activos en todos los espacios. No modifica pagos ni gastos.
El usuario web app_runtime no puede invocarla.
Un bloqueo transaccional global y la unicidad por periodo protegen reintentos.
El ejecutor valida su identidad efectiva y no imprime URLs, secretos ni tracebacks.
No se usan conexiones de administrador o migrador en el workflow.

## Activacion operativa (pendiente, no realizada por el PR)

1. Integrar primero el PR #33; este trabajo parte de su rama actual.
2. Aplicar Alembic 0017 con el migrador y desplegar API/BFF/web del mismo incremento.
3. Un administrador ejecuta infra/postgres/provision-jobs.sql con psql -X --file.
   El script pide una contraseña dedicada con el mecanismo de psql, sin incluirla
   en el SQL versionado. Conserva la separacion de roles y falla ante privilegios
   incompatibles. Para desarrollo local, jobs_role.provision_jobs reutiliza Docker.
4. Guardar en el entorno GitHub test el secreto JOBS_DATABASE_URL, URL PostgreSQL
   del usuario app_jobs (o su usuario de pooler), con TLS para el destino remoto.
   Es distinta de DATABASE_URL y MIGRATION_DATABASE_URL; nunca usar service_role.
5. Con el workflow en main, ejecutar Generar cuotas mensuales test manualmente.
   Revisar resultado y repetir: la segunda ejecucion debe crear cero cuotas.
6. Confirmar que Actions programadas y avisos de fallo estan habilitados. Consultar
   sus ejecuciones para el registro de errores y reintentos diarios.

Sin esos pasos, el PR no deja el proceso remoto activado. No requiere instalar
un servicio HTTP nuevo ni mantener despiertos los servicios web gratuitos.

## Validacion

CI reconstruye PostgreSQL y comprueba 0017 contra los modelos, conserva planes
finitos, valida altas futuras, pausa versionada, reactivacion sin duplicar,
pagos previos, concurrencia, fin de mes, unicidad por periodo y aislamiento.
Provisiona app_jobs solo en la base desechable y demuestra que no puede leer/borrar
tablas, crear objetos o ejecutar funciones de usuario web; app_runtime tampoco
puede ejecutar el generador. API, BFF, Angular y ejecutor tienen pruebas adicionales.
La activacion remota y la revision visual se verifican por separado.
