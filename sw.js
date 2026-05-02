/* Where Bazinc — Service Worker v3 */
const CACHE = 'wherebazinc-v3';
const PRECACHE = ['/', '/login', '/static/icons/icon-192.png', '/static/icons/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE).catch(()=>{})));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/') || e.request.url.includes('/stream')) return;
  // Network first, cache fallback
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});

/* ── PUSH (background) ─────────────────────────────────────────── */
self.addEventListener('push', e => {
  let data = { title: 'Where Bazinc Alert', body: 'New notification', severity: 'medium' };
  try { if (e.data) data = { ...data, ...e.data.json() }; } catch(err) {}

  const icons = { high: '🚨', medium: '⚠️', low: 'ℹ️' };
  const colors = { high: '#ef4444', medium: '#f59e0b', low: '#22c55e' };

  e.waitUntil(
    self.registration.showNotification(data.title, {
      body:              data.body,
      icon:              '/static/icons/icon-192.png',
      badge:             '/static/icons/icon-192.png',
      vibrate:           data.severity === 'high' ? [300,100,300,100,300] : [200,100,200],
      tag:               'wherebazinc-alert',
      renotify:          true,
      requireInteraction: data.severity === 'high',
      data:              { url: data.url || '/dashboard', severity: data.severity },
      actions: [
        { action: 'view', title: '📍 See on map' },
        { action: 'dismiss', title: 'Dismiss' }
      ]
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  if (e.action === 'dismiss') return;
  const target = (e.notification.data && e.notification.data.url) || '/dashboard';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return clients.openWindow(target);
    })
  );
});
