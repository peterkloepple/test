# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m47_vorlagen_aufraeumen  v1.0.0 (ab Programm v2.6.3)
# Vorlagen aufraeumen:
#   - unsichere Kategorien bestaetigen (alle oder markierte)
#   - doppelte Dateien loeschen: Inhalt wird vorher NEU verglichen (SHA-256), Original bleibt,
#     Briefe, die auf die Kopie zeigen, zeigen danach auf das Original
#   - markierte Vorlagen-Dateien loeschen
#   - fehlende aus dem Katalog entfernen, neue/geaenderte als gesehen markieren
#   - leere Dateien (0 Byte) und leere Ordner loeschen
#   - aehnliche Namen ("- Kopie", "(1)", "copy", "Kopie von") mit ANDEREM Inhalt zum Pruefen anzeigen
# Geloescht wird in den Windows-Papierkorb (lokale Laufwerke); bei Netzlaufwerken / ohne Papierkorb
# in den Ordner "_Papierkorb_Vorlagen" im Vorlagen-Ordner (wird beim Scan uebersprungen).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M47_VERSION = "1.0.0"
M47_TRASH = "_Papierkorb_Vorlagen"
M47_UNSICHER = 0.5

# scan skips the program's own trash folder in the template folder
VL_SKIP = re.compile(r"^(~\$|\.|thumbs\.db$|desktop\.ini$|" + re.escape(M47_TRASH.lower()) + r"$)", re.I)

_M47_COPY = [re.compile(p, re.I) for p in (r"^\s*kopie\s+von\s+", r"^\s*copy\s+of\s+",
                                          r"\s*[-_ ]\s*(kopie|copy|duplikat)(\s*\(\d+\))?\s*$", r"\s*\(\d+\)\s*$", r"\s*\[\d+\]\s*$")]


def _m47_norm(name):
    base = os.path.splitext(name)[0]
    prev = None
    while prev != base:
        prev = base
        for rx in _M47_COPY:
            base = rx.sub("", base)
    return re.sub(r"\s+", " ", base).strip().lower()


def _m47_root():
    root = vl_dir()
    if not root or not os.path.isdir(root):
        raise ValueError("Der Vorlagen-Ordner ist nicht erreichbar.")
    if VL_SCAN.get("laeuft"):
        raise ValueError("Der Ordner wird gerade gescannt - bitte kurz warten.")
    return os.path.abspath(root)


def _m47_path(root, rel):
    fp = os.path.abspath(os.path.join(root, rel))
    if os.path.commonpath([fp, root]) != root:
        raise ValueError("Pfad liegt nicht im Vorlagen-Ordner.")
    return fp


def _m47_is_local(fp):
    if not sys.platform.startswith("win"):
        return False
    if fp.startswith("\\\\"):
        return False
    try:
        import ctypes
        drv = os.path.splitdrive(fp)[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(drv) == 3     # DRIVE_FIXED
    except Exception:
        return False


def _m47_recycle(fp):
    """Windows recycle bin via SHFileOperationW (FOF_ALLOWUNDO) -> True when the file is gone"""
    try:
        import ctypes
        from ctypes import wintypes

        class SHFOS(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                        ("lpszProgressTitle", wintypes.LPCWSTR)]
        op = SHFOS(None, 3, fp + "\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return rc == 0 and not op.fAnyOperationsAborted and not os.path.exists(fp)
    except Exception:
        traceback.print_exc()
        return False


def m47_trash(root, fp, nur_ordner=False):
    """-> 'papierkorb' (Windows) or 'ordner' (_Papierkorb_Vorlagen in the template folder)"""
    if not nur_ordner and _m47_is_local(fp) and _m47_recycle(fp):
        return "papierkorb"
    rel = os.path.relpath(fp, root)
    dst = os.path.join(root, M47_TRASH, time.strftime("%Y-%m-%d"), rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    base, ext = os.path.splitext(dst)
    n = 1
    while os.path.exists(dst):
        dst = f"{base}_{n}{ext}"
        n += 1
    shutil.move(fp, dst)
    return "ordner"


def _m47_drop_row(row, ersatz=None):
    """remove a template row; letters pointing at it point at the replacement (or keep only the name)"""
    try:
        if ersatz:
            x("UPDATE briefe SET vorlage_id=? WHERE vorlage_id=?", (ersatz, row["id"]))
        else:
            x("UPDATE briefe SET vorlage_id=NULL WHERE vorlage_id=?", (row["id"],))
    except Exception:
        pass   # letters module not present
    x("DELETE FROM vorlagen WHERE id=?", (row["id"],))


def _m47_active():
    return q("SELECT * FROM vorlagen WHERE status<>'fehlt' AND dublette_von IS NULL")


def m47_info():
    root = vl_dir()
    rows = q("SELECT * FROM vorlagen")
    act = [r for r in rows if r["status"] != "fehlt" and not r["dublette_von"]]
    uns = [r for r in act if not r["manuell"] and (r["sicherheit"] or 0) < M47_UNSICHER]
    dup = [r for r in rows if r["dublette_von"] and r["status"] != "fehlt"]
    fehlt = [r for r in rows if r["status"] == "fehlt"]
    neu = [r for r in act if r["status"] in ("neu", "geaendert")]
    leer = [r for r in act if not (r["groesse"] or 0)]
    groups = {}
    for r in act:
        groups.setdefault((_m47_norm(r["name"]), (r["ext"] or "").lower()), []).append(r)
    aehnlich = []
    for (nm, ext), g in groups.items():
        if len(g) > 1 and len({r["hash"] for r in g}) > 1:
            aehnlich.append({"name": nm, "ext": ext, "dateien": [{"id": r["id"], "rel": r["rel"], "groesse": r["groesse"],
                                                                  "mtime": r["mtime"], "benutzt": r["benutzt"] or 0} for r in
                                                                 sorted(g, key=lambda r: -(r["mtime"] or 0))]})
    leer_ordner = []
    if root and os.path.isdir(root):
        for base, dirs, fns in os.walk(root, topdown=False):
            if os.path.abspath(base) == os.path.abspath(root) or M47_TRASH.lower() in base.lower().replace("\\", "/").split("/"):
                continue
            try:
                if not os.listdir(base):
                    leer_ordner.append(os.path.relpath(base, root).replace("\\", "/"))
            except OSError:
                pass
    dup_bytes = sum(r["groesse"] or 0 for r in dup)
    return {"ok": True, "ordner": root, "erreichbar": bool(root) and os.path.isdir(root),
            "unsicher": len(uns), "doppelt": len(dup), "doppelt_bytes": dup_bytes, "fehlt": len(fehlt), "neu": len(neu),
            "leer_dateien": len(leer), "leer_ordner": leer_ordner, "aehnlich": aehnlich[:200],
            "papierkorb": M47_TRASH, "scan_laeuft": bool(VL_SCAN.get("laeuft"))}


def m47_confirm(d):
    """unsure categories -> fixed as recognised (manuell=1); ids or all unsure"""
    if d.get("alle"):
        ids = [r["id"] for r in _m47_active() if not r["manuell"] and (r["sicherheit"] or 0) < M47_UNSICHER]
    else:
        ids = [int(i) for i in (d.get("ids") or [])]
    for i in ids:
        x("UPDATE vorlagen SET manuell=1, kategorie=COALESCE(NULLIF(kategorie,''), kategorie_auto, 'sonstiges') WHERE id=?", (i,))
    return {"ok": True, "bestaetigt": len(ids)}


def m47_delete_dups(d):
    root = _m47_root()
    if d.get("alle"):
        rows = q("SELECT * FROM vorlagen WHERE dublette_von IS NOT NULL AND status<>'fehlt'")
    else:
        ids = [int(i) for i in (d.get("ids") or [])]
        rows = [r for r in (q("SELECT * FROM vorlagen WHERE id=?", (i,), one=True) for i in ids) if r]
    res = {"ok": True, "geloescht": 0, "papierkorb": 0, "ordner": 0, "bytes": 0, "uebersprungen": 0, "fehler": []}
    for r in rows:
        try:
            if not r["dublette_von"]:
                raise ValueError("ist keine doppelte Datei")
            o = q("SELECT * FROM vorlagen WHERE id=?", (r["dublette_von"],), one=True)
            if not o or o["status"] == "fehlt":
                raise ValueError("Original fehlt - bitte neu scannen")
            fp, fo = _m47_path(root, r["rel"]), _m47_path(root, o["rel"])
            if os.path.normcase(fp) == os.path.normcase(fo):
                raise ValueError("gleiche Datei wie das Original")
            if not os.path.isfile(fo):
                raise ValueError("Original nicht mehr vorhanden - bitte neu scannen")
            if not os.path.isfile(fp):
                _m47_drop_row(r, o["id"])          # already gone: only clean the catalog
                res["geloescht"] += 1
                continue
            h1, h2 = _vl_hash(fp), _vl_hash(fo)
            if not h1 or h1 != h2:
                raise ValueError("Inhalt weicht inzwischen vom Original ab - nicht gelöscht, bitte neu scannen")
            # carry over the user's own category/note to the original
            if r["manuell"] and not o["manuell"]:
                x("UPDATE vorlagen SET kategorie=?, manuell=1 WHERE id=?", (r["kategorie"], o["id"]))
            if (r["notiz"] or "") and not (o["notiz"] or ""):
                x("UPDATE vorlagen SET notiz=? WHERE id=?", (r["notiz"], o["id"]))
            if r["benutzt"]:
                x("UPDATE vorlagen SET benutzt=COALESCE(benutzt,0)+? WHERE id=?", (r["benutzt"], o["id"]))
            where = m47_trash(root, fp)
            res[where] += 1
            res["bytes"] += r["groesse"] or 0
            _m47_drop_row(r, o["id"])
            res["geloescht"] += 1
        except Exception as e:
            res["uebersprungen"] += 1
            res["fehler"].append(f"{r['rel']}: {e}")
    vl_dedupe()
    return res


def m47_delete_files(d):
    """delete the selected template files (any, also originals) - duplicates of a deleted original become the new original"""
    root = _m47_root()
    ids = [int(i) for i in (d.get("ids") or [])]
    res = {"ok": True, "geloescht": 0, "papierkorb": 0, "ordner": 0, "bytes": 0, "uebersprungen": 0, "fehler": []}
    for i in ids:
        r = q("SELECT * FROM vorlagen WHERE id=?", (i,), one=True)
        if not r:
            continue
        try:
            fp = _m47_path(root, r["rel"])
            if os.path.isfile(fp):
                res[m47_trash(root, fp)] += 1
                res["bytes"] += r["groesse"] or 0
            kids = q("SELECT id FROM vorlagen WHERE dublette_von=?", (r["id"],))
            _m47_drop_row(r, kids[0]["id"] if kids else None)
            res["geloescht"] += 1
        except Exception as e:
            res["uebersprungen"] += 1
            res["fehler"].append(f"{r['rel']}: {e}")
    vl_dedupe()
    return res


def m47_delete_empty_dirs():
    root = _m47_root()
    n, err = 0, []
    for _ in range(5):                        # nested empty folders
        found = False
        for rel in m47_info()["leer_ordner"]:
            p = _m47_path(root, rel)
            try:
                os.rmdir(p)
                n += 1
                found = True
            except OSError as e:
                err.append(f"{rel}: {e.strerror or e}")
        if not found:
            break
    return {"ok": True, "ordner": n, "fehler": sorted(set(err))}


def m47_cleanup(d):
    """one-click cleanup with the chosen steps"""
    out = {"ok": True, "schritte": [], "fehler": []}
    if d.get("unsicher"):
        r = m47_confirm({"alle": True})
        out["schritte"].append(f"{r['bestaetigt']} unsichere Kategorie(n) bestätigt")
    if d.get("doppelt"):
        r = m47_delete_dups({"alle": True})
        wo = []
        if r["papierkorb"]:
            wo.append(f"{r['papierkorb']} in den Windows-Papierkorb")
        if r["ordner"]:
            wo.append(f"{r['ordner']} in „{M47_TRASH}“")
        out["schritte"].append(f"{r['geloescht']} doppelte Datei(en) gelöscht ({money_mb(r['bytes'])} frei)" + (f": {', '.join(wo)}" if wo else ""))
        out["fehler"] += r["fehler"]
    if d.get("leer_dateien"):
        ids = [r["id"] for r in _m47_active() if not (r["groesse"] or 0)]
        r = m47_delete_files({"ids": ids})
        out["schritte"].append(f"{r['geloescht']} leere Datei(en) gelöscht")
        out["fehler"] += r["fehler"]
    if d.get("fehlt"):
        r = vl_forget_missing()
        out["schritte"].append(f"{r['entfernt']} fehlende Vorlage(n) aus dem Katalog entfernt")
    if d.get("neu"):
        ids = [r["id"] for r in _m47_active() if r["status"] in ("neu", "geaendert")]
        if ids:
            vl_update({"ids": ids, "gesehen": True})
        out["schritte"].append(f"{len(ids)} neue/geänderte als gesehen markiert")
    if d.get("leer_ordner"):
        r = m47_delete_empty_dirs()
        out["schritte"].append(f"{r['ordner']} leere(r) Ordner gelöscht")
        out["fehler"] += r["fehler"]
    out["info"] = m47_info()
    return out


def money_mb(b):
    b = float(b or 0)
    return f"{b / 1048576:.1f} MB".replace(".", ",") if b >= 1048576 else f"{b / 1024:.0f} KB"


HOOK_GET["/api/vorlagen/aufraeumen"] = lambda h, qs: h._send(200, m47_info())
HOOK_POST["/api/vorlagen/aufraeumen"] = lambda h, d: h._send(200, m47_cleanup(d))
HOOK_POST["/api/vorlagen/bestaetigen"] = lambda h, d: h._send(200, m47_confirm(d))
HOOK_POST["/api/vorlagen/doppelte_loeschen"] = lambda h, d: h._send(200, m47_delete_dups(d))
HOOK_POST["/api/vorlagen/dateien_loeschen"] = lambda h, d: h._send(200, m47_delete_files(d))


def m47_selftest():
    err = []
    try:
        for a, b in (("Angebot - Kopie.docx", "angebot"), ("Angebot (1).docx", "angebot"), ("Kopie von Angebot.docx", "angebot"),
                     ("Angebot - Kopie (2).docx", "angebot"), ("Angebot_copy.docx", "angebot"), ("Angebot 2024.docx", "angebot 2024")):
            if _m47_norm(a) != b:
                err.append(f"m47: Name {a!r} -> {_m47_norm(a)!r} statt {b!r}")
        if not VL_SKIP.match(M47_TRASH):
            err.append("m47: Papierkorb-Ordner wird beim Scan nicht übersprungen")
        # real run in a temp folder: duplicate is deleted only with identical content, original stays
        import tempfile
        tmp = tempfile.mkdtemp(prefix="m47_")
        try:
            a, b2 = os.path.join(tmp, "a.txt"), os.path.join(tmp, "a - Kopie.txt")
            open(a, "w").write("x" * 10)
            open(b2, "w").write("x" * 10)
            if m47_trash(tmp, b2, nur_ordner=True) != "ordner" or os.path.exists(b2) or not os.path.exists(a) or \
                    not os.path.isfile(os.path.join(tmp, M47_TRASH, time.strftime("%Y-%m-%d"), "a - Kopie.txt")):
                err.append("m47: Löschen in den Papierkorb hat nicht funktioniert")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        err.append(f"m47 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m47_selftest)
print(f"INIT m47_vorlagen_aufraeumen v{M47_VERSION}")
