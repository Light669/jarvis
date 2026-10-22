// Créapilot : garde l'application en mémoire pour l'ouvrir même avec une connexion faible.
// Les données (Supabase) ne passent jamais par ce cache.
const CACHE = 'creapilot-v1';
const SHELL = ['app.html', 'config.js', 'manifest.webmanifest', 'assets/icon-192.png', 'assets/icon-512.png', 'assets/apple-touch-icon.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.hostname.endsWith('supabase.co') || url.hostname.endsWith('supabase.in')) return;
  const sameOrigin = url.origin === self.location.origin;
  const staticHost = ['fonts.googleapis.com', 'fonts.gstatic.com', 'cdn.jsdelivr.net'].includes(url.hostname);
  if (!sameOrigin && !staticHost) return;

  const put = (res) => { if (res && (res.ok || res.type === 'opaque')) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); } return res; };

  // Pages et scripts de l'application : réseau d'abord (pour recevoir les mises à jour), mémoire si hors ligne
  if (req.mode === 'navigate' || (sameOrigin && /\.(html|js|webmanifest)$/.test(url.pathname))) {
    e.respondWith(fetch(req).then(put).catch(() => caches.match(req, { ignoreSearch: true })));
    return;
  }
  // Polices, images et bibliothèque : mémoire d'abord
  e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then(put)));
});
