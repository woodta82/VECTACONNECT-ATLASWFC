// Replacement for the VECTA 2.9.0 app-shell service worker.
// Browsers that registered the old worker fetch this script on their next
// visit; it deletes every ATLAS cache, unregisters itself and reloads open
// tabs. Nothing authenticated is ever cached by a service worker again.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k.startsWith("atlas")).map((k) => caches.delete(k)));
      await self.registration.unregister();
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((c) => c.navigate(c.url));
    })()
  );
});
