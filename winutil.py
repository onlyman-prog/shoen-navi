"""アプリ名と、自分のウィンドウを探す処理 (app.py と watcher.pyw で共通)。"""
import ctypes
from ctypes import wintypes
from pathlib import Path

APP_NAME = "荘園手記"
APP_ID = "ShoenShuki.App"


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
