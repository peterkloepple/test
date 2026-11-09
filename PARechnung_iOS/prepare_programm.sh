#!/bin/bash
# PA Rechnung - iPhone-App: Programm in die App kopieren  v1.1.0
# Aufruf: prepare_programm.sh [Programmordner]   (Standard: ../PA_Rechnung neben diesem Ordner)
# Kopiert nur, was das Programm zum Laufen braucht (Kern, modules, ui, assets) - keine Handbuecher, keine Werkzeuge.
# Autor: T. Pfeiffer
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-${PA_PROGRAMM:-$HERE/../PA_Rechnung}}"
echo "INIT prepare_programm v1.1.0  Quelle: $SRC"
if [ ! -d "$SRC/modules" ]; then echo "Programmordner nicht gefunden: $SRC"; exit 1; fi
DST="$HERE/src/parechnung/programm"
rm -rf "$DST"; mkdir -p "$DST"
cp "$SRC"/PA_Rechnung_v*.py "$SRC"/ui.html "$DST"/
cp -R "$SRC"/modules "$SRC"/ui "$SRC"/assets "$DST"/
find "$DST" -name "__pycache__" -prune -exec rm -rf {} +
ls "$DST"/PA_Rechnung_v*.py
