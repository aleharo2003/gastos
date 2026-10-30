# Plan de consulta de membresías

Observado el 30 de octubre de 2026 sobre el commit 92595692c5e9a2c0d67a25cac4082efca4c37b57 del PR #9, con las migraciones hasta 0006.

Se reconstruyó PostgreSQL Supabase en un proyecto desechable. Se cargaron 1.000 perfiles, 10 espacios y 10.000 membresías ficticias como app_migrator y se ejecutó ANALYZE sobre miembros_espacio. Las consultas se ejecutaron como app_runtime mediante runtime_transaction, con RLS y FORCE activos. No se desactivaron scans secuenciales ni se forzó un índice.

## Resultado

| Consulta | Acceso observado | Índice | Filas devueltas |
|---|---|---|---|
| Usuario y espacio concretos | Index Scan | pk_miembros_espacio | 1 |
| Membresías de un usuario | Bitmap Index Scan y Bitmap Heap Scan | pk_miembros_espacio | 10 |

La primera búsqueda usa usuario_id y espacio_id en Index Cond. La segunda usa usuario_id, la primera columna de la clave primaria. En ambas aparece además la comprobación del usuario del contexto impuesta por RLS.

El resultado respalda reutilizar la PK compuesta (usuario_id, espacio_id) para estas consultas. No hace falta agregar otro índice idéntico. El índice separado por espacio_id cumple un propósito distinto y no se retira en esta revisión.

## Consultas observadas

Se usaron parámetros vinculados de la fixture y EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON):

```sql
SELECT rol
FROM public.miembros_espacio
WHERE usuario_id = :usuario_id AND espacio_id = :espacio_id;

SELECT espacio_id, rol
FROM public.miembros_espacio
WHERE usuario_id = :usuario_id;
```

Los planes completos están en [la evidencia JSON](evidencias/us-007-planes-membresias.json). Sus UUID son ficticios; no contiene credenciales ni datos de usuarios reales.

## Alcance

Es una observación de acceso a membresías con esta distribución de datos, no un benchmark ni una garantía de latencia en producción. No prueba el plan completo de todos los futuros endpoints o de cada consulta financiera con subconsultas RLS. Los tiempos del JSON corresponden al equipo de prueba y no se usan como umbral de aceptación.

No se exige un tipo exacto de scan en CI: las estadísticas, el volumen y la versión del optimizador pueden cambiar una elección válida. Las pruebas de seguridad del pipeline siguen comprobando permisos y resultados.

Tras observar los planes se eliminaron los datos ficticios y se completaron las verificaciones restantes de la reconstrucción. Los esquemas externos y centinelas se conservaron. Se retiraron los contenedores y volúmenes del proyecto temporal; no se modificaron las bases persistentes.
