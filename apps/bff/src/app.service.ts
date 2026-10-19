import { BadGatewayException, Injectable } from '@nestjs/common';

function readApiTimeout(value: string): number {
  const timeout = Number(value);
  if (!/^\d+$/.test(value) || !Number.isInteger(timeout) || timeout < 1 || timeout > 2_147_483_647) {
    throw new Error('API_TIMEOUT_MS debe ser un entero entre 1 y 2147483647.');
  }
  return timeout;
}

@Injectable()
export class AppService {
  private readonly apiUrl = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';
  private readonly apiTimeoutMs = readApiTimeout(process.env.API_TIMEOUT_MS ?? '5000');

  getHello(): string {
    return 'Hello World!';
  }

  async getApiMessage(): Promise<{ message: string }> {
    try {
      const response = await fetch(this.apiUrl, {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(this.apiTimeoutMs),
      });

      if (!response.ok) {
        throw new Error(`FastAPI respondió con HTTP ${response.status}`);
      }

      const data: unknown = await response.json();
      if (
        typeof data !== 'object' ||
        data === null ||
        !('message' in data) ||
        typeof data.message !== 'string'
      ) {
        throw new Error('La respuesta de FastAPI tiene un formato inválido');
      }

      return { message: data.message };
    } catch (error) {
      throw new BadGatewayException('No se pudo consultar FastAPI', { cause: error });
    }
  }
}
