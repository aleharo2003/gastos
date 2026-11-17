# Estado de Piggo

## Base actual

Ingresos y saldos (PR #30), transferencias internas (PR #31) y metas de ahorro
(PR #32) están integrados en main. Base de este incremento:
913a7c0f85db7e8c1f5c708e6f7ae9004a6f60c2.

Angular → NestJS BFF → FastAPI → PostgreSQL/Supabase, con RLS/FORCE,
identidad transaccional, dinero decimal exacto y migraciones Alembic.

## Base en revisión: deudas fijas finitas (PR #33)

Rama: feature/fixed-installment-debts. Agrega planes con cuotas mensuales,
progreso, pagos completos/parciales y comprobantes. Crear un plan no mueve dinero;
pagar crea un único gasto y reduce la deuda en la misma transacción.
Ver compromisos-fijos.md para reglas, límites y cobertura parcial de CTAS-38,
CTAS-43 y CTAS-45. Migración requerida: 0016.

El backlog CTAS ya pudo leerse. Las stories mencionadas no quedan cerradas por
este incremento. Gastos mensuales indefinidos/variables y automatización continúan
en PRs posteriores; no confundir el calendario finito con generación mensual automática.

El código y las pruebas se entregan mediante PR. Consultar su CI para resultados
ejecutados. La revisión visual móvil/escritorio y la comprobación del SHA publicado
tras fusionar se registran por separado; esta nota no certifica un despliegue.

## Incremento dependiente: resumen mensual

Rama: feature/monthly-debt-summary, basada en feature/fixed-installment-debts.
Completa la consulta mensual de las cuotas fijas existentes: comprometido, pagado,
pendiente y vencido por moneda, con navegación al pago y paginación.
Ver resumen-mensual-deudas.md. Sin migraciones adicionales.
El PR #33 todavía debe integrarse; este incremento no implica su fusión.

## Orden de producto acordado

1. Ahorros/metas: integrado.
2. Deudas y cuotas: incremento actual.
3. Obligaciones y gastos mensuales, vencimientos y pagos, según stories CTAS.

Backlog: https://aleharo.atlassian.net/jira/software/c/projects/CTAS/boards/34/backlog

## Diseño pendiente

La base visual Piggo conserva los recursos originales y tokens claros/oscuros.
Los controles compartidos y el rediseño de Registrar/Movimientos siguen pendientes
del plan de diseño. La tipografía es candidata, sin afirmar aprobación visual.
Mantener categorías de texto, sin iconos, y mascota sin boca.

## Incremento: gastos mensuales fijos indefinidos

Rama feature/fixed-monthly-commitments, basada en la rama del PR #33 tras integrar
el #34. Agrega total_cuotas null, pausa/reactivacion versionada, calendario unico por
periodo y generador independiente restringido. Requiere migracion 0017.
Ver gastos-mensuales-fijos.md para limites y pasos de activacion.
El rol app_jobs y el secreto JOBS_DATABASE_URL remoto requieren configuracion
administrativa: el PR por si solo no activa la programacion en el entorno test.
Montos variables, confirmacion de estimados, no aplica y avisos siguen pendientes.
