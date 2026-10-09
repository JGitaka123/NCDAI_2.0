// NCDAI service worker. Network-first so clinicians always get the current
// release when online; cached copies are only an offline fallback. Clinical API
// traffic (/api/) is never intercepted or cached.
const CACHE = 'ncdai-shell-v3'
const OFFLINE_SHELL = ['/', '/mobile/', '/mobile/engine.js', '/mobile/evidence.js', '/mobile/app.js', '/mobile/register-sw.js', '/mobile/ncdai-logo.png',
  '/mobile/manifest.webmanifest', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png', '/brand/ncdai-logo.png']

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(OFFLINE_SHELL)).then(() => self.skipWaiting()))
})
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('ncdai-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()))
})
self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  // Cache only application resources, never arbitrary same-origin responses.
  if (url.search || !(OFFLINE_SHELL.includes(url.pathname) || url.pathname === '/consultant' || /^\/(assets|icons|brand)\/[A-Za-z0-9._/-]+$/.test(url.pathname))) return
  event.respondWith(fetch(request).then(response => {
    if (response.ok && response.type === 'basic') {
      const copy = response.clone()
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {}))
    }
    return response
  }).catch(async () => {
    const cache = await caches.open(CACHE)
    const cached = await cache.match(request)
    if (cached) return cached
    if (request.mode === 'navigate') return (await cache.match(url.pathname.startsWith('/mobile') ? '/mobile/' : '/')) || Response.error()
    return Response.error()
  }))
})
