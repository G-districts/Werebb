/* Where Bazinc SW — caching only. OneSignalSDKWorker.js handles ALL push. */
const CACHE = 'wherebazinc-v4';
const PRECACHE = ['/', '/login', '/dashboard', '/static/icons/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/')) return;
  if (e.request.url.includes('onesignal')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
/* Push is handled ENTIRELY by OneSignalSDKWorker.js — do NOT add push handlers here */
