# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m23_backup_plus (v2.0.0)
# Verschluesseltes Backup mit Versionen (AES-256-ZIP, mit 7-Zip/WinZip lesbar),
# Aufbewahrung: taeglich / woechentlich / monatlich, mehrere Ziele (NAS, OneDrive),
# Wiederherstellen einer Version.
# Autor: T. Pfeiffer

BK_DEFAULTS = {"bk_encrypt": False, "bk_keep_daily": 14, "bk_keep_weekly": 8, "bk_keep_monthly": 24, "bk_full_weekly": True,
               "bk_targets": []}
BK_RE = re.compile(r"^backup_(auto_)?(\d{8})(?:_(\d{6}))?(_voll)?(_vor_wiederherstellung)?\.(zip)$")   # v2.0.6: safety copy visible


def bk_settings():
    s = get_settings()
    out = {k: s.get(k, v) for k, v in BK_DEFAULTS.items()}
    tg = [t for t in (out.get("bk_targets") or []) if isinstance(t, str) and t.strip()]
    old = (s.get("backup_target") or "").strip()
    if old and old not in tg:
        tg.insert(0, old)
    out["bk_targets"] = tg
    out["bk_has_pw"] = bool(s.get("bk_pw"))
    return out


def _bk_pw():
    v = get_settings().get("bk_pw")
    return unprotect_secret(v) if v else ""


def _encrypt_zip(src_zip, dst_zip, pw):
    import pyzipper
    with zipfile.ZipFile(src_zip) as zi, pyzipper.AESZipFile(dst_zip, "w", compression=pyzipper.ZIP_DEFLATED,
                                                               encryption=pyzipper.WZ_AES) as zo:
        zo.setpassword(pw.encode("utf-8"))
        zo.setencryption(pyzipper.WZ_AES, nbits=256)
        for info in zi.infolist():
            zo.writestr(info.filename, zi.read(info.filename))


def _retention(names, keep_d, keep_w, keep_m):
    """names: backup file names; returns set of names to keep (daily/weekly/monthly)"""
    dated = []
    for n in names:
        m = BK_RE.match(n)
        if m:
            try:
                dated.append((datetime.datetime.strptime(m.group(2), "%Y%m%d").date(), n))
            except ValueError:
                pass
    dated.sort(reverse=True)
    keep, days = set(), set()
    for d, n in dated:
        if len(days) < keep_d and d not in days:
            days.add(d)
            keep.add(n)
    # v2.1.0: per kept week / month the newest backup AND the newest full backup (with Belege, Projekte ...) of that
    # period stay - before, only the newest one stayed, mostly a database-only backup, so older full backups vanished
    for keyf, lim in ((lambda d_: d_.isocalendar()[:2], keep_w), (lambda d_: (d_.year, d_.month), keep_m)):
        order, per = [], {}
        for d, n in dated:
            k = keyf(d)
            if k not in per:
                per[k] = []
                order.append(k)
            per[k].append(n)
        for k in order[:lim]:
            keep.add(per[k][0])
            full = [n for n in per[k] if BK_RE.match(n).group(4)]
            if full:
                keep.add(full[0])
    return keep


BK_KEEP_MANUAL = 20


def _prune(folder):
    """retention applies to automatic backups only; manual backups: keep the newest BK_KEEP_MANUAL"""
    s = bk_settings()
    try:
        all_ = [n for n in os.listdir(folder) if BK_RE.match(n)]
    except OSError:
        return
    names = [n for n in all_ if n.startswith("backup_auto_")]
    manual = sorted((n for n in all_ if not n.startswith("backup_auto_") and "_vor_wiederherstellung" not in n), reverse=True)
    safety = sorted((n for n in all_ if "_vor_wiederherstellung" in n), reverse=True)
    keep = _retention(names, int(s["bk_keep_daily"] or 14), int(s["bk_keep_weekly"] or 8), int(s["bk_keep_monthly"] or 24))
    keep |= set(manual[:BK_KEEP_MANUAL]) | set(safety[:10])   # v2.0.6: own rule for safety copies
    for n in all_:
        if n not in keep:
            try:
                os.remove(os.path.join(folder, n))
            except OSError:
                pass


def copy_to_target(fn):
    """v2.0.0: several targets, optional AES encryption, versioned retention"""
    s = bk_settings()
    errs = []
    pw = _bk_pw() if s["bk_encrypt"] else ""
    if s["bk_encrypt"] and not pw:
        return "Backup-Verschluesselung ist an, aber es ist kein Passwort gesetzt."
    for tgt in s["bk_targets"]:
        try:
            os.makedirs(tgt, exist_ok=True)
            dst = os.path.join(tgt, os.path.basename(fn))
            if pw:
                _encrypt_zip(fn, dst + ".tmp", pw)
                os.replace(dst + ".tmp", dst)
            else:
                shutil.copy2(fn, dst)
            _prune(tgt)
        except Exception as e:
            traceback.print_exc()
            errs.append(f"{tgt}: {e}")
    if errs:
        return "Kopie ins Backup-Ziel fehlgeschlagen: " + "; ".join(errs)
    return None


@chain_step("make_backup", "m23_backup_plus")
def _m23_step_make_backup(_next, full=True):
    """v2.0.0: never overwrite an existing backup created in the same second"""
    while True:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if not os.path.exists(os.path.join(BACKUP_DIR, "backup_" + stamp + ".zip")):
            break
        time.sleep(0.3)
    return _next(full)


def auto_backup():
    """daily db backup, weekly full backup (with Belege/Assets), retention in BACKUP_DIR and targets"""
    try:
        s = bk_settings()
        tag = datetime.date.today().strftime("%Y%m%d")
        if any(f.startswith("backup_auto_" + tag) for f in os.listdir(BACKUP_DIR)):
            return
        # v2.1.0: weekly full backup on Sunday - or on the first start after 7 days without one
        # (before: only on Sundays, so a PC never used on Sundays never got a full backup automatically)
        seit = (datetime.date.today() - datetime.timedelta(days=6)).strftime("%Y%m%d")
        voll_neu = any((m_ := BK_RE.match(f)) and m_.group(1) and m_.group(4) and m_.group(2) >= seit for f in os.listdir(BACKUP_DIR))
        full = bool(s["bk_full_weekly"]) and (datetime.date.today().weekday() == 6 or not voll_neu)
        fn = make_backup(full=full)
        dst = os.path.join(BACKUP_DIR, "backup_auto_" + tag + ("_voll" if full else "") + ".zip")
        os.replace(fn, dst)
        set_setting("bk_last", {"zeit": now_iso(), "datei": os.path.basename(dst), "fehler": copy_to_target(dst) or ""})
        _prune(BACKUP_DIR)
    except Exception:
        traceback.print_exc()


def bk_list():
    out = []
    for folder, where in [(BACKUP_DIR, "Datenordner")] + [(t, t) for t in bk_settings()["bk_targets"]]:
        try:
            for n in os.listdir(folder):
                m = BK_RE.match(n)
                if not m:
                    continue
                p = os.path.join(folder, n)
                enc = False
                try:
                    with zipfile.ZipFile(p) as z:
                        enc = any(i.flag_bits & 0x1 for i in z.infolist())
                except Exception:
                    pass
                out.append({"name": n, "ort": where, "pfad": p, "datum": f"{m.group(2)[:4]}-{m.group(2)[4:6]}-{m.group(2)[6:]}",
                            "zeit": (m.group(3) or "")[:4], "voll": bool(m.group(4)) or not (m.group(1) or m.group(5)), "vor_wiederherstellung": bool(m.group(5)), "mb": round(os.path.getsize(p) / 1048576, 2),
                            "verschluesselt": enc})
        except OSError:
            continue
    out.sort(key=lambda r: (r["datum"], r["zeit"], r["name"]), reverse=True)
    return {"ok": True, "liste": out, "einstellungen": bk_settings(), "letztes": get_settings().get("bk_last")}


def bk_save(d):
    for k in ("bk_encrypt", "bk_full_weekly"):
        if k in d:
            set_setting(k, bool(d[k]))
    for k in ("bk_keep_daily", "bk_keep_weekly", "bk_keep_monthly"):
        if k in d:
            set_setting(k, max(1, min(400, int(d[k] or 1))))
    if "bk_targets" in d:
        tg = [str(t).strip() for t in (d["bk_targets"] or []) if str(t).strip()]
        set_setting("bk_targets", tg)
        set_setting("backup_target", tg[0] if tg else "")
    if d.get("bk_pw"):
        if len(d["bk_pw"]) < 8:
            raise ValueError("Das Backup-Passwort muss mindestens 8 Zeichen haben.")
        set_setting("bk_pw", protect_secret(d["bk_pw"]))
    if d.get("bk_pw_clear"):
        set_setting("bk_pw", "")
        set_setting("bk_encrypt", False)
    return {"ok": True, "einstellungen": bk_settings()}


def bk_restore(d):
    p = d.get("pfad") or ""
    known = {r["pfad"] for r in bk_list()["liste"]}
    if p not in known:
        raise ValueError("Backup nicht gefunden.")
    pw = (d.get("pw") or "").strip() or _bk_pw()
    tmpdb = os.path.join(BACKUP_DIR, "_restore.sqlite")
    try:
        import pyzipper
        Z = pyzipper.AESZipFile
    except Exception:
        Z = zipfile.ZipFile
    try:
        return _bk_restore_from(d, p, pw, tmpdb, Z)
    finally:
        # v2.1.0: never leave the extracted database behind (wrong password, damaged backup ...)
        try:
            if os.path.exists(tmpdb):
                os.remove(tmpdb)
        except OSError:
            pass


def _bk_restore_from(d, p, pw, tmpdb, Z):
    with Z(p) as z:
        if any(i.flag_bits & 0x1 for i in z.infolist()):
            if not pw:
                raise ValueError("Dieses Backup ist verschluesselt - bitte Passwort eingeben.")
            z.setpassword(pw.encode("utf-8"))
        try:
            data = z.read("daten.sqlite")
        except KeyError:
            raise ValueError("Im Backup ist keine Datenbank enthalten.")
        except RuntimeError:
            raise ValueError("Passwort falsch.")
        with open(tmpdb, "wb") as f:
            f.write(data)
        files = [i for i in z.infolist() if i.filename != "daten.sqlite" and not i.is_dir()]
        c = sqlite3.connect(tmpdb)
        try:
            ok = c.execute("PRAGMA integrity_check").fetchone()[0]
            n = c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        finally:
            c.close()
        if ok != "ok":
            raise ValueError("Die Datenbank im Backup ist beschaedigt.")
        safety = make_backup(full=False)
        os.replace(safety, os.path.join(BACKUP_DIR, "backup_" + time.strftime("%Y%m%d_%H%M%S") + "_vor_wiederherstellung.zip"))
        restored = 0
        if d.get("dateien") and files:
            for i in files:
                parts = [x_ for x_ in re.split(r"[\\/]", i.filename) if x_ not in ("", ".", "..")]
                if not parts or any(":" in x_ for x_ in parts):
                    continue   # no drive letters / streams ("C:" would leave the data folder on Windows)
                dst = os.path.abspath(os.path.join(DATA_DIR, *parts))
                root_ = os.path.abspath(DATA_DIR)
                try:
                    if os.path.normcase(os.path.commonpath([dst, root_])) != os.path.normcase(root_):
                        continue
                except ValueError:
                    continue
                if not os.path.exists(dst):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "wb") as f:
                        f.write(z.read(i.filename))
                    restored += 1
    with DB_LOCK:
        src = sqlite3.connect(tmpdb)
        src.backup(CON)
        src.close()
        try:
            DB_GEN[0] += 1   # v2.0.6: caches (m60) must not show the pre-restore numbers
        except NameError:
            pass
    return {"ok": True, "rechnungen": n, "dateien": restored, "restart": restart_app(1.5)}


def _bk_selftest():
    errs = []
    names = [f"backup_auto_{(datetime.date(2026, 1, 1) + datetime.timedelta(days=i)).strftime('%Y%m%d')}.zip" for i in range(400)]
    k = _retention(names, 14, 8, 24)
    if not (14 <= len(k) <= 14 + 8 + 24):
        errs.append(f"Aufbewahrung behaelt {len(k)} Versionen")
    if names[-1] not in k:
        errs.append("neuestes Backup wuerde geloescht")
    # full backup on a Monday must survive the weekly / monthly thinning-out
    nm2 = [f"backup_auto_{(datetime.date(2026, 1, 5) + datetime.timedelta(days=i)).strftime('%Y%m%d')}{'_voll' if i % 7 == 0 else ''}.zip"
           for i in range(120)]
    k2 = _retention(nm2, 14, 8, 24)
    if any(not any(n.startswith("backup_auto_" + mo) and "_voll" in n for n in k2) for mo in {n[12:18] for n in nm2}):
        errs.append("Aufbewahrung loescht aeltere Voll-Backups")
    return errs


HOOK_GET["/api/backup/list"] = lambda h, qs: h._send(200, bk_list())
HOOK_POST["/api/backup/settings"] = lambda h, d: h._send(200, bk_save(d))
HOOK_POST["/api/backup/restore"] = lambda h, d: h._send(200, bk_restore(d))
HOOK_POST["/api/backup/now"] = lambda h, d: h._send(200, (lambda fn: {"ok": True, "datei": os.path.basename(fn), "warn": copy_to_target(fn)})(make_backup(True)))
HOOK_SELFTEST.append(_bk_selftest)
