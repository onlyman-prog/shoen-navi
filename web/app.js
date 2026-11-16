"use strict";
const $ = (s) => document.querySelector(s);
const TIERS = ["S", "A", "B", "C", "D"];
const RANK = { S: 0, A: 1, B: 2, C: 3, D: 4, "?": 5 };
const W = { S: 1.0, A: 0.85, B: 0.7, C: 0.55, D: 0.4, "?": 0.5 };

let D = null;            // データ
let tab = "s";
let tierOn = new Set();  // ティア絞り込み
let banned = new Set();  // BAN予測で選んだサバイバー
let history = [];        // 詳細画面の戻り先

const api = () => window.pywebview && window.pywebview.api;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// googleusercontent の画像はサイズ指定で軽量化
const sz = (url, s) => (url && url.includes("googleusercontent") ? `${url}=s${s}` : url || "");
const short = (n) => n.replace(/[「」]/g, "");

/* ---------- 起動 / データ ---------- */
async function loadData() {
  try {
    D = api() ? await api().get_data() : await (await fetch("../data/cache.json")).json();
  } catch { D = null; }
  // ゲーム画面から集めた画像があれば差し替え
  if (D) for (const c of Object.values(D.chars)) if (c.gameImg) { c.webImg = c.img; c.img = c.gameImg; }
  render();
  status();
}

function status(msg) {
  const el = $("#status");
  if (msg) return (el.textContent = msg);
  if (!D) return (el.textContent = "データなし — 取得中…");
  el.innerHTML = `ティア ${esc(D.source.tierUpdated.s)} ・ 取得 ${esc(D.fetched)} ・ <u data-url="${esc(D.source.url)}">${esc(D.source.name)}</u>${D.wiki ? ` ・ <u data-url="${esc(D.wiki.url)}">wiki ${esc(D.wiki.updated)}</u>` : ""}`;
}

window.onProgress = (d, t) => {
  $("#bar i").style.width = (100 * d) / t + "%";
  $("#reload").classList.add("spin");
  status(`最新情報を取得中… ${d}/${t}`);
};
window.onUpdated = async (ok, err) => {
  $("#reload").classList.remove("spin");
  $("#bar i").style.width = "0";
  if (!ok) return status("取得失敗（前回データを表示中）: " + (err || ""));
  const cur = $("#detail").hidden ? null : history[history.length - 1];
  await loadData();
  if (cur) showDetail(cur, true);
};

let started = false;
async function init() {
  if (started) return;
  started = true;
  if (api()) {
    try {
      const st = await api().get_settings();
      $("#pin").classList.toggle("on", !!st.on_top);
      pool = new Set(st.pool || []);
    } catch {}
    await loadRecords();
  }
  loadData();
}
// pywebviewready がスクリプト読込前に発火する場合があるので両対応
window.addEventListener("pywebviewready", init);
(function wait(n) {
  if (api() && api().get_data) return init();
  if (n > 30) return init(); // 通常ブラウザで開いた場合
  setTimeout(() => wait(n + 1), 100);
})(0);

/* ---------- 一覧 ---------- */
function chars(side) {
  if (!D) return [];
  return D.order[side].map((n) => D.chars[n]).filter(Boolean);
}

function chHTML(c, opts = {}) {
  if (!c) return "";
  const cls = opts.sel ? "ch sel" : "ch";
  return `<button class="${cls}" data-ch="${esc(c.name)}" title="${esc(c.name)}">
    <img src="${esc(sz(c.img, 96))}" loading="lazy" alt="">
    ${opts.tier !== false ? `<b class="tier ${c.tier}">${c.tier}</b>` : ""}
    ${c.isNew ? '<i class="new">NEW</i>' : ""}
    <span>${esc(short(c.name))}</span></button>`;
}

function render() {
  const showFilters = tab === "s" || tab === "h" || tab === "ban";
  $("#filters").style.display = showFilters ? "" : "none";
  $("#tiers").style.display = tab === "ban" ? "none" : "";
  const q = $("#q").value.trim();
  const list = $("#list");
  if (!D) return (list.innerHTML = '<p class="none">初回データ取得中…</p>');

  if (tab === "m") return renderMaps();
  if (tab === "pl") return renderPlaces();
  if (tab === "ban") return renderBan(q);

  let cs = chars(tab).filter((c) => (!q || c.name.includes(q)) && (!tierOn.size || tierOn.has(c.tier)));
  cs.sort((a, b) => RANK[a.tier] - RANK[b.tier]);
  // ティアごとに見出し
  let html = "", cur = null;
  for (const c of cs) {
    if (c.tier !== cur) {
      if (cur !== null) html += "</div>";
      cur = c.tier;
      html += `<h4 class="grp"><b class="tier ${cur}">${cur}</b></h4><div class="grid">`;
    }
    html += chHTML(c, { tier: false });
  }
  list.innerHTML = html + (cur !== null ? "</div>" : '<p class="none">該当なし</p>');
}

// 中国版公式データ
const cnMap = (name) => (D.cn && D.cn.map && D.cn.map.maps ? D.cn.map.maps[name] : null);
const cnChar = (name) => (D.cn && D.cn.char && D.cn.char.chars ? D.cn.char.chars[name] : null);
// 公式勝率から有利陣営を判定 (9マップ平均との差で ±3pt)
function dataAdv(name) {
  const m = cnMap(name);
  if (!m || !m.all) return null;
  const all = Object.values(D.cn.map.maps).filter((x) => x.all);
  const mean = all.reduce((a, x) => a + x.all[0] - x.all[2], 0) / all.length;
  const d = m.all[0] - m.all[2] - mean;
  return d > 3 ? "h" : d < -3 ? "s" : "n";
}
function statBar(v, label) {
  if (!v) return "";
  return `<div class="sbar"><span class="sl">${label}</span><div class="bar3">
    <i class="bh" style="width:${v[0]}%">ハン勝 ${v[0]}%</i><i class="bd" style="width:${v[1]}%">引分 ${v[1]}%</i><i class="bs" style="width:${v[2]}%">サバ勝 ${v[2]}%</i></div></div>`;
}
function mapHas(map, side, name) { const m = mapByName(map); return !!m && m[side].some((a) => a.name === name); }
const ADV = { s: ["サバ有利", "adv-s"], h: ["ハン有利", "adv-h"], n: ["互角", "adv-n"], mix: ["意見割れ", "adv-m"] };
const proMeta = (side, name) => !!(D.mapSources && D.mapSources.proMeta && (D.mapSources.proMeta[side] || []).includes(name));

// マップ一覧用のデータ (mapInfo があればそれ、無ければ旧データ)
function mapList() {
  if (D.mapInfo && Object.keys(D.mapInfo).length) {
    return Object.entries(D.mapInfo).map(([name, e]) => ({
      name, img: e.img || (D.maps[name] || {}).img || "", adv: e.adv, trait: e.trait,
      s: e.s || [], h: e.h || [], sources: e.sources || {}, opinions: e.opinions || [], cat: e.cat || "",
      dadv: dataAdv(name),
    }));
  }
  return Object.values(D.maps).map((m) => ({ ...m, s: m.s.map((n) => ({ name: n, n: 1, src: [] })), h: m.h.map((n) => ({ name: n, n: 1, src: [] })) }));
}
function mapByName(name) { return mapList().find((m) => m.name === name); }

// 地名・ハッチガイド
const MN = (name) => (D.mapNames && D.mapNames.maps ? D.mapNames.maps[name] : null);
function placeHTML(name, full) {
  const g = MN(name);
  if (!g) return "";
  return `<div class="place">
    ${full ? "" : `<div class="pname">${esc(name)}</div>`}
    <img src="${esc(g.img)}" data-zoom="${esc(g.img)}" loading="lazy" alt="${esc(name)}">
    <div class="hlist"><span class="hl">ハッチ→チャットで選ぶ地名</span>${g.hatches.map((h) => `<span class="hc"><b>${esc(h.area)}</b>${h.nick ? `<small>通称 ${esc(h.nick)}</small>` : ""}</span>`).join("")}</div>
    ${g.basement.length ? `<div class="hlist"><span class="hl bm">地下室</span>${g.basement.map((b) => `<span class="hc"><b>${esc(b)}</b></span>`).join("")}</div>` : ""}
    ${g.tips.length ? `<ul class="ptips">${g.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
  </div>`;
}
function renderPlaces() {
  const names = Object.keys((D.mapNames && D.mapNames.maps) || {});
  $("#list").innerHTML = names.length
    ? `<p class="none">ゲーム内チャットの「エリア」タブで選べる地名です。画像タップで拡大。</p>${names.map((n) => placeHTML(n)).join("")}
       <p class="none">出典: ${esc(D.mapNames.source || "")}</p>`
    : '<p class="none">地名データなし</p>';
}
function renderMaps() {
  $("#list").innerHTML = `<div class="maps">${mapList().map(mapHTML).join("")}</div>`;
}
function mapHTML(m) {
  const a = m.dadv || m.adv;
  const adv = a && ADV[a] ? `<i class="adv ${ADV[a][1]}">${ADV[a][0]}${m.dadv ? "" : "?"}</i>` : "";
  const st = cnMap(m.name);
  const cat = m.cat ? `<small>${m.cat === "ランク外" ? "ランク外" : "ランク" + m.cat + "マップ"}</small>` : "";
  return `<button class="mp" data-map="${esc(m.name)}"><img src="${esc(sz(m.img, 320))}" loading="lazy" alt="">${adv}
    <div>${esc(m.name)}${st && st.all ? `<small class="wr">ハン勝${st.all[0]}%</small>` : cat}</div></button>`;
}

// マップ詳細: 何ソースで推されているかでまとめて表示
function mapRows(list, side) {
  const cs = list.filter((a) => D.chars[a.name]);
  if (!cs.length) return '<p class="none">情報なし</p>';
  const groups = {};
  for (const a of cs) (groups[Math.min(a.n, 3)] ||= []).push(a);
  return Object.keys(groups).sort((a, b) => b - a).map((n) => {
    const label = n >= 3 ? "3つ以上のソースで一致" : n == 2 ? "2つのソースで一致" : "1つのソース";
    const wr = (x) => (cnChar(x) && cnChar(x).top ? cnChar(x).top.win : 0);
    const items = groups[n].sort((a, b) => RANK[D.chars[a.name].tier] - RANK[D.chars[b.name].tier] || wr(b.name) - wr(a.name));
    return `<div class="mgrp"><div class="mlbl">${label}</div><div class="row">${items.map((a) =>
      chHTML(D.chars[a.name]).replace("<button ", `<button title="${esc(a.name + (a.why ? "：" + a.why : "") + "\n出典: " + a.src.join("・") + (cnChar(a.name) && cnChar(a.name).top ? `\n公式(最上位) 勝率${cnChar(a.name).top.win}% 使用${cnChar(a.name).top.use}%` : ""))}" `)
        .replace("</button>", proMeta(side, a.name) ? '<i class="pro">大会</i></button>' : "</button>")).join("")}</div></div>`;
  }).join("");
}

/* ---------- BAN予測 ---------- */
let banMap = "";         // BAN画面に出るマップ(任意)
let records = [];        // 自分の試合記録
let picking = false;     // 実際のハンター選択中
let showHist = false;
let blockedH = new Set(); // 自分たちがBANしたハンター(=来ない)

// スコア = wiki経験則 + 攻略サイトの相性逆引き + マップ + 自分の記録(似たBANの試合ほど加点)
function predict() {
  if (!banned.size || !D) return [];
  const bans = [...banned];
  const out = [];
  for (const h of chars("h")) {
    if (blockedH.has(h.name)) continue;
    let s = 0;
    const why = { wiki: 0, rev: [], rec: 0, map: false };
    for (const r of D.banRules || []) {
      const w = r.hunters[h.name];
      if (w && r.bans.every((b) => banned.has(b))) { s += w * (r.bans.length > 1 ? 1.5 : 1); why.wiki++; }
    }
    if (banned.size >= 2)
      for (const r of D.extraRules || [])
        if (!banned.has(r.missing) && r.hunters.includes(h.name)) { s += r.w; why.wiki++; }
    why.rev = h.badS.filter((b) => banned.has(b));
    s += why.rev.length * 0.7;
    if (banMap && mapHas(banMap, "h", h.name)) { s += 0.4; why.map = true; }
    for (const r of records) {
      if (r.hunter !== h.name || !r.bans.length) continue;
      const inter = r.bans.filter((b) => banned.has(b)).length;
      if (!inter) continue;
      const jac = inter / new Set([...r.bans, ...bans]).size;
      s += 1.5 * jac + (banMap && r.map === banMap ? 0.3 : 0);
      why.rec++;
    }
    if (s < 0.3) continue;
    out.push({ h, s: s + 0.15 * W[h.tier], why });
  }
  return out.sort((a, b) => b.s - a.s).slice(0, 6);
}

function recommendPicks(pred) {
  const top = pred.slice(0, 2).map((p) => p.h.name);
  return chars("s")
    .filter((c) => !banned.has(c.name) && c.goodH.some((h) => top.includes(h)))
    .sort((a, b) => RANK[a.tier] - RANK[b.tier])
    .slice(0, 8);
}

function accuracy() {
  const rs = records.filter((r) => r.pred && r.pred.length && r.hunter);
  if (!rs.length) return "";
  const t1 = rs.filter((r) => r.pred[0] === r.hunter).length;
  const t3 = rs.filter((r) => r.pred.slice(0, 3).includes(r.hunter)).length;
  return `・的中 1位${Math.round((100 * t1) / rs.length)}% 3位内${Math.round((100 * t3) / rs.length)}%`;
}

function whyHTML(p) {
  const tags = [];
  if (p.why.rec) tags.push(`<i class="tag rec">記録${p.why.rec}</i>`);
  if (p.why.wiki) tags.push('<i class="tag wiki">wiki</i>');
  if (p.why.map) tags.push('<i class="tag">MAP</i>');
  return tags.join("") + p.why.rev.map((s) => `<img src="${esc(sz(D.chars[s].img, 48))}" title="${esc(s)}が苦手">`).join("");
}

function renderBan(q) {
  if (banView === "h") return renderHunterSide(q);
  const pred = predict();
  const max = pred.length ? pred[0].s : 1;
  let html = viewSwitch();
  if (!banned.size) {
    html += `<div class="pred"><p class="none">ランク戦の試合前画面（BAN）を<b>自動で読み取り</b>ます。手動ならBANされたサバイバーをタップ → 相手ハンター候補</p></div>`;
  } else {
    html += `<div class="pred">${pred.length ? pred.map((p) => `
        <div class="pr" data-ch="${esc(p.h.name)}">
          <img src="${esc(sz(p.h.img, 96))}" alt="">
          <div class="meter"><span class="nm">${esc(short(p.h.name))}</span> <b class="tier ${p.h.tier}">${p.h.tier}</b>
            <div class="bar" style="width:${(100 * p.s) / max}%"></div>
            <div class="why">${whyHTML(p)}</div>
          </div>
        </div>`).join("") : '<p class="none">該当する傾向なし（記録が増えると予測できます）</p>'}</div>`;
    const picks = recommendPicks(pred);
    if (picks.length)
      html += `<div class="lbl">おすすめピック（上位候補に強い）</div><div class="row">${picks.map((c) => chHTML(c)).join("")}</div>`;
  }
  if (blockedH.size)
    html += `<div class="lbl">BAN済みハンター（候補から除外）</div><div class="row blocked">${[...blockedH].map((n) => D.chars[n] ? chHTML(D.chars[n], { tier: false }).replace("data-ch=", "data-unblock=") : "").join("")}</div>`;
  const maps = [...new Set([...mapList().map((m) => m.name), ...(banMap ? [banMap] : [])])];
  html += `<div class="chips mapchips">${maps.map((m) => `<button class="chip ${m === banMap ? "on" : ""}" data-bmap="${esc(m)}">${esc(m)}</button>`).join("")}</div>`;
  html += `<div class="ban-help">
      <span>BAN ${banned.size}人</span>
      <span class="btns">
        <button id="readnow" title="ゲーム画面から読取 (F8)">📷読取</button>
        <button id="calib" title="読み取り設定">⚙</button>
        <button id="banclear">クリア</button>
      </span></div>`;
  if (banned.size)
    html += `<button id="recbtn" class="wide ${picking ? "on" : ""}">${picking ? "▼ 実際のハンターをタップで記録（戻る）" : "＋ 実際のハンターを記録"}</button>`;

  if (picking) {
    html += `<div class="grid">${chars("h").map((c) => chHTML(c, { tier: false }).replace("data-ch=", "data-rh=")).join("")}</div>`;
  } else {
    const cs = chars("s").filter((c) => !q || c.name.includes(q));
    html += `<div class="grid">${cs.map((c) => chHTML(c, { sel: banned.has(c.name), tier: false })).join("")}</div>`;
  }
  html += `<div class="ban-help foot"><span>記録 ${records.length}件${accuracy()}</span><button id="hist">${showHist ? "履歴を閉じる" : "履歴"}</button></div>`;
  if (showHist) html += histHTML();
  $("#list").innerHTML = html;
}

function histHTML() {
  const rs = records.slice(-30).reverse();
  if (!rs.length) return '<p class="none">まだ記録がありません</p>';
  const ic = (n) => (D.chars[n] ? `<img src="${esc(sz(D.chars[n].img, 48))}" title="${esc(n)}">` : "");
  return `<div class="hist">${rs.map((r) => `
    <div class="hr"><span class="d">${new Date(r.ts * 1000).toLocaleDateString("ja-JP", { month: "numeric", day: "numeric" })}</span>
      <span class="bans">${r.bans.map(ic).join("")}</span><span class="arrow">→</span>${ic(r.hunter)}
      <span class="m">${esc(r.map || "")}</span>
      ${r.pred && r.pred[0] === r.hunter ? '<i class="tag rec">的中</i>' : ""}
      <button class="del" data-del="${r.ts}" title="削除">×</button></div>`).join("")}</div>`;
}

async function loadRecords() {
  if (api()) try { records = await api().get_records(); } catch {}
}

async function addRecord(hunter) {
  const rec = { bans: [...banned], hunter, map: banMap, blocked: [...blockedH], pred: predict().map((p) => p.h.name) };
  const r = await api().add_record(rec);
  records = r.records;
  picking = false;
  toast(`記録しました${r.learned ? `（画面の見た目も${r.learned}枠学習）` : ""}`);
  banned.clear();
  blockedH.clear();
  banMap = "";
  render();
}

// Pythonから: 画面読取結果
window.onBanRead = (r, manual) => {
  if (r.error) return toast(r.error);
  if (r.bans) return onRankEvent({ type: "survivorBans", bans: r.bans });
  // 自動: 一致度が高いときだけ / 手動: 1位が2位より明確に高ければ採用
  const ok = (s) => s[0] && (s[0].score >= 0.72 || (manual && s[0].score >= 0.4 && s[0].score - ((s[1] || {}).score || 0) >= 0.06));
  const names = r.slots.filter(ok).map((s) => s[0].name);
  if (!names.length) return toast("BANを読み取れませんでした（⚙枠で位置を確認）");
  banned = new Set(names);
  picking = false;
  history = [];
  $("#detail").hidden = true;
  if (tab !== "ban") document.querySelector('[data-tab="ban"]').click();
  else render();
  toast("読取: " + names.map(short).join("・") + (manual ? "（違えばタップで修正）" : ""));
};

// Pythonから: ランク戦の試合前画面を自動で読んだ結果
function showBanTab() {
  picking = false;
  history = [];
  $("#detail").hidden = true;
  if (tab !== "ban") document.querySelector('[data-tab="ban"]').click();
  else render();
}
window.onRankEvent = (ev) => {
  if (!D) return;
  if (ev.side) banView = ev.side;
  if (ev.type === "newMatch") {
    banned.clear(); blockedH.clear(); banMap = "";
    sPicks.clear(); hBanned.clear(); sBlocked.clear();
    showBanTab();
    toast(`ランク戦の試合前画面を検出（${ev.side === "h" ? "ハンター" : "サバイバー"}視点）`);
  } else if (ev.type === "survivorBlocks") {
    sBlocked = new Set(ev.names.filter((n) => D.chars[n]));
    showBanTab();
  } else if (ev.type === "hunterBans") {
    hBanned = new Set(ev.names.filter((n) => D.chars[n]));
    showBanTab();
    toast("BANされた: " + ev.names.map(short).join("・"));
  } else if (ev.type === "survivorPicks") {
    sPicks = new Set(ev.names.filter((n) => D.chars[n]));
    showBanTab();
  } else if (ev.type === "map") {
    banMap = ev.map;
    showBanTab();
  } else if (ev.type === "hunterBlocks") {
    blockedH = new Set(ev.hunters.filter((n) => D.chars[n]));
    showBanTab();
    toast("BAN済み: " + ev.hunters.map(short).join("・"));
  } else if (ev.type === "survivorBans") {
    banned = new Set(ev.bans.filter((n) => D.chars[n]));
    showBanTab();
    toast("BANされた: " + ev.bans.map(short).join("・") + "（違えばタップで修正）");
  }
};

// Pythonから: 新しくゲーム内の画像を集めた
let iconT;
window.onIcons = () => {
  clearTimeout(iconT);
  iconT = setTimeout(async () => {
    const cur = $("#detail").hidden ? null : history[history.length - 1];
    await loadData();
    if (cur) showDetail(cur, true);
  }, 1500);
};

let toastT;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => (el.hidden = true), 3500);
}

/* ---------- BAN枠の設定 ---------- */
const cal = { img: null, rects: [], drag: null, start: null };

async function openCalib() {
  $("#calib-view").hidden = false;
  const s = api() ? await api().get_settings() : {};
  cal.rects = (s.slots || []).map((r) => r.slice());
  $("#autoread").checked = s.auto_read !== false;
  $("#autoshot").checked = s.auto_shot !== false;
  $("#gameicons").checked = s.game_icons !== false;
  if (api()) api().icon_stats().then((st) => ($("#iconstat").textContent = `${st.have}/${st.total}体`));
  loadShots();
  $("#calmsg").textContent = s.vision === false ? "画像認識ライブラリが未インストールです"
    : s.game ? "BAN画面を表示した状態で「撮影」" : "ゲームが起動していません";
  drawCalib();
}
async function loadShots() {
  const el = $("#shots");
  const list = api() ? await api().list_shots() : [];
  el.innerHTML = list.length
    ? list.map((x) => `<img src="${x.thumb}" data-shot="${esc(x.name)}" title="${esc(x.name.replace(/(\d{4})(\d\d)(\d\d)_(\d\d)(\d\d)(\d\d).*/, "$2/$3 $4:$5:$6"))}">`).join("")
    : '<p class="none">まだありません（ゲーム中に画面が変わると自動で保存されます）</p>';
}
function setCalImg(r) {
  if (r.error) return ($("#calmsg").textContent = r.error);
  cal.img = new Image();
  cal.img.onload = () => { $("#calmsg").textContent = "BANされたキャラを1枠ずつドラッグで囲む（最大3）"; drawCalib(); };
  cal.img.src = r.img;
}
$("#shots").addEventListener("click", async (e) => {
  const n = e.target.dataset.shot;
  if (!n) return;
  document.querySelectorAll("#shots img").forEach((i) => i.classList.toggle("on", i === e.target));
  setCalImg(await api().use_shot(n));
});
$("#shotsreload").onclick = loadShots;
$("#autoshot").onchange = (e) => api() && api().set_auto_shot(e.target.checked);
$("#gameicons").onchange = async (e) => { if (api()) { await api().set_game_icons(e.target.checked); loadData(); } };
async function calibShot() {
  $("#calmsg").textContent = "撮影中…";
  const r = await api().capture_preview();
  if (r.error) return ($("#calmsg").textContent = r.error);
  cal.img = new Image();
  cal.img.onload = () => { $("#calmsg").textContent = "BANされたキャラを1枠ずつドラッグで囲む（最大3）"; drawCalib(); };
  cal.img.src = r.img;
}
function drawCalib() {
  const cv = $("#calcv");
  const w = cv.clientWidth || 340;
  const ratio = cal.img ? cal.img.height / cal.img.width : 9 / 16;
  const H = w * ratio;
  cv.width = w * devicePixelRatio;
  cv.height = H * devicePixelRatio;
  cv.style.height = H + "px";
  const g = cv.getContext("2d");
  g.scale(devicePixelRatio, devicePixelRatio);
  g.fillStyle = "#000";
  g.fillRect(0, 0, w, H);
  if (cal.img) g.drawImage(cal.img, 0, 0, w, H);
  [...cal.rects, cal.drag].filter(Boolean).forEach((r, i) => {
    g.strokeStyle = "#e2645a"; g.lineWidth = 2;
    g.strokeRect(r[0] * w, r[1] * H, (r[2] - r[0]) * w, (r[3] - r[1]) * H);
    g.fillStyle = "#e2645a"; g.font = "bold 12px sans-serif";
    g.fillText(String(i + 1), r[0] * w + 3, r[1] * H + 13);
  });
}
function calPos(e) {
  const b = $("#calcv").getBoundingClientRect();
  return [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))];
}
$("#calcv").addEventListener("pointerdown", (e) => {
  if (!cal.img || cal.rects.length >= 3) return;
  cal.start = calPos(e);
  cal.drag = [...cal.start, ...cal.start];
  e.target.setPointerCapture(e.pointerId);
});
$("#calcv").addEventListener("pointermove", (e) => {
  if (!cal.drag) return;
  const p = calPos(e), s = cal.start;
  cal.drag = [Math.min(s[0], p[0]), Math.min(s[1], p[1]), Math.max(s[0], p[0]), Math.max(s[1], p[1])];
  drawCalib();
});
$("#calcv").addEventListener("pointerup", () => {
  if (!cal.drag) return;
  const r = cal.drag;
  if (r[2] - r[0] > 0.01 && r[3] - r[1] > 0.01) cal.rects.push(r);
  cal.drag = null;
  drawCalib();
});
$("#calshot").onclick = calibShot;
$("#calundo").onclick = () => { cal.rects.pop(); drawCalib(); };
$("#calsave").onclick = async () => {
  await api().save_slots(cal.rects);
  $("#calmsg").textContent = `保存しました（${cal.rects.length}枠）`;
};
$("#caltest").onclick = async () => {
  await api().save_slots(cal.rects);
  const r = await api().read_now();
  $("#calmsg").textContent = r.error ? r.error :
    r.slots.map((s, i) => `${i + 1}: ${s.map((x) => `${short(x.name)} ${Math.round(x.score * 100)}`).join(" / ")}`).join("\n");
};
$("#autoread").onchange = (e) => api() && api().set_auto_read(e.target.checked);
$("#calclose").onclick = () => ($("#calib-view").hidden = true);
window.addEventListener("resize", () => !$("#calib-view").hidden && drawCalib());

/* ---------- ハンター視点 ---------- */
let banView = "s";          // "s"=サバイバー視点 / "h"=ハンター視点
let pool = new Set();       // マイハンター(自分が使うハンター)
let sBlocked = new Set();   // 自分(ハンター)がBANしたサバイバー
let hBanned = new Set();    // 相手にBANされた自分のハンター
let sPicks = new Set();     // 相手サバイバーのピック(最大4)
let hEdit = "picks";        // 下のグリッドで編集する対象: picks / hban / pool / sban

// wikiで「主要BAN」とされているサバイバー(+wiki表に出てくるBAN対象)
function metaBans() {
  const m = new Set(["占い師", "祭司", "傭兵", "骨董商", "一等航海士", "弁護士", "機械技師", "オフェンス"]);
  for (const r of D.banRules || []) r.bans.forEach((b) => m.add(b));
  return m;
}

// BANおすすめ: マイハンターが苦手なサバイバー + 環境でよくBANされるキャラ + マップ
function banRecs() {
  const hs = [...pool].map((n) => D.chars[n]).filter(Boolean);
  const meta = metaBans();
  const mapS = banMap ? (mapByName(banMap) || { s: [] }).s.map((a) => a.name) : [];
  const out = [];
  for (const s of chars("s")) {
    let sc = 0;
    const why = { vs: [], meta: false, map: false };
    for (const h of hs) {
      if (h.badS.includes(s.name)) { sc += 1.2; why.vs.push(h.name); }
      if (h.goodS.includes(s.name)) sc -= 0.6;
    }
    if (meta.has(s.name)) { sc += 0.8; why.meta = true; }
    if (mapS.includes(s.name)) { sc += 0.4; why.map = true; }
    sc += 0.4 * W[s.tier];
    out.push({ c: s, s: sc, why });
  }
  return out.sort((a, b) => b.s - a.s).slice(0, 6);
}

// ピックおすすめ: 相手4人に対して得意なハンター (BANされたハンターは除外)
function pickRecs() {
  const base = pool.size ? [...pool].map((n) => D.chars[n]).filter(Boolean) : chars("h");
  const mapH = banMap ? (mapByName(banMap) || { h: [] }).h.map((a) => a.name) : [];
  const out = [];
  for (const h of base) {
    if (hBanned.has(h.name)) continue;
    const good = h.goodS.filter((s) => sPicks.has(s));
    const bad = h.badS.filter((s) => sPicks.has(s));
    let sc = good.length - bad.length + 0.4 * W[h.tier];
    const onMap = mapH.includes(h.name);
    if (onMap) sc += 0.5;
    out.push({ h, s: sc, good, bad, onMap });
  }
  return out.sort((a, b) => b.s - a.s).slice(0, 5);
}

function smallIcons(names, cls = "") {
  return names.map((n) => (D.chars[n] ? `<img class="${cls}" src="${esc(sz(D.chars[n].img, 48))}" title="${esc(n)}">` : "")).join("");
}

function setRow(set, attr, emptyMsg) {
  if (!set.size) return `<p class="none">${emptyMsg}</p>`;
  return `<div class="row">${[...set].map((n) => (D.chars[n] ? chHTML(D.chars[n], { tier: false }).replace("data-ch=", `${attr}=`) : "")).join("")}</div>`;
}

function renderHunterSide(q) {
  let html = viewSwitch();
  // 1. BANおすすめ
  const br = banRecs();
  html += `<div class="lbl">BANおすすめ（サバイバー）${pool.size ? "" : '<span class="none">　※マイハンター登録で精度UP</span>'}</div>
    <div class="pred">${br.map((r) => `
      <div class="pr" data-ch="${esc(r.c.name)}">
        <img src="${esc(sz(r.c.img, 96))}" alt="">
        <div class="meter"><span class="nm">${esc(short(r.c.name))}</span> <b class="tier ${r.c.tier}">${r.c.tier}</b>
          ${sBlocked.has(r.c.name) ? '<i class="tag rec">BAN済</i>' : ""}
          <div class="why">${r.why.meta ? '<i class="tag wiki">環境</i>' : ""}${r.why.map ? '<i class="tag">MAP</i>' : ""}${r.why.vs.length ? `<i class="tag bad">苦手</i>${smallIcons(r.why.vs)}` : ""}</div>
        </div></div>`).join("")}</div>`;
  // 2. 相手ピック → おすすめハンター
  html += `<div class="lbl">相手のピック</div>${setRow(sPicks, "data-unpick", "ロビーで自動で読み取ります（下で手動入力も可）")}`;
  if (sPicks.size) {
    const pr = pickRecs();
    const max = Math.max(...pr.map((p) => p.s), 0.1);
    html += `<div class="lbl">おすすめハンター${pool.size ? "（マイハンターから）" : ""}</div><div class="pred">${pr.map((p) => `
      <div class="pr" data-ch="${esc(p.h.name)}">
        <img src="${esc(sz(p.h.img, 96))}" alt="">
        <div class="meter"><span class="nm">${esc(short(p.h.name))}</span> <b class="tier ${p.h.tier}">${p.h.tier}</b>
          <div class="bar" style="width:${Math.max(4, (100 * p.s) / max)}%"></div>
          <div class="why">${p.onMap ? '<i class="tag">MAP</i>' : ""}${p.good.length ? `<i class="tag rec">得意</i>${smallIcons(p.good)}` : ""}${p.bad.length ? `<i class="tag bad">苦手</i>${smallIcons(p.bad)}` : ""}</div>
        </div></div>`).join("")}</div>`;
  }
  // 3. BAN状況
  if (hBanned.size) html += `<div class="lbl">BANされたハンター（除外）</div><div class="row blocked">${[...hBanned].map((n) => (D.chars[n] ? chHTML(D.chars[n], { tier: false }).replace("data-ch=", "data-unhban=") : "")).join("")}</div>`;
  if (sBlocked.size) html += `<div class="lbl">BANしたサバイバー</div><div class="row blocked">${[...sBlocked].map((n) => (D.chars[n] ? chHTML(D.chars[n], { tier: false }).replace("data-ch=", "data-unsban=") : "")).join("")}</div>`;
  // 4. マップ
  const maps = [...new Set([...mapList().map((m) => m.name), ...(banMap ? [banMap] : [])])];
  html += `<div class="chips mapchips">${maps.map((m) => `<button class="chip ${m === banMap ? "on" : ""}" data-bmap="${esc(m)}">${esc(m)}</button>`).join("")}</div>`;
  // 5. 手動編集
  const tabs = { picks: "相手ピック", hban: "BANされた", sban: "BANした", pool: "マイハンター" };
  html += `<div class="chips hedit">${Object.entries(tabs).map(([k, v]) => `<button class="chip ${k === hEdit ? "on" : ""}" data-hedit="${k}">${v}</button>`).join("")}<button class="chip" id="hclear">クリア</button></div>`;
  const side = hEdit === "picks" || hEdit === "sban" ? "s" : "h";
  const set = { picks: sPicks, hban: hBanned, sban: sBlocked, pool }[hEdit];
  const cs = chars(side).filter((c) => !q || c.name.includes(q));
  const ban = hEdit === "hban" || hEdit === "sban";  // BAN系は赤✕、ピック/マイハンターは緑枠
  html += `<div class="grid">${cs.map((c) => chHTML(c, { sel: set.has(c.name), tier: false }).replace("data-ch=", "data-htoggle=").replace('class="ch sel"', ban ? 'class="ch sel"' : 'class="ch on"')).join("")}</div>`;
  $("#list").innerHTML = html;
}

function viewSwitch() {
  return `<div class="seg"><button class="${banView === "s" ? "on" : ""}" data-view="s">サバイバー視点</button><button class="${banView === "h" ? "on" : ""}" data-view="h">ハンター視点</button></div>`;
}

function hToggle(name) {
  const set = { picks: sPicks, hban: hBanned, sban: sBlocked, pool }[hEdit];
  if (set.has(name)) set.delete(name);
  else {
    if (hEdit === "picks" && set.size >= 4) return toast("ピックは4人まで");
    set.add(name);
  }
  if (hEdit === "pool" && api()) api().set_pool([...pool]);
  render();
}

document.addEventListener("click", (e) => {
  const v = e.target.closest("[data-view]");
  if (v) { banView = v.dataset.view; return render(); }
  if (tab !== "ban" || banView !== "h") return;
  const t = e.target.closest("[data-htoggle]");
  if (t) return hToggle(t.dataset.htoggle);
  const ed = e.target.closest("[data-hedit]");
  if (ed) { hEdit = ed.dataset.hedit; return render(); }
  if (e.target.id === "hclear") { sPicks.clear(); hBanned.clear(); sBlocked.clear(); banMap = ""; return render(); }
  for (const [attr, set] of [["unpick", sPicks], ["unhban", hBanned], ["unsban", sBlocked]]) {
    const x = e.target.closest(`[data-${attr}]`);
    if (x) { set.delete(x.dataset[attr]); return render(); }
  }
});

/* ---------- 詳細 ---------- */
function row(names, cls = "") {
  const cs = names.map((n) => D.chars[n]).filter(Boolean);
  if (!cs.length) return '<p class="none">情報なし</p>';
  return `<div class="row ${cls}">${cs.map((c) => chHTML(c)).join("")}</div>`;
}
// 多ソース相性: 一致ソース数のバッジ + ホバーで出典と根拠
const MU = (n) => (D.matchups && D.matchups.chars ? D.matchups.chars[n] : null);
function muRow(list, max = 14) {
  const xs = (list || []).filter((x) => D.chars[x.name]).slice(0, max);
  if (!xs.length) return '<p class="none">情報なし</p>';
  return `<div class="row">${xs.map((x) => chHTML(D.chars[x.name], { tier: false })
    .replace(/title="[^"]*"/, `title="${esc(x.name + "\n出典: " + x.src.join("・") + (x.why.length ? "\n" + x.why.join("\n") : ""))}"`)
    .replace("</button>", `<i class="srcn n${Math.min(x.n, 3)}">${x.n}</i></button>`)).join("")}</div>`;
}
function muMaps(list, cls) {
  if (!list || !list.length) return '<p class="none">情報なし</p>';
  return `<div class="mchips">${list.map((x) => `<button class="mchip ${cls}" data-map="${esc(x.name)}" title="${esc("出典: " + x.src.join("・") + (x.why.length ? "\n" + x.why.join("\n") : ""))}">${esc(x.name)}<i>${x.n}</i></button>`).join("")}</div>`;
}
function iconRow(items) {
  return `<div class="row perk">${items.map((p) => `<div class="ch" title="${esc(p.name)}"><img src="${esc(sz(p.img, 84))}" alt=""><span>${esc(p.name)}</span></div>`).join("")}</div>`;
}

function showDetail(key, replace) {
  if (!replace) history.push(key);
  const body = $("#dbody"), title = $("#dtitle");
  $("#detail").hidden = false;
  body.scrollTop = 0;

  if (key.startsWith("map:")) {
    const m = mapByName(key.slice(4));
    if (!m) return goBack();
    const a = m.dadv || m.adv;
    const adv = a && ADV[a] ? `<i class="adv ${ADV[a][1]}">${ADV[a][0]}</i>` : "";
    const st = cnMap(m.name);
    const links = Object.entries(m.sources || {}).filter(([, v]) => v.url)
      .map(([k, v]) => `<span class="src" data-url="${esc(v.url)}">${esc(k)}</span>`).join(" ");
    title.innerHTML = `<img class="wide" src="${esc(sz(m.img, 320))}" alt=""><div><div class="nm">${esc(m.name)} ${adv}</div><div class="srcs">${links}</div></div>`;
    body.innerHTML = `
      ${m.trait ? `<p class="trait">${esc(m.trait)}</p>` : ""}
      ${MN(m.name) ? `<div class="sec"><div class="lbl">地名・ハッチ</div>${placeHTML(m.name, true)}</div>` : ""}
      ${st ? `<div class="cnbox"><div class="lbl">公式ランク勝率（中国版 S${esc(D.cn.map.season)}・${esc(D.cn.map.period)}）<span class="src" data-url="${esc(D.cn.url)}">出典</span></div>
        ${statBar(st.all, "全段位")}${statBar(st.top, "最上位")}</div>` : ""}
      ${m.opinions.length ? `<div class="ops">${m.opinions.map((o) => `<div><i class="adv ${ADV[o.adv][1]}">${ADV[o.adv][0]}</i> <span>${esc(o.note)}</span> <small>${esc(o.src)}</small></div>`).join("")}</div>` : ""}
      <div class="sec"><div class="lbl">サバイバー目線 おすすめ</div>${mapRows(m.s, "s")}</div>
      <div class="sec"><div class="lbl">ハンター目線 おすすめ</div>${mapRows(m.h, "h")}</div>
      <p class="none">ホバー(スマホは長押し)で理由と出典。上ほど多くの情報源で一致。「大会」=2026年の中国大会(IVL)でよく使われたキャラ。</p>
      ${D.mapSources && D.mapSources.note ? `<p class="none">※ ${esc(D.mapSources.note)}</p>` : ""}`;
    return;
  }

  const c = D.chars[key];
  if (!c) return goBack();
  const isS = c.side === "s";
  title.innerHTML = `<img src="${esc(sz(c.img, 128))}" alt=""><div>
    <div class="nm">${esc(c.name)} <b class="tier ${c.tier}">${c.tier}</b></div>
    <span class="src" data-url="${esc(c.url)}">神ゲー攻略</span> <span class="src" data-url="${esc(c.wiki || "")}">5chWiki</span></div>`;

  const builds = c.builds || [];
  const b = builds[0];
  const cs = cnChar(c.name);
  const mu = MU(c.name);
  const cnRow = (v, label) => v ? `<div class="cnrow"><span class="sl">${label}</span>
    <b>勝率 ${v.win}%</b><span>引分 ${v.draw}%</span><span>使用 ${v.use}%</span><span>BAN ${v.ban}%</span></div>` : "";
  body.innerHTML = `
    ${cs ? `<div class="sec cnbox"><div class="lbl">公式ランクデータ（中国版 S${esc(D.cn.char.season)}）<span class="src" data-url="${esc(D.cn.url)}">出典</span></div>
      ${cnRow(cs.all, "全段位")}${cnRow(cs.top, "最上位")}</div>` : ""}
    <div class="sec"><div class="lbl">人格</div>
      ${builds.length > 1 ? `<div class="chips">${builds.map((x, i) => `<button class="chip ${i ? "" : "on"}" data-b="${i}">${esc(x.name)}</button>`).join("")}</div>` : ""}
      <div id="build">${b ? buildHTML(b) : '<p class="none">情報なし</p>'}</div>
    </div>
    ${!isS ? `<div class="sec"><div class="lbl">補助特質</div>${c.traits.length ? iconRow(c.traits) : '<p class="none">情報なし</p>'}</div>` : ""}
    ${mu ? `<div class="sec"><div class="lbl"><span class="good">得意</span>${isS ? "なハンター" : "なサバイバー"}<small>数字=一致した情報源の数</small></div>${muRow(mu.good)}</div>
    <div class="sec"><div class="lbl"><span class="bad">苦手</span>${isS ? "なハンター" : "なサバイバー"}</div>${muRow(mu.bad)}</div>
    <div class="sec"><div class="lbl">マップ相性</div>
      <div class="mline"><span class="good">得意</span>${muMaps(mu.goodMaps, "g")}</div>
      <div class="mline"><span class="bad">苦手</span>${muMaps(mu.badMaps, "b")}</div></div>` : `
    <div class="sec"><div class="lbl"><span class="good">得意</span>${isS ? "なハンター" : "なサバイバー"}</div>${row(isS ? c.goodH : c.goodS)}</div>
    <div class="sec"><div class="lbl"><span class="bad">苦手</span>${isS ? "なハンター" : "なサバイバー"}</div>${row(isS ? c.badH : c.badS)}</div>`}
    ${isS && c.goodS.length ? `<div class="sec"><div class="lbl">相性◎ 味方</div>${row(c.goodS)}</div>` : ""}
    ${mu ? `<p class="none">ホバー(スマホは長押し)で出典と根拠。出典: 神ゲー攻略・5chWiki本文・Reddit英語圏相性表・中国記事・YouTube(OMC)・マップ集計</p>` : `<div class="sec"><div class="lbl">得意マップ</div>
      ${(() => { const ms = mapList().filter((m) => m[c.side].some((a) => a.name === c.name));
        return ms.length ? `<div class="mrow">${ms.map(mapHTML).join("")}</div>` : '<p class="none">情報なし</p>'; })()}</div>`}`;
  body._builds = builds;
}
function buildHTML(b) {
  return iconRow(b.perks) + (b.tree ? `<img class="tree" src="${esc(b.tree)}" data-zoom="${esc(b.tree)}" alt="人格ツリー">` : "");
}
function goBack() {
  history.pop();
  if (history.length) showDetail(history[history.length - 1], true);
  else $("#detail").hidden = true;
}

/* ---------- イベント ---------- */
$("#tabs").addEventListener("click", (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  tab = t.dataset.tab;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b === t));
  history = [];
  $("#detail").hidden = true;
  render();
  $("#list").scrollTop = 0;
});
$("#tiers").innerHTML = TIERS.map((t) => `<button class="tchip" data-t="${t}">${t}</button>`).join("");
$("#tiers").addEventListener("click", (e) => {
  const t = e.target.dataset.t;
  if (!t) return;
  tierOn.has(t) ? tierOn.delete(t) : tierOn.add(t);
  e.target.classList.toggle("on");
  render();
});
$("#q").addEventListener("input", render);

document.addEventListener("click", (e) => {
  const u = e.target.closest("[data-url]");
  if (u) return api() ? api().open_url(u.dataset.url) : window.open(u.dataset.url);
  const z = e.target.closest("[data-zoom]");
  if (z) { $("#zoom img").src = z.dataset.zoom; $("#zoom").hidden = false; return; }
  if (e.target.closest("#zoom")) return ($("#zoom").hidden = true);
  if (e.target.id === "banclear") { banned.clear(); blockedH.clear(); banMap = ""; picking = false; return render(); }
  const ub = e.target.closest("[data-unblock]");
  if (ub) { blockedH.delete(ub.dataset.unblock); return render(); }
  if (e.target.id === "readnow") return api() && api().read_now().then((r) => onBanRead(r, true));
  if (e.target.id === "calib") return openCalib();
  if (e.target.id === "recbtn") { picking = !picking; return render(); }
  if (e.target.id === "hist") { showHist = !showHist; return render(); }
  const bm = e.target.closest("[data-bmap]");
  if (bm) { banMap = banMap === bm.dataset.bmap ? "" : bm.dataset.bmap; return render(); }
  const rh = e.target.closest("[data-rh]");
  if (rh) return addRecord(rh.dataset.rh);
  const del = e.target.closest("[data-del]");
  if (del) return api().delete_record(+del.dataset.del).then((r) => { records = r; render(); });
  const bb = e.target.closest("[data-b]");
  if (bb) {
    document.querySelectorAll("#dbody .chip").forEach((x) => x.classList.toggle("on", x === bb));
    $("#build").innerHTML = buildHTML($("#dbody")._builds[+bb.dataset.b]);
    return;
  }
  const mp = e.target.closest("[data-map]");
  if (mp) return showDetail("map:" + mp.dataset.map);
  const ch = e.target.closest("[data-ch]");
  if (ch) {
    const n = ch.dataset.ch;
    if (tab === "ban" && $("#detail").hidden && ch.closest("#list > .grid")) {
      banned.has(n) ? banned.delete(n) : banned.add(n);
      return render();
    }
    showDetail(n);
  }
});
$("#back").addEventListener("click", goBack);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!$("#calib-view").hidden) $("#calib-view").hidden = true;
    else if (!$("#zoom").hidden) $("#zoom").hidden = true;
    else if (!$("#detail").hidden) goBack();
  }
  if (e.key === "/" && document.activeElement !== $("#q")) { e.preventDefault(); $("#q").focus(); }
});
$("#pin").addEventListener("click", () => {
  const on = !$("#pin").classList.contains("on");
  $("#pin").classList.toggle("on", on);
  api() && api().set_on_top(on);
});
$("#reload").addEventListener("click", () => api() && api().refresh());
