# Estado de Piggo

Main incorpora ingresos, transferencias y ahorros (PR #30 a #32).
La rama del PR #33 ya integra #34 (resumen mensual) y #35 (gastos fijos indefinidos).
Al iniciar este incremento, #33 sigue abierto hacia main.

## Incremento en revision: montos variables

Rama feature/variable-monthly-commitments, basada en feature/fixed-installment-debts.
Agrega gastos variables, cuotas estimadas, aviso global y confirmacion en lote.
Confirmar no crea gastos; pagar requiere un importe confirmado.
Requiere migracion 0018, posterior a 0017. Ver gastos-variables-estimados.md.

El ejecutor independiente usa el mismo rol app_jobs y la misma funcion actualizada.
La activacion remota del rol, permisos y JOBS_DATABASE_URL de test permanece
pendiente de verificacion operativa. No se considera activa solo por integrar el PR.

## Siguientes incrementos

No aplica puntual, ajustes/intereses, recordatorios y demas tareas del proceso diario.
Consultar CI y revision visual por separado; validar el SHA publicado tras fusionar.

Backlog: https://aleharo.atlassian.net/jira/software/c/projects/CTAS/boards/34/backlog
