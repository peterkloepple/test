# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m52_ku_waechter
# Kleinunternehmer-Waechter (par. 19 UStG, Grenzen ab 2025: Vorjahr 25.000 EUR, laufendes Jahr 100.000 EUR).
# Hochrechnung des Jahresumsatzes + Warnung beim Speichern einer Rechnung.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M52_GRENZE_VJ = 25000.0
M52_GRENZE_LJ = 100000.0
M52_HINWEIS = ("Vereinfachte Berechnung nach Rechnungsdatum (wie die Dashboard-Karte). Maßgeblich ist der Gesamtumsatz nach § 19 UStG "
               "- bitte im Zweifel mit dem Steuerberater klären.")


def m52_umsatz(year, exclude_id=None, bis=None):
    ys = str(year)
    sql = f"SELECT COALESCE(SUM(summe),0) s FROM invoices WHERE substr(datum,1,4)=? AND {COUNT_SQL}"
    args = [ys]
    if exclude_id:
        sql += " AND id!=?"
        args.append(int(exclude_id))
    if bis:
        sql += " AND datum<=?"
        args.append(bis)
    inv = q(sql, args, one=True)["s"]
    sql2 = "SELECT COALESCE(SUM(betrag),0) s FROM belege WHERE typ='einnahme' AND substr(datum,1,4)=?"
    args2 = [ys]
    if bis:
        sql2 += " AND datum<=?"
        args2.append(bis)
    other = q(sql2, args2, one=True)["s"]
    return round(float(inv or 0) + float(other or 0), 2)


def m52_stufe(wert, grenze):
    p = wert / grenze * 100 if grenze else 0
    if p > 100:
        return "kritisch", p
    if p >= 85:
        return "warnung", p
    if p >= 70:
        return "hinweis", p
    return "ok", p


def ku_prognose(year=None, mit_angeboten=False, ref_date=None):
    import calendar
    t = ref_date or datetime.date.today()
    year = int(year or t.year)
    start = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)
    closed = t.year > year      # v2.6.3: a finished year has its real revenue - no projection
    if t.year > year:
        t = end
    elif t.year < year:
        t = start
    days_total = (end - start).days + 1
    days_gone = max(1, (t - start).days + 1)
    bisher = m52_umsatz(year)
    vj = m52_umsatz(year - 1)
    # pipeline: open offers (not expired) and open order confirmations
    ang = q("SELECT COALESCE(SUM(summe),0) s, COUNT(*) n FROM invoices WHERE typ='angebot' AND status='offen' "
            "AND (gueltig_bis IS NULL OR gueltig_bis='' OR gueltig_bis>=?)", (today(),), one=True)
    auf = q("SELECT COALESCE(SUM(summe),0) s, COUNT(*) n FROM invoices WHERE typ='auftrag' AND status NOT IN ('erledigt','storniert','entwurf')", one=True)
    pipeline = round(float(ang["s"] or 0) + float(auf["s"] or 0), 2)
    # 1) linear by days
    # v2.0.6: linear projections only after the first month (3 Jan + 1 invoice gave 182,500 EUR "forecast")
    lin = (round(bisher / days_gone * days_total, 2) if days_gone >= 30 else None) if t.year == year else bisher
    # 2) linear by completed months (more stable at month start)
    mon_done = t.month - 1 + (t.day / ((add_months(datetime.date(t.year, t.month, 1), 1) - datetime.timedelta(days=1)).day))
    lin_m = round(bisher / mon_done * 12, 2) if mon_done >= 1 and t.year == year else lin
    # 3) seasonal profile of the previous year
    # v2.6.3: same day of the previous year (was cut to the 28th -> projection too high from the 29th on)
    vj_bis = m52_umsatz(year - 1, bis=f"{year - 1}-{t.month:02d}-{min(t.day, calendar.monthrange(year - 1, t.month)[1]):02d}")
    saison = None
    if vj > 0 and vj_bis / vj >= 0.05 and t.year == year and not closed:
        saison = round(bisher / (vj_bis / vj), 2)
    cands = [bisher] if closed else ([v for v in (lin, lin_m, saison) if v is not None] or [bisher])
    prognose = round(max(cands), 2)
    lin = bisher if lin is None else lin        # numbers for display/selftest; early January = Stand bisher
    lin_m = bisher if lin_m is None else lin_m
    if mit_angeboten and not closed:
        prognose = round(max(prognose, bisher + pipeline), 2)
    st_lj, p_lj = m52_stufe(bisher, M52_GRENZE_LJ)
    st_pr, p_pr = m52_stufe(prognose, M52_GRENZE_LJ)
    warn = []
    if vj > M52_GRENZE_VJ:
        warn.append({"stufe": "kritisch", "text": f"Umsatz {year - 1} lag bei {money(vj)} und damit über {money(M52_GRENZE_VJ)}: "
                                                   f"Die Kleinunternehmerregelung ist für {year} voraussichtlich nicht anwendbar."})
    if bisher > M52_GRENZE_LJ:
        warn.append({"stufe": "kritisch", "text": f"Der Umsatz {year} liegt über {money(M52_GRENZE_LJ)}. Seit 2025 entfällt die Befreiung "
                                                   "bereits ab dem Umsatz, mit dem die Grenze überschritten wird - ab da Umsatzsteuer berechnen."})
    elif prognose > M52_GRENZE_LJ:
        warn.append({"stufe": "warnung", "text": f"Hochrechnung {money(prognose)} überschreitet {money(M52_GRENZE_LJ)} - "
                                                  "rechtzeitig vorbereiten (Rechnungen mit USt, Voranmeldungen)."})
    if bisher > M52_GRENZE_VJ and year == datetime.date.today().year:
        warn.append({"stufe": "warnung", "text": f"Umsatz {year} bereits über {money(M52_GRENZE_VJ)}: Für {year + 1} ist die "
                                                  "Kleinunternehmerregelung voraussichtlich nicht mehr möglich (Vorjahresgrenze)."})
    elif prognose > M52_GRENZE_VJ and year == datetime.date.today().year:
        warn.append({"stufe": "hinweis", "text": f"Hochrechnung {money(prognose)} liegt über {money(M52_GRENZE_VJ)}: Wird das erreicht, "
                                                  f"gilt {year + 1} voraussichtlich die Regelbesteuerung."})
    gesamt = "ok"
    for w in warn:
        if ["ok", "hinweis", "warnung", "kritisch"].index(w["stufe"]) > ["ok", "hinweis", "warnung", "kritisch"].index(gesamt):
            gesamt = w["stufe"]
    return {"year": year, "stichtag": t.isoformat(), "bisher": bisher, "vorjahr": vj, "vorjahr_bis_stichtag": vj_bis,
            "linear_tage": lin, "linear_monate": lin_m, "saison_vj": saison, "pipeline": pipeline,
            "pipeline_info": f"{ang['n']} Angebot(e), {auf['n']} Auftrag/Aufträge", "mit_angeboten": bool(mit_angeboten),
            "prognose": prognose, "grenze_lj": M52_GRENZE_LJ, "grenze_vj": M52_GRENZE_VJ,
            "stufe_bisher": st_lj, "pct_bisher": round(p_lj, 1), "stufe_prognose": st_pr, "pct_prognose": round(p_pr, 1),
            "pct_prognose_vj": round(prognose / M52_GRENZE_VJ * 100, 1), "stufe": gesamt, "warnungen": warn,
            "rest_bis_grenze": round(M52_GRENZE_LJ - bisher, 2), "hinweis": M52_HINWEIS}


def ku_check_invoice(d):
    """d: {id, summe, datum, typ, status} -> warnings if THIS invoice crosses a limit (hint only, never blocks)"""
    typ = d.get("typ") or "rechnung"
    if typ not in ("rechnung", "storno"):
        return {"warnungen": []}
    summe = float(d.get("summe") or 0)
    dd = d_iso(d.get("datum")) or datetime.date.today()
    year = dd.year
    vorher = m52_umsatz(year, exclude_id=d.get("id"))
    nachher = round(vorher + summe, 2)
    vj = m52_umsatz(year - 1)
    w = []
    if summe > 0 and nachher > M52_GRENZE_LJ:
        if vorher <= M52_GRENZE_LJ:
            w.append(f"Mit dieser Rechnung ({money(summe)}) steigt der Umsatz {year} von {money(vorher)} auf {money(nachher)} und "
                     f"überschreitet die Grenze von {money(M52_GRENZE_LJ)}. Seit 2025 entfällt die Kleinunternehmerbefreiung bereits "
                     "für den Umsatz, mit dem die Grenze überschritten wird - diese Rechnung müsste dann voraussichtlich mit "
                     "Umsatzsteuer ausgestellt werden.")
        else:
            w.append(f"Der Umsatz {year} liegt bereits über {money(M52_GRENZE_LJ)} ({money(vorher)}). Rechnungen ohne Umsatzsteuer "
                     "sind dann voraussichtlich nicht mehr zulässig.")
    if summe > 0 and vorher <= M52_GRENZE_VJ < nachher:
        w.append(f"Mit dieser Rechnung überschreitet der Umsatz {year} {money(M52_GRENZE_VJ)} ({money(nachher)}). "
                 f"Für {year + 1} ist die Kleinunternehmerregelung dann voraussichtlich nicht mehr möglich.")
    if vj > M52_GRENZE_VJ:
        w.append(f"Hinweis: Der Umsatz {year - 1} lag über {money(M52_GRENZE_VJ)} - die Kleinunternehmerregelung gilt {year} "
                 "voraussichtlich nicht.")
    if w:
        w.append("Bitte mit dem Steuerberater klären. Die Rechnung kann trotzdem gespeichert werden.")
    return {"warnungen": w, "vorher": vorher, "nachher": nachher}


def m52_route_prognose(h, qs):
    return h._send(200, ku_prognose(int(qs["year"]) if qs.get("year") else None, qs.get("angebote") in ("1", "true")))


def m52_route_check(h, d):
    return h._send(200, ku_check_invoice(d))


HOOK_GET["/api/m52/prognose"] = m52_route_prognose
HOOK_POST["/api/m52/check"] = m52_route_check


def m52_selftest():
    err = []
    try:
        p = ku_prognose()
        for k in ("bisher", "prognose", "linear_tage", "linear_monate"):
            if not isinstance(p[k], (int, float)):
                err.append(f"m52: {k} fehlt")
        if p["prognose"] + 0.01 < p["bisher"]:
            err.append("m52: Prognose kleiner als bisheriger Umsatz")
        # fixed reference date: 30.06. of a year with 50.000 -> linear about 100.800
        p2 = ku_prognose(2030, ref_date=datetime.date(2030, 6, 30))
        if p2["bisher"] != 0 or p2["prognose"] != 0:
            err.append("m52: leeres Jahr 2030 liefert Umsatz")
        c = ku_check_invoice({"summe": M52_GRENZE_LJ + 1, "datum": "2030-05-01", "typ": "rechnung"})
        if not c["warnungen"]:
            err.append("m52: Grenzüberschreitung 100.000 nicht erkannt")
        c = ku_check_invoice({"summe": 10, "datum": "2030-05-01", "typ": "rechnung"})
        if c["warnungen"]:
            err.append("m52: falsche Warnung bei kleiner Rechnung")
    except Exception as e:
        err.append(f"m52 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m52_selftest)
