// sw.js — Service Worker de SoundPass Staff PWA
// Permite que la app funcione offline y se instale en el dispositivo

const CACHE = "soundpass-v2";
const ASSETS = ["/staff", "/static/icons/icon-192.png"];

// Instalar: guarda los assets en caché
self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(ASSETS))
  );
  self.skipWaiting();
});

// Activar: limpia cachés viejas
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: red primero, caché como respaldo
self.addEventListener("fetch", e => {
  // Las llamadas a la API siempre van a la red
  if (e.request.url.includes("/api/")) return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});