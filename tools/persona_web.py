"""人格の網(ゲーム画面のスクショ)から、どのマスに何ポイント振ったかを読み取る。

- マスの配置は全キャラ共通 (data/persona_layout.json: 中心=0, 右端マス≒1 の座標)
- 画像ごとに円を検出してテンプレートに合わせる (位置と大きさのずれを吸収)
- 各マスの下の「a/b」を自作の数字テンプレート (data/persona_digits.json) で読む
"""
import json
from pathlib import Path
import cv2
import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
_L = json.load(open(DATA / "persona_layout.json", encoding="utf-8"))
LAYOUT = np.array(_L["nodes"], np.float32)
MAXV = _L["max"]  # マスごとの最大ポイント (1 or 3、中心は0)
PARENT = {a: b for a, b in _L.get("edges", [])}  # 中心に向かって1つ手前のマス
CHILDREN = {}
for _a, _b in _L.get("edges", []):
    CHILDREN.setdefault(_b, []).append(_a)
_D = json.load(open(DATA / "persona_digits.json", encoding="utf-8"))
DIG = {k: np.array(t, np.float32) for k, t in zip(_D["keys"], _D["templates"])}
KX, KY = np.array(_D["knnX"], np.float32), np.array(_D["knnY"])
LX, LY = np.array(_D.get("loX", []), np.float32), np.array(_D.get("loY", []), int)
CENTER = int(np.argmin(np.hypot(LAYOUT[:, 0], LAYOUT[:, 1])))
END_IDX = [int(i) for i in np.argsort(-np.hypot(LAYOUT[:, 0], LAYOUT[:, 1]))[:4]]  # 4方向の末端 (大きいマス)


def load(path):
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)


def register(im):
    """(cx, cy, unit) を返す。unit = 中心から右端マスまでの距離に相当する長さ。"""
    H, W = im.shape[:2]
    g = cv2.medianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), 3)
    c = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1.2, minDist=H * 0.025, param1=80, param2=20,
                         minRadius=int(H * 0.014), maxRadius=int(H * 0.045))
    if c is None:
        return None
    P = c[0][:, :2]
    best = (-1, None)
    right = [i for i in range(len(LAYOUT)) if abs(LAYOUT[i, 1]) < 0.02 and LAYOUT[i, 0] > 0.1]
    for cx, cy in P:
        if abs(cx - W / 2) > W * 0.2 or abs(cy - H / 2) > H * 0.2:
            continue
        for dx, dy in P:
            if abs(dy - cy) > H * 0.015 or dx <= cx:
                continue
            for ri in right:
                u = (dx - cx) / LAYOUT[ri, 0]
                if not (H * 0.2 < u < H * 0.6):
                    continue
                proj = np.stack([cx + LAYOUT[:, 0] * u, cy + LAYOUT[:, 1] * u], 1)
                d = np.min(np.hypot(proj[:, None, 0] - P[None, :, 0], proj[:, None, 1] - P[None, :, 1]), 1)
                score = int((d < u * 0.04).sum())
                if score > best[0]:
                    best = (score, (float(cx), float(cy), float(u)))
    return best[1] if best[0] >= 15 else None


def _glyph(m, s):
    x0, y0, w, h = s[:4]
    return cv2.resize(m[y0:y0 + h, x0:x0 + w] * 255, (10, 14), interpolation=cv2.INTER_AREA).ravel() / 255.0


def _digit(x):
    """k近傍 (k=7) で 0〜3 を判定。2 はサンプルが少ないので平均テンプレートでも確認"""
    d = np.sum((KX - x) ** 2, 1)
    nn = KY[np.argsort(d)[:7]]
    v = int(np.bincount(nn, minlength=4).argmax())
    if v == 3 and float(np.sum((x - DIG[2]) ** 2)) < float(np.sum((x - DIG[3]) ** 2)) * 0.7:
        return 2
    return v


def _lo_glyph(c, hs):
    """低解像度: 文字列の左30%をグレースケールで正規化して返す"""
    g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY).astype(np.float32)
    sat = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)[:, :, 1]
    m = (g > np.median(g) + 30) & (sat < 90)
    cols, rows = np.where(m.sum(0) > 0)[0], np.where(m.sum(1) > 0)[0]
    if len(cols) < hs * 1.2 or len(rows) < hs * 0.5:
        return None
    x0, x1, y0, y1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
    w = max(3, int((x1 - x0) * 0.30))
    a = np.where(sat[y0:y1, x0:x0 + w] < 90, g[y0:y1, x0:x0 + w], np.median(g))
    v = cv2.resize(a, (10, 14), interpolation=cv2.INTER_AREA).ravel()
    return (v - v.mean()) / (v.std() + 1e-6)


def _label_crop(im, px, py, u, big):
    return im[max(0, int(py + (0.085 if big else 0.07) * u)):int(py + (0.145 if big else 0.13) * u),
              max(0, int(px - 0.075 * u)):int(px + 0.075 * u)]


def _contrast(c):
    g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY).astype(np.float32)
    s = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)[:, :, 1]
    gg = g[s < 90]
    return float(np.percentile(gg, 98) - np.median(gg)) if gg.size else 0.0


def read(im, _lo=None):
    """[(node, points, max, active), ...] を返す。読めないマスは points=None。"""
    reg = register(im)
    if not reg:
        return None
    cx, cy, u = reg
    lowres = u < 250 if _lo is None else _lo
    k = 398.0 / u  # 基準 (高さ1080の画像で unit=398) に合わせて拡大縮小
    im = cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC if k > 1 else cv2.INTER_AREA)
    cx, cy, u = cx * k, cy * k, 398.0
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    out = []
    p1 = {}  # 低解像度: 最大3のマスが「1」らしい度合い
    guess = []  # 数字が読めず 3 と仮置きしたマス
    thr = 50.0
    if lowres:  # 画像ごとに「明るいラベル」と「暗いラベル」を2つに分ける閾値を決める
        cs = []
        for i, (x, y) in enumerate(LAYOUT):
            if MAXV[i] == 0:
                continue
            c = _label_crop(im, cx + x * u, cy + y * u, u, i in END_IDX)
            if c.size:
                cs.append(_contrast(c))
        if len(cs) > 6:
            v = np.sort(np.array(cs, np.float32))
            best = max(range(2, len(v) - 1), key=lambda j: (v[:j].var() * j + v[j:].var() * (len(v) - j)) * -1)
            thr = max(40.0, (v[best - 1] + v[best]) / 2)
    for i, (x, y) in enumerate(LAYOUT):
        px, py = cx + x * u, cy + y * u
        big = i in END_IDX
        y0, y1 = int(py + (0.085 if big else 0.07) * u), int(py + (0.145 if big else 0.13) * u)
        c = im[max(0, y0):y1, max(0, int(px - 0.075 * u)):int(px + 0.075 * u)]
        # マスの中が色付き (彩度が高い) = 振ってある
        r = int(0.05 * u)
        disk = hsv[max(0, int(py - r)):int(py + r), max(0, int(px - r)):int(px + r)]
        active = bool(disk.size and np.mean(disk[:, :, 1]) > 70 and np.mean(disk[:, :, 2]) > 110)
        if i == CENTER or c.size == 0:
            out.append((i, None, MAXV[i], active)); continue
        g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY).astype(np.float32)
        sat = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)[:, :, 1]
        # 文字は白/灰色。線 (水色/オレンジ) は彩度が高いので除く
        m = ((g > np.median(g) + 45) & (sat < 90)).astype(np.uint8)
        n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
        hs = 0.04 * u
        comps = sorted([st[j] for j in range(1, n) if hs * 0.55 <= st[j][3] <= hs * 1.6 and st[j][4] >= 8], key=lambda s: s[0])
        if lowres and len(LX):
            # 中・低解像度: 最初の数字を 0〜3 で直接判定 (縮小した高解像度画像から作った見本との近さ)
            v = _lo_glyph(c, hs)
            lit = _contrast(c) > thr
            if v is None:
                a = 0 if not lit else (1 if MAXV[i] == 1 else 3)
                cnt = np.zeros(4)
            else:
                d = np.sum((LX - v) ** 2, 1)
                cnt = np.bincount(LY[np.argsort(d)[:9]], minlength=4)
                a = int(cnt.argmax())
            a = min(a, MAXV[i])
            if a and MAXV[i] == 3:
                p1[i] = float(cnt[1])
            out.append((i, a, MAXV[i], a > 0)); continue
        elif len(comps) >= 3 or (len(comps) == 2 and comps[0][0] + comps[0][2] / 2 < c.shape[1] * 0.45):
            # 線が縦に重なると「/」が消えて2つになるので、左側の塊が最初の数字なら読む
            a = _digit(_glyph(m, comps[0]))
        else:
            # 低解像度だと「3/3」がつながる: 文字列全体の左 1/3 を最初の数字とみなす
            ys, xs = np.where(m > 0)
            ok = [j for j in range(1, n) if st[j][3] >= hs * 0.55 and st[j][4] >= 6]
            if not ok:
                out.append((i, (0 if not active else 1 if MAXV[i] == 1 else _guess(guess, i)), MAXV[i], active)); continue
            x0 = min(st[j][0] for j in ok); x1 = max(st[j][0] + st[j][2] for j in ok)
            y0 = min(st[j][1] for j in ok); y1 = max(st[j][1] + st[j][3] for j in ok)
            w = x1 - x0
            if w < hs * 1.2:
                out.append((i, (0 if not active else 1 if MAXV[i] == 1 else _guess(guess, i)), MAXV[i], active)); continue
            a = _digit(_glyph(m, (x0, y0, max(3, int(w * 0.30)), y1 - y0)))
        out.append((i, min(a, MAXV[i]), MAXV[i], active))
    if lowres and p1:
        out = _fit_total(out, p1)
    out = _closure(out)
    if lowres and p1:
        out = _fit_total(out, p1)
    if guess:  # 仮置きしたマスは合計が BUDGET になるように決める (1〜3)。道中のマスは最大で確定
        lit = {n for n, a, _, _ in out if a}
        guess = [g for g in guess if not any(c in lit for c in CHILDREN.get(g, []))]
    if guess:
        tot = sum(a or 0 for _, a, _, _ in out)
        need = BUDGET - (tot - 3 * len(guess))
        if len(guess) <= need <= 3 * len(guess):
            vals = [need // len(guess)] * len(guess)
            for k in range(need % len(guess)):
                vals[k] += 1
            out = [(n, vals[guess.index(n)] if n in guess else a, b, act) for n, a, b, act in out]
    return out


def _closure(out):
    """振ったマスの手前 (中心側) は必ず振ってある。つながっていないマスがあれば、
    「手前を振ったことにする」か「そのマスを外す」の、合計が BUDGET に近くなる方を選ぶ"""
    val = {n: (a or 0) for n, a, _, _ in out}
    for _ in range(6):
        broken = [n for n, v in val.items() if v and PARENT.get(n) is not None and PARENT[n] != CENTER and not val.get(PARENT[n])]
        if not broken:
            break
        for n in broken:
            if not val[n] or val.get(PARENT[n]):
                continue
            tot = sum(val.values())
            p = PARENT[n]
            add = 1 if MAXV[p] == 1 else max(1, min(3, BUDGET - tot))
            if abs(tot + add - BUDGET) <= abs(tot - val[n] - BUDGET):
                val[p] = add
            else:
                val[n] = 0
    # 道中のマス (先に振ったマスがある) は最大まで振らないと先へ進めない
    def subtree(n):  # n とその先にある振ったマス
        s = [n]
        for c in CHILDREN.get(n, []):
            if val.get(c):
                s += subtree(c)
        return s
    for n in sorted(val, key=lambda k: -float(np.hypot(*LAYOUT[k]))):  # 外側から
        lit_kids = [c for c in CHILDREN.get(n, []) if val.get(c)]
        if not val[n] or not lit_kids or val[n] >= MAXV[n]:
            continue
        tot = sum(val.values())
        up = tot + MAXV[n] - val[n]  # 道中なので最大まで振ってある
        cut = tot - sum(val[k] for c in lit_kids for k in subtree(c))  # 先のマスは読み違い
        if abs(up - BUDGET) <= abs(cut - BUDGET):
            val[n] = MAXV[n]
        else:
            for c in lit_kids:
                for k in subtree(c):
                    val[k] = 0
    return [(n, (val[n] if val[n] or a is not None else None), b, act or val[n] > 0) for n, a, b, act in out]


def _guess(guess, i):
    guess.append(i)
    return 3


BUDGET = 26  # 高解像度画像の約7割がこの合計 (全部振り切った状態)


def _fit_total(out, p1):
    """低解像度の推定: 合計が BUDGET から少しずれていたら、1/3 の判定に自信がないマスから直す"""
    tot = sum(a or 0 for _, a, _, _ in out)
    diff = tot - BUDGET
    if diff == 0 or abs(diff) > 6:
        return out
    out = [list(x) for x in out]
    lit = {x[0] for x in out if x[1]}
    p1 = {n: v for n, v in p1.items() if not any(c in lit for c in CHILDREN.get(n, []))}  # 終点だけ
    if diff > 0:  # 多すぎ: 3 と読んだうち「1」らしいものを 1 に (奇数なら最後の1つは 2 に)
        cand = sorted([x for x in out if x[0] in p1 and x[1] == 3], key=lambda x: -p1[x[0]])
        for k, x in enumerate(cand[:(diff + 1) // 2]):
            x[1] = 2 if (diff % 2 and k == (diff + 1) // 2 - 1) else 1
    else:  # 少なすぎ: 1 と読んだうち「1」らしさが低いものを 3 に
        cand = sorted([x for x in out if x[0] in p1 and x[1] == 1], key=lambda x: p1[x[0]])
        need = -diff
        for k, x in enumerate(cand[:(need + 1) // 2]):
            x[1] = 2 if (need % 2 and k == (need + 1) // 2 - 1) else 3
    return [tuple(x) for x in out]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        r = read(load(p))
        print(p, None if r is None else [(i, a, b) for i, a, b, act in r if a])


def analyze_url(url):
    """画像URLを読み取って {"pts": {マス番号: ポイント}, "low": 低解像度か, "ok": 読めたか} を返す"""
    import urllib.request
    src = url.split("=")[0] + "=s0" if "googleusercontent" in url else url
    raw = urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
    im = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        return {"ok": False}
    reg = register(im)
    r = read(im) if reg else None
    if not r:
        return {"ok": False}
    pts = {str(n): int(a) for n, a, b, act in r if a}
    unk = [n for n, a, b, act in r if a is None and MAXV[n] > 0]
    return {"ok": True, "pts": pts, "low": reg[2] < 300, "unknown": unk, "total": sum(pts.values())}


def update_cache(chars, path=DATA / "persona_reads.json", log=print):
    """全キャラの構成画像を読み取り、URLごとに結果を保存 (読み取り済みは再利用)"""
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for c in chars.values():
        for b in c.get("builds", []):
            u = b.get("tree")
            if not u or u in cache:
                continue
            try:
                cache[u] = analyze_url(u)
            except Exception as e:  # 画像取得の失敗は次回に再挑戦
                log(f"persona read failed: {e}")
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


# ---------- 記録した構成の統合と名前付け ----------
_NAMES = _L.get("names", {})


def _ends(side, pts):
    return {_NAMES[side][k] for k in pts if int(k) in END_IDX and k in _NAMES.get(side, {})}


def type_name(side, pts):
    e = _ends(side, pts)
    if side == "s":
        if "危機一髪" in e and "フライホイール効果" in e:
            return "危機一髪＋フラホ型"
        if "危機一髪" in e:
            return "救助型"
        if "フライホイール効果" in e and "膝蓋腱反射" in e:
            return "フラホ＋膝蓋腱型"
        if "フライホイール効果" in e:
            return "フラホ型"
        if "膝蓋腱反射" in e:
            return "膝蓋腱型"
        return "その他"
    if e == {"引き留める", "裏向きカード"}:
        return "右下型"
    short = {"傲慢": "傲慢", "閉鎖空間": "閉鎖空間", "引き留める": "引き留め", "裏向きカード": "裏向き"}
    ks = [short[x] for x in ("傲慢", "閉鎖空間", "引き留める", "裏向きカード") if x in e]
    return "＋".join(ks) + "型" if ks else "その他"


def fix_pts(pts):
    """保存済みの読み取り結果にも「手前のマスは必ず振ってある」を当てはめる"""
    out = _closure([(int(k), v, MAXV[int(k)], True) for k, v in pts.items()] +
                   [(n, 0, MAXV[n], False) for n in range(len(LAYOUT)) if str(n) not in pts])
    return {str(n): int(a) for n, a, _, _ in out if a}


def merge_records(recs):
    """同じキャラで振り方が同じ記録を1つにまとめ、型と違いが分かる名前を付ける"""
    groups = {}
    for r in recs:
        key = (r["char"], json.dumps(sorted(r["web"]["pts"].items())))
        g = groups.get(key)
        if g:
            g["count"] = g.get("count", 1) + r.get("count", 1)
            g["date"] = max(g.get("date", ""), r.get("date", ""))
            g["images"] = sorted(set(g.get("images", []) + r.get("images", [])))
        else:
            groups[key] = dict(r, count=r.get("count", 1))
    out = list(groups.values())
    by = {}
    for r in out:
        r["type"] = type_name(r["side"], r["web"]["pts"])
        r["check"] = sum(r["web"]["pts"].values()) != BUDGET
        by.setdefault((r["char"], r["type"]), []).append(r)
    for (ch, tp), gg in by.items():
        if len(gg) == 1:
            gg[0]["name"] = tp
            continue
        N = _NAMES[gg[0]["side"]]
        for g in gg:
            mine = {N.get(k, k): v for k, v in g["web"]["pts"].items()}
            others = [{N.get(k, k): v for k, v in o["web"]["pts"].items()} for o in gg if o is not g]
            uniq = sorted([n for n, v in mine.items() if all(o.get(n, 0) != v for o in others)], key=lambda n: -mine[n])
            g["name"] = f"{tp}・{uniq[0]}{mine[uniq[0]] if mine[uniq[0]] > 1 else ''}" if uniq else tp
        seen, cnt = {}, {}
        for g in gg:
            cnt[g["name"]] = cnt.get(g["name"], 0) + 1
        for g in gg:
            if cnt[g["name"]] > 1:
                seen[g["name"]] = seen.get(g["name"], 0) + 1
                g["name"] = f"{g['name']}({seen[g['name']]})"
    return out
