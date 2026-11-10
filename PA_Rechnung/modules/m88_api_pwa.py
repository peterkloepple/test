# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m88_api_pwa (v2.0.19, Baustellen-Modus ab v3.5.0, Kalender ab v3.6.2)
# v1.5.0: Abgleich-Zugang (Token-Art sync) auf /sync/ zaehlt nicht zum Anfragen-Limit (Dateipakete, Live-Warten).
# v1.4.0: Abgleich mit Mobilgeraeten (m58) unter /sync/ - eigener Zugang (Token-Art sync, nur fuer /sync/).
# v1.3.0: iPhone-App (nativ): Kopplung liefert der App den Token im Klartext (nur bei {"app": true}, einmalig);
#         Handy-Seite zeigt in der App "Dokument scannen" und ein Zahnrad fuer die App-Einstellungen.
# v1.2.0: Kalender in der Handy-App (/v1/kalender, /v1/kalender/abos, /v1/kalender/abrufen) - alle Kalender inkl. Abos.
#         Fremde Webseiten bekommen nichts: Anfragen, die eine andere Seite im Browser ausloest (Sec-Fetch-Site:
#         cross-site), werden fuer /v1, /pair, /logout abgewiesen; Cross-Origin-Resource-Policy same-origin.
# Schnittstelle & Handy: zweiter kleiner HTTP-Server (Standard AUS) mit
#  - REST-API /v1/... (JSON, Authorization: Bearer <token>), Rechte lesen / schreiben
#  - Handy-Ansicht als PWA unter "/" (Kopplung per QR-Code oder Kopplungscode, Cookie HttpOnly)
#  - Kalender-Abo /ics/<token>.ics (liefert m84_ics, falls das Modul m84 vorhanden ist)
# Tokens werden nur als SHA-256 gespeichert und nur einmal im Klartext angezeigt.
# Rate-Limit je IP, Sperre nach vielen Fehlversuchen, Zugriffsprotokoll (m88_log).
# Es wird KEIN SQL von aussen angenommen - alle Antworten kommen aus vorhandenen Programmfunktionen.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import secrets
import collections

M88_VERSION = "1.5.0"
M88_DEFAULTS = {"aktiv": False, "port": 8780, "modus": "lokal", "rate": 120, "geraet_tage": 365}
M88_PAIR_TTL = 10 * 60
M88_MAX_UPLOAD_MB = 25
M88_ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
M88 = {"srv": None, "host": "", "port": 0, "fehler": "", "gestartet": "", "pair": None, "lock": threading.Lock(),
       "rate": collections.defaultdict(collections.deque), "fails": collections.defaultdict(collections.deque),
       "log_n": 0}


# ---------------------------------------------------------------------------- schema / config
def _m88_schema():
    x("CREATE TABLE IF NOT EXISTS m88_token (id INTEGER PRIMARY KEY, name TEXT, hash TEXT UNIQUE, prefix TEXT, recht TEXT, "
      "typ TEXT, erstellt TEXT, zuletzt TEXT, zuletzt_ip TEXT, aktiv INTEGER DEFAULT 1, widerrufen TEXT, ablauf TEXT)")
    x("CREATE TABLE IF NOT EXISTS m88_log (id INTEGER PRIMARY KEY, zeit TEXT, ip TEXT, methode TEXT, pfad TEXT, status INTEGER, "
      "token TEXT, info TEXT)")
    x("CREATE TABLE IF NOT EXISTS m88_notiz (id INTEGER PRIMARY KEY, zeit TEXT, text TEXT, quelle TEXT, erledigt INTEGER DEFAULT 0)")
    # calendar links made by the settings page before it sent typ "ics" were read tokens named "Kalender-Abo":
    # they become ics tokens (keep working for /ics/, no longer open the whole read API)
    x("UPDATE m88_token SET typ='ics' WHERE typ='api' AND recht='lesen' AND name='Kalender-Abo'")
    # raw tokens in old access-log rows (path /ics/<token>.ics) are masked
    for r_ in q("SELECT id, pfad FROM m88_log WHERE pfad LIKE '/ics/%' OR pfad LIKE '%pa88_%'"):
        if m88_mask(r_["pfad"]) != r_["pfad"]:
            x("UPDATE m88_log SET pfad=? WHERE id=?", (m88_mask(r_["pfad"]), r_["id"]))


HOOK_SCHEMA.append(_m88_schema)


def m88_cfg():
    c = dict(M88_DEFAULTS)
    c.update(get_settings().get("m88") or {})
    try:
        c["port"] = max(1024, min(65535, int(float(c.get("port") or 8780))))
    except Exception:
        c["port"] = 8780
    try:
        c["rate"] = max(10, min(2000, int(float(c.get("rate") or 120))))
    except Exception:
        c["rate"] = 120
    c["modus"] = "lan" if c.get("modus") == "lan" else "lokal"
    c["aktiv"] = bool(c.get("aktiv"))
    return c


def _m88_hash(tok):
    return hashlib.sha256(("pa88|" + (tok or "")).encode("utf-8")).hexdigest()


def m88_token_new(name, recht="lesen", typ="api", tage=None):
    recht = "schreiben" if recht == "schreiben" else "lesen"
    tok = "pa88_" + secrets.token_urlsafe(24)
    ablauf = ""
    if tage:
        ablauf = (datetime.datetime.now() + datetime.timedelta(days=int(tage))).isoformat(timespec="seconds")
    tid = x("INSERT INTO m88_token (name, hash, prefix, recht, typ, erstellt, aktiv, ablauf) VALUES (?,?,?,?,?,?,1,?)",
            ((name or "").strip()[:60] or ("Handy" if typ == "geraet" else "Zugang"), _m88_hash(tok), tok[:9] + "…", recht, typ,
             now_iso(), ablauf))
    return tid, tok


def m88_check_token(tok):
    """-> token row or None"""
    if not tok or len(tok) > 200:
        return None
    r = q("SELECT * FROM m88_token WHERE hash=? AND aktiv=1", (_m88_hash(tok),), one=True)
    if not r:
        return None
    # ablauf is stored as "YYYY-MM-DDTHH:MM:SS" - compare in the same format (now_iso() uses a blank instead of "T")
    if r.get("ablauf") and r["ablauf"] < datetime.datetime.now().isoformat(timespec="seconds"):
        return None
    return r


def m88_tokens():
    return q("SELECT id, name, prefix, recht, typ, erstellt, zuletzt, zuletzt_ip, aktiv, widerrufen, ablauf FROM m88_token "
             "ORDER BY aktiv DESC, id DESC")


_M88_RX_ICS = re.compile(r"^(/ics/)([A-Za-z0-9_\-]{10,200})")     # 9 chars = already masked (same as the shown prefix)
_M88_RX_TOK = re.compile(r"pa88_[A-Za-z0-9_\-]{5,}")


def m88_mask(pfad):
    """no token in clear text in the access log: /ics/<token>.ics and pa88_... anywhere in path/query"""
    p = str(pfad or "")
    p = _M88_RX_ICS.sub(lambda m: m.group(1) + m.group(2)[:9] + "…", p)
    return _M88_RX_TOK.sub(lambda m: m.group(0)[:9] + "…", p)


def m88_log(ip, meth, pfad, status, tok_name="", info=""):
    pfad = m88_mask(pfad)
    try:
        x("INSERT INTO m88_log (zeit, ip, methode, pfad, status, token, info) VALUES (?,?,?,?,?,?,?)",
          (now_iso(), ip, meth, (pfad or "")[:200], int(status), (tok_name or "")[:60], (info or "")[:200]))
        M88["log_n"] += 1
        if M88["log_n"] % 100 == 0:
            x("DELETE FROM m88_log WHERE id NOT IN (SELECT id FROM m88_log ORDER BY id DESC LIMIT 3000)")
    except Exception:
        pass


# ---------------------------------------------------------------------------- data (read)
def _m88_cust(r):
    return {"id": r["id"], "kdnr": r.get("kdnr") or "", "name": r.get("firma") or r.get("name") or r.get("kdnr") or "",
            "ansprechpartner": r.get("name") if r.get("firma") else "", "strasse": r.get("strasse") or "",
            "plz": r.get("plz") or "", "ort": r.get("ort") or "", "tel": r.get("tel") or "", "mobil": r.get("mobil") or "",
            "mail": r.get("mail") or "", "web": r.get("web") or "", "gruppe": r.get("gruppe") or ""}


def m88_kunden(qs):
    rows = q("SELECT * FROM customers ORDER BY COALESCE(NULLIF(firma,''), name)")
    t = (qs.get("q") or "").strip().lower()
    out = [_m88_cust(r) for r in rows]
    if t:
        out = [c for c in out if t in " ".join(str(v) for v in c.values()).lower()]
    return {"anzahl": len(out), "kunden": out}


def _m88_faellig(r):
    d0 = d_iso(r.get("datum"))
    if not d0:
        return "", 0
    due = d0 + datetime.timedelta(days=_frist(r.get("frist")))
    return due.isoformat(), (datetime.date.today() - due).days


def _m88_rest(r):
    """open amount of an invoice - partial payments / discount / write-off from m71 are taken into account"""
    if r.get("status") != "offen":
        return 0.0
    fn = globals().get("m71_state")
    if callable(fn) and r.get("id"):
        try:
            return round(float(fn(r)["rest"]), 2)
        except Exception:
            pass
    return round(float(r.get("summe") or 0), 2)


def _m88_inv_row(r):
    f, tage = _m88_faellig(r)
    return {"id": r["id"], "nr": r.get("nr") or "", "typ": r.get("typ") or "rechnung", "datum": r.get("datum") or "",
            "kunde": inv_name(r), "customer_id": r.get("customer_id"), "project_id": r.get("project_id"),
            "titel": r.get("titel") or "", "summe": round(float(r.get("summe") or 0), 2), "offen": _m88_rest(r), "status": r.get("status") or "",
            "bezahlt_am": r.get("bezahlt_am") or "", "faellig": f, "tage_ueberfaellig": max(0, tage) if r.get("status") == "offen" else 0,
            "mahnstufe": int(r.get("mahnstufe") or 0), "gueltig_bis": r.get("gueltig_bis") or ""}


def m88_rechnungen(qs):
    sql, args = "SELECT * FROM invoices WHERE 1=1", []
    typ = (qs.get("typ") or "rechnung").strip()
    if typ != "alle":
        sql += " AND typ=?"
        args.append(typ)
    if qs.get("status"):
        sql += " AND status=?"
        args.append(qs["status"].strip())
    if qs.get("jahr") and str(qs["jahr"]).isdigit():
        sql += " AND substr(datum,1,4)=?"
        args.append(str(qs["jahr"]))
    if qs.get("kunde") and str(qs["kunde"]).isdigit():
        sql += " AND customer_id=?"
        args.append(int(qs["kunde"]))
    try:
        lim = max(1, min(1000, int(qs.get("limit") or 200)))
    except Exception:
        lim = 200
    sql += " ORDER BY datum DESC, nr DESC LIMIT ?"
    args.append(lim)
    out = [_m88_inv_row(r) for r in q(sql, tuple(args))]
    t = (qs.get("q") or "").strip().lower()
    if t:
        out = [r for r in out if t in (r["nr"] + " " + r["kunde"] + " " + r["titel"]).lower()]
    return {"anzahl": len(out), "summe": round(sum(r["summe"] for r in out), 2), "rechnungen": out}


def m88_rechnung(iid):
    inv = get_invoice(int(iid))
    if not inv:
        return None
    r = _m88_inv_row(inv)
    r.update({"anschrift": inv.get("addr") or [], "zahlart": inv.get("zahlart") or "", "frist": inv.get("frist"),
              "liefer": inv.get("liefer") or "", "toptext": inv.get("toptext") or "", "foottext": inv.get("foottext") or "",
              "positionen": [{"pos": i.get("pos"), "menge": i.get("qty"), "nr": i.get("nr") or "", "name": i.get("name") or "",
                              "beschreibung": i.get("descr") or "", "preis": i.get("price"), "rabatt": i.get("rabatt") or 0,
                              "gesamt": item_total(inv, i)}
                             for i in inv.get("items") or []],
              "mahnungen": [{"stufe": m.get("stufe"), "datum": m.get("datum"), "betrag": m.get("betrag")} for m in inv.get("mahnungen") or []]})
    return r


def m88_rechnung_pdf(iid):
    inv = get_invoice(int(iid))
    if not inv:
        return None, ""
    s = get_settings()
    try:
        fp = invoice_pdf_path(inv, s)
        if inv.get("locked") and os.path.isfile(fp):
            return open(fp, "rb").read(), os.path.basename(fp)
    except Exception:
        pass
    return render_invoice_pdf(inv, s), safe_name(f"{inv.get('typ') or 'rechnung'}_{inv.get('nr') or iid}.pdf")


def m88_offene_posten():
    rows = [_m88_inv_row(r) for r in q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen' ORDER BY datum")]
    rows.sort(key=lambda r: (-r["tage_ueberfaellig"], r["faellig"]))
    ueb = [r for r in rows if r["tage_ueberfaellig"] > 0]
    # "summe" = still open (after partial payments), "rechnungen_summe" = gross amount of these invoices
    return {"anzahl": len(rows), "summe": round(sum(r["offen"] for r in rows), 2), "rechnungen_summe": round(sum(r["summe"] for r in rows), 2),
            "ueberfaellig_anzahl": len(ueb), "ueberfaellig_summe": round(sum(r["offen"] for r in ueb), 2), "posten": rows}


def m88_projekte(qs):
    sql, args = "SELECT * FROM projects", ()
    st = (qs.get("status") or "").strip()
    if st and st != "alle":
        sql, args = sql + " WHERE status=?", (st,)
    cm = {c["id"]: (c.get("firma") or c.get("name") or "") for c in q("SELECT id, firma, name FROM customers")}
    out = []
    for p in q(sql + " ORDER BY status, start DESC", args):
        h = q("SELECT COALESCE(SUM(qty),0) h FROM project_entries WHERE project_id=? AND art='Arbeitszeit'", (p["id"],), one=True)["h"]
        out.append({"id": p["id"], "nr": p.get("nr") or "", "name": p.get("name") or "", "kunde": cm.get(p.get("customer_id"), ""),
                    "customer_id": p.get("customer_id"), "bereich": p.get("bereich") or "", "status": p.get("status") or "",
                    "start": p.get("start") or "", "ende": p.get("ende") or "", "stunden": round(float(h or 0), 2)})
    return {"anzahl": len(out), "projekte": out}


# v3.5.0: Baustellen-Modus - project folder on the phone (address, phone, hours, measurements, photos)
def m88_kalender(qs):
    """v1.2.0: appointments of all active calendars (TimeTree, .ics, Kalender-Abos, program) for the phone app"""
    fn = globals().get("kal_events")
    if not callable(fn):
        raise M88NotFound("Kalender nicht verfügbar.")
    von = qs.get("von") or today()
    try:
        bis = qs.get("bis") or (datetime.date.fromisoformat(von[:10]) + datetime.timedelta(days=14)).isoformat()
        d0, d1 = datetime.date.fromisoformat(von[:10]), datetime.date.fromisoformat(bis[:10])
    except ValueError:
        raise ValueError("Datum bitte als JJJJ-MM-TT.")
    if (d1 - d0).days > 400:
        raise ValueError("Zeitraum zu groß (höchstens 400 Tage).")
    evs = fn(von[:10], bis[:10], qs.get("q") or "")
    cals = {}
    try:
        for c in q("SELECT id, name, farbe, quelle FROM kal_cal WHERE aktiv=1"):
            cals[c["id"]] = c
    except Exception:
        pass
    return {"von": von[:10], "bis": bis[:10], "termine": evs, "kalender": list(cals.values())}


def m88_kalender_abos():
    fn = globals().get("abo_view")
    if not callable(fn):
        return {"abos": []}
    out = []
    for a in fn().get("abos", []):
        l_ = a.get("letzter") or {}
        out.append({"name": a.get("name"), "farbe": a.get("farbe"), "termine": a.get("termine"), "aktiv": a.get("aktiv"),
                    "zuletzt": l_.get("zeit") or "", "ok": l_.get("ok"), "text": l_.get("text") or ""})
    return {"abos": out}


def m88_projekt(pid):
    p = q("SELECT * FROM projects WHERE id=?", (int(pid),), one=True)
    if not p:
        raise M88NotFound("Projekt nicht gefunden.")
    c = q("SELECT * FROM customers WHERE id=?", (p.get("customer_id"),), one=True) if p.get("customer_id") else None
    h = q("SELECT COALESCE(SUM(qty),0) h FROM project_entries WHERE project_id=? AND art='Arbeitszeit'", (p["id"],), one=True)["h"]
    am = []
    if "m41_aufmass_save" in globals():
        am = q("SELECT id, pos, beschreibung, l, b, h, anz, einheit, ergebnis, created FROM m41_aufmass WHERE project_id=? "
               "ORDER BY id DESC LIMIT 12", (p["id"],))
    files = q("SELECT id, name, folder, kind, added FROM project_files WHERE project_id=? ORDER BY id DESC LIMIT 12", (p["id"],))
    adr = ""
    if c:
        adr = ", ".join(x_ for x_ in ((c.get("strasse") or "").strip(), " ".join(y_ for y_ in ((c.get("plz") or "").strip(), (c.get("ort") or "").strip()) if y_)) if x_)
    return {"ok": True, "id": p["id"], "nr": p.get("nr") or "", "name": p.get("name") or "", "status": p.get("status") or "",
            "beschreibung": (p.get("descr") or "")[:1000], "stunden": round(float(h or 0), 2),
            "kunde": ({"name": c.get("firma") or c.get("name") or "", "ansprechpartner": c.get("name") or "", "adresse": adr,
                       "tel": c.get("tel") or "", "mobil": c.get("mobil") or "", "mail": c.get("mail") or ""} if c else None),
            "aufmass": am, "dateien": files, "einheiten": list(globals().get("M41_EINHEITEN") or ["Stk"]), "aufmass_ok": "m41_aufmass_save" in globals()}


def m88_aufmass(d):
    if "m41_aufmass_save" not in globals():
        raise ValueError("Aufmaß ist in diesem Programm nicht verfügbar.")
    pid = _m88_id(d.get("project_id"), "Projekt")
    if not q("SELECT id FROM projects WHERE id=?", (pid,), one=True):
        raise ValueError("Projekt nicht gefunden.")
    if not (d.get("beschreibung") or "").strip():
        raise ValueError("Bitte eine Beschreibung eingeben.")
    rid = m41_aufmass_save({"project_id": pid, "beschreibung": (d.get("beschreibung") or "").strip()[:300], "pos": (d.get("pos") or "").strip()[:20],
                            "modus": "lbh", "l": d.get("l"), "b": d.get("b"), "h": d.get("h"), "anz": d.get("anz") or 1,
                            "einheit": d.get("einheit") or "Stk"})
    r = q("SELECT ergebnis, einheit FROM m41_aufmass WHERE id=?", (rid,), one=True)
    return {"ok": True, "id": rid, "ergebnis": r["ergebnis"], "einheit": r["einheit"]}


def m88_kennzahlen(qs):
    try:
        y = int(qs.get("jahr") or datetime.date.today().year)
    except Exception:
        y = datetime.date.today().year
    st = stats(y)
    e = euer(y)
    op = m88_offene_posten()
    k = kontostand_info()
    out = {"jahr": y, "umsatz": round(float(st.get("total") or 0), 2), "anzahl_rechnungen": st.get("anzahl") or 0,
           "einnahmen": e.get("einnahmen"), "ausgaben": e.get("ausgaben"), "gewinn": e.get("gewinn"),
           "offen_summe": op["summe"], "offen_anzahl": op["anzahl"], "ueberfaellig_summe": op["ueberfaellig_summe"],
           "ueberfaellig_anzahl": op["ueberfaellig_anzahl"],
           "kontostand": (k or {}).get("saldo"),"kontostand_datum": (k or {}).get("datum") or "",
           "monate": [{"monat": m["m"], "umsatz": round(m["umsatz"], 2), "zufluss": round(m["zufluss"], 2),
                       "ausgaben": round(m["ausgaben"], 2)} for m in st.get("months") or []]}
    try:
        if "m54_ruecklage" in globals() and y == datetime.date.today().year:
            r = m54_ruecklage(y)
            out["ruecklage_monat"] = r.get("monat")
    except Exception:
        pass
    return out


def m88_lager(qs):
    if "m42_list" not in globals():
        return {"anzahl": 0, "artikel": [], "hinweis": "Lager-Modul nicht vorhanden"}
    rows = m42_list("nachbestellen" if qs.get("filter") == "nachbestellen" else "")
    out = [{"id": r["id"], "nr": r.get("nr") or "", "name": r.get("name") or "", "kategorie": r.get("kategorie") or "",
            "einheit": r.get("einheit") or "", "bestand": r.get("bestand") or 0, "mindest": r.get("mindest") or 0,
            "lagerort": r.get("lagerort") or "", "nachbestellen": bool(r.get("nachbestellen"))} for r in rows if r.get("aktiv")]
    return {"anzahl": len(out), "artikel": out}


def m88_bausteine():
    return {"bausteine": [{"id": a["id"], "nr": a.get("nr") or "", "name": a.get("name") or "", "preis": a.get("price") or 0,
                           "einheit": a.get("unit") or "", "kategorie": a.get("cat") or ""}
                          for a in q("SELECT * FROM articles WHERE active=1 ORDER BY cat, sort, nr")]}


def m88_status():
    s = get_settings()
    t = s.get("timer")
    tp = None
    if t:
        p = q("SELECT id, nr, name FROM projects WHERE id=?", (t.get("project_id"),), one=True)
        tp = {"project_id": t.get("project_id"), "projekt": (p or {}).get("name") or "", "start": t.get("start")}
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION, "api": M88_VERSION, "firma": s.get("firma") or "",
            "zeit": now_iso(), "timer": tp, "stundensatz": float(s.get("stundensatz") or 0)}


def m88_notizen(nur_offen=True):
    return q("SELECT * FROM m88_notiz " + ("WHERE erledigt=0 " if nur_offen else "") + "ORDER BY erledigt, id DESC LIMIT 300")


# ---------------------------------------------------------------------------- data (write)
def _m88_f(v, name):
    if v in (None, ""):
        raise ValueError(f"{name} fehlt.")
    if isinstance(v, bool):
        raise ValueError(f"{name} ist keine Zahl.")
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(parse_amount(str(v).replace(" ", "")))     # "1,5" / "1.234,5" / "1234.5"
    except Exception:
        raise ValueError(f"{name} ist keine Zahl ({str(v)[:20]}).")


def _m88_id(v, name):
    try:
        return int(str(v if v is not None else "").strip() or 0)
    except ValueError:
        raise ValueError(f"{name} ist keine Nummer.")


def _m88_date(v):
    v = (v or "").strip()
    if not v:
        return today()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    d = iso_from_de(v)
    if not d:
        raise ValueError("Datum unbekannt (JJJJ-MM-TT oder TT.MM.JJJJ).")
    return d


def m88_zeit(d):
    pid = _m88_id(d.get("project_id"), "project_id")
    p = q("SELECT id, name FROM projects WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("Projekt nicht gefunden (project_id).")
    h = _m88_f(d.get("stunden") if d.get("stunden") not in (None, "") else (
        (_m88_f(d.get("minuten"), "Dauer") / 60.0) if d.get("minuten") not in (None, "") else None), "Dauer (stunden oder minuten)")
    if h <= 0 or h > 24:
        raise ValueError("Dauer muss zwischen 0 und 24 Stunden liegen.")
    s = get_settings()
    a = q("SELECT * FROM articles WHERE id=?", (int(d["article_id"]),), one=True) if str(d.get("article_id") or "").isdigit() else None
    eid = x("INSERT INTO project_entries (project_id, datum, art, nr, name, descr, qty, unit, price, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, _m88_date(d.get("datum")), "Arbeitszeit", a["nr"] if a else "", a["name"] if a else "Arbeitszeit",
             (d.get("text") or "")[:300], round(h, 2), "Std", float(a["price"]) if a else float(s.get("stundensatz") or 0), now_iso()))
    return {"ok": True, "id": eid, "stunden": round(h, 2), "projekt": p["name"]}


def m88_fahrt(d):
    km = _m88_f(d.get("km"), "km")
    if km <= 0 or km > 5000:
        raise ValueError("km unplausibel.")
    art = "pendel" if d.get("art") == "pendel" else "dienst"
    ziel = (d.get("ziel") or "").strip()[:120]
    if not ziel:
        raise ValueError("Ziel fehlt.")
    pid = int(d["project_id"]) if str(d.get("project_id") or "").isdigit() else None
    cid = int(d["customer_id"]) if str(d.get("customer_id") or "").isdigit() else None
    fid = x("INSERT INTO fahrten (datum, ziel, zweck, km, art, project_id, customer_id, notiz) VALUES (?,?,?,?,?,?,?,?)",
            (_m88_date(d.get("datum")), ziel, (d.get("zweck") or "")[:200], km, art, pid, cid, (d.get("notiz") or "")[:200]))
    return {"ok": True, "id": fid}


def m88_notiz(d, quelle="API"):
    t = (d.get("text") or "").strip()
    if not t:
        raise ValueError("Text fehlt.")
    nid = x("INSERT INTO m88_notiz (zeit, text, quelle, erledigt) VALUES (?,?,?,0)", (now_iso(), t[:2000], (quelle or "API")[:60]))
    return {"ok": True, "id": nid}


def m88_timer_start(d):
    pid = _m88_id(d.get("project_id"), "project_id")
    if not q("SELECT id FROM projects WHERE id=?", (pid,), one=True):
        raise ValueError("Projekt nicht gefunden.")
    with TIMER_LOCK:   # v2.1.1 (lock from m18, shared with the PC route): two simultaneous starts (handy + PC) must not both pass the check
        if get_settings().get("timer"):
            raise ValueError("Es läuft bereits eine Stoppuhr - zuerst stoppen oder verwerfen.")
        set_setting("timer", {"project_id": pid, "start": datetime.datetime.now().isoformat(timespec="seconds")})
    return {"ok": True}


# ---------------------------------------------------------------------------- PWA content
M88_CSS = """:root{--bg:#f4f3f8;--panel:#fff;--line:#e6e3ef;--ink:#1c1a26;--ink2:#4a4659;--mute:#8a8599;--acc:#6a48e0;--acc2:#5434c8;
--accsoft:#efeafe;--ok:#1f9d6b;--bad:#c8323c;--warn:#c27c0e}
@media (prefers-color-scheme:dark){:root{--bg:#15131c;--panel:#1f1c29;--line:#2f2b3d;--ink:#ece9f5;--ink2:#c3bed3;--mute:#8f89a3;
--acc:#8b6df0;--acc2:#a28cf5;--accsoft:#2a2440}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--acc);color:#fff;padding:calc(env(safe-area-inset-top) + 12px) 16px 12px;display:flex;align-items:center;gap:10px}
header h1{font-size:19px;margin:0;flex:1;font-weight:650}header button{background:rgba(255,255,255,.18);color:#fff;border:0;border-radius:10px;padding:7px 11px;font-size:14px}
main{padding:14px 14px calc(86px + env(safe-area-inset-bottom));max-width:720px;margin:0 auto}
nav{position:fixed;bottom:0;left:0;right:0;z-index:5;background:var(--panel);border-top:1px solid var(--line);display:flex;padding-bottom:env(safe-area-inset-bottom)}
nav button{flex:1;background:none;border:0;color:var(--mute);font-size:11px;padding:8px 0 7px;display:flex;flex-direction:column;align-items:center;gap:2px}
nav button svg{width:23px;height:23px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
nav button.on{color:var(--acc)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:13px 14px;margin:0 0 10px}
.card>b:first-child{display:block;margin-bottom:6px}.row{display:flex;gap:10px;align-items:center}.sp{flex:1;min-width:0}.mute{color:var(--mute);font-size:13px}.r{text-align:right}
.big{font-size:22px;font-weight:650}.kpis{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}.kpis .card{margin:0}
.badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:20px;background:var(--accsoft);color:var(--acc2)}
.badge.bad{background:rgba(200,50,60,.12);color:var(--bad)}.badge.ok{background:rgba(31,157,107,.12);color:var(--ok)}
.ell{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
input,select,textarea{width:100%;font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:11px 12px;margin:4px 0 10px}
label{font-size:13px;color:var(--ink2)}
.btn{display:block;width:100%;border:0;border-radius:12px;background:var(--acc);color:#fff;font:600 17px/1 inherit;padding:15px;margin:6px 0;text-align:center;text-decoration:none}
.btn.sec{background:var(--accsoft);color:var(--acc2)}.btn.bad{background:var(--bad)}
.acts{display:flex;gap:8px;margin-top:8px}.acts a{flex:1;text-align:center;padding:9px;border-radius:10px;background:var(--accsoft);color:var(--acc2);text-decoration:none;font-size:14px}
.search{margin:0 0 10px}.tabs{display:flex;gap:6px;margin:0 0 10px}.tabs button{flex:1;border:1px solid var(--line);background:var(--panel);color:var(--ink2);border-radius:10px;padding:8px;font-size:14px}
.tabs button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.timer{font:600 40px/1.1 ui-monospace,Menlo,Consolas,monospace;text-align:center;margin:8px 0}
.toast{position:fixed;left:14px;right:14px;bottom:calc(84px + env(safe-area-inset-bottom));background:var(--ink);color:var(--bg);padding:12px 14px;border-radius:12px;z-index:9;font-size:15px}
.toast.bad{background:var(--bad);color:#fff}.empty{text-align:center;color:var(--mute);padding:30px 0}
.bar{height:8px;background:var(--accsoft);border-radius:6px;overflow:hidden}.bar div{height:100%;background:var(--acc)}"""

M88_LOGIN = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#6a48e0"><link rel="manifest" href="/manifest.json"><link rel="apple-touch-icon" href="/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><title>PA Rechnung</title><style>__CSS__</style></head><body>
<header><h1>PA Rechnung – Anmelden</h1></header><main>
<div class="card"><p style="margin-top:0">Dieses Handy ist noch nicht gekoppelt.</p>
<p class="mute">Am PC in <b>PA Rechnung → Einstellungen → Schnittstelle &amp; Handy</b> auf <b>„Handy koppeln“</b> klicken und den QR-Code scannen –
oder den dort angezeigten Kopplungscode hier eintippen (nötig, wenn die App vom Startbildschirm aus geöffnet wurde).</p>
<label>Kopplungscode<input id="c" autocomplete="one-time-code" autocapitalize="characters" placeholder="XXXX-XXXX" maxlength="9"></label>
<label>Name dieses Geräts<input id="n" placeholder="z. B. iPhone Thomas"></label>
<button class="btn" id="go">Koppeln</button><div id="msg" class="mute"></div></div></main>
<script>
document.getElementById("go").onclick=async function(){var m=document.getElementById("msg");m.textContent="…";
 try{var r=await fetch("/pair",{method:"POST",headers:{"Content-Type":"application/json","X-PA":"1"},credentials:"same-origin",
  body:JSON.stringify({code:document.getElementById("c").value,name:document.getElementById("n").value})});
  var j=await r.json();if(j.ok){location.replace("/");}else{m.textContent=j.error||"Fehler";m.style.color="#c8323c";}}
 catch(e){m.textContent="Keine Verbindung zum PC.";}};
</script></body></html>"""

M88_APP = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#6a48e0"><link rel="manifest" href="/manifest.json"><link rel="apple-touch-icon" href="/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="PA Rechnung">
<title>PA Rechnung</title><style>__CSS__</style></head><body>
<header><h1 id="ttl">PA Rechnung</h1><button id="nset" title="App-Einstellungen" style="display:none;margin-right:6px">⚙︎</button><button id="rl" title="Neu laden">↻</button></header>
<main id="main"><div class="empty">Lädt …</div></main>
<nav id="nav"></nav>
<script>
"use strict";
var IC={kal:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',posten:'<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',kunden:'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.9.8 3.1 2.6 3.5 5.2"/>',
proj:'<path d="M3 7h7l2 2h9v10H3z"/>',fahrt:'<path d="M5 16l1.5-6h11L19 16"/><rect x="3" y="13" width="18" height="5" rx="1.5"/><circle cx="7.5" cy="18.5" r="1.5"/><circle cx="16.5" cy="18.5" r="1.5"/>',
beleg:'<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',bau:'<path d="M2 20h20M4 20V10l8-6 8 6v10"/><path d="M9 20v-6h6v6"/>',zahlen:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'};
var PAGES=[["posten","Offen"],["kal","Termine"],["kunden","Kunden"],["proj","Zeit"],["bau","Baustelle"],["fahrt","Fahrt"],["beleg","Beleg"],["zahlen","Zahlen"]];
var cur=(location.hash||"#posten").slice(1),ST={},tick=null;
function $(s){return document.querySelector(s);}
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function eur(v){return (Number(v)||0).toLocaleString("de-DE",{minimumFractionDigits:2,maximumFractionDigits:2})+" €";}
function dde(i){return i?i.slice(8,10)+"."+i.slice(5,7)+"."+i.slice(0,4):"";}
function tday(){var d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}
function toast(t,bad){var e=document.createElement("div");e.className="toast"+(bad?" bad":"");e.textContent=t;document.body.appendChild(e);setTimeout(function(){e.remove();},bad?4500:2400);}
async function api(p,body){var o={credentials:"same-origin",headers:{"X-PA":"1"}};
 if(body!==undefined){o.method="POST";if(body instanceof Blob||body instanceof File){o.body=body;o.headers["X-Filename"]=encodeURIComponent(body.name||"foto.jpg");o.headers["Content-Type"]=body.type||"application/octet-stream";}
  else{o.body=JSON.stringify(body);o.headers["Content-Type"]="application/json";}}
 var r;try{r=await fetch(p,o);}catch(e){toast("Keine Verbindung zum PC (offline?)",true);throw e;}
 if(r.status===401){location.replace("/");throw new Error("401");}
 var j=await r.json().catch(function(){return{};});if(!r.ok||j.ok===false){toast(j.error||("Fehler "+r.status),true);throw new Error(j.error||r.status);}return j;}
function navR(){$("#nav").innerHTML=PAGES.map(function(p){return '<button data-p="'+p[0]+'" class="'+(cur===p[0]?"on":"")+'"><svg viewBox="0 0 24 24">'+IC[p[0]]+'</svg>'+p[1]+'</button>';}).join("");
 document.querySelectorAll("#nav button").forEach(function(b){b.onclick=function(){show(b.dataset.p);};});}
function show(p){cur=p;location.hash=p;if(tick){clearInterval(tick);tick=null;}navR();window.scrollTo(0,0);
 $("#ttl").textContent=(PAGES.find(function(x){return x[0]===p;})||["","PA Rechnung"])[1];
 $("#main").innerHTML='<div class="empty">Lädt …</div>';(V[p]||V.posten)().catch(function(e){console.error(e);$("#main").innerHTML='<div class="empty">Konnte nicht laden.<br>PC an und Programm offen?</div>';});}
var V={};
V.posten=async function(){var d=await api("/v1/offene-posten");
 $("#main").innerHTML='<div class="kpis"><div class="card"><div class="mute">Offen</div><div class="big">'+eur(d.summe)+'</div><div class="mute">'+d.anzahl+' Rechnungen</div></div>'+
 '<div class="card"><div class="mute">Überfällig</div><div class="big" style="color:'+(d.ueberfaellig_anzahl?"var(--bad)":"inherit")+'">'+eur(d.ueberfaellig_summe)+'</div><div class="mute">'+d.ueberfaellig_anzahl+' Rechnungen</div></div></div>'+
 (d.posten.map(function(r){return '<div class="card" data-i="'+r.id+'"><div class="row"><div class="sp"><b class="ell" style="display:block">'+esc(r.kunde)+'</b><div class="mute">'+esc(r.nr)+' · '+dde(r.datum)+(r.titel?' · '+esc(r.titel):'')+'</div></div><div class="r"><b>'+eur(r.offen)+'</b>'+(r.offen<r.summe-0.004?'<div class="mute">von '+eur(r.summe)+'</div>':'<br>')+
 (r.tage_ueberfaellig>0?'<span class="badge bad">'+r.tage_ueberfaellig+' Tage über</span>':'<span class="badge">fällig '+dde(r.faellig)+'</span>')+'</div></div></div>';}).join("")||'<div class="empty">Keine offenen Rechnungen 🎉</div>');
 document.querySelectorAll("[data-i]").forEach(function(c){c.onclick=function(){window.open("/v1/rechnungen/"+c.dataset.i+"/pdf","_blank");};});};
V.kunden=async function(){var d=await api("/v1/kunden");var f=function(t){t=(t||"").toLowerCase();return d.kunden.filter(function(c){return !t||(c.name+" "+c.ort+" "+c.kdnr+" "+c.ansprechpartner).toLowerCase().indexOf(t)>=0;});};
 $("#main").innerHTML='<input class="search" id="q" type="search" placeholder="Kunde suchen …"><div id="kl"></div>';
 var draw=function(){$("#kl").innerHTML=f($("#q").value).map(function(c){var tel=c.mobil||c.tel;return '<div class="card"><b>'+esc(c.name)+'</b>'+(c.ansprechpartner?' <span class="mute">· '+esc(c.ansprechpartner)+'</span>':'')+
 '<div class="mute">'+esc([c.strasse,(c.plz+" "+c.ort).trim()].filter(Boolean).join(", "))+'</div><div class="acts">'+
 (tel?'<a href="tel:'+esc(tel.replace(/[^+0-9]/g,""))+'">📞 Anrufen</a>':'')+(c.mail?'<a href="mailto:'+esc(c.mail)+'">✉️ Mail</a>':'')+
 (c.ort?'<a href="https://maps.google.com/?q='+encodeURIComponent(c.strasse+" "+c.plz+" "+c.ort)+'" target="_blank">📍 Karte</a>':'')+'</div></div>';}).join("")||'<div class="empty">Keine Kunden gefunden</div>';};
 $("#q").oninput=draw;draw();};
V.proj=async function(){var r=await Promise.all([api("/v1/projekte?status=aktiv"),api("/v1/status"),api("/v1/bausteine")]);var d=r[0],st=r[1],bs=r[2].bausteine;
 var opts=d.projekte.map(function(p){return '<option value="'+p.id+'">'+esc((p.nr?p.nr+" ":"")+p.name)+'</option>';}).join("");
 var bopt='<option value="">Arbeitszeit (Stundensatz '+eur(st.stundensatz)+')</option>'+bs.filter(function(b){return /std|h$/i.test(b.einheit||"");}).map(function(b){return '<option value="'+b.id+'">'+esc(b.name)+' ('+eur(b.preis)+')</option>';}).join("");
 var t=st.timer;
 $("#main").innerHTML=(t?'<div class="card"><div class="mute">Stoppuhr läuft · '+esc(t.projekt)+'</div><div class="timer" id="tm">0:00:00</div>'+
 '<label>Was wurde gemacht?<input id="td"></label><label>Leistung<select id="ta">'+bopt+'</select></label><button class="btn" id="tstop">Stoppen &amp; buchen</button><button class="btn sec" id="tcan">Verwerfen</button></div>':
 '<div class="card"><b>Stoppuhr</b><label>Projekt<select id="tp">'+opts+'</select></label><button class="btn" id="tstart" '+(d.anzahl?"":"disabled")+'>▶ Start</button><div class="mute">Läuft auf dem PC weiter – dort in der Seitenleiste sichtbar.</div></div>')+
 '<div class="card"><b>Zeit nachtragen</b><label>Projekt<select id="zp">'+opts+'</select></label><div class="row"><div class="sp"><label>Datum<input type="date" id="zd" value="'+tday()+'"></label></div><div class="sp"><label>Stunden<input id="zh" inputmode="decimal" placeholder="z. B. 1,5"></label></div></div>'+
 '<label>Leistung<select id="za">'+bopt+'</select></label><label>Text<input id="zt" placeholder="z. B. Q-SYS Design angepasst"></label><button class="btn" id="zgo">Zeit buchen</button></div>'+
 d.projekte.map(function(p){return '<div class="card"><div class="row"><div class="sp"><b class="ell" style="display:block">'+esc(p.name)+'</b><div class="mute">'+esc(p.nr)+' · '+esc(p.kunde||"")+' · '+esc(p.bereich)+'</div></div><div class="r"><b>'+(p.stunden||0).toLocaleString("de-DE")+' h</b></div></div></div>';}).join("");
 if(t){var s0=new Date(t.start).getTime();var up=function(){var s=Math.max(0,Math.floor((Date.now()-s0)/1000));var e=$("#tm");if(e)e.textContent=Math.floor(s/3600)+":"+String(Math.floor(s/60)%60).padStart(2,"0")+":"+String(s%60).padStart(2,"0");};up();tick=setInterval(up,1000);
  $("#tstop").onclick=async function(){var j=await api("/v1/timer/stop",{descr:$("#td").value,article_id:$("#ta").value||null});toast(j.stunden.toLocaleString("de-DE")+" h gebucht");show("proj");};
  $("#tcan").onclick=async function(){await api("/v1/timer/cancel",{});toast("Stoppuhr verworfen");show("proj");};}
 else if($("#tstart")){$("#tstart").onclick=async function(){await api("/v1/timer/start",{project_id:+$("#tp").value});show("proj");};}
 $("#zgo").onclick=async function(){var j=await api("/v1/zeit",{project_id:+$("#zp").value,datum:$("#zd").value,stunden:$("#zh").value,article_id:$("#za").value||null,text:$("#zt").value});
  toast(j.stunden.toLocaleString("de-DE")+" h auf "+j.projekt+" gebucht");$("#zh").value="";$("#zt").value="";};};
V.fahrt=async function(){var r=await Promise.all([api("/v1/projekte?status=aktiv"),api("/v1/kunden")]);
 $("#main").innerHTML='<div class="card"><b>Fahrt erfassen</b><div class="row"><div class="sp"><label>Datum<input type="date" id="fd" value="'+tday()+'"></label></div><div class="sp"><label>km<input id="fk" inputmode="decimal" placeholder="gesamt"></label></div></div>'+
 '<label>Art<select id="fa"><option value="dienst">Dienstfahrt (gefahrene km gesamt)</option><option value="pendel">Fahrt zur Arbeit (einfache Entfernung)</option></select></label>'+
 '<label>Ziel<input id="fz" placeholder="Ort / Kunde"></label><label>Zweck<input id="fw" placeholder="z. B. Inbetriebnahme"></label>'+
 '<label>Projekt (optional)<select id="fp"><option value="">–</option>'+r[0].projekte.map(function(p){return '<option value="'+p.id+'">'+esc(p.name)+'</option>';}).join("")+'</select></label>'+
 '<label>Kunde (optional)<select id="fc"><option value="">–</option>'+r[1].kunden.map(function(c){return '<option value="'+c.id+'">'+esc(c.name)+'</option>';}).join("")+'</select></label>'+
 '<button class="btn" id="fgo">Fahrt speichern</button></div>';
 $("#fgo").onclick=async function(){await api("/v1/fahrt",{datum:$("#fd").value,km:$("#fk").value,art:$("#fa").value,ziel:$("#fz").value,zweck:$("#fw").value,project_id:$("#fp").value||null,customer_id:$("#fc").value||null});
  toast("Fahrt gespeichert");$("#fk").value="";$("#fz").value="";$("#fw").value="";};};
var NATIVE=!!(window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.pa);
function nat(c){try{window.webkit.messageHandlers.pa.postMessage({cmd:c});}catch(e){}}
window.paNativeDone=function(ok,msg){toast(msg,!ok);};
V.beleg=async function(){
 $("#main").innerHTML='<div class="card"><b>Beleg senden</b><p class="mute">Foto von Rechnung oder Quittung – landet am PC unter „Belege &amp; Import“ zur Prüfung.</p>'+
 (NATIVE?'<button class="btn" id="nscan">📄 Dokument scannen (iPhone)</button>':'')+
 '<label class="btn" style="cursor:pointer">📷 Foto aufnehmen<input id="cam" type="file" accept="image/*,application/pdf" capture="environment" multiple style="display:none"></label>'+
 '<label class="btn sec" style="cursor:pointer">📄 Datei / PDF wählen<input id="fil" type="file" accept="image/*,application/pdf" multiple style="display:none"></label><div id="bl"></div></div>'+
 '<div class="card"><b>Notiz an den PC</b><textarea id="nt" rows="3" placeholder="z. B. Material nachbestellen, Kunde zurückrufen …"></textarea><button class="btn sec" id="ngo">Notiz senden</button></div>';
 var send=async function(fs){for(var i=0;i<fs.length;i++){var f=fs[i];var d=document.createElement("div");d.className="row mute";d.innerHTML='<span class="sp ell"></span><span>sendet …</span>';d.firstChild.textContent=f.name||"Foto";$("#bl").prepend(d);
  try{await api("/v1/beleg",f);d.lastChild.textContent="✓ angekommen";d.lastChild.style.color="var(--ok)";}catch(e){d.lastChild.textContent="Fehler";d.lastChild.style.color="var(--bad)";}}};
 if(NATIVE)$("#nscan").onclick=function(){nat("scan");};
 $("#cam").onchange=function(e){send(e.target.files);e.target.value="";};$("#fil").onchange=function(e){send(e.target.files);e.target.value="";};
 $("#ngo").onclick=async function(){await api("/v1/notiz",{text:$("#nt").value});$("#nt").value="";toast("Notiz gesendet");};};
V.bau=async function(){var d=await api("/v1/projekte?status=aktiv");var pid=ST.bau||(d.projekte[0]||{}).id;
 if(!d.projekte.length){$("#main").innerHTML='<div class="empty">Keine aktiven Projekte.</div>';return;}
 var pj=await api("/v1/projekt?id="+pid);var k=pj.kunde||{};
 var tel=function(n){return n?'<a class="btn sec" href="tel:'+esc(n.replace(/[^0-9+]/g,""))+'">📞 '+esc(n)+'</a>':"";};
 $("#main").innerHTML='<div class="card"><select id="bp">'+d.projekte.map(function(p){return '<option value="'+p.id+'"'+(p.id===pid?" selected":"")+'>'+esc((p.nr?p.nr+" · ":"")+p.name+(p.kunde?" – "+p.kunde:""))+'</option>';}).join("")+'</select>'+
 '<div class="row" style="margin-top:8px"><div class="sp"><b>'+esc(k.name||"ohne Kunde")+'</b>'+(k.ansprechpartner&&k.ansprechpartner!==k.name?'<div class="mute">'+esc(k.ansprechpartner)+'</div>':'')+'<div class="mute">'+esc(k.adresse||"")+'</div></div><div class="r"><b>'+pj.stunden.toLocaleString("de-DE")+' h</b><div class="mute">gebucht</div></div></div>'+
 (k.adresse?'<a class="btn sec" target="_blank" href="https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(k.adresse)+'">🧭 Navigation</a>':'')+tel(k.mobil)+tel(k.tel)+
 (pj.beschreibung?'<p class="mute" style="white-space:pre-wrap">'+esc(pj.beschreibung)+'</p>':'')+'</div>'+
 '<div class="card"><b>Fotos zum Projekt</b><p class="mute">Landen direkt im Projektordner unter „Fotos Baustelle“.</p><label class="btn" style="cursor:pointer">📷 Foto aufnehmen<input id="bcam" type="file" accept="image/*" capture="environment" multiple style="display:none"></label><div id="bfl"></div>'+
 (pj.dateien.length?'<div class="mute" style="margin-top:6px">Zuletzt: '+pj.dateien.slice(0,4).map(function(f){return esc(f.name);}).join(", ")+'</div>':'')+'</div>'+
 (pj.aufmass_ok?'<div class="card"><b>Aufmaß</b><input id="ab" placeholder="Was? z. B. Geländer Treppe EG"><div class="row" style="gap:6px"><input id="al" inputmode="decimal" placeholder="L (m)"><input id="abb" inputmode="decimal" placeholder="B (m)"><input id="ah" inputmode="decimal" placeholder="H (m)"></div>'+
 '<div class="row" style="gap:6px"><input id="aa" inputmode="decimal" placeholder="Anzahl" value="1"><select id="ae">'+pj.einheiten.map(function(e){return '<option>'+esc(e)+'</option>';}).join("")+'</select></div><button class="btn" id="ago">Position speichern</button>'+
 (pj.aufmass.length?'<div style="margin-top:8px">'+pj.aufmass.map(function(a){return '<div class="row mute"><span class="sp ell">'+esc(a.beschreibung)+'</span><b>'+(Number(a.ergebnis)||0).toLocaleString("de-DE",{maximumFractionDigits:3})+' '+esc(a.einheit)+'</b></div>';}).join("")+'</div>':'')+'</div>':'')+
 '<div class="card"><b>Notiz zum Projekt</b><textarea id="bn" rows="3" placeholder="z. B. Material fehlt, Mangel, Absprache mit Kunde …"></textarea><button class="btn sec" id="bngo">Notiz senden</button></div>';
 $("#bp").onchange=function(e){ST.bau=+e.target.value;V.bau();};
 $("#bcam").onchange=async function(e){var fs=e.target.files;for(var i=0;i<fs.length;i++){var f=fs[i];var dv=document.createElement("div");dv.className="row mute";dv.innerHTML='<span class="sp ell"></span><span>sendet …</span>';dv.firstChild.textContent=f.name||"Foto";$("#bfl").prepend(dv);
  try{var o={credentials:"same-origin",method:"POST",body:f,headers:{"X-PA":"1","X-Project":String(pid),"X-Filename":encodeURIComponent(f.name||"foto.jpg"),"Content-Type":f.type||"image/jpeg"}};var r=await fetch("/v1/projekt/foto",o);var j=await r.json();if(!r.ok||j.ok===false)throw new Error(j.error||r.status);dv.lastChild.textContent="✓ im Projekt";dv.lastChild.style.color="var(--ok)";}
  catch(err){dv.lastChild.textContent="Fehler";dv.lastChild.style.color="var(--bad)";toast(String(err.message||err),true);}}e.target.value="";};
 if($("#ago"))$("#ago").onclick=async function(){var n=function(id){var v=$(id).value.replace(",",".");return v===""?null:Number(v);};
  var j=await api("/v1/aufmass",{project_id:pid,beschreibung:$("#ab").value,l:n("#al"),b:n("#abb"),h:n("#ah"),anz:n("#aa")||1,einheit:$("#ae").value});
  toast("Gespeichert: "+(Number(j.ergebnis)||0).toLocaleString("de-DE",{maximumFractionDigits:3})+" "+j.einheit);V.bau();};
 $("#bngo").onclick=async function(){var t=$("#bn").value.trim();if(!t)return;var p=d.projekte.find(function(x){return x.id===pid;})||{};await api("/v1/notiz",{text:"[Projekt "+(p.nr||p.name||pid)+"] "+t});$("#bn").value="";toast("Notiz gesendet");};};
V.kal=async function(){var o=ST.kalo||0,d0=new Date();d0.setHours(0,0,0,0);d0.setDate(d0.getDate()+o);
 var iso=function(d){return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");};
 var d1=new Date(d0);d1.setDate(d1.getDate()+14);
 var r=await Promise.all([api("/v1/kalender?von="+iso(d0)+"&bis="+iso(d1)+"&q="+encodeURIComponent(ST.kalq||"")),api("/v1/kalender/abos")]);var d=r[0],ab=r[1].abos||[];
 var WD=["So","Mo","Di","Mi","Do","Fr","Sa"],by={};d.termine.forEach(function(e){(by[e.start.slice(0,10)]=by[e.start.slice(0,10)]||[]).push(e);});
 var hm=function(s){return s.slice(11,16);},T=iso(new Date());
 var h='<div class="row" style="margin:0 0 10px"><button class="btn sec" id="kp" style="flex:none;width:auto;padding:8px 14px">‹</button><button class="btn sec" id="kh" style="flex:none;width:auto;padding:8px 14px">Heute</button><button class="btn sec" id="kn" style="flex:none;width:auto;padding:8px 14px">›</button><div class="sp mute" style="text-align:right">'+dde(iso(d0))+' – '+dde(iso(new Date(d1.getTime()-864e5)))+'</div></div>'+
  '<input class="search" id="kq" type="search" placeholder="Termine suchen …" value="'+esc(ST.kalq||"")+'">';
 var days=Object.keys(by).sort();
 h+=days.map(function(k){var dt=new Date(k+"T12:00");return '<div class="mute" style="margin:12px 2px 6px;font-weight:600;color:'+(k===T?"var(--acc)":"var(--ink2)")+'">'+WD[dt.getDay()]+' '+dde(k)+(k===T?' · heute':'')+'</div>'+
  by[k].map(function(e){var i=d.termine.indexOf(e);return '<div class="card" data-ke="'+i+'" style="border-left:5px solid '+esc(e.farbe||"#0a84ff")+'"><div class="row"><div style="flex:none;width:58px" class="mute">'+(e.all_day?"ganztägig":hm(e.start)+"<br>"+hm(e.end))+'</div><div class="sp"><b class="ell" style="display:block">'+esc(e.title)+'</b><div class="mute ell">'+esc(e.ort||e.kal)+'</div></div></div></div>';}).join("");}).join("")||'<div class="empty">Keine Termine in diesen 14 Tagen</div>';
 if(ab.length)h+='<div class="card" style="margin-top:14px"><div class="mute" style="margin-bottom:6px"><b>Kalender-Abos</b></div>'+ab.map(function(a){return '<div class="row" style="margin:4px 0"><span style="width:10px;height:10px;border-radius:5px;background:'+esc(a.farbe)+';flex:none"></span><span class="sp ell">'+esc(a.name)+'</span><span class="mute" style="flex:none">'+(a.ok===false?'<span style="color:var(--bad)">Fehler</span>':(a.termine||0)+' Termine')+'</span></div>';}).join("")+
  '<button class="btn sec" id="kab" style="margin-top:8px">↻ Abos jetzt abrufen</button></div>';
 $("#main").innerHTML=h;
 var mv=function(n){ST.kalo=n===0?0:(ST.kalo||0)+n;V.kal();};$("#kp").onclick=function(){mv(-14);};$("#kn").onclick=function(){mv(14);};$("#kh").onclick=function(){mv(0);};
 var qt=null;$("#kq").oninput=function(e){clearTimeout(qt);qt=setTimeout(function(){ST.kalq=e.target.value;V.kal().then(function(){var n=$("#kq");n.focus();n.setSelectionRange(n.value.length,n.value.length);});},350);};
 var b=$("#kab");if(b)b.onclick=async function(){b.disabled=true;b.textContent="wird abgerufen …";try{var j=await api("/v1/kalender/abrufen",{});toast(j.abgerufen+" Abo(s) abgerufen"+((j.fehler||[]).length?" – "+j.fehler[0]:""),(j.fehler||[]).length);}catch(e){toast("Nur mit Schreib-Recht möglich",true);}V.kal();};
 document.querySelectorAll("[data-ke]").forEach(function(c){c.onclick=function(){var e=d.termine[+c.dataset.ke];
  var m=document.createElement("div");m.className="card";m.style.cssText="position:fixed;left:10px;right:10px;bottom:76px;z-index:50;max-height:70vh;overflow:auto;box-shadow:0 8px 30px rgba(0,0,0,.25)";
  m.innerHTML='<div class="row"><b class="sp">'+esc(e.title)+'</b><button class="btn sec" style="flex:none;width:auto;padding:6px 12px" id="kx">✕</button></div>'+
   '<div class="mute" style="margin:6px 0">'+dde(e.start.slice(0,10))+' · '+(e.all_day?"ganztägig":hm(e.start)+"–"+hm(e.end))+' · '+esc(e.kal)+'</div>'+
   (e.notiz?'<div style="white-space:pre-wrap;font-size:14px;margin:8px 0">'+esc(e.notiz)+'</div>':'')+
   '<div class="acts">'+(e.ort?'<a href="https://maps.google.com/?q='+encodeURIComponent(e.ort)+'" target="_blank" rel="noopener noreferrer">📍 Navigation</a>':'')+
   (e.url&&/^https?:/i.test(e.url)?'<a href="'+esc(e.url)+'" target="_blank" rel="noopener noreferrer">🔗 Link</a>':'')+'</div>';
  document.body.appendChild(m);$("#kx").onclick=function(){m.remove();};};});};
V.zahlen=async function(){var d=await api("/v1/kennzahlen");var mx=Math.max.apply(null,d.monate.map(function(m){return m.umsatz;}).concat([1]));var mon=new Date().getMonth();
 $("#main").innerHTML='<div class="kpis"><div class="card"><div class="mute">Umsatz '+d.jahr+'</div><div class="big">'+eur(d.umsatz)+'</div><div class="mute">'+d.anzahl_rechnungen+' Rechnungen</div></div>'+
 '<div class="card"><div class="mute">Gewinn (EÜR)</div><div class="big">'+eur(d.gewinn)+'</div><div class="mute">Ausgaben '+eur(d.ausgaben)+'</div></div>'+
 '<div class="card"><div class="mute">Offen</div><div class="big">'+eur(d.offen_summe)+'</div><div class="mute">davon überfällig '+eur(d.ueberfaellig_summe)+'</div></div>'+
 '<div class="card"><div class="mute">Kontostand'+(d.kontostand_datum?" (ca.)":"")+'</div><div class="big">'+(d.kontostand==null?"–":eur(d.kontostand))+'</div><div class="mute">'+(d.ruecklage_monat!=null?"Rücklage/Monat "+eur(d.ruecklage_monat):"&nbsp;")+'</div></div></div>'+
 '<div class="card"><b>Umsatz je Monat</b>'+d.monate.map(function(m,i){return '<div class="row" style="margin-top:6px'+(i>mon&&d.jahr==new Date().getFullYear()?';opacity:.45':'')+'"><span style="width:34px" class="mute">'+["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"][i]+'</span><div class="sp bar"><div style="width:'+(100*m.umsatz/mx)+'%"></div></div><span style="width:96px" class="r">'+eur(m.umsatz)+'</span></div>';}).join("")+'</div>'+
 '<button class="btn sec" id="lo">Dieses Handy abmelden</button>';
 $("#lo").onclick=async function(){await api("/logout",{});location.replace("/");};};
$("#rl").onclick=function(){show(cur);};
if("serviceWorker" in navigator){navigator.serviceWorker.register("/sw.js").catch(function(){});}
if(NATIVE){$("#nset").style.display="";$("#nset").onclick=function(){nat("settings");};}
navR();show(PAGES.some(function(p){return p[0]===cur;})?cur:"posten");
</script></body></html>"""

M88_SW = """// PA Rechnung PWA service worker v1 - offline shell, network first
const C = "pa88-v1";
self.addEventListener("install", e => { e.waitUntil(caches.open(C).then(c => c.addAll(["/", "/manifest.json", "/icon-192.png"]).catch(() => {}))); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/v1/") || u.pathname.startsWith("/ics/")) return;
  e.respondWith(fetch(e.request).then(r => { if (r.ok && (u.pathname === "/" || u.pathname.endsWith(".png") || u.pathname.endsWith(".json"))) { const cl = r.clone(); caches.open(C).then(c => c.put(e.request, cl)); } return r; })
    .catch(() => caches.match(e.request).then(r => r || caches.match("/"))));
});
"""


def m88_manifest():
    return {"name": "PA Rechnung", "short_name": "PA Rechnung", "start_url": "/", "scope": "/", "display": "standalone",
            "background_color": "#f4f3f8", "theme_color": "#6a48e0", "lang": "de",
            "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}


_M88_ICONS = {}


def m88_icon(size):
    if size in _M88_ICONS:
        return _M88_ICONS[size]
    data = b""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (size, size), (106, 72, 224))
        dr = ImageDraw.Draw(img)
        txt = "PA"
        font = None
        for fn in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(fn, int(size * 0.42))
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()
        try:
            bb = dr.textbbox((0, 0), txt, font=font)
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            dr.text(((size - w) / 2 - bb[0], (size - h) / 2 - bb[1]), txt, fill=(255, 255, 255), font=font)
        except Exception:
            dr.text((size * 0.3, size * 0.4), txt, fill=(255, 255, 255), font=font)
        b = io.BytesIO()
        img.save(b, "PNG")
        data = b.getvalue()
    except Exception:
        data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mPk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    _M88_ICONS[size] = data
    return data


# ---------------------------------------------------------------------------- HTTP server
class M88NotFound(Exception):
    pass


class M88Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows: with SO_REUSEADDR a second program may bind the same port without an error -> no reuse there
    allow_reuse_address = not sys.platform.startswith("win")

    def server_bind(self):
        # the global name is M91Server at run time (m91 loads later): it sets SO_EXCLUSIVEADDRUSE on Windows
        ThreadingHTTPServer.server_bind(self)


class M88Handler(BaseHTTPRequestHandler):
    server_version = "PARechnungAPI/" + M88_VERSION
    timeout = 60

    def log_message(self, fmt, *args):
        pass

    def _ip(self):
        return (self.client_address or ("?",))[0]

    def _out(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")   # v1.2.0: no embedding by foreign pages
        for k, v in (extra or {}).items():
            if isinstance(v, list):
                for vv in v:
                    self.send_header(k, vv)
            else:
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self._status = code
        return True

    # --- limits
    def _rate_ok(self):
        ip, now = self._ip(), time.time()
        lim = m88_cfg()["rate"]
        with M88["lock"]:
            fl = M88["fails"][ip]
            while fl and fl[0] < now - 600:
                fl.popleft()
            if len(fl) >= 10:
                return False, "Zu viele Fehlversuche – 10 Minuten gesperrt."
            dq = M88["rate"][ip]
            while dq and dq[0] < now - 60:
                dq.popleft()
            if len(dq) >= lim:
                return False, f"Zu viele Anfragen (max. {lim} pro Minute)."
            dq.append(now)
            # v2.6.3: forget idle addresses (the dicts grew with every IP that ever asked)
            if len(M88["rate"]) + len(M88["fails"]) > 512:
                for d_ in (M88["rate"], M88["fails"]):
                    for k_ in [k_ for k_, v_ in d_.items() if not v_ or v_[-1] < now - 600]:
                        d_.pop(k_, None)
        return True, ""

    def _sync_ok(self, p):
        """v1.5.0: paired sync device on /sync/ - not counted for the request limit (file packages, live waiting)"""
        if not p.startswith("/sync/"):
            return False
        a = (self.headers.get("Authorization") or "").strip()
        if not a.lower().startswith("bearer "):
            return False
        r = m88_check_token(a[7:].strip())
        return bool(r and r.get("typ") == "sync")

    def _fail(self):
        with M88["lock"]:
            M88["fails"][self._ip()].append(time.time())

    # --- auth
    def _cookie_tok(self):
        ck = self.headers.get("Cookie") or ""
        m = re.search(r"(?:^|;\s*)pa88=([A-Za-z0-9_\-]+)", ck)
        return m.group(1) if m else ""

    def _auth(self, qs=None):
        """-> (token_row, via) ; via = bearer | cookie | query"""
        a = (self.headers.get("Authorization") or "").strip()
        tok, via = "", ""
        if a.lower().startswith("bearer "):
            tok, via = a[7:].strip(), "bearer"
        elif self.headers.get("X-Api-Key"):
            tok, via = self.headers.get("X-Api-Key").strip(), "bearer"
        elif self._cookie_tok():
            tok, via = self._cookie_tok(), "cookie"
        if not tok:
            return None, ""
        r = m88_check_token(tok)
        if r and r.get("typ") == "ics":
            r = None                      # calendar subscription token: only /ics/<token>.ics
        if r and r.get("typ") == "sync" and not urlparse(self.path).path.startswith("/sync/"):
            r = None                      # v1.4.0: sync access only for /sync/ (data exchange with a mobile device)
        if r:
            try:
                x("UPDATE m88_token SET zuletzt=?, zuletzt_ip=? WHERE id=?", (now_iso(), self._ip(), r["id"]))
            except Exception:
                pass
        return r, via

    def _body(self, limit=1 << 20):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > limit:
            raise ValueError("Anfrage zu groß.")
        return self.rfile.read(n) if n > 0 else b""

    def _json(self, limit=1 << 20):
        b = self._body(limit)
        if not b:
            return {}
        d = json.loads(b.decode("utf-8"))
        if not isinstance(d, dict):
            raise ValueError("JSON-Objekt erwartet.")
        return d

    def _finish(self, meth, p, tok):
        if p.startswith(("/v1/", "/pair", "/ics/", "/logout")) or getattr(self, "_status", 200) >= 400:
            m88_log(self._ip(), meth, p, getattr(self, "_status", 0), (tok or {}).get("name") or "")

    # --- GET
    def _xsite(self, p):
        """v1.2.0: request started by another web site in the browser (fetch/img/form) - never answered with data"""
        if not p.startswith(("/v1/", "/pair", "/logout", "/sync/")):
            return False
        return (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site" and \
            (self.headers.get("Sec-Fetch-Mode") or "").lower() != "navigate"

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        tok = None
        self._status = 0
        try:
            ok, why = (True, "") if self._sync_ok(p) else self._rate_ok()
            if not ok:
                return self._out(429, {"ok": False, "error": why})
            if self._xsite(p):
                return self._out(403, {"ok": False, "error": "Anfrage von fremder Webseite abgelehnt."})
            if p == "/manifest.json":
                return self._out(200, m88_manifest(), "application/manifest+json; charset=utf-8")
            if p == "/sw.js":
                return self._out(200, M88_SW, "application/javascript; charset=utf-8", {"Service-Worker-Allowed": "/"})
            if p in ("/icon-192.png", "/icon-512.png", "/apple-touch-icon.png", "/favicon.ico"):
                return self._out(200, m88_icon(512 if "512" in p else 192), "image/png")
            if p == "/pair":
                return self._pair(qs.get("c") or "", "", redirect=True)
            m = re.fullmatch(r"/ics/([A-Za-z0-9_\-]{10,200})\.ics", p)
            if m:
                tok = m88_check_token(m.group(1))
                if tok and tok.get("typ") != "ics":
                    tok = None                    # API/device tokens do not belong into a calendar link
                if not tok:
                    self._fail()
                    return self._out(401, "Kein gültiger Zugang", "text/plain; charset=utf-8")
                fn = globals().get("m84_ics")
                if not callable(fn):
                    return self._out(404, "Kalender-Abo nicht verfügbar", "text/plain; charset=utf-8")
                arten = [a for a in re.split(r"[,; ]+", qs.get("arten") or "") if a]
                try:
                    data = fn(arten or None)
                except TypeError:
                    data = fn()
                return self._out(200, data, "text/calendar; charset=utf-8")
            if p.startswith("/sync/") and callable(globals().get("m58_server_route")):
                tok, via = self._auth()
                return m58_server_route(self, "GET", p, qs, tok)
            if p in ("/", "/index.html"):
                tok, via = self._auth()
                html = (M88_APP if tok else M88_LOGIN).replace("__CSS__", M88_CSS)
                return self._out(200, html, "text/html; charset=utf-8")
            if not p.startswith("/v1/"):
                return self._out(404, {"ok": False, "error": "Nicht gefunden"})
            tok, via = self._auth()
            if not tok:
                self._fail()
                return self._out(401, {"ok": False, "error": "Token fehlt oder ungültig (Authorization: Bearer <token>)."},
                                 extra={"WWW-Authenticate": 'Bearer realm="PA Rechnung"'})
            r = self._route_get(p, qs)
            if r is None:
                return self._out(404, {"ok": False, "error": "Unbekannter Endpunkt"})
            if isinstance(r, tuple):
                return self._out(200, r[0], "application/pdf", {"Content-Disposition": f'inline; filename="{r[1]}"'})
            return self._out(200, r)
        except M88NotFound as e:
            return self._out(404, {"ok": False, "error": str(e)})
        except ValueError as e:
            return self._out(400, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._out(500, {"ok": False, "error": f"Interner Fehler: {e}"})
        finally:
            self._finish("GET", p, tok)

    def _route_get(self, p, qs):
        if p == "/v1/status":
            return m88_status()
        if p == "/v1/kunden":
            return m88_kunden(qs)
        if p == "/v1/rechnungen":
            return m88_rechnungen(qs)
        m = re.fullmatch(r"/v1/rechnungen/(\d+)(/pdf)?", p)
        if m:
            if m.group(2):
                data, fn = m88_rechnung_pdf(m.group(1))
                if not data:
                    raise M88NotFound("Rechnung nicht gefunden.")
                return data, fn
            r = m88_rechnung(m.group(1))
            if not r:
                raise M88NotFound("Rechnung nicht gefunden.")
            return r
        if p == "/v1/offene-posten":
            return m88_offene_posten()
        if p == "/v1/projekte":
            return m88_projekte(qs)
        if p == "/v1/projekt":
            return m88_projekt(qs.get("id") or 0)
        if p == "/v1/kennzahlen":
            return m88_kennzahlen(qs)
        if p == "/v1/lager":
            return m88_lager(qs)
        if p == "/v1/bausteine":
            return m88_bausteine()
        if p == "/v1/notizen":
            return {"notizen": m88_notizen(qs.get("alle") not in ("1", "ja", "true"))}
        if p == "/v1/kalender":
            return m88_kalender(qs)
        if p == "/v1/kalender/abos":
            return m88_kalender_abos()
        return None

    # --- POST
    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        tok = None
        self._status = 0
        try:
            ok, why = (True, "") if self._sync_ok(p) else self._rate_ok()
            if not ok:
                return self._out(429, {"ok": False, "error": why})
            if self._xsite(p):
                return self._out(403, {"ok": False, "error": "Anfrage von fremder Webseite abgelehnt."})
            if p.startswith("/sync/") and callable(globals().get("m58_server_route")):
                tok, via = self._auth()
                return m58_server_route(self, "POST", p, {k: v[0] for k, v in parse_qs(u.query).items()}, tok)
            if p == "/pair":
                d = self._json()
                return self._pair(d.get("code") or "", d.get("name") or "", redirect=False, app=bool(d.get("app")))
            tok, via = self._auth()
            if not tok:
                self._fail()
                return self._out(401, {"ok": False, "error": "Token fehlt oder ungültig."})
            # cookie sessions need the custom header (blocks cross-site form posts)
            if via == "cookie" and self.headers.get("X-PA") != "1":
                return self._out(403, {"ok": False, "error": "Anfrage abgelehnt."})
            if p == "/logout":
                if tok["typ"] == "geraet":
                    x("UPDATE m88_token SET aktiv=0, widerrufen=? WHERE id=?", (now_iso(), tok["id"]))
                return self._out(200, {"ok": True}, extra={"Set-Cookie": "pa88=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
            if not p.startswith("/v1/"):
                return self._out(404, {"ok": False, "error": "Nicht gefunden"})
            if tok["recht"] != "schreiben":
                return self._out(403, {"ok": False, "error": "Dieser Zugang darf nur lesen."})
            if p == "/v1/beleg":
                return self._beleg(tok)
            if p == "/v1/projekt/foto":
                return self._projfoto(tok)
            d = self._json()
            if p == "/v1/zeit":
                return self._out(200, m88_zeit(d))
            if p == "/v1/fahrt":
                return self._out(200, m88_fahrt(d))
            if p == "/v1/notiz":
                return self._out(200, m88_notiz(d, tok.get("name") or "API"))
            if p == "/v1/aufmass":
                return self._out(200, m88_aufmass(d))
            if p == "/v1/kalender/abrufen":
                fn = globals().get("abo_fetch_all")
                if not callable(fn):
                    raise M88NotFound("Kalender-Abos nicht verfügbar.")
                return self._out(200, fn())
            if p == "/v1/timer/start":
                return self._out(200, m88_timer_start(d))
            if p == "/v1/timer/stop":
                return self._out(200, timer_stop({"descr": d.get("descr") or "", "article_id": d.get("article_id")}))
            if p == "/v1/timer/cancel":
                set_setting("timer", None)
                return self._out(200, {"ok": True})
            return self._out(404, {"ok": False, "error": "Unbekannter Endpunkt"})
        except (ValueError, KeyError) as e:
            return self._out(400, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._out(500, {"ok": False, "error": f"Interner Fehler: {e}"})
        finally:
            self._finish("POST", p, tok)

    def _pair(self, code, name, redirect, app=False):
        code = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
        pr = M88.get("pair")
        good = bool(pr) and time.time() < pr["ablauf"] and len(code) == 8 and secrets.compare_digest(code, pr["code"])
        if not good:
            self._fail()
            if redirect:
                html = M88_LOGIN.replace("__CSS__", M88_CSS).replace("Dieses Handy ist noch nicht gekoppelt.",
                                                                     "Der QR-Code ist abgelaufen oder ungültig – am PC neu erzeugen.")
                return self._out(403, html, "text/html; charset=utf-8")
            return self._out(403, {"ok": False, "error": "Kopplungscode falsch oder abgelaufen – am PC neu erzeugen."})
        M88["pair"] = None
        ua = (self.headers.get("User-Agent") or "")
        nm = (name or "").strip() or ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua else "Handy")
        tage = int(m88_cfg().get("geraet_tage") or 365)
        tid, tok = m88_token_new(nm, "schreiben", "geraet", tage)
        ck = f"pa88={tok}; Max-Age={tage * 86400}; Path=/; HttpOnly; SameSite=Strict"
        if redirect:
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", ck)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._status = 302
            return True
        body = {"ok": True, "name": nm}
        if app:
            body["token"] = tok          # v1.3.0: native iPhone app keeps it in the iOS keychain (Bearer)
        return self._out(200, body, extra={"Set-Cookie": ck})

    def _projfoto(self, tok):
        """v3.5.0: photo from the building site -> project folder "Fotos Baustelle" (directly, no review list)"""
        try:
            pid = int(self.headers.get("X-Project") or 0)
        except ValueError:
            pid = 0
        if not pid or not q("SELECT id FROM projects WHERE id=?", (pid,), one=True):
            return self._out(400, {"ok": False, "error": "Projekt fehlt."})
        mx = M88_MAX_UPLOAD_MB * 1048576
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > mx:
            return self._out(413 if n > mx else 400, {"ok": False, "error": f"Datei leer oder zu groß (max. {M88_MAX_UPLOAD_MB} MB)."})
        name = os.path.basename(unquote(self.headers.get("X-Filename") or "")).strip() or "foto.jpg"
        ext = os.path.splitext(name.lower())[1]
        if ext not in HANDY_EXT:
            ext = mimetypes.guess_extension((self.headers.get("Content-Type") or "").split(";")[0].strip()) or ""
            ext = ".jpg" if ext in (".jpe", ".jfif") else ext
            if ext not in HANDY_EXT:
                return self._out(415, {"ok": False, "error": "Nur Fotos und PDFs."})
            name = os.path.splitext(name)[0] + ext
        name = "Baustelle_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + re.sub(r"[^\w.\-]+", "_", name)[-60:]
        tmp = _tmp_for(name)
        left = n
        with open(tmp, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left > 0:
            try:
                os.remove(tmp)
            except Exception:
                pass
            return self._out(400, {"ok": False, "error": "Übertragung abgebrochen."})
        r = add_project_file(pid, tmp, name, folder="Fotos Baustelle")
        return self._out(200, {"ok": True, "datei": r["name"], "info": "Im Projektordner unter „Fotos Baustelle“."})

    def _beleg(self, tok):
        mx = M88_MAX_UPLOAD_MB * 1048576
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return self._out(400, {"ok": False, "error": "Leere Datei."})
        if n > mx:
            return self._out(413, {"ok": False, "error": f"Datei zu groß (max. {M88_MAX_UPLOAD_MB} MB)."})
        name = os.path.basename(unquote(self.headers.get("X-Filename") or "")).strip() or "foto"
        ext = os.path.splitext(name.lower())[1]
        if ext not in HANDY_EXT:
            ct = (self.headers.get("Content-Type") or "").lower()
            ext = mimetypes.guess_extension(ct.split(";")[0].strip()) or ""
            ext = ".jpg" if ext in (".jpe", ".jfif") else ext
            if ext not in HANDY_EXT:
                return self._out(415, {"ok": False, "error": "Nur Fotos und PDFs."})
            name = os.path.splitext(name)[0] + ext
        if re.fullmatch(r"(image|foto|photo|img|dsc|pxl)?[_\-]?\d*\.\w+", name.lower()):
            name = "Handy_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + name
        tmp = _tmp_for(name)
        left = n
        with open(tmp, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left > 0:
            try:
                os.remove(tmp)
            except Exception:
                pass
            return self._out(400, {"ok": False, "error": "Übertragung abgebrochen."})
        threading.Thread(target=handy_store, args=(tmp, name), daemon=True).start()
        return self._out(200, {"ok": True, "datei": name, "info": "In der Beleg-Prüfliste am PC."})


def m88_running():
    return bool(M88["srv"])


def m88_start(host=None, port=None):
    c = m88_cfg()
    host = host or ("0.0.0.0" if c["modus"] == "lan" else "127.0.0.1")
    port = c["port"] if port is None else int(port)
    with M88["lock"]:
        if M88["srv"]:
            return {"ok": True, "port": M88["port"], "host": M88["host"]}
        try:
            srv = M88Server((host, port), M88Handler)
        except OSError as e:
            M88["fehler"] = f"Port {port} ist belegt oder nicht erlaubt ({e}). Bitte einen anderen Port eintragen."
            raise ValueError(M88["fehler"])
        M88.update(srv=srv, host=host, port=srv.server_address[1], fehler="", gestartet=now_iso())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return {"ok": True, "port": M88["port"], "host": host}


def m88_stop():
    with M88["lock"]:
        srv = M88["srv"]
        M88.update(srv=None, gestartet="", pair=None)
    if srv:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass
    return {"ok": True}


def m88_restart():
    m88_stop()
    if m88_cfg()["aktiv"]:
        return m88_start()
    return {"ok": True}


def _m88_boot_start():
    try:
        if m88_cfg()["aktiv"]:
            m88_start()
    except Exception as e:
        M88["fehler"] = str(e)


HOOK_START.append(_m88_boot_start)


def m88_urls():
    c = m88_cfg()
    port = M88["port"] or c["port"]
    ips = lan_ips() if c["modus"] == "lan" else []
    base = [f"http://127.0.0.1:{port}"] + [f"http://{ip}:{port}" for ip in ips]
    return base


def m88_pair_new(ip=None):
    c = m88_cfg()
    if not m88_running():
        raise ValueError("Die Schnittstelle ist aus. Bitte zuerst einschalten und speichern.")
    if c["modus"] != "lan":
        raise ValueError("Zum Koppeln muss „im Heimnetz erreichbar“ eingestellt sein – sonst kommt das Handy nicht an den PC.")
    ips = lan_ips()
    ip = ip if ip in ips else (ips[0] if ips else "")
    if not ip:
        raise ValueError("Keine Netzwerkverbindung gefunden – der PC muss im WLAN/LAN sein.")
    code = "".join(secrets.choice(M88_ALPHA) for _ in range(8))
    M88["pair"] = {"code": code, "ablauf": time.time() + M88_PAIR_TTL}
    url = f"http://{ip}:{M88['port']}/pair?c={code}"
    return {"ok": True, "code": code[:4] + "-" + code[4:], "url": url, "svg": qr_svg(url), "ips": ips, "ip": ip,
            "base": f"http://{ip}:{M88['port']}/", "gueltig_min": M88_PAIR_TTL // 60}


# ---------------------------------------------------------------------------- Dr. Jey example
M88_JEY = r'''# -*- coding: utf-8 -*-
# PA Rechnung - REST-API Beispiel fuer Dr. Jey (LocalKI)  v1.0.0
# Autor: T. Pfeiffer
# Fragt Kennzahlen und offene Posten aus PA Rechnung ab und kann Zeiten/Notizen buchen.
# Nur Standardbibliothek. Token in PA Rechnung unter Einstellungen > Schnittstelle & Handy erzeugen.
import json
import urllib.request

PA_URL = "__URL__"        # Adresse der Schnittstelle
PA_TOKEN = "HIER_TOKEN_EINTRAGEN"


def pa(path, body=None):
    req = urllib.request.Request(PA_URL.rstrip("/") + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Authorization": "Bearer " + PA_TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def kurzbericht():
    k = pa("/v1/kennzahlen")
    op = pa("/v1/offene-posten")
    zeilen = [f"Umsatz {k['jahr']}: {k['umsatz']:.2f} EUR, Gewinn: {k['gewinn']:.2f} EUR",
              f"Offen: {op['summe']:.2f} EUR in {op['anzahl']} Rechnungen, ueberfaellig: {op['ueberfaellig_summe']:.2f} EUR"]
    for p in op["posten"][:5]:
        zeilen.append(f"  {p['nr']} {p['kunde']}: {p['offen']:.2f} EUR offen, faellig {p['faellig']}")
    return "\n".join(zeilen)


# Werkzeuge fuer Dr. Jey (Funktionsaufrufe): Name -> (Beschreibung, Funktion)
WERKZEUGE = {
    "pa_kurzbericht": ("Umsatz, Gewinn und offene Rechnungen aus PA Rechnung", lambda **a: kurzbericht()),
    "pa_offene_posten": ("Liste der offenen Rechnungen", lambda **a: pa("/v1/offene-posten")),
    "pa_kunde_suchen": ("Kunde suchen (q=Suchbegriff)", lambda **a: pa("/v1/kunden?q=" + urllib.request.quote(a.get("q", "")))),
    "pa_zeit_buchen": ("Arbeitszeit buchen (project_id, stunden, text)", lambda **a: pa("/v1/zeit", a)),
    "pa_notiz": ("Notiz in PA Rechnung ablegen (text)", lambda **a: pa("/v1/notiz", {"text": a.get("text", "")})),
}

if __name__ == "__main__":
    print("INIT PA-API Beispiel v1.0.0")
    print(pa("/v1/status"))
    print(kurzbericht())
'''


def m88_jey_file():
    base = (m88_urls() or ["http://127.0.0.1:8780"])[-1]
    try:
        folder = downloads_dir()
    except Exception:
        folder = os.path.expanduser("~")
    fp = os.path.join(folder, "PA_Rechnung_API_DrJey.py")
    write_file(fp, M88_JEY.replace("__URL__", base), text=True)
    return fp


# ---------------------------------------------------------------------------- PC routes (main UI)
def m88_config():
    c = m88_cfg()
    return {"cfg": c, "laeuft": m88_running(), "host": M88["host"], "port": M88["port"], "fehler": M88["fehler"],
            "gestartet": M88["gestartet"], "urls": m88_urls() if m88_running() else [], "ips": lan_ips(),
            "tokens": m88_tokens(), "ics": callable(globals().get("m84_ics")),
            "notizen_offen": q("SELECT COUNT(*) n FROM m88_notiz WHERE erledigt=0", one=True)["n"]}


def _m88_r_save(h, d):
    c = m88_cfg()
    for k in ("aktiv", "port", "modus", "rate", "geraet_tage"):
        if k in d:
            c[k] = d[k]
    set_setting("m88", {"aktiv": bool(c["aktiv"]), "port": int(float(c["port"] or 8780)), "modus": c["modus"] if c["modus"] in ("lan", "lokal") else "lokal",
                        "rate": int(float(c["rate"] or 120)), "geraet_tage": int(float(c.get("geraet_tage") or 365))})
    try:
        m88_restart()
    except ValueError as e:
        return h._send(200, dict(m88_config(), ok=False, error=str(e)))
    return h._send(200, dict(m88_config(), ok=True))


def _m88_r_token_new(h, d):
    # v2.1.0: typ "ics" = calendar subscription only (m84) - the link sits in the phone calendar / may be shared and
    # must not open the whole read API (invoices, customers, figures) like an API token did before
    typ = "ics" if d.get("typ") == "ics" else "api"
    # the calendar button on the settings page (ui/m88_api_pwa.js) sends name "Kalender-Abo" without typ / tage
    if typ == "api" and "typ" not in d and "tage" not in d and (d.get("name") or "") == "Kalender-Abo":
        typ = "ics"
    tid, tok = m88_token_new(d.get("name") or "", "lesen" if typ == "ics" else (d.get("recht") or "lesen"), typ,
                             int(d["tage"]) if str(d.get("tage") or "").isdigit() and int(d["tage"]) > 0 else None)
    return h._send(200, {"ok": True, "id": tid, "token": tok})


def _m88_r_token_revoke(h, d):
    x("UPDATE m88_token SET aktiv=0, widerrufen=? WHERE id=?", (now_iso(), int(d["id"])))
    return h._send(200, {"ok": True})


def _m88_r_token_delete(h, d):
    for i in d.get("ids") or [d.get("id")]:
        if str(i or "").isdigit():
            x("DELETE FROM m88_token WHERE id=?", (int(i),))
    return h._send(200, {"ok": True})


def _m88_r_log(h, qs):
    try:
        n = max(10, min(2000, int(qs.get("n") or 300)))
    except Exception:
        n = 300
    return h._send(200, {"log": q("SELECT * FROM m88_log ORDER BY id DESC LIMIT ?", (n,))})


def _m88_r_notiz_set(h, d):
    ids = [int(i) for i in (d.get("ids") or [d.get("id")]) if str(i or "").isdigit()]
    for i in ids:
        if d.get("loeschen"):
            x("DELETE FROM m88_notiz WHERE id=?", (i,))
        else:
            x("UPDATE m88_notiz SET erledigt=? WHERE id=?", (1 if d.get("erledigt", True) else 0, i))
    return h._send(200, {"ok": True})


def _m88_r_jey(h, d):
    fp = m88_jey_file()
    try:
        open_path(os.path.dirname(fp))
    except Exception:
        pass
    return h._send(200, {"ok": True, "path": fp})


HOOK_GET["/api/m88/config"] = lambda h, qs: h._send(200, m88_config())
HOOK_POST["/api/m88/save"] = _m88_r_save
HOOK_POST["/api/m88/token/new"] = _m88_r_token_new
HOOK_POST["/api/m88/token/revoke"] = _m88_r_token_revoke
HOOK_POST["/api/m88/token/delete"] = _m88_r_token_delete
HOOK_POST["/api/m88/pair"] = lambda h, d: h._send(200, m88_pair_new(d.get("ip")))
HOOK_POST["/api/m88/pair/stop"] = lambda h, d: (M88.update(pair=None), h._send(200, {"ok": True}))[1]
HOOK_GET["/api/m88/log"] = _m88_r_log
HOOK_POST["/api/m88/log/clear"] = lambda h, d: (x("DELETE FROM m88_log"), h._send(200, {"ok": True}))[1]
HOOK_GET["/api/m88/notizen"] = lambda h, qs: h._send(200, {"notizen": m88_notizen(qs.get("alle") != "1")})
HOOK_POST["/api/m88/notiz/set"] = _m88_r_notiz_set
HOOK_POST["/api/m88/jey"] = _m88_r_jey


def _m88_boot(d):
    try:
        d["m88"] = {"laeuft": m88_running(), "notizen": q("SELECT id, zeit, text, quelle FROM m88_notiz WHERE erledigt=0 ORDER BY id DESC LIMIT 20")}
    except Exception:
        pass


HOOK_BOOT.append(_m88_boot)


def _m88_ex(p):
    toks = m88_tokens()
    out = [_sh("Zugaenge (Tokens)", [("Name", "t", 24), ("Kennung", "t", 14), ("Recht", "t", 10), ("Art", "t", 10), ("Erstellt", "t", 18),
                                      ("Zuletzt", "t", 18), ("Letzte IP", "t", 15), ("Status", "t", 12)],
               [[t["name"], t["prefix"], t["recht"], "Gerät" if t["typ"] == "geraet" else "API", (t["erstellt"] or "")[:16].replace("T", " "),
                 (t["zuletzt"] or "")[:16].replace("T", " "), t["zuletzt_ip"] or "", "aktiv" if t["aktiv"] else "widerrufen"] for t in toks], total=False),
           _sh("Zugriffsprotokoll", [("Zeit", "t", 18), ("IP", "t", 15), ("Methode", "t", 8), ("Pfad", "t", 40), ("Status", "n", 8), ("Zugang", "t", 20)],
               [[(r["zeit"] or "")[:19].replace("T", " "), r["ip"], r["methode"], r["pfad"], r["status"], r["token"] or ""]
                for r in q("SELECT * FROM m88_log ORDER BY id DESC LIMIT 2000")], total=False),
           _sh("Notizen vom Handy / aus der API", [("Zeit", "t", 18), ("Von", "t", 18), ("Text", "t", 60), ("Erledigt", "t", 9)],
               [[(r["zeit"] or "")[:16].replace("T", " "), r["quelle"] or "", r["text"], "ja" if r["erledigt"] else ""] for r in m88_notizen(False)], total=False)]
    return out


EXPORTS["m88_api"] = ("Schnittstelle", _m88_ex)


# ---------------------------------------------------------------------------- self test
def _m88_selftest():
    err = []
    import urllib.request
    import urllib.error
    started = False
    tids = []
    log0 = (q("SELECT COALESCE(MAX(id),0) n FROM m88_log", one=True) or {}).get("n") or 0
    try:
        if m88_running():
            return err
        r = m88_start("127.0.0.1", 0)
        started = True
        base = f"http://127.0.0.1:{r['port']}"

        def call(path, tok=None, body=None):
            hd = {"Content-Type": "application/json"}
            if tok:
                hd["Authorization"] = "Bearer " + tok
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         method="POST" if body is not None else "GET", headers=hd)
            try:
                with urllib.request.urlopen(req, timeout=5) as rr:
                    return rr.status, json.loads(rr.read().decode() or "{}")
            except urllib.error.HTTPError as e:
                return e.code, {}
        c, _ = call("/v1/status")
        if c != 401:
            err.append(f"m88: Anfrage ohne Token liefert {c} statt 401")
        t1, tok_r = m88_token_new("_ST_m88_lesen", "lesen")
        t2, tok_w = m88_token_new("_ST_m88_schreiben", "schreiben")
        tids += [t1, t2]
        c, j = call("/v1/status", tok_r)
        if c != 200 or j.get("version") != APP_VERSION:
            err.append(f"m88: /v1/status mit Token liefert {c}")
        c, j = call("/v1/kennzahlen", tok_r)
        if c != 200 or "umsatz" not in j:
            err.append(f"m88: /v1/kennzahlen liefert {c}")
        c, j = call("/v1/offene-posten", tok_r)
        if c != 200 or "posten" not in j:
            err.append(f"m88: /v1/offene-posten liefert {c}")
        c, _ = call("/v1/notiz", tok_r, {"text": "x"})
        if c != 403:
            err.append(f"m88: Lese-Token darf schreiben ({c})")
        c, j = call("/v1/notiz", tok_w, {"text": "_ST_m88 Notiz"})
        if c != 200 or not j.get("id"):
            err.append(f"m88: Notiz mit Schreib-Token liefert {c}")
        x("DELETE FROM m88_notiz WHERE text='_ST_m88 Notiz'")
        x("UPDATE m88_token SET aktiv=0 WHERE id=?", (t1,))
        c, _ = call("/v1/status", tok_r)
        if c != 401:
            err.append(f"m88: widerrufener Token funktioniert noch ({c})")
        c, _ = call("/v1/status", "pa88_falsch")
        if c != 401:
            err.append("m88: falscher Token nicht abgelehnt")
        c, _ = call(f"/ics/{tok_w}.ics")
        if c != 401:
            err.append(f"m88: API-Token als Kalender-Abo angenommen ({c})")
        if tok_w in m88_mask(f"/ics/{tok_w}.ics") or tok_w in m88_mask(f"/v1/x?t={tok_w}"):
            err.append("m88: Token im Zugriffsprotokoll nicht maskiert")
        if q("SELECT 1 FROM m88_log WHERE id>? AND pfad LIKE ?", (log0, f"%{tok_w}%"), one=True):
            err.append("m88: Token steht im Klartext im Zugriffsprotokoll")
    except Exception as e:
        err.append(f"m88 Ausnahme: {e}")
    finally:
        for t in tids:
            try:
                x("DELETE FROM m88_token WHERE id=?", (t,))
            except Exception:
                pass
        try:
            x("DELETE FROM m88_log WHERE id>?", (log0,))
        except Exception:
            pass
        M88["fails"].clear()
        M88["rate"].clear()
        if started:
            m88_stop()
    return err


HOOK_SELFTEST.append(_m88_selftest)


def _m88_bau_selftest():
    err = []
    try:
        cid = x("INSERT INTO customers (kdnr, firma, strasse, plz, ort, mobil) VALUES ('_ST88B','Baustelle Probe GmbH','Werkstr. 3','50667','Köln','0170 1234567')")
        pid = x("INSERT INTO projects (nr, name, customer_id, status, folders, created) VALUES ('_ST88B','Probeprojekt',?, 'aktiv', '[]', ?)", (cid, now_iso()))
        pj = m88_projekt(pid)
        if not pj["kunde"] or "Köln" not in pj["kunde"]["adresse"] or pj["kunde"]["mobil"] != "0170 1234567":
            err.append("m88: Projektmappe ohne Kundendaten")
        if pj["aufmass_ok"]:
            r = m88_aufmass({"project_id": pid, "beschreibung": "Geländer", "l": 2.5, "b": None, "h": 1.1, "anz": 2, "einheit": "m2"})
            if abs(float(r["ergebnis"]) - 5.5) > 1e-6:
                err.append(f"m88: Aufmaß falsch gerechnet ({r['ergebnis']})")
            try:
                m88_aufmass({"project_id": pid, "beschreibung": ""})
                err.append("m88: leere Aufmaß-Position angenommen")
            except ValueError:
                pass
    except Exception as e:
        err.append(f"m88 Baustelle Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m88_bau_selftest)
