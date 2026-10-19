import { BadGatewayException, Injectable } from '@nestjs/common';

@Injectable()
export class AppService {
  getHello(): string {
    return 'Esta funcionando OK!';
  }

  async getApiMessage(): Promise<{ message: string }> {
    const apiUrl =
      process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';

    try {
      const response = await fetch(apiUrl, {
        signal: AbortSignal.timeout(5000),
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
      throw new BadGatewayException('No se pudo consultar FastAPI', {
        cause: error,
      });
    }
  }
}