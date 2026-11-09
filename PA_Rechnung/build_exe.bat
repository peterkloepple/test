@echo off
REM ==========================================================
REM  Pfeiffer-Audio Rechnung v3.7.0 - EXE erzeugen (PyInstaller)
REM  Die EXE enthaelt den Starter + Programm v3.7.0. Spaetere
REM  Versionen kommen als .paupdate-Datei (make_update.bat) und
REM  werden im Programm eingespielt - kein neuer EXE-Bau noetig.
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

echo     Alte Dateien aus der Zeit vor v3.1 entfernen (falls die ZIP ueber einen alten Ordner entpackt wurde) ...
for %%F in (m84_kalender_plus.py m84b_timetree_schreiben.py m84c_kurstermine.py m44_steuerbescheid.py m45_jahr.py m46_angleich.py m98_gmail_login.py m99_mail_privat.py m99b_rechnungsabsender.py m99c_outlook.py m30_mail_import.py m31_imap.py) do if exist "modules\%%F" del /q "modules\%%F"
for %%F in (m44_bescheid.js m45_jahr.js m46_angleich.js m98_gmail.js m99_privat.js m99c_outlook.js) do if exist "ui\%%F" del /q "ui\%%F"
for %%F in (PA_Rechnung_v*.py) do if /i not "%%F"=="PA_Rechnung_v%APPVER%.py" del /q "%%F"

echo [2/3] EXE bauen ...
if exist build rmdir /s /q build
if exist "PA_Rechnung_v%APPVER%.spec" del "PA_Rechnung_v%APPVER%.spec"
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
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
echo EXE: %~dp0dist\PA_Rechnung_v%APPVER%.exe
explorer "%~dp0dist"
pause
exit /b 0

:err
echo.
echo FEHLER beim Erzeugen der EXE - siehe Meldungen oben.
pause
exit /b 1
