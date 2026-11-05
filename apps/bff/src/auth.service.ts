import { BadGatewayException, Injectable, ServiceUnavailableException, UnauthorizedException } from '@nestjs/common';
import { AuthUnavailable, boundedJson, InvalidToken, TokenVerifier } from './token-verifier.js';

@Injectable()
export class AuthService {
  private verifier?: TokenVerifier;

  async getMe(token: string): Promise<{ usuario_id: string }> {
    let userId: string;
    try {
      this.verifier ??= new TokenVerifier(process.env.AUTH_SUPABASE_PROJECT_REF ?? '');
      userId = await this.verifier.verify(token);
    } catch (error) {
      if (error instanceof InvalidToken) throw new UnauthorizedException('No autenticado');
      if (error instanceof AuthUnavailable) throw new ServiceUnavailableException('Autenticacion no disponible');
      throw new ServiceUnavailableException('Autenticacion no disponible');
    }
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const rawTimeout = process.env.API_TIMEOUT_MS ?? '5000';
      const timeout = Number(rawTimeout);
      if (!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 2147483647) throw new Error();
      const response = await fetch(new URL('/me', base), {
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
        redirect: 'error', signal: AbortSignal.timeout(timeout),
      });
      if (response.status === 401) throw new UnauthorizedException('No autenticado');
      if (response.status === 503) throw new ServiceUnavailableException('Autenticacion no disponible');
      if (!response.ok) throw new Error();
      const data = await boundedJson(response, 4096) as { usuario_id?: unknown };
      if (!data || data.usuario_id !== userId) throw new Error();
      return { usuario_id: userId };
    } catch (error) {
      if (error instanceof UnauthorizedException || error instanceof ServiceUnavailableException) throw error;
      // No adjuntar causas que puedan incluir el token o respuestas privadas.
      throw new BadGatewayException('No se pudo consultar FastAPI');
    }
  }
}
