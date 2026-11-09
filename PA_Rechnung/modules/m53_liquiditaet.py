# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m53_liquiditaet
# Liquiditaetsvorschau ueber ca. 3 Monate: Kontostand + erwartete Zahlungen.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import calendar

M53_DEFAULTS = {"min_reserve": 1000.0, "gehalt_netto": 0.0, "gehalt_tag": 0, "privat_monat": 0.0, "privat_tag": 1,
                "ruecklage": True, "tage": 92}


def m53_cfg():
    c = dict(M53_DEFAULTS)
    c.update(get_settings().get("m53_liq") or {})
    return c


def _m53_day(y, m, d):
    last = (add_months(datetime.date(y, m, 1), 1) - datetime.timedelta(days=1)).day
    return datetime.date(y, m, max(1, min(int(d or 1), last)))


def m53_delays():
    """average days between due date and payment per customer (from paid history)"""
    per, allv = {}, []
    for r in q("SELECT customer_id, datum, frist, bezahlt_am FROM invoices WHERE typ='rechnung' AND status='bezahlt' "
               "AND bezahlt_am IS NOT NULL AND bezahlt_am!='' AND COALESCE(source,'')!='import' ORDER BY datum DESC LIMIT 400"):
        d0, d1 = d_iso(r["datum"]), d_iso(r["bezahlt_am"])
        if not d0 or not d1:
            continue
        fr_ = _frist(r["frist"])
        delay = (d1 - (d0 + datetime.timedelta(days=fr_))).days
        delay = max(-fr_, min(120, delay))
        per.setdefault(r["customer_id"], []).append(delay)
        allv.append(delay)
    out = {k: round(sum(v[:12]) / len(v[:12])) for k, v in per.items() if v}
    out["_all"] = round(sum(allv) / len(allv)) if allv else 0
    out["_n"] = len(allv)
    return out


def m53_offen(r):
    """still outstanding amount of an open invoice (partial payments / Skonto / write-offs of m71 deducted)"""
    try:
        if "m71_state" in globals():
            return float(m71_state(dict(r))["rest"])
    except Exception:
        traceback.print_exc()
    return float(r["summe"] or 0)


def m53_fixkosten_table():
    """read fixkosten table of the colleague module (m34) if it exists - columns are detected at runtime"""
    if not q("SELECT name FROM sqlite_master WHERE type='table' AND name='fixkosten'", one=True):
        return None
    cols = {r["name"] for r in q("PRAGMA table_info(fixkosten)")}
    pick = lambda r, names: next((r[n] for n in names if n in cols and r.get(n) not in (None, "")), None)
    out = []
    for r in q("SELECT * FROM fixkosten"):
        if "aktiv" in cols and str(r.get("aktiv")) in ("0", "False", "false"):
            continue
        try:
            betrag = abs(float(pick(r, ("betrag", "amount", "kosten", "preis", "summe")) or 0))
        except Exception:
            betrag = 0
        if not betrag:
            continue
        name = str(pick(r, ("bezeichnung", "name", "partner", "titel", "anbieter")) or "Fixkosten")
        iv = pick(r, ("intervall", "intervall_monate", "rhythmus", "turnus", "periode"))
        months = 1
        if isinstance(iv, (int, float)) and iv:
            months = int(iv)
        elif isinstance(iv, str):
            low = iv.lower().replace("ä", "ae")
            known = globals().get("FIX_INTERVALLE") or {}
            if low in known:
                months = int(known[low])
            elif "halb" in low:
                months = 6
            elif "jahr" in low or "jaehr" in low:
                months = 12
            elif "quart" in low:
                months = 3
            elif "woch" in low:
                months = 0
            else:
                months = int(re.sub(r"\D", "", low)) if re.sub(r"\D", "", low) else 1
        nx = d_iso(str(pick(r, ("naechste", "naechste_faelligkeit", "faellig", "faellig_am", "start", "beginn", "datum")) or ""))
        tag = pick(r, ("tag", "zahltag", "faelligkeitstag"))
        ende = d_iso(str(pick(r, ("ende", "bis", "gueltig_bis")) or ""))
        st = d_iso(str(pick(r, ("start", "beginn")) or ""))
        anker = nx.day if nx else None
        if nx and st and nx.day == min(st.day, calendar.monthrange(nx.year, nx.month)[1]):
            anker = st.day      # due date was cut to the month end (e.g. start 31.01. -> 28.02.)
        out.append({"name": name, "betrag": betrag, "months": months, "next": nx, "tag": int(tag) if str(tag or "").isdigit() else None,
                    "ende": ende, "anker": anker})
    return out


def m53_fixkosten_schaetzung(ref):
    """recurring expenses guessed from belege of the last 12 months (same partner, >=3 months, similar amount)"""
    since = (ref - datetime.timedelta(days=370)).isoformat()
    groups = {}
    for r in q("SELECT datum, partner, betrag FROM belege WHERE typ='ausgabe' AND datum>=? AND betrag>0", (since,)):
        key = re.sub(r"[^a-z0-9äöüß]", "", (r["partner"] or "").lower())[:24]
        if len(key) < 3:
            continue
        groups.setdefault(key, {"name": r["partner"], "rows": []})["rows"].append(r)
    out = []
    for g in groups.values():
        rows = sorted(g["rows"], key=lambda r: r["datum"])
        months = {r["datum"][:7] for r in rows}
        if len(months) < 3:
            continue
        amts = [float(r["betrag"]) for r in rows[-6:]]
        mean = sum(amts) / len(amts)
        sd = (sum((a - mean) ** 2 for a in amts) / len(amts)) ** 0.5
        if mean <= 0 or sd / mean > 0.25:
            continue
        last = d_iso(rows[-1]["datum"])
        if last and (ref - last).days > 75:
            continue
        days = sorted(int(r["datum"][8:10]) for r in rows[-6:])
        out.append({"name": g["name"], "betrag": round(sorted(amts)[len(amts) // 2], 2), "months": 1, "next": None,
                    "tag": days[len(days) // 2], "ende": None})
    return out


def m53_gehalt(cfg, ref):
    netto, tag, quelle = float(cfg.get("gehalt_netto") or 0), int(cfg.get("gehalt_tag") or 0), "Einstellung"
    if not netto:
        vals = []
        for r in q("SELECT datum, details FROM belege WHERE typ='gehalt' ORDER BY datum DESC LIMIT 6"):
            dd = json.loads(r["details"] or "{}")
            if dd.get("zeitraum") == "jahr":
                continue
            v = float(dd.get("netto") or 0)
            if v > 0:
                vals.append(v)
        if vals:
            vals = vals[:3]
            netto = round(sum(vals) / len(vals), 2)
            quelle = f"Ø der letzten {len(vals)} Gehaltsabrechnung(en)"
    if netto and not tag:
        # payday from bank: incoming amounts close to the net salary
        hits = q("SELECT datum FROM bank_tx WHERE betrag BETWEEN ? AND ? ORDER BY datum DESC LIMIT 6", (netto * 0.97, netto * 1.03))
        if hits:
            ds = sorted(int(h["datum"][8:10]) for h in hits)
            tag = ds[len(ds) // 2]
            quelle += ", Zahltag aus Kontoauszug"
        else:
            tag = 28
            quelle += ", Zahltag angenommen (28.)"
    return netto, tag, quelle


def liq_build(start, events, d0, days):
    """pure function: start balance + events -> daily series, minimum, weekly table"""
    end = d0 + datetime.timedelta(days=days)
    per = {}
    for e in events:
        d = d_iso(e["datum"])
        if d and d0 <= d <= end:
            per[d] = per.get(d, 0.0) + e["betrag"]
    series, saldo = [], round(start, 2)
    mn = {"datum": d0.isoformat(), "saldo": saldo}
    for i in range(days + 1):
        d = d0 + datetime.timedelta(days=i)
        saldo = round(saldo + per.get(d, 0.0), 2)
        series.append({"d": d.isoformat(), "saldo": saldo})
        if saldo < mn["saldo"]:
            mn = {"datum": d.isoformat(), "saldo": saldo}
    weeks = []
    for i in range(0, days + 1, 7):
        a = d0 + datetime.timedelta(days=i)
        b = min(end, a + datetime.timedelta(days=6))
        ein = round(sum(v for d, v in per.items() if a <= d <= b and v > 0), 2)
        aus = round(sum(v for d, v in per.items() if a <= d <= b and v < 0), 2)
        weeks.append({"von": a.isoformat(), "bis": b.isoformat(), "ein": ein, "aus": aus,
                      "saldo": next(s["saldo"] for s in series if s["d"] == b.isoformat())})
    return {"series": series, "min": mn, "weeks": weeks, "ende": series[-1]["saldo"]}


def liq_forecast(nur_sicher=False, ruecklage=None, start_override=None, ref_date=None):
    cfg = m53_cfg()
    t = ref_date or datetime.date.today()
    days = int(cfg.get("tage") or 92)
    end = t + datetime.timedelta(days=days)
    use_rl = cfg.get("ruecklage", True) if ruecklage is None else bool(ruecklage)
    k = kontostand_info()
    if start_override is not None:
        start, sinfo = float(start_override), "manuell eingegeben"
    elif k:
        start = float(k["geschaetzt"])
        sinfo = f"Kontostand {de_date(k['datum'])}" + (f" + {k['nachher_n']} spätere Umsätze" if k.get("nachher_n") else "")
    else:
        start, sinfo = 0.0, "kein Kontostand erfasst - Start bei 0 EUR"
    s = get_settings()
    dl = m53_delays()
    ev = []

    def add(d, betrag, art, text, sicher, link=None):
        if d is None:
            return
        if isinstance(d, datetime.date):
            d = d.isoformat()
        ev.append({"datum": d, "betrag": round(betrag, 2), "art": art, "text": text, "sicher": bool(sicher), "link": link})

    # 1) open invoices (and open refunds of storno invoices)
    for r in q("SELECT * FROM invoices WHERE typ IN ('rechnung','storno') AND status='offen'"):
        d0 = d_iso(r["datum"]) or t
        due = d0 + datetime.timedelta(days=_frist(r["frist"]))
        delay = dl.get(r["customer_id"], dl["_all"])
        betrag = m53_offen(r)
        if abs(betrag) < 0.005:
            continue
        exp = due + datetime.timedelta(days=max(0, delay))
        txt = f"{r['nr']} {inv_name(r)}"
        if exp < t:
            exp = t + datetime.timedelta(days=7)
            txt += " (überfällig, angenommen in 7 Tagen)"
        elif delay > 0:
            txt += f" (fällig {de_date(due.isoformat())}, Kunde zahlt Ø {delay} Tage später)"
        if abs(betrag - float(r["summe"] or 0)) >= 0.005:
            txt += f" (Rest nach Teilzahlung, Rechnung {money(r['summe'])})"
        add(exp, betrag, "Offene Rechnung" if r["typ"] == "rechnung" else "Erstattung Storno", txt,
            r["typ"] == "storno", {"inv": r["id"]})
    # 2) drafts waiting for completion
    for r in q("SELECT * FROM invoices WHERE typ='rechnung' AND status='entwurf'"):
        exp = t + datetime.timedelta(days=_frist(r["frist"]) + max(0, dl.get(r["customer_id"], dl["_all"])) + 3)
        add(exp, r["summe"], "Entwurf", f"Entwurf {inv_name(r)} ({r['source'] or 'app'})", False, {"inv": r["id"]})
    # 3) recurring invoices
    for r in q("SELECT r.*, i.summe src_summe, i.frist src_frist, i.customer_id cid FROM recurring r LEFT JOIN invoices i ON i.id=r.invoice_id WHERE r.aktiv=1"):
        nx = d_iso(r["naechstes"])
        n = 0
        while nx and nx <= end and n < 40:
            pay = nx + datetime.timedelta(days=_frist(r["src_frist"]) + max(0, dl.get(r["cid"], dl["_all"])))
            if t <= pay <= end:
                add(pay, float(r["src_summe"] or 0), "Abo-Rechnung", f"{r['name'] or 'Abo'} (Rechnung am {de_date(nx.isoformat())})", False)
            nx = add_months(nx, int(r["intervall"] or 1))
            n += 1
    # 4) maintenance contracts
    for v in q("SELECT * FROM vertraege WHERE aktiv=1"):
        preis = float(v["preis"] or 0)
        if not preis and v["article_id"]:
            a = q("SELECT price FROM articles WHERE id=?", (v["article_id"],), one=True)
            preis = float((a or {}).get("price") or 0)
        nx = d_iso(v["naechste"])
        n = 0
        while preis and nx and nx <= end and n < 40:
            pay = max(nx, t) + datetime.timedelta(days=_frist(s.get("frist")) + max(0, dl.get(v["customer_id"], dl["_all"])))
            if pay <= end:
                add(pay, preis, "Wartungsvertrag", f"{v['name']} (Termin {de_date(nx.isoformat())})", False)
            nx = add_months(nx, int(v["intervall"] or 12))
            n += 1
    # 5) teaching: average of the last 3 complete months, billed at the start of each month
    ms = [add_months(datetime.date(t.year, t.month, 1), -i) for i in (1, 2, 3)]
    tot = sum(float(q("SELECT COALESCE(SUM(summe),0) s FROM invoices WHERE source='unterricht' AND typ='rechnung' AND substr(datum,1,7)=?",
                      (m.isoformat()[:7],), one=True)["s"]) for m in ms)
    if tot > 0:
        avg = round(tot / 3, 2)
        m = datetime.date(t.year, t.month, 1)
        while m <= end:
            billed = q("SELECT id FROM invoices WHERE source='unterricht' AND substr(datum,1,7)=? LIMIT 1", (m.isoformat()[:7],), one=True)
            pay = m + datetime.timedelta(days=3 + _frist(s.get("frist")) + max(0, dl["_all"]))
            if not billed and t <= pay <= end:
                add(pay, avg, "Unterricht", f"Unterricht {MONTHS_LONG[(m.month - 2) % 12]} (Ø letzte 3 Monate)", False)
            m = add_months(m, 1)
    # 6) salary
    netto, tag, gq = m53_gehalt(cfg, t)
    if netto:
        m = datetime.date(t.year, t.month, 1)
        while m <= end:
            d = _m53_day(m.year, m.month, tag)
            if t <= d <= end:
                add(d, netto, "Gehalt", f"Gehalt netto ({gq})", True)
            m = add_months(m, 1)
    # 7) fixed costs
    fk = m53_fixkosten_table()
    fk_src = "Fixkosten-Tabelle"
    if not fk:
        fk = m53_fixkosten_schaetzung(t)
        fk_src = "geschätzt aus wiederkehrenden Belegen"
    for f in fk:
        if f["months"] == 0:
            d = f["next"] or t
            while d <= end:
                if d >= t:
                    add(d, -f["betrag"], "Fixkosten", f"{f['name']} (wöchentlich, {fk_src})", True)
                d += datetime.timedelta(days=7)
            continue
        # v2.6.3: every due date is derived from a fixed anchor day (before: add_months kept the cut day,
        # a cost due on the 31st stayed on the 28th after February)
        mon = f["months"] or 1
        anchor = f["tag"] or f.get("anker") or (f["next"].day if f["next"] else 1)
        if f["next"]:
            base = datetime.date(f["next"].year, f["next"].month, 1)
            k, d = 0, f["next"]
            while d < t:
                k += 1
                mb = add_months(base, k * mon)
                d = _m53_day(mb.year, mb.month, anchor)
        else:
            d = _m53_day(t.year, t.month, anchor)
            k, base = 0, datetime.date(t.year, t.month, 1)
            if d < t:
                k = 1
                mb = add_months(base, 1)
                d = _m53_day(mb.year, mb.month, anchor)
        n = 0
        while d <= end and n < 60:
            if f["ende"] and d > f["ende"]:
                break
            add(d, -f["betrag"], "Fixkosten", f"{f['name']} ({fk_src})", True)
            k += 1
            mb = add_months(base, k * mon)
            d = _m53_day(mb.year, mb.month, anchor)
            n += 1
    # 8) private living costs (optional setting)
    pm = float(cfg.get("privat_monat") or 0)
    if pm:
        m = datetime.date(t.year, t.month, 1)
        while m <= end:
            d = _m53_day(m.year, m.month, cfg.get("privat_tag") or 1)
            if t <= d <= end:
                add(d, -pm, "Privat", "Private Lebenshaltung / Miete (Einstellung)", True)
            m = add_months(m, 1)
    # 9) tax prepayments
    for y in sorted({t.year, end.year}):
        vz = float(tax_inputs(y).get("vorauszahlung") or 0)
        if vz:
            for mo, dd in M54_QUARTALE:
                d = datetime.date(y, mo, dd)
                if t <= d <= end:
                    add(d, -vz / 4, "Steuer", f"ESt-Vorauszahlung {mo // 3}. Quartal {y}", True)
    # 10) tax reserve (net of prepayments) on the 1st of each month
    rl_m = 0.0
    if use_rl:
        try:
            rl_m = m54_ruecklage()["monat_netto"]
        except Exception:
            traceback.print_exc()
        if rl_m > 0:
            m = add_months(datetime.date(t.year, t.month, 1), 1)
            while m <= end:
                add(m, -rl_m, "Rücklage", "Steuer-Rücklage zurücklegen (über Vorauszahlungen hinaus)", True)
                m = add_months(m, 1)
    if nur_sicher:
        ev = [e for e in ev if e["sicher"] or e["betrag"] < 0]
    ev.sort(key=lambda e: (e["datum"], -e["betrag"]))
    res = liq_build(start, ev, t, days)
    minres = float(cfg.get("min_reserve") or 0)
    warn = []
    below = next((p for p in res["series"] if p["saldo"] < minres), None)
    if below:
        warn.append(f"Am {de_date(below['d'])} fällt der Kontostand voraussichtlich unter die Mindestreserve von {money(minres)} "
                    f"(tiefster Stand {money(res['min']['saldo'])} am {de_date(res['min']['datum'])}).")
    if res["min"]["saldo"] < 0:
        warn.append("Der Kontostand wird in diesem Szenario negativ - Zahlungseingänge nachhalten oder Ausgaben verschieben.")
    if not k and start_override is None:
        warn.append("Kein Kontostand erfasst - bitte im Dashboard bzw. Bank-Abgleich eintragen, sonst startet die Vorschau bei 0 EUR.")
    return dict(res, start=round(start, 2), start_info=sinfo, events=ev, warnungen=warn, min_reserve=minres, nur_sicher=bool(nur_sicher),
                ruecklage=use_rl, ruecklage_monat=rl_m, gehalt={"netto": netto, "tag": tag, "quelle": gq},
                fixkosten_quelle=fk_src, zahlverhalten={"durchschnitt_tage": dl["_all"], "rechnungen": dl["_n"]},
                summe_ein=round(sum(e["betrag"] for e in ev if e["betrag"] > 0 and e["datum"] <= end.isoformat()), 2),
                summe_aus=round(sum(e["betrag"] for e in ev if e["betrag"] < 0 and e["datum"] <= end.isoformat()), 2),
                cfg=cfg, stichtag=t.isoformat())


def m53_route_get(h, qs):
    so = qs.get("start")
    return h._send(200, liq_forecast(qs.get("sicher") in ("1", "true"),
                                     None if qs.get("ruecklage") in (None, "") else qs.get("ruecklage") in ("1", "true"),
                                     pnum_py(so) if so not in (None, "") else None))


def pnum_py(v):
    """the UI sends a JS number as text ("1234.567"); German input ("1.234,56") is parsed as amount"""
    try:
        return float(str(v).strip())
    except ValueError:
        return parse_amount(str(v))


def m53_route_cfg(h, d):
    c = m53_cfg()
    for k_, v in (d or {}).items():
        if k_ in M53_DEFAULTS:
            c[k_] = type(M53_DEFAULTS[k_])(v) if not isinstance(M53_DEFAULTS[k_], bool) else bool(v)
    c["tage"] = max(14, min(int(c["tage"]), 370))
    set_setting("m53_liq", c)
    return h._send(200, {"ok": True, "cfg": c})


HOOK_GET["/api/m53/liquiditaet"] = m53_route_get
HOOK_POST["/api/m53/cfg"] = m53_route_cfg


def m53_selftest():
    err = []
    try:
        d0 = datetime.date(2030, 1, 1)
        evs = [{"datum": "2030-01-05", "betrag": 1000.0}, {"datum": "2030-01-10", "betrag": -2500.0},
               {"datum": "2030-02-01", "betrag": 300.0}, {"datum": "2031-01-01", "betrag": 99999.0}]
        r = liq_build(500.0, evs, d0, 60)
        if r["ende"] != -700.0:
            err.append(f"m53: Endsaldo falsch ({r['ende']} statt -700)")
        if r["min"] != {"datum": "2030-01-10", "saldo": -1000.0}:
            err.append(f"m53: Tiefpunkt falsch ({r['min']})")
        if len(r["series"]) != 61:
            err.append("m53: Tagesreihe hat falsche Länge")
        if abs(sum(w["ein"] + w["aus"] for w in r["weeks"]) - (-1200.0)) > 0.01:
            err.append("m53: Wochensummen falsch")
        f = liq_forecast(start_override=1000.0)
        if f["start"] != 1000.0 or not f["series"]:
            err.append("m53: Vorschau mit Datenbank fehlgeschlagen")
        f2 = liq_forecast(nur_sicher=True, start_override=1000.0)
        if any(e["betrag"] > 0 and not e["sicher"] for e in f2["events"]):
            err.append("m53: Szenario 'nur sichere Posten' enthält unsichere Einnahmen")
    except Exception as e:
        err.append(f"m53 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m53_selftest)
