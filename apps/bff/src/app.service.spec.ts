import { BadGatewayException } from '@nestjs/common';
import { AppService } from './app.service.js';

describe('AppService consultando FastAPI', () => {
  beforeEach(() => {
    vi.stubEnv('API_BASE_URL', 'https://api.example.test');
    vi.stubEnv('API_TIMEOUT_MS', undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('devuelve el mensaje de una respuesta válida', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ message: 'Hola desde FastAPI' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(new AppService().getApiMessage()).resolves.toEqual({ message: 'Hola desde FastAPI' });
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.test', {
      headers: { Accept: 'application/json' },
      signal: expect.any(AbortSignal),
    });
  });

  it.each([
    ['HTTP 503', () => new Response('Unavailable', { status: 503 })],
    ['HTML en lugar de JSON', () => new Response('<html>Despertando</html>')],
    ['mensaje de otro tipo', () => Response.json({ message: 123 })],
    ['mensaje ausente', () => Response.json({ status: 'ok' })],
    ['JSON nulo', () => Response.json(null)],
  ])('convierte %s en un error controlado', async (_name, response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response()));

    await expect(new AppService().getApiMessage()).rejects.toThrow(BadGatewayException);
  });

  it('convierte un fallo de conexión en un error controlado', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')));

    await expect(new AppService().getApiMessage()).rejects.toThrow('No se pudo consultar FastAPI');
  });

  it('aborta una consulta que supera el tiempo configurado', async () => {
    vi.stubEnv('API_TIMEOUT_MS', '10');
    vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        options.signal!.addEventListener('abort', () => reject(options.signal!.reason), { once: true });
      });
    }));

    await expect(new AppService().getApiMessage()).rejects.toThrow(BadGatewayException);
  });

  it.each(['', 'abc', '0', '-1', '1.5', '2147483648', '4294967296'])('rechaza API_TIMEOUT_MS=%j al iniciar', (value) => {
    vi.stubEnv('API_TIMEOUT_MS', value);
    expect(() => new AppService()).toThrow('API_TIMEOUT_MS debe ser un entero');
  });
});
