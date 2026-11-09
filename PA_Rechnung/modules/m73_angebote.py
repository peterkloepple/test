# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m73_angebote (v2.0.19)
# Angebote nachfassen: Status offen / angenommen / abgelehnt / abgelaufen, Ablehnungsgrund,
# Wiedervorlage (Standard x Tage nach Versand), Erinnerung auf der Uebersicht, Nachfass-Mail aus
# Vorlage (Angebots-PDF im Anhang), Auswertung Annahmequote und Volumen je Bereich und je Kunde.
# Status "angenommen"/"abgelehnt"/"offen" stehen wie bisher in invoices.status; "abgelaufen" ist
# entweder abgeleitet (gueltig_bis vorbei) oder per Knopf gesetzt (m73_angebot.abgelaufen).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M73_VERSION = "1.0.0"
M73_GRUENDE = ["Preis zu hoch", "Anderer Anbieter", "Projekt verschoben", "Projekt abgesagt", "Keine Rückmeldung", "Budget fehlt", "Sonstiges"]
M73_DEFAULTS = {"m73_tage": 7, "m73_tage2": 14,
                "m73_mail_betreff": "Nachfrage zu unserem Angebot [Nummer]",
                "m73_mail_text": "Guten Tag [Name],\n\nvor einigen Tagen haben wir Ihnen unser Angebot [Nummer] ([Titel]) über [Betrag] geschickt. "
                                 "Haben Sie noch Fragen dazu oder sollen wir etwas anpassen? Das Angebot ist gültig bis [Gueltig].\n\n"
                                 "Über eine kurze Rückmeldung freuen wir uns.\n\nMit freundlichen Grüßen\n[Inhaber]"}
M73_STATUS = {"offen": "offen", "angenommen": "angenommen", "abgelehnt": "abgelehnt", "abgelaufen": "abgelaufen"}


def _m73_schema():
    x("CREATE TABLE IF NOT EXISTS m73_angebot (invoice_id INTEGER PRIMARY KEY, wiedervorlage TEXT, grund TEXT, notiz TEXT, "
      "nachfass INTEGER DEFAULT 0, letzte_nachfass TEXT, abgelaufen INTEGER DEFAULT 0, entschieden_am TEXT, updated TEXT)")


HOOK_SCHEMA.append(_m73_schema)


def m73_cfg(s=None):
    s = s or get_settings()
    c = {k: s.get(k, v) for k, v in M73_DEFAULTS.items()}
    for k in ("m73_tage", "m73_tage2"):
        try:
            c[k] = int(c[k])
        except Exception:
            c[k] = M73_DEFAULTS[k]
    return c


def _m73_add(iso, n):
    d = d_iso(iso) or datetime.date.today()
    return (d + datetime.timedelta(days=int(n))).isoformat()


def m73_list(year=None):
    cfg = m73_cfg()
    t = today()
    meta = {r["invoice_id"]: r for r in q("SELECT * FROM m73_angebot")}
    kids = {}
    for r in q("SELECT ref_id, id, nr, typ, status FROM invoices WHERE ref_id IS NOT NULL"):
        kids.setdefault(r["ref_id"], []).append(r)
    proj = {p["id"]: p for p in q("SELECT id, nr, name, bereich FROM projects")}
    out = []
    sql = "SELECT * FROM invoices WHERE typ='angebot' AND status!='entwurf'"
    args = ()
    if year:
        sql += " AND substr(datum,1,4)=?"
        args = (str(year),)
    for inv in q(sql + " ORDER BY datum DESC, nr DESC", args):
        m = meta.get(inv["id"]) or {}
        ch = kids.get(inv["id"], [])
        if inv["status"] in ("angenommen", "erledigt") or any(c["typ"] in ("auftrag", "rechnung") for c in ch):
            st = "angenommen"
        elif inv["status"] == "abgelehnt":
            st = "abgelehnt"
        elif m.get("abgelaufen") or (inv["gueltig_bis"] and inv["gueltig_bis"] < t):
            st = "abgelaufen"
        else:
            st = "offen"
        basis = inv["versendet_am"] or inv["datum"]
        wv = m.get("wiedervorlage") or ""
        if not wv and st == "offen":
            wv = _m73_add(basis, cfg["m73_tage"] if not m.get("nachfass") else cfg["m73_tage2"])
        p = proj.get(inv["project_id"]) or {}
        out.append({"id": inv["id"], "nr": inv["nr"], "datum": inv["datum"], "titel": inv["titel"] or "", "summe": inv["summe"] or 0,
                    "customer_id": inv["customer_id"], "name": inv_name(inv), "gueltig_bis": inv["gueltig_bis"] or "",
                    "versendet_am": inv["versendet_am"] or "", "status": st, "grund": m.get("grund") or "", "notiz": m.get("notiz") or "",
                    "wiedervorlage": wv if st == "offen" else "", "faellig": st == "offen" and bool(wv) and wv <= t,
                    "nachfass": m.get("nachfass") or 0, "letzte_nachfass": m.get("letzte_nachfass") or "",
                    "entschieden_am": m.get("entschieden_am") or "", "project_id": inv["project_id"],
                    "bereich": p.get("bereich") or "ohne Projekt", "projekt": (p.get("nr") or "") + (" " + p["name"] if p.get("name") else ""),
                    "folge": [{"id": c["id"], "nr": c["nr"], "typ": c["typ"]} for c in ch]})
    return out


def _m73_meta(iid):
    if not q("SELECT invoice_id FROM m73_angebot WHERE invoice_id=?", (iid,), one=True):
        x("INSERT INTO m73_angebot (invoice_id, updated) VALUES (?,?)", (iid, now_iso()))


def m73_set_status(iid, status, grund="", notiz=None):
    if status not in M73_STATUS:
        raise ValueError("Unbekannter Status.")
    inv = q("SELECT * FROM invoices WHERE id=? AND typ='angebot'", (int(iid),), one=True)
    if not inv:
        raise ValueError("Angebot nicht gefunden.")
    _m73_meta(inv["id"])
    if status == "abgelaufen":
        x("UPDATE m73_angebot SET abgelaufen=1, entschieden_am=?, grund=COALESCE(NULLIF(?,''),grund), updated=? WHERE invoice_id=?",
          (today(), grund or "", now_iso(), inv["id"]))
        if inv["status"] != "offen":
            x("UPDATE invoices SET status='offen' WHERE id=?", (inv["id"],))
    else:
        x("UPDATE invoices SET status=?, updated=? WHERE id=?", (status, now_iso(), inv["id"]))
        x("UPDATE m73_angebot SET abgelaufen=0, entschieden_am=?, grund=?, updated=? WHERE invoice_id=?",
          (today() if status != "offen" else "", grund if status == "abgelehnt" else "", now_iso(), inv["id"]))
    if notiz is not None:
        x("UPDATE m73_angebot SET notiz=? WHERE invoice_id=?", (notiz[:500], inv["id"]))
    return {"ok": True}


def m73_wiedervorlage(iid, datum, notiz=None):
    _m73_meta(int(iid))
    if datum and not d_iso(datum):
        raise ValueError("Ungültiges Datum.")
    x("UPDATE m73_angebot SET wiedervorlage=?, updated=? WHERE invoice_id=?", (datum or "", now_iso(), int(iid)))
    if notiz is not None:
        x("UPDATE m73_angebot SET notiz=? WHERE invoice_id=?", (notiz[:500], int(iid)))
    return {"ok": True}


def _m73_fill(text, inv):
    s = get_settings()
    cu = q("SELECT * FROM customers WHERE id=?", (inv.get("customer_id"),), one=True) if inv.get("customer_id") else None
    return (text or "").replace("[Nummer]", inv.get("nr") or "").replace("[Titel]", inv.get("titel") or "") \
        .replace("[Betrag]", money(inv.get("summe") or 0)).replace("[Gueltig]", de_date(inv.get("gueltig_bis") or "")) \
        .replace("[Gültig]", de_date(inv.get("gueltig_bis") or "")).replace("[Datum]", de_date(inv.get("datum") or "")) \
        .replace("[Name]", ((cu["name"] or cu["firma"]) if cu else "") or "").replace("[Inhaber]", s.get("inhaber") or "") \
        .replace("[Firma]", s.get("firma") or "").replace("\\n", "\n")


def m73_mail_prepare(iid):
    inv = q("SELECT * FROM invoices WHERE id=? AND typ='angebot'", (int(iid),), one=True)
    if not inv:
        raise ValueError("Angebot nicht gefunden.")
    cfg = m73_cfg()
    cu = q("SELECT mail FROM customers WHERE id=?", (inv["customer_id"],), one=True) if inv["customer_id"] else None
    try:
        conf = mail_configured()
    except Exception:
        conf = False
    return {"ok": True, "to": (cu["mail"] if cu else "") or "", "subject": _m73_fill(cfg["m73_mail_betreff"], inv),
            "body": _m73_fill(cfg["m73_mail_text"], inv), "configured": conf}


def m73_nachfass(d):
    iid = int(d["id"])
    mail_send({"doc_id": iid, "to": d.get("to") or "", "cc": d.get("cc") or "", "subject": d.get("subject") or "", "body": d.get("body") or ""})
    _m73_meta(iid)
    cfg = m73_cfg()
    x("UPDATE m73_angebot SET nachfass=COALESCE(nachfass,0)+1, letzte_nachfass=?, wiedervorlage=?, updated=? WHERE invoice_id=?",
      (today(), _m73_add(today(), cfg["m73_tage2"]), now_iso(), iid))
    return {"ok": True}


def m73_auswertung(year=None):
    rows = m73_list(year)

    def agg(key):
        g = {}
        for r in rows:
            k = r[key] or "–"
            a = g.setdefault(k, {"name": k, "anzahl": 0, "volumen": 0.0, "angenommen": 0, "vol_angenommen": 0.0, "abgelehnt": 0,
                                 "abgelaufen": 0, "offen": 0, "vol_offen": 0.0})
            a["anzahl"] += 1
            a["volumen"] += r["summe"]
            a[r["status"]] += 1
            if r["status"] == "angenommen":
                a["vol_angenommen"] += r["summe"]
            if r["status"] == "offen":
                a["vol_offen"] += r["summe"]
        for a in g.values():
            entsch = a["angenommen"] + a["abgelehnt"] + a["abgelaufen"]
            a["quote"] = round(100.0 * a["angenommen"] / entsch, 1) if entsch else None
            a["quote_vol"] = round(100.0 * a["vol_angenommen"] / max(0.01, a["volumen"] - a["vol_offen"]), 1) if entsch else None
            for k in ("volumen", "vol_angenommen", "vol_offen"):
                a[k] = round(a[k], 2)
        return sorted(g.values(), key=lambda a: -a["volumen"])
    alle = {"anzahl": len(rows), "volumen": round(sum(r["summe"] for r in rows), 2)}
    for st in M73_STATUS:
        alle[st] = sum(1 for r in rows if r["status"] == st)
        alle["vol_" + st] = round(sum(r["summe"] for r in rows if r["status"] == st), 2)
    entsch = alle["angenommen"] + alle["abgelehnt"] + alle["abgelaufen"]
    alle["quote"] = round(100.0 * alle["angenommen"] / entsch, 1) if entsch else None
    gr = {}
    for r in rows:
        if r["status"] == "abgelehnt":
            k = r["grund"] or "ohne Angabe"
            gr[k] = gr.get(k, 0) + 1
    for r in rows:
        r["_kunde"] = r["name"]
    return {"gesamt": alle, "bereich": agg("bereich"), "kunde": agg("_kunde"), "gruende": sorted(gr.items(), key=lambda kv: -kv[1])}


def _m73_list_route(h, qs):
    y = qs.get("year") or ""
    rows = m73_list(int(y) if y.isdigit() else None)
    a = m73_auswertung(int(y) if y.isdigit() else None)
    for r in rows:
        r.pop("_kunde", None)
    return h._send(200, {"ok": True, "zeilen": rows, "auswertung": a, "cfg": m73_cfg(), "gruende": M73_GRUENDE})


def _m73_cfg_route(h, d):
    for k, v in M73_DEFAULTS.items():
        if k in d:
            set_setting(k, int(float(d[k] or 0)) if isinstance(v, int) else str(d[k]))
    return h._send(200, {"ok": True, "cfg": m73_cfg()})


HOOK_GET["/api/m73/list"] = _m73_list_route
HOOK_GET["/api/m73/mail"] = lambda h, qs: h._send(200, m73_mail_prepare(int(qs.get("id") or 0)))
HOOK_POST["/api/m73/status"] = lambda h, d: h._send(200, m73_set_status(d["id"], d.get("status"), d.get("grund") or "", d.get("notiz")))
HOOK_POST["/api/m73/wv"] = lambda h, d: h._send(200, m73_wiedervorlage(d["id"], d.get("datum") or "", d.get("notiz")))
HOOK_POST["/api/m73/nachfass"] = lambda h, d: h._send(200, m73_nachfass(d))
HOOK_POST["/api/m73/cfg"] = _m73_cfg_route


def _m73_boot(d):
    rows = m73_list()
    due = [r for r in rows if r["faellig"]]
    d["m73"] = {"faellig": len(due), "offen": sum(1 for r in rows if r["status"] == "offen"),
                "abgelaufen_ids": [r["id"] for r in rows if r["status"] == "abgelaufen"],
                "due": [{"id": r["id"], "nr": r["nr"], "name": r["name"], "summe": r["summe"], "wv": r["wiedervorlage"]} for r in due[:8]]}


HOOK_BOOT.append(_m73_boot)


def _m73_ex(p):
    y = str(p.get("year") or "")
    rows = m73_list(int(y) if y.isdigit() else None)
    ids = _ids(p)
    if ids:
        rows = [r for r in rows if r["id"] in ids]
    st = p.get("status") or ""
    if st:
        rows = [r for r in rows if r["status"] == st]
    a = m73_auswertung(int(y) if y.isdigit() else None)
    cols_a = [("Name", "t", 30), ("Angebote", "n", 9), ("Volumen", "m", 13), ("Angenommen", "n", 11), ("Vol. angenommen", "m", 14),
              ("Abgelehnt", "n", 10), ("Abgelaufen", "n", 10), ("Offen", "n", 8), ("Quote %", "n", 9)]
    conv = lambda g: [[r["name"], r["anzahl"], r["volumen"], r["angenommen"], r["vol_angenommen"], r["abgelehnt"], r["abgelaufen"],
                       r["offen"], r["quote"] if r["quote"] is not None else ""] for r in g]
    return [_sh("Angebote" + (f" {y}" if y else ""), [("Nr.", "t", 13), ("Datum", "d", 11), ("Kunde", "t", 28), ("Titel", "t", 28),
                                                     ("Bereich", "t", 14), ("Status", "t", 12), ("Grund", "t", 20), ("Wiedervorlage", "d", 12),
                                                     ("Nachgefasst", "n", 10), ("Betrag", "m", 12)],
                [[r["nr"], r["datum"], r["name"], r["titel"], r["bereich"], r["status"], r["grund"], r["wiedervorlage"], r["nachfass"], r["summe"]]
                 for r in rows], f"Stand {de_date(today())}"),
            _sh("Auswertung je Bereich", cols_a, conv(a["bereich"]), "Quote = angenommen / (angenommen + abgelehnt + abgelaufen)", total=False),
            _sh("Auswertung je Kunde", cols_a, conv(a["kunde"]), "", total=False)]


EXPORTS["m73_angebote"] = ("Angebote", _m73_ex)


def _m73_selftest():
    err = []
    iid = None
    try:
        iid, nr = save_invoice({"nr": "_ST73-0001", "customer_id": None, "kdnr": "", "addr": ["Selbsttest"], "datum": today(),
                                "titel": "Selbsttest m73", "toptext": "", "foottext": "", "zahlart": "Ueberweisung", "frist": 14,
                                "status": "offen", "typ": "angebot", "gueltig_bis": _m73_add(today(), 30),
                                "items": [{"qty": 1, "name": "Test", "price": 500.0, "rabatt": 0}]}, bump=False)
        r = next((r for r in m73_list() if r["id"] == iid), None)
        if not r or r["status"] != "offen" or r["wiedervorlage"] != _m73_add(today(), m73_cfg()["m73_tage"]):
            err.append("m73: Wiedervorlage/Status neu falsch")
        m73_set_status(iid, "abgelehnt", "Preis zu hoch")
        a = m73_auswertung()
        if a["gesamt"]["abgelehnt"] < 1 or not any(g[0] == "Preis zu hoch" for g in a["gruende"]):
            err.append("m73: Ablehnung nicht ausgewertet")
        m73_set_status(iid, "abgelaufen")
        if next(r for r in m73_list() if r["id"] == iid)["status"] != "abgelaufen":
            err.append("m73: abgelaufen nicht gesetzt")
    except Exception as e:
        err.append(f"m73 Ausnahme: {e}")
    finally:
        if iid:
            x("DELETE FROM m73_angebot WHERE invoice_id=?", (iid,))
            x("DELETE FROM items WHERE invoice_id=?", (iid,))
            x("DELETE FROM invoices WHERE id=?", (iid,))
    return err


HOOK_SELFTEST.append(_m73_selftest)
