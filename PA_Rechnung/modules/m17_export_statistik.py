# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m17_export_statistik
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ---------------- v1.6.1: export everything as Excel / PDF ----------------
# A sheet: {"title", "sub", "cols": [(label, kind, width)], "rows": [[...]], "sum": bool}
# kind: t=text, d=date (iso), m=money, n=number, p=percent
TYP_DE = {"rechnung": "Rechnung", "storno": "Storno", "angebot": "Angebot", "auftrag": "Auftragsbestätigung"}
BTYP_DE = {"ausgabe": "Eingangsrechnung / Ausgabe", "gehalt": "Gehalt / Lohn", "einnahme": "Sonstige Einnahme", "anlage": "Anlage zu Rechnung",
           "eigene_rechnung": "Ausgangsrechnung"}


def _sh(title, cols, rows, sub="", total=True):
    return {"title": title, "sub": sub, "cols": cols, "rows": rows, "sum": total and any(c[1] == "m" for c in cols) and len(rows) > 1}


def _kv(title, pairs, sub=""):
    return dict(_sh(title, [("Feld", "t", 30), ("Wert", "t", 60)], [[k, v] for k, v in pairs], sub, False), kv=True)


def _ids(p):
    return {int(i) for i in (p.get("ids") or []) if str(i).strip().lstrip("-").isdigit()}


def _cname(c):
    return (c.get("firma") or c.get("name") or "") if c else ""


def _proj_names():
    return {p["id"]: f"{p['nr']} {p['name']}" for p in q("SELECT id, nr, name FROM projects")}


def ex_invoices(p):
    ids = _ids(p)
    tab, year, status, qq = p.get("tab") or "", str(p.get("year") or ""), p.get("status") or "", (p.get("q") or "").lower()
    pn = _proj_names()
    rows = []
    for r in q("SELECT * FROM invoices ORDER BY datum, nr"):
        if ids:
            if r["id"] not in ids:
                continue
        else:
            if tab == "draft" and r["status"] != "entwurf":
                continue
            if tab == "rechnung" and not (r["typ"] in ("rechnung", "storno") and r["status"] != "entwurf"):
                continue
            if tab in ("angebot", "auftrag") and r["typ"] != tab:
                continue
            if year and tab != "draft" and not (r["datum"] or "").startswith(year):
                continue
            if status and r["status"] != status:
                continue
            if qq and qq not in f"{r['nr']} {r['addr']} {r['titel']}".lower():
                continue
        rows.append([r["nr"] if r["status"] != "entwurf" else "Entwurf", TYP_DE.get(r["typ"], r["typ"]), r["datum"], inv_name(r), r["kdnr"] or "",
                     r["titel"] or "", r["status"] or "", r["bezahlt_am"] or "", pn.get(r["project_id"], ""), r["summe"] or 0.0])
    sub = " · ".join(x for x in ({"rechnung": "Rechnungen", "draft": "Entwürfe", "angebot": "Angebote", "auftrag": "Auftragsbestätigungen"}.get(tab, ""),
                                  year, status, f"Suche „{p.get('q')}“" if qq else "", "Auswahl" if ids else "") if x)
    return [_sh("Rechnungen", [("Nr.", "t", 12), ("Art", "t", 14), ("Datum", "d", 11), ("Kunde", "t", 30), ("Kd-Nr.", "t", 9), ("Titel", "t", 26),
                               ("Status", "t", 11), ("Bezahlt am", "d", 11), ("Projekt", "t", 22), ("Betrag", "m", 13)], rows, sub,
                total=(tab == "rechnung" and not status) or tab in ("angebot", "auftrag"))]   # v2.0.6: no total over mixed document types


def ex_invoice(p):
    inv = get_invoice(int(p["id"]))
    if not inv:
        raise ValueError("Rechnung nicht gefunden.")
    pairs = [("Nummer", inv["nr"] or "Entwurf"), ("Art", TYP_DE.get(inv["typ"], inv["typ"])), ("Datum", de_date(inv["datum"])),
             ("Leistungsdatum", de_date(inv["liefer"]) if inv.get("liefer") else ""), ("Kunde", inv_name(dict(inv, addr=json.dumps(inv["addr"])))),
             ("Kd-Nr.", inv["kdnr"] or ""), ("Anschrift", " / ".join(a for a in inv["addr"] if a)), ("Titel", inv["titel"] or ""),
             ("Status", inv["status"] or ""), ("Bezahlt am", de_date(inv["bezahlt_am"]) if inv.get("bezahlt_am") else ""),
             ("Zahlungsziel", f"{inv.get('frist') or ''} Tage"), ("Summe", _m(inv["summe"] or 0))]
    rows = [[it["pos"], it["nr"] or "", it["name"] or "", it["descr"] or "", it["qty"] or 0, it["price"] or 0, it["rabatt"] or 0, it["total"] or 0]
            for it in inv["items"]]
    out = [_kv(f"Rechnung {inv['nr'] or 'Entwurf'}", pairs),
           _sh("Positionen", [("Pos.", "n", 6), ("Art.-Nr.", "t", 10), ("Bezeichnung", "t", 30), ("Beschreibung", "t", 40), ("Menge", "n", 8),
                              ("Einzelpreis", "m", 12), ("Rabatt %", "n", 9), ("Gesamt", "m", 13)], rows)]
    if inv["mahnungen"]:
        out.append(_sh("Mahnungen", [("Stufe", "n", 8), ("Datum", "d", 11), ("Frist bis", "d", 11), ("Gebühr", "m", 11), ("Betrag", "m", 13)],
                       [[m_["stufe"], m_["datum"], m_["frist_bis"], m_["gebuehr"] or 0, m_["betrag"] or 0] for m_ in inv["mahnungen"]]))
    return out


def ex_customers(p):
    ids = _ids(p)
    agg = {r["customer_id"]: r for r in q(f"SELECT customer_id, COUNT(*) n, COALESCE(SUM(summe),0) s, MAX(datum) l FROM invoices WHERE {COUNT_SQL} GROUP BY customer_id")}
    rows = []
    for c in q("SELECT * FROM customers ORDER BY kdnr"):
        if ids and c["id"] not in ids:
            continue
        a = agg.get(c["id"]) or {}
        rows.append([c["kdnr"], c["anrede"] or "", c["firma"] or "", c["name"] or "", c["strasse"] or "", c["plz"] or "", c["ort"] or "", c["land"] or "",
                     c["tel"] or "", c["mobil"] or "", c["mail"] or "", c["web"] or "", c["gruppe"] or "", c["notiz"] or "",
                     a.get("n", 0), a.get("l") or "", a.get("s", 0.0)])
    return [_sh("Kunden", [("Kd-Nr.", "t", 9), ("Anrede", "t", 8), ("Firma", "t", 24), ("Name", "t", 20), ("Straße", "t", 22), ("PLZ", "t", 7), ("Ort", "t", 16),
                           ("Land", "t", 8), ("Telefon", "t", 15), ("Mobil", "t", 15), ("E-Mail", "t", 24), ("Web", "t", 18), ("Gruppe", "t", 12),
                           ("Notiz", "t", 24), ("Rechnungen", "n", 10), ("Letzte Rechnung", "d", 12), ("Umsatz gesamt", "m", 14)], rows,
                "Auswahl" if ids else f"{len(rows)} Kunden")]


def ex_customer(p):
    c = q("SELECT * FROM customers WHERE id=?", (int(p["id"]),), one=True)
    if not c:
        raise ValueError("Kunde nicht gefunden.")
    pairs = [("Kundennummer", c["kdnr"]), ("Firma", c["firma"] or ""), ("Name", c["name"] or ""), ("Anschrift", f"{c['strasse'] or ''}, {c['plz'] or ''} {c['ort'] or ''}".strip(", ")),
             ("Telefon", c["tel"] or ""), ("Mobil", c["mobil"] or ""), ("E-Mail", c["mail"] or ""), ("Web", c["web"] or ""), ("Gruppe", c["gruppe"] or ""),
             ("Notiz", c["notiz"] or "")]
    invs = q("SELECT * FROM invoices WHERE customer_id=? ORDER BY datum", (c["id"],))
    by = {}
    for r in invs:
        if r["typ"] in ("rechnung", "storno") and r["status"] not in ("entwurf", "storniert"):
            yk = (r["datum"] or "")[:4] or "ohne Datum"
            by[yk] = by.get(yk, 0) + (r["summe"] or 0)
    pairs.append(("Umsatz gesamt", _m(round(sum(by.values()), 2))))
    out = [_kv(f"Kunde {c['kdnr']} {_cname(c)}", pairs),
           _sh("Rechnungen", [("Nr.", "t", 12), ("Art", "t", 14), ("Datum", "d", 11), ("Titel", "t", 30), ("Status", "t", 11), ("Bezahlt am", "d", 11), ("Betrag", "m", 13)],
               [[r["nr"] or "Entwurf", TYP_DE.get(r["typ"], r["typ"]), r["datum"], r["titel"] or "", r["status"], r["bezahlt_am"] or "", r["summe"] or 0] for r in invs]),
           _sh("Umsatz je Jahr", [("Jahr", "t", 8), ("Umsatz", "m", 14)], [[y, round(v, 2)] for y, v in sorted(by.items())])]
    pr = q("SELECT * FROM projects WHERE customer_id=? ORDER BY start", (c["id"],))
    if pr:
        out.append(_sh("Projekte", [("Nr.", "t", 10), ("Name", "t", 30), ("Bereich", "t", 14), ("Status", "t", 12), ("Start", "d", 11)],
                       [[x_["nr"], x_["name"], x_["bereich"] or "", x_["status"] or "", x_["start"] or ""] for x_ in pr], total=False))
    return out


def ex_articles(p):
    ids = _ids(p)
    rows = [[a["nr"] or "", a["name"] or "", a["descr"] or "", a["cat"] or "", a["unit"] or "", a["price"] or 0, "ja" if a["active"] else "nein"]
            for a in q("SELECT * FROM articles ORDER BY cat, sort, nr") if not ids or a["id"] in ids]
    return [_sh("Bausteine", [("Art.-Nr.", "t", 10), ("Bezeichnung", "t", 28), ("Beschreibung", "t", 44), ("Kategorie", "t", 16), ("Einheit", "t", 9),
                              ("Preis", "m", 12), ("Aktiv", "t", 7)], rows, "", False)]


def ex_belege(p):
    ids = _ids(p)
    year, typ = str(p.get("year") or ""), p.get("typ") or ""
    pn = _proj_names()
    rows = []
    for b in q("SELECT * FROM belege ORDER BY datum, id"):
        if ids:
            if b["id"] not in ids:
                continue
        elif (year and not (b["datum"] or "").startswith(year)) or (typ and b["typ"] != typ):
            continue
        rows.append([b["datum"], BTYP_DE.get(b["typ"], b["typ"]), b["partner"] or "", b["nr"] or "", b["kategorie"] or "", pn.get(b["project_id"], ""),
                     b["notiz"] or "", os.path.basename(b["file"] or ""), b["betrag"] or 0])
    return [_sh("Belege", [("Datum", "d", 11), ("Art", "t", 22), ("Partner", "t", 26), ("Beleg-Nr.", "t", 14), ("Kategorie", "t", 26), ("Projekt", "t", 18),
                           ("Notiz", "t", 22), ("Datei", "t", 26), ("Betrag", "m", 13)], rows,
                "Auswahl" if ids else " · ".join(x for x in (year or "alle Jahre", BTYP_DE.get(typ, "")) if x))]


def ex_bank(p):
    ids = _ids(p)
    year = str(p.get("year") or "")
    st_ = {"paid": "Rechnung bezahlt", "ausgabe": "Ausgabe", "einnahme": "Einnahme", "ignore": "ignoriert"}
    rows = [[t["datum"], t["name"] or "", t["zweck"] or "", t["iban"] or "", st_.get(t["status"], t["status"] or ""), t["betrag"] or 0]
            for t in q("SELECT * FROM bank_tx ORDER BY datum, id") if (t["id"] in ids if ids else (not year or (t["datum"] or "").startswith(year)))]
    out = [_sh("Bankbuchungen", [("Datum", "d", 11), ("Name", "t", 28), ("Verwendungszweck", "t", 50), ("IBAN", "t", 24), ("Status", "t", 16), ("Betrag", "m", 13)],
               rows, "Auswahl" if ids else (year or "alle Jahre"))]
    if not ids:
        ks = [[k["datum"], k["quelle"] or "", k["saldo"] or 0] for k in q("SELECT * FROM kontostand ORDER BY datum") if not year or k["datum"].startswith(year)]
        out.append(_sh("Kontostände", [("Datum", "d", 11), ("Quelle", "t", 40), ("Saldo", "m", 14)], ks, "", False))
    return out


def ex_assets(p):
    ids = _ids(p)
    year = int(p.get("year") or datetime.date.today().year)
    rows = [[a["bezeichnung"] or "", a["kategorie"] or "", a["seriennr"] or "", a["standort"] or "", a["kaufdatum"] or "", a["betrag"] or 0,
             "GWG sofort" if a["methode"] == "gwg" else f"linear {a['nd_jahre'] or 0:g} J.", a["afa"], a["restwert"], a["abgang"] or ""]
            for a in afa_year(year) if not ids or a["id"] in ids]
    return [_sh(f"Anlagen {year}", [("Bezeichnung", "t", 28), ("Kategorie", "t", 20), ("Seriennr.", "t", 16), ("Standort", "t", 14), ("Kauf", "d", 11),
                            ("Anschaffung", "m", 13), ("Methode", "t", 14), (f"AfA {year}", "m", 12), (f"Restwert 31.12.{year}", "m", 15), ("Abgang", "d", 11)],
                rows, str(year))]


def ex_fahrten(p):
    ids = _ids(p)
    year = str(p.get("year") or "")
    pn = _proj_names()
    km = float(get_settings().get("km_dienst") or 0.3)
    rows = []
    for r in q("SELECT * FROM fahrten ORDER BY datum"):
        if (ids and r["id"] not in ids) or (not ids and year and not (r["datum"] or "").startswith(year)):
            continue
        dienst = (r["art"] or "dienst") == "dienst"
        rows.append([r["datum"], "Dienstfahrt" if dienst else "zur Arbeit", r["ziel"] or "", r["zweck"] or "", pn.get(r["project_id"], ""), r["km"] or 0,
                     round((r["km"] or 0) * km, 2) if dienst else 0.0])
    return [_sh("Fahrten", [("Datum", "d", 11), ("Art", "t", 13), ("Ziel", "t", 28), ("Zweck", "t", 28), ("Projekt", "t", 20), ("km", "n", 8), ("Betrag", "m", 12)],
                rows, "Auswahl" if ids else (year or "alle Jahre"))]


def ex_zert(p):
    ids = _ids(p)
    rows = [[z["typ"] or "", z["bezeichnung"] or "", z["person"] or "", z["nummer"] or "", z["norm"] or "", z["ausgestellt"] or "", z["gueltig_bis"] or "",
             z["bestaetigt_am"] or "", "ja" if z["aktiv"] else "nein", z["notiz"] or ""]
            for z in q("SELECT * FROM zertifikate ORDER BY gueltig_bis") if not ids or z["id"] in ids]
    return [_sh("Nachweise", [("Typ", "t", 18), ("Bezeichnung", "t", 28), ("Person", "t", 16), ("Nummer", "t", 14), ("Norm", "t", 16), ("Ausgestellt", "d", 11),
                              ("Gültig bis", "d", 11), ("Bestätigt am", "d", 11), ("Aktiv", "t", 6), ("Notiz", "t", 24)], rows, "", False)]


def ex_steuerakte(p):
    ids = _ids(p)
    year = p.get("year")
    rows = [[a["year"], a["art"] or "", a["titel"] or "", a["datum"] or "", os.path.basename(a["file"] or ""), a["notiz"] or ""]
            for a in q("SELECT * FROM steuerakte ORDER BY year, art, datum") if (a["id"] in ids if ids else (not year or a["year"] == int(year)))]
    return [_sh("Steuerakte", [("Jahr", "n", 7), ("Art", "t", 24), ("Titel", "t", 36), ("Datum", "d", 11), ("Datei", "t", 30), ("Notiz", "t", 24)], rows, "", False)]


def ex_stats(p):
    year = int(p.get("year") or datetime.date.today().year)
    st = stats(year)
    mon, jp = euer_months(year, st)
    mrows = [[MONTHS_LONG[x["m"] - 1], x["anzahl"], x["umsatz"], x["zufluss"], x["ausgaben"]] for x in mon]
    if jp:
        mrows.append(["Jahresposten (AfA, Fahrten, Homeoffice)", 0, 0.0, 0.0, jp])
    out = [_sh(f"Monate {year}", [("Monat", "t", 14), ("Rechnungen", "n", 10), ("Umsatz", "m", 13), ("Zahlungseingang", "m", 15), ("Ausgaben", "m", 13)],
               mrows, f"Statistik {year} · Zahlungseingang und Ausgaben nach EÜR (Zuflussprinzip)"),
           _sh(f"Kunden {year}", [("Kunde", "t", 30), ("Kd-Nr.", "t", 9), ("Rechnungen", "n", 10), ("Umsatz", "m", 13), ("Anteil %", "p", 9)],
               [[c["name"], c["kdnr"] or "", c["anzahl"], c["summe"], c["anteil"]] for c in st["kunden"]]),
           _sh(f"Leistungen {year}", [("Art.-Nr.", "t", 10), ("Leistung", "t", 30), ("Positionen", "n", 10), ("Menge", "n", 10), ("Umsatz", "m", 13), ("Anteil %", "p", 9)],
               [[x["nr"] or "", x["name"] or "", x["anzahl"], x["menge"], x["summe"], x["anteil"]] for x in st["leistungen"]])]
    if st["projekte"]:
        out.append(_sh(f"Projekte {year}", [("Nr.", "t", 10), ("Projekt", "t", 30), ("Bereich", "t", 14), ("Rechnungen", "n", 10), ("Umsatz", "m", 13)],
                       [[x["nr"], x["name"], x["bereich"] or "", x["anzahl"], x["summe"]] for x in st["projekte"]]))
    out.append(_sh("Jahresvergleich", [("Jahr", "t", 8), ("Umsatz", "m", 13), ("Einnahmen", "m", 13), ("Ausgaben", "m", 13), ("Gewinn", "m", 13)],
                   [[str(y["year"]), y["umsatz"], y["einnahmen"], y["ausgaben"], y["gewinn"]] for y in st["jahre"]], "", False))
    return out


def ex_euer(p):
    year = int(p.get("year") or datetime.date.today().year)
    e = euer(year)
    rows = [["Betriebseinnahmen aus Rechnungen", e["einnahmen_rechnungen"]], ["Sonstige Betriebseinnahmen", e["einnahmen_sonstige"]],
            ["Summe Betriebseinnahmen", e["einnahmen"]]]
    rows += [[f"   {k}", -v] for k, v in e["kategorien"].items()]
    rows += [["Summe Betriebsausgaben", -e["ausgaben"]], ["Gewinn / Verlust", e["gewinn"]]]
    out = [_sh(f"EÜR {year}", [("Position", "t", 50), ("Betrag", "m", 15)], rows, f"Einnahmen-Überschuss-Rechnung {year}", False),
           _sh(f"Anlage EÜR {year}", [("Zeile", "n", 7), ("Kz", "n", 7), ("Bezeichnung", "t", 60), ("Betrag", "m", 14)],
               [[z, k_, lbl, v] for z, k_, lbl, v in euer_form(year)], "", False),
           _sh(f"Einnahmen {year}", [("Nr.", "t", 12), ("Datum", "d", 11), ("Bezahlt", "d", 11), ("Kunde / Partner", "t", 30), ("Betrag", "m", 13)],
               [[r["nr"], r["datum"], r["bezahlt_am"] or r["datum"], inv_name(r), r["summe"]] for r in e["paid_list"]] +
               [[r["nr"] or "", r["datum"], r["datum"], r["partner"] or "", r["betrag"]] for r in e["einnahmen_list"]]),
           _sh(f"Ausgaben {year}", [("Datum", "d", 11), ("Partner", "t", 28), ("Beleg-Nr.", "t", 14), ("Kategorie", "t", 28), ("Betrag", "m", 13)],
               [[r["datum"], r["partner"] or "", r["nr"] or "", r["kategorie"] or "", r["betrag"]] for r in e["ausgaben_list"]])]
    try:
        tc = tax_calc(year)
        c_ = tc["calc"]
        g = tc["gehalt"]
        out.append(_kv(f"Steuer {year}", [("Bruttolohn", _m(g["brutto"])), ("Lohnsteuer", _m(g["lst"])), ("Gewinn Selbstständigkeit", _m(e["gewinn"])),
                                          ("Zu versteuerndes Einkommen (geschätzt)", _m(c_["zve"])), ("Einkommensteuer", _m(c_["est"])), ("Solidaritätszuschlag", _m(c_["soli"])),
                                          ("Kirchensteuer", _m(c_["kist"])), ("Steuer gesamt", _m(c_["gesamt"])), ("Bereits gezahlt", _m(tc["bereits_gezahlt"])),
                                          ("Differenz (+ Nachzahlung / − Erstattung)", _m(tc["differenz"]))], "Schätzung nach Tarif"))
        if tc["arbeitgeber"]:
            out.append(_sh(f"Gehalt {year}", [("Arbeitgeber", "t", 26), ("Quelle", "t", 24), ("Brutto", "m", 13), ("Lohnsteuer", "m", 12), ("Soli", "m", 10),
                                              ("RV", "m", 11), ("KV", "m", 11), ("PV", "m", 10), ("AV", "m", 10), ("Netto", "m", 13)],
                           [[a["name"], a["quelle"], a["brutto"], a["lst"], a["soli"], a["rv"], a["kv"], a["pv"], a["av"], a["netto"]] for a in tc["arbeitgeber"]]))
    except Exception:
        traceback.print_exc()
    ab = tax_inputs(year).get("abschluss") or {}
    if ab:
        out.append(_kv(f"Jahresabschluss {year}", [(lbl, _m(float(ab[k_])) if isinstance(ab.get(k_), (int, float)) else str(ab.get(k_) or ""))
                                                    for k_, lbl in ABSCHLUSS_FELDER if ab.get(k_) not in (None, "")] +
                       [("Bescheid vom", de_date(ab.get("bescheid_datum") or "")), ("Abgeschlossen", "ja" if ab.get("abgeschlossen") else "nein")] +
                       [("Anmerkung", n_) for n_ in ab.get("notizen") or []]))
    return out


def ex_projects(p):
    rows = []
    for x_ in q("SELECT * FROM projects ORDER BY nr"):
        c = q("SELECT * FROM customers WHERE id=?", (x_["customer_id"],), one=True) if x_["customer_id"] else None
        su = q(f"SELECT COALESCE(SUM(summe),0) s, COUNT(*) n FROM invoices WHERE project_id=? AND {COUNT_SQL}", (x_["id"],), one=True)
        rows.append([x_["nr"], x_["name"], _cname(c), x_["bereich"] or "", x_["status"] or "", x_["start"] or "", x_["ende"] or "", x_["budget"] or 0, su["n"], su["s"]])
    return [_sh("Projekte", [("Nr.", "t", 10), ("Name", "t", 30), ("Kunde", "t", 24), ("Bereich", "t", 13), ("Status", "t", 12), ("Start", "d", 11), ("Ende", "d", 11),
                             ("Budget", "m", 12), ("Rechnungen", "n", 10), ("Umsatz", "m", 13)], rows)]


def ex_project(p):
    x_ = get_project(int(p["id"]))
    if not x_:
        raise ValueError("Projekt nicht gefunden.")
    out = [_kv(f"Projekt {x_['nr']}", [("Nummer", x_["nr"]), ("Name", x_["name"]), ("Kunde", _cname(x_["customer"])), ("Bereich", x_["bereich"] or ""),
                                       ("Status", x_["status"] or ""), ("Start", de_date(x_["start"] or "")), ("Ende", de_date(x_["ende"] or "")),
                                       ("Budget", _m(x_["budget"] or 0)), ("Beschreibung", x_["descr"] or ""), ("Ordner", x_["abs_dir"])]),
           _sh("Leistungen", [("Datum", "d", 11), ("Art", "t", 12), ("Nr.", "t", 10), ("Bezeichnung", "t", 30), ("Beschreibung", "t", 30), ("Menge", "n", 8),
                              ("Einheit", "t", 8), ("Preis", "m", 12), ("Gesamt", "m", 13), ("abgerechnet", "t", 10)],
               [[e_["datum"], e_["art"] or "", e_["nr"] or "", e_["name"] or "", e_["descr"] or "", e_["qty"] or 0, e_["unit"] or "", e_["price"] or 0,
                 round((e_["qty"] or 0) * (e_["price"] or 0), 2), "ja" if e_["invoice_id"] else "nein"] for e_ in x_["entries"]]),
           _sh("Rechnungen", [("Nr.", "t", 12), ("Art", "t", 14), ("Datum", "d", 11), ("Status", "t", 11), ("Betrag", "m", 13)],
               [[r["nr"] or "Entwurf", TYP_DE.get(r["typ"], r["typ"]), r["datum"], r["status"], r["summe"] or 0] for r in x_["invoices"]]),
           _sh("Belege", [("Datum", "d", 11), ("Partner", "t", 28), ("Kategorie", "t", 26), ("Betrag", "m", 13)],
               [[b["datum"], b["partner"] or "", b["kategorie"] or "", b["betrag"] or 0] for b in x_["belege"]]),
           _sh("Dateien", [("Ordner", "t", 26), ("Art", "t", 16), ("Datei", "t", 40), ("Größe KB", "n", 10), ("Hinzugefügt", "d", 11)],
               [[f_["folder"] or "", f_["kind"] or "", f_["name"] or "", round((f_["size"] or 0) / 1024, 1), (f_["added"] or "")[:10]] for f_ in x_["files"]], total=False)]
    return out


def ex_unterricht(p):
    year = str(p.get("year") or datetime.date.today().year)
    cus = {c["id"]: _cname(c) for c in q("SELECT * FROM customers")}
    studs = q("SELECT * FROM students ORDER BY name")
    sn = {s_["id"]: s_["name"] for s_ in studs}
    out = [_sh("Schüler", [("Name", "t", 26), ("Rechnungsempfänger", "t", 26), ("Modus", "t", 10), ("Dauer h", "n", 8), ("Rhythmus", "t", 14), ("Aktiv", "t", 6), ("Notiz", "t", 26)],
               [[s_["name"], cus.get(s_["customer_id"], ""), s_["modus"] or "", s_["dauer"] or 0, s_["rhythmus"] or "", "ja" if s_["aktiv"] else "nein", s_["notiz"] or ""]
                for s_ in studs], "", False),
           _sh(f"Stunden {year}", [("Datum", "d", 11), ("Schüler", "t", 26), ("Dauer h", "n", 8), ("Status", "t", 14), ("abgerechnet", "t", 11), ("Notiz", "t", 30)],
               [[l_["datum"], sn.get(l_["student_id"], ""), l_["dauer"] or 0, l_["status"] or "stattgefunden", "ja" if l_["invoice_id"] else "nein", l_["notiz"] or ""]
                for l_ in q("SELECT * FROM lessons WHERE substr(datum,1,4)=? ORDER BY datum", (year,))], "", False)]
    kurse = q("SELECT * FROM kurse ORDER BY name")
    if kurse:
        out.append(_sh("Kurse", [("Kurs", "t", 26), ("Rechnungsempfänger", "t", 26), ("Modus", "t", 10), ("Start", "d", 11), ("Ende", "d", 11), ("Aktiv", "t", 6)],
                       [[k_["name"], cus.get(k_["customer_id"], ""), k_["modus"] or "", k_["start"] or "", k_["ende"] or "", "ja" if k_["aktiv"] else "nein"] for k_ in kurse], "", False))
    return out


def ex_abos(p):
    cus = {c["id"]: _cname(c) for c in q("SELECT * FROM customers")}
    return [_sh("Wiederkehrende Rechnungen", [("Name", "t", 30), ("Vorlage", "t", 12), ("Intervall Monate", "n", 10), ("Nächste", "d", 11), ("Letzte", "d", 11), ("Aktiv", "t", 6)],
                [[r["name"], (q("SELECT nr FROM invoices WHERE id=?", (r["invoice_id"],), one=True) or {}).get("nr", ""), r["intervall"], r["naechstes"] or "", r["letzte"] or "",
                  "ja" if r["aktiv"] else "nein"] for r in q("SELECT * FROM recurring ORDER BY name")], "", False),
            _sh("Wartungsverträge", [("Name", "t", 28), ("Kunde", "t", 26), ("Intervall Monate", "n", 10), ("Nächste", "d", 11), ("Letzte", "d", 11), ("Preis", "m", 12),
                                     ("Auto-Rechnung", "t", 10), ("Aktiv", "t", 6)],
                [[v["name"], cus.get(v["customer_id"], ""), v["intervall"], v["naechste"] or "", v["letzte"] or "", v["preis"] or 0, "ja" if v["auto_rechnung"] else "nein",
                  "ja" if v["aktiv"] else "nein"] for v in q("SELECT * FROM vertraege ORDER BY name")])]


def ex_mahn(p):
    rows = []
    for r in overdue_list():
        rows.append([r["nr"], r["datum"], r["name"], r["faellig"], r["tage"], r.get("mahnstufe") or 0, r["summe"] or 0])
    return [_sh("Mahnwesen", [("Nr.", "t", 12), ("Datum", "d", 11), ("Kunde", "t", 30), ("Fällig", "d", 11), ("Tage überfällig", "n", 10), ("Mahnstufe", "n", 9),
                              ("Betrag", "m", 13)], rows, "überfällige Rechnungen")]


def ex_gesamt(p):
    out = []
    years = sorted({int(r["y"]) for r in q("SELECT DISTINCT substr(datum,1,4) y FROM invoices WHERE datum<>'' UNION SELECT DISTINCT substr(datum,1,4) FROM belege WHERE datum<>''")
                    if r["y"] and r["y"].isdigit()})
    out += ex_invoices({}) + ex_customers({}) + ex_articles({}) + ex_projects({}) + ex_belege({}) + ex_bank({}) + ex_fahrten({}) + ex_zert({}) + ex_steuerakte({}) + ex_abos({})
    all_items = []
    for r in q("SELECT i.*, v.nr AS rnr, v.datum AS rdatum FROM items i JOIN invoices v ON v.id=i.invoice_id ORDER BY v.datum, v.nr, i.pos"):
        all_items.append([r["rnr"] or "Entwurf", r["rdatum"], r["pos"], r["nr"] or "", r["name"] or "", r["qty"] or 0, r["price"] or 0, r["total"] or 0])
    out.append(_sh("Rechnungspositionen", [("Rechnung", "t", 12), ("Datum", "d", 11), ("Pos.", "n", 6), ("Art.-Nr.", "t", 10), ("Bezeichnung", "t", 34), ("Menge", "n", 8),
                                           ("Einzelpreis", "m", 12), ("Gesamt", "m", 13)], all_items))
    for y in years:
        out += ex_euer({"year": y})[:1]
    out.append(ex_stats({"year": years[-1] if years else datetime.date.today().year})[-1])
    for y in years:
        out += [a for a in ex_assets({"year": y}) if a["rows"]]
    return out


# ---------------- v1.6.2: Statistik-Unterrubriken (Rechnungen / Einnahmen / Ausgaben) ----------------

def _cust_map():
    return {c["id"]: (c["firma"] or c["name"] or c["kdnr"] or "") for c in q("SELECT id, firma, name, kdnr FROM customers")}


def _inv_name_fast(r, cm):
    if r["customer_id"] and cm.get(r["customer_id"]):
        return cm[r["customer_id"]]
    try:
        a = [l for l in json.loads(r["addr"] or "[]") if not re.match(r"^(herrn?|frau|familie|firma)$", l.strip(), re.I)]
    except Exception:
        a = []
    return a[0] if a else (r["kdnr"] or "")


def stats_detail(year=None):
    """flat lists for the Statistik sub tabs; year=None -> all years"""
    ys = str(year) if year else ""
    cm = _cust_map()
    pn = _proj_names()
    today_d = datetime.date.today()
    re_rows = []
    for r in q("SELECT * FROM invoices WHERE typ IN ('rechnung','storno') AND status<>'entwurf' AND datum<>'' ORDER BY datum, nr"):
        if ys and not (r["datum"] or "").startswith(ys):
            continue
        frist = _frist(r["frist"])
        try:
            due = d_iso(r["datum"]) + datetime.timedelta(days=frist)
        except Exception:
            due = None
        tage = None
        if r["status"] == "bezahlt" and r["bezahlt_am"]:
            try:
                tage = (d_iso(r["bezahlt_am"]) - d_iso(r["datum"])).days
            except Exception:
                tage = None
        ueber = bool(r["status"] == "offen" and r["typ"] == "rechnung" and due and due < today_d)
        re_rows.append({"id": r["id"], "nr": r["nr"] or "", "typ": r["typ"], "datum": r["datum"], "jahr": int(r["datum"][:4]),
                        "monat": int(r["datum"][5:7]), "kunde": _inv_name_fast(r, cm), "kdnr": r["kdnr"] or "",
                        "ckey": str(r["customer_id"] or r["kdnr"] or _inv_name_fast(r, cm)), "titel": r["titel"] or "",
                        "status": r["status"] or "", "bezahlt_am": r["bezahlt_am"] or "", "faellig": due.isoformat() if due else "",
                        "tage": tage, "ueberfaellig": ueber, "summe": round(r["summe"] or 0, 2),
                        "zaehlt": r["status"] not in ("storniert",), "projekt": pn.get(r["project_id"], ""), "project_id": r["project_id"],
                        "locked": bool(r["locked"]) if "locked" in r.keys() else False})   # v3.6.1: for "Aufraeumen"
    ein = []
    for r in q("SELECT * FROM invoices WHERE status='bezahlt' AND typ IN ('rechnung','storno') ORDER BY COALESCE(NULLIF(bezahlt_am,''),datum)"):
        try:
            y, ten = zufluss_year(r)
        except Exception:
            continue
        if ys and y != int(ys):
            continue
        z = r["bezahlt_am"] or r["datum"]
        mon = int(z[5:7]) if z[:4] == str(y) else 12
        ein.append({"art": "rechnung", "id": r["id"], "nr": r["nr"] or "", "datum": r["datum"], "zufluss": z, "jahr": y, "monat": mon,
                    "partner": _inv_name_fast(r, cm), "ckey": str(r["customer_id"] or r["kdnr"] or _inv_name_fast(r, cm)),
                    "kategorie": "Rechnung" if r["typ"] == "rechnung" else "Storno / Erstattung", "titel": r["titel"] or "",
                    "zehn_tage": ten, "summe": round(r["summe"] or 0, 2), "projekt": pn.get(r["project_id"], "")})
    for b in q("SELECT * FROM belege WHERE typ='einnahme' AND datum<>'' ORDER BY datum"):
        if ys and not b["datum"].startswith(ys):
            continue
        ein.append({"art": "sonstige", "id": b["id"], "nr": b["nr"] or "", "datum": b["datum"], "zufluss": b["datum"], "jahr": int(b["datum"][:4]),
                    "monat": int(b["datum"][5:7]), "partner": b["partner"] or "", "ckey": "b:" + (b["partner"] or "").strip().lower(),
                    "kategorie": b["kategorie"] or "Sonstige Einnahme", "titel": b["notiz"] or "", "zehn_tage": False,
                    "summe": round(b["betrag"] or 0, 2), "projekt": pn.get(b["project_id"], "")})
    ein.sort(key=lambda x: (x["zufluss"], x["nr"]))
    asset_ids = {r["beleg_id"] for r in q("SELECT beleg_id FROM assets WHERE beleg_id IS NOT NULL")}
    aus = []
    for b in q("SELECT * FROM belege WHERE typ='ausgabe' AND datum<>'' ORDER BY datum, id"):
        if ys and not b["datum"].startswith(ys):
            continue
        k = b["kategorie"] or "Sonstige Betriebsausgaben"
        anl = b["id"] in asset_ids
        abz = 0.0 if anl else round((b["betrag"] or 0) * (0.7 if k.startswith("Bewirtung") else 1.0), 2)
        aus.append({"id": b["id"], "nr": b["nr"] or "", "datum": b["datum"], "jahr": int(b["datum"][:4]), "monat": int(b["datum"][5:7]),
                    "partner": b["partner"] or "", "kategorie": k, "notiz": b["notiz"] or "", "betrag": round(b["betrag"] or 0, 2),
                    "abzug": abz, "anlage": anl, "projekt": pn.get(b["project_id"], ""), "file": b["file"] or ""})
    geh, has_year = [], set()
    graw = []
    for b in q("SELECT * FROM belege WHERE typ='gehalt' AND datum<>'' ORDER BY datum, id"):
        if ys and not b["datum"].startswith(ys):
            continue
        try:
            dd = json.loads(b["details"] or "{}")
        except Exception:
            dd = {}
        graw.append((b, dd))
        if dd.get("zeitraum") == "jahr":
            has_year.add((b["datum"][:4], (b["partner"] or "Arbeitgeber").strip().lower()))
    for b, dd in graw:
        f_ = lambda k: round(float(dd.get(k) or 0), 2)
        jahr_ = dd.get("zeitraum") == "jahr"
        key = (b["datum"][:4], (b["partner"] or "Arbeitgeber").strip().lower())
        geh.append({"id": b["id"], "datum": b["datum"], "jahr": int(b["datum"][:4]), "monat": int(b["datum"][5:7]),
                    "partner": b["partner"] or "Arbeitgeber", "art": "jahr" if jahr_ else "monat",
                    "zeitraum": "Lohnsteuerbescheinigung" if jahr_ else (dd.get("periode") or MONTHS_LONG[int(b["datum"][5:7]) - 1] + " " + b["datum"][:4]),
                    "brutto": f_("brutto"), "lst": f_("lst"), "soli": f_("soli"), "kist": f_("kist"), "rv": f_("rv"), "kv": f_("kv"), "pv": f_("pv"),
                    "av": f_("av"), "netto": f_("netto") or round(b["betrag"] or 0, 2),
                    "steuer": round(f_("lst") + f_("soli") + f_("kist"), 2), "sozial": round(f_("rv") + f_("kv") + f_("pv") + f_("av"), 2),
                    "zaehlt": jahr_ or key not in has_year, "file": b["file"] or "", "notiz": b["notiz"] or ""})
    years = sorted({int(r["y"]) for r in q("SELECT DISTINCT substr(datum,1,4) y FROM invoices WHERE datum<>'' UNION SELECT DISTINCT substr(datum,1,4) FROM belege WHERE datum<>''")
                    if r["y"] and r["y"].isdigit()}, reverse=True)
    return {"year": year, "years": years, "rechnungen": re_rows, "einnahmen": ein, "ausgaben": aus, "gehalt": geh}




def _sd_filter(rows, p, kind):
    st, ck, qq = p.get("status") or "", p.get("ckey") or "", (p.get("q") or "").lower().strip()
    kat, art = p.get("kat") or "", p.get("art") or ""
    out = []
    for r in rows:
        if kind == "re":
            if st == "ueberfaellig":
                if not r["ueberfaellig"]:
                    continue
            elif st and r["status"] != st:
                continue
            if ck and r["ckey"] != ck:
                continue
            hay = f"{r['nr']} {r['kunde']} {r['titel']} {r['projekt']}"
        elif kind == "ein":
            if art and r["art"] != art:
                continue
            if ck and r["ckey"] != ck:
                continue
            hay = f"{r['nr']} {r['partner']} {r['titel']} {r['kategorie']}"
        elif kind == "geh":
            if art and r["art"] != art:
                continue
            if ck and r["partner"].strip().lower() != ck:
                continue
            hay = f"{r['partner']} {r['zeitraum']} {r['notiz']}"
        else:
            if kat and r["kategorie"] != kat:
                continue
            if ck and r["partner"].strip().lower() != ck:
                continue
            hay = f"{r['nr']} {r['partner']} {r['notiz']} {r['kategorie']} {r['projekt']}"
        if qq and qq not in hay.lower():
            continue
        out.append(r)
    ids = _ids(p)
    if ids:
        out = [r for r in out if r["id"] in ids]
    return out


def _sd_group_key(r, g, kind):
    if g == "monat":
        return f"{r['jahr']}-{r['monat']:02d}", f"{MONTHS_LONG[r['monat'] - 1]} {r['jahr']}"
    if g == "quartal":
        qq = (r["monat"] - 1) // 3 + 1
        return f"{r['jahr']}-Q{qq}", f"Q{qq} {r['jahr']}"
    if g == "kunde":
        n = r.get("kunde", r.get("partner", "")) if kind == "re" else r.get("partner", r.get("kunde", ""))
        return (n or "").lower(), n or "(ohne Name)"
    if g == "arbeitgeber":
        return (r.get("partner", r.get("kunde", "")) or "").lower(), r.get("partner", r.get("kunde", "")) or "(ohne Arbeitgeber)"
    if g == "lieferant":
        return (r.get("partner", r.get("kunde", "")) or "").lower(), r.get("partner", r.get("kunde", "")) or "(ohne Lieferant)"
    if g == "kategorie":
        return r.get("kategorie", ""), r.get("kategorie", "")
    if g == "projekt":
        return r.get("projekt", "") or "~", r.get("projekt", "") or "(ohne Projekt)"
    if g == "status":
        return r.get("status", ""), r.get("status", "")
    if g == "art":
        if kind == "geh":
            return r.get("art", ""), "Lohnsteuerbescheinigungen" if r.get("art", "") == "jahr" else "Monatsabrechnungen"
        return r.get("art", ""), "Rechnungen" if r.get("art", "") == "rechnung" else "Sonstige Einnahmen"
    return str(r["jahr"]), str(r["jahr"])


def ex_stat_detail(p, kind):
    yr = p.get("year")
    year = int(yr) if str(yr or "").isdigit() else None
    d = stats_detail(year)
    g = p.get("group") or "jahr"
    lab = "alle Jahre" if not year else str(year)
    if kind == "re":
        rows = _sd_filter(d["rechnungen"], p, "re")
        sheet = _sh(f"Rechnungen {lab}", [("Nr.", "t", 12), ("Datum", "d", 11), ("Kunde", "t", 28), ("Kd-Nr.", "t", 9), ("Titel", "t", 28),
                                           ("Status", "t", 11), ("Fällig", "d", 11), ("Bezahlt am", "d", 11), ("Zahltage", "n", 9),
                                           ("Projekt", "t", 20), ("Betrag", "m", 13)],
                    [[r["nr"], r["datum"], r["kunde"], r["kdnr"], r["titel"], r["status"] + (" (überfällig)" if r["ueberfaellig"] else ""),
                      r["faellig"], r["bezahlt_am"], r["tage"] if r["tage"] is not None else "", r["projekt"], r["summe"]] for r in rows],
                    f"Alle geschriebenen Rechnungen · {lab}")
        val = lambda r: r["summe"] if r["zaehlt"] else 0.0
        title = "Rechnungen"
    elif kind == "ein":
        rows = _sd_filter(d["einnahmen"], p, "ein")
        sheet = _sh(f"Einnahmen {lab}", [("Zufluss", "d", 11), ("Art", "t", 18), ("Nr.", "t", 12), ("Rechnungsdatum", "d", 13), ("Kunde / Partner", "t", 28),
                                          ("Titel / Notiz", "t", 28), ("10-Tage-Regel", "t", 11), ("Betrag", "m", 13)],
                    [[r["zufluss"], r["kategorie"], r["nr"], r["datum"], r["partner"], r["titel"], "ja" if r["zehn_tage"] else "", r["summe"]] for r in rows],
                    f"Betriebseinnahmen nach Zuflussprinzip · {lab}")
        val = lambda r: r["summe"]
        title = "Einnahmen"
    elif kind == "geh":
        rows = _sd_filter(d["gehalt"], p, "geh")
        sheet = _sh(f"Gehalt {lab}", [("Datum", "d", 11), ("Arbeitgeber", "t", 26), ("Zeitraum", "t", 22), ("Brutto", "m", 13), ("Lohnsteuer", "m", 12),
                                       ("Soli", "m", 10), ("KiSt", "m", 10), ("RV", "m", 11), ("KV", "m", 11), ("PV", "m", 10), ("AV", "m", 10),
                                       ("Netto", "m", 13), ("gezaehlt", "t", 9)],
                    [[r["datum"], r["partner"], r["zeitraum"], r["brutto"], r["lst"], r["soli"], r["kist"], r["rv"], r["kv"], r["pv"], r["av"], r["netto"],
                      "ja" if r["zaehlt"] else "nein (Jahreswerte)"] for r in rows],
                    f"Gehaltsabrechnungen · {lab} · Summen ohne Monatswerte, wenn eine Lohnsteuerbescheinigung vorliegt")
        val = lambda r: r["brutto"] if r["zaehlt"] else 0.0
        title = "Gehalt"
    else:
        rows = _sd_filter(d["ausgaben"], p, "aus")
        sheet = _sh(f"Ausgaben {lab}", [("Datum", "d", 11), ("Lieferant", "t", 26), ("Beleg-Nr.", "t", 13), ("Kategorie", "t", 28), ("Notiz", "t", 24),
                                         ("Projekt", "t", 18), ("Hinweis", "t", 16), ("Betrag", "m", 13), ("abzugsfähig", "m", 13)],
                    [[r["datum"], r["partner"], r["nr"], r["kategorie"], r["notiz"], r["projekt"], "Anlage (AfA)" if r["anlage"] else "",
                      r["betrag"], r["abzug"]] for r in rows],
                    f"Betriebsausgaben (Belege) · {lab}")
        val = lambda r: r["abzug"]
        title = "Ausgaben"
    grp = {}
    for r in rows:
        k, lb = _sd_group_key(r, g, kind)
        e = grp.setdefault(k, [lb, 0, 0.0])
        e[1] += 1
        e[2] += val(r)
    tot = sum(v[2] for v in grp.values()) or 1
    keys = sorted(grp, reverse=g in ("jahr", "monat", "quartal")) if g in ("jahr", "monat", "quartal") else sorted(grp, key=lambda k: -grp[k][2])
    gname = {"jahr": "Jahr", "monat": "Monat", "quartal": "Quartal", "kunde": "Kunde", "lieferant": "Lieferant", "kategorie": "Kategorie",
             "projekt": "Projekt", "status": "Status", "art": "Art", "arbeitgeber": "Arbeitgeber"}.get(g, "Gruppe")
    summ = _sh(f"{title} je {gname}", [(gname, "t", 30), ("Anzahl", "n", 9), ("Summe", "m", 14), ("Anteil %", "p", 9)],
               [[grp[k][0], grp[k][1], round(grp[k][2], 2), round(100 * grp[k][2] / tot, 1)] for k in keys], "")
    return [summ, sheet]

EXPORTS = {"invoices": ("Rechnungen", ex_invoices), "invoice": ("Rechnung", ex_invoice), "customers": ("Kunden", ex_customers), "customer": ("Kunde", ex_customer),
           "articles": ("Bausteine", ex_articles), "belege": ("Belege", ex_belege), "bank": ("Bank", ex_bank), "assets": ("Anlagen", ex_assets),
           "fahrten": ("Fahrten", ex_fahrten), "zert": ("Nachweise", ex_zert), "steuerakte": ("Steuerakte", ex_steuerakte), "stats": ("Statistik", ex_stats),
           "euer": ("EUER_Steuer", ex_euer), "projects": ("Projekte", ex_projects), "project": ("Projekt", ex_project), "unterricht": ("Unterricht", ex_unterricht),
           "abos": ("Wartung_Abos", ex_abos), "mahn": ("Mahnwesen", ex_mahn), "gesamt": ("Gesamtexport", ex_gesamt),
           "stat_re": ("Statistik_Rechnungen", lambda p: ex_stat_detail(p, "re")), "stat_ein": ("Statistik_Einnahmen", lambda p: ex_stat_detail(p, "ein")),
           "stat_aus": ("Statistik_Ausgaben", lambda p: ex_stat_detail(p, "aus")), "stat_geh": ("Statistik_Gehalt", lambda p: ex_stat_detail(p, "geh"))}


def _xl_title(t, used):
    t = re.sub(r"[\[\]\*\?/\\:]", "-", XL_ILLEGAL.sub("", t)).strip("'")[:31] or "Tabelle"
    base, n = t, 2
    while t.lower() in used:
        t = (base[:28] + f" {n}")[:31]
        n += 1
    used.add(t.lower())
    return t


XL_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xl_put(ws, row, col, v):
    """write a cell; text is never interpreted as a formula (=, +, -, @ at the start) and illegal characters are removed"""
    if isinstance(v, str):
        v = XL_ILLEGAL.sub("", v)
    c = ws.cell(row, col, v if v != "" else None)
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        c.data_type = "s"
    return c


def export_xlsx(sheets, title):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    used = set()
    hfill = PatternFill("solid", fgColor="5B3FD6")
    tfill = PatternFill("solid", fgColor="EBE7FB")
    thin = Side(style="thin", color="D6D2E6")
    if len(sheets) > 1:
        ws = wb.create_sheet(_xl_title("Übersicht", used))
        _xl_put(ws, 1, 1, title).font = Font(bold=True, size=14)
        _xl_put(ws, 2, 1, f"{get_settings().get('firma') or ''} · erstellt am {de_date(today())} · {APP_NAME} v{APP_VERSION}").font = Font(color="6C6880")
        ws["A4"], ws["B4"], ws["C4"] = "Tabelle", "Zeilen", "Info"
        for c in ("A4", "B4", "C4"):
            ws[c].font = Font(bold=True, color="FFFFFF")
            ws[c].fill = hfill
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 40
        ov = ws
        ov_row = 5
    else:
        ov = None
    for sh in sheets:
        ws = wb.create_sheet(_xl_title(sh["title"], used))
        if ov is not None:
            _xl_put(ov, ov_row, 1, sh["title"]).hyperlink = "#'" + ws.title.replace("'", "''") + "'!A1"
            ov.cell(ov_row, 1).font = Font(color="5B3FD6", underline="single")
            ov.cell(ov_row, 2, len(sh["rows"]))
            _xl_put(ov, ov_row, 3, sh.get("sub") or "")
            ov_row += 1
        cols = sh["cols"]
        for ci, (lb, kd, w) in enumerate(cols, 1):
            c = _xl_put(ws, 1, ci, lb)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = hfill
            c.alignment = Alignment(horizontal="right" if kd in ("m", "n", "p") else "left", vertical="center")
            ws.column_dimensions[get_column_letter(ci)].width = max(6, w * 1.05)
        for ri, row in enumerate(sh["rows"], 2):
            for ci, (v, (lb, kd, w)) in enumerate(zip(row, cols), 1):
                if kd == "d" and isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", v or ""):
                    try:
                        v = datetime.date.fromisoformat(v[:10])
                    except Exception:
                        pass
                c = _xl_put(ws, ri, ci, v)
                if kd == "m":
                    c.number_format = '#,##0.00 "€";[Red]-#,##0.00 "€"'
                elif kd == "d" and isinstance(v, datetime.date):
                    c.number_format = "DD.MM.YYYY"
                elif kd == "p":
                    c.number_format = '0.0 "%"'
                elif kd == "t" and isinstance(v, str) and len(v) > 60:
                    c.alignment = Alignment(wrap_text=True, vertical="top")
                c.border = Border(bottom=thin)
        n = len(sh["rows"])
        if sh["sum"] and n:
            r = n + 2
            ws.cell(r, 1, "Summe").font = Font(bold=True)
            for ci, (lb, kd, w) in enumerate(cols, 1):
                ws.cell(r, ci).fill = tfill
                if kd == "m":
                    L = get_column_letter(ci)
                    c = ws.cell(r, ci, f"=SUM({L}2:{L}{n + 1})")
                    c.number_format = '#,##0.00 "€";[Red]-#,##0.00 "€"'
                    c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        if n:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n + 1}"
        ws.sheet_view.zoomScale = 100
    if not wb.sheetnames:
        wb.create_sheet("Leer")
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _fmt_cell(v, kd):
    if v is None or v == "":
        return ""
    if isinstance(v, str) and len(v) > 700:
        v = v[:700] + " …"
    if kd == "m":
        return _m(float(v))
    if kd == "d":
        return de_date(str(v)[:10]) if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", str(v)) else str(v)
    if kd == "p":
        return f"{float(v):.1f} %".replace(".", ",")
    if kd == "n":
        return f"{v:g}".replace(".", ",") if isinstance(v, float) else str(v)
    return str(v)


def export_pdf(sheets, title):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak, NextPageTemplate, PageTemplate, Frame, KeepTogether
    from reportlab.platypus.doctemplate import BaseDocTemplate
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import landscape
    firma = get_settings().get("firma") or ""
    H1 = ParagraphStyle("h1", fontName=FONT_B(), fontSize=15, leading=19, textColor=JB_INK)
    SUB = ParagraphStyle("s", fontName=FONT_R(), fontSize=8, leading=11, textColor=JB_GRAY, spaceAfter=6)
    CELL = ParagraphStyle("c", fontName=FONT_R(), fontSize=7.4, leading=9, textColor=JB_INK)
    HEAD = ParagraphStyle("hc", parent=CELL, fontName=FONT_B(), textColor=colors.white)
    PW, PH = A4
    LW, LH = landscape(A4)

    def deco(c, doc):
        c.saveState()
        w, h = c._pagesize
        c.setFont(FONT_R(), 7)
        c.setFillColor(JB_GRAY)
        c.drawString(14 * mm, h - 9 * mm, f"{title} · {firma}")
        c.drawRightString(w - 14 * mm, 8 * mm, f"Seite {doc.page} · erstellt am {de_date(today())}")
        c.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, title=title, author=get_settings().get("inhaber") or "", creator=f"{APP_NAME} v{APP_VERSION}")
    tP = PageTemplate(id="P", pagesize=A4, frames=[Frame(14 * mm, 14 * mm, PW - 28 * mm, PH - 28 * mm, id="fp")], onPage=deco)
    tL = PageTemplate(id="L", pagesize=landscape(A4), frames=[Frame(14 * mm, 14 * mm, LW - 28 * mm, LH - 28 * mm, id="fl")], onPage=deco)
    first_land = bool(sheets) and sum(c[2] for c in sheets[0]["cols"]) > 120
    doc.addPageTemplates([tL, tP] if first_land else [tP, tL])
    el = []
    first = True
    prev_t = None
    for sh in sheets:
        cols = sh["cols"]
        tw = sum(c[2] for c in cols)
        land = tw > 120
        avail = (LW if land else PW) - 28 * mm
        tmpl = "L" if land else "P"
        if not first:
            if tmpl != prev_t or len(sh["rows"]) > 25:
                el += [NextPageTemplate(tmpl), PageBreak()]
            else:
                el.append(Spacer(1, 16))
        first = False
        prev_t = tmpl
        head_ = ([Paragraph(esc_xml(sh["title"]), H1),
                                Paragraph(esc_xml(" · ".join(x for x in (sh.get("sub") or "", "" if sh.get("kv") else f"{len(sh['rows'])} Einträge") if x)) or "&nbsp;", SUB)])
        ws_ = [avail * c[2] / tw for c in cols]
        R = lambda kd: ParagraphStyle("r", parent=CELL, alignment=2) if kd in ("m", "n", "p") else CELL
        RH = lambda kd: ParagraphStyle("rh", parent=HEAD, alignment=2) if kd in ("m", "n", "p") else HEAD
        data = [[Paragraph(esc_xml(lb), RH(kd)) for lb, kd, w in cols]]
        for row in sh["rows"]:
            data.append([Paragraph(esc_xml(_fmt_cell(v, kd)), R(kd)) for v, (lb, kd, w) in zip(row, cols)])
        if not sh["rows"]:
            data.append([Paragraph("keine Einträge", CELL)] + [""] * (len(cols) - 1))
        if sh["sum"] and sh["rows"]:
            tot = []
            for ci, (lb, kd, w) in enumerate(cols):
                if kd == "m":
                    tot.append(Paragraph("<b>" + _m(round(sum(float(r[ci] or 0) for r in sh["rows"]), 2)) + "</b>", R(kd)))
                else:
                    tot.append(Paragraph("<b>Summe</b>", CELL) if ci == 0 else "")
            data.append(tot)
        # v2.1.0: long lists as consecutive tables of 200 rows (one huge table makes reportlab's page splitting superlinear)
        body_, tot_ = data[1:], []
        if sh["sum"] and sh["rows"]:
            body_, tot_ = data[1:-1], data[-1:]
        chunks = [body_[i0:i0 + 200] for i0 in range(0, len(body_), 200)] or [[]]
        tables = []
        for ci_, ch in enumerate(chunks):
            last_ = ci_ == len(chunks) - 1
            t = Table([data[0]] + ch + (tot_ if last_ else []), colWidths=ws_, repeatRows=1, splitInRow=1)
            sty = [("BACKGROUND", (0, 0), (-1, 0), JB_ACC), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, JB_SOFT]), ("LINEBELOW", (0, 1), (-1, -1), 0.25, JB_LINE),
                   ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
            if last_ and tot_:
                sty += [("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ebe7fb")), ("LINEABOVE", (0, -1), (-1, -1), 0.8, JB_INK)]
            if not sh["rows"]:
                sty.append(("SPAN", (0, 1), (-1, 1)))
            t.setStyle(TableStyle(sty))
            tables.append(t)
        el.append(KeepTogether(head_ + tables) if len(sh["rows"]) <= 25 else KeepTogether(head_))
        if len(sh["rows"]) > 25:
            el += tables
    doc.build(el or [Paragraph("Keine Daten", H1)])
    return buf.getvalue()


def run_export(d):
    kind = d.get("kind")
    if kind not in EXPORTS:
        raise ValueError("Unbekannter Export.")
    name, fn = EXPORTS[kind]
    fmt = "pdf" if d.get("fmt") == "pdf" else "xlsx"
    params = d.get("params") or {}
    if kind == "invoice" and fmt == "pdf" and not params.get("liste"):
        inv = get_invoice(int(params["id"]))
        if not inv:
            raise ValueError("Rechnung nicht gefunden.")
        data_ = render_invoice_pdf(inv)
        label = f"{name}_{inv['nr'] or 'Entwurf'}"
        label = re.sub(r"[^\w\-]+", "_", label)
    else:
        sheets = fn(params)
        sfx = [str(params[k]) for k in ("year",) if params.get(k)]
        if params.get("ids"):
            sfx.append("Auswahl")
        if kind in ("invoice", "customer", "project"):
            sfx.append(re.sub(r"[^\w\-]+", "_", sheets[0]["title"].split(" ", 1)[-1])[:40])
        label = re.sub(r"[^\w\-]+", "_", "_".join([name] + sfx))
        title = sheets[0]["title"] if kind in ("invoice", "customer", "project") else \
            name.replace("_", " / ").replace("EUER", "EÜR") + (" " + " ".join(sfx) if sfx else "")
        data_ = export_pdf(sheets, title) if fmt == "pdf" else export_xlsx(sheets, title)
    out = os.path.join(DATA_DIR, "Export", f"{label}_{time.strftime('%Y-%m-%d_%H%M%S')}.{fmt}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_file(out, data_)
    if not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(out)
    return {"ok": True, "path": out, "size": len(data_)}
