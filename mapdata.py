"""マップごとの相性の良いキャラを複数ソースから集める。

自動取得(起動時に更新): 神ゲー攻略のマップページ / 5ch攻略Wiki(wikiwiki)のマップページ
手動調査(固定): data/maps_extra.json  … YouTube・X など自動取得できないソースのまとめ
"""
import html
import json
import time
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import scraper

KAMI_MAPS = {
    "軍需工場": "/identity5/page/389510584544064400.html",
    "赤の教会": "/identity5/page/425466826261045674.html",
    "聖心病院": "/identity5/page/423017882767591418.html",
    "湖景村": "/identity5/page/431124319653918253.html",
    "月の河公園": "/identity5/page/432302584372397344.html",
    "レオの思い出": "/identity5/page/433600440207156721.html",
    "永眠町": "/identity5/page/436060644869982740.html",
    "中華街": "/identity5/page/436637878290801505.html",
    "罪の森": "/identity5/page/438204837683801283.html",
    "クレイバーグ競馬場": "/identity5/page/440517321342119203.html",
    "ホワイトサンド精神病院": "/identity5/page/442280295945759908.html",
    "黄金の石窟": "/identity5/page/442291240713624988.html",
}
EXTRA = Path(__file__).parent / "data" / "maps_extra.json"


def _norm(n):
    return re.sub(r"[「」｢｣『』\s]", "", n)


def _text(fragment):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", fragment, flags=re.S)
    t = re.sub(r"<(br|/p|/tr|/li|/div|/td)[^>]*>", "\n", t)
    return html.unescape(re.sub(r"<[^>]+>", "", t))


def _section(page, title, level=3):
    """見出し title から次の同レベル以上の見出しまで。"""
    pat = re.escape(title).replace("の良い", "[のが]良い")
    m = re.search(rf"<h{level}[^>]*>(?:(?!</h{level}>).)*{pat}(?:(?!</h{level}>).)*</h{level}>", page, re.S)
    if not m:
        return ""
    rest = page[m.end():]
    e = re.search(rf"<h[1-{level}][ >]", rest)
    return rest[:e.start()] if e else rest


def _names_with_reason(fragment, names):
    """断片中に出てくるキャラ名(リンクのtitle/alt/本文)と、その行の短い説明。"""
    canon = {_norm(n): n for n in names}
    found = {}
    # リンク・画像の名前
    for t in re.findall(r'(?:title|alt)="(?:第五人格_)?([^"]+)"', fragment):
        n = canon.get(_norm(t))
        if n and n not in found:
            found[n] = ""
    # 本文の行から理由を拾う
    for line in _text(fragment).split("\n"):
        line = line.strip(" ・|　")
        if not line:
            continue
        for key, n in canon.items():
            if key and key in _norm(line):
                if n not in found:
                    found[n] = ""
                rest = _norm(line).replace(key, "", 1).strip("|：:・ ")
                if rest and not found[n]:
                    found[n] = rest[:40]
    return found


def fetch_kami(mp, path, survivors, hunters):
    page = scraper.fetch(path)
    s = _names_with_reason(_section(page, "相性の良いサバイバー"), survivors)
    h = _names_with_reason(_section(page, "相性の良いハンター"), hunters)
    # マップのバナー画像 (alt="第五人格_マップ名", 512x256)
    m = re.search(rf'<img src="(https://lh3[^"]+)"[^>]*alt="第五人格_{re.escape(mp)}\s*"[^>]*width="512" height="256"', page)
    return {"s": s, "h": h, "url": scraper.BASE + path, "img": m.group(1) if m else ""}


def fetch_wiki(mp, survivors, hunters):
    url = scraper.WIKI + urllib.parse.quote(mp)
    page = None
    for i in range(4):  # wikiwikiは連続アクセスで429になるので間をあけて再試行
        try:
            page = scraper.fetch(url, retries=0)
            break
        except Exception:
            time.sleep(3 * (i + 1))
    if page is None:
        raise RuntimeError("wiki fetch failed")
    s = _names_with_reason(_section(page, "相性の良いサバイバー"), survivors)
    h = _names_with_reason(_section(page, "相性の良いハンター"), hunters)
    return {"s": s, "h": h, "url": url}


def load_extra():
    try:
        return json.loads(EXTRA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build(survivors, hunters):
    """{map: {"sources": {...}, "s": [{name, n, src, why}], "h": [...]}}"""
    out = {mp: {"sources": {}} for mp in KAMI_MAPS}

    def kami(mp):
        try:
            return mp, fetch_kami(mp, KAMI_MAPS[mp], survivors, hunters)
        except Exception:
            return mp, None

    with ThreadPoolExecutor(4) as ex:
        for mp, r in ex.map(kami, KAMI_MAPS):
            if r:
                out[mp]["sources"]["神ゲー攻略"] = r
                out[mp]["img"] = r.get("img", "")
    for mp in KAMI_MAPS:  # wikiwikiは1件ずつ
        try:
            out[mp]["sources"]["5ch攻略Wiki"] = fetch_wiki(mp, survivors, hunters)
        except Exception:
            pass
        time.sleep(1.0)
    # YouTube・X などの手動調査分
    extra = load_extra()
    for mp, srcs in extra.get("maps", {}).items():
        e = out.setdefault(mp, {"sources": {}})
        for src, d in srcs.items():
            if src == "_info":
                e.update(d)  # 有利陣営・特徴など
            else:
                e["sources"][src] = {"s": d.get("s", {}), "h": d.get("h", {}), "url": d.get("url", "")}

    # 取得に失敗したソースは前回のデータを使う(wikiwikiは時々アクセス制限がかかる)
    old = (scraper.load_cache() or {}).get("mapInfo", {})
    for mp, e in out.items():
        for src, d in (old.get(mp, {}).get("sources", {})).items():
            if src not in e["sources"] and src in ("神ゲー攻略", "5ch攻略Wiki"):
                e["sources"][src] = d
        if not e.get("img") and old.get(mp, {}).get("img"):
            e["img"] = old[mp]["img"]

    # ソース横断で集計: 何ソースで推されているか
    for mp, e in out.items():
        for side in ("s", "h"):
            agg = {}
            for src, d in e["sources"].items():
                for n, why in d.get(side, {}).items():
                    a = agg.setdefault(n, {"name": n, "n": 0, "src": [], "why": ""})
                    a["n"] += 1
                    a["src"].append(src)
                    if why and not a["why"]:
                        a["why"] = why
            e[side] = sorted(agg.values(), key=lambda a: -a["n"])
    cat = extra.get("mapCategory", {})
    for mp, e in out.items():
        e["cat"] = next((k for k, v in cat.items() if mp in v), "")
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = scraper.load_cache()
    r = build(d["order"]["s"], d["order"]["h"])
    for mp, e in r.items():
        print(mp, {k: len(v.get("s", {})) for k, v in e["sources"].items()},
              {k: len(v.get("h", {})) for k, v in e["sources"].items()})
        print("  S:", [(a["name"], a["n"]) for a in e["s"]][:8])
        print("  H:", [(a["name"], a["n"]) for a in e["h"]][:8])
