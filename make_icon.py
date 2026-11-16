"""荘園ナビのアイコン (icon.ico / web/icon.png / web/icon-1024.png) を生成する。

デザイン: 夜の濃紺に、金の細線で「荘園の門 (ゴシックの尖頭アーチ)」と「導きの星」。
シンプル・高コントラストで、小さいサイズでも形が分かるようにする。
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
S = 4096  # 4倍で描いて縮小 (アンチエイリアス)
GOLD = (222, 190, 120)
BG_TOP, BG_BOT = (30, 33, 44), (10, 11, 15)


def arch_points(x0, x1, ys, r, n=120):
    """尖頭アーチ (左右2つの円弧) の輪郭点。左下 -> 頂点 -> 右下"""
    xm = (x0 + x1) / 2
    cl, cr = x0 + r, x1 - r                      # 左弧の中心x / 右弧の中心x
    ya = ys - math.sqrt(r * r - (xm - cl) ** 2)  # 頂点のy
    pts = []
    a_end = math.atan2(ya - ys, xm - cl)         # 左弧: 180度 -> 頂点
    for i in range(n + 1):
        a = math.pi + (a_end + 2 * math.pi - math.pi) * i / n if a_end < 0 else math.pi
        pts.append((cl + r * math.cos(a), ys + r * math.sin(a)))
    a0 = math.atan2(ya - ys, xm - cr)            # 右弧: 頂点 -> 0度
    for i in range(n + 1):
        a = a0 + (0 - a0) * i / n
        pts.append((cr + r * math.cos(a), ys + r * math.sin(a)))
    return pts, ya


def star(d, cx, cy, R, r, fill):
    """4方向に尖ったきらめき星"""
    pts = []
    for i in range(8):
        a = -math.pi / 2 + i * math.pi / 4
        rr = R if i % 2 == 0 else r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def draw(small=False, full=False):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # 背景: 縦グラデーションの角丸
    grad = Image.new("RGBA", (1, S))
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel((0, y), tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)) + (255,))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=0 if full else int(S * 0.225), fill=255)
    im.paste(grad, (0, 0), mask)
    # 門の後ろにほのかな光
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([S * .22, S * .2, S * .78, S * .86], fill=GOLD + (36,))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S * .08)))

    d = ImageDraw.Draw(im)
    lw = S * (0.058 if small else 0.036)
    x0, x1 = S * 0.29, S * 0.71
    ys, yb = S * 0.57, S * 0.80
    R = S * 0.34

    def ring(xa, xb, rr, w, alpha):
        """尖頭アーチの枠 (外形から内形をくり抜く) を金で塗る"""
        m = Image.new("L", (S, S), 0)
        md = ImageDraw.Draw(m)
        out, _ = arch_points(xa, xb, ys, rr)
        md.polygon([(xa, yb)] + out + [(xb, yb)], fill=255)
        inn, _ = arch_points(xa + w, xb - w, ys, rr - w)
        md.polygon([(xa + w, yb + 1)] + inn + [(xb - w, yb + 1)], fill=0)
        im.paste(Image.new("RGBA", (S, S), GOLD + (alpha,)), (0, 0), m)

    ring(x0, x1, R, lw, 255)
    _, ya = arch_points(x0, x1, ys, R)
    if not small:
        ring(x0 + S * 0.075, x1 - S * 0.075, R - S * 0.075, lw * 0.42, 130)
        d.rectangle([S / 2 - lw * 0.28, ya + S * 0.17, S / 2 + lw * 0.28, yb], fill=GOLD + (190,))
    # 地面の線
    d.rounded_rectangle([S * 0.22, yb - lw * 0.1, S * 0.78, yb + lw * 0.9], radius=int(lw * 0.45), fill=GOLD + (255,))
    # 導きの星
    star(d, S / 2, S * 0.135, S * (0.10 if small else 0.075), S * (0.028 if small else 0.018), (255, 236, 190, 255))
    return im


def main():
    big, small = draw(False), draw(True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [(small if s <= 32 else big).resize((s, s), Image.LANCZOS) for s in sizes]
    imgs[-1].save(ROOT / "icon.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    big.resize((1024, 1024), Image.LANCZOS).save(ROOT / "web" / "icon-1024.png")
    # iPhone/Android 用: 角丸なし (OS が自分で角を丸める)
    draw(False, full=True).resize((1024, 1024), Image.LANCZOS).convert("RGB").save(ROOT / "web" / "icon-full.png")
    big.resize((128, 128), Image.LANCZOS).save(ROOT / "web" / "icon.png")
    # 確認用
    prev = Image.new("RGBA", (1024 + 256 + 64 + 32 + 40, 1024), (60, 60, 60, 255))
    x = 0
    for s in (1024, 256, 64, 32):
        im = big if s > 32 else small
        prev.alpha_composite(im.resize((s, s), Image.LANCZOS), (x, 0)); x += s + 10
    return prev


if __name__ == "__main__":
    import sys
    p = main()
    if len(sys.argv) > 1:
        p.save(sys.argv[1])
    print("ok")
