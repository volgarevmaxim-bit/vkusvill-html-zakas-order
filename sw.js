// Service worker for VkusVill Selector — caches app shell for offline use
var CACHE = 'vkusvill-v5';
var FILES = ['/select/', '/select/index.html', '/select/manifest.json'];

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
        .map(function(k) { return caches.delete(k); }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  // Network-first for API calls (MCP), cache-first for everything else
  var url = new URL(e.request.url);
  if (url.hostname === 'mcp001.vkusvill.ru') {
    // API: network only, don't cache
    return;
  }
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      return cached || fetch(e.request).then(function(resp) {
        // Cache successful responses for next time
        if (resp.ok && resp.type === 'basic') {
          var clone = resp.clone();
          caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
        }
        return resp;
      });
    })
  );
});
