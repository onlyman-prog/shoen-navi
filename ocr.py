"""Windows標準の日本語OCR(Windows.Media.Ocr)で画面の文字を読む。"""
import asyncio

import cv2
import numpy as np

try:
    from winsdk.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap, BitmapAlphaMode
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.globalization import Language
    from winsdk.windows.storage.streams import DataWriter

    _engine = OcrEngine.try_create_from_language(Language("ja"))
except Exception:  # winsdk未インストール等
    _engine = None


def available():
    return _engine is not None


async def _recognize(img):
    h, w = img.shape[:2]
    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    dw = DataWriter()
    dw.write_bytes(bgra.tobytes())
    bmp = SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, w, h,
                                                 BitmapAlphaMode.PREMULTIPLIED)
    res = await _engine.recognize_async(bmp)
    return [ln.text for ln in res.lines]


def read(img, scale=2.0):
    """画像(BGR)の文字を行ごとに返す。小さい文字は拡大して読む。"""
    if _engine is None or img is None or img.size == 0:
        return []
    if scale != 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    try:
        return asyncio.run(_recognize(img))
    except RuntimeError:  # 既存イベントループ内から呼ばれた場合
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_recognize(img))
        finally:
            loop.close()


async def _recognize_boxes(img):
    h, w = img.shape[:2]
    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    dw = DataWriter()
    dw.write_bytes(bgra.tobytes())
    bmp = SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, w, h,
                                                 BitmapAlphaMode.PREMULTIPLIED)
    res = await _engine.recognize_async(bmp)
    out = []
    for ln in res.lines:
        ws = sorted(((wd.text, wd.bounding_rect) for wd in ln.words), key=lambda x: x[1].x)
        if not ws:
            continue
        # 横に大きな隙間があれば別の文字列とみなして分割(本の名前欄が1行にまとまるため)
        seg = [ws[0]]
        for wd in ws[1:]:
            prev = seg[-1][1]
            gap = wd[1].x - (prev.x + prev.width)
            if gap > max(prev.height, wd[1].height) * 1.2:
                out.append(_merge(seg))
                seg = []
            seg.append(wd)
        out.append(_merge(seg))
    return out


def _merge(seg):
    rs = [r for _, r in seg]
    x0 = min(r.x for r in rs); y0 = min(r.y for r in rs)
    x1 = max(r.x + r.width for r in rs); y1 = max(r.y + r.height for r in rs)
    return ("".join(t for t, _ in seg), x0, y0, x1 - x0, y1 - y0)


def read_boxes(img, scale=1.0):
    """文字列と位置 [(text, x, y, w, h)] を返す(座標は元画像基準)。"""
    if _engine is None or img is None or img.size == 0:
        return []
    src = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1 else img
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(_recognize_boxes(src))
    finally:
        loop.close()
    return [(t, x / scale, y / scale, w / scale, h / scale) for t, x, y, w, h in res]
