import { exportJWK, generateKeyPair, SignJWT } from 'jose';
import type { JWTPayload } from 'jose';
import { randomUUID } from 'node:crypto';
import { AuthUnavailable, InvalidToken, TokenVerifier } from './token-verifier.js';

const project = 'abcdefghijklmnopqrst';
const issuer = `https://${project}.supabase.co/auth/v1`;

describe('TokenVerifier', () => {
  let pair: Awaited<ReturnType<typeof generateKeyPair>>;
  let claims: JWTPayload;
  let jwk: Record<string, unknown>;
  let verifier: TokenVerifier;
  let fetchMock: ReturnType<typeof vi.fn>;
  const token = (payload = claims, extra: Record<string, unknown> = {}) =>
    new SignJWT(payload).setProtectedHeader({ alg: 'ES256', kid: 'one', ...extra }).sign(pair.privateKey);

  beforeEach(async () => {
    pair = await generateKeyPair('ES256');
    jwk = { ...await exportJWK(pair.publicKey), kid: 'one', alg: 'ES256', use: 'sig' };
    const now = Math.floor(Date.now() / 1000);
    claims = { iss: issuer, aud: 'authenticated', sub: randomUUID(), session_id: randomUUID(),
      exp: now + 300, iat: now - 5, role: 'authenticated', is_anonymous: false };
    fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ keys: [jwk] })));
    vi.stubGlobal('fetch', fetchMock);
    verifier = new TokenVerifier(project);
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  it('verifica firma e identidad y comparte cache concurrente', async () => {
    const signed = await token();
    expect(await Promise.all([verifier.verify(signed), verifier.verify(signed)])).toEqual([claims.sub, claims.sub]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each(['iss', 'aud', 'exp', 'iat', 'sub', 'session_id', 'role', 'is_anonymous'])('exige %s', async (field) => {
    const payload = { ...claims }; delete payload[field];
    await expect(verifier.verify(await token(payload))).rejects.toBeInstanceOf(InvalidToken);
  });

  it.each([
    ['iss', 'https://other.supabase.co/auth/v1'], ['aud', ['authenticated']],
    ['role', 'anon'], ['role', 'service_role'], ['is_anonymous', true], ['is_anonymous', 'false'],
    ['sub', 'invalid'], ['session_id', 'invalid'], ['sub', '00000000-0000-0000-0000-000000000000'],
    ['exp', 1], ['exp', '123'], ['iat', true],
  ])('rechaza claim %s con valor incorrecto', async (name, value) => {
    await expect(verifier.verify(await token({ ...claims, [name as string]: value }))).rejects.toBeInstanceOf(InvalidToken);
  });

  it('rechaza nbf e iat futuros', async () => {
    for (const field of ['nbf', 'iat']) {
      await expect(verifier.verify(await token({ ...claims, [field]: Math.floor(Date.now() / 1000) + 120 }))).rejects.toBeInstanceOf(InvalidToken);
    }
  });

  it('rechaza firma de otra clave', async () => {
    const other = await generateKeyPair('ES256');
    const signed = await new SignJWT(claims).setProtectedHeader({ alg: 'ES256', kid: 'one' }).sign(other.privateKey);
    await expect(verifier.verify(signed)).rejects.toBeInstanceOf(InvalidToken);
  });

  it('rechaza HS256 y token sin firma sin descargar JWKS', async () => {
    const signed = await new SignJWT(claims).setProtectedHeader({ alg: 'HS256' }).sign(new Uint8Array(64));
    for (const value of [signed, 'eyJhbGciOiJub25lIn0.e30.', 'bad', 'a'.repeat(16385)]) {
      await expect(verifier.verify(value)).rejects.toBeInstanceOf(InvalidToken);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rechaza URL de claves elegida por el token', async () => {
    await expect(verifier.verify(await token(claims, { jku: 'https://attacker.example' }))).rejects.toBeInstanceOf(InvalidToken);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('limita refrescos por kid desconocido', async () => {
    await verifier.verify(await token());
    for (const kid of ['x', 'y']) await expect(verifier.verify(await token(claims, { kid }))).rejects.toBeInstanceOf(InvalidToken);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('acepta una clave rotada despues del cooldown y elimina la anterior', async () => {
    await verifier.verify(await token());
    const clock = Date.now(); vi.spyOn(Date, 'now').mockReturnValue(clock + 31000);
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ keys: [{ ...jwk, kid: 'next' }] })));
    expect(await verifier.verify(await token(claims, { kid: 'next' }))).toBe(claims.sub);
    await expect(verifier.verify(await token())).rejects.toBeInstanceOf(InvalidToken);
    vi.restoreAllMocks();
  });

  it('limita reintentos durante caida de JWKS', async () => {
    fetchMock.mockRejectedValue(new Error('sensitive driver details'));
    for (let i = 0; i < 2; i++) await expect(verifier.verify(await token())).rejects.toBeInstanceOf(AuthUnavailable);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('no usa claves vencidas si JWKS no esta disponible', async () => {
    await verifier.verify(await token());
    const clock = Date.now(); vi.spyOn(Date, 'now').mockReturnValue(clock + 301000);
    fetchMock.mockRejectedValue(new Error('outage'));
    await expect(verifier.verify(await token())).rejects.toBeInstanceOf(AuthUnavailable);
  });

  it('rechaza JWKS enorme', async () => {
    fetchMock.mockResolvedValue(new Response('x'.repeat(65537)));
    await expect(verifier.verify(await token())).rejects.toBeInstanceOf(AuthUnavailable);
  });

  it('rechaza configuracion de proyecto arbitraria', () => {
    expect(() => new TokenVerifier('https://attacker.example')).toThrow(AuthUnavailable);
  });
});
