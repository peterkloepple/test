# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m72_mahnlauf (v2.0.19)
# Mahnlauf auf Knopfdruck: alle ueberfaelligen Rechnungen gesammelt, vorgeschlagene Mahnstufe,
# Haken je Zeile, ein Knopf erstellt alle Mahnungen und verschickt sie per E-Mail (ohne Adresse:
# PDF / Sammel-PDF zum Drucken). Verzugszinsen nach par. 288 BGB (B2B 9, B2C 5 Prozentpunkte ueber
# Basiszinssatz) und Verzugspauschale 40 EUR (nur B2B, par. 288 Abs. 5 BGB), jeweils ab Stufe X.
# create_mahnung wird ersetzt: Mahnbetrag = Restbetrag (Teilzahlungen aus m71) + Gebuehr + Zinsen
# + Pauschale; der GiroCode auf der Mahnung enthaelt damit genau den offenen Gesamtbetrag.
# Protokoll aller Laeufe; optional taeglicher Vorschlag / automatischer Versand (Standard aus).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M72_VERSION = "1.0.0"
# Basiszinssatz par. 247 BGB (Deutsche Bundesbank), changes on 1.1. / 1.7. - interest is computed per half-year
M72_BASIS_TAB = [("2023-01-01", 1.62), ("2023-07-01", 3.12), ("2024-01-01", 3.62), ("2024-07-01", 3.37),
                 ("2025-01-01", 2.27), ("2025-07-01", 1.27), ("2026-01-01", 1.27), ("2026-07-01", 1.52)]
M72_DEFAULTS = {"m72_basis": 1.52, "m72_basis_datum": "2026-07-01", "m72_zinsen_ab": 1, "m72_pauschale_ab": 1,
                "m72_erste": 3, "m72_abstand": 2, "m72_auto_vorschlag": True, "m72_auto_senden": False,
                "m72_mail_betreff": "[Dokument] [Nummer]",
                "m72_mail_text": "Guten Tag [Name],\n\nanbei erhalten Sie unsere [Dokument] zur Rechnung [Nummer]. "
                                 "Offener Gesamtbetrag: [Offen], zahlbar bis [Mahnfrist].\n\n"
                                 "Sollten Sie die Zahlung bereits veranlasst haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.\n\n"
                                 "Mit freundlichen Grüßen\n[Inhaber]"}
M72_STUFEN = ["Zahlungserinnerung", "1. Mahnung", "2. Mahnung", "Letzte Mahnung"]


def _m72_schema():
    x("CREATE TABLE IF NOT EXISTS m72_kunde (customer_id INTEGER PRIMARY KEY, b2b INTEGER)")
    x("CREATE TABLE IF NOT EXISTS m72_extra (mahnung_id INTEGER PRIMARY KEY, rest REAL, zinsen REAL, zins_satz REAL, zins_tage INTEGER, "
      "pauschale REAL, gesamt REAL)")
    x("CREATE TABLE IF NOT EXISTS m72_lauf (id INTEGER PRIMARY KEY, zeit TEXT, art TEXT, anzahl INTEGER, gesendet INTEGER, "
      "gedruckt INTEGER, fehler INTEGER, details TEXT)")


HOOK_SCHEMA.append(_m72_schema)


def m72_cfg(s=None):
    s = s or get_settings()
    c = {k: s.get(k, v) for k, v in M72_DEFAULTS.items()}
    for k in ("m72_basis",):
        try:
            c[k] = float(c[k])
        except Exception:
            c[k] = M72_DEFAULTS[k]
    for k in ("m72_zinsen_ab", "m72_pauschale_ab", "m72_erste", "m72_abstand"):
        try:
            c[k] = int(c[k])
        except Exception:
            c[k] = M72_DEFAULTS[k]
    # a stored rate older than the built-in table is outdated -> show / use the current one
    if not d_iso(str(c.get("m72_basis_datum") or "")) or str(c["m72_basis_datum"])[:10] < M72_BASIS_TAB[-1][0]:
        c["m72_basis_datum"], c["m72_basis"] = M72_BASIS_TAB[-1]
    return c


def m72_b2b(customer_id, cust=None):
    if customer_id:
        o = q("SELECT b2b FROM m72_kunde WHERE customer_id=?", (customer_id,), one=True)
        if o and o["b2b"] is not None:
            return bool(o["b2b"]), True
        c = cust or q("SELECT firma FROM customers WHERE id=?", (customer_id,), one=True)
        return bool(c and (c.get("firma") or "").strip()), False
    return False, False


def m72_basis_tab(cfg=None):
    """[(from_iso, rate)] sorted; the user's entry counts from its date on when it is not older than the built-in table"""
    cfg = cfg or m72_cfg()
    tab = list(M72_BASIS_TAB)
    bd = str(cfg.get("m72_basis_datum") or "")[:10]
    if d_iso(bd) and bd >= tab[-1][0]:
        tab = [r for r in tab if r[0] < bd] + [(bd, float(cfg["m72_basis"]))]
    return tab


def m72_zins_segmente(rest, pp, due, ref, cfg=None):
    """interest par. 288 BGB from the day after 'due' up to 'ref' (incl.), rate = Basiszinssatz of each half-year + pp,
    days/365 -> [(von, bis, tage, satz, zinsen)]"""
    tab = m72_basis_tab(cfg)
    out = []
    d = due + datetime.timedelta(days=1)
    while d <= ref:
        rate = tab[0][1]
        nxt = None
        for k, (iso, r_) in enumerate(tab):
            if iso <= d.isoformat():
                rate = r_
                nxt = tab[k + 1][0] if k + 1 < len(tab) else None
        end = ref
        if nxt:
            end = min(ref, d_iso(nxt) - datetime.timedelta(days=1))
        days = (end - d).days + 1
        satz = round(rate + pp, 2)
        out.append((d.isoformat(), end.isoformat(), days, satz, rest * satz / 100.0 * days / 365.0))
        d = end + datetime.timedelta(days=1)
    return out


def m72_calc(inv, stufe, cfg=None, ref=None):
    """amounts of a dunning letter for stage index 0..3"""
    cfg = cfg or m72_cfg()
    ref = ref or datetime.date.today()
    s = get_settings()
    try:
        st = m71_state(inv)
        rest, gez = st["rest"], round(st["gezahlt"] + st["skonto"] + st["ausgebucht"], 2)
    except Exception:
        rest, gez = round(float(inv.get("summe") or 0), 2), 0.0
    gebs = s.get("mahn_gebuehr") or [0, 0, 0, 0]
    geb = float(gebs[stufe]) if stufe < len(gebs) else 0.0
    b2b, _ = m72_b2b(inv.get("customer_id"))
    d0 = d_iso(inv.get("datum")) or ref
    due = d0 + datetime.timedelta(days=_frist(inv.get("frist")))
    tage = max(0, (ref - due).days)
    zinsen = satz = 0.0
    seg = []
    if cfg["m72_zinsen_ab"] >= 0 and stufe >= cfg["m72_zinsen_ab"] and tage > 0 and rest > 0:
        seg = m72_zins_segmente(rest, 9.0 if b2b else 5.0, due, ref, cfg)
        satz = seg[-1][3] if seg else 0.0
        zinsen = round(sum(s_[4] for s_ in seg), 2)
    pausch = 40.0 if (b2b and cfg["m72_pauschale_ab"] >= 0 and stufe >= cfg["m72_pauschale_ab"] and rest > 0) else 0.0
    return {"rest": rest, "gezahlt": gez, "gebuehr": geb, "zinsen": zinsen, "zins_satz": satz, "zins_tage": tage,
            "pauschale": pausch, "b2b": b2b, "faellig": due.isoformat(), "zins_segmente": seg,
            "gesamt": round(rest + geb + zinsen + pausch, 2)}


def create_mahnung(iid, stufe=None, zinsen=True, pauschale=True):
    inv = get_invoice(iid)
    if not inv or inv["typ"] != "rechnung" or inv["status"] != "offen":
        raise ValueError("Mahnungen sind nur für offene Rechnungen möglich.")
    s = get_settings()
    stufe = min(int(inv.get("mahnstufe") or 0), 3) if stufe in (None, "") else max(0, min(int(stufe), 3))
    cfg = m72_cfg(s)
    if not zinsen:
        cfg["m72_zinsen_ab"] = -1
    if not pauschale:
        cfg["m72_pauschale_ab"] = -1
    c = m72_calc(inv, stufe, cfg)
    if c["rest"] <= 0.005:
        raise ValueError(f"Rechnung {inv['nr']} hat keinen offenen Betrag mehr.")
    texts = s.get("mahn_text") or DEFAULT_SETTINGS["mahn_text"]
    frist_bis = (datetime.date.today() + datetime.timedelta(days=int(s.get("mahn_frist") or 7))).isoformat()
    items = [{"qty": 1, "nr": "", "name": f"Rechnung {inv['nr']} vom {de_date(inv['datum'])}",
              "descr": f"fällig seit {de_date(c['faellig'])}", "price": inv["summe"], "rabatt": 0}]
    if c["gezahlt"] > 0.005:
        zs = []
        try:
            zs = [z for z in m71_rows(inv["id"]) if z["art"] in ("zahlung", "teil")]
        except Exception:
            pass
        items.append({"qty": 1, "nr": "", "name": "abzüglich bereits erhaltener Zahlungen",
                      "descr": ", ".join(f"{de_date(z['datum'])}: {money(z['betrag'])}" for z in zs[:4]), "price": -c["gezahlt"], "rabatt": 0,
                      "_m72kind": "zahlungen", "_m72data": [(z["datum"], z["betrag"]) for z in zs[:4]]})
    if c["gebuehr"]:
        items.append({"qty": 1, "nr": "", "name": "Mahngebühr", "descr": "", "price": c["gebuehr"], "rabatt": 0})
    if c["zinsen"]:
        pp = 9 if c["b2b"] else 5
        seg = c.get("zins_segmente") or []
        if len(seg) > 1:
            descr = (f"Basiszinssatz + {pp} Prozentpunkte auf {money(c['rest'])}: " +
                     "; ".join(f"{de_date(s_[0])}–{de_date(s_[1])}: {s_[2]} Tage zu {nde_py(s_[3])} %" for s_ in seg))
        else:
            descr = (f"{nde_py(c['zins_satz'])} % p. a. ({nde_py(round(c['zins_satz'] - pp, 2))} % Basiszinssatz + {pp} Prozentpunkte) "
                     f"für {c['zins_tage']} Tage auf {money(c['rest'])}")
        items.append({"qty": 1, "nr": "", "name": "Verzugszinsen (§ 288 BGB)", "descr": descr, "price": c["zinsen"], "rabatt": 0,
                      "_m72kind": "zinsen", "_m72data": {"pp": pp, "rest": c["rest"], "seg": seg, "satz": c["zins_satz"], "tage": c["zins_tage"]}})
    if c["pauschale"]:
        items.append({"qty": 1, "nr": "", "name": "Verzugspauschale (§ 288 Abs. 5 BGB)", "descr": "", "price": c["pauschale"], "rabatt": 0,
                      "_m72kind": "pauschale"})
    pseudo = dict(inv)
    pseudo.update(id=None, titel=M72_STUFEN[stufe], _doctitle=M72_STUFEN[stufe], _nrlabel="Rechnung Nr.", _nrvalue=inv["nr"],
                  _meta=[("Datum", de_date(today())), ("Rechnungsdatum", de_date(inv["datum"])), ("Kunden-Nr.", inv["kdnr"])],
                  toptext="Guten Tag,\n\n" + texts[min(stufe, len(texts) - 1)], _mahnfrist=frist_bis, items=items,
                  attachments=[], _paybox=True,
                  foottext="Sollten Sie die Zahlung bereits veranlasst haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.\n" + s["default_foot"])
    pdf = render_invoice_pdf(pseudo, s, attachments=False)
    folder = os.path.dirname(invoice_pdf_path(inv, s))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"mahnung_{re.sub(r'[^0-9A-Za-z]', '', inv['nr'])}_{stufe + 1}.pdf")
    write_file(path, pdf)
    rel = os.path.relpath(path, DATA_DIR) if path.startswith(DATA_DIR) else path
    total = round(sum(line_total(it) for it in items), 2)
    mid = x("INSERT INTO mahnungen (invoice_id, stufe, datum, frist_bis, gebuehr, betrag, file, created) VALUES (?,?,?,?,?,?,?,?)",
            (iid, stufe, today(), frist_bis, c["gebuehr"], total, rel, now_iso()))
    x("INSERT OR REPLACE INTO m72_extra (mahnung_id, rest, zinsen, zins_satz, zins_tage, pauschale, gesamt) VALUES (?,?,?,?,?,?,?)",
      (mid, c["rest"], c["zinsen"], c["zins_satz"], c["zins_tage"], c["pauschale"], total))
    x("UPDATE invoices SET mahnstufe=? WHERE id=?", (stufe + 1, iid))
    lock_invoice(iid)
    return {"ok": True, "id": mid, "path": path, "titel": M72_STUFEN[stufe], "betrag": total}


def m72_vorschlag(ref=None):
    cfg = m72_cfg()
    t0 = ref or datetime.date.today()
    out = []
    for r in overdue_list():
        inv = q("SELECT * FROM invoices WHERE id=?", (r["id"],), one=True)
        if not inv:
            continue
        ms = q("SELECT * FROM mahnungen WHERE invoice_id=? ORDER BY id DESC", (inv["id"],))
        last = ms[0] if ms else None
        ms_n = int(inv["mahnstufe"] or 0)
        stufe = min(ms_n, 3)
        hinweis = ""
        if ms_n >= 4:
            faellig = False
            hinweis = "Letzte Mahnung ist verschickt – gerichtliches Mahnverfahren oder Inkasso prüfen."
        elif not last:
            faellig = r["tage"] >= cfg["m72_erste"]
            if not faellig:
                hinweis = f"erst {r['tage']} Tag(e) überfällig (Mahnlauf ab {cfg['m72_erste']} Tagen)"
        else:
            fb = d_iso(last["frist_bis"]) or t0
            nxt = fb + datetime.timedelta(days=cfg["m72_abstand"])
            faellig = t0 >= nxt
            if not faellig:
                hinweis = f"Frist der {M72_STUFEN[min(last['stufe'], 3)]} läuft bis {de_date(last['frist_bis'])} – nächste Stufe ab {de_date(nxt.isoformat())}"
        c = m72_calc(inv, stufe, cfg, t0)
        if c["rest"] <= 0.005:
            continue
        cu = q("SELECT * FROM customers WHERE id=?", (inv["customer_id"],), one=True) if inv["customer_id"] else None
        b2b, manual = m72_b2b(inv["customer_id"], cu)
        out.append({"id": inv["id"], "nr": inv["nr"], "name": inv_name(inv), "customer_id": inv["customer_id"], "datum": inv["datum"],
                    "faellig": r["faellig"], "tage": r["tage"], "stufe": stufe, "stufe_de": M72_STUFEN[stufe], "mahnungen": len(ms),
                    "letzte": last["datum"] if last else "", "letzte_frist": last["frist_bis"] if last else "", "vorgeschlagen": bool(faellig),
                    "hinweis": hinweis, "mail": (cu["mail"] if cu else "") or "", "b2b": b2b, "b2b_manuell": manual, **{k: c[k] for k in (
                        "rest", "gezahlt", "gebuehr", "zinsen", "zins_satz", "zins_tage", "pauschale", "gesamt")}, "summe": inv["summe"]})
    return out


def _m72_mail_fill(text, inv, titel, total, frist_bis):
    s = get_settings()
    cu = q("SELECT * FROM customers WHERE id=?", (inv.get("customer_id"),), one=True) if inv.get("customer_id") else None
    return (text or "").replace("[Dokument]", titel).replace("[Nummer]", inv.get("nr") or "").replace("[Offen]", money(total)) \
        .replace("[Betrag]", money(inv.get("summe") or 0)).replace("[Mahnfrist]", de_date(frist_bis)) \
        .replace("[Name]", ((cu["name"] or cu["firma"]) if cu else "") or "").replace("[Inhaber]", s.get("inhaber") or "") \
        .replace("[Firma]", s.get("firma") or "").replace("\\n", "\n")


M72_LOCK = threading.RLock()
M72_DOPPELT_SEK = 120


def m72_run(items, art="manuell", sammel_pdf=True):
    """items: [{id, stufe, senden(bool), zinsen(bool), pauschale(bool)}]"""
    # v2.1.0: one run at a time - a double click (or the automatic run at the same moment) created the same
    # reminder two or three times and could send it twice
    with M72_LOCK:
        return _m72_run(items, art, sammel_pdf)


def _m72_recent(iid):
    """a reminder for this invoice created in the last M72_DOPPELT_SEK seconds (same click / parallel run)"""
    lim = (datetime.datetime.now() - datetime.timedelta(seconds=M72_DOPPELT_SEK)).strftime("%Y-%m-%d %H:%M:%S")
    return q("SELECT id FROM mahnungen WHERE invoice_id=? AND COALESCE(created,'')>=? LIMIT 1", (iid, lim), one=True)


def _m72_run(items, art="manuell", sammel_pdf=True):
    cfg = m72_cfg()
    conf = False
    try:
        conf = mail_configured()
    except Exception:
        s_ = get_settings()
        conf = bool(s_.get("smtp_host") and s_.get("smtp_user") and s_.get("smtp_pass"))
    res, pdfs = [], []
    for it in items or []:
        row = {"id": it.get("id"), "ok": False}
        try:
            inv = get_invoice(int(it["id"]))
            row["nr"] = inv["nr"] if inv else ""
            if inv and _m72_recent(inv["id"]):
                raise ValueError("Zu dieser Rechnung wurde eben schon eine Mahnung erstellt (doppelter Klick?).")
            m = create_mahnung(int(it["id"]), it.get("stufe"), it.get("zinsen", True), it.get("pauschale", True))
            row.update(ok=True, mahnung_id=m["id"], titel=m["titel"], betrag=m["betrag"], path=m["path"])
            cu = q("SELECT mail FROM customers WHERE id=?", (inv["customer_id"],), one=True) if inv.get("customer_id") else None
            to = ((it.get("mail") or "") or (cu["mail"] if cu else "") or "").strip()
            if it.get("senden", True) and to and "@" in to and conf:
                mm = q("SELECT * FROM mahnungen WHERE id=?", (m["id"],), one=True)
                try:
                    mail_send({"mahnung_id": m["id"], "to": to, "cc": "",
                               "subject": _m72_mail_fill(cfg["m72_mail_betreff"], inv, m["titel"], m["betrag"], mm["frist_bis"]),
                               "body": _m72_mail_fill(cfg["m72_mail_text"], inv, m["titel"], m["betrag"], mm["frist_bis"])})
                    row["gesendet"] = to
                except ValueError as e:
                    row["fehler"] = str(e)
                    pdfs.append(m["path"])
            else:
                row["drucken"] = True
                if it.get("senden", True) and not to:
                    row["hinweis"] = "keine E-Mail-Adresse – zum Drucken"
                elif it.get("senden", True) and not conf:
                    row["hinweis"] = "E-Mail nicht eingerichtet – zum Drucken"
                pdfs.append(m["path"])
        except Exception as e:
            row["fehler"] = str(e)
        res.append(row)
    sammel = ""
    if pdfs and sammel_pdf:
        try:
            import pypdf
            w = pypdf.PdfWriter()
            for p in pdfs:
                for pg in pypdf.PdfReader(p).pages:
                    w.add_page(pg)
            folder = os.path.join(DATA_DIR, "Mahnlauf")
            os.makedirs(folder, exist_ok=True)
            sammel = os.path.join(folder, f"Mahnlauf_{today()}_{time.strftime('%H%M%S')}.pdf")
            with open(sammel, "wb") as f:
                w.write(f)
        except Exception:
            traceback.print_exc()
            sammel = ""
    n_ok = sum(1 for r in res if r["ok"])
    n_mail = sum(1 for r in res if r.get("gesendet"))
    n_err = sum(1 for r in res if r.get("fehler"))
    x("INSERT INTO m72_lauf (zeit, art, anzahl, gesendet, gedruckt, fehler, details) VALUES (?,?,?,?,?,?,?)",
      (now_iso(), art, n_ok, n_mail, len(pdfs), n_err, json.dumps({"zeilen": res, "sammel": sammel}, ensure_ascii=False, default=str)))
    return {"ok": True, "zeilen": res, "erstellt": n_ok, "gesendet": n_mail, "drucken": [r.get("mahnung_id") for r in res if r.get("drucken")],
            "fehler": n_err, "sammel_pdf": sammel}


def m72_loop():
    time.sleep(90)
    while True:
        try:
            cfg = m72_cfg()
            st = get_settings().get("m72_heute") or {}
            if st.get("datum") != today() and (cfg["m72_auto_vorschlag"] or cfg["m72_auto_senden"]):
                v = m72_vorschlag()
                due = [r for r in v if r["vorgeschlagen"]]
                info = {"datum": today(), "n": len(due), "summe": round(sum(r["gesamt"] for r in due), 2)}
                if cfg["m72_auto_senden"]:
                    send = [{"id": r["id"], "stufe": r["stufe"], "senden": True} for r in due if r["mail"]]
                    if send:
                        rr = m72_run(send, art="automatisch", sammel_pdf=False)
                        info["gesendet"] = rr["gesendet"]
                set_setting("m72_heute", info)
        except Exception:
            traceback.print_exc()
        time.sleep(3600)


HOOK_START.append(m72_loop)


def _m72_list_route(h, qs):
    v = m72_vorschlag()
    return h._send(200, {"ok": True, "zeilen": v, "cfg": m72_cfg(), "stufen": M72_STUFEN,
                         "gebuehr": get_settings().get("mahn_gebuehr") or [0, 0, 0, 0],
                         "laeufe": q("SELECT id, zeit, art, anzahl, gesendet, gedruckt, fehler FROM m72_lauf ORDER BY id DESC LIMIT 50")})


def _m72_run_route(h, d):
    r = m72_run(d.get("items") or [], art="manuell", sammel_pdf=bool(d.get("sammel", True)))
    if r.get("sammel_pdf") and d.get("oeffnen", True):
        open_path(r["sammel_pdf"])
    return h._send(200, r)


def _m72_cfg_route(h, d):
    for k, v in M72_DEFAULTS.items():
        if k in d:
            val = d[k]
            if isinstance(v, bool):
                val = bool(val)
            elif isinstance(v, float):
                val = float(str(val).replace(",", ".") or 0)
            elif isinstance(v, int):
                val = int(float(str(val).replace(",", ".") or 0))
            set_setting(k, val)
    return h._send(200, {"ok": True, "cfg": m72_cfg()})


def _m72_b2b_route(h, d):
    cid = int(d["customer_id"])
    v = d.get("b2b")
    x("INSERT OR REPLACE INTO m72_kunde (customer_id, b2b) VALUES (?,?)", (cid, None if v is None else (1 if v else 0)))
    return h._send(200, {"ok": True})


def _m72_lauf_route(h, qs):
    r = q("SELECT * FROM m72_lauf WHERE id=?", (int(qs.get("id") or 0),), one=True)
    if r:
        r["details"] = json.loads(r["details"] or "{}")
    return h._send(200, {"ok": bool(r), "lauf": r})


HOOK_GET["/api/m72/list"] = _m72_list_route
HOOK_GET["/api/m72/lauf"] = _m72_lauf_route
HOOK_POST["/api/m72/run"] = _m72_run_route
HOOK_POST["/api/m72/cfg"] = _m72_cfg_route
HOOK_POST["/api/m72/b2b"] = _m72_b2b_route
def _m72_open(h, d):
    # v2.0.19: only files inside the data folder - path normalized, ".." cannot leave it
    try:
        p_ = os.path.realpath(d.get("path") or "")
        root_ = os.path.realpath(DATA_DIR)
        ok_ = os.path.commonpath([p_, root_]) == root_ and os.path.isfile(p_)
    except Exception:
        ok_ = False
    return h._send(200, {"ok": open_path(p_) if ok_ else False})


HOOK_POST["/api/m72/open"] = _m72_open


def _m72_boot(d):
    st = get_settings().get("m72_heute") or {}
    d["m72"] = {"heute": st if st.get("datum") == today() else {}}


HOOK_BOOT.append(_m72_boot)


def _m72_ex(p):
    v = m72_vorschlag()
    return [_sh("Mahnlauf – überfällige Rechnungen", [("Nr.", "t", 14), ("Kunde", "t", 28), ("Fällig", "d", 11), ("Tage", "n", 7),
                                                     ("Stufe", "t", 18), ("Rest", "m", 12), ("Gebühr", "m", 10), ("Zinsen", "m", 10),
                                                     ("Pauschale", "m", 10), ("Gesamt", "m", 12), ("B2B", "t", 6), ("E-Mail", "t", 26)],
                [[r["nr"], r["name"], r["faellig"], r["tage"], r["stufe_de"], r["rest"], r["gebuehr"], r["zinsen"], r["pauschale"],
                  r["gesamt"], "ja" if r["b2b"] else "", r["mail"]] for r in v], f"Stand {de_date(today())}")]


EXPORTS["m72_mahnlauf"] = ("Mahnlauf", _m72_ex)


def _m72_selftest():
    err = []
    try:
        cfg = dict(m72_cfg(), m72_basis=1.52, m72_zinsen_ab=0, m72_pauschale_ab=0)
        inv = {"id": None, "summe": 1000.0, "datum": (datetime.date.today() - datetime.timedelta(days=45)).isoformat(), "frist": 10,
               "customer_id": None, "status": "offen", "typ": "rechnung"}
        c = m72_calc(inv, 1, cfg)
        exp = round(1000 * 6.52 / 100 * 35 / 365, 2)    # B2C without customer: 5 Pp.
        if abs(c["zinsen"] - exp) > 0.011 or c["pauschale"] != 0:
            err.append(f"m72: Verzugszinsen B2C {c['zinsen']} statt {exp}")
        if c["zins_tage"] != 35:
            err.append(f"m72: Verzugstage {c['zins_tage']} statt 35")
        # Basiszinssatz change on 1.7.2026 (1,27 -> 1,52): 10 days each, B2B (+9 Pp.)
        seg = m72_zins_segmente(1000.0, 9.0, datetime.date(2026, 6, 20), datetime.date(2026, 7, 10), dict(M72_DEFAULTS))
        z = round(sum(s_[4] for s_ in seg), 2)
        if len(seg) != 2 or abs(z - round(1000 * (10.27 * 10 + 10.52 * 10) / 100 / 365, 2)) > 0.001:
            err.append(f"m72: Zinsen über Basiszins-Wechsel falsch ({z}, {seg})")
    except Exception as e:
        err.append(f"m72 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m72_selftest)
