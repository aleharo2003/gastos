import { BadGatewayException, BadRequestException, Controller, Get, HttpException, Param, Req, Res, StreamableFile, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedBytes } from './token-verifier.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_ARCHIVE_BYTES = 25 * 1024 * 1024;
const ZIP_TYPE = 'application/zip';

@Controller('api/spaces/:space/export')
export class SpaceExportController {
  constructor(private readonly auth: AuthService) {}

  @Get()
  async download(@Param('space') space: string, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const parts = request.headers.authorization?.trim().split(/\s+/) ?? [];
    const count = request.rawHeaders.filter((name, index) => index % 2 === 0 && name.toLowerCase() === 'authorization').length;
    try {
      if (count !== 1 || parts.length !== 2 || parts[0].toLowerCase() !== 'bearer') throw new UnauthorizedException();
      await this.auth.verifyIdentity(parts[1]);
    } catch (error) {
      if (error instanceof UnauthorizedException) response.setHeader('WWW-Authenticate', 'Bearer');
      throw error;
    }
    if (!UUID.test(space)) throw new BadRequestException('Espacio inválido');
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const upstream = await fetch(new URL('/spaces/' + space.toLowerCase() + '/export', base), {
        headers: { Accept: ZIP_TYPE, Authorization: 'Bearer ' + parts[1] },
        redirect: 'error', signal: AbortSignal.timeout(60_000),
      });
      if ([401, 403, 413, 503].includes(upstream.status)) {
        await upstream.body?.cancel().catch(() => undefined);
        throw new HttpException('No se pudo completar la exportación', upstream.status);
      }
      if (!upstream.ok || upstream.headers.get('content-type') !== ZIP_TYPE) {
        await upstream.body?.cancel().catch(() => undefined);
        throw new Error();
      }
      const archive = await boundedBytes(upstream, MAX_ARCHIVE_BYTES);
      if (archive.length < 22 || archive.readUInt32LE(0) !== 0x04034b50) throw new Error();
      response.setHeader('X-Content-Type-Options', 'nosniff');
      return new StreamableFile(archive, { type: ZIP_TYPE, disposition: 'attachment; filename="piggo-datos.zip"' });
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException('No pudimos preparar el archivo');
    }
  }
}
