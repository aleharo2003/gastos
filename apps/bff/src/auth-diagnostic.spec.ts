import { Logger } from '@nestjs/common';
import { AuthService } from './auth.service.js';

describe('Diagnostico seguro de FastAPI', () => {
  let service: AuthService;
  let log: ReturnType<typeof vi.spyOn>;
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    vi.stubEnv('API_BASE_URL', 'https://api.example');
    vi.stubEnv('API_TIMEOUT_MS', '120000');
    service = new AuthService();
    vi.spyOn(service, 'verifyIdentity').mockResolvedValue('user-private');
    log = vi.spyOn(Logger.prototype, 'error').mockImplementation(() => {});
    fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
  async function failure(phase: string) {
    await expect(service.getMe('TOKEN_PRIVATE')).rejects.toMatchObject({ status:502 });
    expect(log).toHaveBeenCalledTimes(1);
    const text = String(log.mock.calls[0][0]);
    expect(text).toContain('fase=' + phase);
    for (const secret of ['TOKEN_PRIVATE','BODY_PRIVATE','user-private','URL_PRIVATE','MESSAGE_PRIVATE']) {
      expect(text).not.toContain(secret);
    }
    return text;
  }
  it('identifica URL invalida sin publicarla', async () => {
    vi.stubEnv('API_BASE_URL','https://user:URL_PRIVATE@api.example');
    await failure('CONFIG_URL'); expect(fetchMock).not.toHaveBeenCalled();
  });
  it('identifica tiempo con caracteres inesperados', async () => {
    vi.stubEnv('API_TIMEOUT_MS','120000 ');
    await failure('CONFIG_TIEMPO');
  });
  it('clasifica DNS usando solo codigo permitido', async () => {
    fetchMock.mockRejectedValue(Object.assign(new Error('MESSAGE_PRIVATE TOKEN_PRIVATE'), { cause:{code:'ENOTFOUND'} }));
    expect(await failure('CONEXION')).toContain('causa=ENOTFOUND');
  });
  it('no registra un codigo de error arbitrario', async () => {
    fetchMock.mockRejectedValue({cause:{code:'MESSAGE_PRIVATE'}});
    expect(await failure('CONEXION')).toContain('causa=NO_CLASIFICADO');
  });
  it('identifica HTTP 500 sin publicar cuerpo', async () => {
    fetchMock.mockResolvedValue(new Response('BODY_PRIVATE',{status:500}));
    expect(await failure('RESPUESTA_HTTP')).toContain('http=500');
  });
  it('identifica JSON incorrecto', async () => {
    fetchMock.mockResolvedValue(new Response('BODY_PRIVATE',{status:200}));
    await failure('RESPUESTA_JSON');
  });
  it('identifica respuesta de otra identidad sin exponerla', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({usuario_id:'BODY_PRIVATE'})));
    await failure('IDENTIDAD');
  });
  it('conserva errores esperados de autenticacion', async () => {
    fetchMock.mockResolvedValue(new Response('BODY_PRIVATE',{status:401}));
    await expect(service.getMe('TOKEN_PRIVATE')).rejects.toMatchObject({status:401});
    expect(log).not.toHaveBeenCalled();
  });
  it('conserva una verificacion exitosa', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({usuario_id:'user-private'})));
    await expect(service.getMe('TOKEN_PRIVATE')).resolves.toEqual({usuario_id:'user-private'});
    expect(log).not.toHaveBeenCalled();
  });
});
