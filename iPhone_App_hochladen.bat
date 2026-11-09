@echo off
REM PA Rechnung - iPhone-App: Projekt zu GitHub hochladen  v1.1.0
REM Dort baut ein Mac in der Cloud die App (Reiter Actions).
REM v1.1.0: installiert Git fuer Windows selbst (winget), wenn es fehlt.
REM Autor: T. Pfeiffer
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo INIT iPhone_App_hochladen v1.1.0
call :findgit
if defined GIT goto gitok
echo.
echo Git fuer Windows fehlt - wird jetzt installiert (einmalig, ca. 1-2 Minuten) ...
where winget >nul 2>nul
if errorlevel 1 goto nowinget
winget install --id Git.Git -e --source winget --silent --accept-package-agreements --accept-source-agreements
call :findgit
if not defined GIT goto nogit
echo Git installiert.
:gitok
if exist ".git" goto push
echo.
echo Jetzt auf github.com ein NEUES, PRIVATES Repository anlegen (z. B. pa-rechnung-ios), OHNE README,
echo und die Adresse kopieren (sie endet auf .git).
start "" "https://github.com/new"
echo.
set /p REPO=Adresse hier einfuegen (Rechtsklick) und Enter: 
if "%REPO%"=="" goto norepo
"%GIT%" init -q -b main
"%GIT%" remote add origin "%REPO%"
:push
"%GIT%" add -A
"%GIT%" -c user.name="T. Pfeiffer" -c user.email="pa-rechnung@localhost" commit -q -m "PA Rechnung iPhone-App %date% %time%"
echo.
echo Lade hoch - beim ersten Mal oeffnet sich ein Fenster zur Anmeldung bei GitHub ...
"%GIT%" push -u origin main
if errorlevel 1 goto fehler
echo.
echo Hochgeladen. Auf github.com im Repository: Reiter "Actions" - "iPhone-App bauen" laeuft (ca. 20 Minuten).
echo Danach den Lauf anklicken und unten unter "Artifacts" PA_Rechnung_iPhone herunterladen.
pause
exit /b 0

:findgit
set "GIT="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GIT set "GIT=%%G"
if not defined GIT if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "GIT=%LocalAppData%\Programs\Git\cmd\git.exe"
exit /b 0

:nowinget
echo winget ist auf diesem PC nicht verfuegbar.
:nogit
echo Git konnte nicht automatisch installiert werden.
echo Bitte von https://git-scm.com/download/win laden, installieren (alle Vorgaben lassen) und diese Datei erneut starten.
start "" "https://git-scm.com/download/win"
pause
exit /b 1
:norepo
echo Keine Adresse eingegeben - abgebrochen.
pause
exit /b 1
:fehler
echo.
echo Hochladen fehlgeschlagen - Adresse (endet auf .git) und Anmeldung bei GitHub pruefen (Handbuch Kapitel 11).
echo Falsche Adresse? Ordner ".git" im iPhone-Ordner loeschen und diese Datei neu starten.
pause
exit /b 1