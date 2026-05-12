// Minimal service worker. Its presence is what lets Chrome show the
// "Install app" prompt; we deliberately do NOT cache /api responses
// (the app is online-only — alerts and rep data must be live).
//
// Strategy:
// - Pre-cache the app shell on install so a flaky connection still loads
//   the React bundle and lets the offline error states render.
// - Network-first for everything else; fall back to cache for the shell.

const CACHE = "fuu-shell-v3";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icon-192-v2.png", "/icon-512-v2.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // Never cache API responses — they're live data and stale entries would
  // mislead the user. Let the network handle them; the app's existing
  // try/catch falls back to embedded sample data on failure.
  if (url.pathname.startsWith("/api/")) return;

  event.respondWith(
    fetch(request)
      .then((res) => {
        // Only cache successful same-origin GETs of the shell-ish paths.
        if (res.ok && url.origin === self.location.origin) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
        }
        return res;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/index.html")))
  );
});
