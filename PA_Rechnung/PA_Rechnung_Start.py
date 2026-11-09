# -*- coding: utf-8 -*-
# =============================================================================
#  Pfeiffer-Audio Rechnung  -  Starter (Launcher) v2.1.1
#  Diese Datei ist der feste Kern der EXE. Sie startet das eigentliche
#  Programm - entweder die in der EXE eingebaute Version oder eine neuere
#  Version, die per Update-Datei (.paupdate) eingespielt wurde und im
#  Datenordner unter "Programm" liegt. So muss die EXE nur neu gebaut werden,
#  wenn eine neue Bibliothek dazukommt.
#  Autor: T. Pfeiffer
# =============================================================================
import os, sys, re, json, time, traceback

LAUNCHER_VERSION = "2.1.1"
CORE_NAME = "PA_Rechnung_core.py"


def _bundle():
    # Never called. Lists every module the program (and future updates) may
    # use, so PyInstaller packs them into the EXE.
    import os, sys, io, re, json, sqlite3, shutil, threading, datetime, time, zipfile          # noqa
    import math, uuid, mimetypes, socket, webbrowser, traceback, struct, csv, base64, hashlib   # noqa
    import smtplib, subprocess, zlib, email, email.policy, email.utils, email.message           # noqa
    import email.mime.text, email.mime.multipart, email.mime.base, email.mime.application       # noqa
    import xml.etree.ElementTree, xml.dom.minidom, xml.sax, html, html.parser, html.entities   # noqa
    import http.server, http.client, http.cookies, urllib.parse, urllib.request, urllib.error  # noqa
    import collections, collections.abc, asyncio, ctypes, ctypes.wintypes, importlib            # noqa
    import importlib.util, argparse, array, bisect, calendar, concurrent.futures, configparser  # noqa
    import contextlib, copy, dataclasses, decimal, difflib, enum, fnmatch, fractions, functools # noqa
    import getpass, glob, gzip, bz2, lzma, tarfile, heapq, hmac, inspect, ipaddress, itertools  # noqa
    import locale, logging, logging.handlers, operator, pathlib, pickle, platform, pprint       # noqa
    import queue, random, secrets, selectors, shlex, signal, ssl, statistics, string, tempfile  # noqa
    import textwrap, typing, unicodedata, warnings, weakref, zoneinfo, imaplib, poplib, ftplib  # noqa
    import codecs, binascii, quopri, mailbox, numbers, colorsys, gettext, runpy, ast, tokenize  # noqa
    import wave, cmath, sched, stringprep, shelve, dbm                                          # noqa  (v2.1.1: wave fehlte -> v2.4.6 startete nicht)
    import json.decoder, email.header, email.parser, email.generator, email.headerregistry     # noqa
    import urllib.robotparser, http.cookiejar, xmlrpc.client, wsgiref, uuid, zipimport         # noqa
    import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageFont, PIL.ImageOps, PIL.ImageFilter          # noqa
    import PIL.ImageEnhance, PIL.ImageChops                                                     # noqa
    import reportlab, reportlab.pdfgen.canvas, reportlab.platypus, reportlab.lib.styles         # noqa
    import reportlab.graphics.barcode.qr, reportlab.graphics.shapes, reportlab.graphics.renderPDF  # noqa
    import reportlab.graphics.charts.barcharts, reportlab.graphics.charts.linecharts            # noqa
    import reportlab.graphics.charts.piecharts                                                 # noqa
    import pypdf, pypdfium2, openpyxl, xlrd, olefile, msoffcrypto, pyzipper                     # noqa
    import cryptography.hazmat.primitives.ciphers, cryptography.hazmat.primitives.kdf.pbkdf2    # noqa
    import cryptography.hazmat.primitives.hashes, cryptography.fernet                           # noqa
    import webview, atexit                                                                       # noqa
    try:
        import tkinter, tkinter.filedialog                                                       # noqa  (file dialog without pywebview window, m20)
    except Exception:
        pass
    try:
        import tzdata                                                                            # noqa  (v2.1.0 zoneinfo under Windows)
    except Exception:
        pass
    try:
        import fints, fints.client, fints.utils, mt940                                           # noqa  (v2.0.0 Bankabruf)
    except Exception:
        pass
    try:
        import winrt.windows.media.ocr, winrt.windows.globalization                              # noqa
        import winrt.windows.graphics.imaging, winrt.windows.storage.streams                    # noqa
    except Exception:
        pass
    try:
        import clr                                                                               # noqa
    except Exception:
        pass


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


VER_RE = re.compile(r"\d+(\.\d+){1,3}")


def vtuple(v):
    t = [int(x) for x in re.findall(r"\d+", str(v or "0"))[:4]]
    return tuple(t + [0] * (4 - len(t)))


def core_version(path):
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4000)
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', head, re.M)
        return m.group(1) if m else "0"
    except Exception:
        return "0"


def builtin_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def builtin_core():
    d = builtin_dir()
    p = os.path.join(d, CORE_NAME)
    if os.path.exists(p):
        return p
    # running from the source folder: newest PA_Rechnung_vX.Y.Z.py
    best, bv = None, (0,)
    for fn in os.listdir(d):
        m = re.match(r"PA_Rechnung_v([\d.]+)\.py$", fn)
        if m and vtuple(m.group(1)) > bv:
            best, bv = os.path.join(d, fn), vtuple(m.group(1))
    return best


def read_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def wait_pid(pid, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        alive = False
        try:
            if sys.platform.startswith("win"):
                import ctypes
                k = ctypes.windll.kernel32
                h = k.OpenProcess(0x1000 | 0x00100000, False, pid)   # QUERY_LIMITED | SYNCHRONIZE
                if h:
                    alive = k.WaitForSingleObject(h, 0) == 0x102      # WAIT_TIMEOUT -> still running
                    k.CloseHandle(h)
            else:
                os.kill(pid, 0)
                alive = True
        except Exception:
            alive = False
        if not alive:
            return
        time.sleep(0.25)


def choose(app_dir):
    """Return (core_path, res_dir, source, version)."""
    b_core = builtin_core()
    b_ver = core_version(b_core) if b_core else "0"
    act = read_json(os.path.join(app_dir, "aktiv.json"), {}) or {}
    start = read_json(os.path.join(app_dir, "start.json"), {}) or {}
    note = None
    if act.get("version") and act.get("version") != "builtin" and not VER_RE.fullmatch(str(act["version"])):
        act = {}
    if act.get("version") and act.get("version") != "builtin":
        vd = os.path.join(app_dir, "versionen", act["version"])
        main_ = act.get("main") or "PA_Rechnung.py"
        if not re.fullmatch(r"[\w\-. ]+\.py", main_):
            main_ = "PA_Rechnung.py"
        core = os.path.join(vd, main_)
        bad = set(act.get("defekt") or [])
        if act["version"] in bad:
            pass
        elif not os.path.exists(core):
            note = f"Update v{act['version']} nicht gefunden - eingebaute Version gestartet."
        elif start.get("version") == act["version"] and not start.get("ok") and int(start.get("tries") or 0) >= 2:
            # started twice without ever showing the window -> roll back
            bad.add(act["version"])
            prev = act.get("vorher") or "builtin"
            act.update({"version": prev, "defekt": sorted(bad)})
            write_json(os.path.join(app_dir, "aktiv.json"), act)
            note = f"Update v{start.get('version')} ließ sich nicht starten - automatisch zurück auf {('v' + prev) if prev != 'builtin' else 'die eingebaute Version'}."
            write_json(os.path.join(app_dir, "hinweis.json"), {"text": note, "datum": time.strftime("%Y-%m-%d %H:%M")})
            return choose(app_dir)
        elif vtuple(act["version"]) >= vtuple(b_ver) or (act.get("fest") and vtuple(b_ver) <= vtuple(act.get("fest_builtin") or b_ver)):
            return core, vd, "update", act["version"]
        else:
            note = None   # EXE itself is newer than the installed update
    if note:
        write_json(os.path.join(app_dir, "hinweis.json"), {"text": note, "datum": time.strftime("%Y-%m-%d %H:%M")})
    return b_core, builtin_dir(), "builtin", b_ver


def run_core(core, res, source, ver, app_dir):
    os.environ["PA_RECHNUNG_RES"] = res
    os.environ["PA_RECHNUNG_RES_FALLBACK"] = builtin_dir()
    os.environ["PA_RECHNUNG_CORE_SOURCE"] = source
    os.environ["PA_RECHNUNG_LAUNCHER"] = LAUNCHER_VERSION
    os.environ["PA_RECHNUNG_BUILTIN_VER"] = core_version(builtin_core() or "")
    os.environ["PA_RECHNUNG_APPDIR"] = app_dir
    if not getattr(sys, "frozen", False):
        os.environ["PA_RECHNUNG_LAUNCHER_PATH"] = os.path.abspath(__file__)
    sp = os.path.join(app_dir, "start.json")
    st = read_json(sp, {}) or {}
    if st.get("version") != ver or st.get("source") != source:
        st = {"version": ver, "source": source, "tries": 0}
    st.update({"tries": int(st.get("tries") or 0) + 1, "ok": False, "zeit": time.strftime("%Y-%m-%d %H:%M:%S")})
    write_json(sp, st)
    with open(core, encoding="utf-8") as f:
        code = compile(f.read(), core, "exec")
    sys.path.insert(0, res)
    g = {"__name__": "__main__", "__file__": core, "__builtins__": __builtins__}
    exec(code, g)


def relaunch(extra_env=None):
    """Start a fresh instance (same arguments, clean PyInstaller env) and exit."""
    import subprocess
    args = [a for i, a in enumerate(sys.argv[1:]) if a != "--wait-pid" and (i == 0 or sys.argv[i] != "--wait-pid")]
    cmd = [sys.executable] + ([] if getattr(sys, "frozen", False) else [os.path.abspath(__file__)]) + args + ["--wait-pid", str(os.getpid())]
    env = {k: v for k, v in os.environ.items() if not (k.startswith("_MEI") or k.startswith("_PYI") or k.startswith("PA_RECHNUNG_RES")
                                                     or k in ("PA_RECHNUNG_CORE_SOURCE", "PA_RECHNUNG_BUILTIN_VER", "PA_RECHNUNG_LAUNCHER"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    kw = {"env": env, "close_fds": True}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x00000008 | 0x00000200
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)
    os._exit(0)


def main():
    if "--wait-pid" in sys.argv:
        try:
            wait_pid(int(sys.argv[sys.argv.index("--wait-pid") + 1]))
        except Exception:
            pass
    data_dir = os.environ.get("PA_RECHNUNG_DATA") or os.path.join(_documents_dir(), "Pfeiffer-Audio Rechnung")
    app_dir = os.path.join(data_dir, "Programm")
    os.makedirs(os.path.join(app_dir, "versionen"), exist_ok=True)
    print(f"INIT Starter v{LAUNCHER_VERSION}")
    core, res, source, ver = choose(app_dir)
    if not core:
        raise SystemExit("Programmkern nicht gefunden.")
    try:
        run_core(core, res, source, ver, app_dir)
    except SystemExit:
        raise
    except Exception:
        st = read_json(os.path.join(app_dir, "start.json"), {}) or {}
        if source != "update" or (st.get("version") == ver and st.get("ok")):
            raise   # built-in version, or the update started fine and failed later: no rollback
        # the update crashed while starting -> mark broken, start previous version
        err = traceback.format_exc()
        act = read_json(os.path.join(app_dir, "aktiv.json"), {}) or {}
        bad = set(act.get("defekt") or [])
        bad.add(ver)
        act.update({"version": act.get("vorher") or "builtin", "defekt": sorted(bad)})
        write_json(os.path.join(app_dir, "aktiv.json"), act)
        write_json(os.path.join(app_dir, "hinweis.json"), {"text": f"Update v{ver} ist beim Start abgestürzt - automatisch zurückgesetzt.", "fehler": err[-3000:],
                                                           "datum": time.strftime("%Y-%m-%d %H:%M")})
        relaunch()


if __name__ == "__main__":
    main()
