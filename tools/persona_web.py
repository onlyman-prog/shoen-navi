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
_L = json.load(open(DATA / "persona_layout.json"))
LAYOUT = np.array(_L["nodes"], np.float32)
MAXV = _L["max"]  # マスごとの最大ポイント (1 or 3、中心は0)
_D = json.load(open(DATA / "persona_digits.json"))
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
    lowres = u < 260 if _lo is None else _lo
    k = 398.0 / u  # 基準 (高さ1080の画像で unit=398) に合わせて拡大縮小
    im = cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC if k > 1 else cv2.INTER_AREA)
    cx, cy, u = cx * k, cy * k, 398.0
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    out = []
    p1 = {}  # 低解像度: 最大3のマスが「1」らしい度合い
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
            # 低解像度: ラベルが白く明るい = 振ってある。最大1なら1、最大3なら 1〜3 を判定
            lit = _contrast(c) > thr
            if not lit:
                a = 0
            elif MAXV[i] == 1:
                a = 1
            else:
                v = _lo_glyph(c, hs)
                a = 3  # 最大3のマスは 3/3 が大半なので、はっきり違うときだけ 1/2 にする
                cnt = np.zeros(4)
                if v is not None:
                    sel = LY > 0
                    d = np.sum((LX[sel] - v) ** 2, 1)
                    cnt = np.bincount(LY[sel][np.argsort(d)[:9]], minlength=4)
                    if cnt[1] >= 7:
                        a = 1
                    elif cnt[2] >= 6:
                        a = 2
            if lit and MAXV[i] == 3:
                p1[i] = float(cnt[1])
            out.append((i, a, MAXV[i], lit)); continue
        elif len(comps) >= 3:
            a = _digit(_glyph(m, comps[0]))
        else:
            # 低解像度だと「3/3」がつながる: 文字列全体の左 1/3 を最初の数字とみなす
            ys, xs = np.where(m > 0)
            ok = [j for j in range(1, n) if st[j][3] >= hs * 0.55 and st[j][4] >= 6]
            if not ok:
                out.append((i, (0 if not active else 1 if MAXV[i] == 1 else None), MAXV[i], active)); continue
            x0 = min(st[j][0] for j in ok); x1 = max(st[j][0] + st[j][2] for j in ok)
            y0 = min(st[j][1] for j in ok); y1 = max(st[j][1] + st[j][3] for j in ok)
            w = x1 - x0
            if w < hs * 1.2:
                out.append((i, (0 if not active else 1 if MAXV[i] == 1 else None), MAXV[i], active)); continue
            a = _digit(_glyph(m, (x0, y0, max(3, int(w * 0.30)), y1 - y0)))
        out.append((i, min(a, MAXV[i]), MAXV[i], active))
    if lowres and p1:
        out = _fit_total(out, p1)
    return out


BUDGET = 26  # 高解像度画像の約7割がこの合計 (全部振り切った状態)


def _fit_total(out, p1):
    """低解像度の推定: 合計が BUDGET から少しずれていたら、1/3 の判定に自信がないマスから直す"""
    tot = sum(a or 0 for _, a, _, _ in out)
    diff = tot - BUDGET
    if diff == 0 or abs(diff) > 6 or diff % 2:
        return out
    out = [list(x) for x in out]
    if diff > 0:  # 多すぎ: 3 と読んだうち「1」らしいものを 1 に
        cand = sorted([x for x in out if x[0] in p1 and x[1] == 3], key=lambda x: -p1[x[0]])
        for x in cand[:diff // 2]:
            x[1] = 1
    else:  # 少なすぎ: 1 と読んだうち「1」らしさが低いものを 3 に
        cand = sorted([x for x in out if x[0] in p1 and x[1] == 1], key=lambda x: p1[x[0]])
        for x in cand[:(-diff) // 2]:
            x[1] = 3
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
    return {"ok": True, "pts": pts, "low": reg[2] < 260, "unknown": unk, "total": sum(pts.values())}


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
