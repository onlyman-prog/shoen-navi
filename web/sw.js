// オフラインでも開けるようにするキャッシュ (画面ファイルは更新優先、画像はキャッシュ優先)
const CACHE = "shoen-navi-v1";
const CORE = ["./", "index.html", "app.js", "style.css", "pwa.js", "data.json", "manifest.webmanifest", "icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  const isImg = /\.(png|jpe?g|webp)$/i.test(u.pathname) || u.hostname.includes("googleusercontent");
  if (isImg) {
    // 画像: キャッシュ優先
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
      if (r.ok || r.type === "opaque") { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, cp)); }
      return r;
    })));
    return;
  }
  if (u.origin !== location.origin) return;
  // 画面・データ: ネット優先、失敗したらキャッシュ
  const key = u.pathname.endsWith("data.json") ? "data.json" : e.request;
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(key, cp)); }
    return r;
  }).catch(() => caches.match(key).then((hit) => hit || caches.match("index.html"))));
});
