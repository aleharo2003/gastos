# Estado de Piggo

## Base e integracion

Main incorpora ingresos, transferencias y ahorros (PR #30 a #32).
El PR #34 de resumen mensual ya se fusiono en la rama del PR #33 de deudas,
que todavia esta abierto hacia main al iniciar este incremento.
No confundir esa fusion entre ramas con un despliegue.

## Incremento en revision: gastos mensuales fijos

Rama feature/fixed-monthly-commitments, basada en feature/fixed-installment-debts.
Agrega total_cuotas null, pausa/reactivacion versionada, calendario unico por periodo
y generador independiente restringido. Requiere migracion 0017.
Ver gastos-mensuales-fijos.md para reglas, cobertura parcial de CTAS y activacion.

La provision administrativa de app_jobs se separa del GRANT de la funcion, que
realiza su propietario app_migrator. El secreto JOBS_DATABASE_URL del entorno test
y la activacion/verificacion del workflow remoto siguen pendientes.
El PR por si solo no activa la programacion.

## Siguientes incrementos

Montos variables y confirmacion de estimados (CTAS-39/47), no aplica puntual,
ajustes e intereses, recordatorios y demas tareas del proceso diario.
Las stories no se consideran terminadas solo por este incremento.

Consultar el CI de cada PR para resultados ejecutados. La revision visual y la
comprobacion del SHA desplegado se verifican por separado.

Backlog: https://aleharo.atlassian.net/jira/software/c/projects/CTAS/boards/34/backlog
