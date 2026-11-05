import { createRemoteJWKSet, customFetch, decodeProtectedHeader, jwtVerify } from 'jose';

export class InvalidToken extends Error {}
export class AuthUnavailable extends Error {}

export async function boundedJson(response: Response, limit: number): Promise<unknown> {
  if (!response.body) throw new Error('Respuesta vacia');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      size += part.value.length;
      if (size > limit) throw new Error('Respuesta demasiado grande');
      chunks.push(part.value);
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown;
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export class TokenVerifier {
  private readonly issuer: string;
  private readonly keys: ReturnType<typeof createRemoteJWKSet>;

  constructor(project: string) {
    if (!/^[a-z0-9]{20}$/.test(project)) throw new AuthUnavailable();
    this.issuer = `https://${project}.supabase.co/auth/v1`;
    let retryAfter = 0;
    this.keys = createRemoteJWKSet(new URL(`${this.issuer}/.well-known/jwks.json`), {
      timeoutDuration: 5000, cooldownDuration: 30000, cacheMaxAge: 300000,
      [customFetch]: async (url, options) => {
        if (Date.now() < retryAfter) throw new AuthUnavailable();
        try {
          const response = await fetch(url, { ...options, redirect: 'error' });
          if (response.status !== 200) throw new AuthUnavailable();
          const data = await boundedJson(response, 65536) as { keys?: unknown };
          if (!data || !Array.isArray(data.keys) || data.keys.length < 1 || data.keys.length > 16) throw new AuthUnavailable();
          const ids = new Set<string>();
          const keys = data.keys.filter((key: unknown) => {
            if (!key || typeof key !== 'object') throw new AuthUnavailable();
            const k = key as Record<string, unknown>;
            if (k.kty !== 'EC' || k.crv !== 'P-256' || k.alg !== 'ES256' || k.use !== 'sig') return false;
            if (typeof k.kid !== 'string' || k.kid.length < 1 || k.kid.length > 200 || ids.has(k.kid) || 'd' in k) throw new AuthUnavailable();
            if ('key_ops' in k && JSON.stringify(k.key_ops) !== '["verify"]') throw new AuthUnavailable();
            ids.add(k.kid);
            return true;
          });
          if (!keys.length) throw new AuthUnavailable();
          return new Response(JSON.stringify({ keys }), { status: 200 });
        } catch {
          retryAfter = Date.now() + 30000;
          throw new AuthUnavailable();
        }
      },
    });
  }

  async verify(token: string): Promise<string> {
    try {
      if (!token || token.length > 16384) throw new InvalidToken();
      let header: ReturnType<typeof decodeProtectedHeader>;
      try { header = decodeProtectedHeader(token); } catch { throw new InvalidToken(); }
      if (header.alg !== 'ES256' || typeof header.kid !== 'string' || !header.kid || header.kid.length > 200 ||
          ['crit', 'jku', 'x5u', 'jwk'].some((name) => name in header)) throw new InvalidToken();
      const { payload } = await jwtVerify(token, this.keys, {
        algorithms: ['ES256'], issuer: this.issuer, audience: 'authenticated', clockTolerance: 30,
        requiredClaims: ['iss', 'aud', 'exp', 'iat', 'sub', 'role', 'is_anonymous', 'session_id'],
      });
      if (payload.aud !== 'authenticated' || payload.role !== 'authenticated' || payload.is_anonymous !== false) throw new InvalidToken();
      for (const name of ['exp', 'iat', 'nbf']) {
        if (name in payload && !Number.isSafeInteger(payload[name])) throw new InvalidToken();
      }
      if (payload.exp! <= payload.iat! || payload.iat! > Date.now() / 1000 + 30) throw new InvalidToken();
      const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
      for (const value of [payload.sub, payload.session_id]) {
        if (typeof value !== 'string' || !uuid.test(value) || value === '00000000-0000-0000-0000-000000000000') throw new InvalidToken();
      }
      return payload.sub!.toLowerCase();
    } catch (error) {
      if (error instanceof InvalidToken) throw error;
      const code = (error as { code?: string })?.code;
      if (code && ['ERR_JWT_EXPIRED', 'ERR_JWT_CLAIM_VALIDATION_FAILED', 'ERR_JWS_SIGNATURE_VERIFICATION_FAILED',
        'ERR_JWS_INVALID', 'ERR_JWT_INVALID', 'ERR_JOSE_ALG_NOT_ALLOWED', 'ERR_JWKS_NO_MATCHING_KEY'].includes(code)) {
        throw new InvalidToken();
      }
      throw new AuthUnavailable();
    }
  }
}
