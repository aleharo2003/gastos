import { HttpErrorResponse } from '@angular/common/http';

export class AnomalyCancelled extends Error {}

export async function confirmAnomaly<T>(send: (confirmation: { confirmar_atipico?: true }) => Promise<T>): Promise<T> {
  try {
    return await send({});
  } catch (error) {
    if (!(error instanceof HttpErrorResponse) || error.status !== 409) throw error;
    const code = error.error?.codigo;
    const warning = code === 'importe_atipico'
      ? 'Este importe supera diez veces el promedio de la categoría en esta moneda. ¿Querés guardarlo igual?'
      : code === 'cotizacion_atipica'
        ? 'El tipo de cambio difiere más de 30 % de la referencia. ¿Querés registrar la venta igual?'
        : null;
    if (!warning) throw error;
    if (!window.confirm(warning)) throw new AnomalyCancelled();
    return send({ confirmar_atipico: true });
  }
}
