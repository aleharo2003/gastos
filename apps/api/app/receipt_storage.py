"""Objetos privados. La autorización de negocio se verifica antes de llamar aquí."""
import os
import re
import httpx
from fastapi import HTTPException

BUCKET = 'gastos-comprobantes'
MAX_BYTES = 5 * 1024 * 1024


class ReceiptStorage:
    def __init__(self):
        ref = os.getenv('AUTH_SUPABASE_PROJECT_REF', '')
        key = os.getenv('APP_STORAGE_SERVICE_KEY', '')
        if not re.fullmatch(r'[a-z0-9]{20}', ref) or not key:
            raise HTTPException(503, 'Comprobantes no configurados')
        self.base = f'https://{ref}.supabase.co/storage/v1'
        self.headers = {'apikey': key}
        if not key.startswith('sb_secret_'):
            self.headers['Authorization'] = 'Bearer ' + key

    def client(self):
        return httpx.Client(headers=self.headers, timeout=30, follow_redirects=False)

    def private(self, client):
        response = client.get(f'{self.base}/bucket/{BUCKET}')
        metadata=response.json() if response.status_code==200 else None
        if not isinstance(metadata,dict) or metadata.get('public') is not False:
            raise ValueError('Bucket ausente o no privado')

    def put(self, path, data, mime):
        try:
            with self.client() as client:
                self.private(client)
                # Ruta incluye hash del contenido: el reintento sólo repone los mismos bytes.
                response = client.post(f'{self.base}/object/{BUCKET}/{path}', content=data,
                    headers={'Content-Type': mime, 'x-upsert': 'true', 'Cache-Control': 'no-store'})
                if response.status_code not in (200, 201):
                    raise ValueError('Storage rechazo subida')
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(503, 'No se pudo guardar el comprobante; reintenta') from None

    def get(self, path):
        try:
            with self.client() as client:
                self.private(client)
                with client.stream('GET', f'{self.base}/object/authenticated/{BUCKET}/{path}') as response:
                    if response.status_code != 200:
                        raise ValueError('Objeto no disponible')
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise ValueError('Objeto excede limite')
                    return bytes(data)
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(503, 'No se pudo recuperar el comprobante') from None
