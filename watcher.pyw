"""ゲーム(IdentityV)の起動を監視して、荘園手記を自動で開く常駐スクリプト。

Windowsのスタートアップに登録して使う (自動起動の設定.bat)。
ゲームごとに1回だけ開く。ゲーム中にアプリを手動で閉じた場合は再度開かない。
"""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from winutil import find_app_window  # noqa: E402
user32 = ctypes.windll.user32


def exists(title):
    return bool(user32.FindWindowW(None, title))


def main():
    # 常駐の二重起動防止
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "IdVHayamiWatcher")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return
    pyw = Path(sys.executable).with_name("pythonw.exe")
    launched = False
    while True:
        game = exists("IdentityV")
        if game and not launched:
            if not find_app_window():
                subprocess.Popen([str(pyw), str(ROOT / "app.py"), "--auto"], cwd=str(ROOT))
            launched = True
        elif not game:
            launched = False
        time.sleep(4)


if __name__ == "__main__":
    main()
