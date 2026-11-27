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


WORK_UNIT = 398.0  # 中心〜端のマスまでを何ピクセルに拡大して読むか
try:  # ラベル全体の見本 (振った数_最大_縮小率 → 64x32 の明るさ)
    _LT = dict(np.load(DATA / "persona_labels.npz"))
except Exception:
    _LT = {}


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
    if best[0] < 15:
        return None
    # 仕上げ: 近くの円と対応づけて、位置と大きさを最小二乗で合わせ直す
    cx, cy, u = best[1]
    for _ in range(3):
        proj = np.stack([cx + LAYOUT[:, 0] * u, cy + LAYOUT[:, 1] * u], 1)
        d = np.hypot(proj[:, None, 0] - P[None, :, 0], proj[:, None, 1] - P[None, :, 1])
        j = d.argmin(1)
        ok = d[np.arange(len(LAYOUT)), j] < u * 0.05
        if ok.sum() < 12:
            break
        X, Y = LAYOUT[ok], P[j[ok]]
        # x_img = cx + X*u, y_img = cy + Y*u を同時に解く
        A = np.zeros((2 * len(X), 3))
        A[0::2, 0], A[0::2, 2] = 1, X[:, 0]
        A[1::2, 1], A[1::2, 2] = 1, X[:, 1]
        b = Y.reshape(-1)
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        cx, cy, u = (float(v) for v in sol)
    return (cx, cy, u)


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


def _read_at(im, _lo=None):
    """[(node, points, max, active), ...] を返す。読めないマスは points=None。"""
    reg = register(im)
    if not reg:
        return None
    cx, cy, u = reg
    lowres = u < 250 if _lo is None else _lo
    k = WORK_UNIT / u  # ラベルの数字を読みやすいよう、大きく拡大してから読む
    im = cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_LANCZOS4 if k > 1 else cv2.INTER_AREA)
    cx, cy, u = cx * k, cy * k, WORK_UNIT
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


def _closure(out, protect=frozenset()):
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
            if abs(tot + add - BUDGET) <= abs(tot - val[n] - BUDGET) or n in protect:
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
        cut_nodes = [k for c in lit_kids for k in subtree(c)]
        if abs(up - BUDGET) <= abs(cut - BUDGET) or any(k in protect for k in cut_nodes):
            val[n] = MAXV[n]
        else:
            for c in lit_kids:
                for k in subtree(c):
                    val[k] = 0
    return [(n, (val[n] if val[n] or a is not None else None), b, act or val[n] > 0) for n, a, b, act in out]


ZOOMS = (398.0, 800.0, 1200.0)
LM_ON, LM_MARGIN = True, 0.1  # ラベル全体の見本合わせを使うか・自信の閾値


def label_match(im, cx, cy, u, n):
    """ラベル全体を見本と比べて「振った数」を返す (線が重なった画素は比べない)。(値, 2位との差)"""
    if not _LT:
        return None, 0.0
    x, y = LAYOUT[n]
    px, py = cx + x * u, cy + y * u
    big = n in END_IDX
    c = im[max(0, int(py + (0.075 if big else 0.06) * u)):int(py + (0.155 if big else 0.14) * u),
           max(0, int(px - 0.08 * u)):int(px + 0.08 * u)]
    if c.size == 0:
        return None, 0.0
    c = cv2.resize(c, (64, 32), interpolation=cv2.INTER_AREA if c.shape[1] > 64 else cv2.INTER_CUBIC)
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    line = ((hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 110)).astype(np.uint8)
    keep = cv2.dilate(line, np.ones((3, 3), np.uint8)) == 0
    keep[:, 30:] = False  # 最初の数字がある左側だけで比べる (「/3」の部分は全員同じなので差が出ない)
    g = hsv[:, :, 2].astype(np.float32)[keep]
    if g.size < 120:
        return None, 0.0
    g = (g - g.mean()) / (g.std() + 1e-6)
    best = {}
    for k, tpl in _LT.items():
        a, m, _ = k.split("_")
        if int(m) != MAXV[n]:
            continue
        tt = tpl[keep]
        tt = (tt - tt.mean()) / (tt.std() + 1e-6)
        s = float((g * tt).mean())
        best[int(a)] = max(best.get(int(a), -9), s)
    if not best:
        return None, 0.0
    order = sorted(best.items(), key=lambda kv: -kv[1])
    label_match.last = best
    return order[0][0], (order[0][1] - order[1][1]) if len(order) > 1 else 1.0


def _lit_by_color(im):
    """マスの縁の明るさで「振ったか」を判定 (振ったマスは明るい青/オレンジ、振っていないマスは暗い)"""
    reg = register(im)
    if not reg:
        return None
    cx, cy, u = reg
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    H, W = im.shape[:2]
    out = {}
    for n, (x, y) in enumerate(LAYOUT):
        px, py = cx + x * u, cy + y * u
        r = 0.052 * u * (1.3 if n in END_IDX else 1)
        y0, y1, x0, x1 = int(py - r), int(py + r), int(px - r), int(px + r)
        if y0 < 0 or x0 < 0 or y1 > H or x1 > W:
            out[n] = None  # 画面外 (判定しない)
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot(xx - px, yy - py)
        ring = (d > 0.55 * r) & (d < 0.9 * r)
        s = float(np.median(hsv[y0:y1, x0:x1, 1][ring]))
        v = float(np.median(hsv[y0:y1, x0:x1, 2][ring]))
        # 明るい灰色 (アイコンが見えるだけで振っていないマス) は彩度が低いので除く
        out[n] = v if (s > 50 or v > 215) else min(v, 100.0)
    # 画像ごとに「明るいマス」と「暗いマス」を2つに分ける (ランキング画面に重なって全体が暗い時も対応)
    vals = sorted(v for k, v in out.items() if v is not None and MAXV[k])
    if len(vals) < 10:
        return None
    if sum(1 for v in vals if v > 150) >= 8:  # ふつうの画面: 明るさ150で分かれる
        return {k: (None if v is None else v > 150) for k, v in out.items()}
    best, thr = -1, 155.0
    for i in range(3, len(vals) - 3):
        if not (8 <= len(vals) - i <= 26):  # 振ったマスは 1構成で 10〜24 個ほど
            continue
        gap = vals[i] - vals[i - 1]
        if gap > best:
            best, thr = gap, (vals[i] + vals[i - 1]) / 2
    if best < 15:  # はっきり分かれない (切り替え中の画面など) ときは色を使わない
        return None
    return {k: (None if v is None else v > thr) for k, v in out.items()}


def read(im, _lo=None):
    """画像を何段階かに拡大して読み、マスごとに多数決 (同数なら 800 倍率の結果)。最後に構造ルールで整える"""
    global WORK_UNIT
    res = []
    keep = WORK_UNIT
    try:
        for z in ZOOMS:
            WORK_UNIT = z
            r = _read_at(im, _lo)
            if r is None:
                return None
            res.append(r)
    finally:
        WORK_UNIT = keep
    lit = _lit_by_color(im)
    reg = register(im)
    protect = frozenset(k for k, v in (lit or {}).items() if v)

    def fix(nodes, votes_of):
        """色の判定とラベル全体の見本合わせで1マスずつ直し、つながりのルールで整える"""
        out = []
        for k, node in enumerate(nodes):
            n, best = node[0], node[1]
            votes = votes_of(k)
            if lit is not None and MAXV[n] and lit.get(n) is not None:
                if not lit[n]:
                    best = 0  # 色が付いていないマスは振っていない
                elif MAXV[n] == 1:
                    best = 1
                else:  # 最大3で振ってあるマス: ラベル全体の見本合わせ (線が重なっても読める)
                    nz = [x for x in votes if x]
                    unsure = len(set(votes)) > 1 or not best  # 拡大率ごとの読みが割れた/読めなかった時だけ
                    v, margin = label_match(im, *reg, n) if (unsure and LM_ON) else (None, 0.0)
                    if v and margin > LM_MARGIN:
                        best = v
                    elif not best:
                        best = max(set(nz), key=nz.count) if nz else 3
            out.append((n, best, node[2], bool(best)))
        return _closure(out, protect)

    def vote(k):
        return [r[k][1] for r in res]

    def majority(k):
        vs = vote(k)
        cnt = {}
        for v in vs:
            cnt[v] = cnt.get(v, 0) + 1
        return max(cnt.items(), key=lambda x: (x[1], x[0] == res[1][k][1]))[0]

    out = fix([(nd[0], majority(k), nd[2], nd[3]) for k, nd in enumerate(res[1])], vote)
    if sum(a or 0 for _, a, _, _ in out) != BUDGET and reg:
        out = _fit_leaves(im, reg, out, vote)
    # 自信のないマス: 最大3の終点で途中まで (1/3・2/3) のもの、拡大率ごとの読みが割れたもの
    val = {n: (a or 0) for n, a, _, _ in out}
    read.unsure = sorted(n for k, (n, a, _, _) in enumerate(out)
                         if a and MAXV[n] == 3 and not any(val.get(c) for c in CHILDREN.get(n, []))
                         and ((a < 3 and reg and reg[2] < 300) or len({v for v in vote(k) if v}) > 1))
    return out


def _fit_leaves(im, reg, out, vote_of):
    """合計が BUDGET からずれた時: 最大3で振ってある「枝の終点」のマスに 1/2/3 を当てはめ直し、
    合計がちょうど BUDGET になる組み合わせの中で、ラベル全体の見本合わせ・各倍率の読みに最も合うものを選ぶ"""
    import itertools
    val = {n: (a or 0) for n, a, _, _ in out}
    leaves = [n for n, v in val.items() if v and MAXV[n] == 3 and not any(val.get(c) for c in CHILDREN.get(n, []))]
    if not leaves or len(leaves) > 7:
        return out
    fixed = sum(v for n, v in val.items() if n not in leaves)
    scores = {}
    for n in leaves:
        label_match.last = {}
        label_match(im, *reg, n)
        s = dict(label_match.last or {})
        k = [i for i, (m, *_r) in enumerate(out) if m == n][0]
        for v in vote_of(k):
            if v:
                s[v] = s.get(v, 0) + 0.15  # 数字の読みとも合っているほど良い
        scores[n] = s
    best, best_s = None, -1e9
    for combo in itertools.product((1, 2, 3), repeat=len(leaves)):
        if fixed + sum(combo) != BUDGET:
            continue
        s = sum(scores[n].get(v, -1) for n, v in zip(leaves, combo))
        if s > best_s:
            best, best_s = combo, s
    if best is None:
        return out
    newv = dict(zip(leaves, best))
    return [(n, newv.get(n, a), b, act) for n, a, b, act in out]


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
    return {"ok": True, "pts": pts, "low": reg[2] < 300, "unsure": [str(n) for n in getattr(read, "unsure", [])], "total": sum(pts.values())}


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


def first_digit_by_ref(im, cx, cy, u, n, debug=False):
    """最大3のマスのラベル「a/3」で、右の「3」を物差しにして左の数字 a を判定する (8倍に拡大して比べる)。
    戻り値: (a, 自信 0〜1)。左の数字が右の3よりずっと細い→1、3とほぼ同じ形→3、それ以外→2"""
    x, y = LAYOUT[n]
    px, py = cx + x * u, cy + y * u
    big = n in END_IDX
    c = im[max(0, int(py + (0.075 if big else 0.06) * u)):int(py + (0.155 if big else 0.14) * u),
           max(0, int(px - 0.085 * u)):int(px + 0.085 * u)]
    if c.size == 0 or c.shape[0] < 4:
        return None, 0.0
    k = max(1.0, 160.0 / c.shape[1])
    c = cv2.resize(c, None, fx=k, fy=k, interpolation=cv2.INTER_LANCZOS4)
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2].astype(np.float32)
    line = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 110)
    bg = np.median(v[~line]) if (~line).any() else np.median(v)
    ink = (v > bg + 0.45 * (np.percentile(v[~line], 99) - bg)) & ~line if (~line).any() else v > bg + 40
    cols = ink.sum(0)
    xs = np.where(cols > 0)[0]
    if len(xs) < 6:
        return None, 0.0
    x0, x1 = xs[0], xs[-1]
    W = x1 - x0 + 1
    # 左の数字 = 文字列の左 35%、右の数字 = 右 35%
    lw, rw = int(W * 0.36), int(W * 0.36)
    L = ink[:, x0:x0 + lw]
    R = ink[:, x1 - rw + 1:x1 + 1]

    def box(m):
        ys, xs2 = np.where(m)
        if len(xs2) == 0:
            return None
        return m[ys.min():ys.max() + 1, xs2.min():xs2.max() + 1]
    bl, br = box(L), box(R)
    if bl is None or br is None or br.shape[1] < 3:
        return None, 0.0
    ratio = bl.shape[1] / br.shape[1]
    if ratio < 0.6:
        return 1, min(1.0, (0.6 - ratio) / 0.2 + 0.5)
    a = cv2.resize(bl.astype(np.float32), (12, 18), interpolation=cv2.INTER_AREA).ravel()
    b = cv2.resize(br.astype(np.float32), (12, 18), interpolation=cv2.INTER_AREA).ravel()
    a, b = a - a.mean(), b - b.mean()
    sim = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6))
    if debug:
        print("ratio", round(ratio, 2), "sim", round(sim, 2))
    if sim > 0.75:
        return 3, min(1.0, (sim - 0.75) / 0.15 + 0.5)
    return 2, min(1.0, (0.75 - sim) / 0.15 + 0.5)
