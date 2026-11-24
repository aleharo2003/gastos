# Estado de Piggo frente a Jira

Revisión inicial en `c3464fd`, actualizada para las entregas recientes sobre `852965d`. Jira devuelve 54 stories abiertas. La cobertura del código y la aceptación funcional son estados distintos.

## Acceso y cuentas

| Story | Cobertura en main | Evidencia o diferencia |
|---|---|---|
| [CTAS-14](https://aleharo.atlassian.net/browse/CTAS-14) | Parcial | Login y alta de espacio personal disponibles para usuarios de prueba. Falta registro p�blico y alta autom�tica desde ese flujo. |
| [CTAS-15](https://aleharo.atlassian.net/browse/CTAS-15) | Implementado | Login, cierre y restauraci�n de sesi�n. Hoy es la secci�n inicial. La disponibilidad de test se valida por separado. |
| [CTAS-16](https://aleharo.atlassian.net/browse/CTAS-16) | Pendiente | Recuperaci�n de contrase�a desde la app. |
| [CTAS-17](https://aleharo.atlassian.net/browse/CTAS-17) | Pendiente | Instalaci�n PWA y recorridos de Android e iOS. |
| [CTAS-23](https://aleharo.atlassian.net/browse/CTAS-23) | Parcial | Alta por nombre. Faltan tipo, moneda y saldo inicial nativos, adem�s de los datos de tarjeta. |
| [CTAS-24](https://aleharo.atlassian.net/browse/CTAS-24) | Parcial | Los saldos por cuenta están en Cuentas. El [PR #75](https://github.com/aleharo2003/gastos/pull/75) agrega el consolidado convertido. El filtro de inactivas depende de CTAS-25. |
| [CTAS-25](https://aleharo.atlassian.net/browse/CTAS-25) | Pendiente | Edici�n y desactivaci�n de cuentas desde la app. |
| [CTAS-26](https://aleharo.atlassian.net/browse/CTAS-26) | Parcial | Categor�as predefinidas de egreso. Falta la cobertura de ingresos y conciliar iconos y colores con el dise�o aprobado. |
| [CTAS-27](https://aleharo.atlassian.net/browse/CTAS-27) | Pendiente | Gesti�n de categor�as personalizadas. |
| [CTAS-28](https://aleharo.atlassian.net/browse/CTAS-28) | Parcial | Registrar gasto es la entrada móvil y se pueden reutilizar los datos de un gasto reciente. Falta validar el recorrido de dos toques con los criterios de Jira. |
| [CTAS-29](https://aleharo.atlassian.net/browse/CTAS-29) | Parcial | Cuenta, fecha, categor�a, descripci�n, moneda, importe y comprobantes. Faltan nota y estado pendiente en el gasto diario. |
| [CTAS-30](https://aleharo.atlassian.net/browse/CTAS-30) | Parcial | Ingreso por cuenta y moneda con impacto en saldo. Falta categor�a de ingreso. |
| [CTAS-31](https://aleharo.atlassian.net/browse/CTAS-31) | Implementado | Transferencia en la misma moneda, saldos de origen y destino, rechazo de la misma cuenta y exclusi�n de ingresos y gastos. |
| [CTAS-32](https://aleharo.atlassian.net/browse/CTAS-32) | Parcial | Filtros, b�squeda y totales para gastos. Falta el historial unificado de movimientos. |
| [CTAS-33](https://aleharo.atlassian.net/browse/CTAS-33) | Parcial | Edici�n de gastos con rec�lculo. Faltan anulaci�n y cobertura del resto de movimientos. |
| [CTAS-34](https://aleharo.atlassian.net/browse/CTAS-34) | Parcial | Saldos calculados a partir de ingresos, gastos y transferencias. Faltan saldo inicial nativo y rec�lculo por anulaci�n. |
| [CTAS-35](https://aleharo.atlassian.net/browse/CTAS-35) | Pendiente | Importaci�n de movimientos. El CSV existente carga �ndices de ajuste. |
| [CTAS-36](https://aleharo.atlassian.net/browse/CTAS-36) | Pendiente | Exportaci�n integral de datos. |
| [CTAS-37](https://aleharo.atlassian.net/browse/CTAS-37) | Pendiente | Resguardo semanal con retenci�n y aviso de fallos. |

## Deudas y vencimientos

| Story | Cobertura en main | Evidencia o diferencia |
|---|---|---|
| [CTAS-38](https://aleharo.atlassian.net/browse/CTAS-38) | Implementado | Compromisos fijos con n�mero de cuotas e indefinidos. |
| [CTAS-39](https://aleharo.atlassian.net/browse/CTAS-39) | Implementado | Gastos variables mensuales, estimaci�n desde el historial y distinci�n de borradores. |
| [CTAS-40](https://aleharo.atlassian.net/browse/CTAS-40) | Implementado | Cuotas por �ndice, marca de ajuste pendiente y rec�lculo al cargar la variaci�n. |
| [CTAS-41](https://aleharo.atlassian.net/browse/CTAS-41) | Implementado | Plan de amortizaci�n en los sistemas soportados, con pruebas de c�lculo. Contrastar un caso bancario real antes del cierre. |
| [CTAS-42](https://aleharo.atlassian.net/browse/CTAS-42) | Implementado | Variaci�n manual e importaci�n de hist�rico por CSV. |
| [CTAS-43](https://aleharo.atlassian.net/browse/CTAS-43) | Implementado | Vencimientos, progreso, montos pagados y pendientes y resumen mensual por moneda. |
| [CTAS-44](https://aleharo.atlassian.net/browse/CTAS-44) | Implementado | Pausa de compromisos y cuota puntual �No aplica� con hist�rico conservado. |
| [CTAS-45](https://aleharo.atlassian.net/browse/CTAS-45) | Implementado | Pagos completos y parciales vinculados a cuenta y saldo. |
| [CTAS-46](https://aleharo.atlassian.net/browse/CTAS-46) | Parcial | Hay workflow programado e independiente para generar cuotas en test, con una corrida manual exitosa. Falta verificar una corrida disparada por horario. |
| [CTAS-47](https://aleharo.atlassian.net/browse/CTAS-47) | Implementado | Contador de borradores, confirmaci�n en lote y correcci�n del estimado al confirmar. |
| [CTAS-48](https://aleharo.atlassian.net/browse/CTAS-48) | Implementado | Hoy muestra pr�ximos vencimientos y vencidos, con totales y pago en pantalla. Si Registrar gasto pasa a ser la pantalla inicial, actualizar ese criterio. |
| [CTAS-49](https://aleharo.atlassian.net/browse/CTAS-49) | Parcial | Hoy calcula vencidos por fecha. Falta validar el marcado persistente que solicita el proceso diario. |

## Monedas y avisos

| Story | Cobertura en main | Evidencia o diferencia |
|---|---|---|
| [CTAS-50](https://aleharo.atlassian.net/browse/CTAS-50) | Parcial | Saldo en USD disponible por moneda. Falta fijar la moneda en la cuenta y restringir sus movimientos. |
| [CTAS-51](https://aleharo.atlassian.net/browse/CTAS-51) | Pendiente | Venta de USD con contraparte y tipo de cambio calculado. |
| [CTAS-52](https://aleharo.atlassian.net/browse/CTAS-52) | Pendiente | Registro y aceptaci�n de ofertas. |
| [CTAS-53](https://aleharo.atlassian.net/browse/CTAS-53) | Pendiente | Ranking y comparaci�n de contrapartes. |
| [CTAS-54](https://aleharo.atlassian.net/browse/CTAS-54) | Parcial | Conversi�n estimada en la interfaz. Falta congelar el tipo de cambio al pagar. |
| [CTAS-55](https://aleharo.atlassian.net/browse/CTAS-55) | Pendiente | Actualizaci�n diaria y persistencia de cotizaciones de referencia. |
| [CTAS-56](https://aleharo.atlassian.net/browse/CTAS-56) | Parcial | Referencia manual en el navegador. Faltan persistencia por fecha y prioridad sobre cotizaciones autom�ticas. |
| [CTAS-57](https://aleharo.atlassian.net/browse/CTAS-57) | Pendiente | Costo promedio de USD y ganancia o p�rdida. |
| [CTAS-58](https://aleharo.atlassian.net/browse/CTAS-58) | Pendiente | Advertencias por montos o tipos de cambio at�picos. La sugerencia de categor�a cubre otro caso. |
| [CTAS-59](https://aleharo.atlassian.net/browse/CTAS-59) | Parcial | Existe el job independiente de cuotas. Falta completar la ejecuci�n diaria de cotizaciones, vencidos y avisos. |
| [CTAS-60](https://aleharo.atlassian.net/browse/CTAS-60) | Parcial | Vista previa del piloto validada. Env�o real fallido en la ejecuci�n #3; faltan entrega confirmada y programaci�n. |
| [CTAS-61](https://aleharo.atlassian.net/browse/CTAS-61) | Pendiente | Suscripci�n y entrega push. La preferencia de canal ya existe. |
| [CTAS-62](https://aleharo.atlassian.net/browse/CTAS-62) | Parcial | Preferencias de canal, anticipaci�n, hora y eventos guardadas. El efecto se verific� en preview de correo; push y resumen siguen pendientes. |
| [CTAS-63](https://aleharo.atlassian.net/browse/CTAS-63) | Parcial | Cola, reserva e idempotencia implementadas para correo. Falta comprobar el reintento de un env�o real en test. |
| [CTAS-64](https://aleharo.atlassian.net/browse/CTAS-64) | Pendiente | Generaci�n y env�o del resumen semanal. |

## Presupuesto y reportes

| Story | Cobertura en main | Evidencia o diferencia |
|---|---|---|
| [CTAS-65](https://aleharo.atlassian.net/browse/CTAS-65) | Implementado | Límite mensual global en ARS o USD, más límites por categoría y conceptos proyectados. Ver [PR #69](https://github.com/aleharo2003/gastos/pull/69), [#70](https://github.com/aleharo2003/gastos/pull/70) y [#72](https://github.com/aleharo2003/gastos/pull/72). |
| [CTAS-66](https://aleharo.atlassian.net/browse/CTAS-66) | Implementado | L�mite semanal en ARS o USD, semana argentina de lunes a domingo, con cotizaci�n manual actual. |
| [CTAS-67](https://aleharo.atlassian.net/browse/CTAS-67) | Implementado | Consumo, disponible e indicador en Hoy y Presupuesto. |
| [CTAS-68](https://aleharo.atlassian.net/browse/CTAS-68) | Parcial | Avisos visuales de proximidad y exceso por categoría en Hoy. Falta la notificación deduplicada por período. |
| [CTAS-69](https://aleharo.atlassian.net/browse/CTAS-69) | En PR | El [PR #73](https://github.com/aleharo2003/gastos/pull/73) agrega activos, pasivos y patrimonio en Hoy, con conversión estimada. |
| [CTAS-70](https://aleharo.atlassian.net/browse/CTAS-70) | Parcial | Ya existe comparación global de gasto y proyección. El [PR #74](https://github.com/aleharo2003/gastos/pull/74) compara el mes actual por categoría. Queda el historial de presupuestos mensuales. |
| [CTAS-71](https://aleharo.atlassian.net/browse/CTAS-71) | Pendiente | Serie temporal filtrable y seguimiento de conceptos. |
| [CTAS-72](https://aleharo.atlassian.net/browse/CTAS-72) | Parcial | Gastos muestra la distribución mensual por categoría, moneda y porcentaje, con acceso a movimientos. Jira ubica el reporte en el dashboard. Ver [PR #67](https://github.com/aleharo2003/gastos/pull/67) y [#68](https://github.com/aleharo2003/gastos/pull/68). |

## Decisiones para continuar

1. Acordar qu� significa una cuenta en Piggo. Hoy una cuenta admite ARS, USD y EUR. Jira pide moneda fija en CTAS-50 y tipo y saldo inicial en CTAS-23. La decisi�n afecta los datos existentes, el saldo global y la edici�n de cuentas.
2. Confirmar la pantalla inicial. Jira pide Hoy en CTAS-15 y CTAS-48. El dise�o de Piggo prioriza Registrar gasto. La aceptaci�n debe reflejar la decisi�n elegida.
3. Validar las stories que tienen el flujo implementado en test y actualizar Jira con evidencia. Completar los faltantes de cuentas y movimientos antes de los reportes que usan esos datos.
4. Retomar el correo por separado. El piloto confirm� una cuota elegible en la [vista previa](https://github.com/aleharo2003/gastos/actions/runs/44427743616). La [ejecuci�n de env�o](https://github.com/aleharo2003/gastos/actions/runs/44429945366) fall�.

Ya est�n en main las [metas de ahorro](metas-ahorro.md) y los [comprobantes](comprobantes-gastos.md). Conviene vincularlos al tablero al actualizarlo. Para contrastar las reglas implementadas, ver [ingresos y saldos](ingresos-saldos.md), [gastos fijos](gastos-mensuales-fijos.md), [estimados variables](gastos-variables-estimados.md), [resumen mensual](resumen-mensual-deudas.md) y [presupuestos](presupuestos-limites.md).

## Entregas pendientes

Los cambios independientes pueden abrirse contra `main` en la misma tanda. Si una entrega depende del esquema o del contrato de otra, la descripción del PR debe indicar cuál se integra primero.

| Frente | Trabajo a preparar |
|---|---|
| Acceso e instalación | Registro y recuperación (CTAS-14, CTAS-16), instalación PWA (CTAS-17). La instalación habilita la validación de push en iOS. |
| Cuentas y categorías | Tipos, saldo inicial, cuentas inactivas y compatibilidad con cuentas multimoneda (CTAS-23 a CTAS-27, CTAS-34, CTAS-50). |
| Movimientos | Completar datos de gastos e ingresos, historial unificado y edición o anulación (CTAS-28 a CTAS-30, CTAS-32, CTAS-33). |
| Importación y resguardo | Importación, exportación y resguardo semanal (CTAS-35 a CTAS-37). |
| Compromisos | Validación de generación por horario y criterio de vencidos del proceso diario (CTAS-46, CTAS-49). |
| Cambio | Venta de divisas, ofertas, contrapartes, tipo congelado, referencia, resultado y alertas de montos (CTAS-51 a CTAS-58). Los reportes de operaciones dependen primero del registro de cambios. |
| Avisos | Proceso diario, correo, push, resumen y deduplicación (CTAS-59 a CTAS-64, CTAS-68). El piloto de correo sigue en pausa. |
| Reportes | Comparación histórica, evolución mensual y acceso a distribución desde Hoy (CTAS-70 a CTAS-72). |
