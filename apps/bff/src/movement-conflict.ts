import { HttpException } from '@nestjs/common';
import { boundedJson } from './token-verifier.js';

export async function movementConflict(response: Awaited<ReturnType<typeof fetch>>): Promise<never> {
  const body = await boundedJson(response, 1024).catch(() => null) as { detail?: { codigo?: unknown } } | null;
  const code = body?.detail?.codigo;
  if (code === 'importe_atipico' || code === 'cotizacion_atipica') throw new HttpException({ codigo: code }, 409);
  throw new HttpException('No se pudo completar la operacion', 409);
}

export function validConfirmation(body: { confirmar_atipico?: unknown }) {
  return body.confirmar_atipico === undefined || typeof body.confirmar_atipico === 'boolean';
}
