import { BadGatewayException, ConflictException, Injectable, Logger, ServiceUnavailableException, UnauthorizedException } from '@nestjs/common';
import { AuthUnavailable, boundedJson, InvalidToken, TokenVerifier } from './token-verifier.js';

@Injectable()
export class AuthService {
  private verifier?: TokenVerifier;
  private readonly logger = new Logger(AuthService.name);

  async getMe(token: string): Promise<{ usuario_id: string }> {
    return this.requestIdentity(token, false);
  }

  async getPersonalSpace(token: string): Promise<{ usuario_id: string; espacio_id: string; nombre: string }> {
    const result = await this.requestIdentity(token, true);
    return result as { usuario_id: string; espacio_id: string; nombre: string };
  }

  async verifyIdentity(token: string): Promise<string> {
    try {
      this.verifier ??= new TokenVerifier(process.env.AUTH_SUPABASE_PROJECT_REF ?? '');
      return await this.verifier.verify(token);
    } catch (error) {
      if (error instanceof InvalidToken) throw new UnauthorizedException('No autenticado');
      if (error instanceof AuthUnavailable) throw new ServiceUnavailableException('Autenticacion no disponible');
      throw new ServiceUnavailableException('Autenticacion no disponible');
    }
  }

  private async requestIdentity(token: string, personal: boolean): Promise<{ usuario_id: string; espacio_id?: string; nombre?: string }> {
    const userId = await this.verifyIdentity(token);
    let phase = 'CONFIG_URL';
    let upstreamStatus: number | undefined;
    const started = Date.now();
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      phase = 'CONFIG_TIEMPO';
      const rawTimeout = process.env.API_TIMEOUT_MS ?? '5000';
      const timeout = Number(rawTimeout);
      if (!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 2147483647) throw new Error();
      phase = 'CONEXION';
      const response = await fetch(new URL(personal ? '/personal-space' : '/me', base), {
        method: personal ? 'POST' : 'GET',
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
        redirect: 'error', signal: AbortSignal.timeout(timeout),
      });
      upstreamStatus = response.status;
      phase = 'RESPUESTA_HTTP';
      if (personal && response.status === 409) throw new ConflictException('El espacio requiere revision');
      if (response.status === 401) throw new UnauthorizedException('No autenticado');
      if (response.status === 503) throw new ServiceUnavailableException('Autenticacion no disponible');
      if (!response.ok) throw new Error();
      phase = 'RESPUESTA_JSON';
      const data = await boundedJson(response, 4096) as { usuario_id?: unknown; espacio_id?: unknown; nombre?: unknown };
      phase = 'IDENTIDAD';
      if (!data || data.usuario_id !== userId) throw new Error();
      if (personal) {
        phase = 'ESPACIO';
        if (data.espacio_id !== userId || typeof data.nombre !== 'string' || data.nombre.length > 200) throw new Error();
        return { usuario_id: userId, espacio_id: data.espacio_id, nombre: data.nombre };
      }
      return { usuario_id: userId };
    } catch (error) {
      if (error instanceof UnauthorizedException || error instanceof ServiceUnavailableException || error instanceof ConflictException) throw error;
      // Lista cerrada: nunca registrar message, stack, URL, cuerpo, token o identidad.
      const detail = error as { name?: unknown; cause?: { code?: unknown } };
      const allowed = ['ECONNREFUSED', 'ECONNRESET', 'ENOTFOUND', 'EAI_AGAIN',
        'ETIMEDOUT', 'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT',
        'CERT_HAS_EXPIRED', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE'];
      const code = typeof detail?.cause?.code === 'string' && allowed.includes(detail.cause.code)
        ? detail.cause.code : detail?.name === 'TimeoutError' ? 'TIMEOUT' : 'NO_CLASIFICADO';
      this.logger.error(`FastAPI diagnostico: operacion=${personal ? 'alta' : 'me'} fase=${phase} http=${upstreamStatus ?? '-'} causa=${code} duracion_ms=${Date.now() - started}`);
      // Mantener el contrato publico y no adjuntar causas privadas.
      throw new BadGatewayException('No se pudo consultar FastAPI');
    }
  }
}
