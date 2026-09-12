var CACHE = "kitchenops-v1";
var ASSETS = ["/static/app.css", "/static/app.js", "/static/manifest.json"];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) {
    return cache.addAll(ASSETS);
  }));
});

self.addEventListener("fetch", function (event) {
  if (event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(function () {
    return caches.match(event.request);
  }));
});
