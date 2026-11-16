"""神ゲー攻略(kamigame.jp)から第五人格のキャラ情報を取得して data/cache.json に保存する。

単体実行:  python scraper.py
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://kamigame.jp"
URLS = {
    "survivor_list": "/identity5/page/377796891347269278.html",
    "hunter_list": "/identity5/page/377796689685175060.html",
    "survivor_tier": "/identity5/page/379354371411968981.html",
    "hunter_tier": "/identity5/page/379360769688515184.html",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IdVHelper/1.0"
DATA_DIR = Path(__file__).parent / "data"
CACHE = DATA_DIR / "cache.json"


def fetch(path, retries=2):
    url = path if path.startswith("http") else BASE + path
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == retries:
                raise
            time.sleep(1.5)


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


# <a href="/identity5/page/ID.html"> <picture>…<img src=URL alt="第五人格_名前">…</picture><br>名前</a>
LINK_RE = re.compile(
    r'<a href="(/identity5/page/\d+\.html)">\s*<picture>.*?<img src="([^"]+)"[^>]*alt="([^"]*)".*?</picture>(.*?)</a>',
    re.S,
)


def links(fragment):
    out, seen = [], set()
    for href, img, alt, label in LINK_RE.findall(fragment):
        name = clean(label) or alt.replace("第五人格_", "")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "url": href, "img": img})
    return out


def sections(page, level):
    """{見出しテキスト: そのセクションのHTML} を返す (level=2 or 3)."""
    out = {}
    pat = re.compile(rf'<h{level} id="[^"]*">(.*?)</h{level}>', re.S)
    ms = list(pat.finditer(page))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(page)
        # 上位見出しが来たらそこで打ち切る
        stop = re.search(rf"<h[1-{level - 1}] ", page[m.end():end]) if level > 2 else None
        if stop:
            end = m.end() + stop.start()
        out[clean(m.group(1))] = page[m.end():end]
    return out


def first_img(fragment):
    m = re.search(r'<img src="([^"]+)"', fragment)
    return m.group(1) if m else None


def parse_list(page):
    i = page.find("table_of_contents")
    chars = links(page[i:])
    # 関連リンク等の重複を避けるため、一覧テーブル(fixed_table)内だけを見る
    tables = re.findall(r'<table class="fixed_table">.*?</table>', page, re.S)
    if tables:  # キャラ数が最多の表 = キャラ一覧 (他はガイド等のナビ)
        chars = max((links(t) for t in tables), key=len)
    return chars


def parse_tier(page, side):
    key = "最強サバイバーランキング" if side == "s" else "最強ハンターランキング"
    i = page.find(f'<h2 id="{key}">')
    j = page.find("<h2", i + 10)
    tiers = {}
    for tb in page[i:j].split("<table")[1:]:
        alts = re.findall(r'alt="([^"]*)"', tb)
        if not alts:
            continue
        tier = alts[0]
        for a in alts[1:]:
            tiers[a.replace("第五人格_", "")] = tier
    m = re.search(r'dateModified" datetime="(\d{4})-(\d\d)-(\d\d)', page)
    return tiers, ("/".join(m.groups()) if m else "")


def parse_char(page):
    h2 = sections(page, 2)
    h3 = sections(page, 3)
    d = {"builds": [], "traits": [], "goodS": [], "goodH": [], "maps": []}

    for title, body in h2.items():
        if title.endswith("おすすめ人格構成"):
            for t3, b3 in sections(body, 3).items():
                if "補助特質" in t3:
                    continue
                perks = [{"name": l["name"], "img": l["img"]} for l in links(b3)]
                d["builds"].append({"name": re.sub(r"おすすめ|人格|構成", "", t3) or "おすすめ", "tree": first_img(b3), "perks": perks})

    for title, body in h3.items():
        if "おすすめの補助特質" in title:
            d["traits"] = [{"name": l["name"], "img": l["img"]} for l in links(body)]
        elif title == "相性の良いサバイバー":
            d["goodS"] = [l["name"] for l in links(body)]
        elif title == "相性の良いハンター":
            d["goodH"] = [l["name"] for l in links(body)]
        elif title == "相性の良いマップ":
            d["maps"] = [{"name": l["name"], "img": l["img"], "url": l["url"]} for l in links(body)]
    return d


def norm(name):
    return re.sub(r"[「」『』\s]", "", name)


WIKI = "https://wikiwiki.jp/identity5ch/"

# wiki本文(文章)にある「BANされなかった」系の傾向は表になっていないので固定で持つ
EXTRA_RULES = [
    {"missing": "占い師", "hunters": ["蝋人形師", "漁師", "破輪"], "w": 0.6,
     "note": "占い師がBANされない→占い師メタ"},
    {"missing": "傭兵", "hunters": ["芸者", "隠者", "夜の番人"], "w": 0.6,
     "note": "傭兵がBANされない→傭兵メタ"},
]


def parse_ban_rules(page, survivors, hunters):
    """wikiwiki ランク戦ページの「BANされるキャラからどんなハンターが来るか」表を解析。"""
    i = page.find("BANされるキャラからどんなハンターが来るか")
    if i < 0:
        return []
    j = page.find("</ul>", i)
    sn = {norm(n): n for n in survivors}
    hn = {norm(n): n for n in hunters}
    rules = []
    for th, td in re.findall(r"<tr><th>(.*?)</th><td>(.*?)</td></tr>", page[i:j], re.S):
        bans = [sn[norm(x)] for x in re.split(r"<br[^>]*>", re.sub(r"BAN", "", th))
                if norm(clean(x)) in sn]
        if not bans:
            continue
        hs = {}
        for seg in re.split(r"<br[^>]*>|。", td):
            text = clean(seg)
            w = 2.0 if re.search(r"ほぼ|高確率", text) else 0.6 if re.search(r"可能性|場合もある", text) else 1.0
            excl = text.split("以外")[0] if "以外" in text else ""
            for t in re.findall(r'title="([^"]+)"', seg):
                h = hn.get(norm(t))
                if h and norm(t) not in norm(excl):
                    hs[h] = max(hs.get(h, 0), w)
        if hs:
            rules.append({"bans": bans, "hunters": hs, "note": clean(td)[:60]})
    return rules


def build(progress=None, workers=4):
    """全データを取得して dict を返す。progress(done, total, msg) を随時呼ぶ。"""
    def p(done, total, msg):
        if progress:
            progress(done, total, msg)

    p(0, 1, "一覧を取得中")
    with ThreadPoolExecutor(workers) as ex:
        sl, hl, st, ht = ex.map(fetch, [URLS["survivor_list"], URLS["hunter_list"],
                                         URLS["survivor_tier"], URLS["hunter_tier"]])
    survivors = parse_list(sl)
    hunters = parse_list(hl)
    s_tier, s_upd = parse_tier(st, "s")
    h_tier, h_upd = parse_tier(ht, "h")

    # 一覧にあってティア表にない＝未実装予告キャラは除外しない(NEW表示用)が、tierは"?"
    def tier_of(name, table):
        n = norm(name)
        for k, v in table.items():
            if norm(k) == n:
                return v
        return "?"

    allc = [("s", c) for c in survivors] + [("h", c) for c in hunters]
    total = len(allc)
    done = 0
    result = {}

    def work(item):
        side, c = item
        try:
            info = parse_char(fetch(c["url"]))
        except Exception as e:  # 1キャラ失敗しても続行
            info = {"error": str(e)}
        return side, c, info

    with ThreadPoolExecutor(workers) as ex:
        for side, c, info in ex.map(work, allc):
            done += 1
            p(done, total, c["name"])
            result[c["name"]] = {
                "name": c["name"], "side": side, "img": c["img"],
                "url": BASE + c["url"],
                "tier": tier_of(c["name"], s_tier if side == "s" else h_tier),
                **info,
            }

    # 名前ゆれ(「」有無)を正規化して参照を一致させる
    canon = {norm(n): n for n in result}
    for c in result.values():
        for k in ("goodS", "goodH"):
            c[k] = [canon.get(norm(x), x) for x in c.get(k, [])]

    # 逆引き: 苦手 = 相手側ページで「相性が良い」と書かれている
    for c in result.values():
        c["badH"], c["badS"] = [], []
    for c in result.values():
        if c["side"] == "h":
            for s in c.get("goodS", []):
                if s in result:
                    result[s]["badH"].append(c["name"])
        else:
            for h in c.get("goodH", []):
                if h in result:
                    result[h]["badS"].append(c["name"])

    # マップ逆引き
    maps = {}
    for c in result.values():
        for m in c.get("maps", []):
            e = maps.setdefault(m["name"], {"name": m["name"], "img": m["img"],
                                            "url": BASE + m["url"], "s": [], "h": []})
            e[c["side"]].append(c["name"])

    # wikiwiki: BAN→ハンター傾向
    ban_rules, wiki_upd = [], ""
    try:
        wp = fetch(WIKI + urllib.parse.quote("ランク戦"))
        ban_rules = parse_ban_rules(wp, [c["name"] for c in survivors], [c["name"] for c in hunters])
        m = re.search(r"Last-modified:\s*([0-9-]+)", wp)
        wiki_upd = m.group(1) if m else ""
    except Exception:
        pass
    for c in result.values():
        c["wiki"] = WIKI + "?cmd=search&word=" + urllib.parse.quote(norm(c["name"]))

    # マップ別の相性(神ゲー攻略・5ch攻略Wiki・YouTube等の集計)
    p(total, total, "マップ情報")
    try:
        import mapdata
        map_info = mapdata.build([c["name"] for c in survivors], [c["name"] for c in hunters])
        _ex = mapdata.load_extra()
        map_sources = {"list": _ex.get("sources", {}), "proMeta": _ex.get("proMeta", {}), "note": _ex.get("mapNote", "")}
    except Exception:
        map_info, map_sources = {}, {}

    # 中国版公式ランク戦データ(マップ別勝率・キャラ別勝率/使用率/BAN率)
    try:
        import cnstats
        cn = cnstats.build()
    except Exception as e:
        cn = {"error": str(e)}

    # キャラ相性・得意/苦手マップ (多言語ソース集計)
    try:
        import matchups
        mu = matchups.build(result, map_info)
    except Exception as e:
        mu = {"error": str(e)}

    # マップ地名ガイド (画像は tools/make_mapnames.py で生成済み)
    try:
        here = Path(__file__).resolve().parent
        mn_def = json.loads((here / "data" / "mapnames.json").read_text(encoding="utf-8"))
        mn_info = json.loads((here / "web" / "mapnames" / "info.json").read_text(encoding="utf-8"))
        map_names = {"source": mn_def.get("_source", ""), "maps": {
            v["name"]: {"key": k, "img": f"mapnames/{k}.jpg", "hatches": mn_info[k]["hatches"], "layout": mn_info[k], "tips": v.get("tips", []),
                        "basement": v.get("basement", []), "areas": [l[0] for l in v["labels"]]}
            for k, v in mn_def.items() if not k.startswith("_") and k in mn_info}}
    except Exception as e:
        map_names = {"error": str(e)}

    return {
        "cn": cn,
        "matchups": mu,
        "mapNames": map_names,
        "mapInfo": map_info,
        "mapSources": map_sources,
        "banRules": ban_rules,
        "extraRules": EXTRA_RULES,
        "wiki": {"name": "5ch攻略Wiki", "url": WIKI + urllib.parse.quote("ランク戦"), "updated": wiki_upd},
        "fetched": time.strftime("%Y-%m-%d %H:%M"),
        "source": {"name": "神ゲー攻略", "url": BASE + "/identity5/index.html",
                   "tierUpdated": {"s": s_upd, "h": h_upd}},
        "chars": result,
        "order": {"s": [c["name"] for c in survivors], "h": [c["name"] for c in hunters]},
        "maps": maps,
    }


def load_cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cache(data):
    DATA_DIR.mkdir(exist_ok=True)
    old = load_cache()
    today = time.strftime("%Y-%m-%d")
    limit = time.strftime("%Y-%m-%d", time.localtime(time.time() - 14 * 86400))
    for n, c in data["chars"].items():
        # 初回取得時は全員 firstSeen="" (NEWなし)。以後、新規に現れたキャラは14日間NEW
        prev = (old or {}).get("chars", {}).get(n)
        c["firstSeen"] = prev.get("firstSeen", "") if prev else (today if old else "")
        c["isNew"] = bool(c["firstSeen"]) and c["firstSeen"] >= limit
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = build(lambda a, b, m: print(f"\r{a}/{b} {m}      ", end="", flush=True))
    save_cache(d)
    print()
    print("survivors", len(d["order"]["s"]), "hunters", len(d["order"]["h"]), "maps", len(d["maps"]))
