# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m86_regeln (v2.0.19)
# Regel-Automatik "Wenn - dann":
#  Ausloeser: neuer Beleg, neue Bankbuchung, Dokument gespeichert, Rechnung x Tage ueberfaellig,
#             Angebot x Tage offen, Wartung faellig, taeglich
#  Bedingungen: Feld enthaelt / gleich / groesser ... (auch eigene Felder aus m85), alle oder eine
#  Aktionen: Kategorie / Projekt / Status setzen, Notiz anhaengen, eigenes Feld setzen,
#            Rechnungsentwurf aus Wartungsvertrag, Erinnerungs-Mail, Hinweis auf der Uebersicht
# Jede Regel wirkt pro Objekt nur EINMAL (Tabelle m86_done); Mails nie doppelt, nur bei aktiver Regel.
# Testlauf zeigt, was passieren wuerde, ohne etwas zu aendern. Alles steht im Protokoll m86_log.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M86_VERSION = "1.0.0"
_m86_tl = threading.local()
M86_STATE = {"tag": "", "last": 0.0, "lock": threading.Lock()}

M86_AUSLOESER = {
    "beleg_neu": {"label": "Neuer Beleg erfasst", "obj": "beleg"},
    "bank_neu": {"label": "Neue Bankbuchung", "obj": "bank"},
    "dok_gespeichert": {"label": "Rechnung/Angebot gespeichert", "obj": "dok"},
    "rechnung_ueberfaellig": {"label": "Rechnung überfällig seit x Tagen", "obj": "dok", "tage": True},
    "angebot_offen": {"label": "Angebot seit x Tagen offen", "obj": "dok", "tage": True},
    "wartung_faellig": {"label": "Wartung / Abo fällig", "obj": "wartung"},
    "taeglich": {"label": "Täglich (einmal am Tag)", "obj": "tag"},
}
M86_EVENT_AUSLOESER = ("beleg_neu", "bank_neu", "dok_gespeichert")
M86_FELDER = {
    "beleg": [("typ", "Art"), ("datum", "Datum"), ("partner", "Partner / Lieferant"), ("nr", "Beleg-Nr."), ("betrag", "Betrag"),
              ("kategorie", "Kategorie"), ("notiz", "Notiz"), ("datei", "Dateiname"), ("projekt", "Projekt-Nr."), ("quelle", "Quelle"), ("text", "alles (Volltext)")],
    "bank": [("datum", "Datum"), ("betrag", "Betrag"), ("name", "Name"), ("zweck", "Verwendungszweck"), ("iban", "IBAN"), ("text", "alles (Volltext)")],
    "dok": [("typ", "Dokument-Art"), ("nr", "Nummer"), ("datum", "Datum"), ("kunde", "Kunde"), ("kdnr", "Kd-Nr."), ("titel", "Titel"), ("summe", "Betrag"),
            ("status", "Status"), ("mahnstufe", "Mahnstufe"), ("tage", "Tage überfällig / offen"), ("projekt", "Projekt-Nr."), ("text", "alles (Volltext)")],
    "wartung": [("name", "Vertrag"), ("kunde", "Kunde"), ("preis", "Preis"), ("naechste", "Nächster Termin"), ("tage", "Tage bis Termin"), ("text", "alles (Volltext)")],
    "tag": [("wochentag", "Wochentag (1=Mo … 7=So)"), ("tag", "Tag im Monat"), ("monat", "Monat")],
}
M86_OPS = {"enthaelt": "enthält", "nicht_enthaelt": "enthält nicht", "gleich": "ist gleich", "ungleich": "ist nicht", "beginnt": "beginnt mit",
           "endet": "endet mit", "groesser": "größer als", "kleiner": "kleiner als", "leer": "ist leer", "nicht_leer": "ist nicht leer", "regex": "passt zu Muster"}
M86_AKTIONEN = {
    "kategorie": {"label": "Kategorie setzen", "obj": ("beleg",)},
    "projekt": {"label": "Projekt zuordnen", "obj": ("beleg", "dok")},
    "status": {"label": "Status setzen", "obj": ("dok",)},
    "notiz": {"label": "Notiz anhängen", "obj": ("beleg", "dok", "wartung")},
    "feld": {"label": "Eigenes Feld setzen", "obj": ("beleg", "dok")},
    "entwurf": {"label": "Rechnungsentwurf aus Vertrag", "obj": ("wartung",)},
    "mail": {"label": "E-Mail senden", "obj": ("dok", "wartung", "tag")},
    "hinweis": {"label": "Hinweis auf der Übersicht", "obj": ("beleg", "bank", "dok", "wartung", "tag")},
}


def _m86_schema():
    x("CREATE TABLE IF NOT EXISTS m86_regel (id INTEGER PRIMARY KEY, name TEXT, aktiv INTEGER DEFAULT 1, ausloeser TEXT, tage INTEGER DEFAULT 0, "
      "modus TEXT DEFAULT 'alle', bedingungen TEXT, aktionen TEXT, wiederholen INTEGER DEFAULT 0, sort INTEGER DEFAULT 0, created TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m86_done (regel_id INTEGER, schluessel TEXT, zeit TEXT, PRIMARY KEY (regel_id, schluessel))")
    x("CREATE TABLE IF NOT EXISTS m86_log (id INTEGER PRIMARY KEY, zeit TEXT, regel_id INTEGER, regel TEXT, objekt TEXT, objekt_id INTEGER, "
      "titel TEXT, aktion TEXT, ergebnis TEXT, ok INTEGER)")
    x("CREATE TABLE IF NOT EXISTS m86_hinweis (id INTEGER PRIMARY KEY, zeit TEXT, regel_id INTEGER, text TEXT, objekt TEXT, objekt_id INTEGER, "
      "erledigt INTEGER DEFAULT 0)")


HOOK_SCHEMA.append(_m86_schema)

# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------


def _m86_row(r):
    r = dict(r)
    for k in ("bedingungen", "aktionen"):
        try:
            r[k] = json.loads(r.get(k) or "[]")
        except Exception:
            r[k] = []
    return r


def m86_regeln(nur_aktiv=False):
    return [_m86_row(r) for r in q("SELECT * FROM m86_regel" + (" WHERE aktiv=1" if nur_aktiv else "") + " ORDER BY sort, id")]


def m86_check_regel(d):
    a = d.get("ausloeser")
    if a not in M86_AUSLOESER:
        raise ValueError("Bitte einen Auslöser wählen.")
    obj = M86_AUSLOESER[a]["obj"]
    akt = [z for z in (d.get("aktionen") or []) if z.get("typ")]
    if not akt:
        raise ValueError("Bitte mindestens eine Aktion („dann …“) angeben.")
    for z in akt:
        if z["typ"] not in M86_AKTIONEN:
            raise ValueError(f"Unbekannte Aktion {z['typ']}.")
        if obj not in M86_AKTIONEN[z["typ"]]["obj"]:
            raise ValueError(f"„{M86_AKTIONEN[z['typ']]['label']}“ passt nicht zum Auslöser „{M86_AUSLOESER[a]['label']}“.")
        if z["typ"] == "mail" and not (z.get("betreff") or "").strip():
            raise ValueError("Bei „E-Mail senden“ bitte einen Betreff angeben.")
        if z["typ"] == "mail" and (z.get("an") or "kunde") not in ("kunde", "ich") and "@" not in (z.get("an") or ""):
            raise ValueError("Bei „E-Mail senden“: Empfänger ist „kunde“, „ich“ oder eine E-Mail-Adresse.")
        if z["typ"] == "kategorie" and not (z.get("wert") or "").strip():
            raise ValueError("Bei „Kategorie setzen“ bitte die Kategorie wählen.")
    for b in d.get("bedingungen") or []:
        if b.get("op") == "regex":
            try:
                re.compile(b.get("wert") or "")
            except re.error as e:
                raise ValueError(f"Muster ungültig: {e}")
    return akt


def m86_save(d):
    akt = m86_check_regel(d)
    name = (d.get("name") or "").strip() or M86_AUSLOESER[d["ausloeser"]]["label"]
    vals = (name[:80], 0 if d.get("aktiv") in (0, False, "0") else 1, d["ausloeser"], int(d.get("tage") or 0),
            "eine" if d.get("modus") == "eine" else "alle", json.dumps([b for b in (d.get("bedingungen") or []) if b.get("feld")], ensure_ascii=False),
            json.dumps(akt, ensure_ascii=False), 1 if d.get("wiederholen") else 0, now_iso())
    if d.get("id"):
        x("UPDATE m86_regel SET name=?, aktiv=?, ausloeser=?, tage=?, modus=?, bedingungen=?, aktionen=?, wiederholen=?, updated=? WHERE id=?",
          vals + (int(d["id"]),))
        return int(d["id"])
    # v2.0.19 (R4): never re-use the id of a deleted rule - its "already done" entries are kept
    # (a deleted rule restored with "Rueckgaengig" must not mail everybody again)
    with DB_LOCK:
        nid = 1 + max(int((q("SELECT MAX(id) m FROM m86_regel", one=True) or {}).get("m") or 0),
                      int((q("SELECT MAX(regel_id) m FROM m86_done", one=True) or {}).get("m") or 0),
                      int((q("SELECT MAX(regel_id) m FROM m86_log", one=True) or {}).get("m") or 0))
        return x("INSERT INTO m86_regel (id, name, aktiv, ausloeser, tage, modus, bedingungen, aktionen, wiederholen, updated, created) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (nid,) + vals + (now_iso(),))

# ---------------------------------------------------------------------------
# objects -> field values
# ---------------------------------------------------------------------------


def _m86_pnr(pid):
    if not pid:
        return ""
    r = q("SELECT nr FROM projects WHERE id=?", (pid,), one=True)
    return (r or {}).get("nr") or ""


def m86_obj(obj, oid):
    """returns (row, values dict, title) or None"""
    if obj == "beleg":
        r = q("SELECT * FROM belege WHERE id=?", (int(oid),), one=True)
        if not r:
            return None
        v = {"typ": r["typ"] or "", "datum": r["datum"] or "", "partner": r["partner"] or "", "nr": r["nr"] or "", "betrag": float(r["betrag"] or 0),
             "kategorie": r["kategorie"] or "", "notiz": r["notiz"] or "", "datei": os.path.basename(r["file"] or ""), "projekt": _m86_pnr(r["project_id"]),
             "quelle": r.get("quelle") or ""}
        return r, v, f"Beleg {de_date(r['datum'])} {r['partner'] or ''} {money(float(r['betrag'] or 0))}".strip()
    if obj == "bank":
        r = q("SELECT * FROM bank_tx WHERE id=?", (int(oid),), one=True)
        if not r:
            return None
        v = {"datum": r["datum"] or "", "betrag": float(r["betrag"] or 0), "name": r["name"] or "", "zweck": r["zweck"] or "", "iban": r["iban"] or ""}
        return r, v, f"Bank {de_date(r['datum'])} {r['name'] or ''} {money(float(r['betrag'] or 0))}"
    if obj == "dok":
        r = q("SELECT * FROM invoices WHERE id=?", (int(oid),), one=True)
        if not r:
            return None
        tage = 0
        d0 = d_iso(r["datum"])
        if d0:
            if r["typ"] == "rechnung":
                tage = (datetime.date.today() - (d0 + datetime.timedelta(days=_frist(r["frist"])))).days
            else:
                tage = (datetime.date.today() - d0).days
        v = {"typ": r["typ"] or "", "nr": r["nr"] or "", "datum": r["datum"] or "", "kunde": inv_name(r), "kdnr": r["kdnr"] or "",
             "titel": r["titel"] or "", "summe": float(r["summe"] or 0), "status": r["status"] or "", "mahnstufe": int(r.get("mahnstufe") or 0),
             "tage": max(0, tage), "projekt": _m86_pnr(r["project_id"])}
        t = DOC_TYPES.get(r["typ"] or "rechnung", {}).get("title", "Dokument")
        return r, v, f"{t} {r['nr'] or 'Entwurf'} {inv_name(r)} {money(float(r['summe'] or 0))}"
    if obj == "wartung":
        r = q("SELECT * FROM vertraege WHERE id=?", (int(oid),), one=True)
        if not r:
            return None
        c = q("SELECT * FROM customers WHERE id=?", (r["customer_id"],), one=True) if r["customer_id"] else None
        nx = d_iso(r["naechste"])
        v = {"name": r["name"] or "", "kunde": (c.get("firma") or c.get("name")) if c else "", "preis": float(r["preis"] or 0),
             "naechste": r["naechste"] or "", "tage": (nx - datetime.date.today()).days if nx else 0}
        return r, v, f"Wartung {r['name']} ({de_date(r['naechste'])})"
    if obj == "tag":
        t = datetime.date.today()
        return {"id": 0}, {"wochentag": t.isoweekday(), "tag": t.day, "monat": t.month}, f"Tag {de_date(t.isoformat())}"
    return None


def _m86_m85_val(obj, row, fid):
    """value of a custom field m85 for the object (own field, or of its customer / project)"""
    try:
        f = q("SELECT * FROM m85_feld WHERE id=?", (int(fid),), one=True)
    except Exception:
        return ""
    if not f:
        return ""
    fo = f["objekt"]
    oid = None
    if fo == "beleg" and obj == "beleg":
        oid = row.get("id")
    elif fo == "rechnung" and obj == "dok":
        oid = row.get("id")
    elif fo == "kunde":
        oid = row.get("customer_id")
    elif fo == "projekt":
        oid = row.get("project_id")
    if not oid:
        return ""
    r = q("SELECT wert FROM m85_wert WHERE objekt=? AND objekt_id=? AND feld_id=?", (fo, int(oid), int(fid)), one=True)
    return (r or {}).get("wert") or ""


def _m86_num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(parse_amount(str(v)))
    except Exception:
        return None


def m86_cond(b, obj, row, vals):
    feld, op, want = b.get("feld") or "", b.get("op") or "enthaelt", str(b.get("wert") or "")
    if feld.startswith("feld:"):
        v = _m86_m85_val(obj, row, feld[5:])
    elif feld == "text":
        v = " ".join(str(x_) for x_ in vals.values())
    else:
        v = vals.get(feld, "")
    sv = ("%.2f" % v) if isinstance(v, float) else str(v)
    lo, wl = sv.lower(), want.lower().strip()
    if op == "leer":
        return sv.strip() in ("", "0", "0.00") if isinstance(v, (int, float)) else not sv.strip()
    if op == "nicht_leer":
        return not (sv.strip() in ("", "0", "0.00") if isinstance(v, (int, float)) else not sv.strip())
    if op in ("groesser", "kleiner"):
        a, c = _m86_num(v), _m86_num(want)
        if a is None or c is None:
            a, c = sv, want            # dates as ISO text compare fine
            if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", want.strip()):
                c = iso_from_de(want.strip())
        return a > c if op == "groesser" else a < c
    if op == "regex":
        try:
            return bool(re.search(want, sv, re.I))
        except re.error:
            return False
    if isinstance(v, float) and op in ("gleich", "ungleich"):
        c = _m86_num(want)
        eq = c is not None and abs(v - c) < 0.005
        return eq if op == "gleich" else not eq
    if op == "gleich":
        return lo.strip() == wl
    if op == "ungleich":
        return lo.strip() != wl
    if op == "beginnt":
        return lo.startswith(wl)
    if op == "endet":
        return lo.endswith(wl)
    if op == "nicht_enthaelt":
        return any(w_ for w_ in wl.split("|")) and not any(w_ and w_ in lo for w_ in wl.split("|"))
    return any(w_ and w_ in lo for w_ in wl.split("|"))      # "a|b" = a oder b


def m86_match(regel, obj, row, vals):
    bs = [b for b in regel.get("bedingungen") or [] if b.get("feld")]
    if not bs:
        return True, []
    res = [(b, m86_cond(b, obj, row, vals)) for b in bs]
    ok = any(r for _b, r in res) if regel.get("modus") == "eine" else all(r for _b, r in res)
    return ok, [f"{b.get('feld')} {M86_OPS.get(b.get('op'), b.get('op'))} „{b.get('wert') or ''}“: {'ja' if r else 'nein'}" for b, r in res]

# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------


def _m86_fill(text, obj, row, vals):
    t = str(text or "")
    rep = {"[Nummer]": vals.get("nr", ""), "[Betrag]": money(float(vals.get("summe") or vals.get("betrag") or vals.get("preis") or 0)),
           "[Kunde]": vals.get("kunde", ""), "[Name]": vals.get("kunde") or vals.get("partner") or vals.get("name") or "",
           "[Tage]": str(vals.get("tage", "")), "[Datum]": de_date(vals.get("datum") or today()), "[Heute]": de_date(today()),
           "[Titel]": vals.get("titel", ""), "[Vertrag]": vals.get("name", "") if obj == "wartung" else "",
           "[Termin]": de_date(vals.get("naechste") or ""), "[Partner]": vals.get("partner", ""), "[Kategorie]": vals.get("kategorie", "")}
    if obj == "dok" and row.get("datum"):
        d0 = d_iso(row["datum"])
        if d0:
            rep["[Faellig]"] = rep["[Fällig]"] = de_date((d0 + datetime.timedelta(days=_frist(row.get("frist")))).isoformat())
    for k, v in rep.items():
        t = t.replace(k, str(v))
    try:
        if "m85_fill" in globals():
            src = []
            if obj == "dok":
                src = [("rechnung", row.get("id")), ("kunde", row.get("customer_id")), ("projekt", row.get("project_id"))]
            elif obj == "beleg":
                src = [("beleg", row.get("id")), ("projekt", row.get("project_id"))]
            elif obj == "wartung":
                src = [("kunde", row.get("customer_id")), ("projekt", row.get("project_id"))]
            t = m85_fill(t, src)
    except Exception:
        pass
    return t.replace("\\n", "\n")


def _m86_project_from_text(vals):
    blob = " ".join(str(v) for v in vals.values()).lower()
    best = None
    for p in q("SELECT id, nr, name FROM projects WHERE COALESCE(nr,'')!=''"):
        nr = (p["nr"] or "").lower()
        if len(nr) >= 4 and nr in blob and (not best or len(nr) > len(best["nr"])):
            best = p
    return best


def _m86_mail_to(z, obj, row):
    an = (z.get("an") or "kunde").strip()
    if an == "ich":
        s = get_settings()
        return s.get("smtp_from_addr") or s.get("smtp_user") or ""
    if an == "kunde":
        cid = row.get("customer_id")
        c = q("SELECT mail FROM customers WHERE id=?", (cid,), one=True) if cid else None
        return (c or {}).get("mail") or ""
    return an


def m86_action_text(z, obj, row, vals):
    t = z.get("typ")
    if t == "kategorie":
        return f"Kategorie → {z.get('wert')}"
    if t == "projekt":
        if z.get("wert") in (None, "", "auto"):
            p = _m86_project_from_text(vals)
            return f"Projekt → {p['nr']} {p['name']} (aus dem Text erkannt)" if p else "Projekt: keine Projekt-Nr. im Text gefunden"
        p = q("SELECT nr, name FROM projects WHERE id=?", (int(z["wert"]),), one=True)
        return f"Projekt → {(p or {}).get('nr', '?')} {(p or {}).get('name', '')}"
    if t == "status":
        return f"Status → {z.get('wert')}"
    if t == "notiz":
        return "Notiz + „" + _m86_fill(z.get("wert"), obj, row, vals)[:80] + "“"
    if t == "feld":
        return f"Feld {z.get('feld')} → {_m86_fill(z.get('wert'), obj, row, vals)}"
    if t == "entwurf":
        return "Rechnungsentwurf aus dem Vertrag anlegen"
    if t == "mail":
        to = _m86_mail_to(z, obj, row)
        return f"E-Mail an {to or '(keine Adresse!)'}: „{_m86_fill(z.get('betreff'), obj, row, vals)[:80]}“" + (" + PDF" if z.get("anhang") and obj == "dok" else "")
    if t == "hinweis":
        return "Hinweis: „" + _m86_fill(z.get("wert") or z.get("text"), obj, row, vals)[:100] + "“"
    return t


def _m86_append(tbl, col, rid, txt):
    cur_ = q(f"SELECT {col} v FROM {tbl} WHERE id=?", (rid,), one=True)
    old = ((cur_ or {}).get("v") or "").strip()
    if txt and txt not in old:
        x(f"UPDATE {tbl} SET {col}=? WHERE id=?", ((old + "\n" + txt).strip() if old else txt, rid))


def m86_do(z, regel, obj, row, vals):
    t = z.get("typ")
    rid = row.get("id")
    if t == "kategorie" and obj == "beleg":
        x("UPDATE belege SET kategorie=? WHERE id=?", (z.get("wert"), rid))
        return f"Kategorie {z.get('wert')}"
    if t in ("projekt", "status") and obj == "dok" and row.get("locked"):
        return "festgeschrieben - unverändert"      # v2.0.19 (R4): GoBD, a locked document is never changed
    if t == "projekt":
        if z.get("wert") in (None, "", "auto"):
            p = _m86_project_from_text(vals)
            if not p:
                return "kein Projekt erkannt"
            pid = p["id"]
        else:
            pid = int(z["wert"])
        x(f"UPDATE {'belege' if obj == 'beleg' else 'invoices'} SET project_id=? WHERE id=?", (pid, rid))
        return f"Projekt {_m86_pnr(pid)}"
    if t == "status" and obj == "dok":
        st = z.get("wert") or ""
        if st == "bezahlt":
            if row.get("status") != "offen":
                return "nicht offen - unverändert"
            x("UPDATE invoices SET status='bezahlt', bezahlt_am=?, updated=? WHERE id=?", (today(), now_iso(), rid))
            lock_invoice(rid)
        elif st in ("offen", "abgelehnt", "angenommen", "erledigt"):
            if (row.get("typ") or "rechnung") in ("rechnung", "storno") and st != "offen":
                return f"Status {st} gibt es nur bei Angeboten/Aufträgen - unverändert"
            x("UPDATE invoices SET status=?, updated=? WHERE id=?", (st, now_iso(), rid))
        else:
            return f"Status {st} nicht erlaubt"
        return f"Status {st}"
    if t == "notiz":
        txt = _m86_fill(z.get("wert"), obj, row, vals).strip()
        _m86_append({"beleg": "belege", "dok": "invoices", "wartung": "vertraege"}[obj], "notiz", rid, txt)
        return "Notiz ergänzt"
    if t == "feld":
        mo = {"beleg": "beleg", "dok": "rechnung"}[obj]
        m85_set(mo, rid, z.get("feld") or "", _m86_fill(z.get("wert"), obj, row, vals))
        return f"Feld {z.get('feld')} gesetzt"
    if t == "entwurf" and obj == "wartung":
        return "Entwurf " + str(_m86_entwurf(row))
    if t == "mail":
        return _m86_mail(z, regel, obj, row, vals)
    if t == "hinweis":
        txt = _m86_fill(z.get("wert") or z.get("text"), obj, row, vals).strip() or regel.get("name") or "Hinweis"
        x("INSERT INTO m86_hinweis (zeit, regel_id, text, objekt, objekt_id) VALUES (?,?,?,?,?)", (now_iso(), regel.get("id"), txt[:400], obj, rid))
        return "Hinweis angelegt"
    return "nichts zu tun"


def _m86_entwurf(v):
    s = get_settings()
    c = q("SELECT * FROM customers WHERE id=?", (v["customer_id"],), one=True) if v["customer_id"] else None
    a = q("SELECT * FROM articles WHERE id=?", (v["article_id"],), one=True) if v["article_id"] else None
    d = {"typ": "rechnung", "status": "entwurf", "customer_id": v["customer_id"], "project_id": v["project_id"],
         "kdnr": c["kdnr"] if c else "", "addr": address_lines(c) if c else [], "datum": today(), "liefer": v.get("naechste") or today(),
         "auftrag": today(), "titel": f"Rechnung {v['name']}", "toptext": s["default_top"], "foottext": s["default_foot"],
         "zahlart": s.get("zahlart", "Ueberweisung"), "frist": s["frist"], "source": "regel",
         "items": [{"qty": 1, "nr": a["nr"] if a else "", "name": (a["name"] if a else v["name"]),
                    "descr": ((v.get("beschreibung") or "") + f"\nTermin {de_date(v.get('naechste') or today())}").strip(),
                    "price": float(v["preis"] or (a["price"] if a else 0)), "rabatt": 0, "article_id": v["article_id"]}]}
    iid, _ = save_invoice(d, bump=False)
    return iid


def _m86_mail(z, regel, obj, row, vals):
    to = _m86_mail_to(z, obj, row)
    if not to or "@" not in to:
        raise ValueError("keine E-Mail-Adresse (beim Kunden hinterlegen)")
    subj = _m86_fill(z.get("betreff"), obj, row, vals)
    body = _m86_fill(z.get("text"), obj, row, vals)
    att = []
    if z.get("anhang") and obj == "dok":
        inv = get_invoice(row["id"])
        if inv and inv.get("status") != "entwurf":
            s = get_settings()
            data = render_invoice_pdf(inv, s)
            att = [(os.path.basename(invoice_pdf_path(inv, s)), data)]
    send_mail(to, "", subj, body, att)
    try:
        x("INSERT INTO mail_log (doc_id, mahnung_id, an, betreff, datum, ok, fehler) VALUES (?,?,?,?,?,1,?)",
          (row.get("id") if obj == "dok" else None, None, to, subj, now_iso(), f"Regel: {regel.get('name')}"))
    except Exception:
        pass
    return f"Mail an {to}"

# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------


def _m86_key(regel, obj, row):
    if obj == "wartung":
        return f"wartung:{row.get('id')}:{row.get('naechste') or ''}"
    if obj == "tag":
        return f"tag:{today()}"
    # v2.0.19 (R4): + creation time - SQLite re-uses the id of a deleted newest row, the new
    # object must not count as "already done" (an undo restores the same creation time)
    cr = (row.get("created") or "")[:19]
    base = f"{obj}:{row.get('id')}" + (f"@{cr}" if cr else "")
    if regel.get("ausloeser") == "rechnung_ueberfaellig":
        return f"{base}:m{int(row.get('mahnstufe') or 0)}"
    return base


def _m86_done(rid, key):
    return bool(q("SELECT 1 FROM m86_done WHERE regel_id=? AND schluessel=?", (rid, key), one=True))


def _m86_claim(rid, key, force=False):
    """v2.0.19 (R4): check + mark in ONE step under DB_LOCK. Two threads (double click on save,
    API server m88, Abo run in the background) could both see 'not done' and both send the mail."""
    with DB_LOCK:
        if not force and _m86_done(rid, key):
            return False
        x("INSERT OR REPLACE INTO m86_done (regel_id, schluessel, zeit) VALUES (?,?,?)", (rid, key, now_iso()))
        return True


def _m86_log(regel, obj, oid, titel, aktion, ergebnis, ok):
    x("INSERT INTO m86_log (zeit, regel_id, regel, objekt, objekt_id, titel, aktion, ergebnis, ok) VALUES (?,?,?,?,?,?,?,?,?)",
      (now_iso(), regel.get("id"), regel.get("name"), obj, oid, (titel or "")[:200], (aktion or "")[:200], (ergebnis or "")[:400], 1 if ok else 0))


def m86_apply(regel, obj, oid, test=False):
    """runs one rule on one object; returns dict for test/log"""
    o = m86_obj(obj, oid)
    if not o:
        return None
    row, vals, titel = o
    key = _m86_key(regel, obj, row)
    ok, gruende = m86_match(regel, obj, row, vals)
    erledigt = bool(regel.get("id")) and _m86_done(regel["id"], key)
    out = {"objekt": obj, "id": row.get("id"), "titel": titel, "passt": ok, "gruende": gruende, "erledigt": erledigt,
           "aktionen": [m86_action_text(z, obj, row, vals) for z in regel.get("aktionen") or []]}
    if test or not ok:
        return out
    mail_key = "mail:" + key
    # "wiederholen" only for event triggers (every save / every new receipt). Periodic triggers run every
    # 10 minutes - they keep their once-per-period claim (day, due date, reminder level), otherwise
    # notes / drafts were created again on every run
    rep = bool(regel.get("wiederholen")) and regel.get("ausloeser") in M86_EVENT_AUSLOESER
    if erledigt and not rep:
        return out
    if not regel.get("id") or not regel.get("aktiv"):
        return out
    if not _m86_claim(regel["id"], key, force=rep):
        return out                                    # another thread was faster
    _m86_tl.busy = True
    try:
        for z in regel.get("aktionen") or []:
            if z.get("typ") == "mail" and not _m86_claim(regel["id"], mail_key):
                continue      # a mail is never sent twice for the same object
            try:
                res = m86_do(z, regel, obj, row, vals)
                _m86_log(regel, obj, row.get("id"), titel, M86_AKTIONEN.get(z.get("typ"), {}).get("label", z.get("typ")), res, True)
                o2 = m86_obj(obj, oid)
                if o2:
                    row, vals = o2[0], o2[1]
            except Exception as e:
                if z.get("typ") == "mail":
                    x("DELETE FROM m86_done WHERE regel_id=? AND schluessel=?", (regel["id"], mail_key))
                _m86_log(regel, obj, row.get("id"), titel, M86_AKTIONEN.get(z.get("typ"), {}).get("label", z.get("typ")), str(e), False)
    finally:
        _m86_tl.busy = False
    out["ausgefuehrt"] = True
    return out


def m86_event(ausloeser, obj, oid):
    if getattr(_m86_tl, "busy", False):
        return
    try:
        for r in m86_regeln(nur_aktiv=True):
            if r["ausloeser"] == ausloeser:
                m86_apply(r, obj, oid)
    except Exception:
        traceback.print_exc()


def m86_candidates(regel, test=False):
    a = regel.get("ausloeser")
    tage = int(regel.get("tage") or 0)
    if a == "beleg_neu":
        return "beleg", [r["id"] for r in q("SELECT id FROM belege ORDER BY id DESC LIMIT 30")] if test else []
    if a == "bank_neu":
        return "bank", [r["id"] for r in q("SELECT id FROM bank_tx ORDER BY id DESC LIMIT 30")] if test else []
    if a == "dok_gespeichert":
        return "dok", [r["id"] for r in q("SELECT id FROM invoices ORDER BY COALESCE(updated, created) DESC LIMIT 30")] if test else []
    if a == "rechnung_ueberfaellig":
        return "dok", [r["id"] for r in overdue_list() if int(r.get("tage") or 0) >= tage]
    if a == "angebot_offen":
        lim = (datetime.date.today() - datetime.timedelta(days=tage)).isoformat()
        return "dok", [r["id"] for r in q("SELECT id FROM invoices WHERE typ='angebot' AND status='offen' AND datum<=?", (lim,))]
    if a == "wartung_faellig":
        return "wartung", [v["id"] for v in vertraege_due()]
    if a == "taeglich":
        return "tag", [0]
    return "", []


def m86_test(d):
    regel = dict(d)
    regel["aktionen"] = [z for z in (d.get("aktionen") or []) if z.get("typ")]
    obj, ids = m86_candidates(regel, test=True)
    out = []
    for oid in ids:
        r = m86_apply(regel, obj, oid, test=True)
        if r:
            out.append(r)
    return {"ok": True, "treffer": [r for r in out if r["passt"]], "gesamt": len(out),
            "hinweis": {"beleg_neu": "geprüft: die letzten 30 Belege", "bank_neu": "geprüft: die letzten 30 Bankbuchungen",
                        "dok_gespeichert": "geprüft: die 30 zuletzt gespeicherten Dokumente"}.get(regel.get("ausloeser"), "geprüft: alles, was jetzt fällig ist")}


def m86_run_periodic(only_id=None):
    if not M86_STATE["lock"].acquire(blocking=False):
        return 0
    n = 0
    try:
        for r in m86_regeln(nur_aktiv=True):
            if only_id and r["id"] != int(only_id):
                continue
            if r["ausloeser"] in M86_EVENT_AUSLOESER:
                continue
            obj, ids = m86_candidates(r)
            for oid in ids:
                res = m86_apply(r, obj, oid)
                if res and res.get("ausgefuehrt"):
                    n += 1
    except Exception:
        traceback.print_exc()
    finally:
        M86_STATE["lock"].release()
    return n


def m86_loop():
    time.sleep(90)
    while True:
        try:
            m86_run_periodic()
        except Exception:
            traceback.print_exc()
        time.sleep(600)


HOOK_START.append(m86_loop)

# ---------------------------------------------------------------------------
# hooks into existing functions
# ---------------------------------------------------------------------------
def _m86_has(ausloeser):
    try:
        return bool(q("SELECT 1 FROM m86_regel WHERE aktiv=1 AND ausloeser=? LIMIT 1", (ausloeser,), one=True))
    except Exception:
        return False   # table not created yet (first start, seed data)


_M86_INS = re.compile(r"^\s*INSERT(?:\s+OR\s+\w+)?\s+INTO\s+(belege|bank_tx)\b", re.I)
_m86_orig_x = chain_inner("x", "m86_regeln")   # v3.1.0: the level below this module
@chain_step("x", "m86_regeln")
def _m86_step_x(_next, sql, args=()):
    rid = _next(sql, args)
    if rid and not getattr(_m86_tl, "busy", False):
        m = _M86_INS.match(sql) if isinstance(sql, str) else None
        if m:
            try:
                if _m86_has("beleg_neu" if m.group(1).lower() == "belege" else "bank_neu"):
                    m86_event("beleg_neu" if m.group(1).lower() == "belege" else "bank_neu", "beleg" if m.group(1).lower() == "belege" else "bank", rid)
            except Exception:
                traceback.print_exc()
    return rid


@chain_step("save_invoice", "m86_regeln")
def _m86_step_save_invoice(_next, d, bump=True):
    r = _next(d, bump)
    if not getattr(_m86_tl, "busy", False):
        try:
            iid = r[0] if isinstance(r, (tuple, list)) else r
            if iid and _m86_has("dok_gespeichert"):
                m86_event("dok_gespeichert", "dok", int(iid))
        except Exception:
            traceback.print_exc()
    return r

# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


def _m86_meta():
    kat = list(EUER_KATEGORIEN) if "EUER_KATEGORIEN" in globals() else []
    m85 = []
    try:
        m85 = [{"id": f["id"], "objekt": f["objekt"], "name": f["name"]} for f in m85_felder()]
    except Exception:
        pass
    return {"ausloeser": M86_AUSLOESER, "felder": M86_FELDER, "ops": M86_OPS, "aktionen": M86_AKTIONEN, "kategorien": kat, "m85": m85,
            "projekte": q("SELECT id, nr, name FROM projects ORDER BY status, nr DESC")}


def _m86_r_list(h, qs):
    rs = m86_regeln()
    stat = {r["regel_id"]: r for r in q("SELECT regel_id, COUNT(*) n, MAX(zeit) z, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) f FROM m86_log GROUP BY regel_id")}
    for r in rs:
        s_ = stat.get(r["id"]) or {}
        r["n"], r["letzte"], r["fehler"] = s_.get("n", 0), s_.get("z", ""), s_.get("f", 0)
    return h._send(200, {"regeln": rs, "meta": _m86_meta(),
                         "log": q("SELECT * FROM m86_log ORDER BY id DESC LIMIT 300")})


def _m86_r_save(h, d):
    return h._send(200, {"ok": True, "id": m86_save(d)})


def _m86_r_del(h, d):
    rid = int(d["id"])
    x("DELETE FROM m86_regel WHERE id=?", (rid,))
    # v2.0.19 (R4): "already done" / "mail sent" entries stay: m89 restores the rule with "Rueckgaengig"
    # (m86_done is not recorded there), it must not mail every object again; ids are never re-used
    return h._send(200, {"ok": True})


def _m86_r_toggle(h, d):
    x("UPDATE m86_regel SET aktiv=?, updated=? WHERE id=?", (1 if d.get("aktiv") else 0, now_iso(), int(d["id"])))
    return h._send(200, {"ok": True})


def _m86_r_test(h, d):
    return h._send(200, m86_test(d))


def _m86_r_run(h, d):
    return h._send(200, {"ok": True, "n": m86_run_periodic(d.get("id"))})


def _m86_r_reset(h, d):
    """forget 'already done' for a rule (it may fire again for every object - mails included)"""
    x("DELETE FROM m86_done WHERE regel_id=?", (int(d["id"]),))
    return h._send(200, {"ok": True})


def _m86_r_hinweise(h, qs):
    return h._send(200, {"hinweise": q("SELECT * FROM m86_hinweis WHERE erledigt=0 ORDER BY id DESC LIMIT 50")})


def _m86_r_hinweis_ok(h, d):
    if d.get("alle"):
        x("UPDATE m86_hinweis SET erledigt=1 WHERE erledigt=0")
    else:
        x("UPDATE m86_hinweis SET erledigt=1 WHERE id=?", (int(d["id"]),))
    return h._send(200, {"ok": True})


def _m86_boot(d):
    try:
        d["m86_hinweise"] = q("SELECT COUNT(*) n FROM m86_hinweis WHERE erledigt=0", one=True)["n"]
    except Exception:
        d["m86_hinweise"] = 0


HOOK_GET["/api/m86/list"] = _m86_r_list
HOOK_GET["/api/m86/hinweise"] = _m86_r_hinweise
HOOK_POST["/api/m86/save"] = _m86_r_save
HOOK_POST["/api/m86/delete"] = _m86_r_del
HOOK_POST["/api/m86/toggle"] = _m86_r_toggle
HOOK_POST["/api/m86/test"] = _m86_r_test
HOOK_POST["/api/m86/run"] = _m86_r_run
HOOK_POST["/api/m86/reset"] = _m86_r_reset
HOOK_POST["/api/m86/hinweis_ok"] = _m86_r_hinweis_ok
HOOK_BOOT.append(_m86_boot)


def _m86_ex(p):
    rows = [[r["zeit"][:16].replace("T", " "), r["regel"] or "", r["titel"] or "", r["aktion"] or "", r["ergebnis"] or "", "ok" if r["ok"] else "Fehler"]
            for r in q("SELECT * FROM m86_log ORDER BY id DESC LIMIT 5000")]
    return [_sh("Regel-Protokoll", [("Zeit", "t", 16), ("Regel", "t", 22), ("Objekt", "t", 34), ("Aktion", "t", 20), ("Ergebnis", "t", 34), ("Status", "t", 8)],
                rows, f"Stand {de_date(today())}", False)]


EXPORTS["m86_log"] = ("Regel_Protokoll", _m86_ex)


def _m86_selftest():
    err = []
    try:
        bid = _m86_orig_x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created) VALUES "
                          "('ausgabe',?,?,?,?,?,?,'','{}',?)", (today(), "_ST Thomann GmbH", "R-1", 39.0, "Sonstige Betriebsausgaben", "", now_iso()))
        kat = EUER_KATEGORIEN[0] if EUER_KATEGORIEN else "Wareneinkauf"
        rid = m86_save({"name": "_ST Regel", "ausloeser": "beleg_neu", "bedingungen": [{"feld": "partner", "op": "enthaelt", "wert": "thomann"},
                                                                                        {"feld": "betrag", "op": "groesser", "wert": "10"}],
                        "aktionen": [{"typ": "kategorie", "wert": kat}, {"typ": "notiz", "wert": "Regel [Partner]"}]})
        t = m86_test(dict(m86_regeln()[-1]))
        if not any(r["id"] == bid for r in t["treffer"]):
            err.append("m86: Testlauf findet den passenden Beleg nicht")
        if q("SELECT kategorie FROM belege WHERE id=?", (bid,), one=True)["kategorie"] == kat and kat != "Sonstige Betriebsausgaben":
            err.append("m86: Testlauf hat etwas geaendert")
        regel = [r for r in m86_regeln() if r["id"] == rid][0]
        m86_apply(regel, "beleg", bid)
        b = q("SELECT kategorie, notiz FROM belege WHERE id=?", (bid,), one=True)
        if b["kategorie"] != kat or "Regel _ST Thomann" not in (b["notiz"] or ""):
            err.append(f"m86: Aktion nicht ausgefuehrt ({b})")
        m86_apply(regel, "beleg", bid)
        if (q("SELECT notiz FROM belege WHERE id=?", (bid,), one=True)["notiz"] or "").count("Regel") != 1:
            err.append("m86: Regel wurde fuer dasselbe Objekt zweimal ausgefuehrt")
        if m86_cond({"feld": "betrag", "op": "kleiner", "wert": "20"}, "beleg", {}, {"betrag": 39.0}):
            err.append("m86: Vergleich kleiner falsch")
        x("DELETE FROM m86_done WHERE regel_id=?", (rid,))
        x("DELETE FROM m86_log WHERE regel_id=?", (rid,))
        x("DELETE FROM m86_regel WHERE id=?", (rid,))
        _m86_orig_x("DELETE FROM belege WHERE id=?", (bid,))
    except Exception as e:
        err.append(f"m86 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m86_selftest)
