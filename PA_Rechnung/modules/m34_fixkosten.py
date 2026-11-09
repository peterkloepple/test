# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m34_fixkosten (v2.0.0)
# Wiederkehrende Ausgaben (Fixkosten): Liste, taegliche Vormerkung faelliger
# Posten (Tabelle fixkosten_vormerk - KEIN gebuchter Beleg, damit nichts doppelt
# in die EUER laeuft), Bestaetigen/Ueberspringen, Verknuepfung mit Bankbuchungen
# (Wrapper um bank_suggest / bank_apply), Vorschlaege aus vorhandenen Belegen,
# Export (EXPORTS["fixkosten"]).
# Autor: T. Pfeiffer

FIX_INTERVALLE = {"monatlich": 1, "quartalsweise": 3, "halbjaehrlich": 6, "jaehrlich": 12}
FIX_LABEL = {"monatlich": "monatlich", "quartalsweise": "quartalsweise", "halbjaehrlich": "halbjährlich", "jaehrlich": "jährlich"}
FIX_CATCHUP_DAYS = 92        # older due dates are skipped when catching up (no flood of old entries)
FIX_LAST_RUN = {"d": ""}
FIX_LOCK = threading.RLock()  # v2.6.3: confirm/skip are serialized (double click booked the expense twice)


# ---------------- date math ----------------

def fix_add_months(d, months, anchor_day=None):
    """d: date. Adds months; day = anchor_day (clamped to month end)."""
    day = anchor_day or d.day
    m0 = d.month - 1 + months
    y, m = d.year + m0 // 12, m0 % 12 + 1
    import calendar
    return datetime.date(y, m, min(day, calendar.monthrange(y, m)[1]))


def fix_next(naechste, intervall, start=None):
    d = d_iso(naechste)
    if not d:
        return ""
    st = d_iso(start) if start else None
    # v2.1.0: the start day is the anchor only if the due date is that day (or the month end it was cut to);
    # start 01.01. with due date 15.07. stays on the 15th (before: jumped to the 1st)
    anchor = d.day
    if st:
        import calendar
        if d.day == min(st.day, calendar.monthrange(d.year, d.month)[1]):
            anchor = st.day
    return fix_add_months(d, FIX_INTERVALLE.get(intervall, 1), anchor).isoformat()


# ---------------- schema ----------------

def _fix_schema():
    x("CREATE TABLE IF NOT EXISTS fixkosten (id INTEGER PRIMARY KEY, name TEXT, partner TEXT, betrag REAL, kategorie TEXT, "
      "intervall TEXT DEFAULT 'monatlich', naechste TEXT, start TEXT, ende TEXT, aktiv INTEGER DEFAULT 1, notiz TEXT, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS fixkosten_vormerk (id INTEGER PRIMARY KEY, fix_id INTEGER, faellig TEXT, name TEXT, partner TEXT, "
      "betrag REAL, kategorie TEXT, status TEXT DEFAULT 'offen', beleg_id INTEGER, bank_tx_id INTEGER, created TEXT, erledigt TEXT, "
      "UNIQUE(fix_id, faellig))")


# ---------------- CRUD ----------------

def fix_list():
    rows = [dict(r) for r in q("SELECT * FROM fixkosten ORDER BY aktiv DESC, naechste, name")]
    for r in rows:
        r["monatlich"] = round((r["betrag"] or 0) / FIX_INTERVALLE.get(r["intervall"], 1), 2)
        r["offen"] = q("SELECT COUNT(*) n FROM fixkosten_vormerk WHERE fix_id=? AND status='offen'", (r["id"],), one=True)["n"]
    return rows


def fix_save(d):
    name = str(d.get("name") or "").strip()
    if not name:
        raise ValueError("Bitte einen Namen eintragen.")
    try:
        betrag = abs(float(d.get("betrag") or 0))
    except Exception:
        raise ValueError("Betrag ungültig.")
    if betrag <= 0:
        raise ValueError("Bitte einen Betrag eintragen.")
    iv = d.get("intervall") if d.get("intervall") in FIX_INTERVALLE else "monatlich"
    kat = d.get("kategorie") if d.get("kategorie") in EUER_KATEGORIEN else "Sonstige Betriebsausgaben"
    start = (d.get("start") or "")[:10] or today()
    naechste = (d.get("naechste") or "")[:10] or start
    ende = (d.get("ende") or "")[:10]
    if not d_iso(start) or not d_iso(naechste) or (ende and not d_iso(ende)):
        raise ValueError("Datum ungültig.")
    vals = (name, str(d.get("partner") or "").strip() or name, betrag, kat, iv, naechste, start, ende, 1 if d.get("aktiv", True) else 0,
            str(d.get("notiz") or ""))
    if d.get("id"):
        x("UPDATE fixkosten SET name=?, partner=?, betrag=?, kategorie=?, intervall=?, naechste=?, start=?, ende=?, aktiv=?, notiz=? WHERE id=?",
          vals + (int(d["id"]),))
        fid = int(d["id"])
    else:
        fid = x("INSERT INTO fixkosten (name, partner, betrag, kategorie, intervall, naechste, start, ende, aktiv, notiz, created) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", vals + (now_iso(),))
    fix_generate()
    return fid


def fix_delete(fid):
    x("DELETE FROM fixkosten_vormerk WHERE fix_id=? AND status='offen'", (int(fid),))
    x("DELETE FROM fixkosten WHERE id=?", (int(fid),))


# ---------------- due -> vormerk ----------------

def fix_generate(heute=None):
    """Creates VORGEMERKTE entries for all due items. Returns number of new entries."""
    heute = d_iso(heute) if heute else datetime.date.today()
    n = 0
    for f in q("SELECT * FROM fixkosten WHERE aktiv=1"):
        nx, guard = d_iso(f["naechste"]), 0
        ende = d_iso(f["ende"]) if f["ende"] else None
        while nx and nx <= heute and guard < 400:
            guard += 1
            if ende and nx > ende:
                break
            if (heute - nx).days <= FIX_CATCHUP_DAYS:
                try:
                    with DB_LOCK:
                        before = q("SELECT id FROM fixkosten_vormerk WHERE fix_id=? AND faellig=?", (f["id"], nx.isoformat()), one=True)
                        if not before:
                            x("INSERT INTO fixkosten_vormerk (fix_id, faellig, name, partner, betrag, kategorie, status, created) VALUES (?,?,?,?,?,?,'offen',?)",
                              (f["id"], nx.isoformat(), f["name"], f["partner"], f["betrag"], f["kategorie"], now_iso()))
                            n += 1
                except Exception:
                    traceback.print_exc()
            nx = d_iso(fix_next(nx.isoformat(), f["intervall"], f["start"]))
        if nx and nx.isoformat() != f["naechste"]:
            x("UPDATE fixkosten SET naechste=? WHERE id=?", (nx.isoformat(), f["id"]))
        if ende and nx and nx > ende:
            x("UPDATE fixkosten SET aktiv=0 WHERE id=?", (f["id"],))
    FIX_LAST_RUN["d"] = heute.isoformat()
    return n


def fix_vormerk_list(status="offen"):
    return [dict(r) for r in q("SELECT v.*, f.intervall FROM fixkosten_vormerk v LEFT JOIN fixkosten f ON f.id=v.fix_id "
                               "WHERE v.status=? ORDER BY v.faellig, v.id", (status,))]


def fix_confirm(vid, datum=None, betrag=None, bank_tx_id=None, notiz=None):
    """Turns a vormerk entry into a real expense beleg. Returns beleg id."""
    with FIX_LOCK:
        return _fix_confirm(vid, datum, betrag, bank_tx_id, notiz)


def _fix_confirm(vid, datum=None, betrag=None, bank_tx_id=None, notiz=None):
    v = q("SELECT * FROM fixkosten_vormerk WHERE id=?", (int(vid),), one=True)
    if not v:
        raise ValueError("Vorgemerkter Posten nicht gefunden.")
    if v["status"] == "bestaetigt" and v["beleg_id"]:
        return v["beleg_id"]
    if v["status"] != "offen":
        raise ValueError("Dieser Posten wurde bereits übersprungen.")
    dat = (datum or v["faellig"])[:10]
    bt = abs(float(betrag)) if betrag not in (None, "") else float(v["betrag"] or 0)
    note = notiz if notiz is not None else f"Fixkosten: {v['name']} (fällig {de_date(v['faellig'])})"
    bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created, quelle) VALUES "
            "('ausgabe',?,?,?,?,?,?,'','{}',?,'fixkosten')",
            (dat, (v["partner"] or v["name"])[:80], "", bt, v["kategorie"] or "Sonstige Betriebsausgaben", note[:200], now_iso()))
    x("UPDATE fixkosten_vormerk SET status='bestaetigt', beleg_id=?, bank_tx_id=?, erledigt=? WHERE id=?", (bid, bank_tx_id, now_iso(), v["id"]))
    return bid


def fix_skip(vid):
    with FIX_LOCK:
        x("UPDATE fixkosten_vormerk SET status='uebersprungen', erledigt=? WHERE id=? AND status='offen'", (now_iso(), int(vid)))


# ---------------- bank matching ----------------

def _fix_tokens(s):
    p = norm_partner(s) if "norm_partner" in globals() else (s or "").lower()
    return [w for w in re.split(r"[^0-9a-zäöüß]+", p) if len(w) >= 3]


def fix_match_tx(t, vorm=None, used=None):
    """Bank tx (negative amount) -> open vormerk row or None.
    Rule: amount +-1 %, supplier name in text, date +-7 days."""
    if (t.get("betrag") or 0) >= 0:
        return None
    td = d_iso(t.get("datum"))
    if not td:
        return None
    text = (str(t.get("name") or "") + " " + str(t.get("zweck") or "")).lower()
    best, bdist = None, 99
    for v in (vorm if vorm is not None else fix_vormerk_list("offen")):
        if used and v["id"] in used:
            continue
        b = float(v["betrag"] or 0)
        if b <= 0 or abs(abs(t["betrag"]) - b) > b * 0.01 + 0.005:
            continue
        vd = d_iso(v["faellig"])
        if not vd or abs((vd - td).days) > 7:
            continue
        toks = _fix_tokens(v["partner"] or v["name"]) or _fix_tokens(v["name"])
        if not toks or not any(w in text for w in toks):
            continue
        dist = abs((vd - td).days)
        if dist < bdist:
            best, bdist = v, dist
    return best


@chain_step("bank_suggest", "m34_fixkosten")
def _m34_step_bank_suggest(_next, txs):
    res = _next(txs)
    try:
        vorm = fix_vormerk_list("offen")
        used = set()
        if vorm:
            for t in res:
                if not t.get("neu", True) or (t.get("betrag") or 0) >= 0 or t.get("dup_beleg"):
                    continue   # v2.0.6: receipt already captured -> never book the fixed cost a second time
                v = fix_match_tx(t, vorm, used)
                if v:
                    used.add(v["id"])
                    t["fix_vormerk"], t["fix_name"] = v["id"], v["name"]
                    t["aktion"], t["kategorie"] = "ausgabe", v["kategorie"] or t.get("kategorie")
                    t["hinweis"] = f"Fixkosten „{v['name']}“ (fällig {de_date(v['faellig'])}) – wird beim Übernehmen bestätigt und verknüpft"
    except Exception:
        traceback.print_exc()
    return res


@chain_step("bank_apply", "m34_fixkosten")
def _m34_step_bank_apply(_next, items):
    rest, n_fix = [], 0
    for t in items:
        if t.get("fix_vormerk") and (t.get("aktion") or "") == "ausgabe" and not q("SELECT id FROM bank_tx WHERE hash=?", (t["hash"],), one=True):
            v = q("SELECT * FROM fixkosten_vormerk WHERE id=? AND status='offen'", (int(t["fix_vormerk"]),), one=True)
            if v:
                bid = fix_confirm(v["id"], t["datum"], abs(t["betrag"]), None, f"Fixkosten: {v['name']} · Bank: {(t.get('zweck') or '')[:120]}")
                if t.get("kategorie") and t["kategorie"] in EUER_KATEGORIEN:
                    x("UPDATE belege SET kategorie=? WHERE id=?", (t["kategorie"], bid))
                tid = x("INSERT INTO bank_tx (hash, datum, betrag, name, zweck, iban, invoice_id, beleg_id, status, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (t["hash"], t["datum"], t["betrag"], t.get("name", ""), t.get("zweck", ""), t.get("iban", ""), None, bid, "ausgabe", now_iso()))
                x("UPDATE fixkosten_vormerk SET bank_tx_id=? WHERE id=?", (tid, v["id"]))
                n_fix += 1
                continue
        rest.append(t)
    r = _next(rest) if rest else {"ok": True, "bezahlt": 0, "ausgaben": 0, "einnahmen": 0}
    r["ausgaben"] = r.get("ausgaben", 0) + n_fix
    r["fixkosten"] = n_fix
    return r


# ---------------- suggestions from belege ----------------

def _fix_classify(gaps):
    for iv, lo, hi in (("monatlich", 25, 36), ("quartalsweise", 80, 100), ("halbjaehrlich", 170, 195), ("jaehrlich", 350, 380)):
        if len(gaps) < 2:
            return None
        ok = [g for g in gaps if lo <= g <= hi]
        if len(ok) >= max(2, math.ceil(len(gaps) * 0.75)):
            return iv
    return None


def fix_suggest(rows=None, skip_existing=True):
    """Recurring expenses from belege: same partner, similar amount (+-5 %), regular gap, >= 3 times."""
    if rows is None:
        rows = [dict(r) for r in q("SELECT id, datum, partner, betrag, kategorie FROM belege WHERE typ='ausgabe' AND datum IS NOT NULL ORDER BY datum")]
    have = {norm_partner(r["partner"] or r["name"]) for r in q("SELECT name, partner FROM fixkosten")} if skip_existing else set()
    groups = {}
    for r in rows:
        k = norm_partner(r.get("partner") or "")
        if k and r.get("betrag"):
            groups.setdefault(k, []).append(r)
    out = []
    for k, rs in groups.items():
        if k in have or len(rs) < 3:
            continue
        # cluster by amount (several subscriptions of the same supplier possible)
        clusters = []
        for r in sorted(rs, key=lambda r: abs(r["betrag"])):
            for c in clusters:
                ref = c[0]["betrag"]
                if abs(abs(r["betrag"]) - abs(ref)) <= abs(ref) * 0.05:
                    c.append(r)
                    break
            else:
                clusters.append([r])
        for c in clusters:
            if len(c) < 3:
                continue
            c.sort(key=lambda r: r["datum"])
            ds = [d_iso(r["datum"]) for r in c if d_iso(r["datum"])]
            gaps = [(b - a).days for a, b in zip(ds, ds[1:]) if (b - a).days > 0]
            iv = _fix_classify(gaps)
            if not iv:
                continue
            last = c[-1]
            kats = {}
            for r in c:
                kats[r.get("kategorie") or ""] = kats.get(r.get("kategorie") or "", 0) + 1
            kat = max(kats, key=kats.get) or "Sonstige Betriebsausgaben"
            nx = d_iso(fix_next(last["datum"], iv))
            while nx and nx < datetime.date.today():
                nx = d_iso(fix_next(nx.isoformat(), iv, last["datum"]))
            out.append({"partner": last["partner"], "name": last["partner"], "betrag": round(abs(last["betrag"]), 2), "intervall": iv,
                        "intervall_label": FIX_LABEL[iv], "kategorie": kat if kat in EUER_KATEGORIEN else "Sonstige Betriebsausgaben",
                        "anzahl": len(c), "letzte": last["datum"], "naechste": nx.isoformat() if nx else "", "start": c[0]["datum"]})
    out.sort(key=lambda s: (-s["anzahl"], s["partner"] or ""))
    return out


# ---------------- export ----------------

def ex_fixkosten(p):
    rows = []
    for f in fix_list():
        rows.append([f["name"], f["partner"] or "", f["kategorie"] or "", FIX_LABEL.get(f["intervall"], f["intervall"]), f["betrag"] or 0.0,
                     f["monatlich"], f["naechste"] or "", f["start"] or "", f["ende"] or "", "ja" if f["aktiv"] else "nein", f["notiz"] or ""])
    akt = [f for f in fix_list() if f["aktiv"]]
    sh1 = _sh("Fixkosten", [("Name", "t", 24), ("Lieferant", "t", 22), ("EÜR-Kategorie", "t", 26), ("Intervall", "t", 13), ("Betrag", "m", 12),
                            ("je Monat", "m", 11), ("Nächste Fälligkeit", "d", 13), ("Start", "d", 11), ("Ende", "d", 11), ("Aktiv", "t", 7),
                            ("Notiz", "t", 24)], rows,
              f"{len(akt)} aktiv · {money(sum(f['monatlich'] for f in akt))} je Monat · {money(sum(f['monatlich'] for f in akt) * 12)} im Jahr")
    vm = [[v["faellig"], v["name"], v["partner"] or "", v["kategorie"] or "", v["betrag"] or 0.0] for v in fix_vormerk_list("offen")]
    out = [sh1]
    if vm:
        out.append(_sh("Vorgemerkt (noch nicht gebucht)", [("Fällig", "d", 11), ("Name", "t", 24), ("Lieferant", "t", 22), ("EÜR-Kategorie", "t", 26),
                                                           ("Betrag", "m", 12)], vm, f"{len(vm)} zu bestätigen"))
    return out


EXPORTS["fixkosten"] = ("Fixkosten", ex_fixkosten)


# ---------------- hooks ----------------

def _fix_loop():
    while True:
        try:
            if FIX_LAST_RUN["d"] != today():
                fix_generate()
        except Exception:
            traceback.print_exc()
        time.sleep(900)


def _fix_boot(d):
    try:
        vm = fix_vormerk_list("offen")
        d["fixkosten"] = {"offen": len(vm), "summe": round(sum(v["betrag"] or 0 for v in vm), 2),
                          "monat": round(sum((f["betrag"] or 0) / FIX_INTERVALLE.get(f["intervall"], 1) for f in q("SELECT * FROM fixkosten WHERE aktiv=1")), 2)}
    except Exception:
        traceback.print_exc()


def _fix_selftest():
    errs = []
    D = datetime.date
    cases = [(("2026-01-31", "monatlich", "2026-01-31"), "2026-02-28"), (("2026-02-28", "monatlich", "2026-01-31"), "2026-03-31"),
             (("2026-11-15", "quartalsweise", None), "2027-02-15"), (("2026-08-31", "halbjaehrlich", None), "2027-02-28"),
             (("2024-02-29", "jaehrlich", "2024-02-29"), "2025-02-28"), (("2025-02-28", "jaehrlich", "2024-02-29"), "2026-02-28")]
    for (a, iv, st), want in cases:
        got = fix_next(a, iv, st)
        if got != want:
            errs.append(f"Fixkosten: Fälligkeit {a} {iv} -> {got}, erwartet {want}")
    if _fix_classify([30, 31, 29, 31]) != "monatlich" or _fix_classify([91, 92]) != "quartalsweise" or _fix_classify([30, 90, 12]) is not None:
        errs.append("Fixkosten: Intervall-Erkennung fehlerhaft")
    v = [{"id": 1, "betrag": 23.79, "faellig": "2026-03-01", "partner": "Adobe Systems", "name": "Adobe CC", "kategorie": "Software / Lizenzen"}]
    if not fix_match_tx({"betrag": -23.79, "datum": "2026-03-04", "name": "ADOBE *CREATIVE", "zweck": "Abo"}, v):
        errs.append("Fixkosten: Bankbuchung wird nicht erkannt")
    if fix_match_tx({"betrag": -25.00, "datum": "2026-03-04", "name": "ADOBE", "zweck": ""}, v) or \
            fix_match_tx({"betrag": -23.79, "datum": "2026-03-20", "name": "ADOBE", "zweck": ""}, v):
        errs.append("Fixkosten: Bankbuchung falsch zugeordnet (Betrag/Datum)")
    rows = [{"id": i, "datum": (D(2026, 1, 5) + datetime.timedelta(days=30 * i)).isoformat(), "partner": "Adobe", "betrag": 23.79,
             "kategorie": "Software / Lizenzen"} for i in range(4)]
    try:
        if not any(s["intervall"] == "monatlich" for s in fix_suggest(rows, False)):
            errs.append("Fixkosten: Vorschlag aus Belegen nicht erkannt")
    except Exception as e:
        errs.append("Fixkosten: Vorschlag Fehler " + str(e))
    return errs


def _fix_post(fn):
    def h_(h, d):
        r = fn(d)
        return h._send(200, dict({"ok": True}, **(r or {})))
    return h_


HOOK_SCHEMA.append(_fix_schema)
HOOK_BOOT.append(_fix_boot)
HOOK_START.append(_fix_loop)
HOOK_SELFTEST.append(_fix_selftest)
HOOK_GET["/api/fixkosten"] = lambda h, qs: h._send(200, {"liste": fix_list(), "vormerk": fix_vormerk_list("offen"),
                                                          "erledigt": [dict(r) for r in q("SELECT * FROM fixkosten_vormerk WHERE status!='offen' ORDER BY erledigt DESC LIMIT 30")],
                                                          "intervalle": [{"id": k, "label": FIX_LABEL[k]} for k in FIX_INTERVALLE]})
HOOK_GET["/api/fixkosten/vorschlaege"] = lambda h, qs: h._send(200, fix_suggest())
HOOK_POST["/api/fixkosten/save"] = _fix_post(lambda d: {"id": fix_save(d)})
HOOK_POST["/api/fixkosten/delete"] = _fix_post(lambda d: fix_delete(d["id"]))
HOOK_POST["/api/fixkosten/confirm"] = _fix_post(lambda d: {"beleg_id": fix_confirm(d["id"], d.get("datum"), d.get("betrag"))})
HOOK_POST["/api/fixkosten/skip"] = _fix_post(lambda d: fix_skip(d["id"]))
