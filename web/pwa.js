// iPhone / ブラウザ版 (PWA) 用: パソコン版の Python API の代わり。
// データは data.json (GitHub Actions が毎日更新) から読み、設定と試合記録は端末内 (localStorage) に保存する。
"use strict";
(() => {
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  async function fetchData() {
    const r = await fetch("data.json?t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }
  const settings = () => ({ on_top: false, pool: [], vision: false, ocr: false, auto: false, game: false, ...ls.get("settings", {}) });
  const none = async () => null;
  const api = {
    async get_data() {
      try {
        const d = await fetchData();
        ls.set("lastFetched", d.fetched || "");
        return d;
      } catch {
        // オフライン: Service Worker のキャッシュから
        const r = await caches.match("data.json").catch(() => null);
        return r ? r.json() : null;
      }
    },
    async get_settings() { return settings(); },
    async set_pool(names) { ls.set("settings", { ...ls.get("settings", {}), pool: names.slice(0, 12) }); },
    async set_on_top() {},
    async open_url(url) { if (String(url).startsWith("https://")) window.open(url, "_blank", "noopener"); },
    async refresh() {
      window.onProgress && window.onProgress(1, 2);
      try { await fetchData(); window.onUpdated && window.onUpdated(true); }
      catch (e) { window.onUpdated && window.onUpdated(false, "通信できません"); }
      return true;
    },
    async get_records() { return ls.get("records", []); },
    async add_record(rec) {
      const recs = ls.get("records", []);
      rec.ts = Math.floor(Date.now() / 1000);
      recs.push(rec);
      ls.set("records", recs);
      return { records: recs, learned: 0 };
    },
    async delete_record(ts) {
      const recs = ls.get("records", []).filter((r) => r.ts !== ts);
      ls.set("records", recs);
      return recs;
    },
    // ゲーム画面の読み取り系はパソコン版のみ
    read_now: none, capture_preview: none, list_shots: async () => [], use_shot: none, save_slots: none,
    set_auto_read: none, set_auto_shot: none, set_game_icons: none, icon_stats: async () => ({ have: 0, total: 0 }),
  };
  window.pywebview = { api };
  document.documentElement.classList.add("pwa");

  // ホバーが無いので「長押し」で title (出典・理由) を表示する
  let timer = null, shown = false, sx = 0, sy = 0;
  const tip = () => document.getElementById("pwatip") || Object.assign(document.body.appendChild(document.createElement("div")), { id: "pwatip" });
  document.addEventListener("touchstart", (e) => {
    const el = e.target.closest("[title]");
    shown = false;
    if (!el || !el.title) return;
    sx = e.touches[0].clientX; sy = e.touches[0].clientY;
    timer = setTimeout(() => {
      const t = tip();
      t.textContent = el.title;
      t.classList.add("on");
      shown = true;
    }, 450);
  }, { passive: true });
  document.addEventListener("touchmove", (e) => {
    if (timer && Math.hypot(e.touches[0].clientX - sx, e.touches[0].clientY - sy) > 10) { clearTimeout(timer); timer = null; }
  }, { passive: true });
  document.addEventListener("touchend", (e) => {
    clearTimeout(timer); timer = null;
    if (shown) { e.preventDefault(); setTimeout(() => tip().classList.remove("on"), 2500); }
  });
  document.addEventListener("contextmenu", (e) => { if (e.target.closest("[title]")) e.preventDefault(); });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();
