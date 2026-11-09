# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m07_bank
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ---------------- Bank CSV ----------------


def _decode(data):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", "replace")


def _iso_any(v):
    v = (v or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", v):
        d_ = d_iso(v)       # v2.6.3: "2025-02-30" is no date
        return d_.isoformat() if d_ else ""
    return iso_from_de(v)


def parse_bank_csv(data):
    text = _decode(data)
    delim = ";" if text.count(";") >= text.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    hi = None
    for i, r in enumerate(rows[:60]):
        low = [c.strip().lower() for c in r]
        # v2.1.0: the head line needs a date column and a DIFFERENT amount column and holds no values -
        # ING starts with "Umsatzanzeige;Datei erstellt am: 27.10.2026", which was taken as head line
        # before (amounts became the booking date as number, e.g. 27102026 EUR)
        if any(re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{2}-\d{2}", c) for c in low):
            continue
        ia = {j for j, c in enumerate(low) if re.search(r"betrag|umsatz|amount|soll|haben", c)}
        idt = {j for j, c in enumerate(low) if re.search(r"datum|buchung|valuta|wertstellung|\bdate\b|tag", c)}
        if ia and idt and (len(ia | idt) >= 2):
            hi = i
            break
    if hi is None:
        raise ValueError("Kopfzeile der CSV nicht erkannt (Spalten Datum und Betrag erwartet).")
    head = [c.strip().lower() for c in rows[hi]]

    def col(*pats, avoid=()):
        for pat in pats:
            for i, h in enumerate(head):
                if re.search(pat, h) and not any(re.search(a, h) for a in avoid):
                    return i
        return None
    c_dat = col(r"buchungsdatum|buchungstag|^buchung$", r"^datum$|datum", r"valuta|wertstellung", r"date")
    c_amt = col(r"^betrag|betrag \(eur\)|betrag$", r"umsatz", r"amount", avoid=(r"saldo", r"ursprung"))
    c_soll = col(r"^soll|soll") if c_amt is None else None
    c_haben = col(r"^haben|haben") if c_amt is None else None
    c_name = col(r"zahlungspflichtige|auftraggeber|empf[aä]nger|beg[uü]nstigt|gegenkonto.*name|^name|name", avoid=(r"bank",))
    c_zweck = col(r"verwendungszweck", r"beschreibung", r"zweck", r"buchungstext", r"vorgang", r"text")
    c_iban = col(r"iban", r"kontonummer")
    # v2.1.0: separate payer / payee columns (DKB: "Zahlungspflichtige*r" + "Zahlungsempfaenger*in") - for an
    # outgoing payment the payee is the partner, not the own name in the payer column
    pay_re, emp_re = r"zahlungspflichtig|auftraggeber", r"empf[aä]nger|beg[uü]nstigt"
    c_pay = col(pay_re, avoid=(r"bank", emp_re))
    c_emp = col(emp_re, avoid=(r"bank", pay_re))
    dual = c_pay is not None and c_emp is not None and c_pay != c_emp
    out = []
    seen = {}
    for r in rows[hi + 1:]:
        if not r or len(r) < 2:
            continue
        get = lambda i: (r[i].strip() if i is not None and i < len(r) else "")
        dat = _iso_any(get(c_dat))
        if not dat:
            continue
        try:
            if c_amt is not None:
                amt = parse_amount(get(c_amt))
            else:
                amt = (parse_amount(get(c_haben)) if get(c_haben) else 0.0) - (parse_amount(get(c_soll)) if get(c_soll) else 0.0)
        except Exception:
            continue
        name, zweck, iban = get(c_name), get(c_zweck), get(c_iban)
        # duplicate key keeps the former name column, so statements imported before stay recognised
        key = f"{dat}|{amt:.2f}|{name}|{zweck}"
        if dual:
            name = (get(c_emp) if amt < 0 else get(c_pay)) or name
        seen[key] = seen.get(key, 0) + 1
        h = hashlib.sha1(f"{key}|{seen[key]}".encode("utf-8")).hexdigest()
        out.append({"hash": h, "datum": dat, "betrag": round(amt, 2), "name": name, "zweck": zweck, "iban": iban})
    return out


def bank_suggest(txs):
    open_ = q("SELECT * FROM invoices WHERE typ IN ('rechnung','storno') AND status='offen'")
    known = {r["hash"] for r in q("SELECT hash FROM bank_tx")}
    res = []
    for t in txs:
        t["neu"] = t["hash"] not in known
        t["vorschlag"] = None
        t["sicher"] = 0
        # whole tokens only: "2026-011" must not hit a date "15.01.2026" or an EREF "20260115-4711"
        # (the old substring match on the stripped text proposed the wrong invoice as paid)
        toks_ = {re.sub(r"[^0-9a-z]", "", w) for w in re.split(r"[\s,;:()]+", (t["zweck"] + " " + t["name"]).lower())}
        toks_.discard("")
        if t["betrag"] > 0:
            best, score = None, 0
            for inv in open_:
                sc = 0
                nrn = re.sub(r"[^0-9a-z]", "", (inv["nr"] or "").lower())
                if nrn and len(nrn) >= 4 and nrn in toks_:
                    sc += 3
                if abs(inv["summe"] - t["betrag"]) < 0.005:
                    sc += 1
                    nm = inv_name(inv).lower()
                    toks = [w for w in re.split(r"\W+", nm) if len(w) > 3]
                    if toks and any(w in (t["name"] + " " + t["zweck"]).lower() for w in toks):
                        sc += 1
                if sc > score:
                    best, score = inv, sc
            if best and score >= 2:
                t["vorschlag"], t["sicher"] = {"id": best["id"], "nr": best["nr"], "name": inv_name(best), "summe": best["summe"]}, score
            elif best and score == 1 and sum(1 for i in open_ if abs(i["summe"] - t["betrag"]) < 0.005) == 1:
                t["vorschlag"], t["sicher"] = {"id": best["id"], "nr": best["nr"], "name": inv_name(best), "summe": best["summe"]}, 1
            # "paid" is only proposed when the amount matches - a number hit alone stays a hint (partial payment?)
            amt_ok = bool(t["vorschlag"]) and abs(float(t["vorschlag"]["summe"] or 0) - t["betrag"]) < 0.005
            t["aktion"] = "paid" if amt_ok else "ignore"
            if t["vorschlag"] and not amt_ok:
                t["hinweis"] = (t.get("hinweis") or "") + "Rechnungsnummer erkannt, Betrag weicht ab - bitte prüfen."
        else:
            t["kategorie"] = guess_category(t["name"] + " " + t["zweck"])
            t["aktion"] = "ausgabe" if t["kategorie"] != "Sonstige Betriebsausgaben" else "ignore"
            try:
                pm = nb_model()["partner"].get(norm_partner(t["name"]))
                if pm:
                    (lt, lk), _n = pm.most_common(1)[0]
                    if lt == "ausgabe":
                        t["kategorie"], t["aktion"] = lk or t["kategorie"], "ausgabe"
                        t["hinweis"] = (t.get("hinweis") or "") + f"Assistent: {t['name']} kennt er als {lk or 'Ausgabe'}."
            except Exception:
                pass
            for inv in open_:
                if inv["typ"] == "storno" and abs(inv["summe"] - t["betrag"]) < 0.005:
                    t["vorschlag"], t["sicher"], t["aktion"] = {"id": inv["id"], "nr": inv["nr"], "name": inv_name(inv), "summe": inv["summe"]}, 2, "paid"
                    break
        if t["betrag"] < 0 and t["aktion"] == "ausgabe":
            dup = q("SELECT id, partner FROM belege WHERE typ='ausgabe' AND abs(betrag-?)<0.01 AND julianday(datum) BETWEEN julianday(?)-10 AND julianday(?)+10 LIMIT 1",
                    (abs(t["betrag"]), t["datum"], t["datum"]), one=True)
            if dup:
                t["aktion"] = "ignore"
                t["dup_beleg"] = dup["id"]
                t["hinweis"] = f"Beleg schon erfasst ({dup['partner']}) - ignoriert, sonst doppelt"
        if not t["neu"]:
            t["aktion"] = "ignore"
        res.append(t)
    return res


def bank_apply(items):
    n_paid = n_out = n_in = 0
    for t in items:
        if q("SELECT id FROM bank_tx WHERE hash=?", (t["hash"],), one=True):
            continue
        inv_id = beleg_id = None
        st = t.get("aktion") or "ignore"
        if st == "paid" and t.get("invoice_id"):
            inv_id = int(t["invoice_id"])
            # v2.0.6: only open invoices - a cancelled one must never become "bezahlt" again
            cur_ = q("SELECT status FROM invoices WHERE id=?", (inv_id,), one=True)
            if cur_ and cur_["status"] == "offen":
                x("UPDATE invoices SET status='bezahlt', bezahlt_am=?, updated=? WHERE id=? AND status='offen'", (t["datum"], now_iso(), inv_id))
                lock_invoice(inv_id)
                n_paid += 1
        elif st == "ausgabe":
            beleg_id = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created, quelle) VALUES "
                         "('ausgabe',?,?,?,?,?,?,'','{}',?,'bank')",
                         (t["datum"], t["name"][:80], "", abs(t["betrag"]), t.get("kategorie") or "Sonstige Betriebsausgaben", t["zweck"][:200], now_iso()))
            n_out += 1
        elif st == "einnahme":
            beleg_id = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created, quelle) VALUES "
                         "('einnahme',?,?,?,?,'',?,'','{}',?,'bank')",
                         (t["datum"], t["name"][:80], "", abs(t["betrag"]), t["zweck"][:200], now_iso()))
            n_in += 1
        x("INSERT INTO bank_tx (hash, datum, betrag, name, zweck, iban, invoice_id, beleg_id, status, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
          (t["hash"], t["datum"], t["betrag"], t["name"], t["zweck"], t.get("iban", ""), inv_id, beleg_id, st, now_iso()))
    return {"ok": True, "bezahlt": n_paid, "ausgaben": n_out, "einnahmen": n_in}
