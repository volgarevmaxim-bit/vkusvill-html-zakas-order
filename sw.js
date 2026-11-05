// Service worker for VkusVill Selector — caches app shell for offline use
var CACHE = 'vkusvill-v11';
var FILES = ['./', './index.html', './manifest.json'];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(cache) {
      return cache.addAll(FILES);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(keys.filter(function(k) { return k !== CACHE; })
        .map(function(c) { return caches.delete(k); }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  // MCP и локальный прокси — только сеть, без кэша; остальное — cache-first
  var url = new URL(e.request.url);
  if (url.hostname === 'mcp.vkusvill.ru' ||
      url.hostname === 'mcp001.vkusvill.ru' ||
      url.hostname === '127.0.0.1' ||
      url.hostname === 'localhost') {
    return;
  }
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      return cached || fetch(e.request).then(function(resp) {
        if (resp.ok && resp.type === 'basic') {
          var clone = resp.clone();
          caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
        }
        return resp;
      });
    })
  );
});
