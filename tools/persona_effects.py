"""5ch攻略wiki の「内在人格-サバイバー/ハンター」から人格ごとの効果文を取り出し、
Lv1/2/3 の値 (a/b/c 表記) を展開して data/persona_effects.json に保存する。
元ページは data/wikicache/persona_s.html / persona_h.html (無ければ取得)。"""
import html, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PAGES = {"s": "内在人格-サバイバー", "h": "内在人格-ハンター"}


def page(side):
    f = ROOT / "data" / "wikicache" / f"persona_{side}.html"
    if not f.exists():
        req = urllib.request.Request("https://wikiwiki.jp/identity5ch/" + urllib.parse.quote(PAGES[side]), headers={"User-Agent": UA})
        f.write_text(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"), encoding="utf-8")
        time.sleep(3)
    return f.read_text(encoding="utf-8")


def text(h):
    h = h[h.find('id="body"'):]
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    h = re.sub(r"<br ?/?>", "\n", h)
    h = re.sub(r"</(p|li|h\d|tr|div|td|th)>", "\n", h)
    h = html.unescape(re.sub(r"<[^>]+>", "", h))
    return [l.strip() for l in re.split(r"\n", re.sub(r"[ \t]+", " ", h)) if l.strip()]


LV = re.compile(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)(?:/(\d+(?:\.\d+)?))?")


def levels(eff):
    """'10/15/20%' → Lv別の文。値の並びが無ければ1つだけ"""
    ms = list(LV.finditer(eff))
    if not ms:
        return [eff]
    n = max(3 if m.group(3) else 2 for m in ms)
    out = []
    for k in range(n):
        out.append(LV.sub(lambda m: (m.groups()[k] if k < len(m.groups()) and m.groups()[k] else m.group(1 if k == 0 else 2)), eff))
    return out


def parse(side):
    ls = text(page(side))
    res = {}
    for i, l in enumerate(ls[:-2]):
        if re.fullmatch(r"\d{2}|究極天賦", l):
            name, eff = ls[i + 1], re.sub(r"(\d秒)(?=試合|アクティブ)", r"。", ls[i + 2])
            if len(name) > 14 or len(eff) < 10:
                continue
            res.setdefault(name, {"eff": eff, "lv": levels(eff)})
    return res


if __name__ == "__main__":
    out = {s: parse(s) for s in PAGES}
    out["src"] = {"label": "5ch攻略Wiki 内在人格", "url": "https://wikiwiki.jp/identity5ch/" + urllib.parse.quote(PAGES["s"])}
    (ROOT / "data" / "persona_effects.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    L = json.loads((ROOT / "data" / "persona_layout.json").read_text(encoding="utf-8"))
    for s in PAGES:
        names = set(L["names"][s].values())
        print(s, len(out[s]), "missing:", sorted(names - set(out[s])))
