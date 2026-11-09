# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m71b_abgleich  v1.0.0 (ab Programm v3.3.0)
# Abgleich-Zentrale Bank - Rechnung - Beleg (nach dem Import):
# - Alle Bankumsaetze, die noch mit nichts verknuepft sind, mit den besten Kandidaten:
#     Eingang  -> offene Rechnung (Rest-Betrag, Rechnungsnummer im Verwendungszweck, Kundenname)
#                 bezahlte Rechnung ohne Bankbewegung (nur verknuepfen, nichts neu buchen)
#     Ausgang  -> vorhandener Beleg (gleicher Betrag, +-10 Tage, noch ohne Bankbewegung)
#                 offene Gutschrift/Storno, sonst "als Ausgabe anlegen" mit erkannter Kategorie
# - Sicherheit 3 = sicher, 2 = wahrscheinlich, 1 = moeglich. "Alle sicheren uebernehmen" bucht nur Stufe 3.
# - Weitere Aktionen: als Einnahme anlegen, privat (keine Buchung), erledigt (ausblenden).
# - Zweite Liste: Ausgabe-Belege eines Jahres ohne Bankbewegung (bar bezahlt? fehlt der Kontoauszug?).
# Zahlungen auf Rechnungen laufen ueber m71 (Teilzahlung, Skonto, Ueberzahlung wie beim Import).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M71B_VERSION = "1.0.0"
M71B_LOCK = threading.Lock()


@db_migration(2, "Bankumsätze: Spalte abg für die Abgleich-Zentrale")
def _m71b_mig2():
    have = {r[1] for r in CON.execute("PRAGMA table_info(bank_tx)")}
    if "abg" not in have:
        CON.execute("ALTER TABLE bank_tx ADD COLUMN abg TEXT")


def _m71b_toks(*txt):
    t = {re.sub(r"[^0-9a-z]", "", w) for w in re.split(r"[\s,;:()/]+", " ".join(x_ or "" for x_ in txt).lower())}
    t.discard("")
    return t


def _m71b_has_abg():
    return any(r["name"] == "abg" for r in q("PRAGMA table_info(bank_tx)"))


def _m71b_open_tx():
    cond = " AND COALESCE(abg,'')=''" if _m71b_has_abg() else ""
    return q("SELECT * FROM bank_tx WHERE invoice_id IS NULL AND beleg_id IS NULL AND COALESCE(status,'') IN ('ignore','')" + cond +
             " ORDER BY datum DESC, id DESC LIMIT 1000")


def _m71b_rest(inv):
    try:
        return m71_state(inv, m71_rows(inv["id"]))["rest"]
    except Exception:
        return float(inv["summe"] or 0)


def m71b_candidates(t, ctx):
    """candidate list for one bank row (best first)"""
    out = []
    b = float(t["betrag"] or 0)
    toks = _m71b_toks(t["zweck"], t["name"])
    txt = ((t["name"] or "") + " " + (t["zweck"] or "")).lower()
    if b > 0:
        for inv in ctx["offen"]:
            if inv["typ"] != "rechnung":
                continue
            rest = ctx["rest"].get(inv["id"], inv["summe"])
            sc = 0
            nrn = re.sub(r"[^0-9a-z]", "", (inv["nr"] or "").lower())
            nr_hit = bool(nrn) and len(nrn) >= 4 and nrn in toks
            amt = abs(rest - b) < 0.005 or abs(float(inv["summe"] or 0) - b) < 0.005
            name_hit = any(w in txt for w in ctx["name_toks"].get(inv["id"], []))
            if nr_hit and amt:
                sc = 3
            elif amt and name_hit:
                sc = 3 if ctx["amt_count"].get(round(b, 2), 0) == 1 else 2
            elif nr_hit:
                sc = 2
            elif amt:
                sc = 2 if ctx["amt_count"].get(round(b, 2), 0) == 1 else 1
            elif name_hit and 0 < b < rest:
                sc = 1
            if sc:
                art = "Teilzahlung" if b < rest - 0.005 else ("Überzahlung" if b > rest + 0.005 else "Zahlung")
                out.append({"aktion": "rechnung", "ziel": inv["id"], "sicher": sc,
                            "text": f"Rechnung {inv['nr']} · {ctx['names'].get(inv['id'], '')} · offen {money(rest)} ({art})"})
        # paid invoice without bank movement -> link only
        for inv in ctx["bezahlt_ohne"]:
            if abs(float(inv["summe"] or 0) - b) < 0.005 and inv["bezahlt_am"]:
                try:
                    dd = abs((datetime.date.fromisoformat(inv["bezahlt_am"][:10]) - datetime.date.fromisoformat(t["datum"][:10])).days)
                except Exception:
                    dd = 99
                if dd <= 20:
                    out.append({"aktion": "verknuepfen_re", "ziel": inv["id"], "sicher": 2 if dd <= 5 else 1,
                                "text": f"Rechnung {inv['nr']} ist schon als bezahlt am {de_date(inv['bezahlt_am'])} erfasst – nur verknüpfen"})
        if not out:
            out.append({"aktion": "einnahme", "ziel": None, "sicher": 0, "text": "Als sonstige Einnahme anlegen"})
    else:
        a = abs(b)
        for inv in ctx["offen"]:
            if inv["typ"] == "storno" and abs(float(inv["summe"] or 0) - b) < 0.005:
                out.append({"aktion": "storno", "ziel": inv["id"], "sicher": 3, "text": f"Storno {inv['nr']} ausgezahlt"})
        for be in ctx["belege"]:
            if abs(float(be["betrag"] or 0) - a) >= 0.01:
                continue
            try:
                dd = abs((datetime.date.fromisoformat(be["datum"][:10]) - datetime.date.fromisoformat(t["datum"][:10])).days)
            except Exception:
                continue
            if dd > 10:
                continue
            ptoks = [w for w in re.split(r"\W+", (be["partner"] or "").lower()) if len(w) > 3]
            name_hit = any(w in txt for w in ptoks)
            sc = 3 if (name_hit and dd <= 5) else (2 if (name_hit or dd <= 3) else 1)
            out.append({"aktion": "beleg", "ziel": be["id"], "sicher": sc,
                        "text": f"Beleg {de_date(be['datum'])} · {be['partner'] or '–'} · {money(be['betrag'])} ({be['kategorie'] or ''})"})
        kat = guess_category((t["name"] or "") + " " + (t["zweck"] or ""))
        try:
            pm = nb_model()["partner"].get(norm_partner(t["name"] or ""))
            if pm:
                (lt, lk), _n = pm.most_common(1)[0]
                if lt == "ausgabe" and lk:
                    kat = lk
        except Exception:
            pass
        out.append({"aktion": "ausgabe", "ziel": None, "sicher": 0, "kategorie": kat, "text": f"Als Ausgabe anlegen ({kat})"})
    out.sort(key=lambda c: -c["sicher"])
    return out


def _m71b_ctx():
    offen = q("SELECT * FROM invoices WHERE typ IN ('rechnung','storno') AND status='offen'")
    rest = {i["id"]: _m71b_rest(i) for i in offen if i["typ"] == "rechnung"}
    amt_count = {}
    for i in offen:
        if i["typ"] == "rechnung":
            amt_count[round(rest[i["id"]], 2)] = amt_count.get(round(rest[i["id"]], 2), 0) + 1
    names = {i["id"]: inv_name(i) for i in offen}
    name_toks = {k: [w for w in re.split(r"\W+", v.lower()) if len(w) > 3] for k, v in names.items()}
    linked_inv = {r["invoice_id"] for r in q("SELECT invoice_id FROM bank_tx WHERE invoice_id IS NOT NULL")} | \
        {r["invoice_id"] for r in q("SELECT invoice_id FROM m71_zahlung WHERE COALESCE(bank_hash,'')<>''")}
    bez = [i for i in q("SELECT * FROM invoices WHERE typ='rechnung' AND status='bezahlt' AND COALESCE(bezahlt_am,'')<>'' "
                        "AND bezahlt_am >= date('now','-400 days')") if i["id"] not in linked_inv]
    linked_bel = {r["beleg_id"] for r in q("SELECT beleg_id FROM bank_tx WHERE beleg_id IS NOT NULL")}
    belege = [b for b in q("SELECT id, datum, partner, betrag, kategorie FROM belege WHERE typ='ausgabe' AND datum >= date('now','-500 days')")
              if b["id"] not in linked_bel]
    for i in bez:
        names.setdefault(i["id"], inv_name(i))
    return {"offen": offen, "rest": rest, "amt_count": amt_count, "names": names, "name_toks": name_toks,
            "bezahlt_ohne": bez, "belege": belege}


def m71b_list():
    ctx = _m71b_ctx()
    rows = []
    for t in _m71b_open_tx():
        c = m71b_candidates(t, ctx)
        rows.append({"id": t["id"], "datum": t["datum"], "betrag": t["betrag"], "name": t["name"], "zweck": t["zweck"],
                     "kandidaten": c[:6], "sicher": c[0]["sicher"] if c else 0})
    return {"ok": True, "umsaetze": rows, "anzahl": len(rows), "sicher": sum(1 for r in rows if r["sicher"] == 3),
            "bank": bool(q("SELECT 1 FROM bank_tx LIMIT 1", one=True))}


def m71b_belege_ohne_bank(year):
    linked = {r["beleg_id"] for r in q("SELECT beleg_id FROM bank_tx WHERE beleg_id IS NOT NULL")}
    rows = [dict(b) for b in q("SELECT id, datum, partner, betrag, kategorie, notiz, quelle FROM belege WHERE typ='ausgabe' AND substr(datum,1,4)=? "
                               "ORDER BY datum", (str(year),)) if b["id"] not in linked]
    kasse = set()
    try:
        kasse = {r["beleg_id"] for r in q("SELECT beleg_id FROM m81_buchung WHERE beleg_id IS NOT NULL")}
    except Exception:
        pass
    for r in rows:
        r["kasse"] = r["id"] in kasse
    return {"ok": True, "year": int(year), "belege": [r for r in rows if not r["kasse"]],
            "summe": round(sum(r["betrag"] or 0 for r in rows if not r["kasse"]), 2)}


def _m71b_apply_one(it):
    t = q("SELECT * FROM bank_tx WHERE id=?", (int(it["tx_id"]),), one=True)
    if not t:
        raise ValueError("Bankumsatz nicht gefunden.")
    if t["invoice_id"] or t["beleg_id"] or (t.get("abg") or ""):
        raise ValueError("Bankumsatz ist schon abgeglichen.")
    a = it.get("aktion")
    zid = it.get("ziel")
    if a == "rechnung":
        inv = q("SELECT * FROM invoices WHERE id=?", (int(zid),), one=True)
        if not inv or inv["typ"] != "rechnung" or inv["status"] != "offen":
            raise ValueError("Rechnung ist nicht (mehr) offen.")
        r = m71_book(inv["id"], t["datum"], t["betrag"], bank_hash=t["hash"], quelle="bank",
                     notiz=((t["name"] or "") + " · " + (t["zweck"] or ""))[:180])
        x("UPDATE bank_tx SET invoice_id=?, status=? WHERE id=?", (inv["id"], "paid" if r.get("status") == "bezahlt" else "teil", t["id"]))
        return f"Rechnung {inv['nr']}: {'bezahlt' if r.get('status') == 'bezahlt' else 'Teilzahlung gebucht'}"
    if a == "verknuepfen_re":
        inv = q("SELECT id, nr, status FROM invoices WHERE id=?", (int(zid),), one=True)
        if not inv or inv["status"] != "bezahlt":
            raise ValueError("Rechnung ist nicht als bezahlt erfasst.")
        x("UPDATE bank_tx SET invoice_id=?, status='paid' WHERE id=?", (inv["id"], t["id"]))
        return f"Rechnung {inv['nr']} verknüpft"
    if a == "storno":
        inv = q("SELECT id, nr, status, typ FROM invoices WHERE id=?", (int(zid),), one=True)
        if not inv or inv["typ"] != "storno" or inv["status"] != "offen":
            raise ValueError("Storno ist nicht offen.")
        x("UPDATE invoices SET status='bezahlt', bezahlt_am=?, updated=? WHERE id=? AND status='offen'", (t["datum"], now_iso(), inv["id"]))
        lock_invoice(inv["id"])
        x("UPDATE bank_tx SET invoice_id=?, status='paid' WHERE id=?", (inv["id"], t["id"]))
        return f"Storno {inv['nr']} ausgezahlt"
    if a == "beleg":
        be = q("SELECT id, partner FROM belege WHERE id=?", (int(zid),), one=True)
        if not be:
            raise ValueError("Beleg nicht gefunden.")
        if q("SELECT 1 FROM bank_tx WHERE beleg_id=?", (be["id"],), one=True):
            raise ValueError("Beleg ist schon mit einem anderen Bankumsatz verknüpft.")
        x("UPDATE bank_tx SET beleg_id=?, status='ausgabe' WHERE id=?", (be["id"], t["id"]))
        return f"Beleg {be['partner'] or ''} verknüpft"
    if a in ("ausgabe", "einnahme"):
        if a == "ausgabe" and t["betrag"] > 0 or a == "einnahme" and t["betrag"] < 0:
            raise ValueError("Richtung passt nicht zum Betrag.")
        bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created, quelle) VALUES "
                "(?,?,?,?,?,?,?,'','{}',?,'bank')",
                (a, t["datum"], (t["name"] or "")[:80], "", abs(t["betrag"]),
                 (it.get("kategorie") or "Sonstige Betriebsausgaben") if a == "ausgabe" else "", (t["zweck"] or "")[:200], now_iso()))
        x("UPDATE bank_tx SET beleg_id=?, status=? WHERE id=?", (bid, a, t["id"]))
        return ("Ausgabe" if a == "ausgabe" else "Einnahme") + " angelegt"
    if a in ("privat", "erledigt"):
        x("UPDATE bank_tx SET abg=? WHERE id=?", (a, t["id"]))
        return "privat markiert" if a == "privat" else "ausgeblendet"
    raise ValueError("Unbekannte Aktion.")


def m71b_apply(d):
    items = d.get("items") or []
    if d.get("alle_sicheren"):
        items = [{"tx_id": r["id"], "aktion": r["kandidaten"][0]["aktion"], "ziel": r["kandidaten"][0].get("ziel"),
                  "kategorie": r["kandidaten"][0].get("kategorie")}
                 for r in m71b_list()["umsaetze"] if r["sicher"] == 3 and r["kandidaten"]]
    ok, fehler = [], []
    with M71B_LOCK:
        for it in items:
            try:
                ok.append(_m71b_apply_one(it))
            except Exception as e:
                fehler.append(str(e)[:200])
    return {"ok": True, "erledigt": len(ok), "texte": ok[:50], "fehler": fehler[:50]}


def m71b_reset(d):
    """undo 'privat' / 'erledigt' for a row (it comes back into the list)"""
    x("UPDATE bank_tx SET abg=NULL WHERE id=? AND invoice_id IS NULL AND beleg_id IS NULL", (int(d["tx_id"]),))
    return {"ok": True}


def m71b_hidden():
    if not _m71b_has_abg():
        return {"ok": True, "umsaetze": []}
    return {"ok": True, "umsaetze": q("SELECT id, datum, betrag, name, zweck, abg FROM bank_tx WHERE COALESCE(abg,'')<>'' "
                                       "AND invoice_id IS NULL AND beleg_id IS NULL ORDER BY datum DESC LIMIT 500")}


HOOK_GET["/api/abgleich/ausgeblendet"] = lambda h, qs: h._send(200, m71b_hidden())
HOOK_GET["/api/abgleich/liste"] = lambda h, qs: h._send(200, m71b_list())
HOOK_GET["/api/abgleich/belege_ohne_bank"] = lambda h, qs: h._send(200, m71b_belege_ohne_bank(int(qs.get("year") or datetime.date.today().year)))
HOOK_POST["/api/abgleich/anwenden"] = lambda h, d: h._send(200, m71b_apply(d))
HOOK_POST["/api/abgleich/zuruecksetzen"] = lambda h, d: h._send(200, m71b_reset(d))
HOOK_BOOT.append(lambda d: d.update(abgleich_offen=len(_m71b_open_tx()) if _m71b_has_abg() else 0))


def m71b_selftest():
    err = []
    try:
        cid = x("INSERT INTO customers (kdnr, firma) VALUES ('_ST71B','Abgleichtest GmbH')")
        iid, nr = save_invoice({"customer_id": cid, "kdnr": "_ST71B", "addr": ["Abgleichtest GmbH"], "datum": today(), "typ": "rechnung",
                                "status": "offen", "titel": "Test", "frist": 14,
                                "items": [{"qty": 1, "name": "Leistung", "price": 321.5, "rabatt": 0}]})
        bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created) VALUES "
                "('ausgabe',?,?,'',?,'Software / Lizenzen','','','{}',?)", (today(), "Softwarehaus Probe", 49.99, now_iso()))
        t1 = x("INSERT INTO bank_tx (hash, datum, betrag, name, zweck, iban, status, created) VALUES (?,?,?,?,?,'','ignore',?)",
               ("_st71b_1", today(), 321.5, "Abgleichtest GmbH", f"Rechnung {nr}", now_iso()))
        t2 = x("INSERT INTO bank_tx (hash, datum, betrag, name, zweck, iban, status, created) VALUES (?,?,?,?,?,'','ignore',?)",
               ("_st71b_2", today(), -49.99, "SOFTWAREHAUS PROBE", "Lizenz", now_iso()))
        t3 = x("INSERT INTO bank_tx (hash, datum, betrag, name, zweck, iban, status, created) VALUES (?,?,?,?,?,'','ignore',?)",
               ("_st71b_3", today(), -12.0, "Baeckerei", "Bon", now_iso()))
        L = {r["id"]: r for r in m71b_list()["umsaetze"]}
        if L[t1]["sicher"] != 3 or L[t1]["kandidaten"][0]["ziel"] != iid:
            err.append("m71b: Rechnung nicht sicher erkannt")
        if L[t2]["kandidaten"][0]["aktion"] != "beleg" or L[t2]["kandidaten"][0]["ziel"] != bid:
            err.append("m71b: Beleg nicht erkannt")
        r = m71b_apply({"alle_sicheren": True})
        if q("SELECT status FROM invoices WHERE id=?", (iid,), one=True)["status"] != "bezahlt":
            err.append("m71b: Rechnung nicht bezahlt gebucht")
        if q("SELECT beleg_id FROM bank_tx WHERE id=?", (t2,), one=True)["beleg_id"] != bid:
            err.append("m71b: Beleg nicht verknüpft")
        m71b_apply({"items": [{"tx_id": t3, "aktion": "privat"}]})
        if any(u["id"] == t3 for u in m71b_list()["umsaetze"]):
            err.append("m71b: privat bleibt in der Liste")
        r = m71b_apply({"items": [{"tx_id": t1, "aktion": "rechnung", "ziel": iid}]})
        if not r["fehler"]:
            err.append("m71b: doppelter Abgleich nicht verhindert")
    except Exception as e:
        err.append(f"m71b Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m71b_selftest)
print(f"INIT m71b_abgleich v{M71B_VERSION}")
