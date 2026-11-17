# Estado de Piggo

## Base actual

Ingresos y saldos (PR #30) y transferencias internas (PR #31) están integrados en
main. La base de este incremento es 86b598f33ab18f8d83ef46e0583fc09702895211.
El flujo técnico sigue siendo Angular → NestJS BFF → FastAPI → PostgreSQL/Supabase,
con RLS/FORCE, identidad transaccional y migraciones Alembic.

## Incremento en revisión: completar ahorros

Rama: feature/savings-goals. Agrega metas con objetivo, cuenta/moneda dedicada,
fecha opcional, progreso derivado del saldo, faltante, edición versionada,
archivo/reactivación y preparación de aportes/retiros desde transferencias.
Una sola meta activa por cuenta y moneda evita atribuir el mismo saldo a dos
objetivos. No se generan nuevos ingresos/gastos al crear o editar una meta.
Ver metas-ahorro.md para reglas, contratos y criterios de aceptación.

El código y las pruebas se entregan mediante PR. Consultar el CI de ese PR para
resultados ejecutados; la revisión visual móvil/escritorio se registra por separado.
Esta nota no certifica un despliegue: validar el SHA publicado tras fusionar.

## Orden de producto acordado

1. Completar y revisar ahorros/metas.
2. Deudas y cuotas.
3. Obligaciones y gastos mensuales, vencimientos y pagos, según stories CTAS.

Backlog aportado:
https://aleharo.atlassian.net/jira/software/c/projects/CTAS/boards/34/backlog

La lectura requiere autorización de Atlassian. Hasta acceder, no inventar IDs ni
criterios CTAS. El handoff Piggo también distingue estimaciones de obligaciones,
pagos y gastos reales: evitar doble contabilización al registrar pagos.

## Diseño pendiente

La base visual Piggo conserva los recursos originales y tokens claros/oscuros.
Los controles compartidos y el rediseño de Registrar/Movimientos siguen pendientes
del plan de diseño. La tipografía es candidata, sin afirmar aprobación visual.
Mantener categorías de texto, sin iconos, y mascota sin boca.
