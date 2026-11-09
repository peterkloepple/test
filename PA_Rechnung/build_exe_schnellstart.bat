@echo off
REM ==========================================================
REM  Pfeiffer-Audio Rechnung v3.7.0 - SCHNELLSTART-EXE (Ordner-Variante)
REM  Wie build_exe.bat, aber als Ordner (--onedir): die EXE muss
REM  beim Start nicht jedes Mal ~150 MB in einen Temp-Ordner
REM  entpacken - startet dadurch mehrere Sekunden schneller.
REM  Ergebnis: dist\PA_Rechnung_v%APPVER%\ (ganzen Ordner behalten,
REM  Verknuepfung auf die EXE darin legen). Updates (.paupdate)
REM  funktionieren genauso.
REM  Autor: T. Pfeiffer
REM ==========================================================
chcp 65001 >nul
cd /d "%~dp0"
set APPVER=3.7.0
set PY=python
where py >nul 2>&1 && set PY=py -3

echo [1/3] Pakete installieren ...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :err
echo     Texterkennung (Windows-OCR, optional) ...
%PY% -m pip install -r requirements_ocr.txt || echo     OCR-Pakete nicht installiert - Programm laeuft trotzdem, nur ohne Texterkennung fuer Scans.
set WINRT=
%PY% -c "import winrt.windows.media.ocr" >nul 2>&1 && set WINRT=--collect-all winrt

echo [2/3] EXE bauen ...
if exist build rmdir /s /q build
if exist "PA_Rechnung_v%APPVER%.spec" del "PA_Rechnung_v%APPVER%.spec"
if exist "dist\PA_Rechnung_v%APPVER%" rmdir /s /q "dist\PA_Rechnung_v%APPVER%"
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name "PA_Rechnung_v%APPVER%" ^
  --icon "assets\app.ico" ^
  --add-data "PA_Rechnung_v%APPVER%.py;." ^
  --add-data "ui.html;." ^
  --add-data "modules;modules" ^
  --add-data "ui;ui" ^
  --add-data "assets;assets" ^
  --add-data "PA_Rechnung_Start.py;build" ^
  --add-data "requirements.txt;build" ^
  --add-data "requirements_ocr.txt;build" ^
  --collect-all reportlab ^
  --collect-submodules reportlab.graphics.barcode ^
  --collect-all pypdfium2 ^
  --collect-all pypdfium2_raw ^
  --collect-all pypdf ^
  --collect-all openpyxl ^
  --collect-all msoffcrypto ^
  --collect-all pyzipper ^
  --collect-all xlrd ^
  --collect-all olefile ^
  --collect-submodules cryptography ^
  %WINRT% ^
  --collect-all webview ^
  --collect-all fints ^
  --collect-all mt940 ^
  --collect-data tzdata ^
  --hidden-import clr ^
  --hidden-import PIL.Image ^
  "PA_Rechnung_Start.py"
if errorlevel 1 goto :err

echo [3/3] Fertig. Ab jetzt reichen Updates als .paupdate-Datei.
echo EXE: %~dp0dist\PA_Rechnung_v%APPVER%\PA_Rechnung_v%APPVER%.exe
echo Den GANZEN Ordner dist\PA_Rechnung_v%APPVER% an seinen Platz kopieren.
explorer "%~dp0dist"
pause
exit /b 0

:err
echo.
echo FEHLER beim Erzeugen der EXE - siehe Meldungen oben.
pause
exit /b 1
