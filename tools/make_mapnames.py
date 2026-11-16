"""マップ地名ガイド画像を作る。

土台: bilibili Wiki の俯瞰図 (ハッチ位置入り) / 地名: 日本版公式ミニマップのエリア名 (wikiwiki ミニマップ)
ミニマップ座標(512x433画像) -> 俯瞰図の % 座標へ、枠の対応で線形変換する。
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "mapsrc"
OUT = ROOT / "web" / "mapnames"
FONT = "C:/Windows/Fonts/BIZ-UDGothicB.ttc"
MAPS = json.load(open(ROOT / "data" / "mapnames.json", encoding="utf-8"))


def rd(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def detect_hatches(key):
    h, p = rd(SRC / f"{key}_hatch.png"), rd(SRC / f"{key}_plain.png")
    if p.shape != h.shape:
        p = cv2.resize(p, (h.shape[1], h.shape[0]), interpolation=cv2.INTER_AREA)
    d = cv2.absdiff(h, p).max(2)
    b, g, r = [h[:, :, i].astype(int) for i in range(3)]
    m = ((d > 60) & (b > 150) & (b > r + 40)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    pts = [(cen[i][0] / h.shape[1] * 100, cen[i][1] / h.shape[0] * 100) for i in range(1, n) if st[i][4] > 2500]
    return sorted(pts, key=lambda q: (q[1], q[0]))


def to_pct(m, x, y):
    (a, b, c, d), (e, f, g, hh) = m["mini"], m["over"]
    return e + (x - a) / (c - a) * (g - e), f + (y - b) / (d - b) * (hh - f)


def text_box(draw, xy, text, font, fill, bg, pad=6, anchor="mm"):
    l, t, r, b = draw.textbbox(xy, text, font=font, anchor=anchor)
    draw.rounded_rectangle((l - pad, t - pad + 1, r + pad, b + pad), radius=8, fill=bg)
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)
    return (l - pad, t - pad, r + pad, b + pad)


def render(key, m, W=1100):
    base = rd(SRC / f"{key}_plain.png")
    rot = m.get("rotate") == "ccw"
    if rot:  # 現在のゲーム内ミニマップの向きに合わせて左90度回転
        base = cv2.rotate(base, cv2.ROTATE_90_COUNTERCLOCKWISE)
    s = W / base.shape[1]
    base = cv2.resize(base, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    base = cv2.convertScaleAbs(base, alpha=1.15, beta=8)
    H = base.shape[0]
    OUT.mkdir(parents=True, exist_ok=True)
    # 文字なしの土台 (アプリ側で地名を重ねて表示する用)。文字が映えるよう少し暗く
    cv2.imencode(".jpg", cv2.convertScaleAbs(base, alpha=0.82, beta=0), [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tofile(str(OUT / f"{key}_base.jpg"))
    layout = []
    im = Image.fromarray(cv2.cvtColor(base, cv2.COLOR_BGR2RGB)).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    f_area = ImageFont.truetype(FONT, 30)
    f_small = ImageFont.truetype(FONT, 21)
    f_hatch = ImageFont.truetype(FONT, 22)
    R = (lambda x, y: (y, 100 - x)) if rot else (lambda x, y: (x, y))
    P = lambda px, py: (R(px, py)[0] / 100 * W, R(px, py)[1] / 100 * H)
    hs = detect_hatches(key)
    hp = [P(hx, hy) for hx, hy in hs]
    # エリア名 (ハッチと重なるなら上下にずらす)
    areas, boxes = [], []
    f_long = ImageFont.truetype(FONT, 25)
    for name, x, y, *tag in m["labels"]:
        px, py = to_pct(m, x, y)
        if name in m.get("fix", {}):
            px, py = m["fix"][name]
        areas.append((name, px, py))
        cx0, cy0 = P(px, py)
        fa = f_area if len(name) <= 7 else f_long
        def cost(c):
            l, t, r, b = dr.textbbox(c, name, font=fa, anchor="mm")
            l, t, r, b = l - 8, t - 8, r + 8, b + 8
            n = sum(3 for (L, T, R, B) in boxes if l < R and r > L and t < B and b > T)
            n += sum(2 for hx, hy in hp if l - 18 < hx < r + 18 and t - 18 < hy < b + 18)
            n += 5 if (l < 0 or r > W or t < 0 or b > H) else 0
            return n + (abs(c[0] - cx0) + abs(c[1] - cy0)) / 200
        cx, cy = min([(cx0 + dx, cy0 + dy) for dx, dy in ((0, 0), (0, 40), (0, -40), (60, 0), (-60, 0), (50, 40), (-50, 40), (0, 76))], key=cost)
        boxes.append(text_box(dr, (cx, cy), name, fa, (255, 255, 255, 255), (20, 24, 40, 205)))
        layout.append({"name": name, "x": round(cx / W * 100, 2), "y": round(cy / H * 100, 2),
                       "basement": name in m.get("basement", []), "gate": m.get("gates", {}).get(name, "")})
        yy = cy + 30
        for t2, c in ([("地下室", (190, 60, 60, 235))] if name in m.get("basement", []) else []) +                      ([(m["gates"][name], (60, 110, 200, 235))] if name in m.get("gates", {}) else []):
            boxes.append(text_box(dr, (cx, yy), t2, f_small, (255, 255, 255, 255), c, pad=4))
            yy += 28
    # ハッチ: マーク + 「チャット欄で選ぶエリア / 通称」
    names = m.get("hatchNames", [])
    hinfo = []
    for i, ((hx, hy), (cx, cy)) in enumerate(zip(hs, hp)):
        area = min(areas, key=lambda a: (a[1] - hx) ** 2 + (a[2] - hy) ** 2)[0]
        if area in m.get("hatchArea", {}):
            area = m["hatchArea"][area]
        nick = names[i] if i < len(names) else ""
        hinfo.append({"x": round(cx / W * 100, 2), "y": round(cy / H * 100, 2), "area": area, "nick": nick})
        dr.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), fill=(255, 205, 40, 250), outline=(30, 20, 0, 255), width=3)
        dr.text((cx, cy + 1), "ハ", font=f_small, fill=(30, 20, 0, 255), anchor="mm")
        if nick:
            txt = "通称「" + nick + "」"
            cands = [((cx + 26, cy), "lm"), ((cx - 26, cy), "rm"), ((cx, cy + 34), "mm"), ((cx, cy - 34), "mm")]
            if cx > W * 0.72:
                cands[0], cands[1] = cands[1], cands[0]
            def bad(c):
                l, t, r, b = dr.textbbox(c[0], txt, font=f_hatch, anchor=c[1])
                l, t, r, b = l - 6, t - 6, r + 6, b + 6
                if l < 0 or r > W or t < 0 or b > H: return 99
                return sum(1 for (L, T, R, B) in boxes if l < R and r > L and t < B and b > T)
            pos, anc = min(cands, key=bad)
            boxes.append(text_box(dr, pos, txt, f_hatch, (40, 30, 0, 255), (255, 225, 120, 240), pad=4, anchor=anc))
    im = Image.alpha_composite(im, ov).convert("RGB")
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / f"{key}.jpg", quality=86)
    gates = []
    for gname, (gx, gy) in m.get("gatePos", {}).items():
        cx, cy = P(*to_pct(m, gx, gy))
        gates.append({"name": gname, "x": round(cx / W * 100, 2), "y": round(cy / H * 100, 2)})
    return {"w": W, "h": H, "base": f"mapnames/{key}_base.jpg", "labels": layout, "hatches": hinfo, "gates": gates}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    keys = sys.argv[1:] or [k for k in MAPS if not k.startswith("_")]
    info = {}
    p = OUT / "info.json"
    if p.exists():
        info = json.load(open(p, encoding="utf-8"))
    for k in keys:
        if not (SRC / f"{k}_plain.png").exists():
            print("skip", k); continue
        info[k] = render(k, MAPS[k])
        print(k, [(h["area"], h["nick"]) for h in info[k]["hatches"]])
    json.dump(info, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
