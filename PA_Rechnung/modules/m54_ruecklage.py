# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m54_ruecklage
# Steuer-Ruecklage live: Hochrechnung der Steuer auf die Selbststaendigkeit (Gewinn + Gehalt aufs Jahr),
# monatlicher Ruecklagebetrag, Soll bis heute vs. bereits zurueckgelegt, Hinweis Vorauszahlungen.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M54_QUARTALE = ((3, 10), (6, 10), (9, 10), (12, 10))   # ESt-Vorauszahlungstermine


def _m54_calc(year, gewinn, sal, t):
    """same formula as tax_calc() (shared tax_core in m04), but with free profit and salary values"""
    fy = fahrten_year(year)
    wk_real = float(t["wk"] or 0) + fy["pendel_eur"] + (homeoffice_eur(t) if t.get("ho_zuordnung") == "gehalt" else 0.0)
    c = tax_core(year, gewinn, sal, t, wk_real)
    return {"zve": c["zve"], "est": c["est"], "soli": c["soli"], "kist": c["kist"], "gesamt": c["gesamt"],
            "gewst": c["gew"]["gewst"], "grenz": c["grenz"]}


def m54_zurueckgelegt(year):
    d = (get_settings().get("m54_zurueckgelegt") or {}).get(str(year)) or {}
    return {"betrag": float(d.get("betrag") or 0), "datum": d.get("datum") or "", "notiz": d.get("notiz") or ""}


def m54_ruecklage(year=None, ref_date=None):
    t0 = ref_date or datetime.date.today()
    year = int(year or t0.year)
    start, end = datetime.date(year, 1, 1), datetime.date(year, 12, 31)
    ref = min(max(t0, start), end)
    frac = ((ref - start).days + 1) / ((end - start).days + 1)
    e = euer(year)
    ti = tax_inputs(year)
    sal, emp = salary_sum(year)
    # annualize salary when only monthly slips exist
    months = q("SELECT COUNT(DISTINCT substr(datum,1,7)) n FROM belege WHERE typ='gehalt' AND substr(datum,1,4)=?", (str(year),), one=True)["n"]
    has_year_cert = any(x_["quelle"].startswith("Lohnsteuer") for x_ in emp)
    sal_f = 1.0
    if months and not has_year_cert and year == t0.year and months < 12:
        sal_f = min(12.0 / months, 12.0)
    sal_y = {k: round(v * sal_f, 2) for k, v in sal.items()}
    # annualize profit
    gewinn = float(e["gewinn"])
    basis = "lineare Hochrechnung"
    if year < t0.year or frac >= 0.999:
        hoch = gewinn
        basis = "Jahreswert"
    elif frac >= 0.15:
        hoch = gewinn / frac
    else:
        # v2.1.1: early in the year a single large payment was multiplied up to 20x - now: profit so far
        # plus the prior-year profit for the rest of the year (or at most x6.7 without a prior year)
        vj = float(euer(year - 1)["gewinn"])
        if vj > 0:
            hoch = gewinn + vj * (1 - frac)
            basis = "Jahresanfang: bisheriger Gewinn + Vorjahresgewinn anteilig für den Rest des Jahres"
        else:
            hoch = gewinn / 0.15 if gewinn > 0 else 0.0
            basis = "Jahresanfang ohne Vorjahr: vorsichtige Hochrechnung"
    hoch = round(max(hoch, 0.0) if gewinn >= 0 else hoch, 2)
    full = _m54_calc(year, hoch, sal_y, ti)
    ohne = _m54_calc(year, 0.0, sal_y, ti)
    anteil_jahr = round(max(0.0, full["gesamt"] - ohne["gesamt"] + full["gewst"]), 2)
    grenz = full["grenz"]
    vz_jahr = float(ti.get("vorauszahlung") or 0)
    vz_bisher = round(vz_jahr / 4 * sum(1 for m, d in M54_QUARTALE if datetime.date(year, m, d) <= ref), 2)
    soll_anteil = min(1.0, max(0.0, gewinn / hoch)) if hoch > 0 else frac
    soll_bis_heute = round(anteil_jahr * soll_anteil, 2)
    soll_netto = round(max(0.0, soll_bis_heute - vz_bisher), 2)
    zur = m54_zurueckgelegt(year)
    luecke = round(soll_netto - zur["betrag"], 2)
    monat = round(anteil_jahr / 12, 2)
    monat_netto = round(max(0.0, anteil_jahr - vz_jahr) / 12, 2)
    lst_y = round(sal_y["lst"] + sal_y["soli"] + sal_y["kist"], 2)
    nachzahlung = round(full["gesamt"] - lst_y - vz_jahr, 2)
    hinweise = []
    diff_vz = round(anteil_jahr - vz_jahr, 2)
    if diff_vz > max(400.0, 0.25 * vz_jahr):
        hinweise.append({"stufe": "warnung", "text": f"Die erwartete Steuer auf die Selbstständigkeit ({money(anteil_jahr)}) liegt deutlich über "
                                                      f"den Vorauszahlungen ({money(vz_jahr)}). Es droht eine Nachzahlung von etwa {money(diff_vz)}. "
                                                      "Eine Anpassung (Erhöhung) der Vorauszahlungen beim Finanzamt beantragen oder den Betrag sicher zurücklegen."})
    elif vz_jahr > 0 and vz_jahr - anteil_jahr > max(400.0, 0.25 * anteil_jahr):
        hinweise.append({"stufe": "hinweis", "text": f"Die Vorauszahlungen ({money(vz_jahr)}) liegen deutlich über der erwarteten Steuer "
                                                      f"({money(anteil_jahr)}). Eine Herabsetzung kann beim Finanzamt beantragt werden."})
    if luecke > 50:
        hinweise.append({"stufe": "warnung" if luecke > 500 else "hinweis",
                         "text": f"Bis heute sollten {money(soll_netto)} zurückgelegt sein, eingetragen sind {money(zur['betrag'])} - "
                                 f"es fehlen {money(luecke)}."})
    return {"year": year, "stichtag": ref.isoformat(), "anteil_jahr": anteil_jahr, "monat": monat, "monat_netto": monat_netto,
            "gewinn_bisher": round(gewinn, 2), "gewinn_hoch": hoch, "basis": basis, "anteil_vergangen": round(frac * 100, 1),
            "grenzsteuersatz": grenz, "gehalt_faktor": round(sal_f, 2), "gehalt_monate": months,
            "vorauszahlung_jahr": vz_jahr, "vorauszahlung_bisher": vz_bisher,
            "soll_bis_heute": soll_bis_heute, "soll_netto": soll_netto, "zurueckgelegt": zur, "luecke": luecke,
            "steuer_gesamt_jahr": full["gesamt"], "lohnsteuer_jahr": lst_y, "nachzahlung_erwartet": nachzahlung,
            "hinweise": hinweise,
            "hinweis": "Schätzung: Gewinn und Gehalt werden aufs Jahr hochgerechnet, Steuer nach § 32a EStG wie in der "
                       "Jahresabrechnung. Ersetzt keine Steuerberatung."}


def m54_route_get(h, qs):
    return h._send(200, m54_ruecklage(int(qs["year"]) if qs.get("year") else None))


def m54_route_save(h, d):
    year = str(int(d.get("year") or datetime.date.today().year))
    allv = get_settings().get("m54_zurueckgelegt") or {}
    allv[year] = {"betrag": round(float(d.get("betrag") or 0), 2), "datum": d.get("datum") or today(), "notiz": (d.get("notiz") or "")[:200]}
    set_setting("m54_zurueckgelegt", allv)
    return h._send(200, dict(m54_ruecklage(int(year)), ok=True))


HOOK_GET["/api/m54/ruecklage"] = m54_route_get
HOOK_POST["/api/m54/save"] = m54_route_save


def m54_selftest():
    err = []
    try:
        y = datetime.date.today().year
        r = m54_ruecklage(y)
        if r["anteil_jahr"] < 0 or r["monat"] < 0:
            err.append("m54: negative Rücklage")
        # formula check against tax_calc for a closed year: same inputs -> same total
        tc = tax_calc(y - 1)
        sal, _ = salary_sum(y - 1)
        c = _m54_calc(y - 1, tc["euer"]["gewinn"], sal, tax_inputs(y - 1))
        cp = tc.get("calc_programm") or tc["calc"]   # v2.6.1: calc may hold the values lt. Bescheid (m46)
        if abs(c["gesamt"] - cp["gesamt"]) > 0.01:
            err.append(f"m54: Steuerformel weicht von tax_calc ab ({c['gesamt']} / {cp['gesamt']})")
        sal0 = {k: 0.0 for k in ("brutto", "lst", "soli", "kist", "rv", "kv", "pv", "av", "netto")}
        a = _m54_calc(2026, 30000.0, sal0, tax_inputs(2099))
        if not (a["est"] > 3000 and a["est"] < 6000):
            err.append(f"m54: ESt für 30.000 EUR unplausibel ({a['est']})")
    except Exception as e:
        err.append(f"m54 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m54_selftest)
