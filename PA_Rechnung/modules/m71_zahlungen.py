# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m71_zahlungen (v2.0.19)
# Zahlungseingaenge: automatischer Abgleich von Bankbuchungen (CSV-Import, FinTS, PSD2) mit offenen
# Rechnungen, Teilzahlungen, Skonto, Ausbuchen eines Restbetrags.
#  - Tabelle m71_zahlung: jede Zahlung je Rechnung (art zahlung / teil / skonto / ausbuchung)
#  - Rechnung bleibt "offen", bis Zahlungen + Skonto + Ausbuchung die Summe decken
#  - Skonto: x % bei Zahlung binnen y Tagen (Standard in den Einstellungen, je Rechnung ueberschreibbar),
#    Platzhalter [Skonto], [Skontobetrag], [Skontodatum], [Skontosatz] in Kopf-/Fusstext
#  - EUER/Statistik: hat eine Rechnung Zahlungseintraege, zaehlt der Zufluss je Zahlung nach Zahlungsdatum
#    (paid_invoices und stats werden ummantelt); Rechnungen ohne Eintraege bleiben wie bisher
#  - Wird eine Rechnung auf anderem Weg (Knopf, Sammelaktion, Import) auf "bezahlt" gesetzt, ergaenzt
#    m71_sync den Rest als Zahlung - so stimmt der Zufluss immer.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M71_VERSION = "1.0.0"
M71_ARTEN = {"zahlung": "Zahlung", "teil": "Teilzahlung", "skonto": "Skonto", "ausbuchung": "Ausgebucht"}
M71_EPS = 0.005
# v2.1.0: bookings one at a time - two requests at once (double click, second window, bank automation in the
# background) both saw the invoice as "offen" and booked the full amount twice (income counted twice)
M71_LOCK = threading.RLock()


def _m71_schema():
    x("CREATE TABLE IF NOT EXISTS m71_zahlung (id INTEGER PRIMARY KEY, invoice_id INTEGER, datum TEXT, betrag REAL, art TEXT, "
      "bank_hash TEXT, quelle TEXT, notiz TEXT, created TEXT)")
    try:
        x("CREATE INDEX IF NOT EXISTS m71_z_inv ON m71_zahlung(invoice_id)")
    except Exception:
        pass
    have = {r["name"] for r in q("PRAGMA table_info(invoices)")}
    if "skonto_pct" not in have:
        x("ALTER TABLE invoices ADD COLUMN skonto_pct REAL")
    if "skonto_tage" not in have:
        x("ALTER TABLE invoices ADD COLUMN skonto_tage INTEGER")


HOOK_SCHEMA.append(_m71_schema)


def m71_cfg(s=None):
    s = s or get_settings()
    return {"skonto_pct": float(s.get("m71_skonto_pct") or 0), "skonto_tage": int(s.get("m71_skonto_tage") or 0),
            "auto": bool(s.get("m71_auto", True)), "auto_teil": bool(s.get("m71_auto_teil", True)),
            "toleranz": float(s.get("m71_toleranz") or 0)}


def _m71_f(v, default=None):
    if v in (None, ""):
        return default
    try:
        return float(v) if isinstance(v, (int, float)) else parse_amount(str(v))
    except Exception:
        try:
            return float(str(v).replace(",", "."))
        except Exception:
            return default


def m71_skonto(inv, s=None):
    """skonto rule of an invoice -> dict or None"""
    c = m71_cfg(s)
    pct = _m71_f(inv.get("skonto_pct"), None)
    tage = inv.get("skonto_tage")
    if pct is None:
        pct = c["skonto_pct"]
    try:
        tage = int(tage) if str(tage).strip() not in ("", "None") else c["skonto_tage"]
    except Exception:
        tage = c["skonto_tage"]
    summe = float(inv.get("summe") or 0)
    if pct <= 0 or summe <= 0 or (inv.get("typ") or "rechnung") != "rechnung":
        return None
    d0 = d_iso(inv.get("datum")) or datetime.date.today()
    bis = d0 + datetime.timedelta(days=max(0, tage))
    return {"pct": round(pct, 2), "tage": tage, "bis": bis.isoformat(), "betrag": round(summe * (1 - pct / 100.0), 2),
            "abzug": round(summe - summe * (1 - pct / 100.0), 2)}


def m71_rows(iid):
    return q("SELECT * FROM m71_zahlung WHERE invoice_id=? ORDER BY datum, id", (iid,))


def m71_state(inv, rows=None, s=None):
    if not isinstance(inv, dict):
        inv = q("SELECT * FROM invoices WHERE id=?", (inv,), one=True) or {}
    rows = m71_rows(inv["id"]) if rows is None and inv.get("id") else (rows or [])
    summe = round(float(inv.get("summe") or 0), 2)
    gez = round(sum(r["betrag"] or 0 for r in rows if r["art"] in ("zahlung", "teil")), 2)
    sk = round(sum(r["betrag"] or 0 for r in rows if r["art"] == "skonto"), 2)
    ab = round(sum(r["betrag"] or 0 for r in rows if r["art"] == "ausbuchung"), 2)
    if inv.get("status") == "bezahlt" and not rows:
        gez = summe
    rest = round(summe - gez - sk - ab, 2)
    if inv.get("status") == "bezahlt":
        rest = min(rest, 0.0) if rest < 0 else 0.0
    return {"summe": summe, "gezahlt": gez, "skonto": sk, "ausgebucht": ab, "rest": rest,
            "teil": bool(rows) and inv.get("status") == "offen" and gez > 0,
            "skonto_regel": m71_skonto(inv, s), "zahlungen": rows}


def _m71_mark_paid(iid, datum):
    x("UPDATE invoices SET status='bezahlt', bezahlt_am=?, updated=? WHERE id=? AND status='offen'", (datum, now_iso(), iid))
    lock_invoice(iid)


def m71_book(iid, datum=None, betrag=0.0, art=None, bank_hash="", quelle="manuell", notiz=""):
    """book a payment; returns {status, art, rest, skonto}"""
    with M71_LOCK:
        return _m71_book(iid, datum, betrag, art, bank_hash, quelle, notiz)


def _m71_book(iid, datum=None, betrag=0.0, art=None, bank_hash="", quelle="manuell", notiz=""):
    inv = q("SELECT * FROM invoices WHERE id=?", (int(iid),), one=True)
    if not inv:
        raise ValueError("Rechnung nicht gefunden.")
    if (inv["typ"] or "rechnung") not in ("rechnung", "storno"):
        raise ValueError("Zahlungen gibt es nur zu Rechnungen.")
    if inv["status"] == "bezahlt":
        raise ValueError(f"Rechnung {inv['nr']} ist bereits bezahlt.")
    if inv["status"] != "offen":
        raise ValueError(f"Rechnung {inv['nr']} ist {inv['status']} - keine Zahlung möglich.")
    datum = (datum or today())[:10]
    if not d_iso(datum):
        raise ValueError("Ungültiges Datum.")
    betrag = round(float(_m71_f(betrag, 0.0)), 2)
    if abs(betrag) < M71_EPS:
        raise ValueError("Bitte einen Betrag angeben.")
    if float(inv["summe"] or 0) < 0:
        betrag = -abs(betrag)    # storno refund is an outflow (EUER), whatever sign was typed
    m71_sync_one(inv["id"])
    inv = q("SELECT * FROM invoices WHERE id=?", (inv["id"],), one=True)
    if art == "ausbuchung":
        st = m71_state(inv)
        if st["rest"] <= M71_EPS:
            raise ValueError("Kein offener Rest zum Ausbuchen.")
        x("INSERT INTO m71_zahlung (invoice_id, datum, betrag, art, bank_hash, quelle, notiz, created) VALUES (?,?,?,?,?,?,?,?)",
          (inv["id"], datum, st["rest"], "ausbuchung", "", quelle, notiz or "Rest ausgebucht", now_iso()))
        _m71_mark_paid(inv["id"], datum)
        return {"ok": True, "status": "bezahlt", "art": "ausbuchung", "rest": 0.0}
    pid = x("INSERT INTO m71_zahlung (invoice_id, datum, betrag, art, bank_hash, quelle, notiz, created) VALUES (?,?,?,?,?,?,?,?)",
            (inv["id"], datum, betrag, "zahlung", bank_hash or "", quelle, (notiz or "")[:200], now_iso()))
    st = m71_state(dict(inv, status="offen"))
    summe = st["summe"]
    res = {"ok": True, "id": pid, "status": "offen", "art": "zahlung", "rest": st["rest"], "skonto": 0.0}
    tol = m71_cfg()["toleranz"]
    if summe < 0:   # storno refund: any booking closes it
        _m71_mark_paid(inv["id"], datum)
        res.update(status="bezahlt", rest=0.0)
        return res
    if st["rest"] <= M71_EPS + tol:
        if st["rest"] < -M71_EPS:
            x("UPDATE m71_zahlung SET notiz=? WHERE id=?", (((notiz or "") + f" Überzahlung {money(-st['rest'])}").strip(), pid))
        elif st["rest"] > M71_EPS:   # small difference within tolerance -> written off
            x("INSERT INTO m71_zahlung (invoice_id, datum, betrag, art, bank_hash, quelle, notiz, created) VALUES (?,?,?,?,?,?,?,?)",
              (inv["id"], datum, st["rest"], "ausbuchung", "", "auto", "Kleindifferenz (Toleranz)", now_iso()))
        _m71_mark_paid(inv["id"], datum)
        res.update(status="bezahlt", rest=0.0)
        return res
    sk = st["skonto_regel"]
    if sk and datum <= sk["bis"] and st["gezahlt"] >= sk["betrag"] - 0.01 and st["skonto"] == 0:
        x("INSERT INTO m71_zahlung (invoice_id, datum, betrag, art, bank_hash, quelle, notiz, created) VALUES (?,?,?,?,?,?,?,?)",
          (inv["id"], datum, st["rest"], "skonto", "", "auto", f"{nde_py(sk['pct'])} % Skonto (Zahlung bis {de_date(sk['bis'])})", now_iso()))
        _m71_mark_paid(inv["id"], datum)
        res.update(status="bezahlt", art="skonto", rest=0.0, skonto=st["rest"])
        return res
    x("UPDATE m71_zahlung SET art='teil' WHERE id=?", (pid,))
    res.update(art="teil")
    return res


def nde_py(v, d=2):
    s_ = f"{float(v):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s_[:-3] if d and s_.endswith("," + "0" * d) else s_


def m71_delete(pid):
    with M71_LOCK:
        return _m71_delete(pid)


def _m71_delete(pid):
    r = q("SELECT * FROM m71_zahlung WHERE id=?", (int(pid),), one=True)
    if not r:
        return {"ok": True}
    x("DELETE FROM m71_zahlung WHERE id=?", (r["id"],))
    if r["art"] in ("zahlung", "teil"):
        x("DELETE FROM m71_zahlung WHERE invoice_id=? AND art='skonto'", (r["invoice_id"],))
        x("DELETE FROM m71_zahlung WHERE invoice_id=? AND art='ausbuchung' AND quelle='auto'", (r["invoice_id"],))
    if r.get("bank_hash"):
        # the bank booking goes back to "Zu pruefen" so it can be assigned again (status 'ignore' hid it for good)
        bt = q("SELECT * FROM bank_tx WHERE hash=?", (r["bank_hash"],), one=True)
        if bt and (bt.get("beleg_id") in (None, "")):
            try:
                x("INSERT OR IGNORE INTO fints_pending (hash, datum, betrag, name, zweck, iban, created) VALUES (?,?,?,?,?,?,?)",
                  (bt["hash"], bt["datum"], bt["betrag"], bt["name"] or "", bt["zweck"] or "", bt["iban"] or "", now_iso()))
                x("DELETE FROM bank_tx WHERE hash=?", (bt["hash"],))
            except Exception:
                traceback.print_exc()
                x("UPDATE bank_tx SET invoice_id=NULL, status='ignore' WHERE hash=?", (r["bank_hash"],))
        else:
            x("UPDATE bank_tx SET invoice_id=NULL, status='ignore' WHERE hash=?", (r["bank_hash"],))
    inv = q("SELECT * FROM invoices WHERE id=?", (r["invoice_id"],), one=True)
    if inv:
        rows = m71_rows(inv["id"])
        st = m71_state(dict(inv, status="offen"), rows)
        if inv["status"] == "bezahlt" and st["rest"] > M71_EPS:
            x("UPDATE invoices SET status='offen', bezahlt_am='', updated=? WHERE id=?", (now_iso(), inv["id"]))
        elif inv["status"] == "offen" and rows and st["rest"] <= M71_EPS:
            _m71_mark_paid(inv["id"], max(r_["datum"] for r_ in rows))
        # remaining 'zahlung' rows of a now open invoice are partial payments
        x("UPDATE m71_zahlung SET art='teil' WHERE invoice_id=? AND art='zahlung' AND "
          "(SELECT status FROM invoices WHERE id=?)='offen'", (inv["id"], inv["id"]))
    return {"ok": True}


def m71_sync_one(iid):
    inv = q("SELECT * FROM invoices WHERE id=?", (iid,), one=True)
    rows = m71_rows(iid)
    if not inv:
        if rows:
            x("DELETE FROM m71_zahlung WHERE invoice_id=?", (iid,))
        return
    if not rows:
        return
    if inv["status"] == "offen":
        if any(r["quelle"] == "status" for r in rows):
            x("DELETE FROM m71_zahlung WHERE invoice_id=? AND quelle='status'", (iid,))
        return
    if inv["status"] == "bezahlt":
        st = m71_state(dict(inv, status="offen"), rows)
        if st["rest"] > M71_EPS:
            x("INSERT INTO m71_zahlung (invoice_id, datum, betrag, art, bank_hash, quelle, notiz, created) VALUES (?,?,?,?,?,?,?,?)",
              (iid, (inv["bezahlt_am"] or today())[:10], st["rest"], "zahlung", "", "status", "Rest beim Markieren als bezahlt", now_iso()))


def m71_sync():
    for r in q("SELECT DISTINCT invoice_id FROM m71_zahlung"):
        try:
            m71_sync_one(r["invoice_id"])
        except Exception:
            traceback.print_exc()


def m71_ids():
    return {r["invoice_id"] for r in q("SELECT DISTINCT invoice_id FROM m71_zahlung")}

# ---------------------------------------------------------------------------
# EUER / Statistik: income by payment date for invoices with payment rows
# ---------------------------------------------------------------------------


def _m71_payment_rows(year_strs=None):
    # status 'storniert': an invoice cancelled after a partial payment - the money was received (Zufluss),
    # a refund is booked as its own outflow; dropping the rows would make the payment vanish from the EUER
    where, args = "", ()
    if year_strs:
        where = f"AND substr(z.datum,1,4) IN ({','.join('?' * len(year_strs))}) "
        args = tuple(year_strs)
    return q(f"SELECT z.id zid, z.datum zdatum, z.betrag zbetrag, z.art zart, i.* FROM m71_zahlung z JOIN invoices i ON i.id=z.invoice_id "
             f"WHERE z.art IN ('zahlung','teil') AND i.status IN ('offen','bezahlt','storniert') AND i.typ IN ('rechnung','storno') "
             f"{where}ORDER BY z.datum, z.id", args)


@chain_step("paid_invoices", "m71_zahlungen")
def _m71_step_paid_invoices(_next, year):
    base = _next(year)
    try:
        m71_sync()
        ids = m71_ids()
        if not ids:
            return base
        out = [r for r in base if r["id"] not in ids]
        for z in _m71_payment_rows((str(year), str(int(year) + 1))):
            r = {k: v for k, v in z.items() if k not in ("zid", "zdatum", "zbetrag", "zart")}
            full = float(r.get("summe") or 0)
            r["summe"], r["bezahlt_am"] = round(z["zbetrag"] or 0, 2), z["zdatum"]
            y, ten = zufluss_year(r)
            if y != int(year):
                continue
            r["zehn_tage"] = ten
            r["m71_zahlung_id"] = z["zid"]
            r["m71_teil"] = abs(full - r["summe"]) > M71_EPS
            r["m71_rechnungsbetrag"] = full
            out.append(r)
        return out
    except Exception:
        traceback.print_exc()
        return base


@chain_step("stats", "m71_zahlungen")
def _m71_step_stats(_next, year):
    r = _next(year)
    try:
        ids = m71_ids()
        if not ids or not r.get("months"):
            return r
        ys = str(year)
        for m in r["months"]:
            m["zufluss"] = 0.0
        for inv in q("SELECT * FROM invoices WHERE status='bezahlt' AND typ IN ('rechnung','storno') AND "
                     "substr(COALESCE(NULLIF(bezahlt_am,''),datum),1,4)=?", (ys,)):
            if inv["id"] in ids:
                continue
            d = inv["bezahlt_am"] or inv["datum"]
            r["months"][int(d[5:7]) - 1]["zufluss"] += inv["summe"] or 0
        for z in _m71_payment_rows((ys,)):
            r["months"][int(z["zdatum"][5:7]) - 1]["zufluss"] += z["zbetrag"] or 0
        for m in r["months"]:
            m["zufluss"] = round(m["zufluss"], 2)
    except Exception:
        traceback.print_exc()
    return r


_m71_orig_euer = chain_inner("euer", "m71_zahlungen")   # v3.1.0: the level below this module
@chain_step("euer", "m71_zahlungen")
def _m71_step_euer(_next, year):
    e = _next(year)
    try:
        ids = m71_ids()
        if ids and e.get("offen_anzahl"):
            cred = q("SELECT COALESCE(SUM(z.betrag),0) s FROM m71_zahlung z JOIN invoices i ON i.id=z.invoice_id WHERE i.status='offen' "
                     "AND i.typ IN ('rechnung','storno') AND substr(i.datum,1,4)=?", (str(year),), one=True)["s"]
            e = dict(e, offen=round(e["offen"] - (cred or 0), 2))
    except Exception:
        traceback.print_exc()
    return e


euer._m60_orig = getattr(CHAINS["euer"][-1].base, "_m60_orig", CHAINS["euer"][-1].base)   # uncached base euer (m04)


@chain_step("stats_detail", "m71_zahlungen")
def _m71_step_stats_detail(_next, year=None):
    """Statistik -> Einnahmen: same basis as the EUER (one row per payment, by payment date, Skonto not counted)"""
    d = _next(year)
    try:
        m71_sync()
        ids = m71_ids()
        if not ids or not isinstance(d.get("einnahmen"), list):
            return d
        ein = [r for r in d["einnahmen"] if not (r.get("art") == "rechnung" and r.get("id") in ids)]
        cm = _cust_map()
        pn = _proj_names()
        ys = [str(year), str(int(year) + 1)] if year else None
        for z in _m71_payment_rows(ys):
            r = {k: v for k, v in z.items() if k not in ("zid", "zdatum", "zbetrag", "zart")}
            r["bezahlt_am"] = z["zdatum"]
            y, ten = zufluss_year(r)
            if year and y != int(year):
                continue
            zd = z["zdatum"]
            name = _inv_name_fast(r, cm)
            full = round(float(r.get("summe") or 0), 2)
            amt = round(float(z["zbetrag"] or 0), 2)
            ein.append({"art": "rechnung", "id": r["id"], "nr": r["nr"] or "", "datum": r["datum"], "zufluss": zd, "jahr": y,
                        "monat": int(zd[5:7]) if zd[:4] == str(y) else 12, "partner": name,
                        "ckey": str(r["customer_id"] or r["kdnr"] or name),
                        "kategorie": ("Rechnung" if r["typ"] == "rechnung" else "Storno / Erstattung") +
                                     (" (Teilzahlung)" if abs(full - amt) > M71_EPS else ""),
                        "titel": r["titel"] or "", "zehn_tage": ten, "summe": amt, "projekt": pn.get(r["project_id"], ""),
                        "m71_zahlung_id": z["zid"]})
        ein.sort(key=lambda r_: (r_["zufluss"], r_["nr"]))
        d["einnahmen"] = ein
    except Exception:
        traceback.print_exc()
    return d

# ---------------------------------------------------------------------------
# placeholders [Skonto] ...
# ---------------------------------------------------------------------------
@chain_step("fill_placeholders", "m71_zahlungen")
def _m71_step_fill_placeholders(_next, text, inv, summe):
    t = _next(text, inv, summe)
    if "[Skonto" not in (t or ""):
        return t
    try:
        # reminders (pseudo document with _mahnfrist) never offer Skonto - the period is over and the amount includes fees
        sk = None if (inv or {}).get("_mahnfrist") else m71_skonto(dict(inv, summe=summe, typ=inv.get("typ") or "rechnung"))
    except Exception:
        sk = None
    if sk:
        satz = sk["pct"]
        txt = (f"Bei Zahlung bis zum {de_date(sk['bis'])} gewähren wir {nde_py(satz)} % Skonto "
               f"(Zahlbetrag {money(sk['betrag'])}).")
        return t.replace("[Skonto]", txt).replace("[Skontobetrag]", money(sk["betrag"])) \
            .replace("[Skontodatum]", de_date(sk["bis"])).replace("[Skontosatz]", nde_py(satz) + " %")
    return re.sub(r"\[Skonto(betrag|datum|satz)?\]", "", t)


@chain_step("save_invoice", "m71_zahlungen")
def _m71_step_save_invoice(_next, d, bump=True):
    res = _next(d, bump)
    try:
        if "skonto_pct" in d or "skonto_tage" in d:
            iid = res[0] if isinstance(res, (tuple, list)) else res
            pct = _m71_f(d.get("skonto_pct"), None)
            tg = d.get("skonto_tage")
            tg = int(_m71_f(tg, 0)) if str(tg).strip() not in ("", "None") else None
            x("UPDATE invoices SET skonto_pct=?, skonto_tage=? WHERE id=? AND COALESCE(locked,0)=0", (pct, tg, iid))
    except Exception:
        traceback.print_exc()
    return res

# ---------------------------------------------------------------------------
# bank matching
# ---------------------------------------------------------------------------


def _m71_blob(t):
    return re.sub(r"[^0-9a-z]", "", ((t.get("zweck") or "") + " " + (t.get("name") or "")).lower())


def _m71_name_hit(inv, t):
    text = ((t.get("name") or "") + " " + (t.get("zweck") or "")).lower()
    toks = [w for w in re.split(r"\W+", re.sub(r"\b(gmbh|co|kg|ag|ug|ohg|gbr|mbh|und|ev)\b", " ", inv_name(inv).lower())) if len(w) > 3]
    return bool(toks) and all(w in text for w in toks[:2])


_M71_NR_RX = {}


def _m71_nr_hit(nr, t, blob=None):
    """invoice number in the transfer text - with boundaries, so 2026-1 is NOT found in 2026-12 (v2.0.19 fix)"""
    parts = re.findall(r"[0-9a-z]+", (nr or "").lower())
    if not parts or len("".join(parts)) < 4:
        return False
    # v2.1.0: quick test first (the number without separators must be in the text without separators), compiled
    # patterns kept - before, every bank booking compiled one pattern per open invoice (minutes for a long list)
    if blob is not None and "".join(parts) not in blob:
        return False
    text = ((t.get("zweck") or "") + " " + (t.get("name") or "")).lower()
    key = "|".join(parts)
    rx = _M71_NR_RX.get(key)
    if rx is None:
        rx = re.compile(r"(?:(?<![0-9a-z])|(?<=re)|(?<=rg)|(?<=nr)|(?<=no)|(?<=rech))" + r"[^0-9a-z]{0,2}".join(re.escape(x_) for x_ in parts) + r"(?![0-9])")
        if len(_M71_NR_RX) > 5000:
            _M71_NR_RX.clear()
        _M71_NR_RX[key] = rx
    return rx.search(text) is not None


def m71_states(invs):
    """v2.1.0: payment state of many invoices with ONE query (before: two queries per invoice and bank booking -
    the bank list with a few hundred bookings and open invoices took minutes)"""
    ids = [i["id"] for i in invs if i.get("id")]
    rows = {}
    for k in range(0, len(ids), 500):
        part = ids[k:k + 500]
        for r in q(f"SELECT * FROM m71_zahlung WHERE invoice_id IN ({','.join('?' * len(part))}) ORDER BY datum, id", part):
            rows.setdefault(r["invoice_id"], []).append(r)
    s = get_settings()
    out = {}
    for inv in invs:
        out[inv["id"]] = m71_state(inv, rows.get(inv["id"]) or [], s)
    return out


def m71_match(t, open_=None, states=None):
    """best open invoice for an incoming amount -> (inv, score, kind, state) ; kind voll/skonto/teil"""
    amt = round(float(t.get("betrag") or 0), 2)
    if amt <= 0:
        return None
    if open_ is None:
        open_ = q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen'")
    if states is None:
        states = m71_states(open_)
    blob = _m71_blob(t)
    best = None
    for inv in open_:
        st = states.get(inv["id"]) or m71_state(inv)
        if st["rest"] <= M71_EPS:
            continue
        nr_hit = _m71_nr_hit(inv["nr"], t, blob)
        name_hit = _m71_name_hit(inv, t)
        kind, sc = None, 0
        sk = st["skonto_regel"]
        if abs(amt - st["rest"]) < M71_EPS:
            kind, sc = "voll", 1
        elif sk and st["skonto"] == 0 and (t.get("datum") or today()) <= sk["bis"] and abs(st["gezahlt"] + amt - sk["betrag"]) < 0.011:
            kind, sc = "skonto", 1
        elif amt < st["rest"] and nr_hit:
            kind, sc = "teil", 0
        if kind is None:
            continue
        sc += (3 if nr_hit else 0) + (1 if name_hit else 0)
        if not best or sc > best[1]:
            best = (inv, sc, kind, st)
    return best


def m71_safe(t, open_=None, states=None):
    """invoice only when the match is unambiguous (invoice no., or amount+name with a single candidate)"""
    if (t.get("betrag") or 0) <= 0:
        return None
    if open_ is None:
        open_ = q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen'")
    if states is None:
        states = m71_states(open_)
    m = m71_match(t, open_, states)
    if not m:
        return None
    inv, sc, kind, st = m
    if sc >= 4:
        return None if (kind == "teil" and not m71_cfg()["auto_teil"]) else inv
    if sc >= 2 and kind in ("voll", "skonto"):
        same = 0
        for o in open_:
            so = states.get(o["id"]) or m71_state(o)
            if abs(so["rest"] - t["betrag"]) < M71_EPS or (so["skonto_regel"] and abs(so["skonto_regel"]["betrag"] - t["betrag"]) < 0.011):
                same += 1
        if same == 1:
            return inv
    return None


@chain_step("fints_safe_invoice", "m71_zahlungen")
def _m71_step_fints_safe_invoice(_next, t):
    inv = None
    try:
        inv = _next(t)
        if inv:
            st_ = m71_state(inv)
            # invoice already partly paid: the full amount no longer fits -> let m71_safe decide
            if st_["gezahlt"] > M71_EPS and abs(st_["rest"] - (t.get("betrag") or 0)) >= M71_EPS:
                inv = None
    except Exception:
        traceback.print_exc()
    if not inv:
        try:
            inv = m71_safe(t)
        except Exception:
            traceback.print_exc()
    return inv


@chain_step("bank_suggest", "m71_zahlungen")
def _m71_step_bank_suggest(_next, txs):
    res = _next(txs)
    try:
        open_ = q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen'")
        states = m71_states(open_)

        def _take(iid, amt):
            # this booking is proposed for the invoice: the next bookings of the same run only see what is left
            st_ = states.get(iid) or m71_state(iid)
            states[iid] = dict(st_, rest=round(st_["rest"] - amt, 2), gezahlt=round(st_["gezahlt"] + amt, 2))

        for t in res:
            if (t.get("betrag") or 0) <= 0 or not t.get("neu", True):
                continue
            v = t.get("vorschlag")
            if v and v.get("id") and v["id"] in states and states[v["id"]]["rest"] <= M71_EPS:
                # proposed by the base matcher, but already covered by an earlier booking of this list
                t["vorschlag"], t["sicher"], t["aktion"] = None, 0, "ignore"
                t["hinweis"] = ((t.get("hinweis") or "") + f" Rechnung {v.get('nr') or ''} ist mit einer anderen Buchung dieser Liste "
                                "schon gedeckt - bitte prüfen (doppelte Zahlung?).").strip()
                v = None
            m = m71_match(t, open_, states)
            if m and (not v or m[1] > (t.get("sicher") or 0) or v.get("id") == m[0]["id"]):
                inv, sc, kind, st = m
                t["vorschlag"] = {"id": inv["id"], "nr": inv["nr"], "name": inv_name(inv), "summe": inv["summe"]}
                t["sicher"] = max(sc, t.get("sicher") or 0)
                t["aktion"] = "paid"
                t["m71"] = {"art": kind, "rest": st["rest"], "gezahlt": st["gezahlt"]}
                # built per kind: skonto_regel is None for invoices without Skonto (eager f-string crashed the whole list)
                if kind == "voll":
                    txt = "Restbetrag" if st["gezahlt"] else ""
                elif kind == "skonto":
                    txt = f"mit Skonto ({nde_py(st['skonto_regel']['pct'])} %)"
                else:
                    txt = f"Teilzahlung, danach offen {money(st['rest'] - t['betrag'])}"
                if txt:
                    t["hinweis"] = ((t.get("hinweis") or "") + " " + f"Rechnung {inv['nr']}: {txt}").strip()
                _take(inv["id"], t["betrag"])
            elif v and v.get("id"):
                st = states.get(v["id"]) or m71_state(v["id"])
                if st["gezahlt"] and abs(st["rest"] - t["betrag"]) >= M71_EPS:
                    t["m71"] = {"art": "teil", "rest": st["rest"], "gezahlt": st["gezahlt"]}
                if t.get("aktion") == "paid":
                    _take(v["id"], t["betrag"])
    except Exception:
        traceback.print_exc()
    return res


_m71_orig_apply = chain_inner("bank_apply", "m71_zahlungen")   # v3.0.0: the level below this module (was: the function before the wrapper)
@chain_step("bank_apply", "m71_zahlungen")
def _m71_step_bank_apply(_next, items):
    with M71_LOCK:
        return _m71_bank_apply(items)


def _m71_bank_apply(items):
    rest, n_paid, n_teil = [], 0, 0
    ueber, offen_gelassen = [], []
    for t in items:
        if (t.get("aktion") == "paid" and t.get("invoice_id") and (t.get("betrag") or 0) > 0
                and not q("SELECT id FROM bank_tx WHERE hash=?", (t["hash"],), one=True)):
            try:
                inv = q("SELECT * FROM invoices WHERE id=?", (int(t["invoice_id"]),), one=True)
            except (TypeError, ValueError):
                inv = None
            if inv and inv["typ"] == "rechnung" and inv["status"] == "offen":
                try:
                    r = m71_book(inv["id"], t["datum"], t["betrag"], bank_hash=t["hash"], quelle="bank",
                                 notiz=((t.get("name") or "") + " · " + (t.get("zweck") or ""))[:180])
                except ValueError as e:
                    # never file it as 'paid' without a payment row (income lost) - leave it in the list
                    offen_gelassen.append({"hash": t["hash"], "betrag": t["betrag"], "grund": str(e)})
                    continue
                x("INSERT INTO bank_tx (hash, datum, betrag, name, zweck, iban, invoice_id, beleg_id, status, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (t["hash"], t["datum"], t["betrag"], t.get("name", ""), t.get("zweck", ""), t.get("iban", ""), inv["id"], None,
                   "paid" if r["status"] == "bezahlt" else "teil", now_iso()))
                if r["status"] == "bezahlt":
                    n_paid += 1
                else:
                    n_teil += 1
                continue
            if inv and (inv["typ"] or "rechnung") in ("rechnung", "storno"):
                # invoice already paid / cancelled (double payment, two bookings for one invoice in one run):
                # the money was received -> income "Ueberzahlung", not a silent 'paid' without any income row
                zw = f"Ueberzahlung Re {inv['nr'] or ''}: {t.get('zweck') or ''}".strip()
                rest.append(dict(t, aktion="einnahme", invoice_id=None, zweck=zw))
                ueber.append({"hash": t["hash"], "nr": inv["nr"], "betrag": t["betrag"], "datum": t.get("datum"), "status": inv["status"]})
                continue
            offen_gelassen.append({"hash": t["hash"], "betrag": t["betrag"], "grund": "Rechnung nicht gefunden oder keine Rechnung."})
            continue
        rest.append(t)
    r = _m71_orig_apply(rest) if rest else {"ok": True, "bezahlt": 0, "ausgaben": 0, "einnahmen": 0}
    r["bezahlt"] = r.get("bezahlt", 0) + n_paid
    r["teilzahlungen"] = n_teil
    r["ueberzahlungen"] = ueber
    r["offen_gelassen"] = offen_gelassen
    return r


@chain_step("fints_import", "m71_zahlungen")
def _m71_step_fints_import(_next, raw, saldo=None, konto="", auto=None, quelle="Bankabruf (FinTS)"):
    res = _next(raw, saldo, konto, auto, quelle)
    try:
        if m71_cfg()["auto"] and not (auto if auto is not None else fints_cfg()["auto"]):
            n = m71_auto_pending()
            if n:
                res["bezahlt"] = (res.get("bezahlt") or []) + n
                res["offen"] = max(0, (res.get("offen") or 0) - len(n))
    except Exception:
        traceback.print_exc()
    return res


def m71_auto_pending():
    """book the unambiguous incoming payments waiting in the bank list"""
    with M71_LOCK:
        return _m71_auto_pending()


def _m71_auto_pending():
    done = []
    open_, states = None, None
    for t in q("SELECT hash, datum, betrag, name, zweck, iban FROM fints_pending WHERE betrag>0 AND hash NOT IN (SELECT hash FROM bank_tx)"):
        t = dict(t, name=t["name"] or "", zweck=t["zweck"] or "", iban=t["iban"] or "")
        if open_ is None:
            open_ = q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen'")
            states = m71_states(open_)
        inv = m71_safe(t, open_, states)
        if inv:
            open_ = None          # a booking changes the open invoices -> load again for the next one
            ra = bank_apply([dict(t, aktion="paid", invoice_id=inv["id"])])
            if ra.get("offen_gelassen"):
                continue
            x("DELETE FROM fints_pending WHERE hash=?", (t["hash"],))
            done.append({"nr": inv["nr"], "name": inv_name(inv), "betrag": t["betrag"], "datum": t["datum"]})
    return done

# ---------------------------------------------------------------------------
# overview / routes
# ---------------------------------------------------------------------------


def m71_overview():
    m71_sync()
    s = get_settings()
    pend = []
    try:
        pend = [t for t in fints_pending_list() if (t.get("betrag") or 0) > 0]
    except Exception:
        traceback.print_exc()
    open_ = []
    t0 = datetime.date.today()
    invs = q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen' ORDER BY datum, nr")
    states = m71_states(invs)
    for inv in invs:
        st = states[inv["id"]]
        d0 = d_iso(inv["datum"]) or t0
        due = d0 + datetime.timedelta(days=_frist(inv["frist"]))
        sk = st["skonto_regel"]
        open_.append({"id": inv["id"], "nr": inv["nr"], "name": inv_name(inv), "datum": inv["datum"], "faellig": due.isoformat(),
                      "tage": (t0 - due).days, "summe": st["summe"], "gezahlt": st["gezahlt"], "rest": st["rest"],
                      "skonto": sk if sk and sk["bis"] >= t0.isoformat() and not st["gezahlt"] else None, "mahnstufe": inv["mahnstufe"] or 0})
    pays = q("SELECT z.*, i.nr, i.customer_id, i.kdnr, i.addr, i.summe isumme, i.status istatus FROM m71_zahlung z "
             "LEFT JOIN invoices i ON i.id=z.invoice_id ORDER BY z.datum DESC, z.id DESC LIMIT 400")
    for p in pays:
        p["name"] = inv_name(p) if p.get("nr") else ""
        p["art_de"] = M71_ARTEN.get(p["art"], p["art"])
    return {"pending": pend, "offen": open_, "zahlungen": pays, "cfg": m71_cfg(s),
            "summe_offen": round(sum(o["rest"] for o in open_), 2), "teil_anzahl": sum(1 for o in open_ if o["gezahlt"])}


def _m71_pending_row(h):
    t = q("SELECT hash, datum, betrag, name, zweck, iban FROM fints_pending WHERE hash=?", (h,), one=True)
    if not t:
        raise ValueError("Diese Buchung ist nicht mehr in der Liste (schon übernommen?).")
    return dict(t, name=t["name"] or "", zweck=t["zweck"] or "", iban=t["iban"] or "")


def _m71_apply_route(h, d):
    t = _m71_pending_row(d.get("hash") or "")
    if not d.get("invoice_id"):
        raise ValueError("Bitte eine Rechnung wählen.")
    inv = q("SELECT id, nr, typ, status FROM invoices WHERE id=?", (int(d["invoice_id"]),), one=True)
    # otherwise bank_apply would file the booking as 'paid' without any payment row -> income lost
    if not inv or inv["typ"] != "rechnung" or inv["status"] != "offen":
        raise ValueError(f"Rechnung {inv['nr'] if inv else ''} ist nicht mehr offen - bitte eine andere wählen oder als Einnahme buchen.".replace("  ", " "))
    if (t.get("betrag") or 0) <= 0:
        raise ValueError("Nur Zahlungseingänge können einer Rechnung zugeordnet werden.")
    r = bank_apply([dict(t, aktion="paid", invoice_id=int(d["invoice_id"]))])
    if r.get("offen_gelassen"):
        raise ValueError("Buchung nicht übernommen: " + r["offen_gelassen"][0]["grund"])
    x("DELETE FROM fints_pending WHERE hash=?", (t["hash"],))
    return h._send(200, dict(r, ok=True))


def _m71_ignore_route(h, d):
    for hs in (d.get("hashes") or [d.get("hash")]):
        if not hs:
            continue
        try:
            t = _m71_pending_row(hs)
        except ValueError:
            continue
        bank_apply([dict(t, aktion=d.get("aktion") or "ignore")])
        x("DELETE FROM fints_pending WHERE hash=?", (hs,))
    return h._send(200, {"ok": True})


def _m71_book_route(h, d):
    r = m71_book(int(d["invoice_id"]), d.get("datum") or today(), d.get("betrag"), d.get("art") or None, quelle="manuell",
                 notiz=d.get("notiz") or "")
    return h._send(200, r)


def _m71_cfg_route(h, d):
    for k in ("m71_skonto_pct", "m71_skonto_tage", "m71_toleranz"):
        if k in d:
            set_setting(k, float(_m71_f(d[k], 0) or 0) if k != "m71_skonto_tage" else int(_m71_f(d[k], 0) or 0))
    for k in ("m71_auto", "m71_auto_teil"):
        if k in d:
            set_setting(k, bool(d[k]))
    return h._send(200, {"ok": True, "cfg": m71_cfg()})


def _m71_state_route(h, qs):
    inv = q("SELECT * FROM invoices WHERE id=?", (int(qs.get("id") or 0),), one=True)
    if not inv:
        return h._send(200, {"ok": False})
    m71_sync_one(inv["id"])
    inv = q("SELECT * FROM invoices WHERE id=?", (inv["id"],), one=True)
    st = m71_state(inv)
    for r in st["zahlungen"]:
        r["art_de"] = M71_ARTEN.get(r["art"], r["art"])
    return h._send(200, dict(st, ok=True, id=inv["id"], status=inv["status"]))


def _m71_auto_route(h, d):
    return h._send(200, {"ok": True, "gebucht": m71_auto_pending()})


HOOK_GET["/api/m71/overview"] = lambda h, qs: h._send(200, m71_overview())
HOOK_GET["/api/m71/state"] = _m71_state_route
HOOK_POST["/api/m71/apply"] = _m71_apply_route
HOOK_POST["/api/m71/ignore"] = _m71_ignore_route
HOOK_POST["/api/m71/book"] = _m71_book_route
HOOK_POST["/api/m71/delete"] = lambda h, d: h._send(200, m71_delete(int(d["id"])))
HOOK_POST["/api/m71/cfg"] = _m71_cfg_route
HOOK_POST["/api/m71/auto"] = _m71_auto_route


def _m71_boot(d):
    rows = q("SELECT z.invoice_id, z.art, z.betrag FROM m71_zahlung z JOIN invoices i ON i.id=z.invoice_id WHERE i.status='offen'")
    cred = {}
    for r in rows:
        if r["art"] in ("zahlung", "teil"):
            cred[r["invoice_id"]] = round(cred.get(r["invoice_id"], 0) + (r["betrag"] or 0), 2)
    rest = {}
    for iid, c in cred.items():
        inv = q("SELECT * FROM invoices WHERE id=?", (iid,), one=True)
        if inv:
            rest[iid] = m71_state(inv)["rest"]
    try:
        npend = q("SELECT COUNT(*) n FROM fints_pending WHERE betrag>0 AND hash NOT IN (SELECT hash FROM bank_tx)", one=True)["n"]
    except Exception:
        npend = 0
    d["m71"] = {"gezahlt": cred, "rest": rest, "pending": npend, "cfg": m71_cfg()}


HOOK_BOOT.append(_m71_boot)


def _m71_ex(p):
    o = m71_overview()
    return [_sh("Offene Rechnungen mit Restbetrag", [("Nr.", "t", 14), ("Kunde", "t", 30), ("Datum", "d", 11), ("Fällig", "d", 11),
                                                    ("Betrag", "m", 12), ("Gezahlt", "m", 12), ("Rest", "m", 12)],
                [[r["nr"], r["name"], r["datum"], r["faellig"], r["summe"], r["gezahlt"], r["rest"]] for r in o["offen"]], f"Stand {de_date(today())}"),
            _sh("Zahlungen", [("Datum", "d", 11), ("Rechnung", "t", 14), ("Kunde", "t", 30), ("Art", "t", 14), ("Betrag", "m", 12), ("Notiz", "t", 40)],
                [[r["datum"], r["nr"] or "", r["name"], r["art_de"], r["betrag"] or 0, r["notiz"] or ""] for r in o["zahlungen"]], "", total=False)]


EXPORTS["m71_zahlungen"] = ("Zahlungen", _m71_ex)


def _m71_selftest():
    err = []
    iid = None
    try:
        iid, nr = save_invoice({"nr": "_ST71-0001", "customer_id": None, "kdnr": "", "addr": ["Selbsttest"], "datum": today(),
                                "titel": "Selbsttest m71", "toptext": "", "foottext": "[Skonto]", "zahlart": "Ueberweisung", "frist": 14,
                                "status": "offen", "typ": "rechnung", "skonto_pct": 2, "skonto_tage": 10,
                                "items": [{"qty": 1, "name": "Test", "price": 100.0, "rabatt": 0}]}, bump=False)
        inv = q("SELECT * FROM invoices WHERE id=?", (iid,), one=True)
        if abs((inv["skonto_pct"] or 0) - 2) > 1e-9:
            err.append("m71: Skonto je Rechnung nicht gespeichert")
        if "Skonto" not in fill_placeholders("[Skonto]", inv, 100.0):
            err.append("m71: Platzhalter [Skonto] nicht ersetzt")
        r1 = m71_book(iid, today(), 40)
        if r1["status"] != "offen" or abs(r1["rest"] - 60) > 0.01:
            err.append(f"m71: Teilzahlung falsch ({r1})")
        r2 = m71_book(iid, today(), 58)   # 98 total = skonto amount
        if r2["status"] != "bezahlt" or r2["art"] != "skonto":
            err.append(f"m71: Skonto nicht erkannt ({r2})")
        y = int(today()[:4])
        got = sum(r["summe"] for r in paid_invoices(y) if r["id"] == iid)
        if abs(got - 98) > 0.01:
            err.append(f"m71: EUER-Zufluss {got}, erwartet 98")
        pid = q("SELECT id FROM m71_zahlung WHERE invoice_id=? AND art IN ('zahlung','teil') ORDER BY id DESC LIMIT 1", (iid,), one=True)["id"]
        m71_delete(pid)
        if q("SELECT status FROM invoices WHERE id=?", (iid,), one=True)["status"] != "offen":
            err.append("m71: Löschen der Zahlung öffnet die Rechnung nicht wieder")
        t = {"hash": "_st71", "datum": today(), "betrag": 60.0, "name": "Max", "zweck": "Rechnung _ST71-0001"}
        m = m71_match(t)
        if not m or m[0]["id"] != iid or m[2] != "voll":
            err.append("m71: Bank-Zuordnung Restbetrag fehlt")
    except Exception as e:
        err.append(f"m71 Ausnahme: {e}")
    finally:
        if iid:
            x("DELETE FROM m71_zahlung WHERE invoice_id=?", (iid,))
            x("DELETE FROM items WHERE invoice_id=?", (iid,))
            x("DELETE FROM invoices WHERE id=?", (iid,))
    return err


HOOK_SELFTEST.append(_m71_selftest)


# ---------------------------------------------------------------------------
# v2.0.19: deleting an invoice removes its payments right away (before: only the
# later m71_sync cleaned up) - linked bank bookings go back to "Zu pruefen"
# ---------------------------------------------------------------------------
@chain_step("inv_delete", "m71_zahlungen")
def _m71_step_inv_delete(_next, iid, _seen=None):
    inv_ = q("SELECT id, locked FROM invoices WHERE id=?", (int(iid),), one=True)
    if inv_ and not (inv_["locked"] and not inv_frei()):
        for r_ in q("SELECT id FROM m71_zahlung WHERE invoice_id=? ORDER BY id DESC", (inv_["id"],)):
            try:
                m71_delete(r_["id"])
            except Exception:
                traceback.print_exc()
    return _next(iid, _seen)


# ---------------------------------------------------------------------------
# v2.1.0: cancelling a partly paid invoice
# Before: the cancellation said "gegenstandslos" and the payments received were not mentioned.
# Now: the cancellation names the payments and the refund; the refund is the open amount of the
# cancellation (negative = payout). The unpaid part is written off on the cancellation (art
# 'ausbuchung', not a cash flow). EUER: received payments stay income (rows of the original),
# the refund becomes an outflow when the cancellation is paid -> nothing is counted twice.
# ---------------------------------------------------------------------------
def _m71_storno_texts(inv, gez, rows, lang):
    zl = ", ".join(f"{de_date(r_['datum'])} {money(r_['betrag'])}" for r_ in rows if r_["art"] in ("zahlung", "teil"))
    if lang == "en":
        # payments are kept in EUR (m82: program currency) -> name the currency, English date format
        dfmt = (lambda d_: _m82_date(d_, "en")) if "_m82_date" in globals() else (lambda d_: d_)
        zl_en = ", ".join(f"{dfmt(r_['datum'])}: {r_['betrag']:,.2f} EUR" for r_ in rows if r_["art"] in ("zahlung", "teil"))
        top = (f"We hereby cancel invoice {inv['nr']} in full. You have already paid {gez:,.2f} EUR on this invoice ({zl_en}).")
        foot = f"We will refund the amount already paid ({gez:,.2f} EUR) to you."
        return top, foot
    top = (f"Hiermit stornieren wir die Rechnung {inv['nr']} vom {de_date(inv['datum'])} in voller Höhe. "
           f"Auf diese Rechnung haben Sie bereits {money(gez)} gezahlt ({zl}).")
    foot = f"Den bereits gezahlten Betrag von {money(gez)} erstatten wir Ihnen."
    return top, foot


@chain_step("storno_invoice", "m71_zahlungen")
def _m71_step_storno_invoice(_next, iid):
    inv0 = q("SELECT * FROM invoices WHERE id=?", (int(iid),), one=True)
    part = None
    if inv0 and inv0["status"] in ("offen", "bezahlt") and (inv0["typ"] or "rechnung") == "rechnung":
        rows0 = m71_rows(inv0["id"])
        st0 = m71_state(inv0, rows0)
        korr = round(st0["skonto"] + st0["ausgebucht"], 2)
        # v2.1.0: also a PAID invoice with Skonto / written-off rest - the customer paid less than the sum,
        # the cancellation asked for a refund of the full sum (EUER and UStVA went negative after paying it)
        if (inv0["status"] == "offen" and st0["gezahlt"] > M71_EPS) or (inv0["status"] == "bezahlt" and rows0 and korr > M71_EPS):
            part = (st0["gezahlt"], rows0, korr if korr > M71_EPS else 0.0)
    res = _next(iid)
    if not part:
        return res
    try:
        sid = res[0] if isinstance(res, (tuple, list)) else res
        sto = q("SELECT * FROM invoices WHERE id=?", (sid,), one=True)
        gez, rows0, korr = part
        lang = "de"
        try:
            # language of the ORIGINAL: m82 (loaded later) copies its document settings to the cancellation only
            # after this wrapper returns - asking the cancellation always gave German texts in English documents
            if "m82_ctx_for" in globals():
                c_ = m82_ctx_for(get_invoice(inv0["id"]))
                lang = (c_ or {}).get("lang") or "de"
        except Exception:
            pass
        top, foot = _m71_storno_texts(inv0, gez, rows0, lang)
        ft = sto["foottext"] or ""
        for old_ in ("Die ursprüngliche Rechnung ist damit gegenstandslos. ", "Die ursprüngliche Rechnung ist damit gegenstandslos.",
                     "Der bereits gezahlte Betrag wird Ihnen erstattet. ", "Der bereits gezahlte Betrag wird Ihnen erstattet."):
            ft = ft.replace(old_, "")
        ft = foot + " " + ft if ft.strip() else foot
        x("UPDATE invoices SET toptext=?, foottext=?, status='offen', bezahlt_am='', updated=? WHERE id=?", (top, ft.strip(), now_iso(), sid))
        summe = float(sto["summe"] or 0)                     # negative (cancellation)
        # Skonto / written-off rest of the original: no refund. quelle 'storno_korr' - it reverses the reduction
        # of the original, so the Soll-UStVA (m80) counts it (the cancellation itself reverses the full sum)
        if korr > M71_EPS:
            x("INSERT INTO m71_zahlung (invoice_id, datum, betrag, art, bank_hash, quelle, notiz, created) VALUES (?,?,?,?,?,?,?,?)",
              (sid, (sto["datum"] or today())[:10], -korr, "ausbuchung", "", "storno_korr",
               f"Skonto / ausgebuchter Teil der Rechnung {inv0['nr']} - keine Erstattung", now_iso()))
        weg = round(summe + gez + korr, 2)                    # e.g. -1000 + 300 = -700 never paid -> no refund
        if weg < -M71_EPS:
            x("INSERT INTO m71_zahlung (invoice_id, datum, betrag, art, bank_hash, quelle, notiz, created) VALUES (?,?,?,?,?,?,?,?)",
              (sid, (sto["datum"] or today())[:10], weg, "ausbuchung", "", "auto",
               f"nicht gezahlter Teil der Rechnung {inv0['nr']} - keine Erstattung", now_iso()))
        # an old PDF of the cancellation (if one was written already) must show the new texts
        try:
            pp = invoice_pdf_path(get_invoice(sid), get_settings())
            if pp and os.path.exists(pp):
                write_file(pp, render_invoice_pdf(get_invoice(sid)))
        except Exception:
            pass
    except Exception:
        traceback.print_exc()
    return res


def _m71_selftest_storno():
    err = []
    try:
        y = datetime.date.today().year
        e0 = euer(y)
        iid, nr = save_invoice({"addr": ["Selbsttest Storno"], "datum": today(), "titel": "_ST71 Storno", "frist": 14, "status": "offen",
                                "zahlart": "Ueberweisung", "items": [{"qty": 1, "name": "Test", "price": 1000}]})
        m71_book(iid, today(), 300)
        sid, snr = storno_invoice(iid)
        sto = q("SELECT * FROM invoices WHERE id=?", (sid,), one=True)
        st = m71_state(sto)
        if sto["status"] != "offen" or abs(st["rest"] + 300) > 0.01:
            err.append(f"m71: Storno nach Teilzahlung - Erstattung {st['rest']} statt -300 / Status {sto['status']}")
        if "300" not in (sto["toptext"] or "") or "gegenstandslos" in (sto["foottext"] or ""):
            err.append("m71: Storno-Text nennt die Teilzahlung nicht")
        e1 = euer(y)
        if abs((e1["einnahmen"] - e0["einnahmen"]) - 300) > 0.01:
            err.append(f"m71: EUER nach Storno {e1['einnahmen'] - e0['einnahmen']} statt 300")
        m71_book(sid, today(), 300)
        e2 = euer(y)
        if abs((e2["einnahmen"] - e0["einnahmen"])) > 0.01 and abs((e2["einnahmen"] - e0["einnahmen"]) + (e2.get("ausgaben", 0) - e0.get("ausgaben", 0))) > 0.01:
            err.append(f"m71: EUER nach Erstattung nicht ausgeglichen ({e2['einnahmen'] - e0['einnahmen']})")
        if q("SELECT status FROM invoices WHERE id=?", (sid,), one=True)["status"] != "bezahlt":
            err.append("m71: Erstattung schliesst die Storno-Rechnung nicht")
        for i_ in (sid, iid):
            x("DELETE FROM m71_zahlung WHERE invoice_id=?", (i_,))
            x("DELETE FROM items WHERE invoice_id=?", (i_,))
            x("DELETE FROM invoices WHERE id=?", (i_,))
    except Exception as e:
        err.append(f"m71 Storno Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m71_selftest_storno)
