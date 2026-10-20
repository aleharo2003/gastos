import { access, writeFile } from 'node:fs/promises';

const output = new URL('../../apps/web/dist/gastos-web/browser/', import.meta.url);
await access(new URL('index.html', output));

const commit = process.env.RENDER_GIT_COMMIT ?? process.env.GITHUB_SHA ?? null;
await writeFile(new URL('version.json', output), `${JSON.stringify({ commit })}\n`, 'utf8');
