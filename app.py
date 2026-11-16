"""荘園ナビ — 第五人格の早見・BAN予測ツール (小窓デスクトップアプリ)

- 起動すると前回データを即表示 → 裏で最新情報を取得 → 画面を自動更新
- ランク戦の試合前画面を自動で読み取り(OCR): マップ / 自分たちがBANしたハンター / BANされたサバイバー
- F8: 今の画面から手動で読み取り
- --auto で起動した場合(ゲーム連動)、ゲーム終了でアプリも閉じる
"""
import ctypes
import json
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from pathlib import Path

try:  # 画面キャプチャ座標を実ピクセルに合わせる
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import webview

import scraper

try:
    import vision
except Exception as e:  # opencv等が無くても早見機能は動かす
    vision = None
    VISION_ERR = str(e)

try:
    import detect
    import ocr
    if not ocr.available():
        detect = None
except Exception:
    detect = None

ROOT = Path(__file__).parent
DATA = scraper.DATA_DIR
SETTINGS = DATA / "settings.json"
RECORDS = DATA / "records.json"
AUTO = "--auto" in sys.argv
APP_NAME = "荘園ナビ"
ICON = ROOT / "icon.ico"


def find_app_window(exclude_self=False):
    """タイトルが APP_NAME で、python(w).exe が持つウィンドウだけを返す。
    (エクスプローラーのタブ等が同じ名前のウィンドウを持つことがあるため FindWindow だけでは不可)"""
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        buf = ctypes.create_unicode_buffer(64)
        u.GetWindowTextW(h, buf, 64)
        if buf.value != APP_NAME:
            return True
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if exclude_self and pid.value == k.GetCurrentProcessId():
            return True
        hp = k.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if hp:
            name = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            ok = k.QueryFullProcessImageNameW(hp, 0, name, ctypes.byref(size))
            k.CloseHandle(hp)
            if ok and Path(name.value).name.lower() in ("python.exe", "pythonw.exe"):
                found.append(h)
                return False
        return True

    u.EnumWindows(cb, 0)
    return found[0] if found else 0

try:  # タスクバーでPythonではなく専用アイコンとして表示する
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ShoenNavi.App")
except Exception:
    pass

DEFAULT_SETTINGS = {"width": 380, "height": 700, "on_top": False, "slots": [], "auto_read": True,
                    "auto_shot": True, "pool": [], "game_icons": True}


def read_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(p, obj):
    DATA.mkdir(exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


class Api:
    def __init__(self):
        self._window = None
        self._busy = False
        self._settings = {**DEFAULT_SETTINGS, **read_json(SETTINGS, {})}
        self._matcher = None
        self._last = None          # (時刻, 画像) 直近の読取り画像。記録時の学習に使う
        self._last_auto = None
        self._lock = threading.Lock()
        self._shots = vision.AutoShots() if vision else None
        self._watcher = None
        self._harvest_t = 0.0

    # ================= JSから呼ぶ =================
    def get_data(self):
        data = scraper.load_cache()
        # ゲーム画面から集めたキャラ画像があれば使う
        gi = ROOT / "web" / "gi"
        if data and vision and self._settings.get("game_icons", True) and gi.exists():
            for c in data["chars"].values():
                f = gi / f"{vision.key(c['name'])}.png"
                if f.exists():
                    c["gameImg"] = f"gi/{f.name}?v={int(f.stat().st_mtime)}"
        return data

    def icon_stats(self):
        gi = ROOT / "web" / "gi"
        data = scraper.load_cache() or {"chars": {}}
        n = sum(1 for c in data["chars"] if vision and (gi / f"{vision.key(c)}.png").exists())
        return {"have": n, "total": len(data["chars"])}

    def set_game_icons(self, value):
        self._set("game_icons", bool(value))

    def get_settings(self):
        return {**self._settings, "vision": vision is not None, "ocr": detect is not None, "auto": AUTO,
                "game": bool(vision and vision.find_game())}

    def refresh(self):
        if self._busy:
            return False
        threading.Thread(target=self._update, daemon=True).start()
        return True

    def set_on_top(self, value):
        self._window.on_top = bool(value)
        self._set("on_top", bool(value))

    def set_pool(self, names):
        """ハンター視点: 自分が使うハンター(マイハンター)を保存。"""
        self._set("pool", [str(n) for n in names][:12])

    def set_auto_read(self, value):
        self._set("auto_read", bool(value))

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    # --- 試合記録 ---
    def get_records(self):
        return read_json(RECORDS, [])

    def add_record(self, rec):
        recs = read_json(RECORDS, [])
        rec["ts"] = int(time.time())
        recs.append(rec)
        write_json(RECORDS, recs)
        learned = 0
        # 直近10分以内に読み取った画面があれば、その枠を正解で学習
        if self._last and time.time() - self._last[0] < 600 and rec.get("bans"):
            m = self._get_matcher()
            if m and len(rec["bans"]) <= len(self._settings["slots"]):
                learned = m.learn(self._last[1], self._settings["slots"], rec["bans"])
        return {"records": recs, "learned": learned}

    def delete_record(self, ts):
        recs = [r for r in read_json(RECORDS, []) if r.get("ts") != ts]
        write_json(RECORDS, recs)
        return recs

    # --- 画面読取 ---
    def capture_preview(self):
        """枠設定用にゲーム画面を撮影して返す。"""
        if not vision:
            return {"error": "画像認識ライブラリがありません: " + VISION_ERR}
        me = find_app_window()
        hide = vision.overlaps(me, [[0, 0, 1, 1]])
        if hide:
            ctypes.windll.user32.ShowWindow(me, 0)
            time.sleep(0.25)
        try:
            img = vision.capture()
        finally:
            if hide:
                ctypes.windll.user32.ShowWindow(me, 5)
        if img is None:
            return {"error": "ゲーム画面が見つかりません（最小化していると撮れません）"}
        vision.save_capture(img)
        self._last = (time.time(), img)
        h, w = img.shape[:2]
        return {"img": vision.to_data_url(img), "w": w, "h": h}

    def save_slots(self, slots):
        self._set("slots", [[float(v) for v in s] for s in slots][:3])
        return True

    def set_auto_shot(self, value):
        self._set("auto_shot", bool(value))

    def list_shots(self):
        """自動スクショ一覧(新しい順)とサムネイル。"""
        if not vision:
            return []
        out = []
        for n in vision.list_auto():
            img = vision.load_auto(n)
            if img is not None:
                out.append({"name": n, "thumb": vision.thumb_url(img)})
        return out

    def use_shot(self, name):
        """自動スクショを枠設定/学習用の画像として使う。"""
        img = vision.load_auto(name) if vision else None
        if img is None:
            return {"error": "画像が見つかりません"}
        self._last = (time.time(), img)
        h, w = img.shape[:2]
        return {"img": vision.to_data_url(img), "w": w, "h": h}

    def read_now(self):
        """F8相当: いま撮影して読み取る。OCRでカードが読めればそれを使い、だめなら枠の画像照合。"""
        w = self._get_watcher()
        if w and vision:
            img = vision.capture()
            if img is not None:
                vision.save_capture(img)
                names = w.read_cards(img) or (w.bans if detect.has_cards(img) else [])
                if names:
                    return {"bans": w.bans}
        if not self._settings.get("slots"):
            return {"error": "BANカードを読み取れませんでした（BAN直後の約2秒間に押してください）"}
        return self._read(manual=True)

    # ================= 内部 =================
    def _set(self, k, v):
        self._settings[k] = v
        self._save()

    def _save(self):
        write_json(SETTINGS, self._settings)

    def _js(self, code):
        try:
            self._window.evaluate_js(code)
        except Exception:
            pass

    def _update(self):
        self._busy = True
        try:
            data = scraper.build(lambda d, t, m: self._js(f"onProgress({d},{t})"))
            scraper.save_cache(data)
            self._js("onUpdated(true)")
            if vision:  # 照合用アイコンを用意
                vision.ensure_icons([c for c in data["chars"].values() if c["side"] == "s"])
                with self._lock:
                    self._matcher = None
        except Exception as e:
            self._js(f"onUpdated(false, {json.dumps(str(e))})")
        finally:
            self._busy = False

    def _get_watcher(self):
        if self._watcher is None and detect:
            data = scraper.load_cache()
            if data:
                self._watcher = detect.RankWatcher(data["order"]["s"], data["order"]["h"])
        return self._watcher

    def _get_matcher(self):
        with self._lock:
            if self._matcher is None and vision:
                data = scraper.load_cache()
                if data:
                    names = data["order"]["s"]
                    vision.ensure_icons([data["chars"][n] for n in names if n in data["chars"]])
                    self._matcher = vision.Matcher(names)
            return self._matcher

    def _read(self, manual):
        if not vision:
            return {"error": "画像認識ライブラリがありません"}
        slots = self._settings.get("slots") or []
        if not slots:
            return {"error": "BAN枠が未設定です（⚙から設定）"}
        me = find_app_window()
        hidden = False
        if vision.overlaps(me, slots):
            if not manual:  # 自動読取: 重なっている間はスキップ(ちらつき防止)
                return {"error": "overlap"}
            # 手動: 一瞬隠して撮影 (ゲームが管理者権限のため裏側は撮れない)
            ctypes.windll.user32.ShowWindow(me, 0)
            hidden = True
            time.sleep(0.25)
        try:
            img = vision.capture()
        finally:
            if hidden:
                ctypes.windll.user32.ShowWindow(me, 4)  # SW_SHOWNOACTIVATE
        if img is None:
            return {"error": "ゲーム画面が見つかりません"}
        m = self._get_matcher()
        res = m.recognize(img, slots)
        if manual:
            vision.save_capture(img)
        self._last = (time.time(), img)
        return {"slots": [[{"name": n, "score": round(s, 3)} for n, s in r] for r in res]}

    def _hotkey_loop(self):
        """F8 をグローバルホットキーとして登録。"""
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, 0x4000, 0x77):  # MOD_NOREPEAT, VK_F8
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                r = self.read_now()
                self._js(f"onBanRead({json.dumps(r, ensure_ascii=False)}, true)")

    def _game_loop(self):
        """ゲームの起動状態を監視。BAN枠の自動読取 / ゲーム終了で自動終了。"""
        gone = 0
        fast = False
        while True:
            time.sleep(0.3 if fast else 1.0)
            hwnd = vision.find_game() if vision else ctypes.windll.user32.FindWindowW(None, "IdentityV")
            if not hwnd:
                gone += 1
                if AUTO and gone * 1.5 > 20:  # ゲーム終了から20秒で閉じる
                    self._save()
                    self._window.destroy()
                    return
                continue
            gone = 0
            if not vision or ctypes.windll.user32.IsIconic(hwnd):
                continue
            try:
                img = vision.capture()
                if img is None:
                    continue
                # 場面が変わったら自動スクショ
                if self._settings.get("auto_shot"):
                    self._shots.maybe_save(img)
                if not self._settings.get("auto_read"):
                    continue
                # ランク戦の試合前画面をOCRで読む
                w = self._get_watcher()
                # キャラ選択/BANの本からゲーム内の顔写真を集める(1.5秒に1回まで)
                if w and self._settings.get("game_icons", True) and time.time() - self._harvest_t > 1.5:
                    self._harvest_t = time.time()
                    if w.harvester.feed(img):
                        self._js("onIcons()")
                if w:
                    for ev in w.feed(img):
                        if ev["type"] == "survivorBans":
                            self._last = (time.time(), img)
                        self._js(f"onRankEvent({json.dumps(ev, ensure_ascii=False)})")
                    if w.active():
                        fast = True
                        continue
                fast = False
                # (任意) 手動で枠を設定している場合は画像照合も
                slots = self._settings.get("slots")
                if not slots:
                    continue
                me = find_app_window()
                if vision.overlaps(me, slots):
                    continue
                res = self._get_matcher().recognize(img, slots)
            except Exception:
                continue
            r = {"slots": [[{"name": n, "score": round(v, 3)} for n, v in x] for x in res]}
            names = [x[0]["name"] for x in r["slots"] if x and x[0]["score"] >= 0.72]
            if names and len(names) == len(r["slots"]):
                if names != self._last_auto:
                    self._last_auto = names
                    self._last = (time.time(), img)
                    self._js(f"onBanRead({json.dumps(r, ensure_ascii=False)}, false)")
            else:
                self._last_auto = None

    def _on_resized(self, w, h):
        self._settings["width"], self._settings["height"] = w, h


def main():
    # 二重起動防止: 既に開いていれば前面に出して終了
    hwnd = find_app_window()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        return
    api = Api()
    s = api._settings
    win = webview.create_window(
        APP_NAME,
        str(ROOT / "web" / "index.html"),
        js_api=api,
        width=s.get("width", 380),
        height=s.get("height", 700),
        min_size=(300, 360),
        on_top=s.get("on_top", False),
        background_color="#14161c",
    )
    api._window = win
    win.events.resized += api._on_resized
    win.events.closing += api._save
    win.events.loaded += lambda: api.refresh()  # 起動時に最新情報を取得

    def background():
        threading.Thread(target=api._hotkey_loop, daemon=True).start()
        threading.Thread(target=api._game_loop, daemon=True).start()

    webview.start(background, http_server=True, private_mode=True,
                  icon=str(ICON) if ICON.exists() else None)


if __name__ == "__main__":
    main()
