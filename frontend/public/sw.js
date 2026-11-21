// RegWatch service worker: lets the app install on Android and open fast.
// Pages and data always come fresh from the network (never a stale screen); only the app's own
// static files are kept, and the last page is shown with a plain note if the phone is offline.
const CACHE = "regwatch-static-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/icons/icon-192.png", "/icons/icon-512.png"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // the API and PDFs: straight to the network
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    e.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return res;
          }),
      ),
    );
    return;
  }
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).catch(
        () =>
          new Response(
            "<!doctype html><meta name=viewport content='width=device-width'><body style='font-family:sans-serif;padding:24px;background:#0e1311;color:#e6ece9'><h2>You are offline</h2><p>RegWatch needs the internet to show the latest circulars. It opens again as soon as you are back online.</p></body>",
            { headers: { "Content-Type": "text/html" } },
          ),
      ),
    );
  }
});
