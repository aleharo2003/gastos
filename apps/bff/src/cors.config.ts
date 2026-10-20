import type { INestApplication } from '@nestjs/common';

export function readFrontendOrigin(
  value: string | undefined,
): string | undefined {
  if (value === undefined) {
    return undefined;
  }

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(
      'FRONTEND_ORIGIN debe ser un origen HTTP(S), sin ruta ni barra final.',
    );
  }

  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username !== '' ||
    url.password !== '' ||
    value !== url.origin
  ) {
    throw new Error(
      'FRONTEND_ORIGIN debe ser un origen HTTP(S), sin ruta ni barra final.',
    );
  }

  return value;
}

export function configureCors(app: INestApplication): void {
  const origin = readFrontendOrigin(process.env.FRONTEND_ORIGIN);
  if (origin === undefined) {
    return;
  }

  app.enableCors({
    origin: [origin],
    methods: ['GET', 'HEAD'],
    credentials: false,
  });
}
