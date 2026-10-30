# Integridad de relaciones entre espacios

RLS decide qué filas puede leer o escribir el usuario. Una clave foránea decide si una referencia es válida. Son comprobaciones diferentes.

Para una entidad con espacio_id y cuenta_id, FOREIGN KEY (cuenta_id) REFERENCES cuentas(id) solo exige que la cuenta exista. No obliga a que sea del mismo espacio. El contrato elegido es FOREIGN KEY (espacio_id, cuenta_id) REFERENCES cuentas(espacio_id, id), con ambas columnas obligatorias. La tabla cuentas ya proporciona la clave única de destino desde 0005.

## Lo que existe y lo que no

Todavía no existe movimientos ni otra entidad financiera hija de cuentas. Este incremento no crea esa funcionalidad ni una migración. La base permanece en 0006. La FK definitiva y los filtros del repositorio deben implementarse y probarse en la story que agregue esa entidad.

CI agrega dos verificaciones:

1. Audita las FKs existentes cuyo origen y destino tienen espacio_id. Exige que el enlace incluya espacio_id a espacio_id, que ambos espacios sean NOT NULL y que la constraint esté validada. Hoy no hay una relación de negocio con ambos extremos de ese tipo; por eso esa parte del control no demuestra una funcionalidad existente.
2. Crea una tabla de prueba en public dentro de una transacción que nunca se confirma que referencia las cuentas reales mediante la FK compuesta. Inserta vínculos válidos en dos espacios, rechaza INSERT cruzados en ambos sentidos y UPDATE de cuenta o espacio con SQLSTATE 23503 y el nombre exacto de la constraint. Luego reemplaza temporalmente la FK por una simple: el auditor la detecta y PostgreSQL admite el enlace cruzado, mostrando por qué es insuficiente. Un rollback restaura la FK compuesta y se repite el rechazo.

La prueba se ejecuta como app_migrator, que puede operar en ambos espacios: el rechazo viene de integridad referencial, no de ocultar la fila mediante RLS. No sustituye las pruebas runtime de las entidades futuras. Se revierten tanto los datos preparados como la tabla de prueba; el entorno entero es además desechable.

## Límites del auditor

No identifica una FK completamente ausente ni infiere relaciones a partir del nombre cuenta_id. Tampoco convierte columnas opcionales en obligatorias. Cada nueva entidad requiere revisar sus FKs, nulabilidad, policies, grants y operaciones reales. Si aparecen vínculos entre espacios deliberados o catálogos globales, se deberá decidir su contrato y ajustar este control explícitamente.

## Ejecución

Ejecutar python infra/ci/check_database.py. No ejecutar esta comprobación manualmente contra bases persistentes.

US-007 sigue pendiente de la revisión del conjunto y de resolver qué criterios corresponden a las entidades futuras. Este contrato transitorio no se presenta como una relación financiera ya implementada.

La tabla de prueba es una tabla ordinaria creada y retirada mediante rollback, no CREATE TEMPORARY: PostgreSQL no permite que una tabla TEMPORARY tenga una FK hacia una tabla permanente. No llega a confirmarse ni queda en la base al finalizar.
