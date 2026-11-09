# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m78_inventor (v2.0.19)
# Inventor-Anbindung erweitert:
#  - Stuecklisten-Datei (Excel/CSV-Export aus Inventor) je Projekt verknuepfen - entweder eine Datei irgendwo
#    auf dem PC (wird ueberwacht) oder eine Datei im Projektordner
#  - Ueberwachung: alle 60 s Aenderungszeit/Groesse pruefen, bei Aenderung neu einlesen, Unterschiede
#    (neu / geaendert / entfernt) protokollieren, verknuepfte Kalkulation (m41) automatisch neu rechnen
#  - Material gegen Lager (m42): Zuordnung Position <-> Lagerartikel (Nr., Name oder manuell - wird gelernt),
#    Bedarf / verfuegbar / reserviert, Reservieren, Entnehmen (Projekt-Eintrag Material wie m42_entnahme)
#  - Bestellliste fehlender Teile nach Lieferant (PDF, Excel, Mail-Text)
#  - Zuschnittliste (Laenge x Anzahl je Profil) mit Stabaufteilung (Stablaenge, Schnittfuge einstellbar)
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M78_VERSION = "1.0.0"
M78_DEF_SET = {"stablaenge": 6000.0, "schnittfuge": 3.0, "intervall": 60}
M78_STATE = {"running": False, "last": 0.0}
M78_LOCK = threading.RLock()     # reserve / take: one request at a time (double click must not book twice)


def _m78_schema():
    x("CREATE TABLE IF NOT EXISTS m78_bom (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, path TEXT, extern INTEGER DEFAULT 0, "
      "mtime REAL, size INTEGER, hash TEXT, rows TEXT, gelesen TEXT, fehler TEXT, kalk_id INTEGER, auto INTEGER DEFAULT 1, "
      "neu_seit TEXT, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS m78_change (id INTEGER PRIMARY KEY, bom_id INTEGER, zeit TEXT, neu INTEGER, geaendert INTEGER, "
      "entfernt INTEGER, details TEXT, gesehen INTEGER DEFAULT 0)")
    x("CREATE TABLE IF NOT EXISTS m78_map (schluessel TEXT PRIMARY KEY, artikel_id INTEGER, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m78_res (id INTEGER PRIMARY KEY, bom_id INTEGER, schluessel TEXT, artikel_id INTEGER, menge REAL, "
      "art TEXT, buchung_id INTEGER, entry_id INTEGER, created TEXT)")
    try:
        x("CREATE INDEX IF NOT EXISTS m78_c_bom ON m78_change(bom_id)")
        x("CREATE INDEX IF NOT EXISTS m78_r_bom ON m78_res(bom_id)")
        x("CREATE INDEX IF NOT EXISTS m78_r_art ON m78_res(artikel_id)")
    except Exception:
        pass


HOOK_SCHEMA.append(_m78_schema)


def m78_settings():
    m = dict(M78_DEF_SET, **(get_settings().get("m78") or {}))
    for k in ("stablaenge", "schnittfuge"):
        try:
            m[k] = float(m[k])
        except Exception:
            m[k] = M78_DEF_SET[k]
    return m


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def _m78_num(v):
    t = re.sub(r"[^\d,.\-]", "", str(v or "")).strip()
    if not t:
        return None
    if "," in t and "." in t:
        # the last separator is the decimal one: "1.500,000" (German) / "1,500.000" (English Inventor)
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")      # "1.500" = thousands separator (German)
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except Exception:
        return None


def _m78_len_mm(v):
    """'1250 mm' / '1,25 m' / '125 cm' / '1250' -> mm"""
    s = str(v or "").strip().lower()
    n = _m78_num(s)
    if n is None:
        return 0.0
    if re.search(r"\d\s*m$", s) and not s.endswith("mm"):
        return round(n * 1000, 1)
    if s.endswith("cm"):
        return round(n * 10, 1)
    return round(n, 1)


def _m78_key(r):
    base = (r.get("nr") or r.get("name") or "").strip().lower()
    base = re.sub(r"\s+", " ", base)
    ln = r.get("laenge") or 0
    return f"{base}|{int(round(ln))}" if ln else base


def m78_parse(path):
    if path.lower().endswith(".xls"):
        raise ValueError("Das alte Excel-Format .xls kann nicht gelesen werden - die Stückliste in Inventor bitte als .xlsx oder .csv exportieren "
                         "(oder in Excel als .xlsx speichern).")
    rows = read_table_file(path)
    hi = None
    for i, r in enumerate(rows[:30]):
        low = " ".join(str(c).lower() for c in r)
        if re.search(r"menge|anz|qty|quantity|stück|stueck", low) and re.search(r"beschreibung|benennung|description|bauteil|teil|part", low):
            hi = i
            break
    if hi is None:
        raise ValueError("Kopfzeile der Stückliste nicht erkannt (Spalten Menge und Benennung/Beschreibung erwartet).")
    head = [str(c).strip().lower() for c in rows[hi]]

    def col(*pats, avoid=()):
        for pat in pats:
            for i, h in enumerate(head):
                if re.search(pat, h) and not any(re.search(a, h) for a in avoid):
                    return i
        return None
    c = {"pos": col(r"^pos|position|element|item"),
         "nr": col(r"bauteilnummer|teilenummer|part number|artikelnummer|sachnummer|zeichnungsnummer|nummer", avoid=(r"bestell", r"order")),
         "name": col(r"beschreibung|benennung|description|titel|bezeichnung"),
         "qty": col(r"menge|anz|qty|quantity|stück|stueck", avoid=(r"einheit", r"unit", r"basis", r"base")),
         "unit": col(r"einheit|unit|^me$", avoid=(r"menge", r"qty", r"quantity")),
         "material": col(r"material|werkstoff"),
         "masse": col(r"masse|gewicht|mass|weight"),
         "laenge": col(r"länge|laenge|length|^lg\b|zuschnitt|g_l"),
         "abmessung": col(r"abmessung|profil|halbzeug|dimension|stock|norm"),
         "lieferant": col(r"lieferant|hersteller|vendor|supplier|bezugsquelle"),
         "bestellnr": col(r"bestellnummer|bestell-?nr|order")}
    agg = {}
    order = []
    for r in rows[hi + 1:]:
        g = lambda k: (str(r[c[k]]).strip() if c[k] is not None and c[k] < len(r) and r[c[k]] is not None else "")
        name = g("name") or g("nr")
        if not name:
            continue
        qty = _m78_num(g("qty"))
        qty = 1.0 if qty is None else qty
        it = {"pos": g("pos"), "nr": g("nr"), "name": name, "qty": qty, "unit": g("unit") or "Stk", "material": g("material"),
              "masse_kg": parse_mass_kg(g("masse")), "laenge": _m78_len_mm(g("laenge")), "abmessung": g("abmessung"),
              "lieferant": g("lieferant"), "bestellnr": g("bestellnr")}
        k = _m78_key(it)
        if k in agg:
            agg[k]["qty"] = round(agg[k]["qty"] + qty, 4)
            if it["pos"] and it["pos"] not in agg[k]["pos"].split(", "):
                agg[k]["pos"] = (agg[k]["pos"] + ", " + it["pos"]).strip(", ")
        else:
            it["key"] = k
            agg[k] = it
            order.append(k)
    return [agg[k] for k in order]


def _m78_abs(b):
    p = b["path"] or ""
    return p if os.path.isabs(p) else os.path.join(DATA_DIR, p)


def _m78_diff(old, new):
    om = {r["key"]: r for r in old or []}
    nm = {r["key"]: r for r in new or []}
    neu = [{"key": k, "name": nm[k]["name"], "qty": nm[k]["qty"]} for k in nm if k not in om]
    weg = [{"key": k, "name": om[k]["name"], "qty": om[k]["qty"]} for k in om if k not in nm]
    ch = []
    for k in nm:
        if k in om:
            diffs = []
            for f, lbl in (("qty", "Menge"), ("material", "Material"), ("masse_kg", "Masse"), ("abmessung", "Abmessung"), ("name", "Benennung")):
                a, b_ = om[k].get(f), nm[k].get(f)
                if (isinstance(a, float) or isinstance(b_, float)) and a is not None and b_ is not None:
                    if abs(float(a or 0) - float(b_ or 0)) > 1e-6:
                        diffs.append(f"{lbl} {num_de(float(a or 0), 2)} → {num_de(float(b_ or 0), 2)}")
                elif (a or "") != (b_ or ""):
                    diffs.append(f"{lbl} {a or '-'} → {b_ or '-'}")
            if diffs:
                ch.append({"key": k, "name": nm[k]["name"], "was": "; ".join(diffs)})
    return neu, ch, weg


def m78_read(bid, force=False, record=True):
    """(re)read one BOM. returns dict with changed flag"""
    b = q("SELECT * FROM m78_bom WHERE id=?", (int(bid),), one=True)
    if not b:
        raise ValueError("Stückliste nicht gefunden.")
    fp = _m78_abs(b)
    if not os.path.isfile(fp):
        x("UPDATE m78_bom SET fehler=? WHERE id=?", ("Datei nicht gefunden: " + fp, b["id"]))
        return {"ok": False, "changed": False, "error": "Datei nicht gefunden"}
    st = os.stat(fp)
    if not force and b["mtime"] and abs(float(b["mtime"]) - st.st_mtime) < 0.001 and int(b["size"] or -1) == st.st_size:
        return {"ok": True, "changed": False}
    raw = open(fp, "rb").read()
    h = hashlib.sha1(raw).hexdigest()
    if not force and h == b["hash"]:
        x("UPDATE m78_bom SET mtime=?, size=? WHERE id=?", (st.st_mtime, st.st_size, b["id"]))
        return {"ok": True, "changed": False}
    try:
        rows = m78_parse(fp)
    except Exception as e:
        # Inventor may still be writing the file - try again on the next round
        x("UPDATE m78_bom SET fehler=? WHERE id=?", (str(e)[:300], b["id"]))
        return {"ok": False, "changed": False, "error": str(e)}
    old = json.loads(b["rows"] or "[]")
    neu, ch, weg = _m78_diff(old, rows)
    x("UPDATE m78_bom SET rows=?, mtime=?, size=?, hash=?, gelesen=?, fehler='' WHERE id=?",
      (json.dumps(rows, ensure_ascii=False), st.st_mtime, st.st_size, h, now_iso(), b["id"]))
    changed = bool(old) and bool(neu or ch or weg)
    if record and changed:
        x("INSERT INTO m78_change (bom_id, zeit, neu, geaendert, entfernt, details) VALUES (?,?,?,?,?,?)",
          (b["id"], now_iso(), len(neu), len(ch), len(weg), json.dumps({"neu": neu, "geaendert": ch, "entfernt": weg}, ensure_ascii=False)))
    if b["kalk_id"] and (changed or force or not old):
        try:
            m78_update_kalk(b["id"])
        except Exception:
            traceback.print_exc()
    return {"ok": True, "changed": changed, "neu": len(neu), "geaendert": len(ch), "entfernt": len(weg), "zeilen": len(rows)}


def m78_check_all():
    out = []
    for b in q("SELECT id FROM m78_bom WHERE auto=1"):
        try:
            r = m78_read(b["id"])
            if r.get("changed"):
                out.append(b["id"])
        except Exception:
            traceback.print_exc()
    M78_STATE["last"] = time.time()
    return out


def _m78_loop():
    if M78_STATE["running"]:
        return
    M78_STATE["running"] = True
    time.sleep(20)
    while True:
        try:
            m78_check_all()
        except Exception:
            traceback.print_exc()
        try:
            iv = max(15, int(m78_settings().get("intervall") or 60))
        except Exception:
            iv = 60
        time.sleep(iv)


HOOK_START.append(_m78_loop)


# ---------------------------------------------------------------------------
# link / unlink
# ---------------------------------------------------------------------------
def m78_link(d):
    pid = int(d["project_id"])
    if not q("SELECT id FROM projects WHERE id=?", (pid,), one=True):
        raise ValueError("Projekt nicht gefunden.")
    extern = 0
    if d.get("file_id"):
        f = q("SELECT * FROM project_files WHERE id=? AND project_id=?", (int(d["file_id"]), pid), one=True)
        if not f:
            raise ValueError("Projektdatei nicht gefunden.")
        path, name = f["path"], f["name"]
    else:
        path = (d.get("path") or "").strip().strip('"')
        if not path or not os.path.isabs(path):
            raise ValueError("Bitte eine Stücklisten-Datei auswählen.")
        if not os.path.isfile(path):
            raise ValueError("Datei nicht gefunden: " + path)
        name, extern = os.path.basename(path), 1
    if not re.search(r"\.(csv|txt|xlsx|xlsm|xls|tsv)$", path.lower()):
        raise ValueError("Bitte eine Stückliste als Excel (.xlsx) oder CSV/TXT auswählen (Export aus Inventor).")
    m78_parse(path if os.path.isabs(path) else os.path.join(DATA_DIR, path))      # validates header
    dup = q("SELECT id FROM m78_bom WHERE project_id=? AND path=?", (pid, path), one=True)
    if dup:
        bid = dup["id"]
    else:
        bid = x("INSERT INTO m78_bom (project_id, name, path, extern, auto, kalk_id, rows, created) VALUES (?,?,?,?,?,?,?,?)",
                (pid, (d.get("name") or name)[:120], path, extern, 0 if d.get("auto") in (0, False, "0") else 1,
                 int(d["kalk_id"]) if d.get("kalk_id") else None, "[]", now_iso()))
        # rows of a deleted id must never leak into a new list (SQLite may hand out the same id again)
        x("DELETE FROM m78_res WHERE bom_id=?", (bid,))
        x("DELETE FROM m78_change WHERE bom_id=?", (bid,))
        x("UPDATE m78_res SET bom_id=? WHERE bom_id=?", (bid, -pid))
    r = m78_read(bid, force=True, record=False)
    return dict(r, id=bid)


def m78_update_bom(d):
    bid = int(d["id"])
    b = q("SELECT * FROM m78_bom WHERE id=?", (bid,), one=True)
    if not b:
        raise ValueError("Stückliste nicht gefunden.")
    if "auto" in d:
        x("UPDATE m78_bom SET auto=? WHERE id=?", (1 if d["auto"] else 0, bid))
    if "name" in d and (d["name"] or "").strip():
        x("UPDATE m78_bom SET name=? WHERE id=?", (d["name"].strip()[:120], bid))
    if "kalk_id" in d:
        kid = d.get("kalk_id")
        if kid == "neu":
            kid, _res = m41_kalk_save({"project_id": b["project_id"], "name": f"Kalkulation {b['name']}", "data": {"rows": []}})
        x("UPDATE m78_bom SET kalk_id=? WHERE id=?", (int(kid) if kid else None, bid))
        if kid:
            m78_update_kalk(bid)
    return {"ok": True}


def m78_unlink(ids):
    for i in ids or []:
        i = int(i)
        b = q("SELECT project_id FROM m78_bom WHERE id=?", (i,), one=True)
        x("DELETE FROM m78_res WHERE bom_id=? AND art='reserviert'", (i,))
        # stock already taken stays with the project (bom_id = -project_id): a list linked again later
        # takes these rows over, so the same material is not booked out of the stock twice
        if b:
            x("UPDATE m78_res SET bom_id=? WHERE bom_id=? AND art='entnommen'", (-int(b["project_id"]), i))
        else:
            x("DELETE FROM m78_res WHERE bom_id=?", (i,))
        x("DELETE FROM m78_change WHERE bom_id=?", (i,))
        x("DELETE FROM m78_bom WHERE id=?", (i,))
    return {"ok": True}


def _m78_upload(h, tmp, name):
    try:
        pid = int(h.headers.get("X-M78-Project") or 0)
        if not q("SELECT id FROM projects WHERE id=?", (pid,), one=True):
            raise ValueError("Projekt nicht gefunden.")
        if not re.search(r"\.(csv|txt|xlsx|xlsm|xls|tsv)$", name.lower()):
            raise ValueError("Bitte eine Stückliste als Excel (.xlsx) oder CSV/TXT hochladen.")
        f = add_project_file(pid, tmp, name)
        r = m78_link({"project_id": pid, "file_id": f["id"]})
        return h._send(200, dict(r, ok=True))
    except ValueError as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return h._send(200, {"ok": False, "error": str(e)})


HOOK_UPLOAD["/api/upload/m78"] = _m78_upload


# ---------------------------------------------------------------------------
# calculation (m41)
# ---------------------------------------------------------------------------
def m78_update_kalk(bid):
    b = q("SELECT * FROM m78_bom WHERE id=?", (int(bid),), one=True)
    if not b or not b["kalk_id"] or "_m41_kalk_load" not in globals():
        return None
    try:
        k = _m41_kalk_load(b["kalk_id"])
    except ValueError:
        x("UPDATE m78_bom SET kalk_id=NULL WHERE id=?", (b["id"],))
        return None
    old = {}
    for r in k["data"].get("rows") or []:
        old[(str(r.get("nr") or "") + "|" + str(r.get("name") or "")).strip().lower()] = r
    chk = {c["key"]: c for c in m78_check(b["id"])["rows"]}
    rows = []
    for r in json.loads(b["rows"] or "[]"):
        # cut parts of one profile differ only by length -> length in the name keeps them apart (and shows in the offer)
        nm = (r.get("name") or "") + (f" L {num_de(r['laenge'], 0)} mm" if r.get("laenge") else "")
        o = old.get(((r.get("nr") or "") + "|" + nm).strip().lower(), {})
        ek = o.get("ek_stk")
        c = chk.get(r["key"]) or {}
        if ek in (None, "", 0, 0.0) and c.get("artikel") and float(c["artikel"].get("ek") or 0) > 0:
            a = c["artikel"]
            if (a.get("einheit") or "").lower() == "m" and r.get("laenge"):
                ek = round(float(a["ek"]) * r["laenge"] / 1000.0, 4)
            elif (a.get("einheit") or "Stk").lower() in ("stk", "st", "stück"):
                ek = float(a["ek"])
        rows.append({"nr": r.get("nr") or "", "name": nm, "qty": r.get("qty") or 0, "unit": r.get("unit") or "Stk",
                     "material": r.get("material") or "", "masse_kg": r.get("masse_kg") or 0, "ek_stk": ek,
                     "preis_kg": o.get("preis_kg"), "use": o.get("use") is not False})
    data = dict(k["data"], rows=rows)
    kid, res = m41_kalk_save({"id": k["id"], "project_id": k["project_id"], "name": k["name"], "data": data})
    return res


# ---------------------------------------------------------------------------
# stock check
# ---------------------------------------------------------------------------
def _m78_lager_ok():
    return "m42_book" in globals() and bool(q("SELECT name FROM sqlite_master WHERE type='table' AND name='m42_artikel'", one=True))


def _m78_find_art(r, arts, mp):
    k = r["key"]
    base = k.split("|")[0]
    for kk in (k, base):
        if kk in mp and mp[kk] in arts:
            return arts[mp[kk]], "gelernt"
    nr = (r.get("nr") or "").strip().lower()
    nm = (r.get("name") or "").strip().lower()
    for a in arts.values():
        if not a["aktiv"]:
            continue
        if nr and (a["nr"] or "").strip().lower() == nr:
            return a, "Nr."
    for a in arts.values():
        if not a["aktiv"]:
            continue
        if nr and (a["name"] or "").strip().lower() == nr:
            return a, "Name"
        if nm and ((a["name"] or "").strip().lower() == nm or (a["nr"] or "").strip().lower() == nm):
            return a, "Name"
    return None, ""


def _m78_bedarf(r, a):
    qty = float(r.get("qty") or 0)
    if a and (a.get("einheit") or "").lower() == "m" and r.get("laenge"):
        return round(qty * float(r["laenge"]) / 1000.0, 3)
    if a and (a.get("einheit") or "").lower() == "kg" and r.get("masse_kg"):
        return round(qty * float(r["masse_kg"]), 3)
    return qty


def m78_check(bid):
    b = q("SELECT * FROM m78_bom WHERE id=?", (int(bid),), one=True)
    if not b:
        raise ValueError("Stückliste nicht gefunden.")
    rows = json.loads(b["rows"] or "[]")
    lager = _m78_lager_ok()
    arts = {a["id"]: a for a in q("SELECT * FROM m42_artikel")} if lager else {}
    mp = {m["schluessel"]: m["artikel_id"] for m in q("SELECT * FROM m78_map")}
    res_all = q("SELECT bom_id, schluessel, artikel_id, menge, art FROM m78_res")
    res_other = {}
    for rr in res_all:
        if rr["art"] == "reserviert" and rr["bom_id"] != b["id"]:
            res_other[rr["artikel_id"]] = res_other.get(rr["artikel_id"], 0.0) + float(rr["menge"] or 0)
    mine = {}
    for rr in res_all:
        if rr["bom_id"] == b["id"]:
            m = mine.setdefault(rr["schluessel"], {"reserviert": 0.0, "entnommen": 0.0})
            m["reserviert" if rr["art"] == "reserviert" else "entnommen"] += float(rr["menge"] or 0)
    out = []
    used = {}
    for r in rows:
        a, how = _m78_find_art(r, arts, mp) if lager else (None, "")
        me = mine.get(r["key"], {"reserviert": 0.0, "entnommen": 0.0})
        bedarf = _m78_bedarf(r, a)
        offen = max(0.0, round(bedarf - me["entnommen"], 4))
        c = dict(r, bedarf=bedarf, einheit=(a["einheit"] if a else r.get("unit") or "Stk"), zuordnung=how,
                 artikel=({"id": a["id"], "nr": a["nr"], "name": a["name"], "einheit": a["einheit"], "bestand": float(a["bestand"] or 0),
                           "ek": float(a["ek"] or 0), "lagerort": a["lagerort"] or "", "notiz": a["notiz"] or ""} if a else None),
                 reserviert=round(me["reserviert"], 4), entnommen=round(me["entnommen"], 4), offen=offen)
        if not a:
            c.update(verfuegbar=0.0, fehlt=offen, status="ohne" if lager else "kein_lager")
        else:
            # stock minus reservations of other BOMs minus what earlier rows of this list already took
            frei = float(a["bestand"] or 0) - res_other.get(a["id"], 0.0) - used.get(a["id"], 0.0)
            frei = round(max(0.0, frei), 4)
            need = max(0.0, offen)
            take = min(frei, need)
            used[a["id"]] = used.get(a["id"], 0.0) + take
            fehlt = round(max(0.0, need - frei), 4)
            c.update(verfuegbar=frei, fehlt=fehlt,
                     status="entnommen" if need <= 1e-9 else ("ok" if fehlt <= 1e-9 else ("teilweise" if frei > 0 else "fehlt")))
        out.append(c)
    summ = {k: sum(1 for c in out if c["status"] == k) for k in ("ok", "teilweise", "fehlt", "ohne", "entnommen", "kein_lager")}
    return {"rows": out, "summe": summ, "lager": lager}


def m78_map(d):
    key = (d.get("key") or "").strip()
    if not key:
        raise ValueError("Position fehlt.")
    aid = d.get("artikel_id")
    if aid in (None, "", 0, "0"):
        x("DELETE FROM m78_map WHERE schluessel=?", (key,))
        return {"ok": True}
    if not q("SELECT id FROM m42_artikel WHERE id=?", (int(aid),), one=True):
        raise ValueError("Lagerartikel nicht gefunden.")
    x("INSERT OR REPLACE INTO m78_map (schluessel, artikel_id, updated) VALUES (?,?,?)", (key, int(aid), now_iso()))
    return {"ok": True}


def m78_reserve(d):
    with M78_LOCK:
        return _m78_reserve(d)


def _m78_reserve(d):
    bid = int(d["bom_id"])
    chk = {c["key"]: c for c in m78_check(bid)["rows"]}
    keys = d.get("keys") or list(chk)
    n = 0
    for k in keys:
        x("DELETE FROM m78_res WHERE bom_id=? AND schluessel=? AND art='reserviert'", (bid, k))
        if d.get("weg"):
            n += 1
            continue
        c = chk.get(k)
        if not c or not c.get("artikel"):
            continue
        menge = min(c["offen"], c["verfuegbar"]) if c["verfuegbar"] > 0 else 0.0
        if menge <= 0:
            continue
        x("INSERT INTO m78_res (bom_id, schluessel, artikel_id, menge, art, created) VALUES (?,?,?,?,?,?)",
          (bid, k, c["artikel"]["id"], round(menge, 4), "reserviert", now_iso()))
        n += 1
    return {"ok": True, "n": n}


def m78_entnahme(d):
    with M78_LOCK:
        return _m78_entnahme(d)


def _m78_entnahme(d):
    bid = int(d["bom_id"])
    b = q("SELECT * FROM m78_bom WHERE id=?", (bid,), one=True)
    if not b:
        raise ValueError("Stückliste nicht gefunden.")
    chk = {c["key"]: c for c in m78_check(bid)["rows"]}
    keys = d.get("keys") or [k for k, c in chk.items() if c.get("artikel") and c["offen"] > 0]
    n, warn = 0, []
    for k in keys:
        c = chk.get(k)
        if not c or not c.get("artikel") or c["offen"] <= 0:
            continue
        # verfuegbar already contains this list's own reservation (only other lists are subtracted)
        menge = c["offen"] if d.get("alles") else (min(c["offen"], c["verfuegbar"]) or 0)
        if menge <= 0:
            warn.append(f"{c['name']}: kein Bestand")
            continue
        r = m42_entnahme({"project_id": b["project_id"], "artikel_id": c["artikel"]["id"], "menge": menge,
                          "notiz": f"Stückliste {b['name']}" + (f" Pos. {c['pos']}" if c.get("pos") else ""), "als_eintrag": d.get("als_eintrag", True)})
        if r.get("warn"):
            warn.append(f"{c['name']}: {r['warn']}")
        x("DELETE FROM m78_res WHERE bom_id=? AND schluessel=? AND art='reserviert'", (bid, k))
        x("INSERT INTO m78_res (bom_id, schluessel, artikel_id, menge, art, buchung_id, entry_id, created) VALUES (?,?,?,?,?,?,?,?)",
          (bid, k, c["artikel"]["id"], round(menge, 4), "entnommen", r.get("buchung_id"), r.get("entry_id"), now_iso()))
        n += 1
    return {"ok": True, "n": n, "warn": warn}


# ---------------------------------------------------------------------------
# order list / cut list
# ---------------------------------------------------------------------------
def m78_bestell(bid):
    b = q("SELECT * FROM m78_bom WHERE id=?", (int(bid),), one=True)
    if not b:
        raise ValueError("Stückliste nicht gefunden.")
    chk = m78_check(bid)
    groups = {}
    for c in chk["rows"]:
        if c["status"] not in ("fehlt", "teilweise", "ohne", "kein_lager") or c["fehlt"] <= 0:
            continue
        a = c.get("artikel") or {}
        lief = c.get("lieferant") or ""
        if not lief and a.get("notiz"):
            m = re.search(r"(?:lieferant|bezug|bei)\s*[:=]?\s*([^,;\n]+)", a["notiz"], re.I)
            lief = m.group(1).strip() if m else ""
        lief = lief or "ohne Lieferant"
        ek = float(a.get("ek") or 0)
        groups.setdefault(lief, []).append({"nr": a.get("nr") or c.get("nr") or "", "bestellnr": c.get("bestellnr") or "",
                                            "name": c["name"] + (f" · L {num_de(c['laenge'], 0)} mm" if c.get("laenge") else ""),
                                            "abmessung": c.get("abmessung") or "", "material": c.get("material") or "",
                                            "menge": round(c["fehlt"], 3), "einheit": c.get("einheit") or "Stk", "ek": ek,
                                            "summe": round(ek * c["fehlt"], 2), "lager": bool(a)})
    out = [{"lieferant": k, "rows": v, "summe": round(sum(r["summe"] for r in v), 2)} for k, v in sorted(groups.items(), key=lambda kv: (kv[0] == "ohne Lieferant", kv[0].lower()))]
    p = q("SELECT nr, name FROM projects WHERE id=?", (b["project_id"],), one=True) or {"nr": "", "name": ""}
    return {"bom": b["name"], "projekt": p, "gruppen": out, "positionen": sum(len(g["rows"]) for g in out)}


def m78_bestell_text(bid):
    d = m78_bestell(bid)
    s = get_settings()
    parts = []
    for g in d["gruppen"]:
        lines = [f"Bestellung {g['lieferant']} - Projekt {d['projekt']['nr']} {d['projekt']['name']}", "",
                 "Sehr geehrte Damen und Herren,", "", "bitte liefern Sie uns folgende Positionen:", ""]
        for r in g["rows"]:
            nr = r["bestellnr"] or r["nr"]
            lines.append(f"- {num_de(r['menge'], 3).rstrip('0').rstrip(',')} {r['einheit']}  {r['name']}"
                         + (f" ({r['abmessung']})" if r["abmessung"] else "") + (f"  Art.-Nr. {nr}" if nr else ""))
        lines += ["", "Bitte bestätigen Sie Liefertermin und Preis.", "", "Mit freundlichen Grüßen", s.get("inhaber") or "", s.get("firma") or ""]
        parts.append({"lieferant": g["lieferant"], "betreff": f"Bestellung Projekt {d['projekt']['nr']}", "text": "\n".join(lines)})
    return {"ok": True, "mails": parts}




# ---------------------------------------------------------------------------
# v2.1.0: cutting optimisation (bin packing)
# A bar of length L holds pieces l1..ln when sum(l) + fuge*(n-1) <= L (no kerf after the
# last piece if nothing is left). Equivalent: items l+fuge into bins of capacity L+fuge.
# FFD/BFD as start, then exact branch-and-bound (time limited), else local improvement.
# ---------------------------------------------------------------------------
M78_PACK_TIME = 1.0


def _m78_lb(sizes, cap):
    if not sizes:
        return 0
    big = sum(1 for s_ in sizes if s_ * 2 > cap)
    return max(-(-sum(sizes) // cap), big)


def _m78_fit(order, sizes, cap, best_fit=False):
    bins, res = [], []
    for i in order:
        s_ = sizes[i]
        j_best = -1
        for j, r_ in enumerate(res):
            if r_ >= s_ and (j_best < 0 or (best_fit and r_ < res[j_best])):
                j_best = j
                if not best_fit:
                    break
        if j_best < 0:
            bins.append([i])
            res.append(cap - s_)
        else:
            bins[j_best].append(i)
            res[j_best] -= s_
    return bins


def _m78_improve(bins, sizes, cap, deadline):
    """try to empty the least filled bar by moving its pieces into the others"""
    bins = [list(b_) for b_ in bins]
    changed = True
    while changed and time.time() < deadline and len(bins) > 1:
        changed = False
        for k in sorted(range(len(bins)), key=lambda k_: sum(sizes[i] for i in bins[k_])):
            others = [list(b_) for j, b_ in enumerate(bins) if j != k]
            res = [cap - sum(sizes[i] for i in b_) for b_ in others]
            ok = True
            for i in sorted(bins[k], key=lambda i_: -sizes[i_]):
                cand = [j for j, r_ in enumerate(res) if r_ >= sizes[i]]
                if not cand:
                    ok = False
                    break
                j = min(cand, key=lambda j_: res[j_])
                others[j].append(i)
                res[j] -= sizes[i]
            if ok:
                bins = others
                changed = True
                break
            if time.time() >= deadline:
                break
    return bins


def _m78_exact(sizes, cap, best_bins, deadline):
    """branch and bound; returns (bins, proven_optimal)"""
    n = len(sizes)
    order = sorted(range(n), key=lambda i: -sizes[i])
    s_ord = [sizes[i] for i in order]
    suffix = [0] * (n + 1)
    for k in range(n - 1, -1, -1):
        suffix[k] = suffix[k + 1] + s_ord[k]
    best = {"n": len(best_bins), "bins": [list(b_) for b_ in best_bins]}
    lb = _m78_lb(sizes, cap)
    res, members = [], []
    last_bin_for_size = {}
    state = {"nodes": 0, "timeout": False}

    def dfs(k):
        if best["n"] <= lb:
            return
        state["nodes"] += 1
        if state["nodes"] % 2000 == 0 and time.time() > deadline:
            state["timeout"] = True
        if state["timeout"]:
            return
        if k == n:
            if len(res) < best["n"]:
                best["n"] = len(res)
                best["bins"] = [[order[i] for i in m_] for m_ in members]
            return
        free = sum(res)
        if len(res) + max(0, -(-(suffix[k] - free) // cap)) >= best["n"]:
            return
        s_ = s_ord[k]
        start_j = last_bin_for_size.get((s_, k - 1), 0) if k > 0 and s_ord[k - 1] == s_ else 0
        tried = set()
        for j in range(start_j, len(res)):
            r_ = res[j]
            if r_ >= s_ and r_ not in tried:
                tried.add(r_)
                res[j] -= s_
                members[j].append(k)
                last_bin_for_size[(s_, k)] = j
                dfs(k + 1)
                members[j].pop()
                res[j] += s_
                if state["timeout"] or best["n"] <= lb:
                    return
        if len(res) + 1 < best["n"]:
            res.append(cap - s_)
            members.append([k])
            last_bin_for_size[(s_, k)] = len(res) - 1
            dfs(k + 1)
            res.pop()
            members.pop()

    import sys as _sys
    old = _sys.getrecursionlimit()
    try:
        _sys.setrecursionlimit(max(old, n + 200))
        dfs(0)
    finally:
        _sys.setrecursionlimit(old)
    return best["bins"], (not state["timeout"]) or best["n"] <= lb


def _m78_fill_remnant(items, sizes, cap):
    """subset of items that fills one remnant best (exact for small sets, else best fit) -> list of indices"""
    cand = [i for i in items if sizes[i] <= cap]
    if not cand:
        return []
    if len(cand) <= 40 and cap <= 200000:
        reach = {0: None}
        for i in sorted(cand, key=lambda i_: -sizes[i_]):
            for v in list(reach.keys()):
                w = v + sizes[i]
                if w <= cap and w not in reach:
                    reach[w] = (v, i)
            if cap in reach:
                break
        v = max(reach)
        out = []
        while reach[v] is not None:
            v, i = reach[v]
            out.append(i)
        return out
    out, r_ = [], cap
    for i in sorted(cand, key=lambda i_: -sizes[i_]):
        if sizes[i] <= r_:
            out.append(i)
            r_ -= sizes[i]
    return out


def _m78_pack(pieces, stab, fuge, limit=None, reste=None):
    """pieces [(len, label)] -> {bars: [{teile, rest, laenge, reststueck}], lb, optimal}"""
    limit = M78_PACK_TIME if limit is None else limit
    deadline = time.time() + limit
    sc = 10.0
    sizes = [int(round((ln + fuge) * sc)) for ln, _ in pieces]
    cap = int(round((stab + fuge) * sc))
    remaining = list(range(len(pieces)))
    bars = []
    for rl in sorted([float(r_) for r_ in (reste or []) if float(r_ or 0) > 0], reverse=True):
        rcap = int(round((rl + fuge) * sc))
        pick = _m78_fill_remnant(remaining, sizes, rcap)
        if pick:
            bars.append((rl, pick, True))
            remaining = [i for i in remaining if i not in set(pick)]
    sub = [sizes[i] for i in remaining]
    lb = _m78_lb(sub, cap)
    optimal = True
    if remaining:
        idx = list(range(len(sub)))
        desc = sorted(idx, key=lambda i: -sub[i])
        cands = [_m78_fit(desc, sub, cap), _m78_fit(desc, sub, cap, best_fit=True)]
        best = min(cands, key=len)
        optimal = len(best) <= lb
        if not optimal and limit > 0:
            if len(sub) <= 120:
                b2, proven = _m78_exact(sub, cap, best, deadline)
                best, optimal = b2, proven
            if not optimal and time.time() < deadline:
                best = _m78_improve(best, sub, cap, deadline)
                optimal = len(best) <= lb
        for b_ in best:
            bars.append((stab, [remaining[i] for i in b_], False))
    out = []
    for ln_bar, ids, is_rest in bars:
        teile = sorted([pieces[i] for i in ids], key=lambda p_: -p_[0])
        used = sum(p_[0] for p_ in teile) + fuge * max(0, len(teile) - 1)
        raw = ln_bar - used
        rest = round(raw - fuge, 1) if raw > fuge + 1e-6 else 0.0
        out.append({"teile": teile, "rest": rest, "laenge": ln_bar, "reststueck": is_rest})
    out.sort(key=lambda b_: (not b_["reststueck"], b_["rest"]))
    return {"bars": out, "lb": lb + sum(1 for b_ in out if b_["reststueck"]), "lb_neu": lb, "optimal": optimal}


def m78_reste(profil=None):
    r = m78_settings().get("reste") or {}
    return r.get(profil, []) if profil is not None else r


def _m78_reste_save(h, d):
    cur_ = m78_settings()
    reste = dict(cur_.get("reste") or {})
    vals = []
    toks = []
    for t in re.split(r"[;\s/]+", str(d.get("reste") or "")):
        # "1200,800" is a list of whole millimetres, "1200,5" a decimal number
        toks += t.split(",") if re.fullmatch(r"\d{3,}(,\d{3,})+", t) else [t]
    for t in toks:
        v = _m78_num(t) if t.strip() else None
        if v and v > 0:
            vals.append(round(v, 1))
    if vals:
        reste[str(d.get("profil") or "")] = sorted(vals, reverse=True)
    else:
        reste.pop(str(d.get("profil") or ""), None)
    cur_["reste"] = reste
    set_setting("m78", cur_)
    return h._send(200, {"ok": True, "reste": reste.get(str(d.get("profil") or ""), [])})


HOOK_POST["/api/m78/reste"] = _m78_reste_save


def m78_zuschnitt(bid, stab=None, fuge=None, reste=True):
    b = q("SELECT * FROM m78_bom WHERE id=?", (int(bid),), one=True)
    if not b:
        raise ValueError("Stückliste nicht gefunden.")
    st = m78_settings()
    stab = float(_m78_num(stab) or st["stablaenge"]) if stab not in (None, "") else float(st["stablaenge"])
    fuge = float(_m78_num(fuge) if fuge not in (None, "") and _m78_num(fuge) is not None else st["schnittfuge"])
    # v2.1.0: same limits as the settings - a negative kerf or bar length would overfill bars
    if not (0 <= fuge <= 50):
        raise ValueError("Schnittfuge muss zwischen 0 und 50 mm liegen.")
    if stab <= 0:
        raise ValueError("Stablänge muss größer als 0 sein.")
    prof = {}
    for r in json.loads(b["rows"] or "[]"):
        if not r.get("laenge"):
            continue
        # profile name: column Abmessung, else the part name without a trailing copy of its own length
        # (e.g. "Rohr 40x40x3 - 1500 mm" -> "Rohr 40x40x3"; "Rohr 40x40x3" stays as it is)
        ln_txt = str(int(round(r["laenge"])))
        nm0 = r.get("name") or ""
        nm1 = re.sub(r"\s*(?:[-–,/]|\bL\s*=?)\s*" + re.escape(ln_txt) + r"(?:[.,]0+)?\s*(?:mm)?\s*$", "", nm0).strip()
        name = r.get("abmessung") or nm1 or nm0 or "Profil"
        k = (name, r.get("material") or "")
        prof.setdefault(k, []).append(r)
    out = []
    for (name, mat), rows in sorted(prof.items(), key=lambda kv: kv[0]):
        teile = []
        pieces = []
        for r in sorted(rows, key=lambda r: -r["laenge"]):
            n = int(round(float(r.get("qty") or 0)))
            teile.append({"laenge": r["laenge"], "anzahl": n, "pos": r.get("pos") or "", "nr": r.get("nr") or "", "name": r.get("name") or ""})
            pieces += [(r["laenge"], r.get("pos") or r.get("nr") or "")] * max(n, 0)
        ueber = [p for p in pieces if p[0] > stab]
        rl = m78_reste(name) if reste else []
        pk = _m78_pack([p for p in pieces if p[0] <= stab], stab, fuge, reste=rl)
        bars = pk["bars"]
        neu = [b_ for b_ in bars if not b_["reststueck"]]
        gesamt = round(sum(p[0] for p in pieces) / 1000.0, 3)
        rest = round(sum(b_["rest"] for b_ in bars) / 1000.0, 3)
        mat_mm = sum(b_["laenge"] for b_ in bars)
        teil_mm = sum(t[0] for b_ in bars for t in b_["teile"])
        lb = _m78_lb([int(round((p[0] + fuge) * 10)) for p in pieces if p[0] <= stab], int(round((stab + fuge) * 10)))
        out.append({"profil": name, "material": mat, "teile": teile, "stueck": len(pieces), "gesamt_m": gesamt, "staebe": len(neu),
                    "reststuecke": len(bars) - len(neu), "reste_lager": rl,
                    "min_staebe": pk["lb_neu"], "min_ohne_reste": lb, "optimal": pk["optimal"],
                    "rest_m": rest, "verschnitt_pct": round(100.0 * (mat_mm - teil_mm) / mat_mm, 1) if mat_mm else 0.0,
                    "ueberlaenge": [{"laenge": p[0], "pos": p[1]} for p in ueber],
                    "plan": [{"teile": [{"laenge": t[0], "pos": t[1]} for t in b_["teile"]], "rest": b_["rest"], "laenge": b_["laenge"],
                              "reststueck": b_["reststueck"]} for b_ in bars]})
    p = q("SELECT nr, name FROM projects WHERE id=?", (b["project_id"],), one=True) or {"nr": "", "name": ""}
    return {"bom": b["name"], "projekt": p, "stablaenge": stab, "schnittfuge": fuge, "profile": out}


def _m78_pdf(bid, was):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    ink, gray, acc, soft = colors.HexColor("#1e1a2b"), colors.HexColor("#6c6880"), colors.HexColor("#3d6f8f"), colors.HexColor("#eef3f6")
    N = ParagraphStyle("n", fontName=FONT_R(), fontSize=9, leading=12, textColor=ink)
    NS = ParagraphStyle("ns", fontName=FONT_R(), fontSize=7.5, leading=9.5, textColor=gray)
    C = ParagraphStyle("c", fontName=FONT_R(), fontSize=8, leading=10, textColor=ink)
    K = ParagraphStyle("k", fontName=FONT_B(), fontSize=7.5, leading=9, textColor=acc)
    H1 = ParagraphStyle("h1", fontName=FONT_B(), fontSize=17, leading=21, textColor=ink)
    H2 = ParagraphStyle("h2", fontName=FONT_B(), fontSize=11, leading=14, textColor=ink, spaceBefore=10, spaceAfter=4)
    e = lambda t: (str(t if t is not None else "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    tsb = [("FONT", (0, 0), (-1, 0), FONT_B(), 7.5), ("TEXTCOLOR", (0, 0), (-1, 0), gray), ("LINEBELOW", (0, 0), (-1, 0), 0.6, ink),
           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
           ("FONT", (0, 1), (-1, -1), FONT_R(), 8), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    buf = io.BytesIO()
    if was == "bestell":
        d = m78_bestell(bid)
        title = f"Bestellliste {d['projekt']['nr']}"
        el = [Paragraph("BESTELLLISTE", K), Paragraph(e(f"{d['projekt']['nr']} {d['projekt']['name']}"), H1),
              Paragraph(e(f"Stückliste {d['bom']} · fehlendes Material nach Lagerabgleich · Stand {de_date(today())}"), NS), Spacer(1, 6)]
        if not d["gruppen"]:
            el.append(Paragraph("Es fehlt kein Material - alles ist im Lager verfügbar oder bereits entnommen.", N))
        for g in d["gruppen"]:
            rows = [["Art.-Nr.", "Bestell-Nr.", "Bezeichnung", "Menge", "Einheit", "EK", "Summe"]]
            for r in g["rows"]:
                rows.append([Paragraph(e(r["nr"]), C), Paragraph(e(r["bestellnr"]), C),
                             Paragraph(e(r["name"] + (f" ({r['abmessung']})" if r["abmessung"] else "")), C),
                             num_de(r["menge"], 2), r["einheit"], money(r["ek"]) if r["ek"] else "", money(r["summe"]) if r["summe"] else ""])
            t = Table(rows, colWidths=[22 * mm, 22 * mm, 64 * mm, 16 * mm, 14 * mm, 18 * mm, 18 * mm], repeatRows=1)
            t.setStyle(TableStyle(tsb + [("ALIGN", (3, 0), (3, -1), "RIGHT"), ("ALIGN", (5, 0), (6, -1), "RIGHT")]))
            el += [KeepTogether([Paragraph(e(g["lieferant"]) + (f" · {money(g['summe'])}" if g["summe"] else ""), H2), t])]
    else:
        d = m78_zuschnitt(bid)
        title = f"Zuschnittliste {d['projekt']['nr']}"
        el = [Paragraph("ZUSCHNITTLISTE", K), Paragraph(e(f"{d['projekt']['nr']} {d['projekt']['name']}"), H1),
              Paragraph(e(f"Stückliste {d['bom']} · Stablänge {num_de(d['stablaenge'], 0)} mm · Schnittfuge {num_de(d['schnittfuge'], 1)} mm · "
                          f"Stand {de_date(today())}"), NS), Spacer(1, 6)]
        if not d["profile"]:
            el.append(Paragraph("Die Stückliste enthält keine Spalte „Länge“ - keine Zuschnitte.", N))
        for pr in d["profile"]:
            rows = [["Pos.", "Teil", "Länge mm", "Anzahl"]] + [[e(t["pos"]), Paragraph(e(t["nr"] or t["name"]), C), num_de(t["laenge"], 1), str(t["anzahl"])] for t in pr["teile"]]
            t = Table(rows, colWidths=[18 * mm, 96 * mm, 30 * mm, 30 * mm], repeatRows=1)
            t.setStyle(TableStyle(tsb + [("ALIGN", (2, 0), (3, -1), "RIGHT")]))
            plan = [["Stab", "Teile (mm)", "Rest mm"]] + [[(f"R {num_de(b_['laenge'], 0)}" if b_.get("reststueck") else str(i + 1 - pr.get("reststuecke", 0))),
                                                           Paragraph(" + ".join(num_de(p["laenge"], 0) + (f" [{e(p['pos'])}]" if p["pos"] else "") for p in b_["teile"]), C),
                                                           num_de(b_["rest"], 0)] for i, b_ in enumerate(pr["plan"])]
            t2 = Table(plan, colWidths=[14 * mm, 136 * mm, 24 * mm], repeatRows=1)
            t2.setStyle(TableStyle(tsb + [("ALIGN", (2, 0), (2, -1), "RIGHT")]))
            head = Paragraph(e(f"{pr['profil']}{' · ' + pr['material'] if pr['material'] else ''}"), H2)
            info = Paragraph(e(f"{pr['stueck']} Teile · {num_de(pr['gesamt_m'], 2)} m gesamt · {pr['staebe']} Stäbe à {num_de(d['stablaenge'], 0)} mm · "
                               f"Rest {num_de(pr['rest_m'], 2)} m · Verschnitt {num_de(pr['verschnitt_pct'], 1)} % · "
                               f"Minimum {pr.get('min_staebe', pr['staebe'])} Stäbe{' (optimal)' if pr.get('optimal') else ''}"
                               + (f" · {pr['reststuecke']} Reststück(e) aus dem Lager (R)" if pr.get("reststuecke") else "")), NS)
            el += [KeepTogether([head, info, Spacer(1, 3), t]), Spacer(1, 4), t2]
            if pr["ueberlaenge"]:
                el.append(Paragraph(e("Überlänge (länger als ein Stab, gesondert bestellen): " +
                                      ", ".join(f"{num_de(u['laenge'], 0)} mm" + (f" [{u['pos']}]" if u["pos"] else "") for u in pr["ueberlaenge"])), N))
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=16 * mm,
                            title=title, author="T. Pfeiffer", creator=f"{APP_NAME} v{APP_VERSION}")

    def onpage(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(gray)
        cv.drawString(18 * mm, 9 * mm, f"{title} · T. Pfeiffer")
        cv.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Seite {dc.page}")
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    return buf.getvalue(), title


def m78_pdf(bid, was, open_=True):
    b = q("SELECT * FROM m78_bom WHERE id=?", (int(bid),), one=True)
    if not b:
        raise ValueError("Stückliste nicht gefunden.")
    data, title = _m78_pdf(bid, "bestell" if was == "bestell" else "zuschnitt")
    p = q("SELECT * FROM projects WHERE id=?", (b["project_id"],), one=True)
    base = ensure_project_folders(p)
    fp = os.path.join(base, safe_name(f"{title.replace(' ', '_')}_{today()}.pdf"))
    write_file(fp, data)
    rel = os.path.relpath(fp, DATA_DIR)
    if q("SELECT id FROM project_files WHERE path=?", (rel,), one=True):
        x("UPDATE project_files SET size=?, added=? WHERE path=?", (len(data), now_iso(), rel))
    else:
        x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
          (p["id"], "", "Stückliste", os.path.basename(fp), rel, len(data), title, now_iso()))
    if open_ and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return {"ok": True, "path": fp, "rel": rel, "name": os.path.basename(fp)}


# ---------------------------------------------------------------------------
# project data, routes, export, boot, selftest
# ---------------------------------------------------------------------------
def m78_project(pid):
    pid = int(pid)
    boms = []
    for b in q("SELECT * FROM m78_bom WHERE project_id=? ORDER BY id", (pid,)):
        chk = m78_check(b["id"])
        ch = q("SELECT * FROM m78_change WHERE bom_id=? ORDER BY id DESC LIMIT 8", (b["id"],))
        for c in ch:
            c["details"] = json.loads(c["details"] or "{}")
        fp = _m78_abs(b)
        boms.append({"id": b["id"], "name": b["name"], "path": fp, "extern": bool(b["extern"]), "auto": bool(b["auto"]),
                     "gelesen": b["gelesen"] or "", "fehler": b["fehler"] or "", "kalk_id": b["kalk_id"], "vorhanden": os.path.isfile(fp),
                     "rows": chk["rows"], "summe": chk["summe"], "lager": chk["lager"], "changes": ch,
                     "ungesehen": sum(1 for c in ch if not c["gesehen"]), "hat_laenge": any(r.get("laenge") for r in chk["rows"])})
    kalks = m41_kalk_list(pid) if "m41_kalk_list" in globals() else []
    files = q("SELECT id, name, path FROM project_files WHERE project_id=? AND (kind='Stückliste' OR lower(name) LIKE '%.csv' OR "
              "lower(name) LIKE '%.xlsx' OR lower(name) LIKE '%.xls' OR lower(name) LIKE '%.txt') ORDER BY added DESC", (pid,))
    arts = q("SELECT id, nr, name, einheit, bestand FROM m42_artikel WHERE aktiv=1 ORDER BY nr, name") if _m78_lager_ok() else []
    return {"boms": boms, "kalks": kalks, "files": files, "artikel": arts, "settings": m78_settings()}


def _m78_seen(d):
    x("UPDATE m78_change SET gesehen=1 WHERE bom_id=?", (int(d["bom_id"]),))
    return {"ok": True}


def _m78_settings_save(h, d):
    cur_ = m78_settings()
    for k in ("stablaenge", "schnittfuge"):
        if k in d and str(d[k]).strip() != "":
            v = _m78_num(d[k])
            if v is None or v < 0 or (k == "stablaenge" and v < 100):
                raise ValueError("Ungültiger Wert für " + ("Stablänge" if k == "stablaenge" else "Schnittfuge") + ".")
            cur_[k] = v
    set_setting("m78", cur_)
    return h._send(200, {"ok": True, "settings": cur_})


HOOK_GET["/api/m78/project"] = lambda h, qs: h._send(200, m78_project(qs["project_id"]))
HOOK_GET["/api/m78/zuschnitt"] = lambda h, qs: h._send(200, m78_zuschnitt(int(qs["bom_id"]), qs.get("stab"), qs.get("fuge")))
HOOK_GET["/api/m78/bestell"] = lambda h, qs: h._send(200, m78_bestell(int(qs["bom_id"])))
HOOK_POST["/api/m78/link"] = lambda h, d: h._send(200, m78_link(d))
HOOK_POST["/api/m78/update"] = lambda h, d: h._send(200, m78_update_bom(d))
HOOK_POST["/api/m78/unlink"] = lambda h, d: h._send(200, m78_unlink(d.get("ids") or [d.get("id")]))
HOOK_POST["/api/m78/reload"] = lambda h, d: h._send(200, m78_read(int(d["id"]), force=True))
HOOK_POST["/api/m78/map"] = lambda h, d: h._send(200, m78_map(d))
HOOK_POST["/api/m78/reserve"] = lambda h, d: h._send(200, m78_reserve(d))
HOOK_POST["/api/m78/entnahme"] = lambda h, d: h._send(200, m78_entnahme(d))
HOOK_POST["/api/m78/seen"] = lambda h, d: h._send(200, _m78_seen(d))
HOOK_POST["/api/m78/mail"] = lambda h, d: h._send(200, m78_bestell_text(int(d["bom_id"])))
HOOK_POST["/api/m78/pdf"] = lambda h, d: h._send(200, m78_pdf(int(d["bom_id"]), d.get("was") or "bestell"))
HOOK_POST["/api/m78/settings"] = _m78_settings_save


def _m78_boot(b):
    try:
        rows = q("SELECT c.bom_id, b.project_id, b.name, p.nr, p.name pname FROM m78_change c JOIN m78_bom b ON b.id=c.bom_id "
                 "LEFT JOIN projects p ON p.id=b.project_id WHERE c.gesehen=0 GROUP BY c.bom_id")
        b["m78"] = {"geaendert": len(rows), "liste": rows[:6]}
    except Exception:
        b["m78"] = {"geaendert": 0, "liste": []}


HOOK_BOOT.append(_m78_boot)


def _m78_ex_bestell(p):
    d = m78_bestell(int(p["bom_id"]))
    rows = []
    for g in d["gruppen"]:
        for r in g["rows"]:
            rows.append([g["lieferant"], r["nr"], r["bestellnr"], r["name"], r["abmessung"], r["menge"], r["einheit"], r["ek"], r["summe"]])
    return [_sh("Bestellliste", [("Lieferant", "t", 22), ("Art.-Nr.", "t", 14), ("Bestell-Nr.", "t", 14), ("Bezeichnung", "t", 34),
                                 ("Abmessung", "t", 16), ("Menge", "n", 9), ("Einheit", "t", 7), ("EK", "m", 11), ("Summe", "m", 12)],
                rows, f"{d['projekt']['nr']} {d['projekt']['name']} · Stückliste {d['bom']}")]


def _m78_ex_zuschnitt(p):
    d = m78_zuschnitt(int(p["bom_id"]))
    teile, plan = [], []
    for pr in d["profile"]:
        for t in pr["teile"]:
            teile.append([pr["profil"], pr["material"], t["pos"], t["nr"] or t["name"], t["laenge"], t["anzahl"]])
        for i, b_ in enumerate(pr["plan"], 1):
            plan.append([pr["profil"], (f"R {int(round(b_['laenge']))}" if b_.get("reststueck") else str(i - pr.get("reststuecke", 0))),
                         " + ".join(f"{int(round(t_['laenge']))}" for t_ in b_["teile"]), b_["rest"]])
    sub = f"{d['projekt']['nr']} {d['projekt']['name']} · Stablänge {int(d['stablaenge'])} mm · Schnittfuge {d['schnittfuge']} mm"
    return [_sh("Zuschnitte", [("Profil", "t", 24), ("Material", "t", 12), ("Pos.", "t", 8), ("Teil", "t", 28), ("Länge mm", "n", 10),
                               ("Anzahl", "n", 8)], teile, sub, total=False),
            _sh("Stabaufteilung", [("Profil", "t", 24), ("Stab", "t", 8), ("Teile (mm)", "t", 60), ("Rest mm", "n", 10)], plan, "", total=False)]


EXPORTS["m78_bestell"] = ("Bestellliste", _m78_ex_bestell)
EXPORTS["m78_zuschnitt"] = ("Zuschnittliste", _m78_ex_zuschnitt)


def _m78_selftest():
    err = []
    pid = bid = aid = None
    tmpf = os.path.join(DATA_DIR, "_tmp_m78_selftest.csv")
    try:
        pid = x("INSERT INTO projects (nr, name, bereich, status, start, folders, created, updated) VALUES (?,?,?,?,?,?,?,?)",
                ("_ST78", "Selbsttest Stückliste", "Metallbau", "aktiv", today(), "[]", now_iso(), now_iso()))
        csv1 = ("Pos.;Bauteilnummer;Menge;Beschreibung;Material;Länge;Lieferant\n"
                "1;_ST78-ROHR;4;Rohr 40x40x3;S235JR;1500 mm;Stahl Meier\n"
                "2;_ST78-ROHR;2;Rohr 40x40x3;S235JR;2500 mm;Stahl Meier\n"
                "3;_ST78-SCHR;20;Schraube M10x30;8.8;;\n")
        open(tmpf, "w", encoding="utf-8").write(csv1)
        r = m78_link({"project_id": pid, "path": tmpf})
        bid = r["id"]
        b = q("SELECT rows FROM m78_bom WHERE id=?", (bid,), one=True)
        rows = json.loads(b["rows"])
        if len(rows) != 3 or abs(rows[0]["laenge"] - 1500) > 0.1:
            err.append(f"m78: Stückliste falsch gelesen ({len(rows)} Zeilen)")
        z = m78_zuschnitt(bid, 6000, 3)
        if not z["profile"] or z["profile"][0]["stueck"] != 6 or z["profile"][0]["staebe"] != 2:   # v2.1.0: 2x (2500+1500+1500), before 3
            err.append(f"m78: Zuschnitt falsch ({z['profile'][0]['staebe'] if z['profile'] else '-'} Stäbe)")
        if _m78_lager_ok():
            aid = m42_save({"nr": "_ST78-SCHR", "name": "Selbsttest Schraube", "kategorie": "Befestigung", "einheit": "Stk", "ek": 0.1, "bestand": 12})
            c = {r_["nr"]: r_ for r_ in m78_check(bid)["rows"]}
            s_ = c.get("_ST78-SCHR")
            if not s_ or s_["status"] != "teilweise" or abs(s_["fehlt"] - 8) > 1e-6:
                err.append(f"m78: Lagerabgleich falsch ({s_ and s_['status']} / {s_ and s_['fehlt']})")
            bs = m78_bestell(bid)
            if not any(g["lieferant"] == "Stahl Meier" for g in bs["gruppen"]):
                err.append("m78: Bestellliste ohne Lieferant-Gruppe")
            m78_reserve({"bom_id": bid})
            m78_entnahme({"bom_id": bid, "keys": [s_["key"]], "als_eintrag": False})
            if abs(q("SELECT bestand FROM m42_artikel WHERE id=?", (aid,), one=True)["bestand"]) > 1e-6:
                err.append("m78: Entnahme hat den Bestand nicht gebucht")
        time.sleep(0.02)
        open(tmpf, "w", encoding="utf-8").write(csv1.replace(";4;Rohr", ";5;Rohr") + "4;_ST78-BLECH;1;Blech 3 mm;S235JR;;\n")
        os.utime(tmpf, (time.time() + 5, time.time() + 5))
        r2 = m78_read(bid)
        if not r2.get("changed") or r2.get("neu") != 1 or r2.get("geaendert") != 1:
            err.append(f"m78: Änderung nicht erkannt ({r2})")
        if not _m78_pdf(bid, "zuschnitt")[0].startswith(b"%PDF") or not _m78_pdf(bid, "bestell")[0].startswith(b"%PDF"):
            err.append("m78: PDF fehlerhaft")
    except Exception as e:
        err.append(f"m78 Ausnahme: {e}")
    finally:
        try:
            if aid:
                x("DELETE FROM m42_buchung WHERE artikel_id=?", (aid,))
                x("DELETE FROM m42_artikel WHERE id=?", (aid,))
            if bid:
                x("DELETE FROM m78_res WHERE bom_id=?", (bid,))
                x("DELETE FROM m78_change WHERE bom_id=?", (bid,))
                x("DELETE FROM m78_bom WHERE id=?", (bid,))
            x("DELETE FROM m78_map WHERE schluessel LIKE '_st78%'")
            if pid:
                x("DELETE FROM project_entries WHERE project_id=?", (pid,))
                x("DELETE FROM project_files WHERE project_id=?", (pid,))
                x("DELETE FROM projects WHERE id=?", (pid,))
            if os.path.exists(tmpf):
                os.remove(tmpf)
        except Exception:
            pass
    return err


HOOK_SELFTEST.append(_m78_selftest)


def _m78_selftest_pack():
    """v2.1.0: cutting optimisation - one bar less than first fit, kerf rule, remnants"""
    err = []
    try:
        L = [3800, 3590, 3520, 2930, 2880, 2530, 1910, 1750, 1540, 1530, 1350, 950, 680]
        pcs = [(v, "") for v in L]
        old_n = len(_m78_fit(sorted(range(len(L)), key=lambda i: -L[i]), [int((v + 3) * 10) for v in L], 60030))
        r = _m78_pack(pcs, 6000, 3)
        if len(r["bars"]) != 5 or old_n != 6:
            err.append(f"m78: Zuschnitt-Optimierung {len(r['bars'])} Stäbe (erwartet 5, First Fit {old_n})")
        for b_ in r["bars"]:
            if sum(p_[0] for p_ in b_["teile"]) + 3 * (len(b_["teile"]) - 1) > 6000 + 1e-6:
                err.append("m78: Stab überfüllt")
        if sorted(p_[0] for b_ in r["bars"] for p_ in b_["teile"]) != sorted(L):
            err.append("m78: Teile gehen bei der Optimierung verloren")
        # kerf: 2 x 3000 fit exactly without kerf, not with kerf
        if len(_m78_pack([(3000, ""), (3000, "")], 6000, 0)["bars"]) != 1 or len(_m78_pack([(3000, ""), (3000, "")], 6000, 3)["bars"]) != 2:
            err.append("m78: Schnittfuge falsch gerechnet")
        # a piece filling the bar exactly needs no kerf behind it
        if len(_m78_pack([(6000, "")], 6000, 3)["bars"]) != 1 or _m78_pack([(6000, "")], 6000, 3)["bars"][0]["rest"] != 0:
            err.append("m78: Teil in voller Stablänge abgelehnt")
        rr = _m78_pack([(2500, ""), (2500, ""), (1500, ""), (1500, ""), (1000, "")], 6000, 3, reste=[2600, 1600])
        if sum(1 for b_ in rr["bars"] if b_["reststueck"]) != 2 or sum(1 for b_ in rr["bars"] if not b_["reststueck"]) != 1:
            err.append("m78: Reststücke nicht zuerst verplant")
        t0 = time.time()
        _m78_pack([(450 + (i * 377) % 2600, "") for i in range(80)], 6000, 3)
        if time.time() - t0 > 2.5:
            err.append("m78: Zuschnitt-Optimierung zu langsam")
    except Exception as e:
        err.append(f"m78 Zuschnitt Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m78_selftest_pack)
