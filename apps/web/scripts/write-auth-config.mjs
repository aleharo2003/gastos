import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const key = process.env.SUPABASE_PUBLISHABLE_KEY?.trim() ?? '';
const projectRef = process.env.SUPABASE_PROJECT_REF?.trim() ?? 'cyxhyfbiacfayixbmotq';
if (key && (!key.startsWith('sb_publishable_') || !/^[a-z0-9]{20}$/.test(projectRef))) {
  throw new Error('Configurar una Publishable key y un project ref validos. No usar secret keys.');
}
const destination = process.argv.includes('--local') ? 'public' : 'dist/gastos-web/browser';
await mkdir(resolve(destination), { recursive: true });
await writeFile(resolve(destination, 'auth-config.json'), JSON.stringify({ projectRef, publishableKey: key }) + '\n');
console.log(key ? 'Configuracion publica de Auth generada.' : 'Auth sin configurar: login deshabilitado.');
