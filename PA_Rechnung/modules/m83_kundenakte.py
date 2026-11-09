# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m83_kundenakte (v2.0.19)
# Kundenakte als Zeitstrahl: alle Ereignisse eines Kunden chronologisch -
# Angebote, Auftraege, Rechnungen, Storno, Zahlungen, Mahnungen, gesendete und
# empfangene E-Mails, Briefe, Projekte, Termine, Fahrten, Unterricht, Projektdateien
# und eigene Notizen (Telefonnotiz, Gespraech, Notiz, Wiedervorlage mit Datum).
# Kennzahlen: Umsatz gesamt / je Jahr, offene Posten, durchschnittliche Zahlungsdauer,
# letzte Aktivitaet, offene Wiedervorlagen. Export als PDF / Excel.
# Andere Module koennen weitere Quellen anmelden: M83_QUELLEN.append(fn(customer_id) -> [event, ...])
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M83_VERSION = "1.0.0"
M83_ARTEN = {"angebot": "Angebot", "auftrag": "Auftragsbestätigung", "rechnung": "Rechnung", "storno": "Storno", "zahlung": "Zahlung",
             "mahnung": "Mahnung", "mail_aus": "E-Mail gesendet", "mail_ein": "E-Mail empfangen", "brief": "Brief", "projekt": "Projekt",
             "termin": "Termin", "fahrt": "Fahrt", "unterricht": "Unterricht", "datei": "Datei", "notiz": "Notiz", "telefon": "Telefonnotiz",
             "gespraech": "Gespräch", "wiedervorlage": "Wiedervorlage", "sonstiges": "Sonstiges"}
M83_NOTIZ_ARTEN = ("notiz", "telefon", "gespraech", "wiedervorlage")
M83_FREEMAIL = {"gmail.com", "googlemail.com", "gmx.de", "gmx.net", "gmx.at", "gmx.ch", "web.de", "t-online.de", "outlook.com", "outlook.de",
                "hotmail.com", "hotmail.de", "live.de", "live.com", "icloud.com", "me.com", "yahoo.com", "yahoo.de", "freenet.de", "posteo.de",
                "mailbox.org", "aol.com", "aol.de", "arcor.de", "vodafone.de", "online.de", "email.de"}
M83_QUELLEN = []


def _m83_schema():
    x("CREATE TABLE IF NOT EXISTS m83_notiz (id INTEGER PRIMARY KEY, customer_id INTEGER, datum TEXT, zeit TEXT, art TEXT, titel TEXT, "
      "text TEXT, wv_datum TEXT, erledigt INTEGER DEFAULT 0, project_id INTEGER, created TEXT, updated TEXT)")
    x("CREATE INDEX IF NOT EXISTS ix_m83_notiz_c ON m83_notiz(customer_id)")


HOOK_SCHEMA.append(_m83_schema)

# ---------------------------------------------------------------------------
# v2.0.19 (R4): dependent rows of deleted objects
# SQLite gives a new row the id of a deleted newest row again (INTEGER PRIMARY KEY without
# AUTOINCREMENT). Notes, own fields, appointments ... of a deleted customer were inherited by the
# next new customer. After "DELETE FROM <table>" the registered cleanups run right away -
# through x(), so they belong to the same user action and come back with "Rueckgaengig" (m89).
# Other modules register: M83_NACH_LOESCHEN.setdefault("customers", []).append(fn)
# ---------------------------------------------------------------------------
M83_NACH_LOESCHEN = {}
_M83_DEL_RX = re.compile(r"^\s*DELETE\s+FROM\s+([A-Za-z_]\w*)", re.I)
_m83_del_tl = threading.local()


def _m83_clean_notes():
    x("DELETE FROM m83_notiz WHERE customer_id IS NOT NULL AND customer_id NOT IN (SELECT id FROM customers)")


M83_NACH_LOESCHEN.setdefault("customers", []).append(_m83_clean_notes)
@chain_step("x", "m83_kundenakte")
def _m83_step_x(_next, sql, args=()):
    rid = _next(sql, args)
    if isinstance(sql, str) and M83_NACH_LOESCHEN and not getattr(_m83_del_tl, "busy", False):
        m = _M83_DEL_RX.match(sql)
        fns = M83_NACH_LOESCHEN.get(m.group(1).lower()) if m else None
        if fns:
            _m83_del_tl.busy = True
            try:
                for fn in fns:
                    try:
                        fn()
                    except Exception:
                        traceback.print_exc()
            finally:
                _m83_del_tl.busy = False
    return rid


def _m83_tab(name):
    return bool(q("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,), one=True))


def _m83_days(a, b):
    try:
        return (datetime.date.fromisoformat(b[:10]) - datetime.date.fromisoformat(a[:10])).days
    except Exception:
        return None


def m83_events(cid):
    c = q("SELECT * FROM customers WHERE id=?", (cid,), one=True)
    if not c:
        raise ValueError("Kunde nicht gefunden.")
    ev = []

    def add(datum, art, titel, text="", betrag=None, status="", ref=None, zeit=""):
        if not datum:
            return
        ev.append({"datum": str(datum)[:10], "zeit": zeit or "", "art": art, "art_de": M83_ARTEN.get(art, art), "titel": titel or "",
                   "text": (text or "")[:400], "betrag": betrag, "status": status or "", "ref": ref or {}})

    invs = q("SELECT id, nr, typ, datum, titel, summe, status, bezahlt_am, storno_von, ref_id FROM invoices WHERE customer_id=?", (cid,))
    inv_ids = [i["id"] for i in invs]
    # v2.1.0: payments of m71 (partial payments, Skonto, written-off rest) - one entry per payment with the amount
    # really received; before only "paid" with the full invoice sum appeared (partial payments were missing)
    pays = {}
    if inv_ids and _m83_tab("m71_zahlung"):
        for k in range(0, len(inv_ids), 500):
            part = inv_ids[k:k + 500]
            for z in q(f"SELECT * FROM m71_zahlung WHERE invoice_id IN ({','.join('?' * len(part))}) ORDER BY datum, id", part):
                pays.setdefault(z["invoice_id"], []).append(z)
    for i in invs:
        typ = i["typ"] or "rechnung"
        add(i["datum"], typ if typ in M83_ARTEN else "rechnung", f"{TYP_DE.get(typ, typ)} {i['nr']}", i["titel"], i["summe"], i["status"],
            {"kind": "invoice", "id": i["id"]})
        if typ in ("rechnung", "storno") and pays.get(i["id"]):
            for z in pays[i["id"]]:
                d_ = _m83_days(i["datum"], z["datum"])
                lbl = {"teil": "Teilzahlung", "skonto": "Skonto", "ausbuchung": "Ausgebucht"}.get(z["art"], "Erstattung" if typ == "storno" else "Zahlung")
                add(z["datum"], "zahlung", f"{lbl} zu {i['nr']}", (f"nach {d_} Tagen" if d_ is not None and z["art"] in ("zahlung", "teil") else "")
                    + (" · " if z.get("notiz") and z["art"] in ("zahlung", "teil") and d_ is not None else "") + (z.get("notiz") or ""),
                    z["betrag"], z["art"], {"kind": "invoice", "id": i["id"]})
            continue
        if typ == "rechnung" and i["status"] == "bezahlt" and i["bezahlt_am"]:
            d_ = _m83_days(i["datum"], i["bezahlt_am"])
            add(i["bezahlt_am"], "zahlung", f"Zahlung zu {i['nr']}", f"nach {d_} Tagen" if d_ is not None else "", i["summe"], "bezahlt",
                {"kind": "invoice", "id": i["id"]})
    if inv_ids:
        ph = ",".join("?" * len(inv_ids))
        for m in q(f"SELECT m.*, i.nr FROM mahnungen m JOIN invoices i ON i.id=m.invoice_id WHERE m.invoice_id IN ({ph})", inv_ids):
            add(m["datum"], "mahnung", f"{MAHN_TITLES[min(int(m['stufe'] or 0), 3)]} zu {m['nr']}", f"Frist bis {de_date(m['frist_bis'])}",
                m["betrag"], "", {"kind": "invoice", "id": m["invoice_id"]})
        for m in q(f"SELECT l.*, i.nr FROM mail_log l JOIN invoices i ON i.id=l.doc_id WHERE l.doc_id IN ({ph})", inv_ids):
            add(m["datum"], "mail_aus", m["betreff"] or f"Mail zu {m['nr']}", f"an {m['an']}" + ("" if m["ok"] else f" - FEHLER: {m['fehler'] or ''}"),
                None, "ok" if m["ok"] else "fehler", {"kind": "invoice", "id": m["doc_id"]}, (m["datum"] or "")[11:16])
    # received mails
    mail = (c.get("mail") or "").strip().lower()
    if mail and _m83_tab("mail_inbox"):
        dom = mail.split("@")[-1] if "@" in mail else ""
        if dom and dom not in M83_FREEMAIL:
            rows = q("SELECT id, absender, absender_addr, betreff, datum, urteil, status FROM mail_inbox WHERE lower(absender_addr)=? OR lower(absender_addr) LIKE ? "
                     "ORDER BY datum DESC LIMIT 300", (mail, "%@" + dom))
        else:
            rows = q("SELECT id, absender, absender_addr, betreff, datum, urteil, status FROM mail_inbox WHERE lower(absender_addr)=? ORDER BY datum DESC LIMIT 300", (mail,))
        for m in rows:
            add(m["datum"], "mail_ein", m["betreff"] or "(ohne Betreff)", f"von {m['absender'] or m['absender_addr']}", None, m["status"] or "",
                {"kind": "mail", "id": m["id"]}, (m["datum"] or "")[11:16])
    if _m83_tab("briefe"):
        for b in q("SELECT id, datum, betreff FROM briefe WHERE customer_id=?", (cid,)):
            add(b["datum"], "brief", b["betreff"] or "Brief", "", None, "", {"kind": "brief", "id": b["id"]})
    projs = q("SELECT id, nr, name, bereich, status, start, ende, created FROM projects WHERE customer_id=?", (cid,))
    pids = [p["id"] for p in projs]
    for p in projs:
        add(p["start"] or (p["created"] or "")[:10], "projekt", f"Projekt {p['nr'] or ''} {p['name'] or ''}".strip(), f"{p['bereich'] or ''} · {p['status'] or ''}",
            None, p["status"], {"kind": "project", "id": p["id"]})
        if p["ende"] and p["status"] in ("abgeschlossen", "erledigt", "fertig"):
            add(p["ende"], "projekt", f"Projekt {p['nr'] or ''} abgeschlossen", p["name"], None, p["status"], {"kind": "project", "id": p["id"]})
    # trips
    if pids:
        ph = ",".join("?" * len(pids))
        trips = q(f"SELECT * FROM fahrten WHERE customer_id=? OR project_id IN ({ph})", [cid] + pids)
    else:
        trips = q("SELECT * FROM fahrten WHERE customer_id=?", (cid,))
    for f in trips:
        add(f["datum"], "fahrt", f"Fahrt nach {f['ziel'] or '?'}", f"{num_de(float(f['km'] or 0), 1)} km · {f['zweck'] or ''}", None, "", {"kind": "trip", "id": f["id"]})
    # project files
    if pids:
        ph = ",".join("?" * len(pids))
        for pf in q(f"SELECT f.id, f.project_id, f.name, f.kind, f.added, p.nr FROM project_files f JOIN projects p ON p.id=f.project_id WHERE f.project_id IN ({ph}) "
                    "ORDER BY f.added DESC LIMIT 300", pids):
            add((pf["added"] or "")[:10], "datei", pf["name"], f"{pf['kind'] or ''} · Projekt {pf['nr'] or ''}", None, "", {"kind": "project", "id": pf["project_id"]})
    # lessons: one entry per month
    st_ids = [r["id"] for r in q("SELECT id FROM students WHERE customer_id=? OR person_customer_id=?", (cid, cid))]
    if st_ids:
        ph = ",".join("?" * len(st_ids))
        for r in q(f"SELECT substr(datum,1,7) mon, COUNT(*) n, SUM(CASE WHEN invoice_id IS NULL THEN 1 ELSE 0 END) offen, MAX(datum) last "
                   f"FROM lessons WHERE student_id IN ({ph}) GROUP BY substr(datum,1,7)", st_ids):
            add(r["last"], "unterricht", f"Unterricht {MONTHS_DE[int(r['mon'][5:7]) - 1]} {r['mon'][:4]}", f"{r['n']} Stunde(n)" + (f", {r['offen']} nicht abgerechnet" if r["offen"] else ""),
                None, "", {"kind": "school", "id": r["mon"]})
    # calendar (TimeTree) - name of the customer in title / place
    names = [n for n in {(c.get("firma") or "").strip(), (c.get("name") or "").strip()} if len(n) >= 4]
    if names and _m83_tab("kal_event"):
        cond = " OR ".join(["lower(title) LIKE ? OR lower(location) LIKE ?"] * len(names))
        args = []
        for n in names:
            args += ["%" + n.lower() + "%", "%" + n.lower() + "%"]
        for e in q(f"SELECT uuid, title, start_ms, start_tz, all_day, location FROM kal_event WHERE {cond} ORDER BY start_ms DESC LIMIT 200", args):
            try:
                dt_ = ms_to_local(e["start_ms"], e["start_tz"], bool(e["all_day"]))
                add(dt_.strftime("%Y-%m-%d"), "termin", e["title"], e["location"] or "", None, "", {"kind": "kal", "id": dt_.strftime("%Y-%m-%d")},
                    "" if e["all_day"] else dt_.strftime("%H:%M"))
            except Exception:
                pass
    if _m83_tab("m84_termin"):
        for e in q("SELECT * FROM m84_termin WHERE customer_id=?", (cid,)):
            add(e["datum"], "termin", e["titel"], e["ort"] or "", None, "", {"kind": "kal", "id": e["datum"]}, "" if e["ganztags"] else (e["von"] or ""))
    # own notes
    for n in q("SELECT * FROM m83_notiz WHERE customer_id=?", (cid,)):
        add(n["datum"], n["art"] if n["art"] in M83_NOTIZ_ARTEN else "notiz", n["titel"] or M83_ARTEN.get(n["art"], "Notiz"), n["text"], None,
            ("erledigt" if n["erledigt"] else ("fällig " + de_date(n["wv_datum"])) if n["wv_datum"] else ""), {"kind": "notiz", "id": n["id"]}, n["zeit"] or "")
    for fn in M83_QUELLEN:
        try:
            for e in fn(cid) or []:
                add(e.get("datum"), e.get("art") or "sonstiges", e.get("titel"), e.get("text"), e.get("betrag"), e.get("status"), e.get("ref"), e.get("zeit"))
        except Exception:
            traceback.print_exc()
    ev.sort(key=lambda e: (e["datum"], e["zeit"]), reverse=True)
    return c, ev, invs


def _m83_offen(offen):
    """v2.0.19 (R4): open amount = rest after partial payments / skonto (m71), not the full invoice sum"""
    tot = 0.0
    for i in offen:
        try:
            tot += float(m71_state(i["id"])["rest"]) if "m71_state" in globals() else float(i["summe"] or 0)
        except Exception:
            tot += float(i["summe"] or 0)
    return round(tot, 2)


def m83_akte(cid, art="", qtext=""):
    cid = int(cid)
    c, ev, invs = m83_events(cid)
    rech = [i for i in invs if (i["typ"] or "rechnung") in ("rechnung", "storno") and i["status"] not in ("entwurf", "storniert")]
    by_year = {}
    for i in rech:
        y = (i["datum"] or "")[:4]
        by_year[y] = round(by_year.get(y, 0) + float(i["summe"] or 0), 2)
    offen = [i for i in invs if (i["typ"] or "rechnung") == "rechnung" and i["status"] == "offen"]
    days = [d for d in (_m83_days(i["datum"], i["bezahlt_am"]) for i in invs if (i["typ"] or "rechnung") == "rechnung" and i["status"] == "bezahlt" and i["bezahlt_am"]) if d is not None and d >= 0]
    t = today()
    past = [e["datum"] for e in ev if e["datum"] <= t]
    ang = [i for i in invs if i["typ"] == "angebot"]
    ang_ok = [i for i in ang if i["status"] in ("angenommen", "erledigt")]
    wv = q("SELECT * FROM m83_notiz WHERE customer_id=? AND COALESCE(wv_datum,'')!='' AND COALESCE(erledigt,0)=0 ORDER BY wv_datum", (cid,))
    kpi = {"umsatz_gesamt": round(sum(float(i["summe"] or 0) for i in rech), 2), "umsatz_jahr": by_year,
           "umsatz_akt": by_year.get(t[:4], 0.0), "offen_summe": _m83_offen(offen), "offen_n": len(offen),
           "zahlungsdauer": round(sum(days) / len(days), 1) if days else None, "zahlungen_n": len(days),
           "letzte": max(past) if past else "", "erste": min(e["datum"] for e in ev) if ev else "",
           "angebote_n": len(ang), "angebote_ok": len(ang_ok), "wv_offen": len(wv), "wv_faellig": len([w for w in wv if w["wv_datum"] <= t])}
    counts = {}
    for e in ev:
        counts[e["art"]] = counts.get(e["art"], 0) + 1
    if art:
        arts = set(art.split(","))
        ev = [e for e in ev if e["art"] in arts]
    if qtext:
        ql = qtext.lower()
        ev = [e for e in ev if ql in (e["titel"] + " " + e["text"] + " " + e["art_de"]).lower()]
    return {"ok": True, "kunde": c, "kpi": kpi, "events": ev, "counts": counts, "arten": M83_ARTEN, "wiedervorlagen": wv}


def m83_wv_due(days_ahead=0):
    lim = (datetime.date.today() + datetime.timedelta(days=days_ahead)).isoformat()
    return q("SELECT n.*, COALESCE(NULLIF(c.firma,''), c.name) kunde FROM m83_notiz n LEFT JOIN customers c ON c.id=n.customer_id "
             "WHERE COALESCE(n.wv_datum,'')!='' AND COALESCE(n.erledigt,0)=0 AND n.wv_datum<=? ORDER BY n.wv_datum", (lim,))


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
def _m83_r_akte(h, qs):
    try:
        return h._send(200, m83_akte(qs.get("id"), qs.get("art") or "", qs.get("q") or ""))
    except ValueError as e:
        return h._send(200, {"ok": False, "error": str(e)})


def _m83_r_save(h, d):
    art = d.get("art") if d.get("art") in M83_NOTIZ_ARTEN else "notiz"
    vals = (int(d["customer_id"]), (d.get("datum") or today())[:10], (d.get("zeit") or "")[:5], art, (d.get("titel") or "")[:200],
            (d.get("text") or "")[:5000], (d.get("wv_datum") or "")[:10], 1 if d.get("erledigt") else 0, d.get("project_id") or None)
    if d.get("id"):
        x("UPDATE m83_notiz SET customer_id=?, datum=?, zeit=?, art=?, titel=?, text=?, wv_datum=?, erledigt=?, project_id=?, updated=? WHERE id=?",
          vals + (now_iso(), int(d["id"])))
        nid = int(d["id"])
    else:
        nid = x("INSERT INTO m83_notiz (customer_id, datum, zeit, art, titel, text, wv_datum, erledigt, project_id, created, updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", vals + (now_iso(), now_iso()))
    return h._send(200, {"ok": True, "id": nid})


def _m83_r_del(h, d):
    ids = d.get("ids") or [d.get("id")]
    for i in ids:
        if i:
            x("DELETE FROM m83_notiz WHERE id=?", (int(i),))
    return h._send(200, {"ok": True})


def _m83_r_done(h, d):
    x("UPDATE m83_notiz SET erledigt=?, updated=? WHERE id=?", (1 if d.get("erledigt", True) else 0, now_iso(), int(d["id"])))
    return h._send(200, {"ok": True})


def _m83_r_get(h, qs):
    return h._send(200, {"ok": True, "notiz": q("SELECT * FROM m83_notiz WHERE id=?", (int(qs["id"]),), one=True)})


def _m83_r_wv(h, qs):
    return h._send(200, {"ok": True, "rows": m83_wv_due(int(qs.get("tage") or 0))})


HOOK_GET["/api/m83/akte"] = _m83_r_akte
HOOK_GET["/api/m83/notiz"] = _m83_r_get
HOOK_GET["/api/m83/wv"] = _m83_r_wv
HOOK_POST["/api/m83/notiz"] = _m83_r_save
HOOK_POST["/api/m83/notiz_delete"] = _m83_r_del
HOOK_POST["/api/m83/notiz_done"] = _m83_r_done


def _m83_boot(d):
    try:
        d["m83"] = {"wv_faellig": len(m83_wv_due(0))}
    except Exception:
        d["m83"] = {"wv_faellig": 0}


HOOK_BOOT.append(_m83_boot)


def _m83_ex(p):
    cid = p.get("id") or p.get("customer_id")
    if not cid and _ids(p):
        cid = sorted(_ids(p))[0]
    if not cid:
        raise ValueError("Kein Kunde gewählt.")
    a = m83_akte(int(cid), p.get("art") or "", p.get("q") or "")
    c, k = a["kunde"], a["kpi"]
    name = c.get("firma") or c.get("name") or c.get("kdnr")
    stamm = [("Kunde", name), ("Kunden-Nr.", c.get("kdnr") or ""), ("Anschrift", ", ".join(address_lines(c))),
             ("Telefon", " / ".join(v for v in (c.get("tel"), c.get("mobil")) if v)), ("E-Mail", c.get("mail") or ""), ("Notiz", c.get("notiz") or "")]
    kz = [("Umsatz gesamt", money(k["umsatz_gesamt"])), (f"Umsatz {today()[:4]}", money(k["umsatz_akt"])),
          ("Offene Posten", f"{money(k['offen_summe'])} ({k['offen_n']} Rechnung(en))"),
          ("Ø Zahlungsdauer", (num_de(k["zahlungsdauer"], 1) + " Tage") if k["zahlungsdauer"] is not None else "–"),
          ("Angebote / angenommen", f"{k['angebote_n']} / {k['angebote_ok']}"), ("Kunde seit (erste Aktivität)", de_date(k["erste"])),
          ("Letzte Aktivität", de_date(k["letzte"])), ("Offene Wiedervorlagen", str(k["wv_offen"]))]
    kz += [(f"Umsatz {y}", money(v)) for y, v in sorted(k["umsatz_jahr"].items(), reverse=True)]
    rows = [[e["datum"], e["zeit"], e["art_de"], e["titel"], e["text"], e["betrag"] if e["betrag"] is not None else "", e["status"]] for e in a["events"]]
    return [_kv(f"Kundenakte {name}", stamm, f"Stand {de_date(today())}"), _kv("Kennzahlen", kz),
            _sh("Zeitstrahl", [("Datum", "d", 11), ("Zeit", "t", 6), ("Art", "t", 16), ("Titel", "t", 34), ("Details", "t", 40), ("Betrag", "m", 12),
                               ("Status", "t", 12)], rows, "", total=False)]


EXPORTS["m83_kundenakte"] = ("Kundenakte", _m83_ex)


def _m83_selftest():
    err = []
    try:
        cid = x("INSERT INTO customers (kdnr, firma, name, mail, created) VALUES (?,?,?,?,?)", ("_ST_M83", "Zeitstrahl Test GmbH", "", "info@zeitstrahl-test.de", now_iso()))
        iid, nr = save_invoice({"customer_id": cid, "kdnr": "_ST_M83", "addr": ["Zeitstrahl Test GmbH"], "datum": "2026-01-10", "typ": "rechnung",
                                "status": "offen", "items": [{"qty": 1, "name": "Test", "price": 100.0}]}, bump=False)
        x("UPDATE invoices SET status='bezahlt', bezahlt_am='2026-01-20' WHERE id=?", (iid,))
        x("INSERT INTO m83_notiz (customer_id, datum, art, titel, wv_datum, erledigt) VALUES (?,?,?,?,?,0)", (cid, "2026-01-05", "telefon", "Anruf", "2000-01-01"))
        a = m83_akte(cid)
        arts = {e["art"] for e in a["events"]}
        if not {"rechnung", "zahlung", "telefon"} <= arts:
            err.append(f"m83: Zeitstrahl unvollständig ({sorted(arts)})")
        if a["kpi"]["zahlungsdauer"] != 10.0:
            err.append(f"m83: Zahlungsdauer falsch ({a['kpi']['zahlungsdauer']})")
        if abs(a["kpi"]["umsatz_gesamt"] - 100.0) > 0.001 or a["kpi"]["wv_faellig"] != 1:
            err.append("m83: Kennzahlen falsch")
        if not any(r["customer_id"] == cid for r in m83_wv_due()):
            err.append("m83: Wiedervorlage nicht fällig")
        sh = _m83_ex({"id": cid})
        if len(sh) != 3:
            err.append("m83: Export unvollständig")
        x("DELETE FROM m83_notiz WHERE customer_id=?", (cid,))
        x("DELETE FROM items WHERE invoice_id=?", (iid,))
        x("DELETE FROM invoices WHERE id=?", (iid,))
        x("DELETE FROM customers WHERE id=?", (cid,))
    except Exception as e:
        traceback.print_exc()
        err.append(f"m83 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m83_selftest)
