# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m75_pruefungen (v2.0.19)
# Pruefprotokolle mit Fristen: DGUV V3 (ortsveraenderliche Betriebsmittel, Grenzwerte nach DIN VDE 0701-0702
# vorbelegt, automatische Bewertung), DGUV V17/Rigging (Traversen, Kettenzuege, Anschlagmittel), Leitern/Tritte,
# frei definierbare Pruefarten mit eigenen Messfeldern. Prueflinge (Kunde oder eigenes Inventar), Pruefungen mit
# Pruefgeraet (Kalibrierung mit Erinnerung), Plaketten-Nr., naechster Termin. PDF-Pruefprotokoll mit
# Unterschriftsfeld, Sammelprotokoll je Kunde, Faelligkeitsliste, "Pruefungen abrechnen" -> Rechnungsentwurf.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M75_VERSION = "1.0.0"
M75_ERGEBNIS = {"bestanden": "bestanden", "maengel": "bestanden mit Mängeln", "nicht_bestanden": "nicht bestanden"}
M75_DEFAULTS = {"pruefer": "", "warn_tage": 30, "preis_je": 0.0, "preis_art": {}, "artikel_id": None, "plakette_next": "",
                "kalib_monate": 12}


def _f(key, label, typ="check", einheit="", vmin=None, vmax=None, hinweis=""):
    return {"key": key, "label": label, "typ": typ, "einheit": einheit, "min": vmin, "max": vmax, "hinweis": hinweis}


# Grenzwerte DIN VDE 0701-0702 (Wiederholungspruefung): Schutzleiterwiderstand <= 0,3 Ohm bis 5 m Leitung
# (+0,1 Ohm je weitere 7,5 m, max. 1 Ohm), Isolationswiderstand >= 1 MOhm (SK I) / >= 2 MOhm (SK II),
# Schutzleiterstrom <= 3,5 mA (SK I), Beruehrungsstrom <= 0,5 mA (SK II).
M75_ARTEN_STD = [
    {"key": "v3_sk1", "name": "DGUV V3 – Gerät Schutzklasse I", "norm": "DGUV Vorschrift 3 / DIN VDE 0701-0702", "intervall": 12, "felder": [
        _f("sicht", "Sichtprüfung (Gehäuse, Leitung, Stecker, Zugentlastung) in Ordnung"),
        _f("rpe", "Schutzleiterwiderstand", "num", "Ω", None, 0.3, "≤ 0,3 Ω bis 5 m Leitung, +0,1 Ω je weitere 7,5 m (max. 1 Ω)"),
        _f("riso", "Isolationswiderstand", "num", "MΩ", 1.0, None, "≥ 1 MΩ (mit Heizelementen ≥ 0,3 MΩ)"),
        _f("ipe", "Schutzleiterstrom", "num", "mA", None, 3.5, "≤ 3,5 mA (Heizgeräte > 3,5 kW: 1 mA/kW, max. 10 mA)"),
        _f("funktion", "Funktionsprüfung in Ordnung")]},
    {"key": "v3_sk2", "name": "DGUV V3 – Gerät Schutzklasse II", "norm": "DGUV Vorschrift 3 / DIN VDE 0701-0702", "intervall": 12, "felder": [
        _f("sicht", "Sichtprüfung (Gehäuse, Leitung, Stecker, Zugentlastung) in Ordnung"),
        _f("riso", "Isolationswiderstand", "num", "MΩ", 2.0, None, "≥ 2 MΩ"),
        _f("ib", "Berührungsstrom", "num", "mA", None, 0.5, "≤ 0,5 mA"),
        _f("funktion", "Funktionsprüfung in Ordnung")]},
    {"key": "v3_sk3", "name": "DGUV V3 – Gerät Schutzklasse III / Netzteil", "norm": "DGUV Vorschrift 3 / DIN VDE 0701-0702", "intervall": 24, "felder": [
        _f("sicht", "Sichtprüfung in Ordnung"),
        _f("riso", "Isolationswiderstand (Netzteil)", "num", "MΩ", 0.25, None, "≥ 0,25 MΩ (SELV/PELV)"),
        _f("funktion", "Funktionsprüfung in Ordnung")]},
    {"key": "v3_leitung", "name": "DGUV V3 – Verlängerung / Mehrfachsteckdose / Kabeltrommel", "norm": "DGUV Vorschrift 3 / DIN VDE 0701-0702", "intervall": 12, "felder": [
        _f("sicht", "Sichtprüfung (Mantel, Stecker, Kupplung) in Ordnung"),
        _f("rpe", "Schutzleiterwiderstand", "num", "Ω", None, 0.3, "≤ 0,3 Ω bis 5 m, +0,1 Ω je weitere 7,5 m (max. 1 Ω)"),
        _f("riso", "Isolationswiderstand", "num", "MΩ", 1.0, None, "≥ 1 MΩ"),
        _f("laenge", "Leitungslänge", "num", "m", None, None, "nur zur Dokumentation"),
        _f("polung", "Durchgang / Polarität / Verdrahtung in Ordnung")]},
    {"key": "v17_traverse", "name": "DGUV V17 – Traverse / Rigging-Element", "norm": "DGUV Vorschrift 17/18, DGUV Information 215-313", "intervall": 12, "felder": [
        _f("sicht", "Sichtprüfung: keine Verformung, Risse, Korrosion, Schweißnähte i. O."),
        _f("verbinder", "Verbinder, Konen, Bolzen, Sicherungen vollständig und i. O."),
        _f("kennz", "Kennzeichnung / Typenschild lesbar"),
        _f("ablege", "Keine Ablegereife erreicht")]},
    {"key": "v17_kettenzug", "name": "DGUV V17 – Elektrokettenzug", "norm": "DGUV Vorschrift 17/18, DGUV Grundsatz 309-001 / IGVW SQ P2", "intervall": 12, "felder": [
        _f("sicht", "Sichtprüfung Gehäuse, Steuerleitung, Steuerung i. O."),
        _f("kette", "Lastkette: Verschleiß / Längung innerhalb Grenzwert"),
        _f("kette_mm", "Kettenmaß über 11 Glieder", "num", "mm", None, None, "Herstellerangabe beachten"),
        _f("haken", "Lasthaken / Sicherungsfalle / Hakenmaul i. O."),
        _f("bremse", "Bremse(n) Funktion i. O."),
        _f("endschalter", "Endschalter / Rutschkupplung i. O."),
        _f("kennz", "Kennzeichnung / Tragfähigkeit lesbar")]},
    {"key": "anschlagmittel", "name": "Anschlagmittel (Rundschlinge, Stahlseil, Schäkel, Kette)", "norm": "DGUV Regel 109-017 / DIN EN 1492, DIN EN 13414", "intervall": 12, "felder": [
        _f("sicht", "Sichtprüfung: keine Schnitte, Quetschungen, Drahtbrüche, Verformung"),
        _f("kennz", "Etikett / Kennzeichnung lesbar (WLL)"),
        _f("ablege", "Keine Ablegereife erreicht")]},
    {"key": "leiter", "name": "Leitern und Tritte", "norm": "DGUV Information 208-016 / TRBS 2121-2", "intervall": 12, "felder": [
        _f("holme", "Holme, Sprossen, Stufen ohne Schäden"),
        _f("gelenke", "Gelenke, Spreizsicherung, Beschläge i. O."),
        _f("fuesse", "Leiterfüße / Rutschhemmung i. O."),
        _f("kennz", "Kennzeichnung / Typenschild vorhanden")]},
]


def _m75_schema():
    x("CREATE TABLE IF NOT EXISTS m75_art (id INTEGER PRIMARY KEY, key TEXT UNIQUE, name TEXT, norm TEXT, intervall INTEGER DEFAULT 12, "
      "felder TEXT, preis REAL DEFAULT 0, aktiv INTEGER DEFAULT 1, eigen INTEGER DEFAULT 0, sort INTEGER DEFAULT 0)")
    x("CREATE TABLE IF NOT EXISTS m75_pruefling (id INTEGER PRIMARY KEY, bezeichnung TEXT, inventar_nr TEXT, hersteller TEXT, typ TEXT, "
      "seriennr TEXT, customer_id INTEGER, asset_id INTEGER, standort TEXT, art_id INTEGER, intervall INTEGER DEFAULT 0, notiz TEXT, "
      "aktiv INTEGER DEFAULT 1, created TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m75_pruefung (id INTEGER PRIMARY KEY, pruefling_id INTEGER, art_id INTEGER, datum TEXT, pruefer TEXT, "
      "geraet_id INTEGER, werte TEXT, ergebnis TEXT, auto TEXT, maengel TEXT, plakette TEXT, naechste TEXT, invoice_id INTEGER, file TEXT, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS m75_geraet (id INTEGER PRIMARY KEY, name TEXT, hersteller TEXT, typ TEXT, seriennr TEXT, kalibriert_am TEXT, "
      "kalibrier_monate INTEGER DEFAULT 12, notiz TEXT, aktiv INTEGER DEFAULT 1)")
    for sql in ("CREATE INDEX IF NOT EXISTS m75_p_pl ON m75_pruefung(pruefling_id)", "CREATE INDEX IF NOT EXISTS m75_pl_c ON m75_pruefling(customer_id)"):
        try:
            x(sql)
        except Exception:
            pass
    for i, a in enumerate(M75_ARTEN_STD):
        if not q("SELECT id FROM m75_art WHERE key=?", (a["key"],), one=True):
            x("INSERT INTO m75_art (key, name, norm, intervall, felder, aktiv, eigen, sort) VALUES (?,?,?,?,?,1,0,?)",
              (a["key"], a["name"], a["norm"], a["intervall"], json.dumps(a["felder"], ensure_ascii=False), i))


HOOK_SCHEMA.append(_m75_schema)


# ---------------------------------------------------------------------------- helpers
def m75_cfg():
    c = dict(M75_DEFAULTS)
    c.update(get_settings().get("m75_cfg") or {})
    if not c.get("pruefer"):
        c["pruefer"] = get_settings().get("inhaber") or "T. Pfeiffer"
    if not c.get("plakette_next"):
        c["plakette_next"] = f"P{datetime.date.today().year}-0001"
    return c


def _m75_d(v):
    try:
        return datetime.date.fromisoformat(str(v or "")[:10])
    except Exception:
        return None


def _m75_num(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^0-9.,\-<>]", "", str(v).strip().replace(" ", "")).lstrip("<>")
    # measurements: a single comma OR a single dot is the decimal separator ("0.500" MOhm = 0,5 - read as 500
    # it passed the insulation test). Dots are thousands only together with a decimal comma ("1.234,5")
    # or as several groups with a non-zero lead ("1.234.567").
    if "," in t and "." in t and t.rfind(".") > t.rfind(","):
        t = t.replace(",", "")                       # "1,234.5" (English)
    elif "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 and re.fullmatch(r"-?[1-9]\d{0,2}(\.\d{3}){2,}", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except Exception:
        return None


def m75_arten(alle=False):
    rows = q("SELECT * FROM m75_art " + ("" if alle else "WHERE aktiv=1 ") + "ORDER BY sort, name")
    for r in rows:
        try:
            r["felder"] = json.loads(r["felder"] or "[]")
        except Exception:
            r["felder"] = []
    return rows


def m75_art(aid):
    r = q("SELECT * FROM m75_art WHERE id=?", (aid,), one=True) if aid else None
    if r:
        try:
            r["felder"] = json.loads(r["felder"] or "[]")
        except Exception:
            r["felder"] = []
    return r


def _m75_eff(f, werte):
    """field with the effective limit: protective conductor resistance (key rpe, standard max 0,3 Ohm) grows with the
    cable length (field laenge) by 0,1 Ohm per further 7,5 m above 5 m, max. 1 Ohm (DIN VDE 0701-0702)"""
    if f.get("key") != "rpe" or f.get("typ") != "num" or f.get("max") is None or abs(float(f["max"]) - 0.3) > 1e-9:
        return f
    ln = _m75_num((werte or {}).get("laenge"))
    if ln is None or ln <= 5:
        return f
    extra = math.ceil(round((ln - 5) / 7.5, 6)) * 0.1
    return dict(f, max=round(min(1.0, 0.3 + extra), 2))


def m75_bewerten(art, werte):
    """automatic result: (ergebnis, list of failed field labels)"""
    fail = []
    missing = []
    for f in (art or {}).get("felder") or []:
        f = _m75_eff(f, werte)
        v = (werte or {}).get(f["key"])
        if f.get("typ") == "check":
            if v in (None, ""):
                missing.append(f["label"])
            elif str(v).lower() in ("0", "false", "nein", "n.i.o.", "nio", "no"):
                fail.append(f["label"])
        elif f.get("typ") == "num":
            n = _m75_num(v)
            if n is None:
                if f.get("min") is not None or f.get("max") is not None:
                    missing.append(f["label"])
                continue
            if f.get("min") is not None and n < float(f["min"]):
                fail.append(f"{f['label']} {num_de(n, 2)} {f.get('einheit') or ''} < {num_de(float(f['min']), 2)}")
            if f.get("max") is not None and n > float(f["max"]):
                fail.append(f"{f['label']} {num_de(n, 2)} {f.get('einheit') or ''} > {num_de(float(f['max']), 2)}")
    if fail:
        return "nicht_bestanden", fail, missing
    return "bestanden", [], missing


def _m75_cust_name(cid):
    c = q("SELECT firma, name, kdnr FROM customers WHERE id=?", (cid,), one=True) if cid else None
    return (c["firma"] or c["name"] or c["kdnr"] or "") if c else ""


def _m75_inc(nr):
    try:
        return inc_number(nr)
    except Exception:
        m = re.match(r"^(.*?)(\d+)$", nr or "")
        return f"{m.group(1)}{int(m.group(2)) + 1:0{len(m.group(2))}d}" if m else (nr or "") + "-1"


def m75_intervall(pl, art=None):
    if pl and int(pl.get("intervall") or 0) > 0:
        return int(pl["intervall"])
    art = art or m75_art(pl.get("art_id") if pl else None)
    return int((art or {}).get("intervall") or 12)


# ---------------------------------------------------------------------------- prueflinge + due list
def m75_prueflinge(customer_id=None, alle=False):
    rows = q("SELECT pl.*, a.name art_name FROM m75_pruefling pl LEFT JOIN m75_art a ON a.id=pl.art_id " +
             ("" if alle else "WHERE pl.aktiv=1 ") + "ORDER BY pl.customer_id, pl.inventar_nr, pl.bezeichnung")
    if customer_id not in (None, ""):
        cid = int(customer_id)
        rows = [r for r in rows if (r["customer_id"] or 0) == cid]
    last = {}
    for p in q("SELECT * FROM m75_pruefung ORDER BY datum, id"):
        last[p["pruefling_id"]] = p
    cfg = m75_cfg()
    t0 = datetime.date.today()
    warn = int(cfg.get("warn_tage") or 30)
    cn = {}
    for r in rows:
        lp = last.get(r["id"])
        r["kunde"] = cn.setdefault(r["customer_id"], _m75_cust_name(r["customer_id"])) if r["customer_id"] else "Eigenes Inventar"
        r["letzte"] = lp["datum"] if lp else ""
        r["letzte_id"] = lp["id"] if lp else None
        r["ergebnis"] = lp["ergebnis"] if lp else ""
        r["plakette"] = lp["plakette"] if lp else ""
        nx = (lp["naechste"] if lp else "") or ""
        r["naechste"] = nx
        dn = _m75_d(nx)
        if not lp:
            r["status"], r["tage"] = "nie", -9999
        elif lp["ergebnis"] == "nicht_bestanden":
            r["status"], r["tage"] = "gesperrt", -9998
        elif dn and dn < t0:
            r["status"], r["tage"] = "ueberfaellig", (dn - t0).days
        elif dn and (dn - t0).days <= warn:
            r["status"], r["tage"] = "faellig", (dn - t0).days
        else:
            r["status"], r["tage"] = "ok", (dn - t0).days if dn else 9999
    return rows


def m75_faellig(customer_id=None):
    return sorted([r for r in m75_prueflinge(customer_id) if r["status"] in ("nie", "ueberfaellig", "faellig", "gesperrt")], key=lambda r: r["tage"])


def m75_kalib_hinweise():
    cfg = m75_cfg()
    t0 = datetime.date.today()
    out = []
    for g in q("SELECT * FROM m75_geraet WHERE aktiv=1"):
        k = _m75_d(g["kalibriert_am"])
        mon = int(g["kalibrier_monate"] or cfg.get("kalib_monate") or 12)
        if not k:
            out.append({"id": g["id"], "name": g["name"], "faellig": "", "tage": -9999, "text": "Kalibrierdatum fehlt"})
            continue
        due = add_months(k, mon)
        dd = (due - t0).days
        if dd <= int(cfg.get("warn_tage") or 30):
            out.append({"id": g["id"], "name": g["name"], "faellig": due.isoformat(), "tage": dd,
                        "text": ("Kalibrierung überfällig seit " if dd < 0 else "Kalibrierung fällig am ") + de_date(due.isoformat())})
    return out


def m75_pruefling_save(d):
    pid = d.get("id")
    cols = ("bezeichnung", "inventar_nr", "hersteller", "typ", "seriennr", "customer_id", "asset_id", "standort", "art_id", "intervall", "notiz", "aktiv")
    v = {}
    for c in cols:
        val = d.get(c)
        if c in ("customer_id", "asset_id", "art_id"):
            val = int(val) if str(val or "").isdigit() and int(val) > 0 else None
        elif c == "intervall":
            try:
                val = max(0, int(float(str(val or 0).replace(",", "."))))
            except Exception:
                val = 0
        elif c == "aktiv":
            val = 0 if str(val) in ("0", "False", "false") else 1
        else:
            val = (str(val) if val is not None else "").strip()[:2000 if c == "notiz" else 200]
        v[c] = val
    if not v["bezeichnung"] and not v["inventar_nr"]:
        raise ValueError("Bitte Bezeichnung oder Inventar-Nr. angeben.")
    if v["inventar_nr"]:
        dup = q("SELECT id FROM m75_pruefling WHERE inventar_nr=? AND COALESCE(customer_id,0)=? AND id<>?",
                (v["inventar_nr"], v["customer_id"] or 0, int(pid or 0)), one=True)
        if dup:
            raise ValueError(f"Inventar-Nr. {v['inventar_nr']} gibt es bei diesem Kunden schon.")
    vals = tuple(v[c] for c in cols)
    if pid:
        x(f"UPDATE m75_pruefling SET {', '.join(c + '=?' for c in cols)}, updated=? WHERE id=?", vals + (now_iso(), int(pid)))
        return int(pid)
    return x(f"INSERT INTO m75_pruefling ({', '.join(cols)}, created, updated) VALUES ({','.join('?' * len(cols))},?,?)", vals + (now_iso(), now_iso()))


def m75_aus_inventar(asset_ids, art_id=None):
    n = 0
    for a in q(f"SELECT * FROM assets WHERE id IN ({','.join('?' * len(asset_ids)) or 'NULL'})", [int(i) for i in asset_ids]):
        if q("SELECT id FROM m75_pruefling WHERE asset_id=?", (a["id"],), one=True):
            continue
        m75_pruefling_save({"bezeichnung": a["bezeichnung"], "seriennr": a["seriennr"] or "", "standort": a["standort"] or "", "asset_id": a["id"],
                            "art_id": art_id, "inventar_nr": f"INV-{a['id']:04d}"})
        n += 1
    return {"ok": True, "n": n}


# ---------------------------------------------------------------------------- pruefungen
def m75_pruefung_save(d):
    pid = int(d.get("pruefling_id") or 0)
    pl = q("SELECT * FROM m75_pruefling WHERE id=?", (pid,), one=True)
    if not pl:
        raise ValueError("Bitte einen Prüfling wählen.")
    art = m75_art(int(d.get("art_id") or pl["art_id"] or 0))
    if not art:
        raise ValueError("Bitte eine Prüfart wählen.")
    werte = {}
    for f in art["felder"]:
        v = (d.get("werte") or {}).get(f["key"])
        if f["typ"] == "check":
            werte[f["key"]] = "" if v in (None, "") else (1 if str(v).lower() in ("1", "true", "ja", "i.o.", "io") else 0)
        elif f["typ"] == "num":
            n = _m75_num(v)
            werte[f["key"]] = "" if n is None else n
        else:
            werte[f["key"]] = (str(v) if v is not None else "")[:300]
    auto, fail, missing = m75_bewerten(art, werte)
    erg = d.get("ergebnis") or auto
    if erg not in M75_ERGEBNIS:
        erg = auto
    if missing and erg == auto == "bestanden":
        # never "bestanden" automatically while required checks / measurements are empty
        raise ValueError("Noch nicht ausgefüllt: " + ", ".join(missing) + ". Bitte eintragen oder das Ergebnis von Hand wählen.")
    datum = (d.get("datum") or today())[:10]
    cfg = m75_cfg()
    plak = (d.get("plakette") or "").strip()
    nr_used = False
    if not plak and erg != "nicht_bestanden" and not d.get("id"):
        plak = cfg["plakette_next"]
        nr_used = True
    naechste = (d.get("naechste") or "").strip()[:10]
    if not naechste and erg != "nicht_bestanden":
        dd = _m75_d(datum)
        naechste = add_months(dd, m75_intervall(pl, art)).isoformat() if dd else ""
    maengel = (d.get("maengel") or "").strip()
    if fail and not maengel:
        maengel = "; ".join(fail)
    vals = (pid, art["id"], datum, (d.get("pruefer") or cfg["pruefer"])[:120], int(d["geraet_id"]) if str(d.get("geraet_id") or "").isdigit() else None,
            json.dumps(werte, ensure_ascii=False), erg, auto, maengel[:2000], plak[:40], naechste)
    if d.get("id"):
        x("UPDATE m75_pruefung SET pruefling_id=?, art_id=?, datum=?, pruefer=?, geraet_id=?, werte=?, ergebnis=?, auto=?, maengel=?, plakette=?, naechste=? "
          "WHERE id=?", vals + (int(d["id"]),))
        out = int(d["id"])
    else:
        out = x("INSERT INTO m75_pruefung (pruefling_id, art_id, datum, pruefer, geraet_id, werte, ergebnis, auto, maengel, plakette, naechste, created) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", vals + (now_iso(),))
    if not pl["art_id"]:
        x("UPDATE m75_pruefling SET art_id=? WHERE id=?", (art["id"], pid))
    if nr_used or (plak and plak == cfg["plakette_next"]):
        c2 = dict(get_settings().get("m75_cfg") or {})
        c2["plakette_next"] = _m75_inc(plak)
        set_setting("m75_cfg", c2)
    if d.get("pruefer"):
        c2 = dict(get_settings().get("m75_cfg") or {})
        if c2.get("pruefer") != d["pruefer"]:
            c2["pruefer"] = d["pruefer"][:120]
            set_setting("m75_cfg", c2)
    return {"ok": True, "id": out, "ergebnis": erg, "auto": auto, "plakette": plak, "naechste": naechste}


def m75_pruefungen(customer_id=None, von=None, bis=None, pruefling_id=None):
    sql = ("SELECT p.*, pl.bezeichnung, pl.inventar_nr, pl.hersteller, pl.typ, pl.seriennr, pl.customer_id, pl.standort, a.name art_name, "
           "g.name geraet_name, i.nr inv_nr, i.status inv_status FROM m75_pruefung p JOIN m75_pruefling pl ON pl.id=p.pruefling_id "
           "LEFT JOIN m75_art a ON a.id=p.art_id LEFT JOIN m75_geraet g ON g.id=p.geraet_id LEFT JOIN invoices i ON i.id=p.invoice_id")
    wh, args = [], []
    if customer_id not in (None, ""):
        wh.append("COALESCE(pl.customer_id,0)=?")
        args.append(int(customer_id))
    if von:
        wh.append("p.datum>=?")
        args.append(von[:10])
    if bis:
        wh.append("p.datum<=?")
        args.append(bis[:10])
    if pruefling_id:
        wh.append("p.pruefling_id=?")
        args.append(int(pruefling_id))
    if wh:
        sql += " WHERE " + " AND ".join(wh)
    rows = q(sql + " ORDER BY p.datum DESC, p.id DESC", tuple(args))
    cn = {}
    for r in rows:
        r["kunde"] = cn.setdefault(r["customer_id"], _m75_cust_name(r["customer_id"])) if r["customer_id"] else "Eigenes Inventar"
        try:
            r["werte"] = json.loads(r["werte"] or "{}")
        except Exception:
            r["werte"] = {}
        if r["invoice_id"] and not r["inv_nr"]:
            r["invoice_id"] = None
    return rows


def m75_delete(kind, ids):
    ids = [int(i) for i in ids or [] if str(i).isdigit()]
    if not ids:
        return {"ok": True, "done": 0}
    ph = ",".join("?" * len(ids))
    if kind in ("pruefung", "pruefling"):
        col = "id" if kind == "pruefung" else "pruefling_id"
        files = {r["file"] for r in q(f"SELECT file FROM m75_pruefung WHERE {col} IN ({ph}) AND COALESCE(file,'')<>''", ids)}
        x(f"DELETE FROM m75_pruefung WHERE {col} IN ({ph})", ids)
        if kind == "pruefling":
            x(f"DELETE FROM m75_pruefling WHERE id IN ({ph})", ids)
        for fn in files:   # protocol PDF only if no remaining test still points to it
            if q("SELECT id FROM m75_pruefung WHERE file=? LIMIT 1", (fn,), one=True):
                continue
            try:
                fp = fn if os.path.isabs(fn) else os.path.join(DATA_DIR, fn)
                if os.path.isfile(fp):
                    os.remove(fp)
            except OSError:
                pass
    elif kind == "geraet":
        x(f"UPDATE m75_pruefung SET geraet_id=NULL WHERE geraet_id IN ({ph})", ids)
        x(f"DELETE FROM m75_geraet WHERE id IN ({ph})", ids)
    elif kind == "art":
        used = q(f"SELECT COUNT(*) n FROM m75_pruefung WHERE art_id IN ({ph})", ids, one=True)["n"]
        if used:
            x(f"UPDATE m75_art SET aktiv=0 WHERE id IN ({ph})", ids)
            return {"ok": True, "done": len(ids), "hinweis": "Prüfart wird in Prüfungen verwendet - nur ausgeblendet."}
        x(f"DELETE FROM m75_art WHERE id IN ({ph})", ids)
    return {"ok": True, "done": len(ids)}


def m75_art_save(d):
    felder = []
    for f in d.get("felder") or []:
        lab = (f.get("label") or "").strip()
        if not lab:
            continue
        key = re.sub(r"[^a-z0-9_]", "", (f.get("key") or "").lower()) or re.sub(r"[^a-z0-9]", "", lab.lower())[:16] or f"f{len(felder) + 1}"
        while any(x_["key"] == key for x_ in felder):
            key += "_"
        felder.append({"key": key, "label": lab[:120], "typ": f.get("typ") if f.get("typ") in ("check", "num", "text") else "check",
                       "einheit": (f.get("einheit") or "")[:12], "min": _m75_num(f.get("min")), "max": _m75_num(f.get("max")),
                       "hinweis": (f.get("hinweis") or "")[:200]})
    name = (d.get("name") or "").strip()
    if not name:
        raise ValueError("Bitte einen Namen für die Prüfart angeben.")
    if not felder:
        raise ValueError("Bitte mindestens ein Prüffeld anlegen.")
    vals = (name[:120], (d.get("norm") or "")[:200], max(1, int(float(str(d.get("intervall") or 12).replace(",", ".")))),
            json.dumps(felder, ensure_ascii=False), round(float(str(d.get("preis") or 0).replace(",", ".")), 2), 0 if d.get("aktiv") in (0, "0", False) else 1)
    if d.get("id"):
        x("UPDATE m75_art SET name=?, norm=?, intervall=?, felder=?, preis=?, aktiv=? WHERE id=?", vals + (int(d["id"]),))
        return int(d["id"])
    return x("INSERT INTO m75_art (name, norm, intervall, felder, preis, aktiv, key, eigen, sort) VALUES (?,?,?,?,?,?,?,1,100)",
             vals + ("eigen_" + uuid.uuid4().hex[:8],))


def m75_geraet_save(d):
    vals = ((d.get("name") or "").strip()[:120], (d.get("hersteller") or "")[:80], (d.get("typ") or "")[:80], (d.get("seriennr") or "")[:80],
            (d.get("kalibriert_am") or "")[:10], max(1, int(float(str(d.get("kalibrier_monate") or 12).replace(",", ".")))), (d.get("notiz") or "")[:500],
            0 if d.get("aktiv") in (0, "0", False) else 1)
    if not vals[0]:
        raise ValueError("Bitte einen Namen für das Prüfgerät angeben.")
    if d.get("id"):
        x("UPDATE m75_geraet SET name=?, hersteller=?, typ=?, seriennr=?, kalibriert_am=?, kalibrier_monate=?, notiz=?, aktiv=? WHERE id=?", vals + (int(d["id"]),))
        return int(d["id"])
    return x("INSERT INTO m75_geraet (name, hersteller, typ, seriennr, kalibriert_am, kalibrier_monate, notiz, aktiv) VALUES (?,?,?,?,?,?,?,?)", vals)


# ---------------------------------------------------------------------------- invoice
M75_ABR_LOCK = threading.RLock()


def m75_abrechnen(ids):
    # v2.1.0: one at a time - a double click created two draft invoices (the first one lost its link)
    with M75_ABR_LOCK:
        return _m75_abrechnen(ids)


def _m75_abrechnen(ids):
    ids = [int(i) for i in ids or [] if str(i).isdigit()]
    rows = [r for r in m75_pruefungen() if r["id"] in ids and not r["invoice_id"]]
    if not rows:
        raise ValueError("Keine offenen (noch nicht abgerechneten) Prüfungen gewählt.")
    custs = {r["customer_id"] for r in rows}
    if len(custs) > 1:
        raise ValueError("Bitte nur Prüfungen eines Kunden zusammen abrechnen.")
    cid = custs.pop()
    if not cid:
        raise ValueError("Prüfungen am eigenen Inventar werden nicht abgerechnet.")
    c = q("SELECT * FROM customers WHERE id=?", (cid,), one=True)
    cfg = m75_cfg()
    s = get_settings()
    art_ = q("SELECT * FROM articles WHERE id=?", (cfg.get("artikel_id"),), one=True) if cfg.get("artikel_id") else None
    groups = {}
    for r in rows:
        groups.setdefault(r["art_id"], []).append(r)
    items = []
    for aid, rs in groups.items():
        a = m75_art(aid) or {"name": "Prüfung", "norm": "", "preis": 0}
        preis = float((cfg.get("preis_art") or {}).get(str(aid)) or a.get("preis") or 0) or (float(art_["price"]) if art_ else float(cfg.get("preis_je") or 0))
        inv = ", ".join((r["inventar_nr"] or r["bezeichnung"] or "") for r in rs)
        items.append({"qty": len(rs), "nr": art_["nr"] if art_ else "", "name": f"Prüfung {a['name']}",
                      "descr": (f"{a['norm']}\n" if a.get("norm") else "") + f"Prüfdatum {', '.join(sorted({de_date(r['datum']) for r in rs}))}\nPrüflinge: {inv}"[:1500],
                      "price": preis, "rabatt": 0, "article_id": art_["id"] if art_ else None})
    d = {"customer_id": cid, "kdnr": c["kdnr"] if c else "", "addr": address_lines(c) if c else [], "datum": today(),
         "liefer": max(r["datum"] for r in rows), "titel": "Rechnung", "typ": "rechnung", "status": "entwurf", "toptext": s.get("default_top", ""),
         "foottext": s.get("default_foot", ""), "zahlart": s.get("zahlart", "Ueberweisung"), "frist": s.get("frist") or 7, "items": items, "source": "pruefung"}
    iid, nr = save_invoice(d)
    x(f"UPDATE m75_pruefung SET invoice_id=? WHERE id IN ({','.join('?' * len(rows))})", [iid] + [r["id"] for r in rows])
    return {"ok": True, "id": iid, "nr": nr, "n": len(rows)}


# ---------------------------------------------------------------------------- PDF
def _m75_dir(cid):
    p = os.path.join(DATA_DIR, "Pruefungen", safe_name(_m75_cust_name(cid) if cid else "Eigenes Inventar") or "Kunde")
    os.makedirs(p, exist_ok=True)
    return p


def _m75_styles():
    from reportlab.lib.styles import ParagraphStyle
    ink, gray, acc = colors.HexColor("#1e1a2b"), colors.HexColor("#6c6880"), colors.HexColor("#5b3fd6")
    N = ParagraphStyle("n", fontName=FONT_R(), fontSize=8.8, leading=11.5, textColor=ink)
    return {"N": N, "NS": ParagraphStyle("ns", parent=N, fontSize=7.5, leading=9.5, textColor=gray),
            "C": ParagraphStyle("c", parent=N, fontSize=8, leading=10),
            "CB": ParagraphStyle("cb", parent=N, fontName=FONT_B(), fontSize=8, leading=10),
            "K": ParagraphStyle("k", fontName=FONT_B(), fontSize=7.5, leading=9, textColor=acc),
            "H1": ParagraphStyle("h1", fontName=FONT_B(), fontSize=18, leading=22, textColor=ink, spaceAfter=2),
            "H2": ParagraphStyle("h2", fontName=FONT_B(), fontSize=11, leading=14, textColor=ink, spaceBefore=8, spaceAfter=3),
            "ink": ink, "gray": gray, "acc": acc, "soft": colors.HexColor("#f3f1fb")}


def _m75_wert_txt(f, v):
    if f["typ"] == "check":
        return "i. O." if v in (1, True, "1") else ("n. i. O." if v in (0, False, "0") else "–")
    if f["typ"] == "num":
        return (num_de(float(v), 2) + " " + (f.get("einheit") or "")).strip() if v not in (None, "") else "–"
    return str(v or "–")


def _m75_grenze(f):
    if f["typ"] != "num":
        return ""
    e = f.get("einheit") or ""
    if f.get("min") is not None and f.get("max") is not None:
        return f"{num_de(f['min'], 2)} … {num_de(f['max'], 2)} {e}"
    if f.get("min") is not None:
        return f"≥ {num_de(f['min'], 2)} {e}"
    if f.get("max") is not None:
        return f"≤ {num_de(f['max'], 2)} {e}"
    return ""


def _m75_ok_feld(f, v):
    if f["typ"] == "check":
        return None if v in (None, "") else v in (1, True, "1")
    if f["typ"] == "num":
        n = _m75_num(v)
        if n is None:
            return None
        if f.get("min") is not None and n < float(f["min"]):
            return False
        if f.get("max") is not None and n > float(f["max"]):
            return False
        return True if (f.get("min") is not None or f.get("max") is not None) else None
    return None


def _m75_protokoll_flow(p, st):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    e = esc_xml
    art = m75_art(p["art_id"]) or {"name": p.get("art_name") or "Prüfung", "norm": "", "felder": []}
    g = q("SELECT * FROM m75_geraet WHERE id=?", (p["geraet_id"],), one=True) if p.get("geraet_id") else None
    s = get_settings()
    el = [Paragraph("PRÜFPROTOKOLL", st["K"]), Paragraph(e(art["name"]), st["H1"]),
          Paragraph(e(art.get("norm") or ""), st["NS"]), Spacer(1, 6)]
    kunde = _m75_cust_name(p["customer_id"]) if p.get("customer_id") else "Eigenes Inventar"
    info = [["Auftraggeber", kunde, "Prüfdatum", de_date(p["datum"])],
            ["Prüfling", p.get("bezeichnung") or "", "Inventar-Nr.", p.get("inventar_nr") or ""],
            ["Hersteller / Typ", " ".join(v for v in (p.get("hersteller") or "", p.get("typ") or "") if v), "Seriennr.", p.get("seriennr") or ""],
            ["Standort", p.get("standort") or "", "Plaketten-Nr.", p.get("plakette") or "–"],
            ["Prüfgerät", (g["name"] + (f" ({g['seriennr']})" if g and g["seriennr"] else "")) if g else "–", "Kalibriert am",
             de_date(g["kalibriert_am"]) if g and g["kalibriert_am"] else "–"]]
    t = Table([[Paragraph(f"<b>{e(a)}</b>", st["C"]), Paragraph(e(b), st["C"]), Paragraph(f"<b>{e(c)}</b>", st["C"]), Paragraph(e(d), st["C"])] for a, b, c, d in info],
              colWidths=[30 * mm, 62 * mm, 28 * mm, 60 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6d2e2")), ("BACKGROUND", (0, 0), (0, -1), st["soft"]),
                           ("BACKGROUND", (2, 0), (2, -1), st["soft"]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    el += [t, Paragraph("Prüfschritte und Messwerte", st["H2"])]
    rows = [["Prüfschritt", "Messwert / Befund", "Grenzwert", "Bewertung"]]
    for f in art["felder"]:
        v = (p.get("werte") or {}).get(f["key"])
        f = _m75_eff(f, p.get("werte") or {})
        ok = _m75_ok_feld(f, v)
        rows.append([Paragraph(e(f["label"]) + (f"<br/><font size=6.5 color='#6c6880'>{e(f.get('hinweis') or '')}</font>" if f.get("hinweis") else ""), st["C"]),
                     Paragraph(e(_m75_wert_txt(f, v)), st["C"]), Paragraph(e(_m75_grenze(f)), st["C"]),
                     Paragraph("<font color='#1f9d6b'><b>i. O.</b></font>" if ok is True else ("<font color='#c0392b'><b>n. i. O.</b></font>" if ok is False else "–"), st["C"])])
    t = Table(rows, colWidths=[78 * mm, 38 * mm, 36 * mm, 28 * mm], repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), FONT_B(), 7.5), ("TEXTCOLOR", (0, 0), (-1, 0), st["gray"]), ("LINEBELOW", (0, 0), (-1, 0), 0.6, st["ink"]),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, st["soft"]]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    el.append(t)
    erg = p.get("ergebnis") or "bestanden"
    col = {"bestanden": "#1f9d6b", "maengel": "#d08a1f", "nicht_bestanden": "#c0392b"}.get(erg, "#1e1a2b")
    el += [Spacer(1, 8), Paragraph(f"<b>Ergebnis:</b> <font color='{col}'><b>{e(M75_ERGEBNIS.get(erg, erg).upper())}</b></font>"
                                   + ("" if erg == "nicht_bestanden" else f" &nbsp;·&nbsp; <b>Nächste Prüfung:</b> {de_date(p.get('naechste') or '') or '–'}"), st["N"])]
    if erg == "nicht_bestanden":
        el.append(Paragraph("Das Betriebsmittel darf bis zur Instandsetzung und erneuten Prüfung nicht verwendet werden.", st["N"]))
    if p.get("maengel"):
        el += [Spacer(1, 4), Paragraph("<b>Mängel / Bemerkungen:</b> " + e(p["maengel"]).replace("\n", "<br/>"), st["N"])]
    sig = Table([["", "", ""], [f"Ort, Datum: {de_date(p['datum'])}", "", f"Prüfer: {p.get('pruefer') or ''} (befähigte Person / Elektrofachkraft)"]],
                colWidths=[70 * mm, 20 * mm, 90 * mm], rowHeights=[16 * mm, 6 * mm])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 1), (0, 1), 0.6, st["ink"]), ("LINEABOVE", (2, 1), (2, 1), 0.6, st["ink"]),
                             ("FONT", (0, 1), (-1, 1), FONT_R(), 7.5), ("TEXTCOLOR", (0, 1), (-1, 1), st["gray"])]))
    el += [Spacer(1, 10), sig, Spacer(1, 4),
           Paragraph(f"{e(s.get('firma') or '')} · {e(s.get('inhaber') or 'T. Pfeiffer')}", st["NS"])]
    return el


def _m75_build(el, titel, fp):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.units import mm
    st = _m75_styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=17 * mm, bottomMargin=15 * mm,
                            title=titel, author="T. Pfeiffer", creator=f"{APP_NAME} v{APP_VERSION}")

    def onpage(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(st["gray"])
        cv.drawString(15 * mm, 8 * mm, f"{titel} · T. Pfeiffer")
        cv.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Seite {dc.page}")
        cv.setStrokeColor(st["acc"])
        cv.setLineWidth(2)
        cv.line(15 * mm, A4[1] - 10 * mm, 37 * mm, A4[1] - 10 * mm)
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    data = buf.getvalue()
    write_file(fp, data)
    return fp


def m75_protokoll_pdf(pids, open_=True):
    from reportlab.platypus import PageBreak
    pids = [int(i) for i in pids if str(i).isdigit()]
    rows = {r["id"]: r for r in m75_pruefungen() if r["id"] in pids}
    if not rows:
        raise ValueError("Keine Prüfung gewählt.")
    st = _m75_styles()
    el = []
    order = [rows[i] for i in pids if i in rows]
    for k, p in enumerate(order):
        if k:
            el.append(PageBreak())
        el += _m75_protokoll_flow(p, st)
    first = order[0]
    if len(order) == 1:
        name = f"Pruefprotokoll_{first.get('inventar_nr') or first.get('bezeichnung') or first['id']}_{first['datum']}.pdf"
    else:
        name = f"Pruefprotokolle_{len(order)}_{today()}.pdf"
    fp = os.path.join(_m75_dir(first["customer_id"]), safe_name(name))
    _m75_build(el, "Prüfprotokoll", fp)
    for p in order:
        x("UPDATE m75_pruefung SET file=? WHERE id=?", (os.path.relpath(fp, DATA_DIR), p["id"]))
    if open_ and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return fp


def m75_sammel_pdf(customer_id, von=None, bis=None, einzel=False, open_=True):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.units import mm
    cid = int(customer_id) if str(customer_id or "").isdigit() else 0
    st = _m75_styles()
    e = esc_xml
    rows = m75_pruefungen(cid, von, bis)
    if not rows:
        raise ValueError("Keine Prüfungen im gewählten Zeitraum.")
    # newest test per pruefling within the period
    last = {}
    for r in sorted(rows, key=lambda r: (r["datum"], r["id"])):
        last[r["pruefling_id"]] = r
    lst = sorted(last.values(), key=lambda r: (r["inventar_nr"] or "", r["bezeichnung"] or ""))
    kunde = _m75_cust_name(cid) if cid else "Eigenes Inventar"
    n_ok = sum(1 for r in lst if r["ergebnis"] == "bestanden")
    n_m = sum(1 for r in lst if r["ergebnis"] == "maengel")
    n_x = sum(1 for r in lst if r["ergebnis"] == "nicht_bestanden")
    zeitraum = f"{de_date(von) if von else de_date(min(r['datum'] for r in lst))} – {de_date(bis) if bis else de_date(max(r['datum'] for r in lst))}"
    el = [Paragraph("SAMMELPROTOKOLL", st["K"]), Paragraph(f"Prüfung elektrischer Betriebsmittel und Arbeitsmittel – {e(kunde)}", st["H1"]),
          Paragraph(f"Zeitraum {zeitraum} · {len(lst)} Prüfling(e): {n_ok} bestanden, {n_m} mit Mängeln, {n_x} nicht bestanden · Stand {de_date(today())}", st["NS"]),
          Spacer(1, 6)]
    tab = [["Inv.-Nr.", "Prüfling", "Hersteller / Typ", "Prüfart", "Datum", "Ergebnis", "Plakette", "Nächste"]]
    for r in lst:
        tab.append([Paragraph(e(r["inventar_nr"] or ""), st["C"]), Paragraph(e(r["bezeichnung"] or ""), st["C"]),
                    Paragraph(e(" ".join(v for v in (r["hersteller"] or "", r["typ"] or "") if v)), st["C"]), Paragraph(e(r["art_name"] or ""), st["C"]),
                    de_date(r["datum"]), Paragraph(e(M75_ERGEBNIS.get(r["ergebnis"], r["ergebnis"] or "")), st["C"]), r["plakette"] or "", de_date(r["naechste"]) if r["naechste"] else "–"])
    t = Table(tab, colWidths=[18 * mm, 36 * mm, 30 * mm, 38 * mm, 15 * mm, 18 * mm, 15 * mm, 15 * mm], repeatRows=1)
    ts = [("FONT", (0, 0), (-1, 0), FONT_B(), 7), ("TEXTCOLOR", (0, 0), (-1, 0), st["gray"]), ("LINEBELOW", (0, 0), (-1, 0), 0.6, st["ink"]),
          ("FONT", (0, 1), (-1, -1), FONT_R(), 7.5), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, st["soft"]]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    for i, r in enumerate(lst, start=1):
        if r["ergebnis"] == "nicht_bestanden":
            ts.append(("TEXTCOLOR", (5, i), (5, i), colors.HexColor("#c0392b")))
    t.setStyle(TableStyle(ts))
    el.append(t)
    mg = [r for r in lst if r["maengel"]]
    if mg:
        el.append(Paragraph("Mängel / Bemerkungen", st["H2"]))
        for r in mg:
            el.append(Paragraph(f"<b>{e(r['inventar_nr'] or r['bezeichnung'] or '')}</b>: {e(r['maengel'])}", st["C"]))
    s = get_settings()
    sig = Table([["", "", ""], [f"Ort, Datum: {de_date(today())}", "", f"Prüfer: {lst[0]['pruefer'] or ''}"]], colWidths=[70 * mm, 20 * mm, 90 * mm], rowHeights=[16 * mm, 6 * mm])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 1), (0, 1), 0.6, st["ink"]), ("LINEABOVE", (2, 1), (2, 1), 0.6, st["ink"]),
                             ("FONT", (0, 1), (-1, 1), FONT_R(), 7.5), ("TEXTCOLOR", (0, 1), (-1, 1), st["gray"])]))
    el += [Spacer(1, 12), sig, Paragraph(f"{e(s.get('firma') or '')} · {e(s.get('inhaber') or 'T. Pfeiffer')}", st["NS"])]
    if einzel:
        for r in lst:
            el.append(PageBreak())
            el += _m75_protokoll_flow(r, st)
    fp = os.path.join(_m75_dir(cid), safe_name(f"Sammelprotokoll_{kunde}_{today()}.pdf"))
    _m75_build(el, f"Sammelprotokoll {kunde}", fp)
    if open_ and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return fp


# ---------------------------------------------------------------------------- export
def _m75_ex(p):
    cid = p.get("customer_id")
    ids = {int(i) for i in (p.get("ids") or []) if str(i).isdigit()}
    st_lbl = {"nie": "nie geprüft", "ueberfaellig": "überfällig", "faellig": "fällig", "gesperrt": "gesperrt (n. bestanden)", "ok": "ok"}
    pls = m75_prueflinge(cid, alle=True)
    out = []
    if p.get("teil") != "pruefungen":
        if ids and p.get("teil") == "prueflinge":
            pls = [r for r in pls if r["id"] in ids]
        out.append(_sh("Prüflinge", [("Kunde", "t", 22), ("Inv.-Nr.", "t", 12), ("Bezeichnung", "t", 26), ("Hersteller", "t", 14), ("Typ", "t", 14),
                                     ("Seriennr.", "t", 16), ("Standort", "t", 16), ("Prüfart", "t", 30), ("Letzte Prüfung", "d", 11), ("Ergebnis", "t", 14),
                                     ("Plakette", "t", 12), ("Nächste", "d", 11), ("Status", "t", 16)],
                       [[r["kunde"], r["inventar_nr"] or "", r["bezeichnung"] or "", r["hersteller"] or "", r["typ"] or "", r["seriennr"] or "", r["standort"] or "",
                         r["art_name"] or "", r["letzte"], M75_ERGEBNIS.get(r["ergebnis"], r["ergebnis"] or ""), r["plakette"] or "", r["naechste"], st_lbl.get(r["status"], "")]
                        for r in pls], f"Stand {de_date(today())}", total=False))
    if p.get("teil") != "prueflinge":
        pr = m75_pruefungen(cid)
        if ids and p.get("teil") == "pruefungen":
            pr = [r for r in pr if r["id"] in ids]
        out.append(_sh("Prüfungen", [("Datum", "d", 11), ("Kunde", "t", 22), ("Inv.-Nr.", "t", 12), ("Prüfling", "t", 26), ("Prüfart", "t", 30),
                                     ("Prüfer", "t", 16), ("Prüfgerät", "t", 18), ("Ergebnis", "t", 16), ("Plakette", "t", 12), ("Nächste", "d", 11),
                                     ("Mängel", "t", 30), ("Rechnung", "t", 12)],
                       [[r["datum"], r["kunde"], r["inventar_nr"] or "", r["bezeichnung"] or "", r["art_name"] or "", r["pruefer"] or "", r["geraet_name"] or "",
                         M75_ERGEBNIS.get(r["ergebnis"], r["ergebnis"] or ""), r["plakette"] or "", r["naechste"] or "", r["maengel"] or "", r["inv_nr"] or ""]
                        for r in pr], "", total=False))
    return out


EXPORTS["m75_pruefungen"] = ("Pruefungen", _m75_ex)


# ---------------------------------------------------------------------------- boot / routes
def _m75_boot(d):
    try:
        f = m75_faellig()
        k = m75_kalib_hinweise()
        d["m75"] = {"faellig": len(f), "ueberfaellig": sum(1 for r in f if r["status"] in ("ueberfaellig", "gesperrt")),
                    "liste": [{"bezeichnung": r["bezeichnung"], "inventar_nr": r["inventar_nr"], "kunde": r["kunde"], "status": r["status"], "naechste": r["naechste"]} for r in f[:8]],
                    "kalib": k}
    except Exception:
        d["m75"] = {"faellig": 0, "ueberfaellig": 0, "liste": [], "kalib": []}


HOOK_BOOT.append(_m75_boot)


def _m75_g_data(h, qs):
    cid = qs.get("customer_id")
    cid = None if cid in (None, "", "alle") else cid
    return h._send(200, {"ok": True, "arten": m75_arten(True), "prueflinge": m75_prueflinge(cid, alle=True), "pruefungen": m75_pruefungen(cid)[:2000],
                         "geraete": q("SELECT * FROM m75_geraet ORDER BY aktiv DESC, name"), "kalib": m75_kalib_hinweise(), "cfg": m75_cfg(),
                         "ergebnis": M75_ERGEBNIS, "assets": q("SELECT id, bezeichnung, kategorie, seriennr, standort FROM assets WHERE abgang IS NULL OR abgang='' ORDER BY bezeichnung")})


def _m75_p_cfg(h, d):
    c = dict(get_settings().get("m75_cfg") or {})
    for k in ("pruefer", "plakette_next"):
        if k in d:
            c[k] = str(d[k] or "").strip()[:120]
    for k in ("warn_tage", "kalib_monate"):
        if k in d:
            c[k] = max(0, int(float(str(d[k] or 0).replace(",", "."))))
    if "preis_je" in d:
        c["preis_je"] = round(float(str(d["preis_je"] or 0).replace(",", ".")), 2)
    if "artikel_id" in d:
        c["artikel_id"] = int(d["artikel_id"]) if str(d["artikel_id"] or "").isdigit() else None
    if "preis_art" in d and isinstance(d["preis_art"], dict):
        c["preis_art"] = {str(k): round(float(str(v or 0).replace(",", ".")), 2) for k, v in d["preis_art"].items() if str(v or "").strip()}
    set_setting("m75_cfg", c)
    return h._send(200, {"ok": True, "cfg": m75_cfg()})


def _m75_p_eval(h, d):
    art = m75_art(int(d.get("art_id") or 0))
    erg, fail, missing = m75_bewerten(art, d.get("werte") or {})
    return h._send(200, {"ok": True, "ergebnis": erg, "fehler": fail, "fehlt": missing})


HOOK_GET["/api/m75/data"] = _m75_g_data
HOOK_GET["/api/m75/faellig"] = lambda h, qs: h._send(200, {"ok": True, "faellig": m75_faellig(qs.get("customer_id") or None)})
HOOK_POST["/api/m75/pruefling/save"] = lambda h, d: h._send(200, {"ok": True, "id": m75_pruefling_save(d)})
HOOK_POST["/api/m75/pruefung/save"] = lambda h, d: h._send(200, m75_pruefung_save(d))
HOOK_POST["/api/m75/eval"] = _m75_p_eval
HOOK_POST["/api/m75/delete"] = lambda h, d: h._send(200, m75_delete(d.get("kind"), d.get("ids") or [d.get("id")]))
HOOK_POST["/api/m75/art/save"] = lambda h, d: h._send(200, {"ok": True, "id": m75_art_save(d)})
HOOK_POST["/api/m75/geraet/save"] = lambda h, d: h._send(200, {"ok": True, "id": m75_geraet_save(d)})
HOOK_POST["/api/m75/inventar"] = lambda h, d: h._send(200, m75_aus_inventar(d.get("ids") or [], d.get("art_id")))
HOOK_POST["/api/m75/abrechnen"] = lambda h, d: h._send(200, m75_abrechnen(d.get("ids") or []))
HOOK_POST["/api/m75/pdf"] = lambda h, d: h._send(200, {"ok": True, "path": m75_protokoll_pdf(d.get("ids") or [d.get("id")])})
HOOK_POST["/api/m75/sammel"] = lambda h, d: h._send(200, {"ok": True, "path": m75_sammel_pdf(d.get("customer_id"), d.get("von"), d.get("bis"), bool(d.get("einzel")))})
HOOK_POST["/api/m75/cfg"] = _m75_p_cfg


def _m75_selftest():
    err = []
    os.environ["PA_RECHNUNG_NO_OPEN"] = os.environ.get("PA_RECHNUNG_NO_OPEN") or "1"
    cid = plid = None
    cfg_old = get_settings().get("m75_cfg")
    files = []
    try:
        a1 = q("SELECT * FROM m75_art WHERE key='v3_sk1'", one=True)
        if not a1:
            return ["m75: Standard-Prüfarten fehlen"]
        art = m75_art(a1["id"])
        if m75_bewerten(art, {"sicht": 1, "rpe": "0,12", "riso": ">20", "ipe": 0.4, "funktion": 1})[0] != "bestanden":
            err.append("m75: Bewertung i. O. falsch")
        if m75_bewerten(art, {"sicht": 1, "rpe": 0.5, "riso": 20, "ipe": 0.4, "funktion": 1})[0] != "nicht_bestanden":
            err.append("m75: Grenzwert Schutzleiter nicht erkannt")
        cid = x("INSERT INTO customers (kdnr, firma, name, created) VALUES (?,?,?,?)", ("_ST75", "Selbsttest Prüf GmbH", "", now_iso()))
        set_setting("m75_cfg", {"plakette_next": "ST-0009", "preis_je": 7.5})
        plid = m75_pruefling_save({"bezeichnung": "Kaltgeräteleitung", "inventar_nr": "ST-1", "customer_id": cid, "art_id": a1["id"]})
        r = m75_pruefung_save({"pruefling_id": plid, "datum": "2026-01-15", "werte": {"sicht": 1, "rpe": 0.1, "riso": 50, "ipe": 0.2, "funktion": 1}})
        if r["plakette"] != "ST-0009" or r["naechste"] != "2027-01-15" or r["ergebnis"] != "bestanden":
            err.append(f"m75: Prüfung gespeichert falsch ({r})")
        if m75_cfg()["plakette_next"] != "ST-0010":
            err.append("m75: Plaketten-Nr. nicht hochgezählt")
        if not any(p["id"] == plid for p in m75_prueflinge(cid)):
            err.append("m75: Prüfling fehlt in Liste")
        inv = m75_abrechnen([r["id"]])
        iv = get_invoice(inv["id"])
        if abs(iv["summe"] - 7.5) > 0.01 or iv["status"] != "entwurf":
            err.append(f"m75: Abrechnung falsch ({iv['summe']})")
        x("DELETE FROM items WHERE invoice_id=?", (inv["id"],))
        x("DELETE FROM invoices WHERE id=?", (inv["id"],))
        files.append(m75_protokoll_pdf([r["id"]], open_=False))
        files.append(m75_sammel_pdf(cid, einzel=True, open_=False))
        if not all(os.path.getsize(f) > 1500 for f in files):
            err.append("m75: PDF leer")
        if len(_m75_ex({"customer_id": cid})) != 2:
            err.append("m75: Export unvollständig")
    except Exception as e:
        err.append(f"m75: Ausnahme {e}")
    finally:
        try:
            if plid:
                m75_delete("pruefling", [plid])
            if cid:
                x("DELETE FROM customers WHERE id=?", (cid,))
            set_setting("m75_cfg", cfg_old or {})
            for f in files:
                try:
                    os.remove(f)
                except OSError:
                    pass
        except Exception:
            pass
    return err


HOOK_SELFTEST.append(_m75_selftest)
