import { readFrontendOrigin } from './cors.config.js';

describe('FRONTEND_ORIGIN', () => {
  it('puede omitirse cuando se usa el proxy local', () => {
    expect(readFrontendOrigin(undefined)).toBeUndefined();
  });

  it.each(['https://web.example.com', 'http://localhost:4200'])(
    'acepta el origen completo %s',
    (origin) => {
      expect(readFrontendOrigin(origin)).toBe(origin);
    },
  );

  it.each([
    '',
    '*',
    'null',
    'ftp://web.example.com',
    'https://web.example.com/',
    'https://web.example.com/cuentas',
    'https://user:password@web.example.com',
    'https://web.example.com?debug=true',
    'https://web.example.com#cuentas',
  ])('rechaza el valor inválido %s', (origin) => {
    expect(() => readFrontendOrigin(origin)).toThrow('FRONTEND_ORIGIN');
  });
});
