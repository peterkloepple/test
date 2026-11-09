# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m74_anlagenakte (v2.0.19)
# AV-Anlagenakte je Kunde: Standorte/Raeume, Geraete je Raum (Seriennr., Firmware, IP, MAC, VLAN,
# Garantie, Wartung), Dateien je Raum (Q-SYS-Design, SIMPL-Programm, Plaene, Fotos), Service-Einsaetze
# -> Servicerechnung als Entwurf. Erinnerungen: Garantie laeuft ab, Wartung faellig, Firmware-Stand alt.
# Geraeteliste Import/Export (Excel/CSV), PDF-Anlagenbericht je Raum oder Kunde (Uebergabedoku).
# Ablage der Dateien: Datenordner/Projekte/Anlagen/<Kunde>/<Raum>.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M74_VERSION = "1.0.0"
M74_KATEGORIEN = ["DSP / Core", "Mediensteuerung", "Display / Projektor", "Kamera", "Mikrofon", "Lautsprecher / Verstärker",
                  "Netzwerk", "Videotechnik / Matrix", "Konferenz / BYOD", "Sonstiges"]
M74_DATEI_ARTEN = [("Q-SYS-Design", (".qsys", ".qsysp", ".qplug", ".lua")),
                   ("Crestron-Programm", (".smw", ".lpz", ".cpz", ".usp", ".ush", ".umc", ".vtz", ".sgd", ".c3prj")),
                   ("Extron-Konfiguration", (".gcp", ".gc4", ".gcx", ".dsp", ".eaf")),
                   ("Plan / Zeichnung", (".dwg", ".dxf", ".idw", ".ipt", ".iam", ".vsd", ".vsdx")),
                   ("Foto", (".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".bmp")),
                   ("Dokument", (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".odt", ".csv")),
                   ("Archiv / Backup", (".zip", ".7z", ".rar"))]
M74_DEFAULTS = {"fw_monate": 12, "warn_tage": 30, "stundensatz": 0.0, "anfahrt": 0.0, "service_artikel": None}
M74_GERAET_COLS = ("raum_id", "kategorie", "hersteller", "modell", "seriennr", "firmware", "fw_geprueft", "ip", "mac", "vlan",
                   "standort", "einbau", "garantie_bis", "wartung_monate", "wartung_letzte", "lager_id", "notiz", "aktiv")
# "Typ" in German device lists is the model ("Hersteller; Typ; Seriennummer") - only explicit headers mean the category
M74_IMPORT_MAP = [("kategorie", r"kategorie|category|ger(ä|ae)te ?art|ger(ä|ae)te ?typ|^art$|gewerk"),
                  ("hersteller", r"hersteller|marke|manufacturer|brand|vendor"),
                  ("modell", r"modell|model|typ|type|produkt|bezeichnung|artikel"), ("seriennr", r"serien|serial|s/?n\b|sn$"),
                  ("firmware", r"firmware|fw|version|software"), ("ip", r"\bip\b|ip-?adresse|ip address|ipv4"),
                  ("mac", r"\bmac\b|mac-?adresse"), ("vlan", r"vlan"), ("standort", r"standort|position|ort im raum|location|platz"),
                  ("einbau", r"einbau|install|inbetrieb"), ("garantie_bis", r"garantie|warranty"),
                  ("wartung_monate", r"wartung.*(monat|interval)|interval"), ("notiz", r"notiz|bemerk|kommentar|note|comment")]


def _m74_schema():
    x("CREATE TABLE IF NOT EXISTS m74_raum (id INTEGER PRIMARY KEY, customer_id INTEGER, project_id INTEGER, gebaeude TEXT, "
      "raum TEXT, adresse TEXT, notiz TEXT, ordner TEXT, created TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m74_geraet (id INTEGER PRIMARY KEY, raum_id INTEGER, kategorie TEXT, hersteller TEXT, modell TEXT, "
      "seriennr TEXT, firmware TEXT, fw_geprueft TEXT, ip TEXT, mac TEXT, vlan TEXT, standort TEXT, einbau TEXT, garantie_bis TEXT, "
      "wartung_monate INTEGER DEFAULT 0, wartung_letzte TEXT, lager_id INTEGER, notiz TEXT, aktiv INTEGER DEFAULT 1, created TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m74_datei (id INTEGER PRIMARY KEY, raum_id INTEGER, name TEXT, path TEXT, art TEXT, size INTEGER, "
      "notiz TEXT, added TEXT)")
    x("CREATE TABLE IF NOT EXISTS m74_service (id INTEGER PRIMARY KEY, raum_id INTEGER, geraet_id INTEGER, datum TEXT, beschreibung TEXT, "
      "stunden REAL DEFAULT 0, material TEXT, invoice_id INTEGER, created TEXT)")
    for sql in ("CREATE INDEX IF NOT EXISTS m74_g_raum ON m74_geraet(raum_id)", "CREATE INDEX IF NOT EXISTS m74_d_raum ON m74_datei(raum_id)",
                "CREATE INDEX IF NOT EXISTS m74_s_raum ON m74_service(raum_id)", "CREATE INDEX IF NOT EXISTS m74_r_cust ON m74_raum(customer_id)"):
        try:
            x(sql)
        except Exception:
            pass


HOOK_SCHEMA.append(_m74_schema)


# ---------------------------------------------------------------------------- helpers
def m74_cfg():
    c = dict(M74_DEFAULTS)
    c.update(get_settings().get("m74_cfg") or {})
    return c


def _m74_d(v):
    try:
        return datetime.date.fromisoformat(str(v or "")[:10])
    except Exception:
        return None


def _m74_date_in(v):
    """ISO or German date -> ISO, '' if empty/invalid"""
    v = str(v or "").strip()
    if not v:
        return ""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return v[:10]
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})", v)
    if m:
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return datetime.date(y, int(m.group(2)), int(m.group(1))).isoformat()
        except Exception:
            return ""
    return ""


def _m74_cust_name(cid):
    c = q("SELECT * FROM customers WHERE id=?", (cid,), one=True) if cid else None
    return (c.get("firma") or c.get("name") or c.get("kdnr") or "") if c else ""


def m74_raum_titel(r):
    return " · ".join(v for v in ((r.get("gebaeude") or "").strip(), (r.get("raum") or "").strip()) if v) or f"Raum {r.get('id')}"


def m74_datei_art(name):
    ext = os.path.splitext(name or "")[1].lower()
    for art, exts in M74_DATEI_ARTEN:
        if ext in exts:
            return art
    return "Sonstiges"


def m74_raum_dir(rid, create=True):
    r = q("SELECT * FROM m74_raum WHERE id=?", (rid,), one=True)
    if not r:
        raise ValueError("Raum nicht gefunden.")
    if r.get("ordner"):
        p = os.path.join(DATA_DIR, r["ordner"])
    else:
        kunde = safe_name(_m74_cust_name(r["customer_id"]) or "ohne Kunde")
        p = os.path.join(PROJ_DIR, "Anlagen", kunde, safe_name(f"{m74_raum_titel(r)}_{r['id']}"))
        x("UPDATE m74_raum SET ordner=? WHERE id=?", (os.path.relpath(p, DATA_DIR), rid))
    if create:
        os.makedirs(p, exist_ok=True)
    return p


def _m74_geraet_status(g, cfg=None, t0=None):
    """list of {art, text, tage, faellig} reminders of one device"""
    cfg = cfg or m74_cfg()
    t0 = t0 or datetime.date.today()
    warn = int(cfg.get("warn_tage") or 30)
    out = []
    if not g.get("aktiv", 1):
        return out
    gb = _m74_d(g.get("garantie_bis"))
    if gb:
        dd = (gb - t0).days
        if -60 <= dd <= warn:
            out.append({"art": "garantie", "faellig": gb.isoformat(), "tage": dd,
                        "text": ("Garantie abgelaufen seit " + de_date(gb.isoformat())) if dd < 0 else ("Garantie endet am " + de_date(gb.isoformat()))})
    wm = int(g.get("wartung_monate") or 0)
    if wm > 0:
        base = _m74_d(g.get("wartung_letzte")) or _m74_d(g.get("einbau"))
        if base:
            due = add_months(base, wm)
            dd = (due - t0).days
            if dd <= warn:
                out.append({"art": "wartung", "faellig": due.isoformat(), "tage": dd,
                            "text": ("Wartung überfällig seit " + de_date(due.isoformat())) if dd < 0 else ("Wartung fällig am " + de_date(due.isoformat()))})
    fm = int(cfg.get("fw_monate") or 0)
    if fm > 0 and (g.get("firmware") or g.get("fw_geprueft") or g.get("einbau")):
        base = _m74_d(g.get("fw_geprueft")) or _m74_d(g.get("einbau"))
        if base:
            due = add_months(base, fm)
            if due <= t0:
                out.append({"art": "firmware", "faellig": due.isoformat(), "tage": (due - t0).days,
                            "text": "Firmware-Stand zuletzt geprüft " + de_date(base.isoformat()) + (f" ({g['firmware']})" if g.get("firmware") else "")})
    return out


def m74_hinweise():
    cfg = m74_cfg()
    t0 = datetime.date.today()
    rows = q("SELECT g.*, r.gebaeude, r.raum, r.customer_id FROM m74_geraet g JOIN m74_raum r ON r.id=g.raum_id WHERE g.aktiv=1")
    out = []
    for g in rows:
        for h in _m74_geraet_status(g, cfg, t0):
            h.update({"geraet_id": g["id"], "raum_id": g["raum_id"], "geraet": " ".join(v for v in (g["hersteller"] or "", g["modell"] or "") if v) or g["kategorie"] or "Gerät",
                      "seriennr": g["seriennr"] or "", "raum": m74_raum_titel(g), "kunde": _m74_cust_name(g["customer_id"])})
            out.append(h)
    return sorted(out, key=lambda h: h["tage"])


# ---------------------------------------------------------------------------- rooms
def m74_raeume(customer_id=None, project_id=None):
    sql = ("SELECT r.*, (SELECT COUNT(*) FROM m74_geraet g WHERE g.raum_id=r.id AND g.aktiv=1) n_geraete, "
           "(SELECT COUNT(*) FROM m74_datei d WHERE d.raum_id=r.id) n_dateien, "
           "(SELECT COUNT(*) FROM m74_service s WHERE s.raum_id=r.id) n_service, "
           "(SELECT COUNT(*) FROM m74_service s WHERE s.raum_id=r.id AND s.invoice_id IS NULL) n_service_offen, "
           "(SELECT MAX(datum) FROM m74_service s WHERE s.raum_id=r.id) letzter_service FROM m74_raum r")
    args, wh = [], []
    if customer_id:
        wh.append("r.customer_id=?")
        args.append(int(customer_id))
    if project_id:
        wh.append("r.project_id=?")
        args.append(int(project_id))
    if wh:
        sql += " WHERE " + " AND ".join(wh)
    rows = q(sql, tuple(args))
    cn = {c["id"]: (c["firma"] or c["name"] or c["kdnr"] or "") for c in q("SELECT id, firma, name, kdnr FROM customers")}
    pn = {p["id"]: f"{p['nr']} {p['name']}" for p in q("SELECT id, nr, name FROM projects")}
    hin = {}
    for h in m74_hinweise():
        hin[h["raum_id"]] = hin.get(h["raum_id"], 0) + 1
    for r in rows:
        r["titel"] = m74_raum_titel(r)
        r["kunde"] = cn.get(r["customer_id"], "")
        r["projekt"] = pn.get(r["project_id"], "")
        r["n_hinweise"] = hin.get(r["id"], 0)
    return sorted(rows, key=lambda r: ((r["kunde"] or "~").lower(), (r["gebaeude"] or "").lower(), (r["raum"] or "").lower()))


def m74_raum_save(d):
    rid = d.get("id")
    cols = ("customer_id", "project_id", "gebaeude", "raum", "adresse", "notiz")
    vals = [int(d["customer_id"]) if str(d.get("customer_id") or "").isdigit() else None,
            int(d["project_id"]) if str(d.get("project_id") or "").isdigit() else None,
            (d.get("gebaeude") or "").strip()[:120], (d.get("raum") or "").strip()[:120], (d.get("adresse") or "").strip()[:300],
            (d.get("notiz") or "")[:4000]]
    if not vals[2] and not vals[3]:
        raise ValueError("Bitte Gebäude oder Raum angeben.")
    if vals[1] and not vals[0]:
        p = q("SELECT customer_id FROM projects WHERE id=?", (vals[1],), one=True)
        if p and p["customer_id"]:
            vals[0] = p["customer_id"]
    if rid:
        x(f"UPDATE m74_raum SET {', '.join(c + '=?' for c in cols)}, updated=? WHERE id=?", tuple(vals) + (now_iso(), int(rid)))
        return int(rid)
    return x(f"INSERT INTO m74_raum ({', '.join(cols)}, created, updated) VALUES ({','.join('?' * len(cols))},?,?)",
             tuple(vals) + (now_iso(), now_iso()))


def m74_raum_delete(rid, dateien=True):
    rid = int(rid)
    r = q("SELECT * FROM m74_raum WHERE id=?", (rid,), one=True)
    if not r:
        return {"ok": True}
    if dateien and r.get("ordner"):
        p = os.path.join(DATA_DIR, r["ordner"])
        if os.path.isdir(p):
            trash = os.path.join(DATA_DIR, "Papierkorb", "Anlagen")
            os.makedirs(trash, exist_ok=True)
            try:
                shutil.move(p, os.path.join(trash, os.path.basename(p) + "_" + time.strftime("%Y%m%d%H%M%S")))
            except Exception:
                pass
    if dateien and r.get("ordner"):
        # reports filed in the project point into the moved folder -> remove these links too
        pre = r["ordner"].rstrip("\\/")
        for pf in q("SELECT id, path FROM project_files WHERE path LIKE ?", (pre + "%",)):
            if (pf["path"] or "")[len(pre):len(pre) + 1] in ("/", "\\"):
                x("DELETE FROM project_files WHERE id=?", (pf["id"],))
    x("DELETE FROM m74_geraet WHERE raum_id=?", (rid,))
    x("DELETE FROM m74_datei WHERE raum_id=?", (rid,))
    x("DELETE FROM m74_service WHERE raum_id=?", (rid,))
    x("DELETE FROM m74_raum WHERE id=?", (rid,))
    return {"ok": True}


def m74_raum_detail(rid):
    rid = int(rid)
    r = q("SELECT * FROM m74_raum WHERE id=?", (rid,), one=True)
    if not r:
        raise ValueError("Raum nicht gefunden.")
    cfg = m74_cfg()
    r["titel"] = m74_raum_titel(r)
    r["kunde"] = _m74_cust_name(r["customer_id"])
    pr = q("SELECT nr, name FROM projects WHERE id=?", (r["project_id"],), one=True) if r["project_id"] else None
    r["projekt"] = f"{pr['nr']} {pr['name']}" if pr else ""
    ger = q("SELECT g.*, a.nr lager_nr, a.name lager_name FROM m74_geraet g LEFT JOIN m42_artikel a ON a.id=g.lager_id "
            "WHERE g.raum_id=? ORDER BY g.aktiv DESC, g.kategorie, g.hersteller, g.modell", (rid,)) if _m74_has_lager() else \
        q("SELECT * FROM m74_geraet WHERE raum_id=? ORDER BY aktiv DESC, kategorie, hersteller, modell", (rid,))
    for g in ger:
        g["hinweise"] = _m74_geraet_status(g, cfg)
    dat = q("SELECT * FROM m74_datei WHERE raum_id=? ORDER BY art, name", (rid,))
    for f in dat:
        f["fehlt"] = not os.path.isfile(os.path.join(DATA_DIR, f["path"] or ""))
    srv = q("SELECT s.*, i.nr inv_nr, i.status inv_status FROM m74_service s LEFT JOIN invoices i ON i.id=s.invoice_id "
            "WHERE s.raum_id=? ORDER BY s.datum DESC, s.id DESC", (rid,))
    gmap = {g["id"]: g for g in ger}
    for s_ in srv:
        try:
            s_["material"] = json.loads(s_["material"] or "[]")
        except Exception:
            s_["material"] = []
        g = gmap.get(s_["geraet_id"])
        s_["geraet"] = (" ".join(v for v in (g["hersteller"] or "", g["modell"] or "") if v) or g["kategorie"]) if g else ""
    return {"ok": True, "raum": r, "geraete": ger, "dateien": dat, "service": srv, "cfg": cfg,
            "kategorien": M74_KATEGORIEN, "ordner": r.get("ordner") or ""}


def _m74_has_lager():
    try:
        q("SELECT id FROM m42_artikel LIMIT 1")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------- devices
def m74_geraet_save(d):
    gid = d.get("id")
    rid = int(d.get("raum_id") or 0)
    if not q("SELECT id FROM m74_raum WHERE id=?", (rid,), one=True):
        raise ValueError("Bitte zuerst einen Raum wählen.")
    vals = []
    for c in M74_GERAET_COLS:
        v = d.get(c)
        if c == "raum_id":
            v = rid
        elif c in ("fw_geprueft", "einbau", "garantie_bis", "wartung_letzte"):
            v = _m74_date_in(v)
        elif c == "wartung_monate":
            try:
                v = max(0, int(float(str(v or 0).replace(",", "."))))
            except Exception:
                v = 0
        elif c == "lager_id":
            v = int(v) if str(v or "").isdigit() else None
        elif c == "aktiv":
            v = 0 if str(v) in ("0", "False", "false") else 1
        elif c == "mac":
            v = (v or "").strip().upper().replace("-", ":")
        else:
            v = (str(v) if v is not None else "").strip()[:2000 if c == "notiz" else 200]
        vals.append(v)
    if not any(vals[i] for i in (2, 3, 4)):   # hersteller, modell, seriennr
        if not vals[1]:
            raise ValueError("Bitte mindestens Hersteller, Modell oder Seriennummer angeben.")
    if gid:
        old = q("SELECT firmware, fw_geprueft FROM m74_geraet WHERE id=?", (int(gid),), one=True)
        # new firmware entered -> counts as checked today
        if old and (old["firmware"] or "") != vals[5] and vals[5] and vals[6] == (old["fw_geprueft"] or ""):
            vals[6] = today()
        x(f"UPDATE m74_geraet SET {', '.join(c + '=?' for c in M74_GERAET_COLS)}, updated=? WHERE id=?", tuple(vals) + (now_iso(), int(gid)))
        return int(gid)
    if vals[5] and not vals[6]:
        vals[6] = today()
    return x(f"INSERT INTO m74_geraet ({', '.join(M74_GERAET_COLS)}, created, updated) VALUES ({','.join('?' * len(M74_GERAET_COLS))},?,?)",
             tuple(vals) + (now_iso(), now_iso()))


def m74_geraete_bulk(ids, action, value=None):
    ids = [int(i) for i in ids or [] if str(i).isdigit()]
    if not ids:
        return {"ok": True, "done": 0}
    ph = ",".join("?" * len(ids))
    if action == "delete":
        x(f"DELETE FROM m74_geraet WHERE id IN ({ph})", ids)
    elif action == "fw_ok":
        x(f"UPDATE m74_geraet SET fw_geprueft=?, updated=? WHERE id IN ({ph})", [today(), now_iso()] + ids)
    elif action == "wartung_ok":
        x(f"UPDATE m74_geraet SET wartung_letzte=?, updated=? WHERE id IN ({ph})", [_m74_date_in(value) or today(), now_iso()] + ids)
    elif action == "move":
        if not q("SELECT id FROM m74_raum WHERE id=?", (int(value or 0),), one=True):
            raise ValueError("Ziel-Raum nicht gefunden.")
        x(f"UPDATE m74_geraet SET raum_id=?, updated=? WHERE id IN ({ph})", [int(value), now_iso()] + ids)
    elif action == "aktiv":
        x(f"UPDATE m74_geraet SET aktiv=?, updated=? WHERE id IN ({ph})", [1 if value else 0, now_iso()] + ids)
    elif action == "copy":
        tgt = int(value or 0)
        if not q("SELECT id FROM m74_raum WHERE id=?", (tgt,), one=True):
            raise ValueError("Ziel-Raum nicht gefunden.")
        for g in q(f"SELECT * FROM m74_geraet WHERE id IN ({ph})", ids):
            g = dict(g, raum_id=tgt, seriennr="", mac="", ip="")
            g.pop("id", None)
            m74_geraet_save(g)
    else:
        raise ValueError("Unbekannte Aktion.")
    return {"ok": True, "done": len(ids)}


def m74_suche(qtext):
    t = (qtext or "").strip().lower()
    if len(t) < 2:
        return {"ok": True, "treffer": []}
    like = "%" + t.replace("%", "") + "%"
    rows = q("SELECT g.*, r.gebaeude, r.raum, r.customer_id FROM m74_geraet g JOIN m74_raum r ON r.id=g.raum_id WHERE "
             "lower(COALESCE(g.hersteller,'')||' '||COALESCE(g.modell,'')||' '||COALESCE(g.seriennr,'')||' '||COALESCE(g.firmware,'')||' '||"
             "COALESCE(g.ip,'')||' '||COALESCE(g.mac,'')||' '||COALESCE(g.vlan,'')||' '||COALESCE(g.standort,'')||' '||COALESCE(g.notiz,'')||' '||"
             "COALESCE(g.kategorie,'')||' '||COALESCE(r.gebaeude,'')||' '||COALESCE(r.raum,'')) LIKE ? "
             "ORDER BY g.hersteller, g.modell LIMIT 300", (like,))
    # MAC also without separators
    t2 = re.sub(r"[^0-9a-f]", "", t)
    if len(t2) >= 4:
        seen = {r["id"] for r in rows}
        for g in q("SELECT g.*, r.gebaeude, r.raum, r.customer_id FROM m74_geraet g JOIN m74_raum r ON r.id=g.raum_id WHERE g.mac<>''"):
            if g["id"] not in seen and t2 in re.sub(r"[^0-9a-f]", "", (g["mac"] or "").lower()):
                rows.append(g)
    for g in rows:
        g["raum_titel"] = m74_raum_titel(g)
        g["kunde"] = _m74_cust_name(g["customer_id"])
    return {"ok": True, "treffer": rows}


# ---------------------------------------------------------------------------- files
def m74_datei_add(tmp, name, rid, notiz=""):
    rid = int(rid or 0)
    try:
        base = m74_raum_dir(rid)
        nm = safe_name(name) or "datei"
        dst = os.path.join(base, nm)
        stem, ext = os.path.splitext(nm)
        k = 2
        while os.path.exists(dst):
            dst = os.path.join(base, f"{stem}_{k}{ext}")
            k += 1
        shutil.move(tmp, dst)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    rel = os.path.relpath(dst, DATA_DIR)
    fid = x("INSERT INTO m74_datei (raum_id, name, path, art, size, notiz, added) VALUES (?,?,?,?,?,?,?)",
            (rid, os.path.basename(dst), rel, m74_datei_art(dst), os.path.getsize(dst), (notiz or "")[:300], now_iso()))
    warn = ""
    if re.search(r"passw|kennw|password|credential|zugang", name or "", re.I):
        warn = ("Hinweis: Diese Datei sieht nach einer Passwortliste aus. Passwörter nicht im Klartext ablegen - "
                "besser in einem Passwort-Manager oder als verschlüsseltes ZIP/7z speichern.")
    return {"ok": True, "id": fid, "name": os.path.basename(dst), "warn": warn}


def m74_dateien_sync(rid):
    """take over files that were copied into the room folder with the Explorer"""
    base = m74_raum_dir(int(rid))
    have = {r["path"] for r in q("SELECT path FROM m74_datei WHERE raum_id=?", (int(rid),))}
    n = 0
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if fn.startswith((".", "~$")) or fn.lower().startswith("anlagenbericht_"):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, DATA_DIR)
            if rel in have:
                continue
            x("INSERT INTO m74_datei (raum_id, name, path, art, size, notiz, added) VALUES (?,?,?,?,?,?,?)",
              (int(rid), fn, rel, m74_datei_art(fn), os.path.getsize(fp), "", now_iso()))
            n += 1
    # forget entries whose file was removed in the Explorer
    gone = 0
    for r in q("SELECT id, path FROM m74_datei WHERE raum_id=?", (int(rid),)):
        if not os.path.isfile(os.path.join(DATA_DIR, r["path"] or "")):
            x("DELETE FROM m74_datei WHERE id=?", (r["id"],))
            gone += 1
    return {"ok": True, "neu": n, "entfernt": gone}


def m74_dateien_delete(ids):
    ids = [int(i) for i in ids or [] if str(i).isdigit()]
    trash = os.path.join(DATA_DIR, "Papierkorb", "Anlagen")
    for r in q(f"SELECT * FROM m74_datei WHERE id IN ({','.join('?' * len(ids)) or 'NULL'})", ids):
        fp = os.path.join(DATA_DIR, r["path"] or "")
        if os.path.isfile(fp):
            os.makedirs(trash, exist_ok=True)
            try:
                shutil.move(fp, os.path.join(trash, time.strftime("%Y%m%d%H%M%S_") + os.path.basename(fp)))
            except Exception:
                pass
        x("DELETE FROM m74_datei WHERE id=?", (r["id"],))
    return {"ok": True, "done": len(ids)}


# ---------------------------------------------------------------------------- service
def _m74_num(v, default, name):
    """number from the form: 12 / 12,5 / 1.234,50 / 1234.5 -> float; empty -> default; garbage -> clear message"""
    if v in (None, ""):
        return default
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(parse_amount(str(v).strip()))
    except Exception:
        raise ValueError(f"{name}: „{v}“ ist keine Zahl.")


def m74_service_save(d):
    sid = d.get("id")
    rid = int(d.get("raum_id") or 0)
    if not q("SELECT id FROM m74_raum WHERE id=?", (rid,), one=True):
        raise ValueError("Raum nicht gefunden.")
    mat = []
    for m_ in d.get("material") or []:
        name = (m_.get("name") or "").strip()
        if not name:
            continue
        # v2.1.0: German amounts with thousands separator ("1.234,50") gave price 0 without a message
        qty = _m74_num(m_.get("qty"), 1.0, "Menge")
        price = _m74_num(m_.get("price"), 0.0, "Preis")
        mat.append({"name": name[:200], "qty": qty, "price": price, "nr": (m_.get("nr") or "")[:40], "lager_id": m_.get("lager_id")})
    std = _m74_num(d.get("stunden"), 0.0, "Stunden")
    vals = (rid, int(d["geraet_id"]) if str(d.get("geraet_id") or "").isdigit() else None, _m74_date_in(d.get("datum")) or today(),
            (d.get("beschreibung") or "").strip()[:4000], std, json.dumps(mat, ensure_ascii=False))
    if sid:
        cur_ = q("SELECT invoice_id FROM m74_service WHERE id=?", (int(sid),), one=True)
        if cur_ and cur_["invoice_id"] and q("SELECT id FROM invoices WHERE id=?", (cur_["invoice_id"],), one=True):
            st = q("SELECT status FROM invoices WHERE id=?", (cur_["invoice_id"],), one=True)["status"]
            if st != "entwurf":
                raise ValueError("Dieser Einsatz ist schon abgerechnet - bitte die Rechnung ändern.")
        x("UPDATE m74_service SET raum_id=?, geraet_id=?, datum=?, beschreibung=?, stunden=?, material=? WHERE id=?", vals + (int(sid),))
        out = int(sid)
    else:
        out = x("INSERT INTO m74_service (raum_id, geraet_id, datum, beschreibung, stunden, material, created) VALUES (?,?,?,?,?,?,?)",
                vals + (now_iso(),))
    if d.get("wartung_erledigt") and vals[1]:
        x("UPDATE m74_geraet SET wartung_letzte=? WHERE id=?", (vals[2], vals[1]))
    return out


def m74_service_delete(ids):
    ids = [int(i) for i in ids or [] if str(i).isdigit()]
    if ids:
        x(f"DELETE FROM m74_service WHERE id IN ({','.join('?' * len(ids))})", ids)
    return {"ok": True, "done": len(ids)}


M74_ABR_LOCK = threading.RLock()


def m74_servicerechnung(ids):
    """create a draft invoice from service entries (same customer)"""
    # v2.1.0: one at a time - a double click created two draft invoices for the same entries
    with M74_ABR_LOCK:
        return _m74_servicerechnung(ids)


def _m74_servicerechnung(ids):
    ids = [int(i) for i in ids or [] if str(i).isdigit()]
    rows = q(f"SELECT s.*, r.customer_id, r.project_id, r.gebaeude, r.raum FROM m74_service s JOIN m74_raum r ON r.id=s.raum_id "
             f"WHERE s.id IN ({','.join('?' * len(ids)) or 'NULL'}) ORDER BY s.datum, s.id", ids)
    if not rows:
        raise ValueError("Keine Service-Einsätze gewählt.")
    open_ = []
    for r in rows:
        inv = q("SELECT id FROM invoices WHERE id=?", (r["invoice_id"],), one=True) if r["invoice_id"] else None
        if not inv:
            open_.append(r)
    if not open_:
        raise ValueError("Die gewählten Einsätze sind schon abgerechnet.")
    custs = {r["customer_id"] for r in open_}
    if len(custs) > 1:
        raise ValueError("Bitte nur Einsätze eines Kunden zusammen abrechnen.")
    cid = custs.pop()
    c = q("SELECT * FROM customers WHERE id=?", (cid,), one=True) if cid else None
    cfg = m74_cfg()
    s = get_settings()
    art = q("SELECT * FROM articles WHERE id=?", (cfg.get("service_artikel"),), one=True) if cfg.get("service_artikel") else None
    satz = float(art["price"]) if art else float(cfg.get("stundensatz") or 0)
    gnames = {g["id"]: (" ".join(v for v in (g["hersteller"] or "", g["modell"] or "") if v) or g["kategorie"] or "")
              for g in q("SELECT id, hersteller, modell, kategorie FROM m74_geraet")}
    items = []
    for r in open_:
        raum = m74_raum_titel(r)
        txt = (r["beschreibung"] or "").strip()
        gn = gnames.get(r["geraet_id"], "")
        if r["stunden"]:
            items.append({"qty": round(float(r["stunden"]), 2), "nr": art["nr"] if art else "", "name": (art["name"] if art else "Service-Einsatz") +
                          f" am {de_date(r['datum'])}", "descr": f"{raum}{' · ' + gn if gn else ''}\n{txt}".strip(), "price": satz, "rabatt": 0,
                          "article_id": art["id"] if art else None})
        elif txt:
            items.append({"qty": 0, "nr": "", "name": f"Service-Einsatz am {de_date(r['datum'])}", "descr": f"{raum}{' · ' + gn if gn else ''}\n{txt}".strip(),
                          "price": 0, "rabatt": 0})
        try:
            mats = json.loads(r["material"] or "[]")
        except Exception:
            mats = []
        for m_ in mats:
            items.append({"qty": m_.get("qty") or 1, "nr": m_.get("nr") or "", "name": m_.get("name") or "Material", "descr": "", "price": m_.get("price") or 0, "rabatt": 0})
    if float(cfg.get("anfahrt") or 0) > 0:
        tage = sorted({r["datum"] for r in open_})
        items.append({"qty": len(tage), "nr": "", "name": "Anfahrtspauschale", "descr": ", ".join(de_date(t) for t in tage), "price": float(cfg["anfahrt"]), "rabatt": 0})
    pids = {r["project_id"] for r in open_ if r["project_id"]}
    d = {"customer_id": cid, "kdnr": c["kdnr"] if c else "", "addr": address_lines(c) if c else [], "project_id": pids.pop() if len(pids) == 1 else None,
         "datum": today(), "liefer": max(r["datum"] for r in open_), "titel": "Rechnung", "typ": "rechnung", "status": "entwurf",
         "toptext": s.get("default_top", ""), "foottext": s.get("default_foot", ""), "zahlart": s.get("zahlart", "Ueberweisung"),
         "frist": s.get("frist") or 7, "items": items, "source": "service"}
    iid, nr = save_invoice(d)
    x(f"UPDATE m74_service SET invoice_id=? WHERE id IN ({','.join('?' * len(open_))})", [iid] + [r["id"] for r in open_])
    return {"ok": True, "id": iid, "nr": nr, "n": len(open_)}


# ---------------------------------------------------------------------------- import / export
def _m74_rows_from_file(path):
    ext = os.path.splitext(path)[1].lower()
    rows = []
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        for r in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else (v.isoformat()[:10] if isinstance(v, (datetime.date, datetime.datetime)) else str(v)) for v in r])
        wb.close()
    elif ext in (".csv", ".txt"):
        data = open(path, "rb").read()
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except Exception:
                continue
        delim = ";" if text.count(";") >= text.count(",") else ","
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    else:
        raise ValueError("Bitte eine Excel-Datei (.xlsx) oder CSV-Datei wählen.")
    return rows


def m74_import(path, rid):
    rid = int(rid or 0)
    if not q("SELECT id FROM m74_raum WHERE id=?", (rid,), one=True):
        raise ValueError("Bitte zuerst einen Raum wählen.")
    rows = _m74_rows_from_file(path)
    hi, cmap = None, {}
    for i, r in enumerate(rows[:20]):
        m = {}
        for j, h in enumerate(r):
            hl = str(h or "").strip().lower()
            if not hl:
                continue
            for key, pat in M74_IMPORT_MAP:
                if key not in m and re.search(pat, hl):
                    m[key] = j
                    break
        if len(m) >= 2:
            hi, cmap = i, m
            break
    if hi is None:
        raise ValueError("Kopfzeile nicht erkannt. Erwartet werden Spalten wie Hersteller, Modell, Seriennummer, IP, MAC.")
    n = 0
    for r in rows[hi + 1:]:
        get = lambda k: (str(r[cmap[k]]).strip() if k in cmap and cmap[k] < len(r) and r[cmap[k]] is not None else "")
        d = {k: get(k) for k, _p in M74_IMPORT_MAP}
        if not (d["hersteller"] or d["modell"] or d["seriennr"]):
            continue
        d["raum_id"] = rid
        if d["kategorie"] and d["kategorie"] not in M74_KATEGORIEN:
            d["notiz"] = (d["notiz"] + " " if d["notiz"] else "") + f"(Kategorie: {d['kategorie']})"
            d["kategorie"] = _m74_guess_kat(d["kategorie"] + " " + d["modell"])
        elif not d["kategorie"]:
            d["kategorie"] = _m74_guess_kat(d["hersteller"] + " " + d["modell"])
        m74_geraet_save(d)
        n += 1
    return {"ok": True, "n": n, "spalten": sorted(cmap)}


def _m74_guess_kat(t):
    t = (t or "").lower()
    for kat, pat in (("DSP / Core", r"core|dsp|tesira|q-?sys|biamp|xilica|nexia|i-?o-?frame|qio"),
                     ("Mediensteuerung", r"crestron|cp[34]|rmc|tsw|tss|extron ipcp|ipl|amx|control"),
                     ("Display / Projektor", r"display|monitor|projektor|beamer|tv|panel|xg-|ph50|sharp|nec|epson|led"),
                     ("Kamera", r"kamera|camera|ptz|aw-ue|nc-|ptzoptics|eagle|smartvision"),
                     ("Mikrofon", r"mikro|mic|mxa|tcc|ceiling|beyerdynamic|shure|sennheiser|stegos|ccs"),
                     ("Lautsprecher / Verstärker", r"lautspr|speaker|amp|verstärk|cxd|spa|ad-"),
                     ("Netzwerk", r"switch|router|access point|netgear|cisco|unifi|poe|firewall"),
                     ("Videotechnik / Matrix", r"matrix|dtp|hdmi|scaler|c3-|xtp|dmps|nvx|encoder|decoder"),
                     ("Konferenz / BYOD", r"clickshare|byod|teams|zoom|mtr|avhub|cx-")):
        if re.search(pat, t):
            return kat
    return "Sonstiges"


def _m74_ex(p):
    ids = {int(i) for i in (p.get("ids") or []) if str(i).isdigit()}
    sql = "SELECT g.*, r.gebaeude, r.raum, r.customer_id FROM m74_geraet g JOIN m74_raum r ON r.id=g.raum_id"
    args, wh = [], []
    if p.get("raum_id"):
        wh.append("g.raum_id=?")
        args.append(int(p["raum_id"]))
    if p.get("customer_id"):
        wh.append("r.customer_id=?")
        args.append(int(p["customer_id"]))
    if wh:
        sql += " WHERE " + " AND ".join(wh)
    rows = q(sql + " ORDER BY r.customer_id, r.gebaeude, r.raum, g.kategorie, g.hersteller", tuple(args))
    if ids:
        rows = [r for r in rows if r["id"] in ids]
    cn = {}
    out = [_sh("Anlagenakte - Geräte",
               [("Kunde", "t", 22), ("Raum", "t", 22), ("Kategorie", "t", 18), ("Hersteller", "t", 16), ("Modell", "t", 20), ("Seriennr.", "t", 18),
                ("Firmware", "t", 12), ("FW geprüft", "d", 11), ("IP", "t", 15), ("MAC", "t", 18), ("VLAN", "t", 7), ("Standort", "t", 16),
                ("Einbau", "d", 11), ("Garantie bis", "d", 11), ("Wartung (Mon.)", "n", 9), ("Letzte Wartung", "d", 11), ("Aktiv", "t", 6), ("Notiz", "t", 28)],
               [[cn.setdefault(r["customer_id"], _m74_cust_name(r["customer_id"])), m74_raum_titel(r), r["kategorie"] or "", r["hersteller"] or "",
                 r["modell"] or "", r["seriennr"] or "", r["firmware"] or "", r["fw_geprueft"] or "", r["ip"] or "", r["mac"] or "", r["vlan"] or "",
                 r["standort"] or "", r["einbau"] or "", r["garantie_bis"] or "", r["wartung_monate"] or 0, r["wartung_letzte"] or "",
                 "ja" if r["aktiv"] else "nein", r["notiz"] or ""] for r in rows], f"Stand {de_date(today())}", total=False)]
    if not ids and not p.get("nur_geraete"):
        hin = m74_hinweise()
        if p.get("raum_id"):
            hin = [h for h in hin if h["raum_id"] == int(p["raum_id"])]
        out.append(_sh("Hinweise (Garantie, Wartung, Firmware)", [("Fällig", "d", 11), ("Art", "t", 10), ("Kunde", "t", 22), ("Raum", "t", 22),
                                                                  ("Gerät", "t", 26), ("Seriennr.", "t", 18), ("Hinweis", "t", 40)],
                       [[h["faellig"], h["art"], h["kunde"], h["raum"], h["geraet"], h["seriennr"], h["text"]] for h in hin], "", total=False))
    return out


EXPORTS["m74_anlagen"] = ("Anlagenakte", _m74_ex)


def _m74_csv_vorlage():
    head = ["Kategorie", "Hersteller", "Modell", "Seriennummer", "Firmware", "IP", "MAC", "VLAN", "Standort", "Einbau", "Garantie bis",
            "Wartung Monate", "Notiz"]
    ex = ["DSP / Core", "QSC", "Core 8 Flex", "3-1234567", "9.13.0", "192.168.1.10", "00:60:74:AA:BB:CC", "10", "Technikschrank", today(), "", "12", ""]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(head)
    w.writerow(ex)
    return buf.getvalue()


# ---------------------------------------------------------------------------- PDF report
def m74_bericht_pdf(raum_ids, titel=None, mit_service=True, open_=True):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    raum_ids = [int(i) for i in raum_ids if str(i).isdigit()]
    if not raum_ids:
        raise ValueError("Kein Raum gewählt.")
    details = [m74_raum_detail(r) for r in raum_ids]
    kunde = details[0]["raum"]["kunde"]
    acc, ink, gray, soft = colors.HexColor("#5b3fd6"), colors.HexColor("#1e1a2b"), colors.HexColor("#6c6880"), colors.HexColor("#f3f1fb")
    N = ParagraphStyle("n", fontName=FONT_R(), fontSize=8.5, leading=11, textColor=ink)
    NS = ParagraphStyle("ns", parent=N, fontSize=7.5, leading=9.5, textColor=gray)
    C = ParagraphStyle("c", parent=N, fontSize=7.5, leading=9.2)
    KIC = ParagraphStyle("k", fontName=FONT_B(), fontSize=7.5, leading=9, textColor=acc)
    H1 = ParagraphStyle("h1", fontName=FONT_B(), fontSize=19, leading=23, textColor=ink, spaceAfter=2)
    H2 = ParagraphStyle("h2", fontName=FONT_B(), fontSize=12.5, leading=16, textColor=ink, spaceBefore=8, spaceAfter=4)
    H3 = ParagraphStyle("h3", fontName=FONT_B(), fontSize=10, leading=13, textColor=ink, spaceBefore=8, spaceAfter=3)
    e = esc_xml
    titel = titel or (f"Anlagenbericht {details[0]['raum']['titel']}" if len(details) == 1 else f"Anlagenbericht {kunde or ''}".strip())
    ts = [("FONT", (0, 0), (-1, 0), FONT_B(), 7), ("TEXTCOLOR", (0, 0), (-1, 0), gray), ("LINEBELOW", (0, 0), (-1, 0), 0.6, ink),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=17 * mm, bottomMargin=15 * mm,
                            title=titel, author="T. Pfeiffer", creator=f"{APP_NAME} v{APP_VERSION}")
    el = [Paragraph("ANLAGENDOKUMENTATION", KIC), Paragraph(e(titel), H1),
          Paragraph(f"Kunde: {e(kunde or '-')} · {len(details)} Raum/Räume · Stand {de_date(today())} · erstellt von T. Pfeiffer", NS), Spacer(1, 6)]
    for k, dt in enumerate(details):
        r = dt["raum"]
        if k:
            el.append(PageBreak())
        el.append(Paragraph(e(r["titel"]), H2))
        info = []
        if r.get("adresse"):
            info.append(("Adresse", r["adresse"]))
        if r.get("projekt"):
            info.append(("Projekt", r["projekt"]))
        if r.get("notiz"):
            info.append(("Notiz", r["notiz"]))
        if info:
            t = Table([[Paragraph(f"<b>{e(a)}</b>", C), Paragraph(e(b).replace("\n", "<br/>"), C)] for a, b in info], colWidths=[28 * mm, 152 * mm])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
            el.append(t)
        ger = [g for g in dt["geraete"] if g["aktiv"]]
        el.append(Paragraph(f"Geräte ({len(ger)})", H3))
        if ger:
            rows = [["Kategorie", "Hersteller / Modell", "Seriennr.", "Firmware", "IP / VLAN", "MAC", "Standort", "Einbau", "Garantie"]]
            for g in ger:
                rows.append([Paragraph(e(g["kategorie"] or ""), C), Paragraph(e(" ".join(v for v in (g["hersteller"] or "", g["modell"] or "") if v)), C),
                             Paragraph(e(g["seriennr"] or ""), C), Paragraph(e(g["firmware"] or ""), C),
                             Paragraph(e((g["ip"] or "") + (f" / {g['vlan']}" if g["vlan"] else "")), C), Paragraph(e(g["mac"] or ""), C),
                             Paragraph(e(g["standort"] or ""), C), de_date(g["einbau"]) if g["einbau"] else "", de_date(g["garantie_bis"]) if g["garantie_bis"] else ""])
            t = Table(rows, colWidths=[22 * mm, 30 * mm, 22 * mm, 16 * mm, 24 * mm, 25 * mm, 18 * mm, 13 * mm, 13 * mm], repeatRows=1)
            t.setStyle(TableStyle(ts + [("FONT", (7, 1), (8, -1), FONT_R(), 7)]))
            el.append(t)
        else:
            el.append(Paragraph("Keine Geräte erfasst.", NS))
        if dt["dateien"]:
            el.append(Paragraph(f"Dokumentation / Dateien ({len(dt['dateien'])})", H3))
            rows = [["Art", "Datei", "Notiz", "Größe"]] + [[Paragraph(e(f["art"] or ""), C), Paragraph(e(f["name"] or ""), C), Paragraph(e(f["notiz"] or ""), C),
                                                            f"{round((f['size'] or 0) / 1024)} KB"] for f in dt["dateien"]]
            t = Table(rows, colWidths=[32 * mm, 80 * mm, 50 * mm, 18 * mm], repeatRows=1)
            t.setStyle(TableStyle(ts + [("ALIGN", (3, 0), (3, -1), "RIGHT")]))
            el.append(t)
        if mit_service and dt["service"]:
            el.append(Paragraph(f"Service-Historie ({len(dt['service'])})", H3))
            rows = [["Datum", "Gerät", "Tätigkeit", "Std."]] + [[de_date(s_["datum"]), Paragraph(e(s_["geraet"] or ""), C),
                                                                 Paragraph(e(s_["beschreibung"] or "").replace("\n", "<br/>"), C), num_de(s_["stunden"] or 0, 2)]
                                                                for s_ in dt["service"]]
            t = Table(rows, colWidths=[18 * mm, 38 * mm, 110 * mm, 14 * mm], repeatRows=1)
            t.setStyle(TableStyle(ts + [("ALIGN", (3, 0), (3, -1), "RIGHT")]))
            el.append(t)
    el += [Spacer(1, 14), Paragraph("Hinweis: Zugangsdaten und Passwörter sind aus Sicherheitsgründen nicht Bestandteil dieser Dokumentation.", NS)]

    def onpage(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(gray)
        cv.drawString(15 * mm, 8 * mm, f"{titel} · T. Pfeiffer")
        cv.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Seite {dc.page}")
        cv.setStrokeColor(acc)
        cv.setLineWidth(2)
        cv.line(15 * mm, A4[1] - 10 * mm, 37 * mm, A4[1] - 10 * mm)
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    data = buf.getvalue()
    if len(details) == 1:
        base = m74_raum_dir(raum_ids[0])
    else:
        base = os.path.join(PROJ_DIR, "Anlagen", safe_name(kunde or "ohne Kunde"))
        os.makedirs(base, exist_ok=True)
    fp = os.path.join(base, safe_name(f"Anlagenbericht_{titel.replace('Anlagenbericht ', '')}_{today()}.pdf"))
    write_file(fp, data)
    rel = os.path.relpath(fp, DATA_DIR)
    # also file it in the linked project
    pids = {dt["raum"]["project_id"] for dt in details if dt["raum"].get("project_id")}
    for pid in pids:
        if not q("SELECT id FROM project_files WHERE path=?", (rel,), one=True):
            x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
              (pid, "", "Dokument", os.path.basename(fp), rel, len(data), "Anlagenbericht", now_iso()))
    if open_ and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return fp


# ---------------------------------------------------------------------------- boot / routes
def _m74_boot(d):
    try:
        h = m74_hinweise()
        d["m74"] = {"hinweise": len(h), "liste": h[:12], "raeume": q("SELECT COUNT(*) n FROM m74_raum", one=True)["n"]}
    except Exception:
        d["m74"] = {"hinweise": 0, "liste": [], "raeume": 0}


HOOK_BOOT.append(_m74_boot)


def _m74_ok(h, extra=None):
    return h._send(200, dict({"ok": True}, **(extra or {})))


def _m74_g_list(h, qs):
    return h._send(200, {"ok": True, "raeume": m74_raeume(qs.get("customer_id"), qs.get("project_id")), "hinweise": m74_hinweise(),
                         "kategorien": M74_KATEGORIEN, "cfg": m74_cfg(),
                         "lager": q("SELECT id, nr, name, ek FROM m42_artikel WHERE aktiv=1 ORDER BY nr, name") if _m74_has_lager() else []})


def _m74_upload_file(h, tmp, name):
    r = m74_datei_add(tmp, name, h.headers.get("X-Raum") or 0, unquote(h.headers.get("X-Notiz") or ""))
    return h._send(200, r)


def _m74_upload_import(h, tmp, name):
    ext = os.path.splitext(name)[1].lower()
    tmp2 = tmp
    if not tmp.lower().endswith(ext):
        tmp2 = tmp + ext
        os.replace(tmp, tmp2)
    try:
        r = m74_import(tmp2, h.headers.get("X-Raum") or 0)
    finally:
        try:
            os.remove(tmp2)
        except OSError:
            pass
    return h._send(200, r)


def _m74_p_cfg(h, d):
    c = m74_cfg()
    for k in M74_DEFAULTS:
        if k in d:
            v = d[k]
            if k in ("fw_monate", "warn_tage"):
                v = max(0, int(float(str(v or 0).replace(",", "."))))
            elif k in ("stundensatz", "anfahrt"):
                v = round(float(str(v or 0).replace(",", ".")), 2)
            elif k == "service_artikel":
                v = int(v) if str(v or "").isdigit() else None
            c[k] = v
    set_setting("m74_cfg", c)
    return _m74_ok(h, {"cfg": c})


def _m74_p_vorlage(h, d):
    exp = os.path.join(DATA_DIR, "Export")
    os.makedirs(exp, exist_ok=True)
    fp = os.path.join(exp, "Geraeteliste_Vorlage.csv")
    write_file(fp, _m74_csv_vorlage(), text=True)
    if not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return _m74_ok(h, {"path": fp})


HOOK_GET["/api/m74/list"] = _m74_g_list
HOOK_GET["/api/m74/raum"] = lambda h, qs: h._send(200, m74_raum_detail(int(qs["id"])))
HOOK_GET["/api/m74/suche"] = lambda h, qs: h._send(200, m74_suche(qs.get("q") or ""))
HOOK_GET["/api/m74/hinweise"] = lambda h, qs: h._send(200, {"ok": True, "hinweise": m74_hinweise()})
HOOK_POST["/api/m74/raum/save"] = lambda h, d: _m74_ok(h, {"id": m74_raum_save(d)})
def _m74_p_raum_del(h, d):
    ids = [i for i in (d.get("ids") or [d.get("id")]) if str(i or "").isdigit()]
    for i in ids:
        m74_raum_delete(int(i), d.get("dateien", True))
    return _m74_ok(h, {"done": len(ids)})


HOOK_POST["/api/m74/raum/delete"] = _m74_p_raum_del
HOOK_POST["/api/m74/geraet/save"] = lambda h, d: _m74_ok(h, {"id": m74_geraet_save(d)})
HOOK_POST["/api/m74/geraet/bulk"] = lambda h, d: h._send(200, m74_geraete_bulk(d.get("ids"), d.get("action"), d.get("value")))
HOOK_POST["/api/m74/datei/delete"] = lambda h, d: h._send(200, m74_dateien_delete(d.get("ids") or [d.get("id")]))
HOOK_POST["/api/m74/datei/sync"] = lambda h, d: h._send(200, m74_dateien_sync(int(d["raum_id"])))
HOOK_POST["/api/m74/ordner"] = lambda h, d: _m74_ok(h, {"opened": open_path(m74_raum_dir(int(d["raum_id"])))})
HOOK_POST["/api/m74/service/save"] = lambda h, d: _m74_ok(h, {"id": m74_service_save(d)})
HOOK_POST["/api/m74/service/delete"] = lambda h, d: h._send(200, m74_service_delete(d.get("ids") or [d.get("id")]))
HOOK_POST["/api/m74/service/rechnung"] = lambda h, d: h._send(200, m74_servicerechnung(d.get("ids") or []))
HOOK_POST["/api/m74/bericht"] = lambda h, d: _m74_ok(h, {"path": m74_bericht_pdf(d.get("raum_ids") or [], d.get("titel"), d.get("service", True))})
HOOK_POST["/api/m74/cfg"] = _m74_p_cfg
HOOK_POST["/api/m74/vorlage"] = _m74_p_vorlage
HOOK_UPLOAD["/api/upload/m74datei"] = _m74_upload_file
HOOK_UPLOAD["/api/upload/m74import"] = _m74_upload_import


def _m74_selftest():
    err = []
    os.environ["PA_RECHNUNG_NO_OPEN"] = os.environ.get("PA_RECHNUNG_NO_OPEN") or "1"
    rid = None
    try:
        cid = x("INSERT INTO customers (kdnr, firma, name, created) VALUES (?,?,?,?)", ("_ST74", "Selbsttest Anlagen GmbH", "", now_iso()))
        rid = m74_raum_save({"customer_id": cid, "gebaeude": "Haus A", "raum": "Saal 1"})
        gid = m74_geraet_save({"raum_id": rid, "kategorie": "DSP / Core", "hersteller": "QSC", "modell": "Core 8 Flex", "seriennr": "ST-74-1",
                               "ip": "10.0.0.5", "mac": "00-60-74-aa-bb-cc", "garantie_bis": (datetime.date.today() + datetime.timedelta(days=5)).isoformat(),
                               "wartung_monate": 12, "einbau": "01.01.2020", "firmware": "9.10"})
        g = q("SELECT * FROM m74_geraet WHERE id=?", (gid,), one=True)
        if g["mac"] != "00:60:74:AA:BB:CC" or g["einbau"] != "2020-01-01":
            err.append("m74: MAC/Datum nicht normalisiert")
        arts = {h["art"] for h in m74_hinweise() if h["geraet_id"] == gid}
        if not {"garantie", "wartung"} <= arts:
            err.append(f"m74: Erinnerungen fehlen ({arts})")
        if not any(t["id"] == gid for t in m74_suche("6074aabb")["treffer"]):
            err.append("m74: Suche nach MAC ohne Trenner findet Gerät nicht")
        sid = m74_service_save({"raum_id": rid, "geraet_id": gid, "datum": today(), "beschreibung": "Firmware-Update", "stunden": 1.5,
                                "material": [{"name": "Patchkabel", "qty": 2, "price": 4.5}], "wartung_erledigt": True})
        cfg_old = get_settings().get("m74_cfg")
        set_setting("m74_cfg", dict(M74_DEFAULTS, stundensatz=80.0))
        r = m74_servicerechnung([sid])
        inv = get_invoice(r["id"])
        if inv["status"] != "entwurf" or abs(inv["summe"] - 129.0) > 0.01:
            err.append(f"m74: Servicerechnung falsch ({inv['status']}, {inv['summe']})")
        x("DELETE FROM items WHERE invoice_id=?", (r["id"],))
        x("DELETE FROM invoices WHERE id=?", (r["id"],))
        set_setting("m74_cfg", cfg_old or {})
        if _m74_guess_kat("Crestron CP4") != "Mediensteuerung":
            err.append("m74: Kategorie-Erkennung falsch")
        if not _m74_ex({"raum_id": rid})[0]["rows"]:
            err.append("m74: Export leer")
        x("DELETE FROM customers WHERE id=?", (cid,))
    except Exception as e:
        err.append(f"m74: Ausnahme {e}")
    finally:
        if rid:
            try:
                m74_raum_delete(rid)
            except Exception:
                pass
    return err


HOOK_SELFTEST.append(_m74_selftest)
