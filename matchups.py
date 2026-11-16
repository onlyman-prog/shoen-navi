"""キャラ相性・得意/苦手マップを複数ソースから集計する。

ソース:
  kami   神ゲー攻略 (キャラページの相性欄・得意マップ)
  wiki   5ch攻略wiki (キャラページ・対策ページ本文から抽出: tools/mine_wiki.py -> data/matchups_wiki.json)
  reddit 英語圏 Reddit の相性表とコメント (2024-12〜2025-02)
  cn163  中国 網易号のまとめ (2021)
  omc    YouTube OMC「全ハンター/全サバイバー長所短所」(2026-03)
  map    マップ別おすすめ集計 (mapdata: 神ゲー/wiki/YouTube 等)
A が B に強い => B は A に弱い、として両方向に登録する。
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
LABEL = {"kami": "神ゲー", "wiki": "5chWiki", "reddit": "Reddit(英)", "cn163": "中国記事", "omc": "YouTube", "map": "マップ集計"}


def _load(name):
    p = DATA / name
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def build(chars, map_info=None):
    extra = _load("matchups_extra.json")
    wiki = _load("matchups_wiki.json")
    side = {n: c["side"] for n, c in chars.items()}
    res = {n: {"good": {}, "bad": {}, "goodMaps": {}, "badMaps": {}} for n in chars}

    def add(a, b, src, why=""):
        """a が b に強い"""
        if a not in res or b not in res or side[a] == side[b]:
            return
        for x, y, k in ((a, b, "good"), (b, a, "bad")):
            e = res[x][k].setdefault(y, {"src": [], "why": []})
            if src not in e["src"]:
                e["src"].append(src)
            if why and why not in e["why"] and len(e["why"]) < 3:
                e["why"].append(why)

    def add_map(c, mp, good, src, why=""):
        if c not in res:
            return
        e = res[c]["goodMaps" if good else "badMaps"].setdefault(mp, {"src": [], "why": []})
        if src not in e["src"]:
            e["src"].append(src)
        if why and why not in e["why"] and len(e["why"]) < 2:
            e["why"].append(why)

    # 神ゲー攻略
    for n, c in chars.items():
        for o in c.get("goodH", []) + c.get("goodS", []):
            add(n, o, "kami")
        for m in c.get("maps", []):
            add_map(n, m["name"], True, "kami")
    # 5chWiki 抽出
    for n, rows in wiki.items():
        for r in rows:
            if "opp" in r:
                (add(n, r["opp"], "wiki", r["s"]) if r["pol"] == "+" else add(r["opp"], n, "wiki", r["s"]))
            elif "map" in r:
                add_map(n, r["map"], r["pol"] == "+", "wiki", r["s"])
    # Reddit / 中国記事 (ハンター: そのハンターに強いサバ)
    for src in ("reddit", "cn163"):
        for h, ss in extra.get(src, {}).items():
            for s in ss:
                add(s, h, src)
    for h, ss in extra.get("redditHunterGood", {}).items():
        for s in ss:
            add(h, s, "reddit")
    # YouTube OMC
    omc = extra.get("omc", {})
    for h, (ss, why) in omc.get("hunterWeak", {}).items():
        for s in ss:
            add(s, h, "omc", why)
    for h, (ss, why) in omc.get("hunterStrong", {}).items():
        for s in ss:
            add(h, s, "omc", why)
    for s, (hs, why) in omc.get("survivorWeak", {}).items():
        for h in hs:
            add(h, s, "omc", why)
    for s, (hs, why) in omc.get("survivorStrong", {}).items():
        for h in hs:
            add(s, h, "omc", why)
    for c, v in omc.get("maps", {}).items():
        for mp in v.get("good", []):
            add_map(c, mp, True, "omc", v.get("why", ""))
        for mp in v.get("bad", []):
            add_map(c, mp, False, "omc", v.get("why", ""))
    # マップ集計 (2ソース以上で推されているもの)
    for mp, e in (map_info or {}).items():
        for sd in ("s", "h"):
            for a in e.get(sd, []):
                if a.get("n", 0) >= 2:
                    add_map(a["name"], mp, True, "map", a.get("why", ""))

    def pack(d, sub=None):
        out = []
        for k, e in d.items():
            if sub and k in sub:
                continue
            out.append({"name": k, "n": len(e["src"]), "src": [LABEL[s] for s in e["src"]], "why": e["why"]})
        return sorted(out, key=lambda x: -x["n"])

    final = {}
    for n, r in res.items():
        # 同じ相手が得意/苦手の両方に出たら、ソース数が多い方だけ残す (同数なら両方消す)
        g, b = r["good"], r["bad"]
        for o in set(g) & set(b):
            if len(g[o]["src"]) > len(b[o]["src"]):
                del b[o]
            elif len(b[o]["src"]) > len(g[o]["src"]):
                del g[o]
            else:
                del g[o], b[o]
        gm, bm = r["goodMaps"], r["badMaps"]
        for o in set(gm) & set(bm):
            if len(gm[o]["src"]) >= len(bm[o]["src"]):
                del bm[o]
            else:
                del gm[o]
        final[n] = {"good": pack(g), "bad": pack(b), "goodMaps": pack(gm), "badMaps": pack(bm)}
    return {"sources": extra.get("_sources", {}), "chars": final}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = json.load(open(DATA / "cache.json", encoding="utf-8"))
    r = build(d["chars"], d.get("mapInfo"))
    for n in sys.argv[1:] or ["傭兵", "リッパー", "祭司", "「使徒」"]:
        c = r["chars"][n]
        print("■", n)
        for k in ("good", "bad"):
            print(" ", k, [(x["name"], x["n"]) for x in c[k][:10]])
        print("  maps+", [(x["name"], x["n"]) for x in c["goodMaps"]], "maps-", [(x["name"], x["n"]) for x in c["badMaps"]])
