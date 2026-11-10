# -*- coding: utf-8 -*-
# =============================================================================
#  Pfeiffer-Audio Rechnung  -  v3.7.1
#  Rechnungen aus Bausteinen, Kundendatenbank, Projekte mit Dateistruktur,
#  Belege-Import (PDF mit Erkennung), Statistik, Jahresabrechnung, Steuer.
#  Autor: T. Pfeiffer
#  Laeuft als Windows-Programm (pywebview / WebView2), Fallback: Browser.
#  Ab v2.0.0 modular: dieser Kern laedt alle Dateien aus "modules" (sortiert)
#  in seinen Namensraum; neue Funktionen docken ueber HOOK_* an.
# =============================================================================
import os, sys, io, re, json, sqlite3, shutil, threading, datetime, time, zipfile
import math, uuid, mimetypes, socket, webbrowser, traceback, struct, csv, base64, hashlib, smtplib, subprocess
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

APP_NAME = "Pfeiffer-Audio Rechnung"
APP_VERSION = "3.7.1"

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    RES_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = os.environ.get("PA_RECHNUNG_RES") or RES_DIR
RES_FALLBACK = os.environ.get("PA_RECHNUNG_RES_FALLBACK") or RES_DIR


def res_path(*parts):
    p = os.path.join(RES_DIR, *parts)
    return p if os.path.exists(p) else os.path.join(RES_FALLBACK, *parts)


def _documents_dir():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and os.path.isdir(buf.value):
                return buf.value
        except Exception:
            pass
    home = os.path.expanduser("~")
    for name in ("Documents", "Dokumente"):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            return p
    return home


# v2.0.0: Datenordner frei waehlbar - Zeiger-Datei im Benutzerprofil (AppData)
DEFAULT_DATA_DIR = os.path.join(_documents_dir(), "Pfeiffer-Audio Rechnung")


def pointer_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "Pfeiffer-Audio Rechnung", "datenordner.json")


def read_pointer():
    try:
        with open(pointer_path(), encoding="utf-8") as f:
            p = (json.load(f) or {}).get("path") or ""
        return p if p and os.path.isdir(p) else ""
    except Exception:
        return ""


def _pointer_target():
    """path stored in the pointer file ("" = no pointer / no path), also when the folder is missing"""
    try:
        with open(pointer_path(), encoding="utf-8") as f:
            d_ = json.load(f)
        return str((d_ or {}).get("path") or "").strip() if isinstance(d_, dict) else ""
    except Exception:
        return ""


def _data_dir_missing(p):
    # v2.6.3: a chosen data folder that is not reachable (USB drive / NAS not connected) must not silently
    # switch to an empty default folder - new invoices would end up in a second database
    msg = f"Datenordner {p} nicht erreichbar - Laufwerk/NAS verbinden und neu starten"
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, APP_NAME, 0x10)     # MB_ICONERROR
        except Exception:
            pass
    sys.exit(2)


if os.environ.get("PA_RECHNUNG_DATA"):
    DATA_DIR = os.environ["PA_RECHNUNG_DATA"]
else:
    _pt = _pointer_target()
    if _pt and not os.path.isdir(_pt):
        _data_dir_missing(_pt)
    DATA_DIR = read_pointer() or DEFAULT_DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "daten.sqlite")
BELEG_DIR = os.path.join(DATA_DIR, "Belege")
PROJ_DIR = os.path.join(DATA_DIR, "Projekte")
BACKUP_DIR = os.path.join(DATA_DIR, "Backup")
ASSET_DIR = os.path.join(DATA_DIR, "Assets")
for _d in (DATA_DIR, BELEG_DIR, PROJ_DIR, BACKUP_DIR, ASSET_DIR):
    os.makedirs(_d, exist_ok=True)


# ----------------------------------------------------------------------------
# v2.0.0  Modul-Lader und Andockpunkte (Hooks)
# ----------------------------------------------------------------------------
HOOK_GET = {}        # path -> fn(handler, qs)
HOOK_POST = {}       # path -> fn(handler, data)
HOOK_UPLOAD = {}     # path -> fn(handler, tmp_path, filename)
HOOK_BOOT = []       # fn(bootstrap_dict)  - add data for the UI
HOOK_SCHEMA = []     # fn()                - create tables / migrations (after init_db)
HOOK_START = []      # fn()                - background threads at program start
HOOK_SELFTEST = []   # fn() -> list of error strings (empty = ok)
MODULES_LOADED = []
# v3.5.1: module files that were merged into another file (v3.1.0). If an old copy is still lying around (ZIP unpacked
# over an older folder, EXE built from such a folder) it must NOT be loaded a second time - every step, route and
# background job would run twice (e.g. tax adjustment twice -> wrong figures).
MODULES_REPLACED = {
    "m84_kalender_plus.py": "m84_kalender.py", "m84b_timetree_schreiben.py": "m84_kalender.py", "m84c_kurstermine.py": "m84_kalender.py",
    "m44_steuerbescheid.py": "m44_steuerjahr.py", "m45_jahr.py": "m44_steuerjahr.py", "m46_angleich.py": "m44_steuerjahr.py",
    "m98_gmail_login.py": "m98_mail.py", "m99_mail_privat.py": "m98_mail.py", "m99b_rechnungsabsender.py": "m98_mail.py",
    "m99c_outlook.py": "m98_mail.py", "m30_mail_import.py": "m30_mail_eingang.py", "m31_imap.py": "m30_mail_eingang.py",
}
MODULES_SKIPPED = []
MODULES_FAILED = []   # v2.4.7: modules that could not load because a library is missing (program starts anyway)
# these modules must load - without them the program must not start (base, data, PIN lock, security)
MODULES_CRITICAL = re.compile(r"m(0\d|1\d|2[0-2])[_a-z]|m92|m97")


def modules_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "modules")


def load_modules(g):
    md = modules_dir()
    if not os.path.isdir(md):
        md = res_path("modules")
    for fn in sorted(os.listdir(md)):
        if not re.fullmatch(r"m\d\d\w*\.py", fn):
            continue
        if fn in MODULES_REPLACED and os.path.isfile(os.path.join(md, MODULES_REPLACED[fn])):
            MODULES_SKIPPED.append(fn)
            print(f"INIT Modul {fn} uebersprungen - steckt seit v3.1.0 in {MODULES_REPLACED[fn]} (alte Datei bitte loeschen)")
            continue
        fp = os.path.join(md, fn)
        try:
            with open(fp, encoding="utf-8") as f:
                code = compile(f.read(), fp, "exec")
            exec(code, g)
        except Exception as e:
            # v2.4.7/2.4.8: a broken or incomplete add-on module (missing library, DLL error, syntax error, missing
            # function of another module that failed) only switches this one function off - the program still starts.
            # Base modules, PIN lock and security must load, otherwise the program does not start at all.
            if MODULES_CRITICAL.match(fn):
                raise
            traceback.print_exc()
            what = getattr(e, "name", "") if isinstance(e, ImportError) else ""
            MODULES_FAILED.append({"modul": fn, "fehlt": what or f"{type(e).__name__}: {e}"[:160]})
            print(f"INIT Modul {fn} NICHT geladen - {type(e).__name__}: {e}")
            continue
        MODULES_LOADED.append(fn)


load_modules(globals())


def _wrap_hooks():
    g = globals()
    base_init, base_boot = g["init_db"], g["bootstrap"]

    def init_db():
        # v3.5.1: safety copy of the database before a new program version changes it, migrations afterwards
        if "db_pre_update" in g:
            g["db_pre_update"]()
        base_init()
        for f in HOOK_SCHEMA:
            try:
                f()
            except Exception:
                traceback.print_exc()
        if "db_after_schema" in g:
            g["db_after_schema"]()

    def bootstrap():
        d = base_boot()
        d["modul_fehler"] = list(MODULES_FAILED)
        for f in HOOK_BOOT:
            try:
                f(d)
            except Exception:
                traceback.print_exc()
        return d
    g["init_db"], g["bootstrap"] = init_db, bootstrap


_wrap_hooks()


def start_hooks():
    for f in HOOK_START:
        threading.Thread(target=f, daemon=True).start()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if run_selftest(print_=True)["ok"] else 1)
    main()
