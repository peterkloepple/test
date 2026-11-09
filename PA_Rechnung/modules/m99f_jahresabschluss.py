# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m99f_jahresabschluss  v1.0.0 (ab Programm v3.4.0)
# Jahresabschluss-Assistent: fuehrt Schritt fuer Schritt durch ein Steuerjahr.
#   1 Rechnungen   (Entwuerfe, nicht festgeschrieben, bezahlt ohne Datum, offene Forderungen)
#   2 Belege       (ohne Datei, unbearbeitete Importe, Monate ohne Ausgaben, GWG ueber der Grenze)
#   3 Bank         (Kontoauszuege bis 31.12., offene Umsaetze im Abgleich)
#   4 Kasse        (Kassenbuch mit Abschluss zum Jahresende)
#   5 Anlagen      (Zugaenge des Jahres, AfA)
#   6 Fahrten / Gehalt (Fahrtenbuch, 12 Gehaltsabrechnungen)
#   7 Umsatzsteuer (Kleinunternehmer-Grenzen bzw. UStVA)
#   8 Ergebnis     (Gewinn, Steuer, Steuerbescheid in der Steuerakte)
#   9 ELSTER-Werte (Anlage EUER Zeile/Kennzahl, Anlage N) zum Abtippen
#  10 Ausgabe      (Jahresbericht-PDF, DATEV-Export, Datenpaket)
# Jeder Punkt: ok / Hinweis / Fehler, Erklaerung und Sprung auf die passende Seite. Haken "erledigt" je Schritt
# wird gespeichert (Einstellung m99f_done).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M99F_VERSION = "1.0.0"


def _ja(schritt, titel, status, text, seite="", n=None):
    return {"schritt": schritt, "titel": titel, "status": status, "text": text, "seite": seite, "n": n}


def _m99f_tab(name):
    return bool(q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,), one=True))


def m99f_check(year):
    y = int(year)
    ys = str(y)
    out = []

    def safe(fn):
        try:
            fn()
        except Exception as e:
            traceback.print_exc()
            out.append(_ja(0, "Prüfung", "fehler", f"Prüfung fehlgeschlagen: {e}"))

    def rechnungen():
        ent = q("SELECT COUNT(*) AS n FROM invoices WHERE typ='rechnung' AND status='entwurf' AND substr(datum,1,4)=?", (ys,), one=True)["n"]
        out.append(_ja(1, "Entwürfe", "warn" if ent else "ok",
                       f"{ent} Rechnungs-Entwürfe – fertigstellen oder löschen." if ent else "Keine offenen Entwürfe.", "inv", ent))
        nl = q("SELECT COUNT(*) AS n FROM invoices WHERE typ IN ('rechnung','storno') AND status IN ('offen','bezahlt') "
               "AND COALESCE(locked,0)=0 AND substr(datum,1,4)=?", (ys,), one=True)["n"]
        out.append(_ja(1, "Festgeschrieben", "warn" if nl else "ok",
                       f"{nl} Rechnungen sind noch nicht festgeschrieben (GoBD) – als PDF ausgeben oder versenden." if nl
                       else "Alle Rechnungen sind festgeschrieben.", "inv", nl))
        bz = q("SELECT COUNT(*) AS n FROM invoices WHERE typ='rechnung' AND status='bezahlt' AND COALESCE(bezahlt_am,'')='' AND substr(datum,1,4)=?",
               (ys,), one=True)["n"]
        out.append(_ja(1, "Zahldatum", "fehler" if bz else "ok",
                       f"{bz} bezahlte Rechnungen ohne Zahldatum – die Einnahme landet sonst im falschen Jahr." if bz
                       else "Jede bezahlte Rechnung hat ein Zahldatum.", "m45jahr", bz))
        of = q("SELECT COUNT(*) AS n, COALESCE(SUM(summe),0) AS s FROM invoices WHERE typ='rechnung' AND status='offen' AND substr(datum,1,4)=?",
               (ys,), one=True)
        out.append(_ja(1, "Offene Forderungen", "info" if of["n"] else "ok",
                       f"{of['n']} Rechnungen aus {y} noch offen ({money(of['s'])}) – zählen erst bei Zahlung (EÜR, Zufluss)." if of["n"]
                       else "Keine offenen Rechnungen aus diesem Jahr.", "inv", of["n"]))

    def belege():
        nf = q("SELECT COUNT(*) AS n FROM belege WHERE typ='ausgabe' AND COALESCE(file,'')='' AND COALESCE(quelle,'')<>'kasse' AND substr(datum,1,4)=?",
               (ys,), one=True)["n"]
        out.append(_ja(2, "Belegdateien", "warn" if nf else "ok",
                       f"{nf} Ausgaben ohne Belegdatei (z. B. aus dem Kontoauszug angelegt) – Rechnung/Quittung nachreichen oder einscannen." if nf
                       else "Zu jeder Ausgabe gibt es eine Belegdatei.", "beleg", nf))
        pe = q("SELECT COUNT(*) AS n FROM pending_belege", one=True)["n"]
        out.append(_ja(2, "Unbearbeitete Importe", "warn" if pe else "ok",
                       f"{pe} importierte Belege warten noch auf „Übernehmen“." if pe else "Keine unbearbeiteten Importe.", "beleg", pe))
        ms = {int(r["m"]) for r in q("SELECT DISTINCT substr(datum,6,2) AS m FROM belege WHERE typ='ausgabe' AND substr(datum,1,4)=?", (ys,))}
        last = 12 if y < datetime.date.today().year else datetime.date.today().month
        leer = [m_ for m_ in range(1, last + 1) if m_ not in ms]
        mon = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
        out.append(_ja(2, "Monate ohne Ausgaben", "info" if leer else "ok",
                       ("Keine Ausgaben in: " + ", ".join(mon[m_ - 1] for m_ in leer) + " – fehlt dort etwas (Telefon, Software, Fahrtkosten)?") if leer
                       else "In jedem Monat gibt es Ausgaben.", "beleg", len(leer)))
        gwg = [b for b in q("SELECT id, partner, betrag, datum FROM belege WHERE typ='ausgabe' AND kategorie LIKE 'Arbeitsmittel%' AND substr(datum,1,4)=?", (ys,))
               if not gwg_check(b["betrag"], b["datum"])]
        have = {r["beleg_id"] for r in q("SELECT beleg_id FROM assets WHERE beleg_id IS NOT NULL")}
        gwg = [b for b in gwg if b["id"] not in have]
        out.append(_ja(2, "Geringwertige Wirtschaftsgüter", "warn" if gwg else "ok",
                       (f"{len(gwg)} Arbeitsmittel über der GWG-Grenze als Sofort-Ausgabe gebucht – als Anlagegut (AfA) erfassen: " +
                        ", ".join(f"{b['partner']} {money(b['betrag'])}" for b in gwg[:4])) if gwg else "Keine Arbeitsmittel über der GWG-Grenze offen.",
                       "assets", len(gwg)))

    def bank():
        if not q("SELECT 1 FROM bank_tx LIMIT 1", one=True):
            out.append(_ja(3, "Kontoauszüge", "info", "Keine Bankumsätze im Programm – Abgleich mit dem Konto bitte selbst prüfen.", "bank"))
            return
        mx = q("SELECT MAX(datum) AS d FROM bank_tx", one=True)["d"] or ""
        end = f"{y}-12-31"
        if y < datetime.date.today().year:
            out.append(_ja(3, "Kontoauszüge bis Jahresende", "ok" if mx >= f"{y}-12-24" else "warn",
                           f"Neuester Bankumsatz vom {de_date(mx)}." + ("" if mx >= f"{y}-12-24" else f" Umsätze bis {de_date(end)} einlesen."), "bank"))
        cond = " AND COALESCE(abg,'')=''" if any(r["name"] == "abg" for r in q("PRAGMA table_info(bank_tx)")) else ""
        n = q("SELECT COUNT(*) AS n FROM bank_tx WHERE invoice_id IS NULL AND beleg_id IS NULL AND COALESCE(status,'') IN ('ignore','') "
              "AND substr(datum,1,4)=?" + cond, (ys,), one=True)["n"]
        out.append(_ja(3, "Abgleich", "warn" if n else "ok",
                       f"{n} Bankumsätze aus {y} sind noch nichts zugeordnet." if n else "Alle Bankumsätze sind zugeordnet.", "m71b", n))

    def kasse():
        if not _m99f_tab("m81_kasse") or not q("SELECT 1 FROM m81_kasse WHERE COALESCE(aktiv,1)=1", one=True):
            return
        for k in q("SELECT id, name FROM m81_kasse WHERE COALESCE(aktiv,1)=1"):
            if not q("SELECT 1 FROM m81_buchung WHERE kasse_id=? AND substr(datum,1,4)=? LIMIT 1", (k["id"], ys), one=True):
                continue
            ab = q("SELECT MAX(bis) AS b FROM m81_abschluss WHERE kasse_id=?", (k["id"],), one=True)["b"] or ""
            ok_ = ab >= f"{y}-12-31" or (y == datetime.date.today().year)
            out.append(_ja(4, f"Kassenbuch {k['name']}", "ok" if ok_ else "warn",
                           f"Letzter Kassenabschluss: {de_date(ab) if ab else 'keiner'}." + ("" if ok_ else " Kassensturz zum 31.12. machen."), "m81kasse"))

    def anlagen():
        z = q("SELECT COUNT(*) AS n, COALESCE(SUM(betrag),0) AS s FROM assets WHERE substr(kaufdatum,1,4)=?", (ys,), one=True)
        afa = 0.0
        try:
            afa = round(sum(r.get("afa", 0) or 0 for r in afa_year(y)), 2)
        except Exception:
            afa = 0.0
        out.append(_ja(5, "Anlagen & AfA", "info",
                       f"{z['n']} Zugänge in {y} ({money(z['s'])})" + (f" · AfA {y}: {money(afa)}" if afa else "") + " – Liste unter Anlagen & Inventar prüfen.",
                       "assets", z["n"]))

    def fahrten_gehalt():
        f = q("SELECT COUNT(*) AS n, COALESCE(SUM(km),0) AS km FROM fahrten WHERE substr(datum,1,4)=?", (ys,), one=True)
        out.append(_ja(6, "Fahrten", "info", f"{f['n']} Fahrten · {num_de(f['km'], 0)} km erfasst." if f["n"] else "Keine Fahrten erfasst – stimmt das?", "trips", f["n"]))
        g = {r["m"] for r in q("SELECT DISTINCT substr(datum,6,2) AS m FROM belege WHERE typ='gehalt' AND substr(datum,1,4)=?", (ys,))}
        if g:
            last = 12 if y < datetime.date.today().year else datetime.date.today().month - 1
            fehlt = max(0, last - len(g))
            out.append(_ja(6, "Gehaltsabrechnungen", "warn" if fehlt else "ok",
                           f"{len(g)} Monate erfasst" + (f" – {fehlt} fehlen." if fehlt else "."), "m45jahr", len(g)))

    def ust():
        tc = tax_calc(y)
        if "m80_regel_on" in globals() and m80_ab() and m80_ab()[:4] <= ys:
            out.append(_ja(7, "Umsatzsteuer", "info", f"Regelbesteuerung ab {de_date(m80_ab())} – Voranmeldungen unter Jahresabrechnung & Steuer → UStVA, Jahreserklärung mit diesen Werten.", "tax"))
        else:
            out.append(_ja(7, "Kleinunternehmer-Grenzen", "ok" if tc.get("ku_ok") else "fehler",
                           f"Umsatz {y}: {money(tc.get('umsatz', 0))} · Vorjahr {money(tc.get('umsatz_vj', 0))} (Grenzen 25.000 € Vorjahr / 100.000 € laufend)." +
                           ("" if tc.get("ku_ok") else " Grenze überschritten – Umsatzsteuer prüfen!"), "tax"))
        return tc

    def ergebnis():
        tc = tax_calc(y)
        e = euer(y)
        out.append(_ja(8, "Gewinn (EÜR)", "info", f"Einnahmen {money(e['einnahmen'])} · Ausgaben {money(e['ausgaben'])} · Gewinn {money(e['gewinn'])}.", "tax"))
        c_ = tc.get("calc") or {}
        out.append(_ja(8, "Steuer (geschätzt)", "info",
                       f"Einkommensteuer gesamt {money(c_.get('gesamt', 0))} · bereits gezahlt {money(tc.get('bereits_gezahlt', 0))} · "
                       f"{'Nachzahlung' if (tc.get('differenz') or 0) > 0 else 'Erstattung'} etwa {money(abs(tc.get('differenz') or 0))}.", "tax"))
        sb = q("SELECT COUNT(*) AS n FROM steuerakte WHERE year=? AND (art LIKE '%escheid%' OR titel LIKE '%escheid%')", (y,), one=True)["n"]
        out.append(_ja(8, "Steuerbescheid", "ok" if sb else "info",
                       "Steuerbescheid liegt in der Steuerakte." if sb else "Noch kein Steuerbescheid – kommt er, unter Jahr bearbeiten → Bescheid einfügen.",
                       "m45jahr", sb))

    for fn in (rechnungen, belege, bank, kasse, anlagen, fahrten_gehalt, ust, ergebnis):
        safe(fn)
    elster = {}
    try:
        elster = m79_ausfuell(y) if "m79_ausfuell" in globals() else {}
    except Exception:
        traceback.print_exc()
    done = (get_settings().get("m99f_done") or {}).get(ys) or []
    n_f = sum(1 for p_ in out if p_["status"] == "fehler")
    n_w = sum(1 for p_ in out if p_["status"] == "warn")
    return {"ok": True, "year": y, "punkte": out, "fehler": n_f, "hinweise": n_w, "elster": elster, "erledigt": done,
            "fertig": n_f == 0 and n_w == 0}


def m99f_done(d):
    y = str(int(d["year"]))
    allx = dict(get_settings().get("m99f_done") or {})
    cur = set(allx.get(y) or [])
    s = int(d["schritt"])
    if d.get("an"):
        cur.add(s)
    else:
        cur.discard(s)
    allx[y] = sorted(cur)
    set_setting("m99f_done", allx)
    return {"ok": True, "erledigt": allx[y]}


HOOK_GET["/api/jahresabschluss"] = lambda h, qs: h._send(200, m99f_check(int(qs.get("year") or datetime.date.today().year - 1)))
HOOK_POST["/api/jahresabschluss/erledigt"] = lambda h, d: h._send(200, m99f_done(d))


def m99f_selftest():
    err = []
    try:
        r = m99f_check(datetime.date.today().year)
        if not r["punkte"] or any(p_["schritt"] == 0 for p_ in r["punkte"]):
            err.append("m99f: Prüfung unvollständig: " + "; ".join(p_["text"] for p_ in r["punkte"] if p_["schritt"] == 0)[:300])
        if not {1, 2, 7, 8} <= {p_["schritt"] for p_ in r["punkte"]}:
            err.append("m99f: Schritte fehlen")
        m99f_done({"year": 2000, "schritt": 3, "an": True})
        if 3 not in (get_settings().get("m99f_done") or {}).get("2000", []):
            err.append("m99f: Haken nicht gespeichert")
    except Exception as e:
        err.append(f"m99f Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m99f_selftest)
print(f"INIT m99f_jahresabschluss v{M99F_VERSION}")
