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
  hideSplash();
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

/* 起動アニメーション: 最低 2.1 秒見せてから、データ読込後にフェードアウト (クリックで飛ばせる) */
const SPLASH_T0 = Date.now();
function hideSplash(now) {
  const el = $("#splash");
  if (!el || el.classList.contains("out")) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const wait = now || reduce ? 0 : Math.max(0, 2100 - (Date.now() - SPLASH_T0));
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 800); }, wait);
}
$("#splash") && $("#splash").addEventListener("click", () => hideSplash(true));
setTimeout(() => hideSplash(true), 7000); // 読込が遅くても閉じる

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
  if (tab === "beg") return renderBeginner();
  if (tab === "ctr") return renderCounter();

  let cs = chars(tab).filter((c) => (!q || c.name.includes(q)) && (!tierOn.size || tierOn.has(c.tier)));
  cs.sort((a, b) => RANK[a.tier] - RANK[b.tier]);
  // ティアごとに見出し
  let html = "", cur = null;
  for (const c of cs) {
    if (c.tier !== cur) {
      if (cur !== null) html += "</div>";
      cur = c.tier;
      const n = cs.filter((x) => x.tier === cur).length;
      html += `<h4 class="grp t-${cur}"><span class="tl">${cur}</span><span class="tn">${TIER_LABEL[cur] || ""}</span><small>${n}</small></h4><div class="grid">`;
    }
    html += chHTML(c, { tier: false });
  }
  list.innerHTML = html + (cur !== null ? "</div>" : '<p class="none">該当なし</p>');
}

/* ---------- 複数サイトのティア評価 ---------- */
const TIER_NUM = { "SS": 5.5, "S+": 5.5, "S": 5, "S-": 4.6, "A+": 4.3, "A": 4, "A-": 3.6, "B+": 3.3, "B": 3, "B-": 2.6, "C+": 2.3, "C": 2, "C-": 1.6, "D": 1 };
const numTier = (v) => (v >= 4.75 ? "S" : v >= 3.75 ? "A" : v >= 2.75 ? "B" : v >= 1.75 ? "C" : "D");
function tierVotes(c) {
  const out = [];
  if (c.tier && c.tier !== "?") out.push({ label: D.source.name, tier: c.tier, url: c.url, date: D.source.tierUpdated[c.side] || "" });
  const X = D.tiersExtra;
  if (X) for (const [k, s] of Object.entries(X.sources)) {
    const t = X[c.side] && X[c.side][k] && X[c.side][k][c.name];
    if (t) out.push({ label: s.label, tier: t, url: s["url_" + c.side] || "", date: s["date_" + c.side] || "", note: s["note_" + c.side] || "" });
  }
  return out;
}
function tierAvg(c) {
  const v = tierVotes(c).map((x) => TIER_NUM[x.tier]).filter(Boolean);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}
function tierBox(c) {
  const vs = tierVotes(c);
  if (vs.length < 2) return "";
  const avg = tierAvg(c), nums = vs.map((x) => TIER_NUM[x.tier]);
  const split = Math.max(...nums) - Math.min(...nums) >= 2;
  return `<div class="sec"><div class="lbl">ティア評価<small>${vs.length}サイト ・ 平均 <b class="tier ${numTier(avg)}">${numTier(avg)}</b>${split ? " ・ 評価が割れています" : ""}</small></div>
    <div class="tvotes">${vs.map((x) => `<span class="tv" ${x.url ? `data-url="${esc(x.url)}"` : ""} title="${esc(x.label)} ${esc(x.date)}${x.note ? "（" + esc(x.note) + "）" : ""}"><b class="tier ${x.tier[0]}">${esc(x.tier)}</b><small>${esc(x.label)}</small></span>`).join("")}</div></div>`;
}

function tplExamples(side, k) {
  const V = D.personaVideos;
  if (!V) return "";
  const ex = (V[side] || []).filter((v) => v.tpl === k && !(v.chars || []).length);
  if (!ex.length) return "";
  return `<div class="tex">${ex.map((v) => `<div class="texi">${webHTML(v, side, true)}<small>${esc(v.name)}</small></div>`).join("")}</div>
    <p class="none">例: ${esc(V.sources[ex[0].src].label)}（${esc(V.sources[ex[0].src].date)}）の動画の画面を読み取ったもの</p>`;
}

/* 人格テンプレのまとめ (全キャラのおすすめ構成から集計) */
function tplSummary(side) {
  const cs = chars(side), by = {};
  for (const c of cs) for (const k of new Set((c.builds || []).map((b) => tplOf(side, b)))) (by[k] ||= []).push(c);
  const list = TPL[side].filter((x) => by[x.k]);
  const core = list.filter((x) => x.k !== "other");
  return `<h4 class="grp"><span class="tn">人格テンプレ</span><small>${core.length}パターン用意すれば${side === "s" ? "ほぼ全サバイバー" : "全ハンター"}に対応</small></h4>
    <div class="tpls">${list.map((x) => `<div class="tpl"><div class="th"><b>${esc(x.name)}</b><small>${by[x.k].length}キャラ</small></div>
      ${x.key.length ? `<div class="tk">${x.key.map((k) => `<i>${esc(k)}</i>`).join("")}</div>` : ""}<p>${esc(x.note)}</p>
      ${tplExamples(side, x.k)}
      <div class="tc">${by[x.k].map((c) => `<button data-ch="${esc(c.name)}" title="${esc(c.name)}"><img src="${esc(sz(c.img, 48))}" alt="" loading="lazy"></button>`).join("")}</div></div>`).join("")}</div>
    ${side === "s" ? '<p class="none">2026年7月の新人格: 「愛着効果」（味方の治療が速くなり約8割で手を離しても完了）は全サバイバーにおすすめ、アイテム消費型は「使い切った後の箱開け高速化」も強い（唯のん 2026/7）。</p>' : ""}
    <p class="none">各キャラのおすすめ構成（${esc(D.source.name)}）を自動で分類した結果。キャラ詳細の「人格」にもテンプレ名を表示しています。</p>`;
}

/* ---------- 初心者おすすめ ---------- */
// 扱いやすさ (YouTube解説) と 今の強さ (最新ティア) を足して並べる。ティアが変われば順番も変わる
const EASE_PT = { S: 3, "S-": 2.6, A: 2.2, B: 1.5 };
const TIER_PT = { S: 2, A: 1.6, B: 1.1, C: 0.6, D: 0, "?": 0.8 };
let begSide = "s";
function renderBeginner() {
  const B = D.beginner, list = $("#list");
  if (!B || !B[begSide]) return (list.innerHTML = '<p class="none">おすすめデータがありません</p>');
  const S = B[begSide], src = B._sources || {};
  const picks = S.pick.map((p, i) => ({ p, i, c: D.chars[p.name] })).filter((x) => x.c)
    .map((x) => { const nt = x.c.tier; return { ...x, nt, pt: (EASE_PT[x.p.ease] || 2) + (TIER_PT[nt] ?? 0.8) }; }) // 一覧(ランキング)と同じティア
    .sort((a, b) => b.pt - a.pt || a.i - b.i);
  const cards = picks.map(({ p, c, nt }, i) => `<button class="bcard" data-ch="${esc(c.name)}">
      <span class="brank">${i + 1}</span>
      <img src="${esc(sz(c.img, 128))}" loading="lazy" alt="">
      <span class="bbody">
        <span class="bname">${esc(short(c.name))}</span>
        <span class="bbadges"><span class="bb ease" title="初心者の扱いやすさ（YouTube解説）">扱いやすさ <b>${esc(p.ease || "-")}</b></span><span class="bb now t-${nt}" title="今の環境での強さ（サバ/ハンター一覧のランキングと同じ：${esc(D.source.name)} ${esc(D.source.tierUpdated[begSide] || "")}）">今の強さ <b>${nt}</b></span>${p.note ? `<span class="bb note">${esc(p.note)}</span>` : ""}</span>
        <span class="bwhy">${esc(p.why)}</span>
        ${p.tip ? `<span class="btip"><em>コツ</em>${esc(p.tip)}</span>` : ""}
        <span class="bsrc">${(p.src || []).map((k) => src[k] ? `<small data-url="${esc(src[k].url)}" title="${esc(src[k].label)}${src[k].date ? " (" + esc(src[k].date) + ")" : ""}">${esc(src[k].short || src[k].label)}</small>` : "").join("")}</span>
      </span></button>`).join("");
  const avoid = (S.avoid || []).map((a) => {
    const c = D.chars[a.name];
    return c ? `<button class="bavoid" data-ch="${esc(c.name)}"><img src="${esc(sz(c.img, 64))}" loading="lazy" alt=""><span><b>${esc(short(c.name))}<i class="tier ${c.tier}">${c.tier}</i></b><small>${esc(a.why)}</small></span></button>` : "";
  }).join("");
  const links = Object.values(src).filter((s) => s.url).map((s) => `<u data-url="${esc(s.url)}">${esc(s.label)}${s.date ? `（${esc(s.date)}）` : ""}</u>`).join(" ・ ");
  list.innerHTML = `<div class="beg">
    <div class="pseg bseg"><button data-bside="s" class="${begSide === "s" ? "on" : ""}">サバイバー</button><button data-bside="h" class="${begSide === "h" ? "on" : ""}">ハンター</button></div>
    <p class="blead">${begSide === "s" ? "操作がシンプルで、今の環境でも戦えるサバイバー" : "操作がシンプルで、今の環境でも勝ちやすいハンター"}<br><small>「扱いやすさ」はYouTube解説、「今の強さ」はサバ/ハンター一覧のランキングと同じ。2つの合計で並べています（ティアが変わると順番も変わります）・タップで詳細へ</small></p>
    <div class="blist">${cards}</div>
    <h4 class="grp"><span class="tn">${begSide === "s" ? "最初は避けたいキャラ" : "強いけど最初は難しいキャラ"}</span><small>慣れてから</small></h4>
    <div class="bavoids">${avoid}</div>
    ${tplSummary(begSide)}
    <p class="bfoot">出典: ${links}（${esc(B.updated || "")} まとめ）</p></div>`;
}

/* ---------- ハンター対策・ダメージ計算 ---------- */
// 体力ゲージ (2マス=ダウン。0.5刻みで半マス)
function hpSVG(d, w = 54) {
  const cell = (x, i) => {
    const l = d >= i + 0.5, r = d >= i + 1;
    return `<rect x="${x}" y="2" width="11" height="12" rx="3" fill="${l ? "var(--bad)" : "var(--good)"}"/>
      <rect x="${x + 11}" y="2" width="11" height="12" rx="3" fill="${r ? "var(--bad)" : "var(--good)"}"/>
      <rect x="${x}" y="2" width="22" height="12" rx="3" fill="none" stroke="#0008"/><line x1="${x + 11}" y1="2" x2="${x + 11}" y2="14" stroke="#0006"/>`;
  };
  return `<svg class="hp" viewBox="0 0 50 16" width="${w}">${cell(2, 0)}${cell(26, 1)}</svg>`;
}
// サバイバーの人形 (0 無傷 / 1 負傷 / 2 ダウン)
function survSVG(st) {
  const col = st === 0 ? "var(--good)" : "var(--bad)";
  if (st === 2) return `<svg class="surv" viewBox="0 0 48 40"><circle cx="9" cy="30" r="5" fill="${col}"/><path d="M15 28h22l5 4H15z" fill="${col}"/><path d="M6 20l4 4M14 18v5M22 20l-3 4" stroke="var(--bad)" stroke-width="2" stroke-linecap="round"/></svg>`;
  return `<svg class="surv" viewBox="0 0 48 40"><circle cx="24" cy="8" r="5.5" fill="${col}"/><path d="M17 16h14l2 13h-4l-1 10h-8l-1-10h-4z" fill="${col}"/>${st === 1 ? '<path d="M30 20l4-3M31 25l5-1" stroke="#fff8" stroke-width="1.6" stroke-linecap="round"/>' : ""}</svg>`;
}
const CT_ICON = {
  hit: '<path d="M5 19L17 7M14 5l5 5"/><path d="M4 14l6 6"/>',
  terror: '<rect x="4" y="5" width="16" height="14" rx="1"/><path d="M12 5v14M4 12h16"/>',
  gate: '<path d="M4 20V9a8 8 0 0 1 16 0v11"/><path d="M8 20v-9M12 20V7M16 20v-9"/>',
  half: '<circle cx="12" cy="12" r="7"/><path d="M12 5a7 7 0 0 1 0 14z" fill="currentColor"/>',
  chair: '<path d="M7 3v10h10V3M7 13l-2 8M17 13l2 8M5 17h14"/>',
  eye: '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/>',
  run: '<circle cx="15" cy="4.5" r="2"/><path d="M8 21l3-6 3 2v4M10 9l4-2 3 4 3 1M6 12l3-3"/>',
};
const ctIcon = (k) => `<svg class="cti" viewBox="0 0 24 24">${CT_ICON[k]}</svg>`;
let ctrTag = "", ctrView = "b", ctrPick = "";
function renderCounter() {
  const C = D.counter, list = $("#list");
  if (!C) return (list.innerHTML = '<p class="none">対策データがありません</p>');
  const eq = (parts, d, note) => `<div class="ceq">${parts.map((p) => `<span class="cp ${p[2] || ""}">${p[0]}<b>${p[1]}</b></span>`).join('<i class="op">＋</i>')}<i class="op">＝</i>${hpSVG(d, 46)}<span class="cres">${note}</span></div>`;
  const basics = `
    <div class="cbox">
      <div class="ch3">体力は2マス（0.5刻み）</div>
      <div class="cstates">
        <div>${survSVG(0)}${hpSVG(0)}<b>無傷</b><small>ダメージ 0</small></div>
        <div class="arw">→</div>
        <div>${survSVG(1)}${hpSVG(1)}<b>負傷</b><small>ダメージ 1</small></div>
        <div class="arw">→</div>
        <div>${survSVG(2)}${hpSVG(2)}<b>ダウン</b><small>ダメージ 2</small></div>
      </div>
    </div>
    <div class="cbox">
      <div class="ch3">ダメージの足し算</div>
      <div class="cparts">
        <span class="cpart">${ctIcon("hit")}<b>通常攻撃</b><em>1</em></span>
        <span class="cpart">${ctIcon("half")}<b>スキル（多く）</b><em>0.5</em></span>
        <span class="cpart bad">${ctIcon("terror")}<b>恐怖の一撃</b><em>＋1</em><small>板窓の乗り越え・救助・治療などの最中に殴られる</small></span>
        <span class="cpart bad">${ctIcon("gate")}<b>引き留める</b><em>＋1</em><small>通電してから120秒間（ハンターの人格）</small></span>
      </div>
      ${eq([["通常", "1"], ["恐怖", "＋1", "bad"]], 2, "無傷でも即ダウン")}
      ${eq([["通常", "1"], ["引き留める", "＋1", "bad"]], 2, "通電後は1発でダウン")}
      ${eq([["スキル", "0.5"], ["スキル", "0.5"]], 1, "2回で負傷")}
      ${eq([["檻の外", "0.5"], ["恐怖", "＋1", "bad"], ["引き留める", "＋1", "bad"]], 2, "足萎えの羊なら2.5 → ダウン")}
    </div>
    <div class="cbox">
      <div class="ch3">覚えておくこと</div>
      <ul class="ctips">
        <li>${ctIcon("run")}<span>殴られると一瞬<b>加速</b>、ハンターは<b>硬直</b> → 距離を取るチャンス<small>0.5ダメージではほとんどのキャラは加速しない</small></span></li>
        <li>${ctIcon("half")}<span>0.5だけの傷は<b>基本は治療できない</b>（1たまってから）<small>0.5を重ねてくるハンターには傷を残さないのが大事</small></span></li>
        <li>${ctIcon("terror")}<span>ハンターが近い時は<b>板窓・救助・治療をしない</b>（恐怖の一撃）</span></li>
        <li>${ctIcon("chair")}<span>救助された後20秒は<b>危機一髪</b>でダウンを先送りできる</span></li>
      </ul>
    </div>
    <div class="cbox">
      <div class="ch3">椅子のゲージ</div>
      <svg class="chairbar" viewBox="0 -2 320 56">
        <rect x="10" y="18" width="300" height="12" rx="6" fill="#ffffff14"/>
        <rect x="10" y="18" width="150" height="12" rx="6" fill="var(--good)" opacity=".55"/>
        <rect x="160" y="18" width="150" height="12" rx="6" fill="var(--bad)" opacity=".55"/>
        <line x1="130" y1="14" x2="130" y2="34" stroke="var(--gold1)" stroke-width="2"/><text x="130" y="9" text-anchor="middle">4割救助</text>
        <line x1="160" y1="14" x2="160" y2="34" stroke="#fff" stroke-width="2" stroke-dasharray="3 2"/><text x="160" y="48" text-anchor="middle">5割</text>
        <line x1="280" y1="14" x2="280" y2="34" stroke="var(--gold1)" stroke-width="2"/><text x="280" y="9" text-anchor="middle">9割救助</text>
        <text x="10" y="48">0%</text><text x="310" y="48" text-anchor="end">脱落</text>
      </svg>
      <p class="cnote">5割を越えてから救助されると、<b>次に吊られたら即脱落</b>。2回吊られた人も次は即脱落。</p>
    </div>`;
  const tags = C.tags || {};
  const hs = chars("h").filter((c) => C.h[c.name]).sort((a, b) => RANK[a.tier] - RANK[b.tier]);
  const seg = `<div class="pseg bseg"><button data-cview="b" class="${ctrView === "b" ? "on" : ""}">基本</button><button data-cview="h" class="${ctrView === "h" ? "on" : ""}">キャラ別</button></div>`;
  const foot = `<p class="bfoot">5ch攻略Wikiの対策ページと、YouTubeの対策解説動画（各カードの「くわしく」に動画名と日付）を短くまとめたもの（${esc(C.updated)}）。古い動画の内容は今の性能と違う場合があります</p>`;
  if (ctrView === "b") {
    list.innerHTML = `<div class="beg ctr">${seg}<h4 class="grp"><span class="tn">ダメージの基本</span></h4><div class="cgrid">${basics}</div>${foot}</div>`;
    return;
  }
  const q = ($("#q").value || "").trim();
  const pickable = hs.filter((c) => !ctrTag || (C.h[c.name].tags || []).includes(ctrTag));
  const shown = (ctrPick ? hs.filter((c) => c.name === ctrPick) : pickable).filter((c) => !q || c.name.includes(q));
  const pick = `<div class="cpick">
      <button data-cpick="" class="${ctrPick ? "" : "on"}"><span class="all">全</span><small>全員</small></button>
      ${pickable.map((c) => `<button data-cpick="${esc(c.name)}" class="${ctrPick === c.name ? "on" : ""}" title="${esc(c.name)}"><img src="${esc(sz(c.img, 96))}" alt="" loading="lazy"><small>${esc(short(c.name))}</small></button>`).join("")}
    </div>`;
  const cards = shown.map((c) => {
    const x = C.h[c.name];
    const open = ctrPick === c.name || ctrOpen.has(c.name);
    return `<div class="ccard${open ? " open" : ""}" data-cc="${esc(c.name)}">
      <button class="chd" data-ch="${esc(c.name)}"><img src="${esc(sz(c.img, 96))}" alt="" loading="lazy"><span><b>${esc(short(c.name))}<i class="tier ${c.tier}">${c.tier}</i></b><small>${esc(x.t)}</small></span></button>
      ${ctrBody(x, tags)}
      ${ctrMore(x) ? (ctrPick === c.name ? ctrMore(x) : `<button class="cmore" data-cmore="${esc(c.name)}">${open ? "とじる ▲" : "くわしく（チェイス・救助・立ち回り） ▼"}</button>${open ? ctrMore(x) : ""}`) : ""}
    </div>`;
  }).join("");
  list.innerHTML = `<div class="beg ctr">${seg}
    <div class="ctagbar">${Object.entries(tags).map(([k, v]) => `<button data-ctag="${k}" class="ctag t-${k} ${ctrTag === k ? "on" : ""}">${esc(v)}</button>`).join("")}</div>
    ${pick}
    <h4 class="grp"><span class="tn">${ctrPick ? esc(short(ctrPick)) + "の対策" : "ハンター別の対策"}</span>${ctrPick ? "" : `<small>${shown.length}体</small>`}</h4>
    <div class="clist${ctrPick ? " one" : ""}">${cards || '<p class="none">該当なし</p>'}</div>
    ${foot.replace("</p>", "・カードの名前をタップで詳細へ</p>")}</div>`;
}
function ctrBody(x, tags) {
  const b = [...(x.tags || []).map((t) => `<i class="ctag t-${t}">${esc((tags || {})[t] || t)}</i>`), ...(x.dmg || []).map((d) => `<i class="cdmg">${esc(d[0])} <b>${esc(d[1])}</b></i>`)];
  return `${b.length ? `<div class="cbadges">${b.join("")}</div>` : ""}
    <ol class="cl">${x.c.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    ${x.see ? `<div class="csee">${ctIcon("eye")}<span><em>見分け方</em>${esc(x.see)}</span></div>` : ""}
    ${x.r ? `<div class="cr">${ctIcon("chair")}<span>${esc(x.r)}</span></div>` : ""}`;
}
const CTR_SEC = [["chase", "チェイス", "run"], ["rescue", "救助", "chair"], ["game", "解読・立ち回り", "gate"]];
function ctrMore(x) {
  const secs = CTR_SEC.filter(([k]) => (x[k] || []).length);
  if (!secs.length) return "";
  const S = (D.counter && D.counter.sources) || {};
  return `<div class="cmorebody">${secs.map(([k, l, ic]) => `<div class="csec"><div class="csh">${ctIcon(ic)}${l}</div><ul>${x[k].map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>`).join("")}
    ${(x.src || []).length ? `<div class="csrc">${x.src.map((k) => S[k] ? `<small data-url="${esc(S[k].url)}" title="${esc(S[k].label)}">${S[k].url.includes("youtube") ? "▶ " : ""}${esc(S[k].label)}<b>${esc(S[k].date)}</b></small>` : "").join("")}</div>` : ""}</div>`;
}
let ctrOpen = new Set();
// ハンター詳細などから対策タブのそのキャラへ飛ぶ
function goCounter(name) {
  ctrTag = ""; ctrView = "h"; ctrPick = name;
  document.querySelector('[data-tab="ctr"]').click();
  const el = [...document.querySelectorAll("[data-cc]")].find((e) => e.dataset.cc === name);
  if (!el) return;
  $("#list").scrollTop = 0;
  const pb = $(".cpick button.on"); if (pb) pb.scrollIntoView({ block: "nearest", inline: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1600);
}
// キャラ詳細 (ハンター) に出す短い対策
function counterSec(c) {
  const x = D.counter && D.counter.h[c.name];
  if (!x) return "";
  return `<div class="sec"><div class="lbl">サバイバー側の対策<button class="mini goctr" data-goctr="${esc(c.name)}">対策をくわしく見る →</button></div><div class="ccard flat"><p class="ct">${esc(x.t)}</p>${ctrBody(x, D.counter.tags)}</div></div>`;
}

/* 人格マスのツールチップ (効果を Lv1/2/3 で) */
function ptipHTML(key) {
  const [side, name, p, mx] = key.split("|");
  const E = D.personaEffects && D.personaEffects[side] && D.personaEffects[side][name];
  const cur = +p, max = +mx || 1;
  let body;
  if (!E) body = '<p class="ptn">効果の情報がありません</p>';
  else if (max <= 1 || E.lv.length <= 1) body = `<p class="ptl on1">${esc(E.lv[0])}</p>`;
  else body = Array.from({ length: max }, (_, k) => `<p class="ptl${k + 1 === cur ? " cur" : ""}"><b>Lv${k + 1}</b>${esc(E.lv[Math.min(k, E.lv.length - 1)])}</p>`).join("");
  return `<div class="pth"><b>${esc(name)}</b><span>${cur ? `${cur}/${max} 振り` : `未振り（最大${max}）`}</span></div>${body}`;
}
function ptipShow(el, x, y) {
  let t = $("#ptip");
  if (!t) { t = document.createElement("div"); t.id = "ptip"; document.body.appendChild(t); }
  t.innerHTML = ptipHTML(el.getAttribute("data-pk"));
  t.hidden = false;
  const w = t.offsetWidth, h = t.offsetHeight, W = innerWidth, H = innerHeight;
  t.style.left = Math.max(8, Math.min(W - w - 8, x + 14)) + "px";
  t.style.top = (y + 16 + h > H - 8 ? Math.max(8, y - h - 12) : y + 16) + "px";
}
const ptipHide = () => { const t = $("#ptip"); if (t) t.hidden = true; };
document.addEventListener("mouseover", (e) => {
  const el = e.target.closest && e.target.closest("[data-pk]");
  if (el) ptipShow(el, e.clientX, e.clientY); else ptipHide();
});
document.addEventListener("mousemove", (e) => {
  const t = $("#ptip");
  if (t && !t.hidden && e.target.closest && e.target.closest("[data-pk]")) ptipShow(e.target.closest("[data-pk]"), e.clientX, e.clientY);
});
document.addEventListener("touchstart", (e) => {
  const el = e.target.closest && e.target.closest("[data-pk]");
  if (el) { const p = e.touches[0]; ptipShow(el, p.clientX, p.clientY); } else ptipHide();
}, { passive: true });
document.addEventListener("scroll", ptipHide, true);

const TIER_LABEL = { S: "環境トップ", A: "強力", B: "標準", C: "やや不利", D: "厳しい" };

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
// 読みにくい地名にふりがな
const FURI = { 旧妓楼: "きゅうぎろう", 妓楼: "ぎろう", 槐樹: "かいじゅ", 酔芳庭: "すいほうてい", 紙飾屋: "かみかざりや", 獅子楼: "ししろう",
  酒楼: "しゅろう", 赤傘巷: "あかがさこう", 裁縫屋: "さいほうや", 骨董屋: "こっとうや", 浅瀬: "あさせ", 東屋: "あずまや", 石浜: "いしはま",
  積卸: "つみおろし", 廃墟: "はいきょ", 彫像: "ちょうぞう", 狩人: "かりゅうど", 監視所: "かんしじょ", 野営地: "やえいち", 始発駅: "しはつえき",
  廃材: "はいざい", 最果て: "さいはて", 飼育: "しいく", 貨物: "かもつ", 箱詰め: "はこづめ" };
const FURI_RE = new RegExp(Object.keys(FURI).sort((a, b) => b.length - a.length).join("|"), "g");
const furi = (t) => esc(t).replace(FURI_RE, (w) => `<ruby>${w}<rt>${FURI[w]}</rt></ruby>`);
let placeMap = "";      // 地名タブで表示中のマップ
let placeLayer = "all"; // all | hatch | base | gate
// 地図の上に地名・ハッチ・地下室・ゲートを重ねる (文字は画面幅に合わせて自動で拡大縮小)
function mapOverlay(g, cls = "") {
  const L = g.layout;
  if (!L) return `<img class="pimg" src="${esc(g.img)}" data-zoom="${esc(g.img)}" alt="">`;
  const lab = L.labels.map((l) => `<span class="pl${l.basement ? " is-base" : ""}${l.gate ? " is-gate" : ""}" data-area="${esc(l.name)}" data-x="${l.x}" data-y="${l.y}" style="left:${l.x}%;top:${l.y}%">${furi(l.name)}${
    l.basement ? '<i class="tb">地下室</i>' : ""}</span>`).join("");
  const gate = (L.gates || []).map((q) => `<span class="pg${q.name === "正門" ? " main" : ""}" data-x="${q.x}" data-y="${q.y}" style="left:${q.x}%;top:${q.y}%" title="${esc(q.name + "ゲート")}"><svg viewBox="0 0 24 24"><path d="M5 20V9a7 7 0 0 1 14 0v11M5 20h14M12 4v16"/></svg>${esc(q.name)}</span>`).join("");
  const hat = L.hatches.map((h, i) => `<b class="ph" data-hi="${i}" style="left:${h.x}%;top:${h.y}%" title="${esc("ハッチ → チャットで「" + h.area + "」" + (h.nick ? "\n通称: " + h.nick : ""))}"></b>`).join("");
  return `<div class="pmap ${cls}" data-layer="${placeLayer}" style="aspect-ratio:${L.w}/${L.h}"><img src="${esc(L.base)}" alt="" loading="lazy">${lab}${gate}${hat}</div>`;
}
// 実際の表示サイズを測って、地名ラベル同士・ハッチマークと重ならないように配置し直す
function declutter(map) {
  const W = map.clientWidth, H = map.clientHeight;
  if (!W || !H) return;
  const labs = [...map.querySelectorAll(".pl")];
  const hats = [...map.querySelectorAll(".ph")].map((h) => {
    const r = h.offsetWidth / 2 + 3;
    return { x: (parseFloat(h.style.left) / 100) * W, y: (parseFloat(h.style.top) / 100) * H, r };
  });
  const gates = [...map.querySelectorAll(".pg")].map((el) => {
    const w = el.offsetWidth, h = el.offsetHeight;
    const x = Math.min(W - w / 2 - 2, Math.max(w / 2 + 2, (+el.dataset.x / 100) * W));
    const y = Math.min(H - h / 2 - 2, Math.max(h / 2 + 2, (+el.dataset.y / 100) * H));
    el.style.left = (x / W) * 100 + "%"; el.style.top = (y / H) * 100 + "%";
    return { x, y, r: Math.max(w, h) / 2 + 3 };
  });
  hats.push(...gates);
  const B = labs.map((el) => ({ el, x: (+el.dataset.x / 100) * W, y: (+el.dataset.y / 100) * H, w: el.offsetWidth + 4, h: el.offsetHeight + 4 }));
  const ox = B.map((b) => b.x), oy = B.map((b) => b.y);
  for (let it = 0; it < 80; it++) {
    let moved = false;
    for (let i = 0; i < B.length; i++) {
      const a = B[i];
      for (let j = i + 1; j < B.length; j++) {
        const b = B[j];
        const dx = (a.w + b.w) / 2 - Math.abs(a.x - b.x), dy = (a.h + b.h) / 2 - Math.abs(a.y - b.y);
        if (dx <= 0 || dy <= 0) continue;
        moved = true;
        if (dy < dx * 1.4) { const s = (a.y <= b.y ? -1 : 1) * (dy / 2 + .5); a.y += s; b.y -= s; }
        else { const s = (a.x <= b.x ? -1 : 1) * (dx / 2 + .5); a.x += s; b.x -= s; }
      }
      for (const h of hats) {  // ハッチマークは動かさず、ラベル側を逃がす
        const dx = a.w / 2 + h.r - Math.abs(a.x - h.x), dy = a.h / 2 + h.r - Math.abs(a.y - h.y);
        if (dx <= 0 || dy <= 0) continue;
        moved = true;
        if (dy < dx) a.y += (a.y <= h.y ? -1 : 1) * (dy + .5); else a.x += (a.x <= h.x ? -1 : 1) * (dx + .5);
      }
      // 元の位置に少し引き戻す (遠くへ飛ばない) + 地図の内側に収める
      a.x += (ox[i] - a.x) * 0.02; a.y += (oy[i] - a.y) * 0.02;
      a.x = Math.min(W - a.w / 2, Math.max(a.w / 2, a.x));
      a.y = Math.min(H - a.h / 2, Math.max(a.h / 2, a.y));
    }
    if (!moved) break;
  }
  for (const b of B) { b.el.style.left = (b.x / W) * 100 + "%"; b.el.style.top = (b.y / H) * 100 + "%"; }
}
const mapRO = "ResizeObserver" in window ? new ResizeObserver((es) => es.forEach((e) => declutter(e.target))) : null;
function watchMaps(root = document) {
  root.querySelectorAll(".pmap").forEach((m) => { if (mapRO) mapRO.observe(m); declutter(m); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => root.querySelectorAll(".pmap").forEach(declutter));
}
function placeHTML(name, full) {
  const g = MN(name);
  if (!g) return "";
  const layers = [["all", "すべて"], ["hatch", "ハッチ"], ["base", "地下室"], ["gate", "ゲート"]];
  return `<div class="place" data-place="${esc(name)}">
    <div class="pmapwrap">${mapOverlay(g)}<button class="pzoom" data-mz="${esc(name)}" aria-label="拡大"><svg viewBox="0 0 24 24"><path d="M14 4h6v6M10 20H4v-6M20 4l-6.5 6.5M4 20l6.5-6.5"/></svg></button></div>
    <div class="seg pseg">${layers.map(([k, t]) => `<button data-layer="${k}" class="${placeLayer === k ? "on" : ""}">${t}</button>`).join("")}</div>
    <div class="pcards">
      <div class="pcard"><div class="pct"><i class="dot h"></i>ハッチ<small>タップで場所を表示 ・ チャットで選ぶ地名</small></div>
        ${g.hatches.map((h, i) => `<button class="prow" data-hi="${i}"><b>${furi(h.area)}</b>${h.nick ? `<small>通称「${esc(h.nick)}」</small>` : ""}</button>`).join("")}</div>
      ${g.basement.length ? `<div class="pcard"><div class="pct"><i class="dot b"></i>地下室<small>どちらかに出現</small></div>
        ${g.basement.map((b) => `<button class="prow" data-area="${esc(b)}"><b>${furi(b)}</b></button>`).join("")}</div>` : ""}
      ${g.tips.length ? `<div class="pcard tips">${g.tips.map((t) => `<p>${furi(t)}</p>`).join("")}</div>` : ""}
    </div>
  </div>`;
}
function renderPlaces() {
  const names = Object.keys((D.mapNames && D.mapNames.maps) || {});
  if (!names.length) return ($("#list").innerHTML = '<p class="none">地名データなし</p>');
  if (!names.includes(placeMap)) placeMap = names[0];
  $("#list").innerHTML = `<div class="mapsel">${names.map((n) => `<button class="${n === placeMap ? "on" : ""}" data-pm="${esc(n)}">${esc(n)}</button>`).join("")}</div>
    ${placeHTML(placeMap)}
    <p class="none">地名はゲーム内チャットの「エリア」タブで選べる公式名です。出典: ${esc(D.mapNames.source || "")}</p>`;
  watchMaps($("#list"));
}
// ハッチ/地下室のハイライト
function placeFocus(root, sel) {
  root.querySelectorAll(".hi").forEach((x) => x.classList.remove("hi"));
  sel.forEach((x) => x && x.classList.add("hi"));
  const m = root.querySelector(".pmap");
  if (m && m.getBoundingClientRect().top < 40) m.scrollIntoView({ behavior: "smooth", block: "start" });
}
function openMapZoom(name) {
  const g = MN(name);
  if (!g) return;
  $("#mapzoom .mzscroll").innerHTML = mapOverlay(g, "big");
  $("#mapzoom").hidden = false;
  watchMaps($("#mapzoom"));
}
function renderMaps() {
  $("#list").innerHTML = `<div class="maps">${mapList().map(mapHTML).join("")}</div>`;
}
function mapHTML(m) {
  const a = m.dadv || m.adv;
  const adv = a && ADV[a] ? `<i class="adv ${ADV[a][1]}">${ADV[a][0]}${m.dadv ? "" : "?"}</i>`
    : m.cat === "ランク外" ? '<i class="adv adv-out">ランク外</i>' : "";
  const st = cnMap(m.name);
  const cat = m.cat && m.cat !== "ランク外" ? `<small>ランク${m.cat}マップ</small>` : "";
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
function toast(msg, ms = 3500) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => (el.hidden = true), ms);
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
  if (!list || !list.length) return '<span class="none mnone">情報なし</span>';
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
    $("#detail").style.setProperty("--hero", `url("${sz(m.img, 640)}")`);
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
    watchMaps(body);
    return;
  }

  const c = D.chars[key];
  if (!c) return goBack();
  const isS = c.side === "s";
  $("#detail").style.setProperty("--hero", `url("${c.img.startsWith("gi/") ? c.img : sz(c.img, 256)}")`);
  title.innerHTML = `<img src="${esc(sz(c.img, 128))}" alt=""><div>
    <div class="nm">${esc(c.name)} <b class="tier ${c.tier}">${c.tier}</b></div>
    <span class="src" data-url="${esc(c.url)}">神ゲー攻略</span> <span class="src" data-url="${esc(c.wiki || "")}">5chWiki</span>
    ${!isS && D.counter && D.counter.h[c.name] ? `<button class="goctr top" data-goctr="${esc(c.name)}"><svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.6-3 8.2-7 10-4-1.8-7-5.4-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>対策を見る</button>` : ""}</div>`;

  const builds = [...(c.builds || []), ...extraBuilds(c)];
  const b = builds[0];
  const cs = cnChar(c.name);
  const mu = MU(c.name);
  const cnRow = (v, label) => v ? `<div class="cnrow"><span class="sl">${label}</span>
    <b>勝率 ${v.win}%</b><span>引分 ${v.draw}%</span><span>使用 ${v.use}%</span><span>BAN ${v.ban}%</span></div>` : "";
  const nsrc = mu ? new Set(["good", "bad", "goodMaps", "badMaps"].flatMap((k) => mu[k].flatMap((x) => x.src))).size : 0;
  const srcNames = Object.values((D.matchups && D.matchups.sources) || {}).map((s) => s.label).join("・");
  const muSec = mu ? `
    <div class="sec"><div class="lbl"><span><span class="good">得意</span>${isS ? "なハンター" : "なサバイバー"}</span></div>${muRow(mu.good)}</div>
    <div class="sec"><div class="lbl"><span><span class="bad">苦手</span>${isS ? "なハンター" : "なサバイバー"}</span></div>${muRow(mu.bad)}</div>` : `
    <div class="sec"><div class="lbl"><span><span class="good">得意</span>${isS ? "なハンター" : "なサバイバー"}</span></div>${row(isS ? c.goodH : c.goodS)}</div>
    <div class="sec"><div class="lbl"><span><span class="bad">苦手</span>${isS ? "なハンター" : "なサバイバー"}</span></div>${row(isS ? c.badH : c.badS)}</div>`;
  body.innerHTML = `
    ${muSec}
    ${!isS ? counterSec(c) : ""}
    <div class="sec"><div class="lbl">人格${api() && api().capture_persona ? '<button class="mini capp" data-capp title="ゲームで人格の網の画面を開いてから押すと、その画面を読み取ってこのキャラの構成として保存します">ゲーム画面から記録</button>' : ""}</div>
      ${builds.length > 1 ? `<div class="chips">${builds.map((x, i) => `<button class="chip ${i ? "" : "on"}${x.mine ? " mine" : x.srcUrl ? " vid" : ""}" data-b="${i}" title="${esc(x.title || x.name)}">${esc(x.name)}</button>`).join("")}</div>` : ""}
      <div id="build">${b ? buildHTML(b, c.side, c.personas) : '<p class="none">情報なし</p>'}</div>
    </div>
    ${mu ? `<div class="sec"><div class="lbl">マップ相性</div>
      <div class="mline"><span class="good">得意</span>${muMaps(mu.goodMaps, "g")}</div>
      <div class="mline"><span class="bad">苦手</span>${muMaps(mu.badMaps, "b")}</div></div>` : `<div class="sec"><div class="lbl">得意マップ</div>
      ${(() => { const ms = mapList().filter((m) => m[c.side].some((a) => a.name === c.name));
        return ms.length ? `<div class="mrow">${ms.map(mapHTML).join("")}</div>` : '<p class="none">情報なし</p>'; })()}</div>`}
    ${!isS ? `<div class="sec"><div class="lbl">補助特質</div>${c.traits.length ? iconRow(c.traits) : '<p class="none">情報なし</p>'}</div>` : ""}
    ${isS && c.goodS.length ? `<div class="sec"><div class="lbl">相性◎ 味方</div>${row(c.goodS)}</div>` : ""}
    <details class="more"><summary>くわしい情報（ティア評価・公式データ・出典）</summary>
      ${tierBox(c)}
      ${mu && nsrc <= 2 ? `<p class="thin">⚠ このキャラは相性情報が少なめです（情報源 ${nsrc}件）</p>` : ""}
      ${cs ? `<div class="sec cnbox"><div class="lbl">公式ランクデータ（中国版 S${esc(D.cn.char.season)}）<span class="src" data-url="${esc(D.cn.url)}">出典</span></div>
        ${cnRow(cs.all, "全段位")}${cnRow(cs.top, "最上位")}</div>` : ""}
      ${mu ? `<p class="none">アイコンの数字=一致した情報源の数。ホバー(スマホは長押し)で出典と根拠。相性の出典: ${esc(srcNames)}・マップ集計</p>` : ""}
    </details>`;
  body._builds = builds;
  body._side = c.side;
  body._personas = c.personas;
}
/* 人格テンプレ: 構成をキャラ共通のパターンに分類 */
const TPL = {
  s: [
    { k: "chase", name: "チェイス型", key: ["膝蓋腱反射", "フライホイール効果"], note: "追われても時間を稼ぐ。ほとんどのサバイバーの基本" },
    { k: "rescue", name: "救助型", key: ["危機一髪"], note: "救助に行く役。危機一髪＋中治り/癒合が定番" },
    { k: "both", name: "危機一髪＋フライホイール", key: ["危機一髪", "フライホイール効果"], note: "救助もチェイスもこなす万能型" },
    { k: "other", name: "キャラ専用", key: [], note: "解読型（弁護士・心眼）や怪力（踊り子）など" },
  ],
  h: [
    { k: "rb", name: "右下型", key: ["引き留める", "裏向きカード"], note: "通電後の逆転＋補助特質の切り替え。大多数のハンターの基本" },
    { k: "arro", name: "傲慢型", key: ["傲慢", "引き留める", "破壊欲"], note: "存在感を早くためたいハンター向け" },
    { k: "chase", name: "チェイス特化型", key: ["破壊欲", "閉鎖空間", "衝動", "狂暴"], note: "板・窓に強くして初動のチェイスを速くする" },
  ],
};
function tplOf(side, b) {
  const u = new Set(b.use || (b.perks || []).map((p) => p.name)), nm = b.name || "";
  if (side === "s") {
    if (u.has("危機一髪") && u.has("フライホイール効果")) return "both";
    if (u.has("危機一髪") || nm.includes("救助")) return "rescue";
    if (u.has("フライホイール効果") || u.has("膝蓋腱反射") || nm.includes("チェイス")) return "chase";
    return "other";
  }
  if (u.has("傲慢") || nm.includes("傲慢")) return "arro";
  if (u.has("引き留める") || u.has("裏向きカード") || nm.includes("右下")) return "rb";
  return "chase";
}
/* 人格の網: 画像から読み取った「どのマスに何ポイント」を図にする */
const DIRS = [["上", 0, -1], ["右", 1, 0], ["下", 0, 1], ["左", -1, 0]];
function webHTML(b, side, compact) {
  const L = D.personaLayout, w = b.web;
  if (!L || !w || !w.pts) return "";
  const names = L.names[side] || {}, icons = L.icons[side] || {}, pts = w.pts, uns = new Set(w.unsure || []);
  const P = L.nodes.map(([x, y]) => [x * 100, y * 100]); // 小さい単位だと文字の設定が効きすぎるので 100 倍
  const R = (i) => (L.max[i] === 0 ? 7.5 : [0, 1, 2, 3].includes(i) ? 6.8 : 5.2);
  const on = (i) => (pts[i] || 0) > 0;
  const lines = L.edges.map(([i, j]) => `<line x1="${P[i][0]}" y1="${P[i][1]}" x2="${P[j][0]}" y2="${P[j][1]}" class="${on(i) && (on(j) || j === L.center) ? "on" : ""}"/>`).join("");
  const nodes = P.map(([x, y], i) => {
    const r = R(i), n = names[i] || "", p = pts[i] || 0, mx = L.max[i];
    if (i === L.center) return `<circle cx="${x}" cy="${y}" r="${r}" class="core"/>`;
    const pk = `data-pk="${side}|${esc(n)}|${p}|${mx}"`;
    if (!p) return `<circle cx="${x}" cy="${y}" r="${r * 0.62}" class="off" ${pk}/><circle cx="${x}" cy="${y}" r="${r}" class="hit" ${pk}/>`;
    const ic = icons[n];
    return `<g class="nd" ${pk}><circle cx="${x}" cy="${y}" r="${r}" class="lit"/>
      ${ic ? `<image href="${esc(sz(ic, 64))}" x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" clip-path="circle(50%)"/>` : ""}
      <text x="${x}" y="${y + r + 5.6}" class="pt${p < mx ? " part" : ""}${uns.has(String(i)) ? " uns" : ""}">${p}/${mx}${uns.has(String(i)) ? "?" : ""}</text></g>`;
  }).join("");
  // 方向ごとの一覧 (中心からの向きで上下左右に分ける)
  const groups = DIRS.map(([lab, dx, dy]) => {
    const items = Object.keys(pts).map(Number).filter((i) => {
      const [x, y] = P[i]; return Math.abs(x) + Math.abs(y) > 1 && (dx ? Math.sign(x) === dx && Math.abs(x) >= Math.abs(y) : Math.sign(y) === dy && Math.abs(y) > Math.abs(x));
    }).sort((a, b) => Math.hypot(...P[a]) - Math.hypot(...P[b]));
    return items.length ? `<div class="wdir"><b>${lab}</b>${items.map((i) => `<span class="${pts[i] < L.max[i] ? "part" : ""}" data-pk="${side}|${esc(names[i] || "")}|${pts[i]}|${L.max[i]}">${esc(names[i] || "?")}<i>${pts[i]}/${L.max[i]}${uns.has(String(i)) ? "?" : ""}</i></span>`).join("")}</div>` : "";
  }).join("");
  const total = Object.values(pts).reduce((a, v) => a + v, 0);
  if (compact) return `<div class="webwrap ${side} mini"><svg class="web" viewBox="-112 -112 224 224" role="img" aria-label="人格の網">${lines}${nodes}</svg></div>`;
  return `<div class="webwrap ${side}"><svg class="web" viewBox="-112 -112 224 224" role="img" aria-label="人格の網">${lines}${nodes}</svg></div>
    <div class="wlist">${groups}</div>
    <p class="none wnote">合計 ${total}ポイント・ゲーム画面の画像から自動で読み取り${total !== 26 ? "（合計が26にならないため、一部のマスを読み違えている可能性があります）" : ""}${uns.size ? "。「?」のマスは数字が小さく 1/2/3 のどれか確実ではありません（元の画像で確認できます）" : ""}。マスにカーソル（スマホはタップ）で人格の効果をLv別に表示。</p>`;
}
/* 神ゲー以外の構成: 動画から読み取ったもの・自分でゲーム画面から記録したもの */
function extraBuilds(c) {
  const L = D.personaLayout, out = [];
  const ends = (w) => Object.keys(w.pts).filter((i) => [0, 1, 2, 3].includes(+i)).map((i) => L && L.names[c.side][i]).filter(Boolean);
  const V = D.personaVideos;
  if (V) for (const v of V[c.side] || []) if ((v.chars || []).includes(c.name)) {
    const s = V.sources[v.src] || {};
    out.push({ name: `${s.label || "動画"}`, title: v.name, web: v.web, use: ends(v.web), desc: `${v.name}（${s.label || ""} ${s.date || ""} の動画の画面から読み取り）`, srcUrl: s.url });
  }
  const same = (w) => (c.builds || []).find((b) => b.web && JSON.stringify(Object.entries(b.web.pts).sort()) === JSON.stringify(Object.entries(w.pts).sort()));
  for (const r of D.myPersonas || []) if (r.char === c.name) {
    const s = same(r.web);
    out.push({ name: r.name || "記録", web: r.web, use: ends(r.web), mine: r.id,
      desc: `ゲーム画面から記録（${r.date}${(r.count || 1) > 1 ? `・同じ振り方を${r.count}回記録` : ""}）${s ? `。神ゲー攻略の「${s.name}」と同じ振り方` : ""}${r.check ? "。合計が26ポイントにならないため読み取りに自信なし" : ""}` });
  }
  return out;
}
function buildHTML(b, side, personas) {
  const P = Object.fromEntries((personas || []).map((p) => [p.name, p]));
  const tpl = TPL[side].find((x) => x.k === tplOf(side, b));
  const pts = b.points || {};
  const rows = (b.use || (b.perks || []).map((p) => p.name)).map((n) => {
    const p = P[n] || (b.perks || []).find((x) => x.name === n) || { name: n };
    const pt = pts[n];
    return `<div class="prow2"><img src="${esc(sz(p.img || "", 84))}" alt="" loading="lazy"><div><b>${esc(n)}${pt ? `<i class="ppt">${pt}ポイント</i>` : ""}</b>${(p.effects || []).map((x) => `<span>${esc(x)}</span>`).join("")}</div></div>`;
  }).join("");
  const extra = Object.entries(pts).filter(([n]) => !(b.use || []).includes(n)).map(([n, v]) => `<i class="ppt">${esc(n)} ${v}ポイント</i>`).join("");
  const used = b.use || (b.perks || []).map((p) => p.name);
  const icons = used.map((n) => { const p = P[n] || (b.perks || []).find((x) => x.name === n) || {};
    const img = p.img || (D.personaLayout && D.personaLayout.icons[side] && D.personaLayout.icons[side][n]) || "";
    return `<div class="ch" title="${esc(n + (p.effects ? "\n・" + p.effects.join("\n・") : ""))}"><img src="${esc(sz(img, 84))}" alt=""><span>${esc(n)}${pts[n] ? `<i class="ppt">${pts[n]}</i>` : ""}</span></div>`; }).join("");
  const web = webHTML(b, side);
  const extraBtns = (b.srcUrl ? `<span class="src" data-url="${esc(b.srcUrl)}">元の動画</span>` : "") + (b.mine ? `<button class="mini" data-delp="${b.mine}">この記録を削除</button>` : "");
  return `${extraBtns ? `<div class="bextra">${extraBtns}</div>` : ""}${web || (b.tree ? `<img class="tree" src="${esc(b.tree)}" data-zoom="${esc(b.tree)}" alt="人格ツリー">` : "")}
    ${icons ? `<div class="row perk">${icons}</div>` : ""}
    ${tpl ? `<div class="btpl">テンプレ：<b>${esc(tpl.name)}</b></div>` : ""}
    ${b.desc || rows ? `<details class="more"><summary>この構成の説明と人格の効果</summary>
      ${b.desc ? `<p class="bdesc">${esc(b.desc).replace(/「(.+?)」/g, "<b>「$1」</b>")}</p>` : ""}
      ${extra ? `<div class="pextra">${extra}</div>` : ""}
      ${rows ? `<div class="prows">${rows}</div>` : ""}
      ${b.tree ? `<div class="lbl2">元の画像（ゲーム画面）<small>タップで拡大</small></div><img class="tree raw" src="${esc(b.tree)}" data-zoom="${esc(b.tree)}" alt="人格ツリー" loading="lazy">` : ""}</details>` : ""}`;
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
  const bs = e.target.closest("[data-bside]");
  if (bs) { begSide = bs.dataset.bside; render(); $("#list").scrollTop = 0; return; }
  const gc = e.target.closest("[data-goctr]");
  if (gc) return goCounter(gc.dataset.goctr);
  const cm = e.target.closest("[data-cmore]");
  if (cm) { const n = cm.dataset.cmore; ctrOpen.has(n) ? ctrOpen.delete(n) : ctrOpen.add(n); const y = $("#list").scrollTop; render(); $("#list").scrollTop = y; return; }
  const ct = e.target.closest("[data-ctag]");
  if (ct) { const k = ct.dataset.ctag; ctrTag = ctrTag === k ? "" : k; ctrPick = ""; return render(); }
  const cv = e.target.closest("[data-cview]");
  if (cv) { ctrView = cv.dataset.cview; render(); $("#list").scrollTop = 0; return; }
  const cp = e.target.closest("[data-cpick]");
  if (cp) { ctrPick = cp.dataset.cpick; const y = $("#list").scrollTop, x = $(".cpick").scrollLeft; render(); $("#list").scrollTop = y; $(".cpick").scrollLeft = x; return; }
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
  if (e.target.closest("[data-capp]")) {
    const key = history[history.length - 1], c = D.chars[key];
    if (!c) return;
    toast("ゲーム画面を読み取り中…", 1500);
    api().capture_persona(c.name, c.side, "").then((r) => {
      if (!r || r.error) return toast((r && r.error) || "読み取りに失敗しました", 4000);
      D.myPersonas = r.recs;
      showDetail(key, true);
      const chips = [...document.querySelectorAll("#dbody .chip[data-b]")];
      const hit = chips.find((x) => x.textContent === r.rec.name) || chips[chips.length - 1];
      hit && hit.click();
      toast(r.dup ? `同じ振り方の記録があったのでまとめました（${r.rec.name}・${r.rec.count}回目）` : `記録しました：${r.rec.name}（合計 ${r.total}ポイント）`, 3000);
    });
    return;
  }
  const dp = e.target.closest("[data-delp]");
  if (dp) {
    api().delete_persona(+dp.dataset.delp).then((recs) => { D.myPersonas = recs; showDetail(history[history.length - 1], true); toast("削除しました", 1500); });
    return;
  }
  const bb = e.target.closest("[data-b]");
  if (bb) {
    document.querySelectorAll("#dbody .chip").forEach((x) => x.classList.toggle("on", x === bb));
    $("#build").innerHTML = buildHTML($("#dbody")._builds[+bb.dataset.b], $("#dbody")._side, $("#dbody")._personas);
    return;
  }
  const pm = e.target.closest("[data-pm]");
  if (pm) { placeMap = pm.dataset.pm; renderPlaces(); return pm.scrollIntoView({ inline: "center", block: "nearest" }); }
  if (e.target.closest(".mzclose")) return ($("#mapzoom").hidden = true);
  const mz = e.target.closest("[data-mz]");
  if (mz) return openMapZoom(mz.dataset.mz);
  const ly = e.target.closest(".pseg [data-layer]");
  if (ly) {
    placeLayer = ly.dataset.layer;
    const root = ly.closest(".place");
    root.querySelectorAll(".pseg button").forEach((b) => b.classList.toggle("on", b === ly));
    root.querySelector(".pmap").dataset.layer = placeLayer;
    return;
  }
  const hi = e.target.closest(".place [data-hi], .place [data-area]");
  if (hi) {
    const root = hi.closest(".place");
    const g = MN(root.dataset.place);
    if (hi.dataset.hi != null) {
      const h = g.hatches[+hi.dataset.hi];
      return placeFocus(root, [root.querySelector(`.ph[data-hi="${hi.dataset.hi}"]`), root.querySelector(`.pl[data-area="${CSS.escape(h.area)}"]`), root.querySelector(`.prow[data-hi="${hi.dataset.hi}"]`)]);
    }
    return placeFocus(root, [root.querySelector(`.pl[data-area="${CSS.escape(hi.dataset.area)}"]`), hi.classList.contains("prow") ? hi : root.querySelector(`.prow[data-area="${CSS.escape(hi.dataset.area)}"]`)]);
  }
  if (e.target.closest(".pmapwrap .pmap")) return openMapZoom(e.target.closest(".place").dataset.place);
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
    if (!$("#mapzoom").hidden) $("#mapzoom").hidden = true;
    else if (!$("#calib-view").hidden) $("#calib-view").hidden = true;
    else if (!$("#zoom").hidden) $("#zoom").hidden = true;
    else if (!$("#detail").hidden) goBack();
  }
  if (e.key === "/" && document.activeElement !== $("#q")) { e.preventDefault(); $("#q").focus(); }
});
$("#pin").addEventListener("click", () => {
  const on = !$("#pin").classList.contains("on");
  $("#pin").classList.toggle("on", on);
  api() && api().set_on_top(on);
  toast(`最前面に固定：${on ? "オン" : "オフ"}`, 1500);
});
$("#reload").addEventListener("click", () => api() && api().refresh());
