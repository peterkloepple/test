# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m85_felder (v2.0.19)
# Eigene Felder fuer Kunden, Projekte, Bausteine, Belege, Rechnungen/Angebote und Lagerartikel.
#  - Definition (Name, Typ Text/Zahl/Datum/Auswahl/Ja-Nein/Link, Pflicht, Auswahlwerte, Reihenfolge,
#    als Spalte in Listen zeigen) in Einstellungen > Eigene Felder
#  - Werte in m85_wert (objekt, objekt_id, feld_id, wert)
#  - Platzhalter {{Feld:Name}} bzw. [Feld:Name] in Rechnungstexten, Mailtexten und Briefen
#  - Exporte (Excel/PDF) bekommen die Felder als zusaetzliche Spalten
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M85_VERSION = "1.0.0"
M85_OBJ = {"kunde": ("Kunden", "customers"), "projekt": ("Projekte", "projects"), "baustein": ("Bausteine", "articles"),
           "beleg": ("Belege", "belege"), "rechnung": ("Rechnungen & Angebote", "invoices"), "lager": ("Lagerartikel", "m42_artikel")}
M85_TYPEN = {"text": "Text", "zahl": "Zahl", "datum": "Datum", "auswahl": "Auswahl", "janein": "Ja/Nein", "link": "Link / Pfad"}
M85_PH_RE = re.compile(r"\{\{\s*Feld\s*:\s*([^}]{1,60}?)\s*\}\}|\[\s*Feld\s*:\s*([^\]]{1,60}?)\s*\]", re.I)


def _m85_schema():
    x("CREATE TABLE IF NOT EXISTS m85_feld (id INTEGER PRIMARY KEY, objekt TEXT, name TEXT, typ TEXT DEFAULT 'text', "
      "pflicht INTEGER DEFAULT 0, auswahl TEXT, sort INTEGER DEFAULT 0, spalte INTEGER DEFAULT 0, hinweis TEXT, "
      "aktiv INTEGER DEFAULT 1, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS m85_wert (objekt TEXT, objekt_id INTEGER, feld_id INTEGER, wert TEXT, "
      "PRIMARY KEY (objekt, objekt_id, feld_id))")
    try:
        x("CREATE INDEX IF NOT EXISTS m85_w_feld ON m85_wert(feld_id)")
    except Exception:
        pass
    # values of deleted objects are removed at program start
    for k, (_l, tbl) in M85_OBJ.items():
        try:
            x(f"DELETE FROM m85_wert WHERE objekt=? AND objekt_id NOT IN (SELECT id FROM {tbl})", (k,))
        except Exception:
            pass   # table (e.g. m42_artikel) not there yet


HOOK_SCHEMA.append(_m85_schema)


# v2.0.19 (R4): values of a deleted object go right away (in the same user action, so "Rueckgaengig"
# brings them back) - before, a new object with the re-used id inherited them until the next start
def _m85_cleaner(obj, tbl):
    def fn():
        x(f"DELETE FROM m85_wert WHERE objekt=? AND objekt_id NOT IN (SELECT id FROM {tbl})", (obj,))
    return fn


if "M83_NACH_LOESCHEN" in globals():
    for _k, (_l, _t) in M85_OBJ.items():
        M83_NACH_LOESCHEN.setdefault(_t, []).append(_m85_cleaner(_k, _t))


def _m85_norm(s):
    return re.sub(r"\s+", "", str(s or "").strip().lower())


def m85_felder(obj=None, alle=False):
    sql = "SELECT * FROM m85_feld" + (" WHERE objekt=?" if obj else "") + " ORDER BY objekt, sort, id"
    rows = q(sql, (obj,) if obj else ())
    for r in rows:
        try:
            r["auswahl"] = json.loads(r["auswahl"] or "[]")
        except Exception:
            r["auswahl"] = []
    return rows if alle else [r for r in rows if r["aktiv"]]


def m85_werte(obj, oid):
    return {r["feld_id"]: r["wert"] for r in q("SELECT feld_id, wert FROM m85_wert WHERE objekt=? AND objekt_id=?", (obj, int(oid)))}


def m85_by_name(obj, oid):
    """{normalized field name: display value} for one object"""
    if not oid:
        return {}
    out = {}
    w = m85_werte(obj, oid)
    for f in m85_felder(obj):
        v = w.get(f["id"])
        if v in (None, ""):
            continue
        out[_m85_norm(f["name"])] = m85_display(f, v)
    return out


def m85_display(f, v):
    if v in (None, ""):
        return ""
    t = f.get("typ")
    if t == "janein":
        return "ja" if str(v) in ("1", "true", "ja") else "nein"
    if t == "datum":
        return de_date(v)
    if t == "zahl":
        try:
            fv = float(v)
            return num_de(fv, 2) if abs(fv - round(fv)) > 1e-9 else str(int(round(fv)))
        except Exception:
            return str(v)
    return str(v)


def _m85_check(f, v):
    """validate + normalize one value, returns stored string or raises"""
    v = "" if v is None else str(v).strip()
    if v == "":
        if f["pflicht"]:
            raise ValueError(f"Pflichtfeld „{f['name']}“ ist leer.")
        return ""
    t = f["typ"]
    if t == "zahl":
        try:
            # v2.0.19 (R4): "1.234" is German for 1234 (the list/dialog shows 1234 that way and sends it back);
            # parse_amount knows "1.234" / "1.234,5" / "12,5" / "12.5" - only plain integers are kept as typed
            return v if re.fullmatch(r"-?\d+", v) else repr(float(parse_amount(v)))
        except Exception:
            raise ValueError(f"„{f['name']}“: „{v}“ ist keine Zahl.")
    if t == "datum":
        iso = v[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", v) else iso_from_de(v)
        try:
            datetime.date.fromisoformat(iso)
        except Exception:
            raise ValueError(f"„{f['name']}“: „{v}“ ist kein Datum.")
        return iso
    if t == "janein":
        return "1" if v.lower() in ("1", "true", "ja", "on", "yes") else "0"
    if t == "auswahl":
        opts = f.get("auswahl") or []
        if opts and v not in opts:
            raise ValueError(f"„{f['name']}“: „{v}“ ist kein erlaubter Wert ({', '.join(opts)}).")
        return v
    return v[:2000]


def m85_save_werte(obj, oid, werte, partial=False):
    if obj not in M85_OBJ:
        raise ValueError("Unbekannter Bereich.")
    oid = int(oid)
    fs = {f["id"]: f for f in m85_felder(obj)}
    werte = {int(k): v for k, v in (werte or {}).items() if str(k).lstrip("-").isdigit()}
    errs, clean = [], {}
    for fid, f in fs.items():
        if fid not in werte:
            if partial:
                continue
            werte[fid] = (m85_werte(obj, oid).get(fid) or "")
        try:
            clean[fid] = _m85_check(f, werte[fid])
        except ValueError as e:
            errs.append(str(e))
    if errs:
        raise ValueError(" ".join(errs))
    for fid, v in clean.items():
        if v == "":
            x("DELETE FROM m85_wert WHERE objekt=? AND objekt_id=? AND feld_id=?", (obj, oid, fid))
        else:
            x("INSERT OR REPLACE INTO m85_wert (objekt, objekt_id, feld_id, wert) VALUES (?,?,?,?)", (obj, oid, fid, v))
    return {"ok": True, "werte": m85_werte(obj, oid)}


def m85_set(obj, oid, name, wert):
    """set one value by field name (used by the rules module m86)"""
    f = next((f for f in m85_felder(obj) if _m85_norm(f["name"]) == _m85_norm(name)), None)
    if not f:
        raise ValueError(f"Eigenes Feld „{name}“ gibt es bei {M85_OBJ.get(obj, (obj,))[0]} nicht.")
    return m85_save_werte(obj, oid, {f["id"]: wert}, partial=True)


def m85_feld_save(d):
    obj = d.get("objekt")
    if obj not in M85_OBJ:
        raise ValueError("Bitte einen Bereich wählen.")
    name = (d.get("name") or "").strip()
    if not name:
        raise ValueError("Bitte einen Namen für das Feld angeben.")
    if re.search(r"[{}\[\]]", name):
        raise ValueError("Der Feldname darf keine Klammern enthalten.")
    typ = d.get("typ") if d.get("typ") in M85_TYPEN else "text"
    dup = q("SELECT id FROM m85_feld WHERE objekt=? AND lower(name)=lower(?) AND id!=?", (obj, name, int(d.get("id") or 0)), one=True)
    if dup:
        raise ValueError(f"Ein Feld „{name}“ gibt es dort schon.")
    aus = d.get("auswahl") or []
    if isinstance(aus, str):
        aus = [a.strip() for a in re.split(r"[\n;]", aus) if a.strip()]
    aus = list(dict.fromkeys(str(a).strip() for a in aus if str(a).strip()))[:200]
    if typ == "auswahl" and not aus:
        raise ValueError("Für ein Auswahlfeld bitte die Auswahlwerte angeben (einer je Zeile).")
    vals = (obj, name[:60], typ, 1 if d.get("pflicht") else 0, json.dumps(aus, ensure_ascii=False), 1 if d.get("spalte") else 0,
            (d.get("hinweis") or "")[:200], 0 if d.get("aktiv") in (0, False, "0") else 1)
    if d.get("id"):
        x("UPDATE m85_feld SET objekt=?, name=?, typ=?, pflicht=?, auswahl=?, spalte=?, hinweis=?, aktiv=? WHERE id=?", vals + (int(d["id"]),))
        return int(d["id"])
    srt = (q("SELECT COALESCE(MAX(sort),0) m FROM m85_feld WHERE objekt=?", (obj,), one=True) or {}).get("m") or 0
    return x("INSERT INTO m85_feld (objekt, name, typ, pflicht, auswahl, spalte, hinweis, aktiv, sort, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
             vals + (srt + 1, now_iso()))


def m85_boot(d):
    fs = m85_felder(alle=True)
    werte = {}
    if fs:
        for r in q("SELECT objekt, objekt_id, feld_id, wert FROM m85_wert"):
            werte.setdefault(r["objekt"], {}).setdefault(str(r["objekt_id"]), {})[str(r["feld_id"])] = r["wert"]
    d["m85"] = {"felder": fs, "werte": werte, "objekte": {k: v[0] for k, v in M85_OBJ.items()}, "typen": M85_TYPEN}


HOOK_BOOT.append(m85_boot)


def _m85_ok(h, extra=None):
    return h._send(200, dict({"ok": True}, **(extra or {})))


def _m85_r_felder(h, qs):
    return h._send(200, {"felder": m85_felder(qs.get("obj") or None, alle=True), "objekte": {k: v[0] for k, v in M85_OBJ.items()},
                         "typen": M85_TYPEN})


def _m85_r_werte(h, qs):
    obj, oid = qs.get("obj"), qs.get("id")
    return h._send(200, {"werte": m85_werte(obj, oid) if obj and oid else {}, "felder": m85_felder(obj)})


def _m85_r_feld_save(h, d):
    return _m85_ok(h, {"id": m85_feld_save(d)})


def _m85_r_feld_del(h, d):
    fid = int(d["id"])
    x("DELETE FROM m85_wert WHERE feld_id=?", (fid,))
    x("DELETE FROM m85_feld WHERE id=?", (fid,))
    return _m85_ok(h)


def _m85_r_sort(h, d):
    for i, fid in enumerate(d.get("ids") or []):
        x("UPDATE m85_feld SET sort=? WHERE id=?", (i + 1, int(fid)))
    return _m85_ok(h)


def _m85_r_werte_save(h, d):
    return h._send(200, m85_save_werte(d.get("obj"), d.get("id"), d.get("werte") or {}, partial=bool(d.get("partial"))))


def _m85_r_bulk(h, d):
    """same value for many objects (multi select)"""
    obj, fid, v = d.get("obj"), int(d.get("feld_id") or 0), d.get("wert")
    n = 0
    for oid in d.get("ids") or []:
        m85_save_werte(obj, oid, {fid: v}, partial=True)
        n += 1
    return _m85_ok(h, {"n": n})


HOOK_GET["/api/m85/felder"] = _m85_r_felder
HOOK_GET["/api/m85/werte"] = _m85_r_werte
HOOK_POST["/api/m85/feld_save"] = _m85_r_feld_save
HOOK_POST["/api/m85/feld_delete"] = _m85_r_feld_del
HOOK_POST["/api/m85/sort"] = _m85_r_sort
HOOK_POST["/api/m85/werte_save"] = _m85_r_werte_save
HOOK_POST["/api/m85/bulk"] = _m85_r_bulk

# ---------------------------------------------------------------------------
# Placeholders {{Feld:Name}} / [Feld:Name]
# ---------------------------------------------------------------------------


def m85_fill(text, sources):
    """sources: list of (objekt, id) - first one that has the field wins"""
    if not text or "eld" not in text:
        return text
    cache = []

    def vals():
        if not cache:
            cache.extend(m85_by_name(o, i) for o, i in sources if i)
        return cache

    def rep(m):
        k = _m85_norm(m.group(1) or m.group(2))
        for vv in vals():
            if k in vv:
                return vv[k]
        return ""
    return M85_PH_RE.sub(rep, text)


def _m85_inv_sources(inv):
    return [("rechnung", inv.get("id")), ("kunde", inv.get("customer_id")), ("projekt", inv.get("project_id"))]


@chain_step("fill_placeholders", "m85_felder")
def _m85_step_fill_placeholders(_next, text, inv, summe):
    t = _next(text, inv, summe)
    try:
        return m85_fill(t, _m85_inv_sources(inv or {}))
    except Exception:
        traceback.print_exc()
        return t


@chain_step("mail_fill", "m85_felder")
def _m85_step_mail_fill(_next, text, inv, title):
    t = _next(text, inv, title)
    try:
        return m85_fill(t, _m85_inv_sources(inv or {}))
    except Exception:
        return t


# letters (m27): placeholder regex accepts "Feld:Name", values come from customer / project
if "BR_PH_RE" in globals():
    _M85_PHC = r"[\wäöüÄÖÜß\-]+(?:\s*:\s*[\wäöüÄÖÜß\-. /]{1,40}?)?"
    BR_PH_RE = re.compile(r"\{\{\s*(" + _M85_PHC + r")\s*\}\}|«\s*(" + _M85_PHC + r")\s*»|<<\s*(" + _M85_PHC + r")\s*>>|\[\s*(" + _M85_PHC + r")\s*\]")
    _m85_orig_br_key = _br_key

    def _br_key(m):
        k = next(g for g in m.groups() if g is not None)
        kk = k.lower().replace(" ", "")
        if kk.startswith("feld:"):
            return "m85:" + kk[5:]
        if ":" in kk:
            return None
        return _m85_orig_br_key(m)

    _m85_orig_br_values = br_values

    def br_values(b, s=None):
        v = _m85_orig_br_values(b, s)
        try:
            for src in (m85_by_name("projekt", b.get("project_id")), m85_by_name("kunde", b.get("customer_id"))):
                for k, val in src.items():
                    v["m85:" + k] = val
        except Exception:
            traceback.print_exc()
        return v

# ---------------------------------------------------------------------------
# Exports: custom fields as additional columns
# ---------------------------------------------------------------------------


def _m85_key_db(kind, r):
    if kind == "customers":
        return (r.get("kdnr") or "",)
    if kind == "invoices":
        return (r.get("nr") or "",) if r.get("status") != "entwurf" else None
    if kind == "projects":
        return (r.get("nr") or "", r.get("name") or "")
    if kind == "belege":
        return (r.get("datum") or "", r.get("partner") or "", r.get("nr") or "", round(float(r.get("betrag") or 0), 2))
    if kind == "articles":
        return (r.get("nr") or "", r.get("name") or "")
    if kind == "m42_lager":
        return (r.get("nr") or "", r.get("name") or "")
    return None


def _m85_key_row(kind, row):
    try:
        if kind == "customers":
            return (row[0] or "",)
        if kind == "invoices":
            return (row[0] or "",)
        if kind == "projects":
            return (row[0] or "", row[1] or "")
        if kind == "belege":
            return (row[0] or "", row[2] or "", row[3] or "", round(float(row[-1] or 0), 2))
        if kind in ("articles", "m42_lager"):
            return (row[0] or "", row[1] or "")
    except Exception:
        return None
    return None


M85_EXP = {"customers": ("kunde", "customers"), "invoices": ("rechnung", "invoices"), "projects": ("projekt", "projects"),
           "belege": ("beleg", "belege"), "articles": ("baustein", "articles"), "m42_lager": ("lager", "m42_artikel")}


def _m85_wrap_export(kind):
    obj, tbl = M85_EXP[kind]
    title, fn = EXPORTS[kind]

    def wrapped(p, _fn=fn):
        sheets = _fn(p)
        try:
            fs = m85_felder(obj)
            if not fs or not sheets:
                return sheets
            sh = sheets[0]
            keymap = {}
            for r in q(f"SELECT * FROM {tbl}"):
                k = _m85_key_db(kind, r)
                if k is not None:
                    keymap.setdefault(k, r["id"])
            allw = {}
            for r in q("SELECT objekt_id, feld_id, wert FROM m85_wert WHERE objekt=?", (obj,)):
                allw.setdefault(r["objekt_id"], {})[r["feld_id"]] = r["wert"]
            for f in fs:
                sh["cols"].append((f["name"][:30], "t", max(10, min(24, len(f["name"]) + 4))))
            for row in sh["rows"]:
                oid = keymap.get(_m85_key_row(kind, row))
                w = allw.get(oid, {}) if oid else {}
                row.extend(m85_display(f, w.get(f["id"])) for f in fs)
        except Exception:
            traceback.print_exc()
        return sheets
    EXPORTS[kind] = (title, wrapped)


def _m85_exports():
    for k in M85_EXP:
        if k in EXPORTS and not getattr(EXPORTS[k][1], "_m85", False):
            _m85_wrap_export(k)
            EXPORTS[k][1]._m85 = True


_m85_exports()
# m42_lager etc. may be registered later by other modules -> once more at start
HOOK_SCHEMA.append(_m85_exports)


def _m85_selftest():
    err = []
    try:
        fid = m85_feld_save({"objekt": "kunde", "name": "_ST Raum", "typ": "auswahl", "auswahl": ["A", "B"], "pflicht": 1})
        cid = q("SELECT id FROM customers LIMIT 1", one=True)
        if cid:
            try:
                m85_save_werte("kunde", cid["id"], {fid: "X"})
                err.append("m85: ungueltiger Auswahlwert wurde angenommen")
            except ValueError:
                pass
            m85_save_werte("kunde", cid["id"], {fid: "B"})
            inv = {"id": None, "customer_id": cid["id"], "project_id": None, "nr": "1", "datum": today(), "frist": 7}
            t = fill_placeholders("Raum {{Feld:_ST Raum}} / [Feld:_st raum]", inv, 10.0)
            if t != "Raum B / B":
                err.append(f"m85: Platzhalter ergibt „{t}“")
            x("DELETE FROM m85_wert WHERE feld_id=?", (fid,))
        f2 = m85_feld_save({"objekt": "beleg", "name": "_ST Zahl", "typ": "zahl"})
        if _m85_check({"name": "z", "typ": "zahl", "pflicht": 0}, "1.234,50") != repr(1234.5):
            err.append("m85: Zahl 1.234,50 falsch gelesen")
        x("DELETE FROM m85_feld WHERE id IN (?,?)", (fid, f2))
    except Exception as e:
        err.append(f"m85 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m85_selftest)
