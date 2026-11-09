@echo off
REM Startet das Programm direkt mit Python (ohne EXE)
chcp 65001 >nul
cd /d "%~dp0"
set PY=python
where py >nul 2>&1 && set PY=py -3
%PY% -m pip install -r requirements.txt --quiet
%PY% -m pip install -r requirements_ocr.txt --quiet
%PY% "PA_Rechnung_Start.py"
