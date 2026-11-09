#!/bin/bash
# PA Rechnung - iPhone/iPad-App bauen auf einem Mac  v1.1.0 (Programm v3.7.0)
# Nur noetig, wenn ein Mac vorhanden ist - ohne Mac baut GitHub die App (siehe Handbuch, Kapitel 8).
#   ./build_ios.sh          -> Simulator
#   ./build_ios.sh xcode    -> Xcode oeffnen (auf dem eigenen iPhone installieren)
# Autor: T. Pfeiffer
set -e
cd "$(dirname "$0")"
echo "INIT build_ios v1.1.0"
bash ./prepare_programm.sh "${PA_PROGRAMM:-../PA_Rechnung}"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q --upgrade "briefcase>=0.3.20"
if [ -d build/parechnung/ios ]; then briefcase update iOS -r; else briefcase create iOS --no-input; fi
briefcase build iOS
if [ "$1" == "xcode" ]; then
  briefcase open iOS
else
  briefcase run iOS
fi
