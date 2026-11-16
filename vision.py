"""ゲーム画面からBANされたサバイバーを読み取る。

仕組み:
  1. ゲームウィンドウ(IdentityV)のクライアント領域をキャプチャ
  2. 事前に設定した「BAN枠」(画面に対する割合の矩形, 最大3つ)を切り出し
  3. 各枠をサバイバーのアイコン画像とテンプレートマッチング
  4. 記録(正解)が付くたびに、その枠の切り抜きを学習用テンプレートとして保存
     → 使うほど自分の画面に合った画像で照合でき、精度が上がる
"""
import ctypes
import hashlib
import itertools
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

import cv2
import mss
import numpy as np

GAME_TITLE = "IdentityV"
DATA = Path(__file__).parent / "data"
ICONS = DATA / "icons"
LEARNED = DATA / "learned"
CAPTURES = DATA / "captures"
MAX_LEARNED = 6

user32 = ctypes.windll.user32


# OpenCVのimread/imwriteは日本語パスを扱えないので自前で読み書き
def imread(path):
    try:
        return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def imwrite(path, img):
    ok, buf = cv2.imencode(Path(path).suffix or ".png", img)
    if ok:
        buf.tofile(str(path))
    return ok


# ---------------- ウィンドウ / キャプチャ ----------------
def find_game():
    return user32.FindWindowW(None, GAME_TITLE) or None


def client_rect(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right - r.left, r.bottom - r.top


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def overlaps(other_hwnd, slots):
    """other_hwnd のウィンドウがゲーム画面上のBAN枠に重なっているか。"""
    g = find_game()
    if not g or not other_hwnd or not user32.IsWindowVisible(other_hwnd) or user32.IsIconic(other_hwnd):
        return False
    gx, gy, gw, gh = client_rect(g)
    ox0, oy0, ox1, oy1 = window_rect(other_hwnd)
    for x0, y0, x1, y1 in slots:
        sx0, sy0, sx1, sy1 = gx + x0 * gw, gy + y0 * gh, gx + x1 * gw, gy + y1 * gh
        if sx0 < ox1 and ox0 < sx1 and sy0 < oy1 and oy0 < sy1:
            return True
    return False


def capture():
    """ゲーム画面(BGR)を返す。ゲームが無い/最小化中は None。"""
    hwnd = find_game()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    x, y, w, h = client_rect(hwnd)
    if w < 100 or h < 100:
        return None
    with mss.mss() as s:
        shot = s.grab({"left": x, "top": y, "width": w, "height": h})
    return cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)


def save_capture(img):
    CAPTURES.mkdir(parents=True, exist_ok=True)
    files = sorted(CAPTURES.glob("*.png"))
    for f in files[:-19]:  # 最新20枚だけ残す
        f.unlink(missing_ok=True)
    p = CAPTURES / time.strftime("%Y%m%d_%H%M%S.png")
    imwrite(str(p), img)
    return p


def crop(img, frac):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = frac
    return img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


# ---------------- テンプレート ----------------
def key(name):
    return hashlib.md5(name.encode()).hexdigest()[:12]


def ensure_icons(chars):
    """サバイバーのアイコンをローカルに保存(初回 or 新キャラのみダウンロード)。"""
    from concurrent.futures import ThreadPoolExecutor
    ICONS.mkdir(parents=True, exist_ok=True)

    def get(c):
        p = ICONS / f"{key(c['name'])}.png"
        if p.exists() or not c.get("img"):
            return
        try:
            req = urllib.request.Request(c["img"] + "=s160", headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=15).read()
            arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if arr is not None:
                imwrite(p, arr)
        except Exception:
            pass

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(get, chars))


def gray(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.equalizeHist(g)


class Matcher:
    def __init__(self, names):
        self.names = list(names)
        self.reload()

    def reload(self):
        self.base, self.learned = {}, {}
        for n in self.names:
            k = key(n)
            p = ICONS / f"{k}.png"
            if p.exists():
                im = imread(str(p))
                if im is not None:
                    self.base[n] = gray(im)
            d = LEARNED / k
            if d.exists():
                self.learned[n] = [gray(imread(str(f))) for f in sorted(d.glob("*.png"))]

    def score_slot(self, slot):
        """枠画像に対する各キャラの一致度 {name: 0..1}。"""
        if slot.size == 0:
            return {}
        g = gray(slot)
        h, w = g.shape
        out = {}
        for n in self.names:
            best = -1.0
            # 学習済み切り抜き: 同じ形なので同サイズで比較(少しずらしても許容)
            for t in self.learned.get(n, []):
                # 同サイズに揃えて中央90%を切り出し、枠内で±5%ずらして照合
                tt = cv2.resize(t, (w, h))
                mx, my = max(1, w // 20), max(1, h // 20)
                tt = tt[my:h - my, mx:w - mx]
                best = max(best, float(cv2.matchTemplate(g, tt, cv2.TM_CCOEFF_NORMED).max()))
            # 攻略サイトのアイコン: 枠内を複数サイズでスライド
            b = self.base.get(n)
            if b is not None:
                for k in (0.55, 0.7, 0.85, 1.0):
                    s = int(min(w, h) * k)
                    if s < 16:
                        continue
                    tt = cv2.resize(b, (s, s))
                    v = float(cv2.matchTemplate(g, tt, cv2.TM_CCOEFF_NORMED).max())
                    best = max(best, v * 0.9)  # 公式外の画像なので少し割り引く
            out[n] = best
        return out

    def recognize(self, img, slots):
        """各枠ごとに上位3候補 [(name, score), ...] を返す。"""
        res = []
        for fr in slots:
            sc = self.score_slot(crop(img, fr))
            res.append(sorted(sc.items(), key=lambda x: -x[1])[:3])
        return res

    def learn(self, img, slots, names):
        """正解の names を枠に割り当てて切り抜きを保存。割り当ては一致度の合計が最大になる順列。"""
        crops = [crop(img, fr) for fr in slots]
        if not names or len(names) > len(crops):
            return 0
        scores = [self.score_slot(c) for c in crops]
        best, best_perm = -1e9, None
        for perm in itertools.permutations(range(len(crops)), len(names)):
            s = sum(scores[i].get(n, 0) for i, n in zip(perm, names))
            if s > best:
                best, best_perm = s, perm
        for i, n in zip(best_perm, names):
            d = LEARNED / key(n)
            d.mkdir(parents=True, exist_ok=True)
            imwrite(str(d / f"{int(time.time() * 1000)}.png"), crops[i])
            for f in sorted(d.glob("*.png"))[:-MAX_LEARNED]:
                f.unlink(missing_ok=True)
        self.reload()
        return len(names)


def to_data_url(img, max_w=900):
    h, w = img.shape[:2]
    if w > max_w:
        img = cv2.resize(img, (max_w, int(h * max_w / w)))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


# ---------------- 自動スクショ ----------------
AUTO_DIR = CAPTURES / "auto"


class AutoShots:
    """ゲーム中の画面を見て、場面が変わったら自動保存する。

    試合中はカメラが常に動くので「変化したら保存」だけだとすぐ上限に達し、
    試合前(BAN/キャラ選択)の画面が押し出される。そこで:
      - 保存は最短 interval 秒おき
      - 直近 recent 秒は全部残す(1試合まるごと)
      - それより古いものは thin 秒に1枚まで間引く / 全体で keep 枚まで
    """

    def __init__(self, interval=4, recent=15 * 60, thin=30, keep=400, diff=6.0):
        self.interval, self.recent, self.thin, self.keep, self.diff = interval, recent, thin, keep, diff
        self.prev = None
        self.last_t = 0

    def maybe_save(self, img):
        now = time.time()
        if now - self.last_t < self.interval:
            return None
        small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (96, 54)).astype(np.float32)
        if self.prev is not None and float(np.abs(small - self.prev).mean()) < self.diff:
            return None  # ほぼ同じ画面
        self.prev, self.last_t = small, now
        AUTO_DIR.mkdir(parents=True, exist_ok=True)
        p = AUTO_DIR / time.strftime("%Y%m%d_%H%M%S.jpg")
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            buf.tofile(str(p))
        self._prune(now)
        return p

    def _prune(self, now):
        files = sorted(AUTO_DIR.glob("*.jpg"))
        last_kept = None
        for f in files:
            try:
                t = time.mktime(time.strptime(f.stem[:15], "%Y%m%d_%H%M%S"))
            except ValueError:
                continue
            if now - t <= self.recent:
                break
            if last_kept is not None and t - last_kept < self.thin:
                f.unlink(missing_ok=True)
            else:
                last_kept = t
        files = sorted(AUTO_DIR.glob("*.jpg"))
        for f in files[:-self.keep]:
            f.unlink(missing_ok=True)


def list_auto(limit=200):
    if not AUTO_DIR.exists():
        return []
    return [f.name for f in sorted(AUTO_DIR.glob("*.jpg"), reverse=True)[:limit]]


def load_auto(name):
    p = AUTO_DIR / Path(name).name  # パス外参照を防ぐ
    return imread(p) if p.exists() else None


def thumb_url(img, w=200):
    return to_data_url(img, max_w=w)
