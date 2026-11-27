const cachePrefix = 'piggo-offline-';
const cacheName = cachePrefix + 'v1';
const offlinePage = new URL('offline.html', self.registration.scope).href;

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(cacheName).then((cache) => cache.add(offlinePage)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((names) => Promise.all(
    names.filter((name) => name.startsWith(cachePrefix) && name !== cacheName)
      .map((name) => caches.delete(name)),
  )));
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || request.mode !== 'navigate'
    || url.origin !== self.location.origin
    || url.pathname !== new URL(self.registration.scope).pathname) return;

  event.respondWith(fetch(request).catch(async () => {
    const cache = await caches.open(cacheName);
    return (await cache.match(offlinePage)) ?? Response.error();
  }));
});

self.addEventListener('push', (event) => {
  let payload;
  try { payload = event.data?.json(); } catch { return; }
  if (payload?.type !== 'due') return;
  event.waitUntil(self.registration.showNotification('Tenés vencimientos en Piggo', {
    body: 'Abrí Hoy para revisar tus próximos pagos.',
    tag: 'piggo-due',
  }));
});

async function openToday() {
  const target = new URL(self.registration.scope);
  target.searchParams.set('vista', 'hoy');
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  const existing = windows.find(client => {
    const url = new URL(client.url);
    return url.origin === target.origin && url.pathname === target.pathname;
  });
  if (existing) {
    try {
      const navigated = await existing.navigate(target.href);
      if (navigated) return navigated.focus();
    } catch {
      // El navegador puede cerrar la ventana mientras se procesa el toque.
    }
  }
  return self.clients.openWindow(target.href);
}

self.addEventListener('notificationclick', (event) => {
  if (event.notification.tag !== 'piggo-due') return;
  event.notification.close();
  event.waitUntil(openToday());
});
