# Piggo: base visual v1

Primer incremento del plan aprobado: identidad, tokens y tipografía de interfaz.
La arquitectura sigue siendo Angular → NestJS BFF → FastAPI → PostgreSQL/Supabase.

## Recursos de marca

Los PNG de `apps/web/public/brand/piggo/` son copias byte por byte de
`imagenes/logo_aprobado.png` y `imagenes/mascota_aprobada.png` del handoff del usuario.
`npm run test:brand` comprueba sus SHA-256 para detectar sustituciones accidentales.

- Logo: moneda dorada, cara sin boca, lettering original con última o como hocico,
  y lema «Tu futuro, gasto a gasto». Nunca recrear el wordmark con una fuente.
- Mascota: cerdito rosado sin boca. Se reserva para usos discretos y estados útiles.
- El PNG del logo tiene fondo claro. Se presenta sobre una superficie blanca también
  en oscuro: no se invierte, recolorea, vectoriza ni se elimina su fondo en este PR.
- El favicon actual se conserva hasta revisar la derivación de moneda sola.

## Tokens

Fuente: `apps/web/src/styles/piggo-tokens.css`. El prefijo `--piggo-` define tokens
de marca, colores semánticos, tipografía, espaciado, radios, sombra y target táctil.
Los alias `--g-*` mantienen compatibles las pantallas existentes durante la migración.

| Token de marca | Valor | Procedencia |
| --- | --- | --- |
| primary | `#FEBA0E` | Píxel (620, 200) del logo original 1254 × 1254 |
| ink | `#52270D` | Píxel (300, 850) del mismo archivo |
| gold | `#FFCA28` | Propuesta de la especificación maestra |
| mascot | `#F7A4B4` | Propuesta de la especificación maestra |

El arte tiene gradientes y antialiasing; esas muestras no describen todos sus tonos.
Los colores semánticos son decisiones de interfaz para asegurar contraste, no colores
extraídos del logo. Los estados incluyen texto; no depender únicamente del color.

`light-dark()` elige cada pareja según `color-scheme`. El modo Dispositivo utiliza
la preferencia del sistema, incluso si cambia sin recargar; los modos Claro/Oscuro
fijan el esquema con `data-theme`. Se conserva la clave `gastos.theme` y el script
de inicialización previo al render para respetar las preferencias existentes.
Requiere navegadores con `light-dark()` (Chrome/Edge 123+, Firefox 120+, Safari 17.5+).

## Tipografía para revisión visual

Se propone **Nunito Sans** como candidata de interfaz en esta entrega revisable.
Es una elección provisional: no reemplaza la aprobación visual del usuario.
La fuente variable se sirve desde la propia aplicación, con `font-display: swap`
y fallback `system-ui, sans-serif`. No se consulta Google Fonts desde el navegador.
Peso del archivo original: 571240 bytes; no se añade una dependencia npm.

Fuente oficial: [Google Fonts / Nunito Sans](https://github.com/google/fonts/tree/main/ofl/nunitosans).
Blob original: `ccc8565733e7d037ede2c9cc971ceb6375e28733`.
Licencia SIL OFL 1.1 completa: `apps/web/public/fonts/nunito-sans/OFL.txt`.
SHA-256 de la fuente: `f934d7142fb4784bf828da485b7dcbd90c0c80d514e9d49a5da0ed3a1ae2491d`.
Una futura optimización WOFF2 debe conservar la licencia y verificar caracteres es-AR.

## Accesibilidad y aplicación gradual

- Texto normal: parejas principales con contraste mínimo 4.5:1.
- Bordes de campos y foco sobre fondo/superficie: mínimo 3:1.
- CTA amarillo con texto marrón; el amarillo no se usa como texto sobre blanco.
- Controles globales: mínimo 48 px; se mantienen labels y foco visible.
- Números tabulares, sin cambiar normalización decimal ni formato monetario existente.
- `prefers-reduced-motion` desactiva animaciones/transiciones y scroll animado.
- La cabecera y el acceso adoptan Piggo; las demás pantallas reciben los tokens mediante
  alias. Los controles reutilizables y la navegación responsive se entregan después.
- Los componentes existentes pueden tener tamaños propios; los recorridos reales deben
  comprobarse al rediseñar cada pantalla. La prueba de tokens no certifica toda la UI.

## Verificación

Desde `apps/web`: `npm run test:brand`, `npm test -- --watch=false`,
`npm run build` y `npm run build:test`.
El CI ejecuta contraste e integridad junto con las pruebas y compilaciones existentes.

El primer conjunto comprueba 34 parejas de contraste y la integridad de ambos PNG.
No sustituye la revisión visual de estados, foco, zoom, móvil y modo oscuro.

## Siguientes incrementos

1. Controles compartidos.
2. Separar formulario/listado conservando estado, permisos e idempotencia.
3. Navegación y Registrar gasto responsive como entrada principal en móvil.
4. Confirmación y comprobantes con gasto guardado antes de subir archivos.

Registro rápido, últimas selecciones persistidas, borrador duradero, categorías
administrables, ingresos, saldos, vencimientos y límites por categoría son historias
separadas. Este PR no cambia API, BFF, base de datos, rutas ni reglas financieras.
