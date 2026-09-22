@echo off
echo Compilation de FIT Altitude Tool en cours...
py -m PyInstaller --noconfirm --onefile --windowed --clean --collect-data tkinterdnd2 --collect-all imagecodecs --collect-all fit_tool --collect-all fitdecode --name "FIT Altitude Tool" app.py
echo.
echo Compilation terminee ! L'executable se trouve dans le dossier "dist".
pause
