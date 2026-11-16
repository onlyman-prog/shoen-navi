@echo off
cd /d "%~dp0"
python -c "import webview, cv2, mss" 2>nul || python -m pip install --user pywebview opencv-python mss numpy
start "" pythonw app.py
