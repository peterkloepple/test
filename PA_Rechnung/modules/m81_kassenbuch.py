# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m81_kassenbuch (v2.0.19)
# Kassenbuch: eine oder mehrere Kassen, Bareinnahmen / Barausgaben / Einlagen / Entnahmen / Geldtransit
# mit laufender Nummer je Kasse, laufendem Bestand (Warnung bei negativem Bestand), Tages-/Monatsabschluss
# mit Zaehlprotokoll (danach nur noch Stornobuchungen), Vorschlaege aus Rechnungen mit Zahlart Bar.
# Doppelzaehlung vermeiden: die EUER rechnet weiter NUR aus Rechnungen und Belegen. Eine Kassenbuchung
#  - Einnahme aus Rechnung   -> verknuepft die Rechnung (setzt sie auf bezahlt), KEIN neuer Beleg
#  - sonstige Bareinnahme    -> legt einen Beleg typ 'einnahme' (quelle 'kasse') an
#  - Barausgabe              -> verknuepft einen vorhandenen Beleg ODER legt einen Beleg typ 'ausgabe' an
#  - Einlage/Entnahme/Transit-> kein Beleg, keine EUER-Wirkung (nur Geldbestand, DATEV ueber m79)
# GoBD: Aenderungen werden ueber m51_log protokolliert; abgeschlossene Buchungen sind gesperrt.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M81_VERSION = "1.0.0"
M81_ARTEN = {"einnahme": ("Einnahme", 1), "ausgabe": ("Ausgabe", -1), "einlage": ("Privateinlage", 1),
             "entnahme": ("Privatentnahme", -1), "bank_kasse": ("Geldtransit Bank → Kasse", 1),
             "kasse_bank": ("Geldtransit Kasse → Bank", -1)}
M81_STUECKE = [500, 200, 100, 50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01]
M81_LOCK = threading.RLock()     # bookings one at a time: running number + "already in the cash book" checks


def _m81_schema():
    x("CREATE TABLE IF NOT EXISTS m81_kasse (id INTEGER PRIMARY KEY, name TEXT, anfang REAL DEFAULT 0, anfang_datum TEXT, "
      "konto INTEGER, aktiv INTEGER DEFAULT 1, notiz TEXT, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS m81_buchung (id INTEGER PRIMARY KEY, kasse_id INTEGER, nr INTEGER, datum TEXT, art TEXT, "
      "vz INTEGER DEFAULT 1, betrag REAL, text TEXT, kategorie TEXT, beleg_id INTEGER, beleg_neu INTEGER DEFAULT 0, "
      "invoice_id INTEGER, inv_bezahlt INTEGER DEFAULT 0, storno_von INTEGER, storniert INTEGER DEFAULT 0, "
      "abschluss_id INTEGER, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS m81_abschluss (id INTEGER PRIMARY KEY, kasse_id INTEGER, bis TEXT, art TEXT, soll REAL, "
      "ist REAL, differenz REAL, zaehl TEXT, notiz TEXT, created TEXT)")
    try:
        x("CREATE INDEX IF NOT EXISTS m81_b_kasse ON m81_buchung(kasse_id, datum)")
        x("CREATE INDEX IF NOT EXISTS m81_b_inv ON m81_buchung(invoice_id)")
        x("CREATE INDEX IF NOT EXISTS m81_b_beleg ON m81_buchung(beleg_id)")
    except Exception:
        pass


HOOK_SCHEMA.append(_m81_schema)


def _m81_log(rid, aktion, alt="", neu="", info=""):
    try:
        m51_log("Kassenbuch", rid, aktion, "kasse", alt, neu, info)
    except Exception:
        pass


def _m81_f(v):
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return float(parse_amount(str(v)))


def m81_kassen():
    ks = q("SELECT * FROM m81_kasse ORDER BY aktiv DESC, id")
    for k in ks:
        k["bestand"] = m81_bestand(k["id"])
        last = q("SELECT bis FROM m81_abschluss WHERE kasse_id=? ORDER BY bis DESC, id DESC LIMIT 1", (k["id"],), one=True)
        k["abgeschlossen_bis"] = last["bis"] if last else ""
    return ks


def m81_kasse_save(d):
    name = (d.get("name") or "").strip() or "Kasse"
    anfang = round(_m81_f(d.get("anfang")), 2)
    ad = (d.get("anfang_datum") or today())[:10]
    konto = int(d["konto"]) if str(d.get("konto") or "").strip().isdigit() else None
    if d.get("id"):
        k = q("SELECT * FROM m81_kasse WHERE id=?", (int(d["id"]),), one=True)
        if not k:
            raise ValueError("Kasse nicht gefunden.")
        has_ab = q("SELECT id FROM m81_abschluss WHERE kasse_id=? LIMIT 1", (k["id"],), one=True)
        if has_ab and (abs(anfang - float(k["anfang"] or 0)) > 0.004 or ad != k["anfang_datum"]):
            raise ValueError("Anfangsbestand kann nach dem ersten Abschluss nicht mehr geändert werden.")
        first = q("SELECT MIN(datum) d FROM m81_buchung WHERE kasse_id=?", (k["id"],), one=True)
        if first and first["d"] and ad > first["d"]:
            raise ValueError(f"Es gibt Buchungen ab {de_date(first['d'])} - der Anfangsbestand muss davor liegen.")
        if anfang < float(k["anfang"] or 0) - 0.004:
            neg = _m81_negative_check(k["id"], anfang=anfang)
            if neg:
                raise ValueError(_m81_neg_msg(neg))
        x("UPDATE m81_kasse SET name=?, anfang=?, anfang_datum=?, konto=?, aktiv=?, notiz=? WHERE id=?",
          (name, anfang, ad, konto, 1 if d.get("aktiv", 1) else 0, d.get("notiz") or "", k["id"]))
        _m81_log(k["id"], "Kasse geändert", f"{k['name']} {k['anfang']}", f"{name} {anfang}")
        return k["id"]
    kid = x("INSERT INTO m81_kasse (name, anfang, anfang_datum, konto, aktiv, notiz, created) VALUES (?,?,?,?,1,?,?)",
            (name, anfang, ad, konto, d.get("notiz") or "", now_iso()))
    _m81_log(kid, "Kasse angelegt", "", f"{name}, Anfangsbestand {money(anfang)} am {de_date(ad)}")
    return kid


def m81_bestand(kid, bis=None):
    k = q("SELECT anfang FROM m81_kasse WHERE id=?", (kid,), one=True)
    if not k:
        return 0.0
    if bis:
        r = q("SELECT COALESCE(SUM(vz*betrag),0) s FROM m81_buchung WHERE kasse_id=? AND datum<=?", (kid, bis), one=True)
    else:
        r = q("SELECT COALESCE(SUM(vz*betrag),0) s FROM m81_buchung WHERE kasse_id=?", (kid,), one=True)
    return round(float(k["anfang"] or 0) + float(r["s"] or 0), 2)


def _m81_last_close(kid):
    r = q("SELECT bis FROM m81_abschluss WHERE kasse_id=? ORDER BY bis DESC LIMIT 1", (kid,), one=True)
    return r["bis"] if r else ""


def _m81_negative_check(kid, bis=None, extra=None, anfang=None):
    """-> first date (up to bis) on which the running balance gets negative, or ''.
    extra: list of (datum, signed amount) of a booking that is about to be made / removed (checked before
    anything is written); anfang: a new opening balance to check"""
    k = q("SELECT anfang FROM m81_kasse WHERE id=?", (kid,), one=True)
    bal = float(anfang if anfang is not None else ((k["anfang"] or 0) if k else 0.0))
    per = {}
    for r in q("SELECT datum, SUM(vz*betrag) s FROM m81_buchung WHERE kasse_id=? GROUP BY datum", (kid,)):
        per[r["datum"]] = per.get(r["datum"], 0.0) + float(r["s"] or 0)
    for d_, v_ in extra or []:
        per[d_] = per.get(d_, 0.0) + float(v_)
    for d_ in sorted(per):
        if bis and d_ > bis:
            break
        bal += per[d_]
        if bal < -0.004:
            return d_
    return ""


def _m81_neg_msg(neg):
    return (f"Der Kassenbestand würde am {de_date(neg)} negativ - eine Kasse kann nicht weniger als 0 € enthalten. "
            "Fehlt eine Einnahme oder Einlage? Bitte zuerst nachbuchen.")


def m81_buchen(d):
    with M81_LOCK:
        return _m81_buchen(d)


def _m81_buchen(d):
    kid = int(d.get("kasse_id") or 0)
    k = q("SELECT * FROM m81_kasse WHERE id=?", (kid,), one=True)
    if not k:
        raise ValueError("Bitte zuerst eine Kasse anlegen.")
    art = d.get("art") or "einnahme"
    if art not in M81_ARTEN:
        raise ValueError("Unbekannte Buchungsart.")
    datum = (d.get("datum") or today())[:10]
    if datum < (k["anfang_datum"] or "0000"):
        raise ValueError(f"Datum liegt vor dem Anfangsbestand der Kasse ({de_date(k['anfang_datum'])}).")
    lc = _m81_last_close(kid)
    if lc and datum <= lc:
        raise ValueError(f"Die Kasse ist bis {de_date(lc)} abgeschlossen - Buchungen nur mit späterem Datum.")
    betrag = round(abs(_m81_f(d.get("betrag"))), 2)
    inv = None
    if d.get("invoice_id"):
        inv = q("SELECT * FROM invoices WHERE id=?", (int(d["invoice_id"]),), one=True)
        if not inv:
            raise ValueError("Rechnung nicht gefunden.")
        if q("SELECT id FROM m81_buchung WHERE invoice_id=? AND storniert=0 AND storno_von IS NULL", (inv["id"],), one=True):
            raise ValueError(f"Rechnung {inv['nr']} ist schon im Kassenbuch.")
        if not betrag:
            betrag = round(abs(float(inv["summe"] or 0)), 2)
            if "m71_state" in globals() and inv["status"] == "offen":
                betrag = round(abs(m71_state(inv)["rest"]), 2) or betrag   # v2.0.19: rest after partial payments
        art = "einnahme" if float(inv["summe"] or 0) >= 0 else "ausgabe"
    if not betrag:
        raise ValueError("Bitte einen Betrag eintragen.")
    if M81_ARTEN[art][1] < 0:
        # checked BEFORE anything is written (payment, receipt): cash can not go below 0
        neg = _m81_negative_check(kid, extra=[(datum, -betrag)])
        if neg:
            raise ValueError(_m81_neg_msg(neg))
    text = (d.get("text") or "").strip()
    kat = d.get("kategorie") or ""
    beleg_id, beleg_neu, inv_paid = None, 0, 0
    if inv:
        text = text or f"Rechnung {inv['nr']} {inv_name(inv)}"
        if inv["status"] == "offen" and "m71_book" in globals():
            # v2.0.19: book through the payment module - partial cash payments count correctly (EUER by payment date)
            r71 = m71_book(inv["id"], datum, betrag, quelle="kasse", notiz=f"Kassenbuch {kid}")
            x("UPDATE invoices SET zahlart='Bar' WHERE id=? AND COALESCE(zahlart,'')=''", (inv["id"],))
            inv_paid = 1 if r71.get("status") == "bezahlt" else 2
        elif inv["status"] == "offen":
            x("UPDATE invoices SET status='bezahlt', bezahlt_am=?, zahlart='Bar', updated=? WHERE id=? AND status='offen'", (datum, now_iso(), inv["id"]))
            try:
                lock_invoice(inv["id"])
            except Exception:
                pass
            inv_paid = 1
    elif art in ("einnahme", "ausgabe"):
        if d.get("beleg_id"):
            b = q("SELECT * FROM belege WHERE id=?", (int(d["beleg_id"]),), one=True)
            if not b:
                raise ValueError("Beleg nicht gefunden.")
            if q("SELECT id FROM m81_buchung WHERE beleg_id=? AND storniert=0 AND storno_von IS NULL", (b["id"],), one=True):
                raise ValueError("Dieser Beleg ist schon im Kassenbuch.")
            beleg_id = b["id"]
            text = text or f"{b['partner'] or ''} {b['nr'] or ''}".strip()
            kat = kat or b["kategorie"] or ""
        else:
            if not text:
                raise ValueError("Bitte einen Buchungstext eintragen.")
            if art == "ausgabe":
                kat = kat or "Sonstige Betriebsausgaben"
            det = {"kasse": kid}
            if art == "einnahme" and "m80_regel_on" in globals() and m80_regel_on(datum):
                # Regelbesteuerung (m80): a cash sale contains USt - gross split by rate (booking value, else the
                # standard rate of m80); UStVA (Kz 81/86), EUER and DATEV read details.ust / ust_satz
                try:
                    sz = float(str(d.get("ust_satz")).replace(",", ".")) if str(d.get("ust_satz") or "").strip() not in ("", "None") \
                        else float(m80_cfg().get("satz") or 19)
                except Exception:
                    raise ValueError("USt-Satz bitte als Zahl (19, 7 oder 0).")
                if sz < 0 or sz >= 100:
                    raise ValueError("USt-Satz bitte als Zahl (19, 7 oder 0).")
                if sz:
                    det["ust"] = round(betrag * sz / (100.0 + sz), 2)
                    det["ust_satz"] = sz
            det = json.dumps(det, ensure_ascii=False)
            beleg_id = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created, quelle) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,'kasse')",
                         (art, datum, (d.get("partner") or text)[:80], d.get("belegnr") or "", betrag,
                          kat if art == "ausgabe" else (kat or ""), f"Kasse: {text}"[:200], d.get("file") or "", det, now_iso()))
            beleg_neu = 1
    else:
        text = text or M81_ARTEN[art][0]
    vz = M81_ARTEN[art][1]
    nr = (q("SELECT COALESCE(MAX(nr),0) n FROM m81_buchung WHERE kasse_id=?", (kid,), one=True)["n"] or 0) + 1
    bid = x("INSERT INTO m81_buchung (kasse_id, nr, datum, art, vz, betrag, text, kategorie, beleg_id, beleg_neu, invoice_id, "
            "inv_bezahlt, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kid, nr, datum, art, vz, betrag, text[:200], kat, beleg_id, beleg_neu, inv["id"] if inv else None, inv_paid, now_iso()))
    _m81_log(bid, "Kassenbuchung", "", f"Nr. {nr} {de_date(datum)} {M81_ARTEN[art][0]} {money(vz * betrag)} {text}")
    neg = _m81_negative_check(kid)
    return {"ok": True, "id": bid, "nr": nr, "bestand": m81_bestand(kid),
            "warn": (f"Achtung: Der Kassenbestand wird am {de_date(neg)} negativ - eine Kasse kann nicht weniger als 0 € enthalten. "
                     "Fehlt eine Einnahme oder Einlage?") if neg else ""}


def _m81_undo_payment(b):
    """v2.0.19: take back the payment this cash booking made on an invoice (m71 row or plain 'bezahlt')"""
    if not (b["invoice_id"] and b["inv_bezahlt"]):
        return
    if "m71_delete" in globals():
        r = q("SELECT id FROM m71_zahlung WHERE invoice_id=? AND quelle='kasse' AND datum=? AND abs(abs(betrag)-?)<0.005 "
              "ORDER BY id DESC LIMIT 1", (b["invoice_id"], b["datum"], abs(float(b["betrag"] or 0))), one=True)
        if r:
            m71_delete(r["id"])
            return
    x("UPDATE invoices SET status='offen', bezahlt_am='', updated=? WHERE id=? AND status='bezahlt'", (now_iso(), b["invoice_id"]))


def m81_loeschen(bid):
    with M81_LOCK:
        return _m81_loeschen(bid)


def _m81_loeschen(bid):
    b = q("SELECT * FROM m81_buchung WHERE id=?", (int(bid),), one=True)
    if not b:
        return {"ok": True}
    if b["abschluss_id"]:
        raise ValueError("Diese Buchung ist abgeschlossen - bitte stornieren statt löschen.")
    if q("SELECT id FROM m81_buchung WHERE storno_von=?", (b["id"],), one=True):
        raise ValueError("Zu dieser Buchung gibt es eine Stornobuchung - zuerst die Stornobuchung löschen.")
    if b["storno_von"]:
        o = q("SELECT invoice_id, inv_bezahlt FROM m81_buchung WHERE id=?", (b["storno_von"],), one=True)
        if o and o["invoice_id"] and o["inv_bezahlt"]:
            # the cancellation took back the payment of the invoice - deleting it would revive the cash booking
            # while the invoice stays open
            raise ValueError("Diese Stornobuchung hat die Zahlung der Rechnung zurückgenommen und kann nicht gelöscht werden. "
                             "Wurde die Rechnung doch bar bezahlt, bitte die Rechnung neu im Kassenbuch buchen.")
    if int(b["vz"]) > 0:
        # removing money from the cash book must not make the balance negative
        neg = _m81_negative_check(b["kasse_id"], extra=[(b["datum"], -float(b["betrag"] or 0))])
        if neg:
            raise ValueError(_m81_neg_msg(neg))
    if b["beleg_neu"] and b["beleg_id"]:
        x("DELETE FROM belege WHERE id=?", (b["beleg_id"],))
    if b["inv_bezahlt"] and b["invoice_id"]:
        _m81_undo_payment(b)
        try:
            x("UPDATE invoices SET locked=0 WHERE id=? AND COALESCE(versendet_am,'')=''", (b["invoice_id"],))
        except Exception:
            pass
    if b["storno_von"]:
        x("UPDATE m81_buchung SET storniert=0 WHERE id=?", (b["storno_von"],))
    x("DELETE FROM m81_buchung WHERE id=?", (b["id"],))
    _m81_log(b["id"], "Kassenbuchung gelöscht", f"Nr. {b['nr']} {de_date(b['datum'])} {money(b['vz'] * b['betrag'])} {b['text']}", "")
    return {"ok": True, "bestand": m81_bestand(b["kasse_id"])}


def m81_storno(bid, datum=None):
    with M81_LOCK:
        return _m81_storno(bid, datum)


def _m81_storno(bid, datum=None):
    b = q("SELECT * FROM m81_buchung WHERE id=?", (int(bid),), one=True)
    if not b:
        raise ValueError("Buchung nicht gefunden.")
    if b["storno_von"]:
        raise ValueError("Eine Stornobuchung kann nicht storniert werden.")
    if b["storniert"]:
        raise ValueError("Die Buchung ist schon storniert.")
    datum = (datum or today())[:10]
    lc = _m81_last_close(b["kasse_id"])
    if lc and datum <= lc:
        datum = (datetime.date.fromisoformat(lc) + datetime.timedelta(days=1)).isoformat()
    if int(b["vz"]) > 0:
        # cancelling an income takes money out of the cash book
        neg = _m81_negative_check(b["kasse_id"], extra=[(datum, -float(b["betrag"] or 0))])
        if neg:
            raise ValueError(_m81_neg_msg(neg))
    beleg_id = None
    if b["beleg_id"]:
        ob = q("SELECT * FROM belege WHERE id=?", (b["beleg_id"],), one=True)
        if ob and b["beleg_neu"]:
            det = {"kasse": b["kasse_id"], "storno_von": ob["id"]}
            try:
                odet = json.loads(ob["details"] or "{}")
            except Exception:
                odet = {}
            if isinstance(odet, dict):
                # the cancellation reverses Vorsteuer / USt of the original as well (UStVA Kz 66 / 81 / 86, EUER)
                for k_ in ("vorsteuer", "ust"):
                    try:
                        if odet.get(k_) not in (None, "") and float(odet[k_]):
                            det[k_] = -round(float(odet[k_]), 2)
                    except Exception:
                        pass
                if odet.get("ust_satz") not in (None, ""):
                    det["ust_satz"] = odet["ust_satz"]
                if "vorsteuer" in det:
                    det["vorsteuer_quelle"] = "Storno Kasse"
            beleg_id = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created, quelle) "
                         "VALUES (?,?,?,?,?,?,?,'',?,?,'kasse')",
                         (ob["typ"], datum, ob["partner"], ob["nr"], -float(ob["betrag"] or 0), ob["kategorie"],
                          f"Storno Kasse Nr. {b['nr']}", json.dumps(det, ensure_ascii=False), now_iso()))
    if b["invoice_id"] and b["inv_bezahlt"]:
        _m81_undo_payment(b)
    nr = (q("SELECT COALESCE(MAX(nr),0) n FROM m81_buchung WHERE kasse_id=?", (b["kasse_id"],), one=True)["n"] or 0) + 1
    sid = x("INSERT INTO m81_buchung (kasse_id, nr, datum, art, vz, betrag, text, kategorie, beleg_id, beleg_neu, invoice_id, "
            "inv_bezahlt, storno_von, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
            (b["kasse_id"], nr, datum, b["art"], -int(b["vz"]), b["betrag"], f"Storno Nr. {b['nr']}: {b['text']}"[:200], b["kategorie"],
             beleg_id, 1 if beleg_id else 0, None, b["id"], now_iso()))
    x("UPDATE m81_buchung SET storniert=1 WHERE id=?", (b["id"],))
    _m81_log(sid, "Kassenbuchung storniert", f"Nr. {b['nr']}", f"Storno Nr. {nr} am {de_date(datum)}")
    return {"ok": True, "id": sid, "nr": nr, "bestand": m81_bestand(b["kasse_id"]), "warn": ""}


def m81_abschluss(d):
    with M81_LOCK:
        return _m81_abschluss(d)


def _m81_abschluss(d):
    kid = int(d.get("kasse_id") or 0)
    k = q("SELECT * FROM m81_kasse WHERE id=?", (kid,), one=True)
    if not k:
        raise ValueError("Kasse nicht gefunden.")
    bis = (d.get("bis") or today())[:10]
    if bis > today():
        raise ValueError("Abschluss nur bis heute möglich.")
    lc = _m81_last_close(kid)
    if lc and bis <= lc:
        raise ValueError(f"Bis {de_date(lc)} ist schon abgeschlossen.")
    neg = _m81_negative_check(kid, bis)
    if neg:
        raise ValueError(f"Der Kassenbestand ist am {de_date(neg)} negativ - so kann die Kasse nicht abgeschlossen werden. "
                         "Bitte die fehlende Einnahme oder Einlage nachbuchen (oder die falsche Ausgabe korrigieren).")
    zaehl = d.get("zaehl") or {}
    if not isinstance(zaehl, dict):
        zaehl = {}
    ist = None
    if zaehl:
        ist = round(sum(float(st) * int(zaehl.get(str(st)) or zaehl.get(f"{st:g}") or 0) for st in M81_STUECKE), 2)
    elif str(d.get("ist") or "").strip():
        ist = round(_m81_f(d.get("ist")), 2)
    soll = m81_bestand(kid, bis)
    diff = round((ist - soll), 2) if ist is not None else 0.0
    if abs(diff) >= 0.005 and d.get("differenz_buchen"):
        # Kassendifferenz: booked on the closing day before the lock
        art = "einnahme" if diff > 0 else "ausgabe"
        m81_buchen({"kasse_id": kid, "art": art, "datum": bis, "betrag": abs(diff), "text": "Kassendifferenz laut Zählprotokoll",
                    "kategorie": "Sonstige Betriebsausgaben" if art == "ausgabe" else ""})
        soll = m81_bestand(kid, bis)
        diff = round((ist - soll), 2)
    aid = x("INSERT INTO m81_abschluss (kasse_id, bis, art, soll, ist, differenz, zaehl, notiz, created) VALUES (?,?,?,?,?,?,?,?,?)",
            (kid, bis, d.get("art") or "tag", soll, ist, diff, json.dumps(zaehl), d.get("notiz") or "", now_iso()))
    n = q("SELECT COUNT(*) n FROM m81_buchung WHERE kasse_id=? AND datum<=? AND abschluss_id IS NULL", (kid, bis), one=True)["n"]
    x("UPDATE m81_buchung SET abschluss_id=? WHERE kasse_id=? AND datum<=? AND abschluss_id IS NULL", (aid, kid, bis))
    _m81_log(aid, "Kassenabschluss", "", f"bis {de_date(bis)}: Soll {money(soll)}, gezählt {money(ist) if ist is not None else '-'}, "
                                          f"Differenz {money(diff)}, {n} Buchungen festgeschrieben")
    return {"ok": True, "id": aid, "soll": soll, "ist": ist, "differenz": diff, "buchungen": n, "warn": ""}


def m81_vorschlaege(kid=None):
    """cash invoices (Zahlart Bar) not yet in the cash book"""
    k = q("SELECT * FROM m81_kasse WHERE id=?", (kid,), one=True) if kid else q("SELECT * FROM m81_kasse WHERE aktiv=1 ORDER BY id LIMIT 1", one=True)
    if not k:
        return []
    start = max(k["anfang_datum"] or "0000", _m81_last_close(k["id"]) or "0000")
    out = []
    # v2.1.0: a cancellation always carries zahlart 'Bar' (m02) - it is a cash refund only when the original was paid in cash
    # (before, the refund of every bank-paid invoice was offered as a cash book entry)
    for r in q("SELECT id, nr, datum, summe, status, bezahlt_am, customer_id, kdnr, addr, typ FROM invoices i WHERE typ IN ('rechnung','storno') "
               "AND zahlart='Bar' AND (typ='rechnung' OR COALESCE(ref_id,0)=0 OR "
               "COALESCE((SELECT o.zahlart FROM invoices o WHERE o.id=i.ref_id),'Bar')='Bar') "
               "AND status IN ('offen','bezahlt') AND id NOT IN (SELECT invoice_id FROM m81_buchung WHERE invoice_id IS NOT NULL "
               "AND storniert=0 AND storno_von IS NULL) "
               "ORDER BY datum DESC LIMIT 200"):
        d_ = (r["bezahlt_am"] or r["datum"] or "")[:10] if r["status"] == "bezahlt" else today()
        if d_ <= start:
            continue
        bt_ = r["summe"]
        if r["status"] == "offen" and "m71_state" in globals():
            try:
                bt_ = m71_state(r["id"])["rest"] if float(r["summe"] or 0) >= 0 else r["summe"]
            except Exception:
                pass
        out.append({"invoice_id": r["id"], "nr": r["nr"], "datum": d_, "betrag": bt_, "status": r["status"],
                    "name": inv_name(r), "typ": r["typ"]})
    return out


def m81_list(kid, von=None, bis=None):
    k = q("SELECT * FROM m81_kasse WHERE id=?", (kid,), one=True)
    if not k:
        return {"kasse": None, "rows": []}
    von = (von or "0000-01-01")[:10]
    bis = (bis or "9999-12-31")[:10]
    start_bal = m81_bestand(kid, (datetime.date.fromisoformat(von) - datetime.timedelta(days=1)).isoformat()) if von > "0001" else float(k["anfang"] or 0)
    if von <= (k["anfang_datum"] or ""):
        start_bal = float(k["anfang"] or 0)
    rows = q("SELECT b.*, i.nr inv_nr, l.file beleg_file, l.partner beleg_partner FROM m81_buchung b LEFT JOIN invoices i ON i.id=b.invoice_id "
             "LEFT JOIN belege l ON l.id=b.beleg_id WHERE b.kasse_id=? AND b.datum BETWEEN ? AND ? ORDER BY b.datum, b.nr", (kid, von, bis))
    bal = start_bal
    ein = aus = 0.0
    for r in rows:
        v = int(r["vz"]) * float(r["betrag"] or 0)
        bal = round(bal + v, 2)
        r["wert"] = round(v, 2)
        r["bestand"] = bal
        r["negativ"] = bal < -0.004
        r["art_label"] = M81_ARTEN.get(r["art"], (r["art"], 1))[0]
        r["gesperrt"] = bool(r["abschluss_id"])
        if v > 0:
            ein += v
        else:
            aus += -v
    return {"kasse": k, "von": von, "bis": bis, "anfang": round(start_bal, 2), "ende": round(bal, 2), "ein": round(ein, 2), "aus": round(aus, 2),
            "rows": rows}


def m81_links():
    """for m79 DATEV: ({beleg_id: kasse_id}, {invoice_id: kasse_id}, {kasse_id: account or None})"""
    kb, ki = {}, {}
    for r in q("SELECT kasse_id, beleg_id, invoice_id, beleg_neu, storniert, storno_von FROM m81_buchung"):
        # a cancelled link to an existing receipt / invoice means: not paid in cash -> not on the cash account
        if (r["storniert"] or r["storno_von"]) and not r["beleg_neu"]:
            continue
        if r["beleg_id"]:
            kb[r["beleg_id"]] = r["kasse_id"]
        if r["invoice_id"]:
            ki[r["invoice_id"]] = r["kasse_id"]
    kk = {r["id"]: r["konto"] for r in q("SELECT id, konto FROM m81_kasse")}
    return kb, ki, kk


def m81_datev_extra(von, bis, K):
    """for m79: Einlage / Entnahme / Transit as DATEV rows (args of add())"""
    out = []
    kk = {r["id"]: (r["konto"] or K["_kasse"]) for r in q("SELECT id, konto FROM m81_kasse")}
    for r in q("SELECT * FROM m81_buchung WHERE art IN ('einlage','entnahme','bank_kasse','kasse_bank') AND datum BETWEEN ? AND ? ORDER BY datum, nr", (von, bis)):
        ka = kk.get(r["kasse_id"], K["_kasse"])
        amt = float(r["betrag"] or 0) * (1 if int(r["vz"]) == M81_ARTEN[r["art"]][1] else -1)
        konto, gegen = {"einlage": (ka, K["_privat_ein"]), "entnahme": (K["_privat_ent"], ka),
                        "bank_kasse": (ka, K["_bank"]), "kasse_bank": (K["_bank"], ka)}[r["art"]]
        out.append((r["datum"], amt, "S", konto, gegen, r["text"], f"K{r['kasse_id']}-{r['nr']}", "", "", "Kasse", r["id"]))
    return out


def m81_boot(d):
    try:
        ks = q("SELECT id FROM m81_kasse WHERE aktiv=1", ())
        d["m81"] = {"kassen": len(ks), "vorschlaege": len(m81_vorschlaege()) if ks else 0}
    except Exception:
        d["m81"] = {"kassen": 0, "vorschlaege": 0}


HOOK_BOOT.append(m81_boot)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def m81_route_data(h, qs):
    ks = m81_kassen()
    kid = int(qs.get("kasse") or 0) or (ks[0]["id"] if ks else 0)
    lst = m81_list(kid, qs.get("von"), qs.get("bis")) if kid else {"kasse": None, "rows": []}
    ab = q("SELECT * FROM m81_abschluss WHERE kasse_id=? ORDER BY bis DESC, id DESC LIMIT 60", (kid,)) if kid else []
    return h._send(200, {"kassen": ks, "kasse_id": kid, "liste": lst, "abschluesse": ab, "vorschlaege": m81_vorschlaege(kid) if kid else [],
                         "arten": {k: v[0] for k, v in M81_ARTEN.items()}, "kategorien": EUER_KATEGORIEN, "stuecke": M81_STUECKE,
                         "heute": today(), "bestand_heute": m81_bestand(kid) if kid else 0.0,
                         "abgeschlossen_bis": _m81_last_close(kid) if kid else ""})


def m81_route_kasse(h, d):
    kid = m81_kasse_save(d)
    return h._send(200, {"ok": True, "id": kid})


def m81_route_buchen(h, d):
    return h._send(200, m81_buchen(d))


def m81_route_uebernehmen(h, d):
    kid = int(d.get("kasse_id") or 0)
    with M81_LOCK:
        res = _m81_uebernehmen(kid, d.get("ids") or [])
    return h._send(200, res)


def _m81_uebernehmen(kid, ids):
    n, warn = 0, ""
    for iid in ids:
        v = next((r for r in m81_vorschlaege(kid) if r["invoice_id"] == int(iid)), None)
        if not v:
            continue
        r = m81_buchen({"kasse_id": kid, "invoice_id": v["invoice_id"], "datum": v["datum"], "betrag": abs(float(v["betrag"] or 0))})
        n += 1
        warn = r.get("warn") or warn
    return {"ok": True, "n": n, "warn": warn}


def m81_route_del(h, d):
    ids = d.get("ids") or ([d["id"]] if d.get("id") else [])
    res = {"ok": True}
    for i in ids:
        res = m81_loeschen(i)
    return h._send(200, res)


def m81_route_storno(h, d):
    return h._send(200, m81_storno(d["id"], d.get("datum")))


def m81_route_abschluss(h, d):
    return h._send(200, m81_abschluss(d))


def m81_route_belege(h, qs):
    """open cash receipts that can be linked (not yet in the cash book, not from the bank)"""
    rows = q("SELECT id, typ, datum, partner, nr, betrag, kategorie FROM belege WHERE typ IN ('ausgabe','einnahme') "
             "AND COALESCE(quelle,'') NOT IN ('bank','kasse') AND id NOT IN (SELECT beleg_id FROM m81_buchung WHERE beleg_id IS NOT NULL) "
             "ORDER BY datum DESC LIMIT 300")
    return h._send(200, {"rows": rows})


HOOK_GET["/api/m81/data"] = m81_route_data
HOOK_GET["/api/m81/belege"] = m81_route_belege
HOOK_POST["/api/m81/kasse"] = m81_route_kasse
HOOK_POST["/api/m81/buchen"] = m81_route_buchen
HOOK_POST["/api/m81/uebernehmen"] = m81_route_uebernehmen
HOOK_POST["/api/m81/del"] = m81_route_del
HOOK_POST["/api/m81/storno"] = m81_route_storno
HOOK_POST["/api/m81/abschluss"] = m81_route_abschluss

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _m81_ex(p):
    ks = q("SELECT * FROM m81_kasse ORDER BY id")
    kid = int(p.get("kasse") or 0) or (ks[0]["id"] if ks else 0)
    if not kid:
        return [_sh("Kassenbuch", [("Hinweis", "t", 60)], [["Noch keine Kasse angelegt."]], "", False)]
    von, bis = p.get("von") or "", p.get("bis") or ""
    lst = m81_list(kid, von or None, bis or None)
    ids = {int(i) for i in (p.get("ids") or []) if str(i).isdigit()}
    rows = [r for r in lst["rows"] if not ids or r["id"] in ids]
    k = lst["kasse"]
    sub = (f"{de_date(lst['von'])} - {de_date(lst['bis'])}" if von else "alle Buchungen") + \
          f" · Anfangsbestand {money(lst['anfang'])} · Endbestand {money(lst['ende'])}"
    out = [_sh(f"Kassenbuch {k['name']}", [("Nr.", "t", 6), ("Datum", "d", 11), ("Art", "t", 16), ("Text", "t", 40), ("Einnahme", "m", 12),
                                            ("Ausgabe", "m", 12), ("Bestand", "m", 13), ("Kategorie", "t", 22), ("Beleg/Rechnung", "t", 16)],
               [[str(r["nr"]), r["datum"], r["art_label"] + (" (Storno)" if r["storno_von"] else ""), r["text"] or "",
                 r["wert"] if r["wert"] > 0 else 0, -r["wert"] if r["wert"] < 0 else 0, r["bestand"], r["kategorie"] or "",
                 r["inv_nr"] or (f"Beleg {r['beleg_id']}" if r["beleg_id"] else "")] for r in rows], sub, False)]
    ab = q("SELECT * FROM m81_abschluss WHERE kasse_id=? ORDER BY bis", (kid,))
    if ab and not ids:
        out.append(_sh("Abschlüsse / Zählprotokolle", [("Bis", "d", 11), ("Art", "t", 10), ("Soll", "m", 13), ("Gezählt", "m", 13),
                                                         ("Differenz", "m", 12), ("Notiz", "t", 40)],
                       [[a["bis"], "Monat" if a["art"] == "monat" else "Tag", a["soll"], a["ist"] if a["ist"] is not None else "", a["differenz"],
                         a["notiz"] or ""] for a in ab], "", False))
    return out


EXPORTS["m81_kasse"] = ("Kassenbuch", _m81_ex)

# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------


def m81_selftest():
    err = []
    kid = None
    try:
        y = datetime.date.today()
        d0 = (y - datetime.timedelta(days=10)).isoformat()
        e_before = euer(y.year)["gewinn"] if d0[:4] == str(y.year) else None
        kid = m81_kasse_save({"name": "_ST_M81", "anfang": "100,00", "anfang_datum": d0})
        r1 = m81_buchen({"kasse_id": kid, "art": "einnahme", "datum": d0, "betrag": "50", "text": "Barverkauf Test"})
        r2 = m81_buchen({"kasse_id": kid, "art": "ausgabe", "datum": d0, "betrag": "20,50", "text": "Porto", "kategorie": "Bürobedarf / Porto"})
        m81_buchen({"kasse_id": kid, "art": "kasse_bank", "datum": d0, "betrag": "100", "text": "Einzahlung Bank"})
        if abs(m81_bestand(kid) - 29.5) > 0.001:
            err.append(f"m81: Bestand {m81_bestand(kid)} statt 29,50")
        if e_before is not None:
            g = euer(y.year)["gewinn"]
            if abs((g - e_before) - 29.5) > 0.01:
                err.append(f"m81: EÜR-Wirkung {g - e_before:.2f} statt 29,50 (Transit darf nicht zählen)")
        try:
            m81_buchen({"kasse_id": kid, "art": "entnahme", "datum": d0, "betrag": "40", "text": "Test"})
            err.append("m81: Buchung mit negativem Bestand wurde angenommen")
        except ValueError:
            pass
        if abs(m81_bestand(kid) - 29.5) > 0.001:
            err.append(f"m81: abgelehnte Buchung hat den Bestand geändert ({m81_bestand(kid)})")
        a = m81_abschluss({"kasse_id": kid, "bis": d0, "zaehl": {"20": 1, "5": 1, "2": 2, "0.5": 1}})
        if abs(a["soll"] - 29.5) > 0.001 or abs(a["differenz"]) > 0.001:
            err.append(f"m81: Abschluss Soll {a['soll']} / Diff {a['differenz']}")
        try:
            m81_loeschen(r1["id"])
            err.append("m81: abgeschlossene Buchung ließ sich löschen")
        except ValueError:
            pass
        m81_storno(r2["id"])
        if abs(m81_bestand(kid) - 50.0) > 0.001:
            err.append(f"m81: Bestand nach Storno {m81_bestand(kid)} statt 50,00")
        if e_before is not None:
            g = euer(y.year)["gewinn"]
            if abs((g - e_before) - 50.0) > 0.01:
                err.append(f"m81: EÜR nach Storno {g - e_before:.2f} statt 50,00")
        ex = _m81_ex({"kasse": kid})
        if not ex or len(ex[0]["rows"]) != 4:
            err.append("m81: Export unvollständig")
        if "m79_bookings" in globals():
            dv = [r for r in m79_bookings(d0, today()) if r["quelle"] in ("Kasse",)]
            if not dv:
                err.append("m81: Geldtransit fehlt im DATEV-Export")
    except Exception as e:
        traceback.print_exc()
        err.append(f"m81 Ausnahme: {e}")
    finally:
        try:
            if kid:
                for b in q("SELECT beleg_id FROM m81_buchung WHERE kasse_id=? AND beleg_neu=1", (kid,)):
                    x("DELETE FROM belege WHERE id=?", (b["beleg_id"],))
                x("DELETE FROM m81_buchung WHERE kasse_id=?", (kid,))
                x("DELETE FROM m81_abschluss WHERE kasse_id=?", (kid,))
                x("DELETE FROM m81_kasse WHERE id=?", (kid,))
        except Exception:
            pass
    return err


HOOK_SELFTEST.append(m81_selftest)


# ---------------------------------------------------------------------------
# v2.0.19: a receipt that is part of the cash book cannot be deleted under "Belege"
# (the cash book would keep counting it, the EUER not) - delete/storno it in the cash book
# ---------------------------------------------------------------------------
def _m81_beleg_in_kasse(bid):
    try:
        return q("SELECT b.nr, b.abschluss_id, k.name FROM m81_buchung b LEFT JOIN m81_kasse k ON k.id=b.kasse_id "
                 "WHERE b.beleg_id=? AND b.storniert=0 AND b.storno_von IS NULL LIMIT 1", (int(bid),), one=True)
    except Exception:
        return None


def _m81_beleg_msg(r):
    return (f"Dieser Beleg steht im Kassenbuch ({r['name'] or 'Kasse'}, Nr. {r['nr']}) - bitte dort "
            + ("stornieren (Kasse ist abgeschlossen)." if r["abschluss_id"] else "löschen oder stornieren."))


def _m81_beleg_closed(bid):
    """booking of a CLOSED cash period that uses this receipt (also cancelled ones and cancellation receipts)"""
    try:
        return q("SELECT b.nr, b.abschluss_id, k.name FROM m81_buchung b LEFT JOIN m81_kasse k ON k.id=b.kasse_id "
                 "WHERE b.beleg_id=? AND b.abschluss_id IS NOT NULL LIMIT 1", (int(bid),), one=True)
    except Exception:
        return None


def _m81_closed_msg(r):
    return (f"Dieser Beleg gehört zu einem abgeschlossenen Kassenzeitraum ({r['name'] or 'Kasse'}, Nr. {r['nr']}) und kann "
            "nicht mehr geändert werden. Korrekturen bitte als Stornobuchung im Kassenbuch.")


def _m81_beleg_block(bid, aenderung=True):
    """-> error text or '' . aenderung: amount / date / type would change (or the receipt is deleted)"""
    r = _m81_beleg_closed(bid)
    if r:
        return _m81_closed_msg(r)
    if aenderung:
        r = _m81_beleg_in_kasse(bid)
        if r:
            return _m81_beleg_msg(r)
    return ""


def _m81_route_beleg_delete(h, d):
    msg = _m81_beleg_block(d.get("id") or 0)
    if msg:
        return h._send(200, {"ok": False, "error": msg})
    x("DELETE FROM belege WHERE id=?", (d["id"],))
    return h._send(200, {"ok": True})


HOOK_POST["/api/beleg/delete"] = _m81_route_beleg_delete


def _m81_route_beleg_update(h, d):
    """receipts of a closed cash period stay unchanged (GoBD); a receipt of an open cash booking keeps amount,
    date and type (the cash book holds a copy) - everything else goes on to the normal handler (m19)"""
    try:
        bid = int(d.get("id") or 0)
    except Exception:
        bid = 0
    if bid:
        old = q("SELECT typ, datum, betrag FROM belege WHERE id=?", (bid,), one=True)
        try:
            nb = float(d.get("betrag") or 0)        # same conversion as the m19 handler
        except Exception:
            nb = _m81_f(d.get("betrag"))
        chg = bool(old) and ((d.get("typ") or "") != (old["typ"] or "") or str(d.get("datum") or "")[:10] != (old["datum"] or "")[:10]
                             or abs(nb - float(old["betrag"] or 0)) > 0.004)
        msg = _m81_beleg_block(bid, chg)
        if msg:
            return h._send(200, {"ok": False, "error": msg})
    return None     # None: ext_post falls through to the original route in m19


HOOK_POST["/api/beleg/update"] = _m81_route_beleg_update

@chain_step("bulk_action", "m81_kassenbuch")
def _m81_step_bulk_action(_next, d):
    act = (d or {}).get("action")
    if (d or {}).get("kind") == "beleg" and act in ("delete", "kategorie", "typ", "datum"):
        keep, msgs = [], []
        for i in d.get("ids") or []:
            try:
                msg = _m81_beleg_block(i, act in ("delete", "typ", "datum"))
            except Exception:
                msg = ""
            if msg:
                msgs.append(msg)
            else:
                keep.append(i)
        if msgs:
            res = _next(dict(d, ids=keep)) if keep else {"ok": True, "done": 0, "skipped": 0, "errors": []}
            if isinstance(res, dict):
                res = dict(res)
                res["skipped"] = int(res.get("skipped") or 0) + len(msgs)
                res["errors"] = list(res.get("errors") or []) + [
                    f"{len(msgs)} Beleg(e) stehen im Kassenbuch und wurden nicht geändert - bitte dort löschen oder stornieren."]
            return res
    return _next(d)
