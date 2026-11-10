# -*- coding: utf-8 -*-
# PA Rechnung - iPhone/iPad-App: Programmwahl und Start  v1.0.0
# Die App bringt eine Programmversion mit (Ordner "programm"). Neuere Versionen holt das Programm beim Abgleich
# vom PC und legt sie im Programmordner der App ab (aktiv.json + Ordner <Version>). Dieser Starter nimmt die
# neuere von beiden. Startet ein Update zweimal nicht (oder mit Fehler), wird es als defekt gemerkt und es laeuft
# wieder die mitgelieferte Version - die App bleibt immer benutzbar.
# Ohne toga/iOS-Teile, damit sich der Ablauf auch am PC pruefen laesst.
# Autor: T. Pfeiffer
import json
import os
import re
import runpy
import shutil
import socket
import sys
import time
import traceback

STARTER_VERSION = "1.0.0"


def vt(v):
    return tuple(int(n) for n in re.findall(r"\d+", str(v or ""))[:4])


def core_in(d):
    """newest PA_Rechnung_v*.py in a folder -> (path, version) or (None, "")"""
    best, bv = None, ""
    try:
        for fn in os.listdir(d):
            m = re.fullmatch(r"PA_Rechnung_v([\d.]+)\.py", fn)
            if m and vt(m.group(1)) > vt(bv):
                best, bv = os.path.join(d, fn), m.group(1)
    except OSError:
        pass
    return best, bv


def _rj(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _wj(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def mark_defekt(prog_dir, version, sha, why):
    lst = [e for e in (_rj(os.path.join(prog_dir, "defekt.json"), []) or []) if isinstance(e, dict)]
    lst.append({"version": version, "sha": sha, "grund": str(why)[-800:], "zeit": time.strftime("%Y-%m-%d %H:%M:%S")})
    _wj(os.path.join(prog_dir, "defekt.json"), lst[-20:])
    print(f"INIT Starter: Programm-Update v{version} als defekt gemerkt - {str(why)[-200:]}")


def choose(bundled, prog_dir):
    """-> (core file, version, 'app' | 'update', sha)"""
    b_core, b_ver = core_in(bundled)
    if not b_core:
        raise FileNotFoundError("Programmdatei PA_Rechnung_v*.py fehlt im App-Paket")
    os.makedirs(prog_dir, exist_ok=True)
    act = _rj(os.path.join(prog_dir, "aktiv.json"), {}) or {}
    ver, sha = str(act.get("version") or ""), str(act.get("sha") or "")
    u_core, u_ver = core_in(os.path.join(prog_dir, ver)) if re.fullmatch(r"\d+(\.\d+){1,3}", ver) else (None, "")
    bad = any(isinstance(e, dict) and e.get("sha") == sha for e in (_rj(os.path.join(prog_dir, "defekt.json"), []) or []))
    if u_core and vt(u_ver) > vt(b_ver) and not bad:
        sp = os.path.join(prog_dir, "start.json")
        st = _rj(sp, {}) or {}
        if st.get("sha") != sha:
            st = {"sha": sha, "version": u_ver, "tries": 0, "ok": False}
        if st.get("ok") or int(st.get("tries") or 0) < 2:
            st["tries"] = int(st.get("tries") or 0) + 1
            _wj(sp, st)
            return u_core, u_ver, "update", sha
        mark_defekt(prog_dir, u_ver, sha, "App wurde zweimal beim Start beendet")
    # tidy up: update folders that the installed app has caught up with
    try:
        for fn in os.listdir(prog_dir):
            if re.fullmatch(r"\d+(\.\d+){1,3}", fn) and vt(fn) <= vt(b_ver):
                shutil.rmtree(os.path.join(prog_dir, fn), ignore_errors=True)
        shutil.rmtree(os.path.join(prog_dir, "_neu"), ignore_errors=True)
    except OSError:
        pass
    return b_core, b_ver, "app", ""


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _run(core, bundled):
    os.environ["PA_RECHNUNG_RES"] = os.path.dirname(core)
    os.environ["PA_RECHNUNG_RES_FALLBACK"] = bundled
    os.environ["PA_RECHNUNG_PORT"] = str(_free_port())
    sys.argv = [core, "--server"]
    g = runpy.run_path(core, run_name="pa_rechnung_core")
    return g["server_start"]()


def start(bundled, prog_dir):
    """starts the program (database, modules, server on 127.0.0.1) -> (url, info)"""
    print(f"INIT PA Rechnung Starter v{STARTER_VERSION}")
    os.environ["PA_RECHNUNG_PROG_DIR"] = prog_dir
    core, ver, src, sha = choose(bundled, prog_dir)
    print(f"INIT Starter: Programm v{ver} ({'Update vom PC' if src == 'update' else 'aus der App'})")
    try:
        url = _run(core, bundled)
    except Exception:
        if src != "update":
            raise
        err = traceback.format_exc()
        print(err)
        mark_defekt(prog_dir, ver, sha, err)
        core, b_ver = core_in(bundled)
        url = _run(core, bundled)
        return url, {"version": b_ver, "quelle": "app", "hinweis": f"Programm-Update v{ver} startete nicht - es laeuft wieder v{b_ver}."}
    if src == "update":
        st = _rj(os.path.join(prog_dir, "start.json"), {}) or {}
        st["ok"] = True
        _wj(os.path.join(prog_dir, "start.json"), st)
    return url, {"version": ver, "quelle": src}
