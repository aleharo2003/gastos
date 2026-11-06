# Crear y listar cuentas

## Alcance
En Mi espacio se muestran las cuentas guardadas y un formulario para agregar
una cuenta por nombre. Ejemplos: Efectivo, Banco o Billetera.
Este incremento usa la tabla existente; no agrega migraciones ni dependencias.
No implementa saldos, monedas, tipos de cuenta, edición, borrado ni movimientos.

## Recorrido
Angular usa GET y POST /api/spaces/{espacio_id}/accounts en el BFF.
El BFF valida el token y llama a las rutas equivalentes de FastAPI.
FastAPI vuelve a validar el JWT y usa runtime_transaction con usuario y espacio.
Las consultas usan parámetros SQL; RLS sigue siendo la barrera de aislamiento.

Una membresía owner o editor permite crear. Lector solo puede listar.
No alcanza con conocer el UUID de un espacio: se exige pertenencia.
No se aceptan usuario_id ni rol en el cuerpo. La identidad proviene del token.

El nombre se recorta y debe tener entre 1 y 80 caracteres, sin caracteres de control.
El cuerpo de creación contiene id y nombre. Angular genera el UUID antes del envío.
Un reintento con el mismo ID y nombre devuelve la misma cuenta; otro nombre
con ese ID produce conflicto. Un ID que pertenece a otro espacio no revela datos.
Se permiten nombres iguales con IDs distintos: no se usa el nombre como identidad.

## Reintentos y listado
Mientras el formulario permanece abierto, un fallo conserva el ID de la solicitud.
Reintentar sin cambiar el nombre no crea otra cuenta. El botón se bloquea
durante el envío. Tras un resultado incierto, también puede actualizarse la lista.
Recargar la página o cambiar el nombre abandona ese identificador pendiente:
antes de repetir una operación incierta, comprobar la lista.

La lista se entrega en páginas de 100 cuentas, ordenadas por ID, con next_offset.
Ver más solicita otra página y Actualizar lista vuelve a la primera.
Si otras personas crean cuentas durante la paginación, actualizar para reconciliar.
La pantalla descarta respuestas tardías después de cerrar sesión.

## Prueba en test
1. Ingresar y pulsar Abrir mi espacio.
2. Crear Efectivo: debe aparecer Cuenta guardada y una fila Efectivo.
3. Recargar, volver a abrir el espacio y comprobar que la cuenta sigue.
4. Crear otra cuenta, por ejemplo Banco.
5. Un nombre vacío no debe enviarse.

No agregar variables en Render. Publicar mediante el pipeline existente.
CI prueba permisos, aislamiento, reintentos concurrentes, paginación y rutas HTTP.
La prueba de PostgreSQL usa una base desechable.
El siguiente incremento utilizará estas cuentas para registrar gastos.
