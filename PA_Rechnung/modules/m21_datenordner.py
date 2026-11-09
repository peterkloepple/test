# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m21_datenordner (v2.0.0)
# Datenordner anzeigen und aendern (umziehen / kopieren / vorhandenen nutzen).
# Der Zeiger liegt im Benutzerprofil (AppData), siehe Kern pointer_path().
# Der Ordner "Programm" (installierte Updates) bleibt immer am Standardort,
# weil der Starter der EXE ihn dort sucht.
# Autor: T. Pfeiffer

DD_SKIP = {"Programm", "_update", "__pycache__"}
DD_FROZEN = [False]   # v2.0.6: True after the data folder was copied - no more writes until restart


def _dir_stats(path, skip=DD_SKIP):
    n, size = 0, 0
    if not os.path.isdir(path):
        return 0, 0
    for root, dirs, files in os.walk(path):
        if os.path.abspath(root) == os.path.abspath(path):
            dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            try:
                size += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return n, size


def _free_bytes(path):
    p = path
    while p and not os.path.exists(p):
        np_ = os.path.dirname(p)
        if np_ == p:
            break
        p = np_
    try:
        return shutil.disk_usage(p or path).free
    except Exception:
        return None


def datadir_info():
    n, size = _dir_stats(DATA_DIR)
    return {"ok": True, "path": DATA_DIR, "default": DEFAULT_DATA_DIR, "pointer": read_pointer(), "pointer_file": pointer_path(),
            "env": bool(os.environ.get("PA_RECHNUNG_DATA")), "files": n, "size_mb": round(size / 1048576, 1),
            "programm_dir": APP_DIR, "is_default": os.path.normcase(os.path.abspath(DATA_DIR)) == os.path.normcase(os.path.abspath(DEFAULT_DATA_DIR))}


def _norm_target(p):
    p = (p or "").strip().strip('"')
    if not p:
        raise ValueError("Bitte einen Ordner angeben.")
    p = os.path.abspath(os.path.expanduser(p))
    return p


def datadir_check(path):
    p = _norm_target(path)
    cur = os.path.normcase(os.path.abspath(DATA_DIR))
    pn = os.path.normcase(p)
    res = {"ok": True, "path": p, "warnungen": [], "fehler": ""}
    if pn == cur:
        res["fehler"] = "Das ist bereits der aktuelle Datenordner."
        return res
    if pn.startswith(cur + os.sep):
        res["fehler"] = "Der neue Ordner darf nicht innerhalb des aktuellen Datenordners liegen."
        return res
    if cur.startswith(pn + os.sep):
        res["fehler"] = "Der neue Ordner darf nicht oberhalb des aktuellen Datenordners liegen - bitte einen eigenen Unterordner waehlen."
        return res
    exists = os.path.isdir(p)
    has_db = exists and os.path.isfile(os.path.join(p, "daten.sqlite"))
    nonempty = exists and any(True for _ in os.scandir(p))
    res.update({"exists": exists, "has_data": has_db, "empty": exists and not nonempty})
    if p.startswith("\\\\") or (len(p) > 1 and p[1] == ":" and _is_network_drive(p[:2])):
        res["warnungen"].append("Netzlaufwerk/NAS: Die Datenbank sollte nur von EINEM PC gleichzeitig geoeffnet werden, "
                                "und bei Netzwerkaussetzern kann es haken. Besser: Datenordner lokal, Backup-Ziel auf dem NAS.")
    low = p.lower()
    if any(k in low for k in ("onedrive", "dropbox", "google drive", "icloud")):
        res["warnungen"].append("Cloud-Synchronisationsordner: Funktioniert, aber das Programm nur auf EINEM PC gleichzeitig nutzen, "
                                "sonst entstehen Konflikt-Kopien der Datenbank.")
    n, size = _dir_stats(DATA_DIR)
    free = _free_bytes(p)
    res.update({"need_mb": round(size / 1048576, 1), "free_mb": round(free / 1048576, 1) if free is not None else None})
    if free is not None and free < size * 1.1 + 50 * 1048576:
        res["warnungen"].append("Auf dem Ziel ist wenig Platz frei.")
    try:
        os.makedirs(p, exist_ok=True)
        t_ = os.path.join(p, ".pa_schreibtest")
        with open(t_, "w") as f:
            f.write("ok")
        os.remove(t_)
        if not exists:
            try:
                os.rmdir(p)
            except OSError:
                pass
    except Exception as e:
        res["fehler"] = f"In diesen Ordner kann nicht geschrieben werden: {e}"
    return res


def _is_network_drive(drive):
    if os.name != "nt":
        return False
    try:
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == 4   # DRIVE_REMOTE
    except Exception:
        return False


def write_pointer(path):
    pp = pointer_path()
    os.makedirs(os.path.dirname(pp), exist_ok=True)
    if path is None:
        try:
            os.remove(pp)
        except FileNotFoundError:
            pass
        return
    tmp = pp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"path": path, "gesetzt": now_iso(), "vorher": DATA_DIR}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, pp)


def _rewrite_paths(dbfile, old, new):
    """replace absolute paths that point into the old data folder (settings + text columns)"""
    # v2.0.6: only whole path prefixes (C:\\PA must not hit C:\\PA Archiv) - old + separator, or the exact value
    o1, n1 = old.rstrip("\\/"), new.rstrip("\\/")
    variants = [(o1 + "\\", n1 + "\\"), (o1.replace("\\", "\\\\") + "\\\\", n1.replace("\\", "\\\\") + "\\\\"),
                (o1.replace("\\", "/") + "/", n1.replace("\\", "/") + "/")]
    exact = [(o1, n1), ('"' + o1.replace("\\", "\\\\") + '"', '"' + n1.replace("\\", "\\\\") + '"')]
    c = sqlite3.connect(dbfile)
    try:
        tabs = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        n = 0
        for t in tabs:
            if t == "audit_log":
                continue   # v2.0.6: the GoBD log is append-only (hash chain) - never rewrite it
            cols = [r[1] for r in c.execute(f'PRAGMA table_info("{t}")') if (r[2] or "").upper() in ("TEXT", "")]
            for col in cols:
                for a, b in exact:
                    if a != b and a:
                        n += c.execute(f'UPDATE "{t}" SET "{col}"=? WHERE "{col}"=?', (b, a)).rowcount or 0
                for a, b in variants:
                    if a == b or not a:
                        continue
                    cur_ = c.execute(f'UPDATE "{t}" SET "{col}"=REPLACE("{col}", ?, ?) WHERE instr("{col}", ?) > 0', (a, b, a))
                    n += cur_.rowcount or 0
        c.commit()
        return n
    finally:
        c.close()


def datadir_change(d):
    mode = d.get("mode") or "move"          # move | copy | use | default
    if os.environ.get("PA_RECHNUNG_DATA"):
        raise ValueError("Der Datenordner ist ueber die Umgebungsvariable PA_RECHNUNG_DATA fest vorgegeben und kann hier nicht geaendert werden.")
    if mode == "default":
        target = DEFAULT_DATA_DIR
        if not os.path.isfile(os.path.join(target, "daten.sqlite")):
            raise ValueError("Am Standardort liegen keine Daten. Bitte stattdessen 'Umziehen' mit dem Standardordner waehlen.")
        write_pointer(None)
        return {"ok": True, "path": target, "restart": restart_app(1.5)}
    chk = datadir_check(d.get("path"))
    if chk["fehler"]:
        raise ValueError(chk["fehler"])
    target = chk["path"]
    if mode == "use":
        if not chk.get("has_data"):
            raise ValueError("Im gewaehlten Ordner liegen keine Programmdaten (daten.sqlite fehlt). Zum Umziehen bitte 'Umziehen' waehlen.")
        same_default = os.path.normcase(target) == os.path.normcase(os.path.abspath(DEFAULT_DATA_DIR))
        write_pointer(None if same_default else target)
        return {"ok": True, "path": target, "restart": restart_app(1.5)}
    if chk.get("has_data"):
        raise ValueError("Im Zielordner liegen bereits Programmdaten. Waehle 'Vorhandene Daten verwenden' oder einen leeren Ordner.")
    os.makedirs(target, exist_ok=True)
    # v2.0.6: files first, database LAST (and writes are frozen from then on until the restart) -
    # before, everything saved while the files were copied was lost after the move
    # 1) all other files (except Programm/_update and the db itself)
    n_src = 0
    errs = []
    for root, dirs, files in os.walk(DATA_DIR):
        if os.path.abspath(root) == os.path.abspath(DATA_DIR):
            dirs[:] = [x_ for x_ in dirs if x_ not in DD_SKIP]
        rel = os.path.relpath(root, DATA_DIR)
        dst_root = os.path.join(target, rel) if rel != "." else target
        os.makedirs(dst_root, exist_ok=True)
        for f in files:
            if rel == "." and (f.startswith("daten.sqlite") or f.endswith(".tmp")):
                continue
            n_src += 1
            try:
                shutil.copy2(os.path.join(root, f), os.path.join(dst_root, f))
            except Exception as e:
                errs.append(f"{os.path.join(rel, f)}: {e}")
    # 2) verify
    missing = []
    for root, dirs, files in os.walk(DATA_DIR):
        if os.path.abspath(root) == os.path.abspath(DATA_DIR):
            dirs[:] = [x_ for x_ in dirs if x_ not in DD_SKIP]
        rel = os.path.relpath(root, DATA_DIR)
        for f in files:
            if rel == "." and (f.startswith("daten.sqlite") or f.endswith(".tmp")):
                continue
            s_ = os.path.join(root, f)
            t_ = os.path.join(target, rel, f) if rel != "." else os.path.join(target, f)
            try:
                if not os.path.isfile(t_) or os.path.getsize(t_) != os.path.getsize(s_):
                    missing.append(os.path.join(rel, f))
            except OSError:
                missing.append(os.path.join(rel, f))
    if missing or errs:
        raise ValueError(f"Kopieren unvollstaendig ({len(missing)} Datei(en) fehlen/abweichend). Der alte Datenordner bleibt aktiv. "
                         + "; ".join((errs + missing)[:5]))
    # 3) database consistently via sqlite backup api, writes frozen until the restart
    with DB_LOCK:
        bk = sqlite3.connect(os.path.join(target, "daten.sqlite"))
        CON.backup(bk)
        bk.close()
        DD_FROZEN[0] = True
    try:
        nrw = _rewrite_paths(os.path.join(target, "daten.sqlite"), os.path.abspath(DATA_DIR), target)
        same_default = os.path.normcase(target) == os.path.normcase(os.path.abspath(DEFAULT_DATA_DIR))
        write_pointer(None if same_default else target)
    except Exception:
        DD_FROZEN[0] = False
        try:
            os.remove(os.path.join(target, "daten.sqlite"))
        except OSError:
            pass
        raise
    if mode == "move":
        _wj(os.path.join(target, "_umzug.json"), {"alt": os.path.abspath(DATA_DIR), "datum": now_iso(), "dateien": n_src})
    return {"ok": True, "path": target, "dateien": n_src + 1, "pfade_angepasst": nrw, "restart": restart_app(1.5)}


def _dd_old_ok(old):
    """the recorded old data folder may be tidied up only if it is a real, separate data folder of this program"""
    try:
        if not isinstance(old, str) or not old.strip() or not os.path.isabs(old):
            return False
        o = os.path.normcase(os.path.abspath(old)).rstrip("\\/")
        cur = os.path.normcase(os.path.abspath(DATA_DIR)).rstrip("\\/")
        if not o or o == cur or cur.startswith(o + os.sep) or o.startswith(cur + os.sep):
            return False   # same folder, parent or child of the current data folder
        if os.path.dirname(o) == o or re.fullmatch(r"[a-z]:", o) or o.startswith("\\\\") and o.count("\\") <= 3:
            return False   # drive root / UNC share root
        home = os.path.normcase(os.path.abspath(os.path.expanduser("~"))).rstrip("\\/")
        if o == home or home.startswith(o + os.sep):
            return False   # user profile or above
        if os.path.normcase(os.path.basename(o)) in ("documents", "dokumente", "desktop", "downloads"):
            return False
        return os.path.isfile(os.path.join(old, "daten.sqlite"))
    except Exception:
        return False


def datadir_cleanup_old():
    """after a 'move': put the old data into a subfolder _alter_Datenordner_<date> (nothing is deleted)"""
    mp = os.path.join(DATA_DIR, "_umzug.json")
    m = _rj(mp)
    if not m or not m.get("alt"):
        return
    old = m["alt"]
    if not _dd_old_ok(old):
        # defense in depth: only a folder that really was a data folder of this program is ever tidied up
        print(f"INIT Datenordner: alter Ordner {old!r} wird NICHT aufgeraeumt (keine gueltigen Programmdaten)")
        try:
            os.remove(mp)
        except OSError:
            pass
        return
    try:
        if os.path.isdir(old) and os.path.normcase(os.path.abspath(old)) != os.path.normcase(os.path.abspath(DATA_DIR)):
            arch = os.path.join(old, "_alter_Datenordner_" + time.strftime("%Y-%m-%d"))
            os.makedirs(arch, exist_ok=True)
            for e in os.listdir(old):
                if e in DD_SKIP or e.startswith("_alter_Datenordner_"):
                    continue
                try:
                    shutil.move(os.path.join(old, e), os.path.join(arch, e))
                except Exception:
                    traceback.print_exc()
            with open(os.path.join(arch, "LIESMICH.txt"), "w", encoding="utf-8") as f:
                f.write(f"Diese Daten wurden am {m.get('datum', '')[:10]} nach\r\n{DATA_DIR}\r\nverschoben. "
                        "Sie werden nicht mehr benutzt und koennen nach einer Kontrolle geloescht werden.\r\n")
        os.remove(mp)
    except Exception:
        traceback.print_exc()


def _dd_start():
    time.sleep(8)
    datadir_cleanup_old()


def _dd_selftest():
    errs = []
    if not os.path.isdir(DATA_DIR):
        errs.append("Datenordner fehlt")
    if not pointer_path().endswith("datenordner.json"):
        errs.append("Zeigerpfad falsch")
    return errs


HOOK_GET["/api/datadir"] = lambda h, qs: h._send(200, datadir_info())
HOOK_POST["/api/datadir/check"] = lambda h, d: h._send(200, datadir_check(d.get("path")))
HOOK_POST["/api/datadir/change"] = lambda h, d: h._send(200, datadir_change(d))
HOOK_START.append(_dd_start)
HOOK_SELFTEST.append(_dd_selftest)
