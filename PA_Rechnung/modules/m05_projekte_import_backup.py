# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m05_projekte_import_backup
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------------

def project_dir(p):
    d = p.get("dir") or ""
    if not d:
        # v2.6.3: max. 80 characters - project folder + sub folders + file name must stay below MAX_PATH
        d = os.path.join("Projekte", safe_name(f"{p['nr']} {p['name']}")[:80].rstrip(" .") or "Projekt")
    return d


def ensure_project_folders(p):
    base = os.path.join(DATA_DIR, project_dir(p))
    for f in json.loads(p.get("folders") or "[]"):
        os.makedirs(os.path.join(base, *f.split("/")), exist_ok=True)
    return base


def get_project(pid):
    p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not p:
        return None
    p["folders"] = json.loads(p["folders"] or "[]")
    p["files"] = q("SELECT * FROM project_files WHERE project_id=? ORDER BY folder, name", (pid,))
    p["entries"] = q("SELECT * FROM project_entries WHERE project_id=? ORDER BY datum, id", (pid,))
    p["invoices"] = q("SELECT id, nr, datum, summe, status, typ, storno_von, frist, mahnstufe, gueltig_bis, locked FROM invoices WHERE project_id=? ORDER BY datum", (pid,))
    p["belege"] = q("SELECT * FROM belege WHERE project_id=? ORDER BY datum", (pid,))
    p["customer"] = q("SELECT * FROM customers WHERE id=?", (p["customer_id"],), one=True) if p["customer_id"] else None
    p["abs_dir"] = os.path.join(DATA_DIR, project_dir(p))
    return p


def save_project(d):
    s = get_settings()
    pid = d.get("id")
    folders = d.get("folders")
    if folders is None and d.get("template_id"):
        t = q("SELECT * FROM templates WHERE id=?", (d["template_id"],), one=True)
        folders = json.loads(t["folders"]) if t else []
    folders = folders or ["01 Allgemein"]
    nr = (d.get("nr") or "").strip()
    if not nr:
        nr = s["next_projnr"]
        while q("SELECT id FROM projects WHERE nr=?", (nr,), one=True):
            nr = inc_number(nr)
        s["next_projnr"] = nr
    vals = (nr, d.get("name") or "Neues Projekt", d.get("customer_id") or None, d.get("bereich", "Sonstiges"),
            d.get("status", "aktiv"), d.get("start") or today(), d.get("ende") or "", d.get("descr", ""),
            json.dumps(folders, ensure_ascii=False), float(d.get("budget") or 0))
    if pid:
        x("UPDATE projects SET nr=?, name=?, customer_id=?, bereich=?, status=?, start=?, ende=?, descr=?, folders=?, budget=?, updated=? WHERE id=?",
          vals + (now_iso(), pid))
    else:
        pid = x("INSERT INTO projects (nr, name, customer_id, bereich, status, start, ende, descr, folders, budget, created, updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", vals + (now_iso(), now_iso()))
        p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        p["dir"] = project_dir(p)
        x("UPDATE projects SET dir=? WHERE id=?", (p["dir"], pid))
        if nr == s["next_projnr"]:
            set_setting("next_projnr", inc_number(nr))
    p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    ensure_project_folders(p)
    return pid


def add_project_file(pid, tmp_path, filename, folder=None):
    p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    folders = json.loads(p["folders"] or "[]")
    kind, auto_folder = detect_kind(filename, folders)
    # v2.1.0: sub folder comes from the UI (X-Folder) - never leave the project folder ("..", drive, absolute path)
    if folder:
        folder = "/".join(safe_name(p_) for p_ in re.split(r"[\\/]+", str(folder)) if p_.strip() not in ("", ".", "..")) or None
    folder = folder or auto_folder
    base = ensure_project_folders(p)
    dst_dir = os.path.join(base, *folder.split("/")) if folder else base
    os.makedirs(dst_dir, exist_ok=True)
    dst = fit_path(dst_dir, safe_name(filename), PATH_MAX_WIN - 5)     # v2.6.3: room for " (k)"
    root, ext = os.path.splitext(dst)
    k = 2
    while os.path.exists(dst):
        dst = f"{root} ({k}){ext}"
        k += 1
    shutil.move(tmp_path, dst)
    rel = os.path.relpath(dst, DATA_DIR)
    fid = x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
            (pid, folder, kind, os.path.basename(dst), rel, os.path.getsize(dst), "", now_iso()))
    return {"id": fid, "kind": kind, "folder": folder, "name": os.path.basename(dst)}


import collections as _m05_coll
THUMB_CACHE = _m05_coll.OrderedDict()     # v2.6.3: LRU, max. THUMB_MAX entries
THUMB_MAX = 500
THUMB_LOCK = threading.Lock()


def file_thumb(rel):
    with THUMB_LOCK:
        if rel in THUMB_CACHE:
            THUMB_CACHE.move_to_end(rel)
            return THUMB_CACHE[rel]
    fp = os.path.join(DATA_DIR, rel)
    ext = os.path.splitext(fp)[1].lower()
    data = None
    try:
        from PIL import Image
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"):
            im = Image.open(fp)
            im.thumbnail((360, 360))
            b = io.BytesIO()
            im.convert("RGB").save(b, "JPEG", quality=82)
            data = b.getvalue()
        elif ext == ".pdf" and pdfium:
            with PDFIUM_LOCK:     # v3.6.1: pdfium is not thread safe (thumbnails load in parallel)
                doc = pdfium.PdfDocument(fp, password=FILE_PW.get(os.path.abspath(fp)))
                try:
                    im = doc[0].render(scale=0.6).to_pil()
                finally:
                    doc.close()
            im.thumbnail((360, 360))
            b = io.BytesIO()
            im.convert("RGB").save(b, "JPEG", quality=82)
            data = b.getvalue()
    except Exception:
        data = None
    if data is None and ext not in IMAGE_EXT and os.path.exists(fp):
        try:
            t_, used_, fmt_ = extract_text_any(fp, fp, FILE_PW.get(os.path.abspath(fp)))
            if used_ and ext == ".pdf" and pdfium:
                FILE_PW[os.path.abspath(fp)] = used_
                with PDFIUM_LOCK:
                    doc = pdfium.PdfDocument(fp, password=used_)
                    try:
                        im = doc[0].render(scale=0.6).to_pil()
                    finally:
                        doc.close()
                im.thumbnail((360, 360))
                b = io.BytesIO()
                im.convert("RGB").save(b, "JPEG", quality=82)
                data = b.getvalue()
            else:
                data = text_preview_png(t_, fmt_)
        except PasswordNeeded:
            data = text_preview_png("", FORMAT_NAMES.get(ext, ext.upper()), locked=True)
        except Exception:
            try:
                data = text_preview_png("", FORMAT_NAMES.get(ext, ext.lstrip(".").upper() or "Datei"))
            except Exception:
                data = None
    if data is not None:      # v2.6.3: a failure (file still locked / being written) is retried next time
        with THUMB_LOCK:
            THUMB_CACHE[rel] = data
            THUMB_CACHE.move_to_end(rel)
            while len(THUMB_CACHE) > THUMB_MAX:
                THUMB_CACHE.popitem(last=False)
    return data

# ----------------------------------------------------------------------------
# Import from old program (rechnung10.vdt)
# ----------------------------------------------------------------------------

def import_vdt(path):
    d = open(path, "rb").read()
    recs = {}
    for i in range(256, len(d), 256):
        b = d[i:i + 256]
        if not any(b):
            continue
        idx, cnt, typ = b[1], b[2], b[3]
        rid = struct.unpack("<I", b[4:8])[0]
        if cnt == 0 or idx >= cnt:
            continue
        recs.setdefault((typ, rid), [None] * cnt)[idx] = b[8:]
    na = nc = 0
    for (typ, rid), parts in recs.items():
        data = b"".join(p for p in parts if p)
        try:
            if typ == 2:
                f = data.split(b"\x00")
                name, desc, nr = f[0], f[1], f[2]
                off = len(name) + len(desc) + len(nr) + 3 + 6
                price = struct.unpack("<i", data[off:off + 4])[0] / 1000.0
                nm = name.decode("cp1252", "replace").strip()
                nrs = nr.decode("cp1252", "replace").strip()
                if not nm or nm == "Offene Rechnung":
                    continue
                if q("SELECT id FROM articles WHERE nr=? AND name=?", (nrs, nm), one=True):
                    continue
                x("INSERT INTO articles (nr, name, descr, price, unit, cat, active) VALUES (?,?,?,?,?,?,1)",
                  (nrs, nm, desc.decode("cp1252", "replace").replace("\r\n", "\n").strip(), price, "Stk", "Import"))
                na += 1
            elif typ == 3:
                m = re.search(rb"[\x20-\xff]{3,}\x00", data[8:])
                f = [v.decode("cp1252", "replace").strip() for v in data[8 + m.start():].split(b"\x00")]
                if q("SELECT id FROM customers WHERE kdnr=?", (f[0],), one=True):
                    continue
                mo = re.match(r"(\d{4,5})\s+(.*)", f[4])
                plz, ort = (mo.group(1), mo.group(2)) if mo else ("", f[4])
                x("INSERT INTO customers (kdnr, anrede, firma, name, strasse, plz, ort, land, tel, mobil, mail, web, notiz, gruppe, created) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (f[0], "", f[1], f[2], f[3], plz, ort, "DE", f[5], f[9], f[10], f[11], "", "Import", now_iso()))
                nc += 1
        except Exception:
            continue
    return {"articles": na, "customers": nc}

# ----------------------------------------------------------------------------
# Backup
# ----------------------------------------------------------------------------

def make_backup(full=True):
    fn = os.path.join(BACKUP_DIR, "backup_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip")
    with DB_LOCK:
        tmpdb = os.path.join(BACKUP_DIR, "_tmp_" + uuid.uuid4().hex[:8] + ".sqlite")   # v2.0.6: unique (parallel backups)
        bk = sqlite3.connect(tmpdb)
        CON.backup(bk)
        bk.close()
    try:
        with zipfile.ZipFile(fn, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmpdb, "daten.sqlite")
            if full:
                # v2.0.6: really complete - all files in the data folder (Belege, Assets, Projekte, Rechnungen,
                # Briefe, Dokumente ...), except Backup, program versions and temp files
                skip_top = {"Backup", "Programm", "_update", "__pycache__", "_outlook_import", "_outlook_angehaengt"}
                for root, dirs, files in os.walk(DATA_DIR):
                    if os.path.abspath(root) == os.path.abspath(DATA_DIR):
                        dirs[:] = [d_ for d_ in dirs if d_ not in skip_top and not d_.startswith("_alter_Datenordner_")]
                        files = [f for f in files if not (f.startswith("daten.sqlite") or f.startswith("_tmp_") or f.endswith(".tmp"))]
                    # v2.6.3: never the persistent bank browser profile (bank cookies / session) in a backup
                    if os.path.normcase(os.path.abspath(root)) == os.path.normcase(os.path.join(os.path.abspath(DATA_DIR), "Bankzugang")):
                        dirs[:] = [d_ for d_ in dirs if d_ != "browser"]
                    for f in files:
                        p = os.path.join(root, f)
                        try:
                            z.write(p, os.path.relpath(p, DATA_DIR))
                        except (OSError, ValueError):
                            traceback.print_exc()
    except Exception:
        # v2.1.0: no half-written zip that looks like a valid backup (disk full ...)
        try:
            os.remove(fn)
        except OSError:
            pass
        raise
    finally:
        try:
            os.remove(tmpdb)
        except OSError:
            pass
    return fn


# copy_to_target(): definiert in m23_backup_plus (v2.1.0: alte, nie benutzte Fassung entfernt)


# auto_backup(): definiert in m23_backup_plus (v2.1.0: alte, nie benutzte Fassung entfernt)
