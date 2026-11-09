# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m28_unterricht_dateien (v2.0.7)
# Dateiablage im Unterricht: Dateien (Noten, Aufnahmen, Arbeitsblaetter, Fotos,
# Vertraege ...) je Kurs, je Schueler/in oder als allgemeines Material.
# Ablage im Datenordner unter "Unterricht" (Material / Kurse / Schueler),
# jede Datei optional mit Datum (Stunde) und Notiz. Dateien, die im Explorer
# in die Ordner gelegt werden, holt "Ordner abgleichen" ins Programm.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M28_VERSION = "1.0.0"
UNT_DIR = os.path.join(DATA_DIR, "Unterricht")
UNT_ZIELE = ("allg", "kurs", "schueler")
UNT_ARTEN = ["Noten & Arbeitsblätter", "Aufnahme (Audio)", "Video", "Foto", "Dokument", "Projekt-/Session-Datei", "Sonstiges"]
UNT_EXT = {
    "Aufnahme (Audio)": (".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg", ".wma", ".mid", ".midi"),
    "Video": (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".webm"),
    "Foto": (".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".bmp", ".tif", ".tiff"),
    "Projekt-/Session-Datei": (".als", ".alp", ".flp", ".logicx", ".ptx", ".cpr", ".npr", ".rpp", ".song", ".bwproject", ".tsi", ".nmsv", ".fxp"),
    "Noten & Arbeitsblätter": (".pdf", ".mscz", ".mscx", ".musicxml", ".mxl", ".sib", ".gp", ".gp5", ".gpx", ".tg"),
    "Dokument": (".docx", ".doc", ".odt", ".txt", ".rtf", ".xlsx", ".xls", ".ods", ".pptx", ".ppt", ".md", ".csv"),
}
UNT_SKIP = re.compile(r"^(~\$|\.|desktop\.ini$|thumbs\.db$)", re.I)


def m28_schema():
    x("CREATE TABLE IF NOT EXISTS unt_files (id INTEGER PRIMARY KEY, ziel TEXT, ziel_id INTEGER, name TEXT, path TEXT, size INTEGER, "
      "art TEXT, datum TEXT, notiz TEXT, added TEXT)")
    x("CREATE TABLE IF NOT EXISTS unt_dirs (ziel TEXT, ziel_id INTEGER, path TEXT, PRIMARY KEY (ziel, ziel_id))")
    x("CREATE INDEX IF NOT EXISTS ix_unt_files_ziel ON unt_files(ziel, ziel_id)")


HOOK_SCHEMA.append(m28_schema)


def unt_art(name):
    ext = os.path.splitext(name or "")[1].lower()
    for art, exts in UNT_EXT.items():
        if ext in exts:
            return art
    return "Sonstiges"


def _unt_check(ziel, zid):
    if ziel not in UNT_ZIELE:
        raise ValueError("Unbekanntes Ziel für die Datei.")
    zid = int(zid or 0)
    if ziel == "kurs" and not q("SELECT id FROM kurse WHERE id=?", (zid,), one=True):
        raise ValueError("Diesen Kurs gibt es nicht mehr.")
    if ziel == "schueler" and not q("SELECT id FROM students WHERE id=?", (zid,), one=True):
        raise ValueError("Diese/n Schüler/in gibt es nicht mehr.")
    return ziel, (0 if ziel == "allg" else zid)


def unt_target_name(ziel, zid):
    if ziel == "kurs":
        r = q("SELECT name FROM kurse WHERE id=?", (zid,), one=True)
        return r["name"] if r else f"Kurs {zid} (gelöscht)"
    if ziel == "schueler":
        r = q("SELECT name FROM students WHERE id=?", (zid,), one=True)
        return r["name"] if r else f"Schüler {zid} (gelöscht)"
    return "Allgemeines Material"


def unt_dir(ziel, zid, create=True):
    """folder of a target - fixed at first use, so renaming a course keeps its files together"""
    r = q("SELECT path FROM unt_dirs WHERE ziel=? AND ziel_id=?", (ziel, zid), one=True)
    if r and r["path"]:
        p = os.path.join(DATA_DIR, r["path"])
    else:
        sub = {"allg": ["Material"], "kurs": ["Kurse"], "schueler": ["Schueler"]}[ziel]
        if ziel != "allg":
            sub = sub + [safe_name(unt_target_name(ziel, zid))[:80]]
        p = os.path.join(UNT_DIR, *sub)
        base, k = p, 2
        while ziel != "allg" and os.path.exists(p) and q("SELECT 1 FROM unt_dirs WHERE path=?", (os.path.relpath(p, DATA_DIR),), one=True):
            p = f"{base} ({k})"
            k += 1
        if create:
            x("INSERT OR REPLACE INTO unt_dirs (ziel, ziel_id, path) VALUES (?,?,?)", (ziel, zid, os.path.relpath(p, DATA_DIR)))
    if create:
        os.makedirs(p, exist_ok=True)
    return p


def _unt_unique(dst):
    root, ext = os.path.splitext(dst)
    k = 2
    while os.path.exists(dst):
        dst = f"{root} ({k}){ext}"
        k += 1
    return dst


def unt_add_file(tmp, filename, ziel, zid, datum="", notiz=""):
    ziel, zid = _unt_check(ziel, zid)
    d = unt_dir(ziel, zid)
    dst = _unt_unique(os.path.join(d, safe_name(filename)))
    shutil.move(tmp, dst)
    name = os.path.basename(dst)
    fid = x("INSERT INTO unt_files (ziel, ziel_id, name, path, size, art, datum, notiz, added) VALUES (?,?,?,?,?,?,?,?,?)",
            (ziel, zid, name, os.path.relpath(dst, DATA_DIR), os.path.getsize(dst), unt_art(name),
             datum if re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum or "") else "", notiz or "", now_iso()))
    return {"ok": True, "id": fid, "name": name, "art": unt_art(name)}


def unt_list(ziel, zid):
    ziel, zid = (ziel, int(zid or 0)) if ziel in UNT_ZIELE else ("allg", 0)
    rows = q("SELECT * FROM unt_files WHERE ziel=? AND ziel_id=? ORDER BY COALESCE(NULLIF(datum,''), substr(added,1,10)) DESC, name", (ziel, zid))
    for r in rows:
        r["fehlt"] = not os.path.isfile(os.path.join(DATA_DIR, r["path"] or ""))
    r_ = q("SELECT path FROM unt_dirs WHERE ziel=? AND ziel_id=?", (ziel, zid), one=True)
    return {"ok": True, "ziel": ziel, "id": zid, "titel": unt_target_name(ziel, zid), "dateien": rows,
            "ordner": r_["path"] if r_ else "", "arten": UNT_ARTEN}


def unt_counts():
    out = {}
    for r in q("SELECT ziel, ziel_id, COUNT(*) n FROM unt_files GROUP BY ziel, ziel_id"):
        out[f"{r['ziel']}:{r['ziel_id']}"] = r["n"]
    return out


def unt_orphans():
    return q("SELECT f.ziel, f.ziel_id, COUNT(*) n FROM unt_files f WHERE (f.ziel='kurs' AND NOT EXISTS (SELECT 1 FROM kurse k WHERE k.id=f.ziel_id)) "
             "OR (f.ziel='schueler' AND NOT EXISTS (SELECT 1 FROM students s WHERE s.id=f.ziel_id)) GROUP BY f.ziel, f.ziel_id")


def unt_update(d):
    f = q("SELECT * FROM unt_files WHERE id=?", (int(d["id"]),), one=True)
    if not f:
        raise ValueError("Datei nicht gefunden.")
    path = f["path"]
    ziel, zid = f["ziel"], f["ziel_id"]
    if d.get("ziel") and (d["ziel"] != f["ziel"] or int(d.get("ziel_id") or 0) != int(f["ziel_id"] or 0)):
        ziel, zid = _unt_check(d["ziel"], d.get("ziel_id"))
        src = os.path.join(DATA_DIR, path)
        if os.path.isfile(src):
            dst = _unt_unique(os.path.join(unt_dir(ziel, zid), os.path.basename(src)))
            shutil.move(src, dst)
            path = os.path.relpath(dst, DATA_DIR)
    name = os.path.basename(path)
    if (d.get("name") or "").strip() and d["name"].strip() != f["name"]:
        new = safe_name(d["name"].strip())
        if not os.path.splitext(new)[1]:
            new += os.path.splitext(f["name"])[1]
        src = os.path.join(DATA_DIR, path)
        dst = _unt_unique(os.path.join(os.path.dirname(src), new))
        if os.path.isfile(src):
            os.replace(src, dst)
        path, name = os.path.relpath(dst, DATA_DIR), os.path.basename(dst)
    datum = d.get("datum", f["datum"]) or ""
    if datum and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
        datum = f["datum"] or ""
    x("UPDATE unt_files SET ziel=?, ziel_id=?, name=?, path=?, art=?, datum=?, notiz=? WHERE id=?",
      (ziel, zid, name, path, d.get("art") or f["art"], datum, d.get("notiz", f["notiz"]) or "", f["id"]))
    THUMB_CACHE.pop(f["path"], None)
    return {"ok": True}


def unt_delete(ids, datei=True):
    """remove entries; with datei=True the file goes to <Datenordner>/_Papierkorb (recoverable)"""
    n = 0
    for i in ids or []:
        f = q("SELECT * FROM unt_files WHERE id=?", (int(i),), one=True)
        if not f:
            continue
        x("DELETE FROM unt_files WHERE id=?", (f["id"],))
        if datei and not q("SELECT id FROM unt_files WHERE path=?", (f["path"],), one=True):
            try:
                trash_file(f["path"])
            except Exception:
                traceback.print_exc()
        n += 1
    return {"ok": True, "n": n}


def unt_sync(ziel, zid):
    """take over files that were put into the folder with the Explorer"""
    ziel, zid = _unt_check(ziel, zid)
    base = unt_dir(ziel, zid)
    known = {os.path.normcase(r["path"]) for r in q("SELECT path FROM unt_files")}
    n = 0
    for root, dirs, files in os.walk(base):
        dirs[:] = [d_ for d_ in dirs if not UNT_SKIP.match(d_)]
        for fn in files:
            if UNT_SKIP.match(fn):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, DATA_DIR)
            if os.path.normcase(rel) in known:
                continue
            x("INSERT INTO unt_files (ziel, ziel_id, name, path, size, art, datum, notiz, added) VALUES (?,?,?,?,?,?,?,?,?)",
              (ziel, zid, fn, rel, os.path.getsize(fp), unt_art(fn), "", "", now_iso()))
            n += 1
    # entries whose file is gone
    gone = [r["id"] for r in q("SELECT id, path FROM unt_files WHERE ziel=? AND ziel_id=?", (ziel, zid))
            if not os.path.isfile(os.path.join(DATA_DIR, r["path"] or ""))]
    return {"ok": True, "neu": n, "fehlen": len(gone)}


def unt_open(d):
    if d.get("id"):
        f = q("SELECT path FROM unt_files WHERE id=?", (int(d["id"]),), one=True)
        if not f:
            raise ValueError("Datei nicht gefunden.")
        fp = os.path.join(DATA_DIR, f["path"])
        if d.get("ordner"):
            return {"ok": open_path(os.path.dirname(fp))}
        if not os.path.isfile(fp):
            raise ValueError("Die Datei liegt nicht mehr im Ordner (verschoben oder gelöscht).")
        return {"ok": open_path(fp)}
    ziel, zid = _unt_check(d.get("ziel") or "allg", d.get("ziel_id"))
    return {"ok": open_path(unt_dir(ziel, zid)), "path": unt_dir(ziel, zid)}


def _unt_upload(h, tmp, name):
    try:
        r = unt_add_file(tmp, name, unquote(h.headers.get("X-Ziel") or "allg"), h.headers.get("X-Id") or 0,
                         unquote(h.headers.get("X-Datum") or ""), unquote(h.headers.get("X-Notiz") or ""))
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    return h._send(200, r)


def _unt_boot(d):
    d["unt_counts"] = unt_counts()


def _unt_selftest():
    errs = []
    try:
        if unt_art("Etude.pdf") != "Noten & Arbeitsblätter" or unt_art("take1.wav") != "Aufnahme (Audio)":
            errs.append("Unterricht-Dateien: Art-Erkennung falsch")
        q("SELECT COUNT(*) n FROM unt_files", one=True)
    except Exception as e:
        errs.append(f"Unterricht-Dateien: {e}")
    return errs


def unt_recent(n=8):
    """v2.0.8: newest files for the dashboard"""
    rows = q("SELECT * FROM unt_files ORDER BY added DESC, id DESC LIMIT ?", (max(1, min(int(n or 8), 50)),))
    for r in rows:
        r["ziel_name"] = unt_target_name(r["ziel"], r["ziel_id"])
    return {"ok": True, "dateien": rows}


HOOK_GET["/api/unt/recent"] = lambda h, qs: h._send(200, unt_recent(qs.get("n") or 8))
HOOK_UPLOAD["/api/upload/unt"] = _unt_upload
HOOK_GET["/api/unt/files"] = lambda h, qs: h._send(200, unt_list(qs.get("ziel") or "allg", qs.get("id") or 0))
HOOK_GET["/api/unt/overview"] = lambda h, qs: h._send(200, {"ok": True, "counts": unt_counts(), "orphans": unt_orphans(), "arten": UNT_ARTEN})
HOOK_POST["/api/unt/file/update"] = lambda h, d: h._send(200, unt_update(d))
HOOK_POST["/api/unt/file/delete"] = lambda h, d: h._send(200, unt_delete(d.get("ids") or ([d["id"]] if d.get("id") else []), d.get("datei", True)))
HOOK_POST["/api/unt/sync"] = lambda h, d: h._send(200, unt_sync(d.get("ziel") or "allg", d.get("ziel_id")))
HOOK_POST["/api/unt/open"] = lambda h, d: h._send(200, unt_open(d))
HOOK_BOOT.append(_unt_boot)
HOOK_SELFTEST.append(_unt_selftest)
