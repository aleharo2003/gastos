# Estado de Piggo

## Incremento actual

- Rama: `feature/piggo-design-foundation`.
- Base: `main` en `ced4b217e119d20df0995c5acb6651324eef5c31`.
- Alcance: primer PR del plan aprobado, base visual Piggo.
- Recursos originales conservados, tokens claros/oscuros, Nunito Sans candidata
  alojada localmente, cabecera y copy de acceso con la marca y el lema exactos.
- Contratos, almacenamiento de sesión/tema, RLS y arquitectura sin cambios.
- Prueba local de marca: 36 comprobaciones aprobadas.
- Pruebas Angular y build locales bloqueados: Node instalado 22.18.0 frente al
  24.22.0 del proyecto, y dependencias ausentes de caché. El PR conserva Node y lockfile.
  Consultar los resultados de CI del PR para la validación completa.

## Próximo PR

Controles compartidos basados en tokens. Después, separar Registrar de Movimientos
sin perder borradores ni IDs de reintento y aplicar el layout móvil/escritorio.
La tipografía sigue pendiente de aprobación visual. Mantener categorías opcionales
de texto, sin iconos, y la mascota sin boca.
