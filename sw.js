// SY service worker: app shell cached for offline use; data always fetched fresh (falls back to last copy offline).
const SHELL = "sy-shell-v8";
const FILES = ["./", "index.html", "manifest.webmanifest", "vendor/chart.umd.min.js",
  "icons/icon-192.png", "icons/icon-512.png", "icons/favicon-48.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES))); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL && k !== "sy-data").map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const isData = url.pathname.endsWith(".json");
  const isPage = e.request.mode === "navigate" || url.pathname.endsWith(".html") || url.pathname.endsWith("/");
  if (isData || isPage) {   // network first, so updates show immediately
    e.respondWith(fetch(e.request,{cache:"no-store"}).then(r => { const copy = r.clone(); caches.open(isData ? "sy-data" : SHELL).then(c => c.put(isData ? url.pathname : e.request, copy)); return r; })
      .catch(() => caches.match(isData ? url.pathname : e.request).then(m => m || caches.match("index.html"))));
  } else {
    e.respondWith(caches.match(e.request).then(m => m || fetch(e.request)));
  }
});
