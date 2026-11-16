@echo off
rem ゲーム起動時に荘園ナビを自動で開く常駐(watcher)を、Windowsのスタートアップに登録/解除する
cd /d "%~dp0"
python -c "import webview, cv2, mss" 2>nul || python -m pip install --user pywebview opencv-python mss numpy

set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\荘園ナビ_ゲーム連動.lnk"
if exist "%LNK%" (
  del "%LNK%"
  echo 自動起動を解除しました。
  pause
  exit /b
)
for /f "delims=" %%P in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%P"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath=$env:PYW; $s.Arguments='\"%~dp0watcher.pyw\"'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0icon.ico'; $s.Save()"
start "" "%PYW%" "%~dp0watcher.pyw"
echo 自動起動を登録しました。ゲームを起動すると荘園ナビが開きます。
echo （もう一度このファイルを実行すると解除）
pause
