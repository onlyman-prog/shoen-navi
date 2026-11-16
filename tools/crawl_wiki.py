"""5ch攻略wiki のキャラページ/対策ページを取得して data/wikicache に保存する (3秒間隔)。"""
import hashlib, json, os, time, urllib.parse, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "wikicache")
os.makedirs(CACHE, exist_ok=True)
d = json.load(open(os.path.join(ROOT, "data", "cache.json"), encoding="utf-8"))
# wikiwiki 上の表記
FIX = {"「囚人」": "｢囚人｣"}
names = list(d["chars"])
pages = []
for n in names:
    w = n.replace("「", "").replace("」", "") if n not in ("「囚人」",) else n
    pages.append((n, "main", n))
    pages.append((n, "taisaku", n.replace("「", "").replace("」", "") + "の対策"))
for n, kind, title in pages:
    fn = f"{CACHE}/{kind}_{hashlib.md5(n.encode()).hexdigest()[:6]}_{n.strip('「」')}.html"
    if os.path.exists(fn) and os.path.getsize(fn) > 5000:
        continue
    cands = [title, title.replace("「", "｢").replace("」", "｣"), title.strip("「」")] if kind == "main" else [title]
    for t in cands:
        ok = False
        for i in range(5):
            try:
                req = urllib.request.Request("https://wikiwiki.jp/identity5ch/" + urllib.parse.quote(t), headers={"User-Agent": UA})
                s = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
                if "このページは存在しません" in s or 'id="body"' not in s:
                    break
                open(fn, "w", encoding="utf-8").write(s); ok = True; break
            except urllib.error.HTTPError as e:
                if e.code == 404: break
                time.sleep(20 * (i + 1))
            except Exception:
                time.sleep(10)
        time.sleep(3)
        if ok: break
    print(kind, n, "ok" if ok else "NG", flush=True)
