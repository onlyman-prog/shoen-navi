"""ランク戦の試合前画面をOCRで読み、BAN情報を自動で拾う。

サバイバー視点の流れ (YouTubeのランク戦配信で確認):
  1. 「タップして相手のハンター人格を0/2つブロック」 + 「【マップ名】へ」  … 画面上部
  2. 「相手の「心の獣」/「歯医者」がブロックされました。」             … 画面上部 (自分たちがBANしたハンター)
  3. 直後の約2秒、画面左上に写真カードが最大3枚 = ハンターにBANされたサバイバー
     (カード下部に名前。長い名前は「脱出マ..」のように省略される)
"""
import difflib
import re
import time

from pathlib import Path

import cv2
import numpy as np

import ocr

try:
    import vision  # 学習したカード画像の保存/照合に使う
except Exception:
    vision = None

MAPS = ["軍需工場", "赤の教会", "聖心病院", "湖景村", "月の河公園", "レオの思い出", "永眠町", "中華街",
        "罪の森", "クレイバーグ競馬場", "ホワイトサンド精神病院", "黄金の石窟"]

# 画面に対する割合 (x0, y0, x1, y1)。ウィンドウの縦横比の違いを吸収できるよう広めに取る
TOP_BAND = (0.0, 0.0, 1.0, 0.18)
CARDS = (0.03, 0.06, 0.48, 0.34)
LOBBY = (0.12, 0.40, 0.80, 0.66)  # ハンター視点ロビー: サバイバーの頭上のキャラ名


def crop(img, r):
    h, w = img.shape[:2]
    return img[int(r[1] * h):int(r[3] * h), int(r[0] * w):int(r[2] * w)]


def clean(s):
    return re.sub(r"[\s「」『』・.,、。…:;'\"`\-ー_|!！?？()（）\[\]【】]", "", s)


def norm(n):
    return re.sub(r"[「」\s]", "", n)


def fuzzy(text, names, min_len=2, cutoff=0.6):
    """OCR文字列 text に最も近い名前。省略表記(先頭一致)にも対応。"""
    t = clean(text)
    if len(t) == 1 and min_len <= 2:
        # 1文字しか読めなくても、その字で始まる名前が1つだけなら採用 (例: 「神」→「神童」)
        hit = [n for n in names if norm(n).startswith(t)]
        return hit[0] if len(hit) == 1 else None
    if len(t) < min_len:
        return None
    best, best_s = None, 0.0
    for n in names:
        nn = norm(n).replace("ー", "")
        # 省略されている可能性があるので、名前の先頭を同じ長さに切って比べる
        a = difflib.SequenceMatcher(None, t, nn[:len(t)]).ratio()
        b = difflib.SequenceMatcher(None, t, nn).ratio()
        s = max(a * (0.9 if len(t) < len(nn) else 1.0), b)
        # 前後が切れて真ん中だけ見えている名前 (例: 「空エンジニア」→航空エンジニア)
        if len(t) >= 3 and t in nn:
            s = max(s, 0.9)
        if s > best_s:
            best, best_s = n, s
    return best if best_s >= cutoff else None


def has_cards(img):
    """左上にBANカード(明るいベージュの枠)が出ていそうか。OCR前の軽い判定。"""
    roi = crop(img, CARDS)
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m = (hsv[:, :, 2] > 170) & (hsv[:, :, 1] < 80)
    return m.mean() > 0.08


def has_book(img):
    """画面中央に本(BAN/キャラ選択の一覧)が開いているか。"""
    c = crop(img, (0.2, 0.15, 0.8, 0.85))
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 90)).mean() > 0.25


def find_cards(img):
    """左上のBANカード(写真)を検出して、左から順に (カード画像, 名前欄画像) を返す。"""
    roi = crop(img, CARDS)
    H = img.shape[0]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m = ((hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w >= H * 0.05 and h >= H * 0.07 and 1.0 < h / w < 1.6 and h < H * 0.3:
            boxes.append((x, y, w, h))
    out = []
    for x, y, w, h in sorted(boxes)[:3]:
        card = roi[y:y + h, x:x + w]
        label = roi[y + int(h * 0.80):y + h - 1, x + 2:x + w - 2]
        out.append((card, label))
    return out


def read_label(label):
    """名前欄を拡大してOCR。そのままと2値化の両方を試す。"""
    if label.size == 0:
        return []
    g = cv2.cvtColor(label, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = cv2.copyMakeBorder(bw, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return [" ".join(ocr.read(cv2.cvtColor(x, cv2.COLOR_GRAY2BGR), 1.0)) for x in (g, bw)]


class CardMemory:
    """OCRで名前が分かったカードの見た目を保存し、次回は画像でも照合する(使うほど賢くなる)。"""
    SIZE = (48, 60)

    def __init__(self):
        self.dir = (vision.DATA / "cards") if vision else None
        self.db = {}
        if self.dir and self.dir.exists():
            for d in self.dir.iterdir():
                name = (d / "name.txt").read_text(encoding="utf-8") if (d / "name.txt").exists() else None
                if name:
                    self.db[name] = [self._feat(vision.imread(f)) for f in d.glob("*.png")]

    def add_face(self, name, face):
        """本から集めた顔写真(枠なし)も照合に使う。"""
        self.db.setdefault(name, []).append(
            cv2.resize(face, (48, 48), interpolation=cv2.INTER_AREA).astype(np.float32))

    def load_faces(self, names):
        gi = Path(__file__).parent / "web" / "gi"
        if not (vision and gi.exists()):
            return
        for n in names:
            f = gi / f"{vision.key(n)}.png"
            if f.exists():
                im = vision.imread(f)
                if im is not None:
                    self.add_face(n, im)

    def _feat(self, card):
        # 枠(ベージュ)と名前欄を除いた顔写真部分(カラー)
        h, w = card.shape[:2]
        face = card[int(h * 0.08):int(h * 0.76), int(w * 0.10):int(w * 0.90)]
        return cv2.resize(face, (48, 48), interpolation=cv2.INTER_AREA).astype(np.float32)

    @staticmethod
    def _sim(a, b):
        # b の中央部分を a の上で少しずらしながら、色チャンネルごとに相関を取る
        t = b[6:42, 6:42]
        return float(np.mean([cv2.matchTemplate(a[:, :, c], t[:, :, c], cv2.TM_CCOEFF_NORMED).max()
                              for c in range(3)]))

    def match(self, card, cutoff=0.68, margin=0.08):
        f = self._feat(card)
        scores = sorted(((max(self._sim(f, t) for t in ts), n) for n, ts in self.db.items() if ts), reverse=True)
        if not scores or scores[0][0] < cutoff:
            return None
        if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
            return None
        return scores[0][1]

    def add(self, name, card):
        if not self.dir:
            return
        d = self.dir / vision.key(name)
        d.mkdir(parents=True, exist_ok=True)
        (d / "name.txt").write_text(name, encoding="utf-8")
        files = sorted(d.glob("*.png"))
        if len(files) >= 5:
            return
        vision.imwrite(d / f"{int(time.time() * 1000)}.png", card)
        self.db.setdefault(name, []).append(self._feat(card))


class RankWatcher:
    def __init__(self, survivors, hunters):
        self.survivors, self.hunters = survivors, hunters
        self.memory = CardMemory()
        self.memory.load_faces(survivors + hunters)
        self.harvester = IconHarvester(survivors + hunters, self.memory, survivors)
        self.reset()
        self.last_seen = 0.0

    def active(self, now=None):
        """試合前画面の最中か(この間は短い間隔で読む)。"""
        now = now or time.time()
        return now < self.card_until or now - self.last_seen < 25

    def read_cards(self, img):
        """左上カードを読んで、新しく分かったBANキャラを返す。
        サバイバー視点ならBANされたサバイバー、ハンター視点ならBANされた(自分の)ハンター。"""
        names = self.hunters if self.side == "h" else self.survivors
        new = []
        for card, label in find_cards(img):
            name = None
            for txt in read_label(label):
                name = fuzzy(txt, names)
                if name:
                    break
            if name:
                self.memory.add(name, card)
            else:
                name = self.memory.match(card)
                if name not in names:
                    name = None
            if name and name not in self.bans and name not in new:
                new.append(name)
        if new:
            self.bans = (self.bans + new)[:3]
        return new

    def reset(self, side="s"):
        self.side = side          # "s"=サバイバー視点 / "h"=ハンター視点
        self.map = None
        self.blocked = []         # 自分たちがBANしたキャラ
        self.bans = []            # 相手にBANされたキャラ(左上カード)
        self.picks = {}           # ハンター視点: 相手サバイバーのピック {名前: 最後に見えた時刻}
        self.sent_picks = []
        self.card_until = 0.0
        self.lobby_until = 0.0
        self.lobby_start = 0.0
        self.last_seen = 0.0

    def feed(self, img, now=None):
        """1フレーム処理して、新しく分かったことをイベントのリストで返す。"""
        now = now or time.time()
        ev = []
        top = " ".join(ocr.read(crop(img, TOP_BAND), scale=1.5 if img.shape[0] < 900 else 1.0))
        # OCRは「ブ」を「プ」、「ー」を「-」と読みがちなので揃える
        top_c = clean(top).replace("プロック", "ブロック")

        # 1. BAN開始: 「相手のハンター人格を…ブロック」(サバ視点) /「相手のサバイバー人格を…」(ハン視点)
        side = None
        if "人格" in top_c and "ブロック" in top_c and "ブロックされました" not in top_c:
            if "ハンタ" in top_c:
                side = "s"
            elif "サバイ" in top_c or "バイバ" in top_c:
                side = "h"
        if side:
            if now - self.last_seen > 60 or side != self.side:  # 新しい試合
                self.reset(side)
                ev.append({"type": "newMatch", "side": side})
            self.last_seen = now
            m = re.search(r"[【\[](.+?)[】\]]", top)
            mp = fuzzy(m.group(1), MAPS) if m else None
            if mp and mp != self.map:
                self.map = mp
                ev.append({"type": "map", "map": mp, "side": self.side})

        # 2. 「相手のA/B/Cがブロックされました。」= 自分たちがBANしたキャラ
        if "ブロックされました" in top_c:
            self.last_seen = now
            m = re.search(r"相手の(.+?)が[ブプ]ロ", re.sub(r"\s", "", top))
            body = m.group(1) if m else ""
            parts = [x for x in re.split(r"[/／」]", body) if clean(x)]
            names = self.survivors if self.side == "h" else self.hunters
            got = []
            for x in parts:
                n = fuzzy(x, names, min_len=2, cutoff=0.5)
                if n and n not in got:
                    got.append(n)
            if got and got != self.blocked:
                self.blocked = got
                ev.append({"type": "survivorBlocks" if self.side == "h" else "hunterBlocks",
                           "names": got, "hunters": got, "side": self.side})
            self.card_until = now + 10
            if self.side == "h" and not self.lobby_until:
                self.lobby_start, self.lobby_until = now + 3, now + 90
                self.picks = {}

        # 3. 相手にBANされたキャラ (左上のカード)
        if now < self.card_until or now - self.last_seen < 20:
            if self.read_cards(img):
                if self.side == "h":
                    ev.append({"type": "hunterBans", "names": self.bans, "side": "h"})
                else:
                    ev.append({"type": "survivorBans", "bans": self.bans, "side": "s"})

        # 4. ハンター視点: ロビーで相手サバイバーのキャラ名(頭上の文字)を読む
        if self.side == "h" and self.lobby_start <= now < self.lobby_until and not has_book(img):
            if "エリア選択を待って" in top_c:
                self.lobby_until = -1  # ピック終了
            else:
                for ln in ocr.read(crop(img, LOBBY), scale=3.0 if img.shape[0] < 900 else 2.0):
                    n = fuzzy(ln, self.survivors, cutoff=0.75)
                    if n:
                        self.picks[n] = now
                cur = [n for n, t in sorted(self.picks.items(), key=lambda x: -x[1])[:4]]
                if sorted(cur) != sorted(self.sent_picks):
                    self.sent_picks = cur
                    ev.append({"type": "survivorPicks", "names": cur, "side": "h"})
        return ev


# ---------------- ゲーム内の顔写真を集める ----------------
BAD_OVERLAY = ("体験", "験", "時間", "所有", "使用中", "選択", "希望", "ハンタ", "サバイ", "認知", "???", "？？")


def normalize_face(face):
    """白い枠の残りを削り、内側を顔中心の正方形に整える(「新」の札などもほぼ消える)。"""
    if face is None or face.size == 0:
        return face
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    white = (hsv[:, :, 2] > 180) & (hsv[:, :, 1] < 50)
    h, w = white.shape
    t, b, l, r = 0, h, 0, w
    while t < h * 0.15 and white[t, l:r].mean() > 0.5:
        t += 1
    while b > h * 0.85 and white[b - 1, l:r].mean() > 0.5:
        b -= 1
    while l < w * 0.15 and white[t:b, l].mean() > 0.5:
        l += 1
    while r > w * 0.85 and white[t:b, r - 1].mean() > 0.5:
        r -= 1
    f = face[t:b, l:r]
    h, w = f.shape[:2]
    # 内側に少し寄せる(枠の影・札の端を落とす)
    m = int(min(h, w) * 0.07)
    f = f[m:h - m, m:w - m]
    h, w = f.shape[:2]
    # 「使用中」の帯や「新」の判子は写真の上端に重なるので、上を2割落として顔に寄せる
    f = f[int(h * 0.2):, :]
    h, w = f.shape[:2]
    side = min(h, w)
    x0 = (w - side) // 2
    return f[:side, x0:x0 + side]


def has_overlay(face):
    """「使用中」(上部の紺の帯) や「新」(左上の赤い判子) が写っているか。"""
    h, w = face.shape[:2]
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    corner = hsv[:int(h * 0.3), :int(w * 0.3)]
    red = (((corner[:, :, 0] < 8) | (corner[:, :, 0] > 172)) & (corner[:, :, 1] > 150) & (corner[:, :, 2] > 110)).mean()
    return red > 0.08


def banner_in_use(img, rect):
    """元画像で写真の上端付近をOCRし、「使用中」などの帯が掛かっているか。"""
    x0, y0, x1, y1 = rect
    h = y1 - y0
    reg = img[max(0, int(y0 - 0.15 * h)):int(y0 + 0.35 * h), max(0, x0 - 5):x1]
    txt = clean(" ".join(ocr.read(reg, 3.0)))
    return any(k in txt for k in ("使用", "用中", "選択", "希望"))


def quality(face, banner=False):
    """大きいほど良い。札が写っていたら大きく減点(札なしが見つかれば差し替わる)。"""
    return face.shape[0] * (0.3 if banner or has_overlay(face) else 1.0)


def good_face(face):
    """切り出した顔写真として使えるか。灰色(BAN/使用中)、ベージュ背景だらけ、文字の重なりを除外。"""
    if face is None or face.size == 0:
        return False
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    if hsv[:, :, 1].mean() < 30 or cv2.cvtColor(face, cv2.COLOR_BGR2GRAY).std() < 30:
        return False
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    beige = ((h >= 8) & (h <= 30) & (s > 25) & (s < 120) & (v > 120)).mean()
    if beige > 0.35:  # 紙(本・一覧)の背景ばかり = 顔ではない
        return False
    # 写真全体と、札が付きやすい上部を拡大したもの両方で文字の重なりを確認
    top = face[:max(8, int(face.shape[0] * 0.35))]
    bottom = face[int(face.shape[0] * 0.65):]
    txt = clean(" ".join(ocr.read(face, 2.0) + ocr.read(top, 3.5) + ocr.read(bottom, 3.5)))
    return not any(k in txt for k in BAD_OVERLAY)
class IconHarvester:
    """キャラ選択/BAN/マイスタイル等の「写真が並んだ画面」から、名前付きの顔写真を切り出して保存する。

    1. 画面の名前をOCRし、キャラ名として読めたものを基準点にする
    2. 基準点どうしの間隔から、写真の並び(横・縦の間隔)を推定する
       (等間隔に並んでいない名前 = 一覧やポップアップ はここで除外)
    3. 並びから全マスの位置を出し、1マスずつ名前欄を拡大OCR
    4. 名前の上にある白いポラロイド枠を探し、その内側を顔写真として保存
    """

    def __init__(self, names, memory=None, survivors=None):
        self.names = names
        self.survivors = set(survivors or [])
        self.hunters = [n for n in names if n not in self.survivors]
        self.memory = memory
        # UIからそのまま使えるよう web/gi に保存
        self.dir = (Path(__file__).parent / "web" / "gi") if vision else None
        self.have = {}
        if self.dir and self.dir.exists():
            for f in self.dir.glob("*.png"):
                # 既に保存済みの画像は確定扱い(後から上書きしない。足りないキャラだけ集める)
                self.have[f.stem] = float("inf")

    @staticmethod
    def _sig(im):
        g = cv2.cvtColor(cv2.resize(im, (32, 32), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32).ravel()
        g -= g.mean()
        return g / (np.linalg.norm(g) + 1e-6)

    def _dup(self, k, face):
        """別キャラとして保存済みの顔とほぼ同じなら True (「女王蜂」→「血の女王」のような名前の読み違い対策)。"""
        s = self._sig(face)
        for f in self.dir.glob("*.png"):
            if f.stem == k:
                continue
            im = vision.imread(f)
            if im is not None and float(s @ self._sig(im)) > 0.85:
                return True
        return False

    # --- 並びの推定 ---
    @staticmethod
    def _spacing(anchors, H):
        """同じ行/列に並ぶ基準点から、横・縦の間隔を推定。"""
        dxs, dys = [], []
        for i, (ax, ay) in enumerate(anchors):
            row = [abs(bx - ax) for j, (bx, by) in enumerate(anchors) if j != i and abs(by - ay) < 0.02 * H]
            col = [abs(by - ay) for j, (bx, by) in enumerate(anchors) if j != i and abs(bx - ax) < 0.02 * H]
            if row:
                dxs.append(min(row))
            if col:
                dys.append(min(col))
        # 飛び飛びにしか読めないと2マス分の距離になるので、最小の間隔を採用
        dxs = [v for v in dxs if 0.08 * H < v < 0.35 * H]
        dys = [v for v in dys if 0.10 * H < v < 0.40 * H]
        dx = float(min(dxs)) if dxs else None
        dy = float(min(dys)) if dys else None
        return dx, dy

    @staticmethod
    def _snap_x(img, x0, y0, x1, y1):
        """写真(x0..x1)の左右に白い枠があるか探して位置を合わせる。見つからなければ None。"""
        H, W = img.shape[:2]
        w = x1 - x0
        hsv = cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2HSV)
        white = ((hsv[:, :, 2] > 185) & (hsv[:, :, 1] < 45)).mean(axis=0) > 0.8
        lo, hi = max(0, int(x0 - 0.35 * w)), min(W - 1, int(x1 + 0.35 * w))
        cols = [x for x in range(lo, hi) if white[x]]
        mid = (x0 + x1) / 2
        left = [x for x in cols if x < mid]
        right = [x for x in cols if x > mid]
        if not left or not right:
            return None
        nl, nr = max(left), min(right)
        if not (0.75 * w < nr - nl < 1.3 * w):
            return None
        return nl + 2, nr - 1

    def _read_cell(self, img, cx, cy, d, names):
        H = img.shape[0]
        lw, lh = 0.5 * d, 0.045 * H
        lab = img[int(max(0, cy - lh)):int(cy + lh), int(max(0, cx - lw)):int(cx + lw)]
        # 拡大しすぎると「記」が「三一ロ」のように部首で割れるので、複数の倍率で試す
        for sc in (1.25, 2.0, 4.0):
            for t, bx, by, bw, bh in ocr.read_boxes(lab, sc):
                n = fuzzy(t, names, cutoff=0.75)
                if n:
                    return n, (cx - lw + bx + bw / 2, cy - lh + by + bh / 2, bh)
        return None, None

    def _check_half(self, img, anchors, d, names, horizontal):
        if d / 2 < 0.07 * img.shape[0]:
            return d
        for ax, ay in anchors[:3]:
            for sgn in (1, -1):
                cx, cy = (ax + sgn * d / 2, ay) if horizontal else (ax, ay + sgn * d / 2)
                if self._read_cell(img, cx, cy, d / 2, names)[0]:
                    return d / 2
        return d

    @staticmethod
    def _aligned(anchors, dx, dy, H):
        """推定した間隔ぴったりに隣がある基準点だけ残す。"""
        keep = []
        for i, (ax, ay) in enumerate(anchors):
            for j, (bx, by) in enumerate(anchors):
                if i == j:
                    continue
                ddx, ddy = abs(ax - bx), abs(ay - by)
                for k in (1, 2, 3):
                    if dx and ddy < 0.02 * H and abs(ddx - k * dx) < 0.06 * dx * k:
                        keep.append((ax, ay))
                    elif dy and ddx < 0.02 * H and abs(ddy - k * dy) < 0.06 * dy * k:
                        keep.append((ax, ay))
        return list(dict.fromkeys(keep))

    # --- ポラロイド枠から顔写真を切り出す ---
    @staticmethod
    def _face(img, cx, cy, th, dx, with_rect=False):
        """名前(中心cx,cy, 文字高th)のすぐ上の写真を切り出す。
        名前欄の上端から上へ走査し、白い枠(行全体が白)に挟まれた範囲を写真とみなす。"""
        H, W = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        white = (hsv[:, :, 2] > 185) & (hsv[:, :, 1] < 45)
        sx0, sx1 = int(max(0, cx - 0.25 * dx)), int(min(W, cx + 0.25 * dx))

        def row_white(y):
            return white[y, sx0:sx1].mean() > 0.8

        y = int(cy - th * 0.7)
        lim = int(max(1, cy - 1.8 * dx))
        while y > lim and row_white(y):          # 名前欄〜写真の下枠
            y -= 1
        y_bot = y
        while y > lim and not row_white(y):      # 写真
            y -= 1
        y_top = y
        h = y_bot - y_top
        if not (0.35 * dx < h < 1.5 * dx):
            return (None, None) if with_rect else None
        rows = white[y_top + int(h * 0.1):y_bot - int(h * 0.1)]

        def col_white(x):
            return rows[:, x].mean() > 0.8

        xl = int(cx)
        while xl > max(0, cx - 0.8 * dx) and not col_white(xl):
            xl -= 1
        xr = int(cx)
        while xr < min(W - 1, cx + 0.8 * dx) and not col_white(xr):
            xr += 1
        w = xr - xl
        if not (0.4 * dx < w < 1.3 * dx) or not (0.6 < h / w < 1.5):
            return (None, None) if with_rect else None
        face = img[y_top + 2:y_bot - 1, xl + 2:xr - 1]
        return (face, (xl + 2, y_top + 2, xr - 1, y_bot - 1)) if with_rect else face

    def feed(self, img):
        if img is None or not self.dir or not has_book(img):
            return []
        H, W = img.shape[:2]
        anchors, sides = [], []
        for t, x, y, w, h in ocr.read_boxes(crop(img, (0.05, 0.08, 0.95, 0.97)), 1.5 if H >= 700 else 2.5):
            n = fuzzy(t, self.names, cutoff=0.75)
            if n:
                anchors.append((x + w / 2 + 0.05 * W, y + h / 2 + 0.08 * H))
                sides.append(n in self.survivors)
        if not anchors:
            return []
        # このページはサバイバー/ハンターどちらの一覧か(多数決)
        names = self.survivors if sum(sides) * 2 >= len(sides) else self.hunters
        dx, dy = self._spacing(anchors, H)
        if not dx:
            return []
        anchors = self._aligned(anchors, dx, dy, H)
        if len(anchors) < 2:
            return []
        # 名前が1つおきにしか読めないと間隔を2倍に見積もるので、半分の位置に名前があるか確かめる
        dx = self._check_half(img, anchors, dx, names, horizontal=True)
        if dy:
            dy = self._check_half(img, anchors, dy, names, horizontal=False)
        dy = dy or dx * 1.3
        cands = []
        for ax, ay in anchors:
            for i in range(-3, 4):
                for j in range(-3, 4):
                    cx, cy = ax + i * dx, ay + j * dy
                    if 0.05 * W < cx < 0.95 * W and 0.12 * H < cy < 0.97 * H and                             all(abs(cx - a) > 0.3 * dx or abs(cy - b) > 0.3 * dy for a, b in cands):
                        cands.append((cx, cy))
        got, geo, pending = [], [], []
        for cx, cy in cands:
            name, box = self._read_cell(img, cx, cy, dx, names)
            if not name:
                continue
            k = vision.key(name)
            face, rect = self._face(img, box[0], box[1], box[2], dx, with_rect=True)
            if face is None:
                pending.append((name, box))  # 顔や髪が白くて枠と区別できなかった
                continue
            geo.append([(v - c) / dx for v, c in zip(rect, (box[0], box[1], box[0], box[1]))])
            face = normalize_face(face)
            if not good_face(face):
                continue
            q = quality(face, banner_in_use(img, rect))
            if self.have.get(k, 0) >= q:
                continue  # 既にもっと良い画像がある
            if self._dup(k, face):
                continue  # 名前の読み違い(別キャラの顔と同じ)
            self.dir.mkdir(parents=True, exist_ok=True)
            vision.imwrite(self.dir / f"{k}.png", face)
            self.have[k] = q
            if self.memory:
                self.memory.add_face(name, face)
            got.append(name)
        # 失敗したマス: 成功した写真の「名前から見た位置と大きさ」の中央値を当てはめる
        if geo and pending:
            g = np.median(np.array(geo), axis=0)
            for name, (bx, by, _) in pending:
                k = vision.key(name)
                x0, y0, x1, y1 = (int(bx + g[0] * dx), int(by + g[1] * dx), int(bx + g[2] * dx), int(by + g[3] * dx))
                if x0 < 0 or y0 < 0 or x1 > W or y1 > H or x1 - x0 < 10:
                    continue
                # 名前がはみ出していると横にずれるので、左右の白い枠を探して補正し、確認できなければ使わない
                fixed = self._snap_x(img, x0, y0, x1, y1)
                if fixed:
                    x0, x1 = fixed
                face = normalize_face(img[y0:y1, x0:x1])
                if not good_face(face):
                    continue
                q = quality(face, banner_in_use(img, (x0, y0, x1, y1)))
                if not fixed:
                    q *= 0.5  # 位置を枠で確認できなかったので仮扱い(確認できた画像が来たら差し替え)
                if self.have.get(k, 0) >= q or self._dup(k, face):
                    continue
                self.dir.mkdir(parents=True, exist_ok=True)
                vision.imwrite(self.dir / f"{k}.png", face)
                self.have[k] = q
                if self.memory:
                    self.memory.add_face(name, face)
                got.append(name)
        return got
