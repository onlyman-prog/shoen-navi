"""iPhone 用 Web アプリ (PWA) を site/ に組み立てる。

    python scraper.py          # data/cache.json を最新にする (GitHub Actions では毎日)
    python tools/build_pwa.py  # site/ を作る -> GitHub Pages で公開

パソコン版と同じ web/ の画面 (app.js / style.css) を使い、pwa.js で Python API を置き換える。
"""
import hashlib, json, shutil, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = ROOT / "site"
VER = None


def key(name):  # vision.key と同じ
    return hashlib.md5(name.encode()).hexdigest()[:12]


def main():
    global VER
    data = json.loads((ROOT / "data" / "cache.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for f in OUT.iterdir():  # フォルダごと消すと使用中で失敗することがあるので中身だけ消す
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    # 画像: ゲーム画面から集めたキャラ画像・地名ガイド
    for sub in ("gi", "mapnames"):
        if (WEB / sub).exists():
            shutil.copytree(WEB / sub, OUT / sub, ignore=shutil.ignore_patterns("*.json"))
    for c in data["chars"].values():
        f = OUT / "gi" / f"{key(c['name'])}.png"
        if f.exists():
            c["gameImg"] = f"gi/{f.name}"
    data["beginner"] = json.loads((ROOT / "data" / "beginner.json").read_text(encoding="utf-8"))
    data["tiersExtra"] = json.loads((ROOT / "data" / "tiers_extra.json").read_text(encoding="utf-8"))
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    VER = hashlib.md5((WEB / "app.js").read_bytes() + (WEB / "style.css").read_bytes()).hexdigest()[:8]
    for f in ("app.js", "style.css", "pwa.js", "sw.js"):
        shutil.copy(WEB / f, OUT / f)
    # アイコン (OS が角を丸めるので角丸なしの版から作る)
    src = Image.open(WEB / "icon-full.png").convert("RGB")
    for s, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        src.resize((s, s), Image.LANCZOS).save(OUT / name)
    shutil.copy(WEB / "icon.png", OUT / "icon.png")
    (OUT / "manifest.webmanifest").write_text(json.dumps({
        "name": "荘園手記 — Manor Notes", "short_name": "荘園手記", "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#14161c", "theme_color": "#14161c", "lang": "ja",
        "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    # index.html: iPhone 用の meta と pwa.js を差し込む
    t = (WEB / "index.html").read_text(encoding="utf-8")
    head = ('<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="robots" content="noindex, nofollow">\n'
            '<meta name="apple-mobile-web-app-capable" content="yes">\n'
            '<meta name="mobile-web-app-capable" content="yes">\n'
            '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
            '<meta name="apple-mobile-web-app-title" content="荘園手記">\n'
            '<meta name="theme-color" content="#14161c">\n'
            '<link rel="manifest" href="manifest.webmanifest">\n'
            '<link rel="apple-touch-icon" href="apple-touch-icon.png">\n'
            f'<link rel="stylesheet" href="pwa.css?v={VER}">\n')
    import re
    t = re.sub(r'<meta name="viewport"[^>]*>\s*', "", t)
    t = t.replace("</head>", head + "</head>", 1)
    t = re.sub(r'(href="style\.css)(\?v=[^"]*)?"', rf'\1?v={VER}"', t)
    t = re.sub(r'<script src="app\.js(\?v=[^"]*)?"></script>',
               f'<script src="pwa.js?v={VER}"></script>\n<script src="app.js?v={VER}"></script>', t)
    (OUT / "index.html").write_text(t, encoding="utf-8")
    (OUT / "pwa.css").write_text(PWA_CSS, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    n = sum(1 for _ in OUT.rglob("*") if _.is_file())
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"site/ ok: {n} files, {size:.1f} MB, data {data.get('fetched')}")


# iPhone 向けの見た目調整 (パソコン専用ボタンを隠す・ノッチ対応・タップしやすく)
PWA_CSS = """
/* パソコン専用のボタンを隠す */
.pwa #pin, .pwa #readnow, .pwa #calib { display: none !important; }
.pwa body { -webkit-text-size-adjust: 100%; overscroll-behavior-y: none;
  padding: env(safe-area-inset-top) env(safe-area-inset-right) calc(58px + env(safe-area-inset-bottom)) env(safe-area-inset-left); }
.pwa input, .pwa select { font-size: 16px; }
.pwa .ch, .pwa .mchip, .pwa button, .pwa .pl, .pwa .ph { -webkit-touch-callout: none; -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
/* タブは画面下 (親指で押しやすい iOS 風) */
.pwa header { min-height: 44px; backdrop-filter: none; -webkit-backdrop-filter: none; background: var(--bg); }
.pwa header::before { content: "荘園手記"; flex: 1; padding-left: 14px; font: 700 18px/1 var(--serif); letter-spacing: .14em;
  background: linear-gradient(180deg, #fff, var(--gold1) 50%, var(--gold2)); -webkit-background-clip: text; background-clip: text; color: transparent; }
.pwa #tabs { position: fixed; left: 0; right: 0; bottom: 0; z-index: 7; flex: none;
  background: rgba(14, 16, 21, .9); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid var(--line); padding: 4px 6px env(safe-area-inset-bottom); }
.pwa #tabs button { font-size: 10px; padding: 6px 0 4px; gap: 3px; }
.pwa #tabs button svg { width: 22px; height: 22px; }
.pwa #tabs button.on::after { display: none; }
.pwa #tabs button.on svg { filter: drop-shadow(0 0 6px rgba(220,189,124,.45)); }
.pwa footer { border-top: 0; text-align: center; }
.pwa #detail { padding-top: env(safe-area-inset-top); }
.pwa #dbody { padding-bottom: calc(78px + env(safe-area-inset-bottom)); }
.pwa #mapzoom .mzscroll { padding-top: calc(60px + env(safe-area-inset-top)); }
#pwatip { position: fixed; left: 12px; right: 12px; bottom: calc(70px + env(safe-area-inset-bottom)); z-index: 99;
  background: #222632; color: #fff; border: 1px solid #343a48; border-radius: 12px; padding: 10px 12px;
  font-size: 13px; line-height: 1.5; white-space: pre-line; box-shadow: 0 8px 28px #0009;
  opacity: 0; transform: translateY(10px); transition: .15s; pointer-events: none; }
#pwatip.on { opacity: 1; transform: none; }
"""

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
