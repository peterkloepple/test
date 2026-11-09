# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m15_update
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ---------------- v1.6.0: program updates without rebuilding the EXE ----------------
APP_DIR = os.environ.get("PA_RECHNUNG_APPDIR") or os.path.join(DATA_DIR, "Programm")
CORE_SOURCE = os.environ.get("PA_RECHNUNG_CORE_SOURCE") or "direkt"
LAUNCHER_VER = os.environ.get("PA_RECHNUNG_LAUNCHER") or ""
UPDATE_FORMAT = "PA-Rechnung-Update"
_START_MARKED = [False]


def vtuple(v):
    t = [int(n) for n in re.findall(r"\d+", str(v or "0"))[:4]]
    return tuple(t + [0] * (4 - len(t)))


VER_RE = re.compile(r"\d+(\.\d+){1,3}")


def _rj(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _wj(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def mark_start_ok():
    if _START_MARKED[0] or not LAUNCHER_VER:
        return
    _START_MARKED[0] = True
    sp = os.path.join(APP_DIR, "start.json")
    st = _rj(sp, {}) or {}
    st.update({"ok": True, "tries": 0, "ok_zeit": now_iso()})
    try:
        _wj(sp, st)
    except Exception:
        pass


def _has_module(name):
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def installed_updates():
    vd = os.path.join(APP_DIR, "versionen")
    out = []
    if os.path.isdir(vd):
        for v in os.listdir(vd):
            m = _rj(os.path.join(vd, v, "update.json"))
            if m and not v.endswith(".neu"):
                out.append({"version": v, "datum": m.get("date", ""), "changelog": m.get("changelog", "")})
    return sorted(out, key=lambda r: vtuple(r["version"]), reverse=True)


def update_info():
    act = _rj(os.path.join(APP_DIR, "aktiv.json"), {}) or {}
    hin = _rj(os.path.join(APP_DIR, "hinweis.json"))
    builtin = os.environ.get("PA_RECHNUNG_BUILTIN_VER") or (APP_VERSION if CORE_SOURCE != "update" else "")
    return {"version": APP_VERSION, "source": CORE_SOURCE, "launcher": LAUNCHER_VER, "builtin": builtin,
            "active": act.get("version") or "builtin", "defekt": act.get("defekt") or [], "installed": installed_updates(),
            "hinweis": hin, "app_dir": APP_DIR}


def restart_app(delay=1.0):
    if os.environ.get("PA_RECHNUNG_NO_RESTART"):
        return False
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        lp = os.environ.get("PA_RECHNUNG_LAUNCHER_PATH")
        cmd = [sys.executable, lp] if lp else [sys.executable, os.path.abspath(__file__)]
    cmd += ["--wait-pid", str(os.getpid())]
    if "--server" in sys.argv:
        cmd.append("--server")
    env = dict(os.environ)
    for k in list(env):
        if k.startswith("_MEI") or k.startswith("_PYI") or k in ("PA_RECHNUNG_RES", "PA_RECHNUNG_RES_FALLBACK", "PA_RECHNUNG_CORE_SOURCE",
                                                                 "PA_RECHNUNG_BUILTIN_VER", "PA_RECHNUNG_LAUNCHER"):
            env.pop(k, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    kw = {"env": env, "close_fds": True}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)
    threading.Timer(delay, lambda: os._exit(0)).start()
    return True


def read_update_manifest(path):
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ValueError("Das ist keine gültige Update-Datei (.paupdate).")
    try:
        man = json.loads(z.read("update.json").decode("utf-8"))
    except KeyError:
        z.close()
        raise ValueError("Keine Update-Datei für Pfeiffer-Audio Rechnung (update.json fehlt).")
    if man.get("format") != UPDATE_FORMAT:
        z.close()
        raise ValueError("Keine Update-Datei für Pfeiffer-Audio Rechnung.")
    return z, man


def install_paupdate(path, allow_same=False, prune=True):
    z, man = read_update_manifest(path)
    with z:
        ver = str(man.get("version") or "")
        main_ = man.get("main") or "PA_Rechnung.py"
        if not VER_RE.fullmatch(ver):
            raise ValueError("Update-Datei ohne gültige Versionsnummer.")
        if not isinstance(main_, str) or not re.fullmatch(r"[\w\-. ]+\.py", main_):
            raise ValueError("Update-Datei mit ungültiger Programmdatei.")
        if vtuple(ver) < vtuple(APP_VERSION) or (vtuple(ver) == vtuple(APP_VERSION) and not allow_same):
            raise ValueError(f"v{ver} ist nicht neuer als die laufende Version v{APP_VERSION}. "
                             "Ältere Versionen kannst du unter „Installierte Versionen“ wieder aktivieren.")
        if not LAUNCHER_VER:
            raise ValueError("Dein Programm wurde noch ohne Starter gebaut. Bitte einmalig die EXE ab v1.6.0 bauen "
                             "(build_exe.bat) – danach kommen alle Updates nur noch als .paupdate-Datei.")
        if vtuple(man.get("min_launcher") or "0") > vtuple(LAUNCHER_VER):
            raise ValueError(f"Dieses Update braucht eine neuere EXE (Starter ab v{man.get('min_launcher')}, vorhanden v{LAUNCHER_VER}). "
                             "Bitte einmalig build_exe.bat aus dem Programm-Paket ausführen.")
        missing = [m for m in (man.get("requires") or []) if not _has_module(m)]
        if missing:
            raise ValueError("Dieses Update braucht Bibliotheken, die in deiner EXE fehlen (" + ", ".join(missing) +
                             "). Bitte einmalig die neue EXE bauen (build_exe.bat).")
        names = set(z.namelist())
        files = man.get("files") or []
        if not isinstance(files, list) or not all(isinstance(f, dict) and isinstance(f.get("path"), str) and f["path"].strip()
                                                  and not f["path"].endswith(("/", "\\")) for f in files):
            raise ValueError("Update-Datei unvollständig oder beschädigt (Dateiliste).")
        if not any(f.get("path") == main_ for f in files):
            raise ValueError("Update-Datei unvollständig (Programmdatei fehlt).")
        for f in files:
            pth = f.get("path") or ""
            if pth.startswith(("/", "\\")) or ".." in re.split(r"[\\/]", pth) or ":" in pth:
                raise ValueError("Update-Datei enthält ungültige Pfade.")
            if "files/" + pth not in names:
                raise ValueError(f"Update-Datei unvollständig ({pth} fehlt).")
            if hashlib.sha256(z.read("files/" + pth)).hexdigest() != f.get("sha256"):
                raise ValueError(f"Update-Datei ist beschädigt ({pth}) – bitte neu herunterladen.")
        try:
            src_ = z.read("files/" + main_).decode("utf-8")
            compile(src_, main_, "exec")
        except (SyntaxError, UnicodeDecodeError) as e:
            raise ValueError(f"Update-Datei fehlerhaft ({e}) – nicht installiert.")
        mv_ = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', src_, re.M)
        if not mv_ or vtuple(mv_.group(1)) != vtuple(ver):
            raise ValueError(f"Update-Datei widersprüchlich: Programm meldet v{mv_.group(1) if mv_ else '?'}, Paket v{ver}.")
        base = os.path.join(APP_DIR, "versionen")
        vd, tmpd = os.path.join(base, ver), os.path.join(base, ver + ".neu")
        shutil.rmtree(tmpd, ignore_errors=True)
        try:
            for f in files:
                dst = os.path.join(tmpd, *re.split(r"[\\/]", f["path"]))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as fh:
                    fh.write(z.read("files/" + f["path"]))
            _wj(os.path.join(tmpd, "update.json"), man)
            if os.path.isdir(vd):
                old_ = vd + ".alt"
                shutil.rmtree(old_, ignore_errors=True)
                os.replace(vd, old_)
                shutil.rmtree(old_, ignore_errors=True)
            os.replace(tmpd, vd)
        except OSError as e:
            shutil.rmtree(tmpd, ignore_errors=True)
            raise ValueError(f"Update konnte nicht abgelegt werden: {e}")
    ap = os.path.join(APP_DIR, "aktiv.json")
    act = _rj(ap, {}) or {}
    prev = APP_VERSION if CORE_SOURCE == "update" else "builtin"
    act = {"version": ver, "main": main_, "vorher": prev, "defekt": [v for v in (act.get("defekt") or []) if v != ver],
           "installiert": now_iso()}
    _wj(ap, act)
    try:
        os.remove(os.path.join(APP_DIR, "start.json"))
    except Exception:
        pass
    if prune:
        prune_versions(ver, prev)
    return {"ok": True, "version": ver, "changelog": man.get("changelog", ""), "restart": True, "vorher": prev}


def prune_versions(ver, prev):
    """keep the active, the previous and the three newest versions"""
    keep = {ver, prev} | {r["version"] for r in installed_updates()[:3]}
    for r in installed_updates():
        if r["version"] not in keep:
            shutil.rmtree(os.path.join(APP_DIR, "versionen", r["version"]), ignore_errors=True)


def activate_version(ver):
    ap = os.path.join(APP_DIR, "aktiv.json")
    act = _rj(ap, {}) or {}
    if ver != "builtin" and not VER_RE.fullmatch(str(ver)):
        raise ValueError("Ungültige Version.")
    if ver != "builtin":
        if not os.path.isfile(os.path.join(APP_DIR, "versionen", ver, "update.json")):
            raise ValueError(f"Version {ver} ist nicht installiert.")
        man = _rj(os.path.join(APP_DIR, "versionen", ver, "update.json"), {}) or {}
        act["main"] = man.get("main") or "PA_Rechnung.py"
    builtin = os.environ.get("PA_RECHNUNG_BUILTIN_VER") or "0"
    act.update({"vorher": APP_VERSION if CORE_SOURCE == "update" else "builtin", "version": ver,
                "fest": ver != "builtin" and vtuple(ver) < vtuple(builtin), "fest_builtin": builtin,
                "defekt": [v for v in (act.get("defekt") or []) if v != ver]})
    _wj(ap, act)
    try:
        os.remove(os.path.join(APP_DIR, "start.json"))
    except Exception:
        pass
    return {"ok": True, "version": ver}
