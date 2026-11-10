import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';

describe('Comprobantes HTTP',()=>{
  let app:INestApplication,fetchMock:ReturnType<typeof vi.fn>;
  const space=randomUUID(),account=randomUUID(),expense=randomUUID(),id=randomUUID();
  const path=`/api/spaces/${space}/accounts/${account}/expenses/${expense}/receipts`;
  const row={id,nombre:'ticket.pdf',mime:'application/pdf',bytes:14};
  beforeEach(async()=>{
    const module=await Test.createTestingModule({imports:[AppModule]}).overrideProvider(AuthService).useValue({verifyIdentity:vi.fn().mockResolvedValue(randomUUID())}).compile();
    app=module.createNestApplication();await app.init();
    vi.stubEnv('API_BASE_URL','https://api.example');fetchMock=vi.fn().mockResolvedValue(new Response(JSON.stringify(row)));vi.stubGlobal('fetch',fetchMock);
  });
  afterEach(async()=>{await app.close();vi.unstubAllGlobals();vi.unstubAllEnvs();});
  it('rechaza descarga y subida sin token',async()=>{
    await request(app.getHttpServer()).get(path+'/'+id+'/file').expect(401);
    await request(app.getHttpServer()).post(path+'/'+id).set('Content-Type','application/octet-stream').send(Buffer.from('x')).expect(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('reenvia bytes y nombre sin clave de Storage',async()=>{
    const data=Buffer.from('%PDF-1.7\n%%EOF');
    await request(app.getHttpServer()).post(path+'/'+id).set('Authorization','Bearer token').set('Content-Type','application/octet-stream').set('X-Receipt-Name','ticket.pdf').send(data).expect(201).expect(row);
    const [url,options]=fetchMock.mock.calls[0];expect(String(url)).toContain(`/receipts/${id}`);expect(Buffer.from(options.body)).toEqual(data);
    expect(options.headers.Authorization).toBe('Bearer token');expect(options.headers.apikey).toBeUndefined();
  });
  it('limita el cuerpo antes de reenviar',async()=>{
    await request(app.getHttpServer()).post(path+'/'+id).set('Authorization','Bearer token').set('Content-Type','application/octet-stream').set('X-Receipt-Name','ticket.pdf').send(Buffer.alloc(5*1024*1024+1)).expect(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('descarga sin cache ni URL publica',async()=>{
    fetchMock.mockResolvedValue(new Response('%PDF-1.7\n%%EOF',{headers:{'Content-Type':'application/pdf'}}));
    await request(app.getHttpServer()).get(path+'/'+id+'/file').set('Authorization','Bearer token').expect(200).expect('Cache-Control','no-store').expect('X-Content-Type-Options','nosniff').expect('Content-Disposition',`attachment; filename="comprobante-${id}.pdf"`);
  });
  it('conserva denegacion sin filtrar detalles del backend',async()=>{
    fetchMock.mockResolvedValue(new Response('secret',{status:403}));
    const result=await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(403);expect(result.text).not.toContain('secret');
  });
});
