# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m70_exe_erneuern (v2.0.19)
# EXE automatisch erneuern: nach einem eingespielten Update baut das Programm auf
# diesem PC selbst die passende neue EXE (Python + PyInstaller, unsichtbar im
# Hintergrund) und tauscht beim Beenden (oder per Knopf) die alte EXE gegen die
# neue aus. Verknuepfungen auf Desktop, im Startmenue und in der Taskleiste
# werden auf die neue EXE umgebogen.
#  - Bau-Ordner: <Datenordner>/Programm/exe_bau/<version>/ (Kern, ui, modules,
#    assets, Starter, requirements) + bau.bat, Log unter exe_bau/logs/
#  - Tausch: PowerShell-Skript wartet auf das Programmende (PID), verschiebt die
#    alte EXE nach Programm/exe_alt (nur die letzte bleibt), legt die neue an
#    den Platz der alten, biegt .lnk-Dateien um, schreibt das Ergebnis nach
#    Programm/exe_tausch_ergebnis.json und startet ggf. die neue EXE.
#  - Ohne EXE (Quellcode / start_ohne_exe.bat) wird nichts getauscht.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import atexit
import tempfile

M70_VERSION = "1.0.0"
M70_DEFAULTS = {"auto_bau": True, "auto_tausch": True, "python": "", "variante": "auto", "ocr": True}
M70_RUN = {"state": "idle", "ver": "", "phase": "", "pct": 0, "msg": "", "proc": None, "log": "", "start": 0.0,
           "art": "", "dir": "", "lock": threading.Lock(), "py_cache": None}
M70_NO_WINDOW = 0x08000000
M70_DETACHED = 0x00000008
M70_BELOW_NORMAL = 0x00004000
M70_PHASES = {"pip": ("Pakete installieren", 10), "ocr": ("Texterkennung installieren", 28), "pyinstaller": ("EXE wird gebaut", 35)}


def _m70_is_win():
    return sys.platform.startswith("win")


def m70_settings():
    s = dict(M70_DEFAULTS)
    s.update(get_settings().get("m70") or {})
    return s


def _m70_base():
    return os.path.join(APP_DIR, "exe_bau")


def _m70_status_path():
    return os.path.join(_m70_base(), "status.json")


def _m70_status():
    st = _rj(_m70_status_path(), {}) or {}
    st.setdefault("bauten", [])
    st.setdefault("fehlversuch", {})
    return st


def _m70_status_save(st):
    st["bauten"] = (st.get("bauten") or [])[-12:]
    _wj(_m70_status_path(), st)


def _m70_clean_env():
    env = {k: v for k, v in os.environ.items() if not (k.startswith("_MEI") or k.startswith("_PYI") or k.startswith("PA_RECHNUNG_") or k.startswith("PA_M70_")
                                                      or k in ("TCL_LIBRARY", "TK_LIBRARY", "PYTHONHOME", "PYTHONPATH"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def m70_exe_info():
    """the running EXE: path, kind (onefile / onedir / none) and its built-in program version"""
    frozen = bool(getattr(sys, "frozen", False))
    exe = sys.executable if frozen else ""
    art = "kein"
    if frozen:
        art = "onedir" if os.path.isdir(os.path.join(os.path.dirname(exe), "_internal")) else "onefile"
    builtin = os.environ.get("PA_RECHNUNG_BUILTIN_VER") or (APP_VERSION if CORE_SOURCE != "update" else "")
    return {"frozen": frozen, "exe": exe, "art": art, "builtin": builtin, "version": APP_VERSION, "source": CORE_SOURCE,
            "veraltet": bool(frozen and builtin and vtuple(builtin) < vtuple(APP_VERSION))}


# ---------------------------------------------------------------- Python suchen
def _m70_try_python(cmd):
    try:
        r = subprocess.run(cmd + ["-c", "import sys,struct;print(sys.version.split()[0], struct.calcsize('P')*8)"],
                           capture_output=True, text=True, timeout=20, env=_m70_clean_env(),
                           creationflags=M70_NO_WINDOW if _m70_is_win() else 0)
        if r.returncode == 0 and r.stdout.strip():
            v, bits = (r.stdout.split() + ["?", "?"])[:2]
            if vtuple(v) < (3, 9, 0, 0):
                return {"ok": False, "cmd": cmd, "version": v, "error": f"Python {v} ist zu alt (ab 3.9 noetig)."}
            return {"ok": True, "cmd": cmd, "version": v, "bits": bits}
    except Exception as e:
        return {"ok": False, "cmd": cmd, "error": str(e)[:200]}
    return {"ok": False, "cmd": cmd, "error": "keine Antwort"}


def _m70_candidates(s=None):
    s = s or m70_settings()
    out = []
    if (s.get("python") or "").strip():
        out.append([s["python"].strip().strip('"')])
    if not getattr(sys, "frozen", False) and sys.executable:
        out.append([sys.executable])
    if shutil.which("py"):
        out.append([shutil.which("py"), "-3"])
    for n in ("python", "python3"):
        p = shutil.which(n)
        if p and "WindowsApps" not in p:     # Store-Platzhalter oeffnet nur den Microsoft Store
            out.append([p])
    if _m70_is_win():
        import glob as _g
        for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            if base:
                for p in sorted(_g.glob(os.path.join(base, "Programs", "Python", "Python3*", "python.exe")) +
                                _g.glob(os.path.join(base, "Python3*", "python.exe")), reverse=True):
                    out.append([p])
    seen, res = set(), []
    for c in out:
        k = "|".join(c).lower()
        if k not in seen:
            seen.add(k)
            res.append(c)
    return res


M70_NO_PY = ("Auf diesem PC wurde kein Python gefunden. Zum automatischen Bauen der EXE einmalig Python installieren: "
             "python.org -> Downloads -> Windows -> aktuelle Version, im Installer unbedingt den Haken "
             "\"Add python.exe to PATH\" setzen. Danach hier \"Python suchen\" klicken. Alternativ den Pfad zur python.exe eintragen.")


def m70_find_python(force=False, s=None):
    if M70_RUN["py_cache"] and not force:
        return M70_RUN["py_cache"]
    tried = []
    for c in _m70_candidates(s):
        r = _m70_try_python(c)
        tried.append({"cmd": " ".join(c), "ok": r.get("ok"), "info": r.get("version") or r.get("error") or ""})
        if r.get("ok"):
            res = dict(r, tried=tried)
            M70_RUN["py_cache"] = res
            return res
    res = {"ok": False, "error": M70_NO_PY, "tried": tried}
    M70_RUN["py_cache"] = None
    return res


# ---------------------------------------------------------------- Bau-Ordner
def _m70_launcher_dir():
    cands = [os.path.join(RES_DIR, "build"), os.path.join(RES_FALLBACK, "build"), RES_DIR, RES_FALLBACK]
    lp = os.environ.get("PA_RECHNUNG_LAUNCHER_PATH")
    if lp:
        cands.append(os.path.dirname(lp))
    cands.append(os.path.dirname(os.path.abspath(__file__)))
    for d in cands:
        if d and os.path.isfile(os.path.join(d, "PA_Rechnung_Start.py")):
            return d
    return ""


def _m70_find_file(name, first_dir):
    for d in (first_dir, os.path.join(RES_DIR, "build"), os.path.join(RES_FALLBACK, "build"), RES_DIR, RES_FALLBACK):
        if d and os.path.isfile(os.path.join(d, name)):
            return os.path.join(d, name)
    return ""


def m70_variante(s=None):
    s = s or m70_settings()
    v = s.get("variante") or "auto"
    if v in ("onefile", "onedir"):
        return v
    i = m70_exe_info()
    return "onedir" if i["art"] == "onedir" else "onefile"


def m70_prepare(target_base=None, ver=None, py_cmd=None, art=None, ocr=None):
    """copy the running program into a build folder and write bau.bat; returns dict with paths"""
    ver = ver or APP_VERSION
    s = m70_settings()
    art = art or m70_variante(s)
    ocr = s.get("ocr", True) if ocr is None else ocr
    base = target_base or _m70_base()
    d = os.path.join(base, ver)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    core = os.path.abspath(__file__)
    shutil.copy2(core, os.path.join(d, f"PA_Rechnung_v{ver}.py"))
    shutil.copy2(res_path("ui.html"), os.path.join(d, "ui.html"))
    for sub, src in (("modules", modules_dir() if os.path.isdir(modules_dir()) else res_path("modules")), ("ui", ui_dir()),
                     ("assets", res_path("assets"))):
        if not os.path.isdir(src):
            raise ValueError(f"Ordner {sub} der laufenden Version nicht gefunden ({src}).")
        shutil.copytree(src, os.path.join(d, sub), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    ld = _m70_launcher_dir()
    if not ld:
        raise ValueError("Starter-Quelle (PA_Rechnung_Start.py) nicht gefunden. Bitte das Update v2.0.19 oder neuer einspielen "
                         "(enthaelt den Starter im Ordner build) oder einmalig build_exe.bat ausfuehren.")
    bd = os.path.join(d, "build")
    os.makedirs(bd, exist_ok=True)
    shutil.copy2(os.path.join(ld, "PA_Rechnung_Start.py"), os.path.join(d, "PA_Rechnung_Start.py"))
    shutil.copy2(os.path.join(ld, "PA_Rechnung_Start.py"), os.path.join(bd, "PA_Rechnung_Start.py"))
    for rq in ("requirements.txt", "requirements_ocr.txt"):
        p = _m70_find_file(rq, ld)
        if p:
            shutil.copy2(p, os.path.join(d, rq))
            shutil.copy2(p, os.path.join(bd, rq))
        elif rq == "requirements.txt":
            txt = ("pywebview>=5.0\nreportlab>=4.0\npypdf>=4.0\npypdfium2>=4.20\npillow>=10.0\nopenpyxl>=3.1\npyinstaller>=6.0\n"
                   "msoffcrypto-tool>=5.4\nxlrd>=2.0\nolefile>=0.47\npyzipper>=0.3.6\ncryptography>=42\nfints>=4.0\n")
            for p2 in (os.path.join(d, rq), os.path.join(bd, rq)):
                open(p2, "w", encoding="utf-8").write(txt)
    if not os.path.isfile(os.path.join(d, "assets", "app.ico")):
        raise ValueError("assets/app.ico fehlt in der laufenden Version.")
    py = py_cmd
    if py is None:
        f = m70_find_python()
        if not f.get("ok"):
            raise ValueError(f["error"])
        py = f["cmd"]
    bat = os.path.join(d, "bau.bat")
    with open(bat, "w", encoding="utf-8") as fh:
        fh.write(m70_bat_text(d, ver, py, art, ocr and os.path.isfile(os.path.join(d, "requirements_ocr.txt"))))
    return {"dir": d, "bat": bat, "ver": ver, "art": art,
            "ziel": os.path.join(d, "dist", f"PA_Rechnung_v{ver}.exe") if art == "onefile" else os.path.join(d, "dist", f"PA_Rechnung_v{ver}")}


def _m70_q(p):
    return '"' + _m70_pct(p) + '"'


def _m70_pct(p):
    # v2.1.0: a literal % in a folder name would be expanded by cmd inside the .bat
    return str(p).replace("%", "%%")


def m70_bat_text(d, ver, py, art, ocr):
    pyc = " ".join(_m70_q(p) if (" " in p or "\\" in p or "/" in p) else _m70_pct(p) for p in py)
    J = lambda *a: os.path.join(d, *a)
    data = [(J(f"PA_Rechnung_v{ver}.py"), "."), (J("ui.html"), "."), (J("modules"), "modules"), (J("ui"), "ui"),
            (J("assets"), "assets"), (J("build"), "build")]
    opts = ["--noconfirm", "--clean", "--" + art, "--windowed", "--distpath", _m70_q(J("dist")), "--workpath", _m70_q(J("work")),
            "--specpath", _m70_q(J("work")), "--name", _m70_q(f"PA_Rechnung_v{ver}"), "--icon", _m70_q(J("assets", "app.ico"))]
    for src, dst in data:
        opts += ["--add-data", _m70_q(f"{src};{dst}")]
    for c in ("reportlab", "pypdfium2", "pypdfium2_raw", "pypdf", "openpyxl", "msoffcrypto", "pyzipper", "xlrd", "olefile",
              "webview", "fints", "mt940"):
        opts += ["--collect-all", c]
    opts += ["--collect-data", "tzdata"]   # v2.1.0: zoneinfo needs the tz database under Windows
    opts += ["--collect-submodules", "reportlab.graphics.barcode", "--collect-submodules", "cryptography", "%WINRT%",
             "--hidden-import", "clr", "--hidden-import", "PIL.Image", _m70_q(J("PA_Rechnung_Start.py"))]
    L = ["@echo off", "REM Pfeiffer-Audio Rechnung - EXE automatisch bauen (m70) v" + ver, "REM Autor: T. Pfeiffer", "chcp 65001 >nul",
         f'cd /d "{_m70_pct(d)}"', f"set PY={pyc}", "echo ##PHASE pip",
         "%PY% -m pip install --disable-pip-version-check --no-input -r requirements.txt", "if errorlevel 1 goto :err"]
    if ocr:
        L += ["echo ##PHASE ocr",
              "%PY% -m pip install --disable-pip-version-check --no-input -r requirements_ocr.txt || echo ##HINWEIS OCR-Pakete nicht installiert"]
    L += ["set WINRT=", '%PY% -c "import winrt.windows.media.ocr" >nul 2>&1 && set WINRT=--collect-all winrt',
          "echo ##PHASE pyinstaller", "%PY% -m PyInstaller " + " ".join(opts), "if errorlevel 1 goto :err",
          "echo ##OK", "exit /b 0", ":err", "echo ##FEHLER", "exit /b 1", ""]
    return "\r\n".join(L)


# ---------------------------------------------------------------- Bauen
def _m70_logdir():
    p = os.path.join(_m70_base(), "logs")
    os.makedirs(p, exist_ok=True)
    return p


def m70_build(reason="manuell"):
    with M70_RUN["lock"]:
        if M70_RUN["state"] == "laeuft":
            raise ValueError("Es wird bereits eine EXE gebaut.")
        if not _m70_is_win():
            raise ValueError("Die EXE kann nur unter Windows gebaut werden.")
        M70_RUN.update(state="laeuft", phase="vorbereiten", pct=3, msg="Bau-Ordner wird vorbereitet …", start=time.time(), ver=APP_VERSION)
    try:
        prep = m70_prepare()
    except Exception as e:
        M70_RUN.update(state="fehler", msg=str(e), pct=0)
        _m70_record(False, str(e), "", reason)
        raise ValueError(str(e))
    log = os.path.join(_m70_logdir(), f"bau_{APP_VERSION}_{time.strftime('%Y%m%d_%H%M%S')}.log")
    M70_RUN.update(log=log, art=prep["art"], dir=prep["dir"], phase="pip", pct=8, msg="Pakete werden installiert …")
    st = _m70_status()
    st["laufend"] = {"ver": APP_VERSION, "log": log, "art": prep["art"], "dir": prep["dir"], "ziel": prep["ziel"], "start": now_iso(),
                     "grund": reason}
    _m70_status_save(st)
    fh = open(log, "wb")
    try:
        # /s + outer quotes: cmd keeps the quoted path even with ( ) & @ ^ in folder names (e.g. "Jo (Privat)")
        proc = subprocess.Popen('cmd.exe /d /s /c ""' + prep["bat"] + '""', stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                cwd=prep["dir"], env=_m70_clean_env(), creationflags=M70_NO_WINDOW | M70_BELOW_NORMAL)
    except Exception as e:
        fh.close()
        M70_RUN.update(state="fehler", msg=f"Bau konnte nicht gestartet werden: {e}")
        _m70_record(False, M70_RUN["msg"], log, reason)
        raise ValueError(M70_RUN["msg"])
    M70_RUN["proc"] = proc
    threading.Thread(target=_m70_watch, args=(proc, fh, prep, log, reason), daemon=True).start()
    return {"ok": True, "ver": APP_VERSION, "art": prep["art"]}


def _m70_log_tail(path, n=60):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            sz = f.tell()
            f.seek(max(0, sz - 200000))
            txt = f.read().decode("utf-8", "replace")
        return txt.splitlines()[-n:]
    except Exception:
        return []


def _m70_progress(log):
    lines = _m70_log_tail(log, 4000)
    phase, after = "pip", 0
    for ln in lines:
        if ln.startswith("##PHASE "):
            phase, after = ln.split()[1], 0
        else:
            after += 1
    lbl, p0 = M70_PHASES.get(phase, ("läuft", 10))
    if phase == "pyinstaller":
        pct = min(96, p0 + after // 9)
    else:
        pct = min(p0 + 16, p0 + after // 4)
    last = next((l_.strip() for l_ in reversed(lines) if l_.strip() and not l_.startswith("##")), "")
    return phase, lbl, pct, last[:160]


def _m70_watch(proc, fh, prep, log, reason):
    while proc.poll() is None:
        try:
            ph, lbl, pct, last = _m70_progress(log)
            M70_RUN.update(phase=ph, pct=pct, msg=f"{lbl} … {last}")
        except Exception:
            pass
        time.sleep(1.5)
    try:
        fh.close()
    except Exception:
        pass
    _m70_finish(proc.returncode, prep["ziel"], prep["art"], log, reason, prep["dir"])


def _m70_finish(rc, ziel, art, log, reason, d):
    tail = _m70_log_tail(log, 400)
    ok = rc == 0 and any(l_.strip() == "##OK" for l_ in tail)
    exe = ziel if art == "onefile" else os.path.join(ziel, os.path.basename(ziel) + ".exe")
    if ok and not os.path.isfile(exe):
        ok = False
    st = _m70_status()
    st.pop("laufend", None)
    if M70_RUN.get("state") == "abgebrochen":
        _m70_status_save(st)
        _m70_record(False, "abgebrochen", log, reason)
        return
    if ok:
        st["bereit"] = {"ver": M70_RUN.get("ver") or APP_VERSION, "art": art, "quelle": ziel, "exe": exe, "dir": d, "fertig": now_iso(),
                        "groesse": os.path.getsize(exe)}
        st["fehlversuch"].pop(st["bereit"]["ver"], None)
        _m70_status_save(st)
        M70_RUN.update(state="fertig", pct=100, phase="fertig", msg="Neue EXE ist fertig gebaut.")
        _m70_record(True, "fertig", log, reason)
    else:
        err = _m70_explain(tail)
        st["fehlversuch"][APP_VERSION] = int(st["fehlversuch"].get(APP_VERSION) or 0) + 1
        _m70_status_save(st)
        M70_RUN.update(state="fehler", pct=0, phase="fehler", msg=err)
        _m70_record(False, err, log, reason)


def _m70_explain(tail):
    t = "\n".join(tail).lower()
    if "no module named pip" in t:
        return "In diesem Python fehlt pip. Python neu installieren (python.org) oder \"python -m ensurepip\" ausfuehren."
    if "could not find a version" in t or "failed to establish a new connection" in t or "getaddrinfo failed" in t:
        return "Pakete konnten nicht geladen werden - keine Internetverbindung? Spaeter erneut bauen."
    if "permission denied" in t or "zugriff verweigert" in t:
        return "Zugriff verweigert (Virenscanner oder geoeffnete Datei). Erneut versuchen, ggf. Bau-Ordner im Virenscanner freigeben."
    if "no module named pyinstaller" in t:
        return "PyInstaller fehlt und konnte nicht installiert werden."
    last = [l_ for l_ in tail if l_.strip() and not l_.startswith("##")][-3:]
    return "EXE-Bau fehlgeschlagen. " + (" | ".join(x_.strip()[:140] for x_ in last) or "Details im Log.")


def _m70_record(ok, msg, log, reason):
    st = _m70_status()
    dauer = round(time.time() - (M70_RUN.get("start") or time.time()))
    st["bauten"].append({"ver": M70_RUN.get("ver") or APP_VERSION, "datum": now_iso(), "ok": bool(ok), "msg": (msg or "")[:400],
                         "log": log, "art": M70_RUN.get("art") or "", "dauer_s": dauer, "grund": reason})
    _m70_status_save(st)


def m70_cancel():
    p = M70_RUN.get("proc")
    if M70_RUN["state"] != "laeuft" or not p:
        return {"ok": True, "laeuft": False}
    M70_RUN["state"] = "abgebrochen"
    M70_RUN["msg"] = "Bau abgebrochen."
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=20, creationflags=M70_NO_WINDOW)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    return {"ok": True}


def m70_check_orphan():
    """a build that was still running when the program closed: finished in the meantime?"""
    st = _m70_status()
    lf = st.get("laufend")
    if not lf or M70_RUN["state"] == "laeuft":
        return
    tail = _m70_log_tail(lf.get("log") or "", 400)
    if any(l_.strip() in ("##OK", "##FEHLER") for l_ in tail):
        M70_RUN.update(ver=lf.get("ver") or APP_VERSION, art=lf.get("art") or "")
        _m70_finish(0 if any(l_.strip() == "##OK" for l_ in tail) else 1, lf["ziel"], lf.get("art") or "onefile", lf.get("log") or "",
                    lf.get("grund") or "", lf.get("dir") or "")
    elif lf.get("start", "") < (datetime.datetime.now() - datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"):   # same format as now_iso()
        st.pop("laufend", None)
        _m70_status_save(st)


# ---------------------------------------------------------------- Tauschen
def _m70_ps(s):
    return "'" + str(s).replace("'", "''") + "'"


def m70_swap_script(pid, alt_exe, art, quelle, neu_exe, ziel_dir, alt_dir, ergebnis, log, starten, bau_dir):
    P = _m70_ps
    lines = [
        "# Pfeiffer-Audio Rechnung - EXE tauschen (m70). Autor: T. Pfeiffer",
        "$ErrorActionPreference = 'Stop'",
        f"$pidWait = {int(pid)}", f"$alt = {P(alt_exe)}", f"$art = {P(art)}", f"$quelle = {P(quelle)}", f"$neuExe = {P(neu_exe)}",
        f"$zielDir = {P(ziel_dir)}", f"$altDir = {P(alt_dir)}", f"$ergebnis = {P(ergebnis)}", f"$log = {P(log)}",
        f"$bauDir = {P(bau_dir)}", f"$starten = ${'true' if starten else 'false'}",
        "function L($t) { try { Add-Content -LiteralPath $log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $t) -Encoding UTF8 } catch {} }",
        "function Retry([scriptblock]$sb) { for ($i = 0; $i -lt 40; $i++) { try { & $sb; return } catch { Start-Sleep -Milliseconds 750 } }; & $sb }",
        "function Fertig($ok, $text, $n) { $j = @{ ok = $ok; text = $text; neu = $neuExe; alt = $alt; verknuepfungen = $n; zeit = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') } | ConvertTo-Json; [IO.File]::WriteAllText($ergebnis, $j) }",
        "L ('Tausch startet, warte auf Programmende (PID ' + $pidWait + ')')",
        "try { Wait-Process -Id $pidWait -Timeout 120 -ErrorAction SilentlyContinue } catch {}",
        "Start-Sleep -Milliseconds 1200",
        "$verschoben = @()",
        "$intNeu = Join-Path $zielDir '_internal'",
        "$intAlt = Join-Path $zielDir '_internal_m70alt'",     # same folder = same drive: a directory rename always works
        "$intGesichert = $false",
        # the previous backup is only parked (sibling folder = same drive, rename) and removed after a successful swap
        "$altVorher = $altDir.TrimEnd('\\') + '_vorher'",
        "$altGeparkt = $false",
        "try {",
        "  if (Test-Path -LiteralPath $altVorher) { Remove-Item -LiteralPath $altVorher -Recurse -Force -ErrorAction SilentlyContinue }",
        "  if (Test-Path -LiteralPath $altDir) { Retry { Move-Item -LiteralPath $altDir -Destination $altVorher -Force }; $altGeparkt = $true }",
        "  New-Item -ItemType Directory -Path $altDir -Force | Out-Null",
        "  $altName = Split-Path $alt -Leaf",
        "  Retry { Move-Item -LiteralPath $alt -Destination (Join-Path $altDir $altName) -Force }",
        "  $verschoben += ,@((Join-Path $altDir $altName), $alt)",
        "  if ($art -eq 'onedir') {",
        "    if (Test-Path -LiteralPath $intAlt) { Remove-Item -LiteralPath $intAlt -Recurse -Force -ErrorAction SilentlyContinue }",
        "    if (Test-Path -LiteralPath $intNeu) { Retry { Move-Item -LiteralPath $intNeu -Destination $intAlt -Force }; $intGesichert = $true }",
        # a retry after a partial copy must start clean - otherwise PowerShell copies INTO the existing folder (_internal\\_internal)
        "    Retry { if (Test-Path -LiteralPath $intNeu) { Remove-Item -LiteralPath $intNeu -Recurse -Force }; Copy-Item -LiteralPath (Join-Path $quelle '_internal') -Destination $intNeu -Recurse -Force }",
        "    Retry { Copy-Item -LiteralPath (Join-Path $quelle ((Split-Path $quelle -Leaf) + '.exe')) -Destination $neuExe -Force }",
        "  } else {",
        "    Retry { Copy-Item -LiteralPath $quelle -Destination $neuExe -Force }",
        "  }",
        "  if (-not (Test-Path -LiteralPath $neuExe)) { throw 'neue EXE fehlt nach dem Kopieren' }",
        "  L ('Neue EXE: ' + $neuExe)",
        "} catch {",
        "  $err = $_.Exception.Message",
        "  L ('FEHLER: ' + $err + ' - stelle alte EXE wieder her')",
        "  try { if ($intGesichert -and (Test-Path -LiteralPath $intAlt)) { if (Test-Path -LiteralPath $intNeu) { Remove-Item -LiteralPath $intNeu -Recurse -Force }; Move-Item -LiteralPath $intAlt -Destination $intNeu -Force } } catch { L ('Wiederherstellen _internal fehlgeschlagen: ' + $_.Exception.Message) }",
        "  try { if ((Test-Path -LiteralPath $neuExe) -and ($neuExe -ine $alt)) { Remove-Item -LiteralPath $neuExe -Force } } catch {}",
        "  foreach ($v in $verschoben) { try { Move-Item -LiteralPath $v[0] -Destination $v[1] -Force } catch { L ('Wiederherstellen fehlgeschlagen: ' + $v[1]) } }",
        "  try { if ($altGeparkt -and (Test-Path -LiteralPath $altVorher) -and (Test-Path -LiteralPath $alt)) { if (Test-Path -LiteralPath $altDir) { Remove-Item -LiteralPath $altDir -Recurse -Force }; Move-Item -LiteralPath $altVorher -Destination $altDir -Force } } catch { L ('Alte Sicherung nicht zurueckgelegt: ' + $_.Exception.Message) }",
        "  Fertig $false ('Tausch fehlgeschlagen: ' + $err + ' - die alte EXE wird weiter benutzt.') 0",
        "  if ($starten -and (Test-Path -LiteralPath $alt)) { Start-Process -FilePath $alt -WorkingDirectory $zielDir }",
        "  exit 1",
        "}",
        "# old _internal: keep it as backup in exe_alt (may be another drive -> copy), otherwise just remove it",
        "if ($intGesichert -and (Test-Path -LiteralPath $intAlt)) {",
        "  try { Copy-Item -LiteralPath $intAlt -Destination (Join-Path $altDir '_internal') -Recurse -Force -ErrorAction Stop } catch { L ('Sicherung _internal nicht kopiert: ' + $_.Exception.Message) }",
        "  try { Remove-Item -LiteralPath $intAlt -Recurse -Force -ErrorAction Stop } catch { L ('Alter Ordner _internal_m70alt bleibt liegen: ' + $_.Exception.Message) }",
        "}",
        "if ($altGeparkt -and (Test-Path -LiteralPath $altVorher)) { try { Remove-Item -LiteralPath $altVorher -Recurse -Force -ErrorAction Stop } catch { L ('Vorherige Sicherung bleibt liegen: ' + $_.Exception.Message) } }",
        "$n = 0",
        "try {",
        "  $sh = New-Object -ComObject WScript.Shell",
        "  $orte = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory'), [Environment]::GetFolderPath('StartMenu'), [Environment]::GetFolderPath('CommonStartMenu'), (Join-Path $env:APPDATA 'Microsoft\\Internet Explorer\\Quick Launch'), [Environment]::GetFolderPath('Startup'))",
        "  foreach ($o in $orte) {",
        "    if (-not $o -or -not (Test-Path -LiteralPath $o)) { continue }",
        "    foreach ($f in (Get-ChildItem -LiteralPath $o -Filter *.lnk -Recurse -Force -ErrorAction SilentlyContinue)) {",
        "      $fp = $f.FullName",
        "      try {",
        "        $l = $sh.CreateShortcut($fp)",
        "        if ($l.TargetPath -and ($l.TargetPath -ieq $alt)) {",
        "          $l.TargetPath = $neuExe",
        "          if (-not $l.WorkingDirectory -or ($l.WorkingDirectory -ieq $zielDir)) { $l.WorkingDirectory = $zielDir }",
        "          if ((-not $l.IconLocation) -or ($l.IconLocation -like ($alt + '*')) -or ($l.IconLocation -like ',*')) { $l.IconLocation = $neuExe + ',0' }",
        "          $l.Save(); $n++; L ('Verknuepfung umgebogen: ' + $fp)",
        "        }",
        "      } catch { L ('Verknuepfung nicht geaendert: ' + $fp) }",
        "    }",
        "  }",
        "} catch { L ('Verknuepfungen: ' + $_.Exception.Message) }",
        "try { if ($bauDir -and (Test-Path -LiteralPath $bauDir)) { Remove-Item -LiteralPath $bauDir -Recurse -Force } } catch {}",
        "Fertig $true ('Neue EXE eingesetzt.') $n",
        "L ('Tausch fertig, ' + $n + ' Verknuepfung(en) umgebogen')",
        "if ($starten) { Start-Process -FilePath $neuExe -WorkingDirectory $zielDir }",
        "exit 0",
        "",
    ]
    return "\r\n".join(lines)


def m70_ready():
    st = _m70_status()
    b = st.get("bereit")
    if not b:
        return None
    if not os.path.isfile(b.get("exe") or ""):
        st.pop("bereit", None)
        _m70_status_save(st)
        return None
    return b


def m70_launch_swap(starten=True):
    if not getattr(sys, "frozen", False):
        raise ValueError("Das Programm laeuft ohne EXE (direkt aus Python) - es gibt keine EXE zum Tauschen.")
    if not _m70_is_win():
        raise ValueError("EXE-Tausch geht nur unter Windows.")
    b = m70_ready()
    if not b:
        raise ValueError("Es liegt keine fertig gebaute neue EXE bereit.")
    if os.environ.get("PA_M70_TAUSCH_LAEUFT"):
        return {"ok": True, "schon": True}
    alt = sys.executable
    ziel_dir = os.path.dirname(alt)
    art_now = "onedir" if os.path.isdir(os.path.join(ziel_dir, "_internal")) else "onefile"
    if b["art"] != art_now:
        raise ValueError(f"Die neue EXE wurde als {'Ordner' if b['art'] == 'onedir' else 'Einzeldatei'} gebaut, die laufende ist eine "
                         f"{'Ordner' if art_now == 'onedir' else 'Einzeldatei'}-EXE. Bitte mit Bau-Variante \"wie bisher\" neu bauen.")
    neu = os.path.join(ziel_dir, f"PA_Rechnung_v{b['ver']}.exe")
    ps1 = os.path.join(APP_DIR, "exe_tausch.ps1")
    erg = os.path.join(APP_DIR, "exe_tausch_ergebnis.json")
    try:
        os.remove(erg)
    except Exception:
        pass
    with open(ps1, "w", encoding="utf-8-sig") as fh:     # BOM: PowerShell 5 liest sonst Umlaute falsch
        fh.write(m70_swap_script(os.getpid(), alt, b["art"], b["quelle"], neu, ziel_dir, os.path.join(APP_DIR, "exe_alt"), erg,
                                 os.path.join(_m70_logdir(), "tausch.log"), starten, b.get("dir") or ""))
    st = _m70_status()
    st["tausch"] = {"ver": b["ver"], "alt": alt, "neu": neu, "gestartet": now_iso()}
    _m70_status_save(st)
    os.environ["PA_M70_TAUSCH_LAEUFT"] = "1"
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", ps1],
                     creationflags=M70_DETACHED | M70_NO_WINDOW, close_fds=True, env=_m70_clean_env(),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "neu": neu}


M70_AFTER = {"done": False, "lock": threading.Lock()}


def m70_after_start_once():
    """evaluate the swap result once per program start - early, so the UI (bootstrap) already sees it"""
    with M70_AFTER["lock"]:
        if M70_AFTER["done"]:
            return
        M70_AFTER["done"] = True
        try:
            m70_after_start()
        except Exception:
            traceback.print_exc()


def m70_after_start():
    """on program start: evaluate a finished swap, clean up, maybe start the automatic build"""
    st = _m70_status()
    erg_p = os.path.join(APP_DIR, "exe_tausch_ergebnis.json")
    erg = _rj(erg_p)
    if erg is None and os.path.exists(erg_p):
        try:
            erg = json.loads(open(erg_p, encoding="utf-8-sig").read())
        except Exception:
            erg = None
    if erg:
        st["ergebnis"] = dict(erg, gesehen=False)
        if erg.get("ok"):
            st.pop("bereit", None)
        st.pop("tausch", None)
        try:
            os.remove(erg_p)
        except Exception:
            pass
        _m70_status_save(st)
    info = m70_exe_info()
    b = st.get("bereit")
    if b and info["frozen"] and info["builtin"] and vtuple(b["ver"]) <= vtuple(info["builtin"]) and \
            os.path.normcase(sys.executable) == os.path.normcase(os.path.join(os.path.dirname(sys.executable), f"PA_Rechnung_v{b['ver']}.exe")):
        st.pop("bereit", None)
        _m70_status_save(st)
    m70_check_orphan()


def m70_auto_loop():
    m70_after_start_once()
    time.sleep(25)
    try:
        s = m70_settings()
        info = m70_exe_info()
        st = _m70_status()
        b = st.get("bereit")
        if not (s.get("auto_bau") and info["frozen"] and info["veraltet"] and _m70_is_win()):
            return
        if b and vtuple(b["ver"]) >= vtuple(APP_VERSION):
            return
        if int(st["fehlversuch"].get(APP_VERSION) or 0) >= 2 or st.get("laufend"):
            return
        if not m70_find_python().get("ok"):
            st["fehlversuch"][APP_VERSION] = 2
            _m70_status_save(st)
            _m70_record(False, M70_NO_PY, "", "automatisch")
            M70_RUN.update(state="fehler", msg=M70_NO_PY)
            return
        m70_build("automatisch nach Update")
    except Exception:
        traceback.print_exc()


HOOK_START.append(m70_auto_loop)


# swap automatically when the program is closed normally
def _m70_on_exit():
    try:
        if M70_RUN.get("_swapped") or not getattr(sys, "frozen", False) or not _m70_is_win():
            return
        if m70_settings().get("auto_tausch") and m70_ready():
            M70_RUN["_swapped"] = True
            m70_launch_swap(starten=False)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":     # nicht im Selbsttest-Namensraum
    atexit.register(_m70_on_exit)

# restart after an update etc.: start into the new EXE when one is ready
@chain_step("restart_app", "m70_exe_erneuern")
def _m70_step_restart_app(_next, delay=1.0):
    try:
        if (not os.environ.get("PA_RECHNUNG_NO_RESTART") and getattr(sys, "frozen", False) and _m70_is_win()
                and m70_settings().get("auto_tausch") and m70_ready()):
            m70_launch_swap(starten=True)
            M70_RUN["_swapped"] = True
            threading.Timer(delay, lambda: os._exit(0)).start()
            return True
    except Exception:
        traceback.print_exc()
    return _next(delay)


# a new update was installed: forget failed attempts for that version
@chain_step("install_paupdate", "m70_exe_erneuern")
def _m70_step_install_paupdate(_next, path, allow_same=False):
    r = _next(path, allow_same)
    try:
        if r.get("ok") and r.get("version"):
            st = _m70_status()
            st["fehlversuch"].pop(r["version"], None)
            st["neu_installiert"] = {"ver": r["version"], "zeit": now_iso()}
            _m70_status_save(st)
    except Exception:
        pass
    return r


# ---------------------------------------------------------------- API
def m70_state():
    st = _m70_status()
    run = {k: M70_RUN[k] for k in ("state", "ver", "phase", "pct", "msg", "art")}
    if run["state"] == "idle" and st.get("laufend"):
        run.update(state="laeuft_extern", msg="Ein Bau aus einer frueheren Sitzung laeuft evtl. noch.")
    return {"ok": True, "info": m70_exe_info(), "settings": m70_settings(), "run": run, "bereit": m70_ready(),
            "bauten": list(reversed(st.get("bauten") or []))[:10], "ergebnis": st.get("ergebnis"), "variante": m70_variante(),
            "py": M70_RUN["py_cache"], "is_win": _m70_is_win(), "app_dir": APP_DIR}


def _m70_get_info(h, qs):
    return h._send(200, m70_state())


def _m70_get_log(h, qs):
    st = _m70_status()
    p = qs.get("log") or M70_RUN.get("log") or ((st.get("bauten") or [{}])[-1].get("log") or "")
    if qs.get("tausch"):
        p = os.path.join(_m70_logdir(), "tausch.log")
    base = os.path.normcase(os.path.abspath(_m70_base())) + os.sep
    if p and not os.path.normcase(os.path.abspath(p)).startswith(base):
        return h._send(200, {"ok": False, "error": "Log nicht erlaubt."})
    return h._send(200, {"ok": True, "path": p, "lines": _m70_log_tail(p, 600) if p else []})


def _m70_post_build(h, d):
    return h._send(200, m70_build("manuell"))


def _m70_post_cancel(h, d):
    return h._send(200, m70_cancel())


def _m70_post_swap(h, d):
    r = m70_launch_swap(starten=True)
    M70_RUN["_swapped"] = True
    threading.Timer(1.2, lambda: os._exit(0)).start()
    return h._send(200, r)


def _m70_post_discard(h, d):
    st = _m70_status()
    b = st.pop("bereit", None)
    _m70_status_save(st)
    if b and b.get("dir"):
        shutil.rmtree(b["dir"], ignore_errors=True)
    return h._send(200, {"ok": True})


def _m70_post_settings(h, d):
    s = m70_settings()
    for k in ("auto_bau", "auto_tausch", "ocr"):
        if k in d:
            s[k] = bool(d[k])
    if "python" in d:
        s["python"] = str(d.get("python") or "").strip().strip('"')[:400]
        M70_RUN["py_cache"] = None
    if d.get("variante") in ("auto", "onefile", "onedir"):
        s["variante"] = d["variante"]
    set_setting("m70", s)
    return h._send(200, {"ok": True, "settings": s})


def _m70_post_python(h, d):
    s = m70_settings()
    if "python" in d:
        s["python"] = str(d.get("python") or "").strip().strip('"')
    return h._send(200, dict(m70_find_python(force=True, s=s), ok_req=True))


def _m70_post_seen(h, d):
    st = _m70_status()
    if st.get("ergebnis"):
        st["ergebnis"]["gesehen"] = True
        _m70_status_save(st)
    return h._send(200, {"ok": True})


HOOK_GET["/api/m70/info"] = _m70_get_info
HOOK_GET["/api/m70/log"] = _m70_get_log
HOOK_POST["/api/m70/bauen"] = _m70_post_build
HOOK_POST["/api/m70/abbrechen"] = _m70_post_cancel
HOOK_POST["/api/m70/tauschen"] = _m70_post_swap
HOOK_POST["/api/m70/verwerfen"] = _m70_post_discard
HOOK_POST["/api/m70/settings"] = _m70_post_settings
HOOK_POST["/api/m70/python"] = _m70_post_python
HOOK_POST["/api/m70/gesehen"] = _m70_post_seen


def _m70_boot(d):
    try:
        if __name__ == "__main__":     # not inside the self test namespace (it shares the real program folder)
            m70_after_start_once()
        st = _m70_status()
        e = st.get("ergebnis")
        info = m70_exe_info()
        d["m70"] = {"bereit": (m70_ready() or {}).get("ver") or "", "laeuft": M70_RUN["state"] == "laeuft",
                    "ergebnis": e if e and not e.get("gesehen") else None, "veraltet": info["veraltet"],
                    "auto_tausch": bool(info["frozen"] and m70_settings().get("auto_tausch"))}
    except Exception:
        d["m70"] = {}


HOOK_BOOT.append(_m70_boot)


# ---------------------------------------------------------------- Selbsttest (Trockenlauf, baut nichts)
def _m70_selftest():
    err = []
    tmp = tempfile.mkdtemp(prefix="m70_")
    try:
        if not _m70_launcher_dir():
            return err     # aeltere Installation ohne Starter-Quelle: nichts zu pruefen
        for art in ("onefile", "onedir"):
            r = m70_prepare(target_base=tmp, ver="9.9.9", py_cmd=["C:\\Python Test\\python.exe"], art=art, ocr=True)
            d = r["dir"]
            for p in ("PA_Rechnung_v9.9.9.py", "ui.html", "PA_Rechnung_Start.py", "requirements.txt", "bau.bat",
                      os.path.join("build", "PA_Rechnung_Start.py"), os.path.join("assets", "app.ico")):
                if not os.path.isfile(os.path.join(d, p)):
                    err.append(f"m70: Bau-Ordner ohne {p}")
            if not any(f.endswith(".py") for f in os.listdir(os.path.join(d, "modules"))):
                err.append("m70: Bau-Ordner ohne Module")
            bat = open(r["bat"], encoding="utf-8").read()
            for must in ("-m PyInstaller", "--" + art, '"C:\\Python Test\\python.exe"', "##OK", "requirements_ocr.txt", "build;build"):
                if must not in bat:
                    err.append(f"m70: bau.bat ({art}) ohne {must}")
        ps = m70_swap_script(1234, "C:\\Pro'gramme\\PA_Rechnung_v2.0.18.exe", "onefile", "C:\\x\\dist\\PA_Rechnung_v9.9.9.exe",
                             "C:\\Pro'gramme\\PA_Rechnung_v9.9.9.exe", "C:\\Pro'gramme", "C:\\a\\exe_alt", "C:\\a\\e.json",
                             "C:\\a\\t.log", True, "C:\\x")
        for must in ("Wait-Process -Id $pidWait", "CreateShortcut", "Pro''gramme", "Move-Item", "Start-Process -FilePath $neuExe", "_internal_m70alt"):
            if must not in ps:
                err.append(f"m70: Tausch-Skript ohne {must}")
        if "$starten = $true" not in ps:
            err.append("m70: Tausch-Skript startet nicht neu")
    except Exception as e:
        err.append(f"m70 Ausnahme: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return err


HOOK_SELFTEST.append(_m70_selftest)
