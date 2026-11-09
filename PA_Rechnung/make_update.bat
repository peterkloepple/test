@echo off
REM ==========================================================
REM  Pfeiffer-Audio Rechnung v3.7.0 - Update-Datei (.paupdate) erzeugen
REM  Nimmt die neueste PA_Rechnung_vX.Y.Z.py + ui.html + assets
REM  + Starter/requirements (build/) fuer den automatischen EXE-Bau
REM  und legt dist\PA_Rechnung_vX.Y.Z.paupdate an.
REM  Autor: T. Pfeiffer
REM ==========================================================
chcp 65001 >nul
cd /d "%~dp0"
set PY=python
where py >nul 2>&1 && set PY=py -3
%PY% make_update.py %*
if errorlevel 1 goto :err
echo.
echo Fertig. Die .paupdate-Datei im Programm unter
echo Einstellungen ^> Daten ^> Programm-Update einspielen
echo (oder einfach ins Programmfenster ziehen).
explorer "%~dp0dist"
pause
exit /b 0
:err
echo FEHLER - siehe Meldungen oben.
pause
exit /b 1
