"""荘園ナビのアイコン(icon.ico / web/icon.png)を生成する。

デザイン: 夜の荘園を思わせる濃紺の角丸 + 金の羅針盤 + 赤い北針。
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
S = 1024  # 高解像度で描いて縮小(きれいなアンチエイリアス)
GOLD = (217, 180, 90)
GOLD_D = (150, 118, 52)
RED = (214, 72, 62)
BG1, BG2 = (34, 38, 52), (14, 16, 22)


def draw_small():
    """16〜32px用: 細部を省き、リングと針を太く。"""
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, S, S], radius=220, fill=BG1 + (255,))
    c, R = S / 2, 400
    d.ellipse([c - R, c - R, c + R, c + R], outline=GOLD + (255,), width=110)
    L, Wd = 330, 120
    d.polygon([(c, c - L), (c + Wd, c), (c - Wd, c)], fill=RED + (255,))
    d.polygon([(c, c + L), (c + Wd, c), (c - Wd, c)], fill=GOLD + (255,))
    return im


def draw():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # 背景: 角丸 + 縦グラデーション
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        gd.line([(0, y), (S, y)], fill=tuple(int(BG1[i] * (1 - t) + BG2[i] * t) for i in range(3)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([24, 24, S - 24, S - 24], radius=210, fill=255)
    im.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(im)
    c = S / 2
    # 外枠の細い金線
    d.rounded_rectangle([56, 56, S - 56, S - 56], radius=180, outline=GOLD_D + (180,), width=6)

    # 羅針盤のリング
    R = 330
    d.ellipse([c - R, c - R, c + R, c + R], outline=GOLD + (255,), width=34)
    d.ellipse([c - R + 58, c - R + 58, c + R - 58, c + R - 58], outline=GOLD_D + (200,), width=8)
    # 目盛り (12本、東西南北は長く)
    for k in range(12):
        a = math.radians(k * 30)
        r0 = R - 60 if k % 3 == 0 else R - 40
        r1 = R - 20
        d.line([(c + r0 * math.sin(a), c - r0 * math.cos(a)), (c + r1 * math.sin(a), c - r1 * math.cos(a))],
               fill=GOLD + (255,), width=14 if k % 3 == 0 else 8)

    # 針 (北=赤 / 南=金)。菱形を2つ
    L, Wd = 250, 62
    d.polygon([(c, c - L), (c + Wd, c), (c - Wd, c)], fill=RED + (255,))
    d.polygon([(c, c + L), (c + Wd, c), (c - Wd, c)], fill=GOLD + (255,))
    # 針の陰影(右半分を少し暗く)
    d.polygon([(c, c - L), (c + Wd, c), (c, c)], fill=(170, 52, 45, 255))
    d.polygon([(c, c + L), (c + Wd, c), (c, c)], fill=GOLD_D + (255,))
    # 中心
    d.ellipse([c - 40, c - 40, c + 40, c + 40], fill=BG2 + (255,), outline=GOLD + (255,), width=14)

    # ほんのり光彩
    glow = im.filter(ImageFilter.GaussianBlur(6))
    out = Image.alpha_composite(glow, im)
    return out


def main():
    big = draw()
    small = draw_small()
    imgs = [(small if n <= 32 else big).resize((n, n), Image.LANCZOS) for n in (16, 24, 32, 48, 64, 128, 256)]
    imgs[-1].save(ROOT / "icon.ico", format="ICO", sizes=[im.size for im in imgs], append_images=imgs[:-1])
    (ROOT / "web").mkdir(exist_ok=True)
    big.resize((128, 128), Image.LANCZOS).save(ROOT / "web" / "icon.png")
    print("ok")


if __name__ == "__main__":
    main()
