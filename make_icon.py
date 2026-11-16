"""荘園手記のアイコン (icon.ico / web/icon.png / web/icon-1024.png) を生成する。

デザイン: 夜の濃紺に、金で縁取った革装の「手記」。表紙に荘園の門(尖頭アーチ)と星の紋章、深紅のしおり紐。
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
    # 本の後ろにほのかな光
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([S * .2, S * .16, S * .8, S * .88], fill=GOLD + (34,))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S * .09)))
    d = ImageDraw.Draw(im)
    lw = S * (0.05 if small else 0.026)
    bx0, by0, bx1, by1 = S * 0.25, S * 0.15, S * 0.73, S * 0.83   # 表紙
    rad = S * 0.045

    def rrect_ring(box, r, w, fill_rgba, inner_rgba=None):
        m = Image.new("L", (S, S), 0); md = ImageDraw.Draw(m)
        md.rounded_rectangle(box, radius=r, fill=255)
        if inner_rgba is None:
            md.rounded_rectangle([box[0] + w, box[1] + w, box[2] - w, box[3] - w], radius=max(1, r - w), fill=0)
        im.paste(Image.new("RGBA", (S, S), fill_rgba), (0, 0), m)

    # ページの小口 (表紙の右にのぞく紙)
    if not small:
        d.rounded_rectangle([bx1 - S * .02, by0 + S * .03, bx1 + S * .035, by1 - S * .03], radius=int(S * .02), fill=(226, 214, 186, 255))
        for i in range(1, 6):
            y = by0 + S * .03 + (by1 - by0 - S * .06) * i / 6
            d.line([(bx1 - S * .005, y), (bx1 + S * .03, y)], fill=(176, 160, 128, 255), width=int(S * .004))
    # 革の表紙 (縦グラデーション)
    leather = Image.new("RGBA", (1, S))
    for y in range(S):
        t = y / (S - 1)
        leather.putpixel((0, y), (int(64 - 26 * t), int(36 - 14 * t), int(40 - 16 * t), 255))
    leather = leather.resize((S, S))
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle([bx0, by0, bx1, by1], radius=int(rad), fill=255)
    im.paste(leather, (0, 0), m)
    # 金の縁
    rrect_ring([bx0, by0, bx1, by1], rad, lw, GOLD + (255,))
    # 背表紙の線
    sx = bx0 + S * (0.085 if small else 0.07)
    d.rectangle([sx - lw * .35, by0 + lw, sx + lw * .35, by1 - lw], fill=GOLD + (255,))
    cx = (sx + bx1) / 2
    if not small:
        # 内側の細い飾り枠
        rrect_ring([sx + S * .035, by0 + S * .045, bx1 - S * .04, by1 - S * .045], S * .02, lw * .4, GOLD + (120,))
    # 表紙の紋章: 尖頭アーチ + 星
    aw = S * (0.20 if small else 0.15)
    ys, yb = S * (0.55 if small else 0.56), S * (0.68 if small else 0.67)
    m = Image.new("L", (S, S), 0); md = ImageDraw.Draw(m)
    out, ya = arch_points(cx - aw / 2, cx + aw / 2, ys, aw * 0.82)
    md.polygon([(cx - aw / 2, yb)] + out + [(cx + aw / 2, yb)], fill=255)
    w2 = lw * (1.0 if small else 0.9)
    inn, _ = arch_points(cx - aw / 2 + w2, cx + aw / 2 - w2, ys, aw * 0.82 - w2)
    md.polygon([(cx - aw / 2 + w2, yb - w2)] + inn + [(cx + aw / 2 - w2, yb - w2)], fill=0)
    im.paste(Image.new("RGBA", (S, S), GOLD + (255,)), (0, 0), m)
    star(d, cx, ya - S * (0.075 if small else 0.06), S * (0.07 if small else 0.05), S * (0.02 if small else 0.013), (255, 236, 190, 255))
    # しおり紐 (深紅)
    rx, rw = bx1 - S * 0.14, S * (0.05 if small else 0.04)
    rb = by1 + S * (0.09 if small else 0.08)
    d.polygon([(rx - rw / 2, by1 - lw), (rx + rw / 2, by1 - lw), (rx + rw / 2, rb), (rx, rb - rw * 0.7), (rx - rw / 2, rb)], fill=(168, 44, 52, 255))
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
