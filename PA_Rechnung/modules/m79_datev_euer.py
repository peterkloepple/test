# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m79_datev_euer (v2.0.19)
# (a) DATEV-Export: Buchungsstapel im DATEV-Format (EXTF 700, Kategorie 21, Formatversion 13),
#     SKR03 / SKR04, Kontenzuordnung je EUER-Kategorie (vorbelegt, editierbar), Geldkonto Bank/Kasse,
#     optional Debitoren/Kreditoren, Belegdateien als ZIP (Dateiname = Belegfeld 1). cp1252, Semikolon.
# (b) Anlage EUER: Zeilen/Kennzahlen je Jahr (Tabelle im Modul + eigene Korrekturen), Ausfuellhilfe
#     "Zeile 12 (Kz 111): x EUR" in Jahresabrechnung & Steuer und im Jahresbericht-PDF.
# (c) Anlage N / Vorsorgeaufwand: Ausfuellhilfe aus den Gehaltsabrechnungen (Nummern der
#     Lohnsteuerbescheinigung) und Werbungskosten aus den Fahrten.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M79_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Kontenrahmen (Vorschlag - mit dem Steuerberater abstimmen)
# ---------------------------------------------------------------------------
M79_SKR = {
    "03": {
        "_bank": 1200, "_kasse": 1000, "_transit": 1360, "_privat_ent": 1800, "_privat_ein": 1890,
        "_erloese_ku": 8195, "_erloese_19": 8400, "_erloese_7": 8300, "_erloese_0": 8120, "_sonst_ertrag": 2700,
        "_vst": 1576, "_ust19": 1776, "_ust7": 1771, "_ust_zahlung": 1780, "_km": 4673, "_bewirt_na": 4654,
        "Waren / Material": 3200, "Fremdleistungen": 3100, "Arbeitsmittel / Equipment (GWG)": 4855,
        "Arbeitsmittel (Kleinmaterial)": 4985, "Software / Lizenzen": 4964, "Telekommunikation / Internet": 4920,
        "Fahrtkosten / Reise": 4670, "Übernachtung / Reisenebenkosten": 4676, "Raumkosten / Miete": 4210,
        "Miete / Leasing Geräte": 4960, "Werbung / Marketing": 4600, "Fortbildung / Fachliteratur": 4945,
        "Rechts- und Steuerberatung": 4950, "Bürobedarf / Porto": 4930, "Versicherungen / Beiträge": 4360,
        "Bankgebühren": 4970, "Bewirtung (70%)": 4650, "Abschreibung (AfA)": 4830, "Sonstige Betriebsausgaben": 4900,
        "Umsatzsteuer-Zahlung (Finanzamt)": 1780,
    },
    "04": {
        "_bank": 1800, "_kasse": 1600, "_transit": 1460, "_privat_ent": 2100, "_privat_ein": 2180,
        "_erloese_ku": 4185, "_erloese_19": 4400, "_erloese_7": 4300, "_erloese_0": 4120, "_sonst_ertrag": 4830,
        "_vst": 1406, "_ust19": 3806, "_ust7": 3801, "_ust_zahlung": 3820, "_km": 6673, "_bewirt_na": 6644,
        "Waren / Material": 5200, "Fremdleistungen": 5900, "Arbeitsmittel / Equipment (GWG)": 6260,
        "Arbeitsmittel (Kleinmaterial)": 6845, "Software / Lizenzen": 6837, "Telekommunikation / Internet": 6805,
        "Fahrtkosten / Reise": 6670, "Übernachtung / Reisenebenkosten": 6680, "Raumkosten / Miete": 6310,
        "Miete / Leasing Geräte": 6835, "Werbung / Marketing": 6600, "Fortbildung / Fachliteratur": 6821,
        "Rechts- und Steuerberatung": 6825, "Bürobedarf / Porto": 6815, "Versicherungen / Beiträge": 6400,
        "Bankgebühren": 6855, "Bewirtung (70%)": 6640, "Abschreibung (AfA)": 6220, "Sonstige Betriebsausgaben": 6300,
        "Umsatzsteuer-Zahlung (Finanzamt)": 3820,
    },
}
M79_KONTO_LABEL = {
    "_bank": "Geldkonto Bank", "_kasse": "Geldkonto Kasse", "_transit": "Geldtransit", "_privat_ent": "Privatentnahme",
    "_privat_ein": "Privateinlage", "_erloese_ku": "Erlöse Kleinunternehmer (§ 19)", "_erloese_19": "Erlöse 19 % USt",
    "_erloese_7": "Erlöse 7 % USt", "_erloese_0": "Erlöse steuerfrei / 0 %", "_sonst_ertrag": "Sonstige Erträge / Einnahmen",
    "_vst": "Vorsteuer", "_ust19": "Umsatzsteuer 19 %", "_ust7": "Umsatzsteuer 7 %", "_ust_zahlung": "USt-Vorauszahlung / Zahlung Finanzamt",
    "_km": "Fahrten Privat-Pkw (km-Pauschale)",
    "_bewirt_na": "Bewirtung nicht abziehbar (30 %)",
}
M79_DEFAULTS = {"berater": 0, "mandant": 0, "skr": "03", "wj_beginn": "01-01", "kontenlaenge": 4, "debitoren": False,
                "kreditoren": False, "konten": {}, "km_buchen": True, "festschreibung": False, "kuerzel": ""}

# ---------------------------------------------------------------------------
# Anlage EUER - Zeilen je Jahr. Grundlage ist EUER_FORM (Vordruck 2025, m01).
# Die Kennzahlen (Kz) bleiben ueber die Jahre meist gleich, die ZEILENNUMMERN koennen sich
# jaehrlich verschieben -> eigene Korrekturen je Jahr in den Einstellungen (m79_zeilen).
# Zusaetzliche Schluessel fuer die Regelbesteuerung (m80).
# ---------------------------------------------------------------------------
M79_FORM_EXTRA = {
    "_einnahmen_regel": (15, 112, "Umsatzsteuerpflichtige Betriebseinnahmen (netto)"),
    "_einnahmen_frei": (16, 103, "Umsatzsteuerfreie / nicht steuerbare Betriebseinnahmen"),
    "_ust_vereinnahmt": (17, 140, "Vereinnahmte Umsatzsteuer"),
    "_ust_erstattet": (18, 141, "Vom Finanzamt erstattete Umsatzsteuer"),
    "_vorsteuer": (57, 185, "Gezahlte Vorsteuerbeträge"),
    "Umsatzsteuer-Zahlung (Finanzamt)": (58, 186, "An das Finanzamt gezahlte Umsatzsteuer"),
}
M79_FORM_JAHRE = {2024: "aus Vordruck 2025 übernommen - bitte mit dem Vordruck 2024 abgleichen",
                  2025: "Vordruck 2025",
                  2026: "aus Vordruck 2025 übernommen - bitte mit dem Vordruck 2026 abgleichen"}
M79_FORM_HINWEIS = ("Die Zeilennummern der Anlage EÜR können sich jedes Jahr ändern - die Kennzahlen (Kz) bleiben meist gleich. "
                    "Bitte vor dem Übertragen mit dem amtlichen Vordruck bzw. ELSTER abgleichen und abweichende Zeilen unten korrigieren.")

# Lohnsteuerbescheinigung (Nummern bleiben seit Jahren gleich)
M79_LSTB = [("brutto", "3", "Bruttoarbeitslohn"), ("lst", "4", "Einbehaltene Lohnsteuer"),
            ("soli", "5", "Einbehaltener Solidaritätszuschlag"), ("kist", "6", "Einbehaltene Kirchensteuer Arbeitnehmer"),
            ("rv", "23a", "Arbeitnehmeranteil Rentenversicherung"), ("kv", "25", "Arbeitnehmerbeiträge Krankenversicherung"),
            ("pv", "26", "Arbeitnehmerbeiträge Pflegeversicherung"), ("av", "27", "Arbeitnehmerbeiträge Arbeitslosenversicherung")]


def m79_cfg():
    c = dict(M79_DEFAULTS)
    c.update(get_settings().get("m79") or {})
    if c.get("skr") not in M79_SKR:
        c["skr"] = "03"
    return c


def m79_konten(cfg=None):
    cfg = cfg or m79_cfg()
    k = dict(M79_SKR[cfg["skr"]])
    for kk, v in (cfg.get("konten") or {}).items():
        try:
            if str(v).strip():
                k[kk] = int(str(v).strip())
        except Exception:
            pass
    return k

# ---------------------------------------------------------------------------
# (b) Anlage EUER
# ---------------------------------------------------------------------------


def m79_form_table(year):
    base = dict(EUER_FORM)
    base.update(M79_FORM_EXTRA)
    ov = (get_settings().get("m79_zeilen") or {}).get(str(int(year))) or {}
    for k, v in ov.items():
        try:
            z, kz, lbl = v
            o = base.get(k) or (0, 0, k)
            base[k] = (int(z) if str(z).strip() else o[0], int(kz) if str(kz).strip() else o[1], str(lbl or o[2]))
        except Exception:
            pass
    return base


_m79_orig_euer_form = chain_inner("euer_form", "m79_datev_euer")   # v3.0.0: the level below this module (was: the function before the wrapper)
@chain_step("euer_form", "m79_datev_euer")
def _m79_step_euer_form(_next, year):
    """same result as before for a pure Kleinunternehmer year without own corrections (2025 table);
    with corrections the year table is used, with Regelbesteuerung (m80) income/expenses are split net/USt/VSt"""
    year = int(year)
    ov = (get_settings().get("m79_zeilen") or {}).get(str(year))
    split = None
    if "m80_euer_split" in globals():
        try:
            split = m80_euer_split(year)
        except Exception:
            traceback.print_exc()
            split = None
    if not ov and not split:
        return _next(year)
    tab = m79_form_table(year)
    e = euer(year)
    lines = {}

    def add(key, v):
        if not v:
            return
        z, kz, lbl = tab.get(key, tab["Sonstige Betriebsausgaben"])
        k = (z, kz)
        lines.setdefault(k, [z, kz, lbl, 0.0])
        lines[k][3] = round(lines[k][3] + v, 2)
    if split:
        add("_einnahmen_ku", split["ein_ku"])
        add("_einnahmen_regel", split["ein_netto"])
        add("_einnahmen_frei", split["ein_frei"])
        add("_ust_vereinnahmt", split["ust"])
        add("_ust_erstattet", split["ust_erstattet"])
        for k, v in split["kategorien_netto"].items():
            add(k, v)
        add("_vorsteuer", split["vorsteuer"])
    else:
        add("_einnahmen_ku", e["einnahmen"])
        for k, v in e["kategorien"].items():
            add(k, v)
    out = sorted(lines.values(), key=lambda r: (r[0], r[1]))
    # Regelbesteuerung: euer() (m80) already counts Bewirtung with 70 % net + full Vorsteuer - total and profit
    # match the listed lines
    zs = tab.get("_summe", (75, 199, "Summe Betriebsausgaben"))
    out.append([zs[0], zs[1], zs[2], e["ausgaben"]])
    out.append([97, 219, "Steuerpflichtiger Gewinn/Verlust", e["gewinn"]])
    return out


def m79_anlage_n(year):
    year = int(year)
    sal, emp = salary_sum(year)
    ti = tax_inputs(year)
    fy = fahrten_year(year)
    wk_p = 1230.0 if year >= 2023 else 1200.0
    rows = [{"nr": nr, "label": lbl, "betrag": round(float(sal.get(k) or 0), 2), "key": k} for k, nr, lbl in M79_LSTB]
    pend = [r for r in fy["rows"] if r.get("art") == "pendel"]
    km_max = max([float(r["km"] or 0) for r in pend] or [0])
    wk = [{"label": "Wege Wohnung - erste Tätigkeitsstätte (Entfernungspauschale)", "betrag": fy["pendel_eur"],
           "info": f"{fy['pendel_tage']} Arbeitstage, einfache Entfernung bis {num_de(km_max, 0)} km" if pend else "keine Pendelfahrten erfasst"}]
    if ti.get("ho_zuordnung") == "gehalt" and homeoffice_eur(ti):
        wk.append({"label": "Homeoffice-Tagespauschale", "betrag": homeoffice_eur(ti), "info": f"{int(ti.get('ho_tage') or 0)} Tage"})
    if float(ti.get("wk") or 0):
        wk.append({"label": "Weitere Werbungskosten (eigene Angabe)", "betrag": round(float(ti["wk"]), 2), "info": ""})
    wk_sum = round(sum(w["betrag"] for w in wk), 2)
    return {"year": year, "arbeitgeber": emp, "lstb": rows, "werbungskosten": wk, "wk_summe": wk_sum,
            "wk_pauschale": wk_p, "wk_wirkt": wk_sum > wk_p,
            "vorsorge": [{"label": "Rentenversicherung (Arbeitnehmeranteil, Nr. 23a)", "betrag": round(sal["rv"], 2)},
                         {"label": "Krankenversicherung (Arbeitnehmer, Nr. 25)", "betrag": round(sal["kv"], 2)},
                         {"label": "Pflegeversicherung (Arbeitnehmer, Nr. 26)", "betrag": round(sal["pv"], 2)},
                         {"label": "Arbeitslosenversicherung (Arbeitnehmer, Nr. 27)", "betrag": round(sal["av"], 2)}],
            "hinweis": "Die Werte der Lohnsteuerbescheinigung liegen dem Finanzamt meist elektronisch vor (eDaten) - "
                       "zum Abgleich nutzen. Werbungskosten nur eintragen, wenn sie über der Pauschale liegen."}


def m79_ausfuell(year):
    year = int(year)
    form = euer_form(year)
    ov = (get_settings().get("m79_zeilen") or {}).get(str(year)) or {}
    return {"year": year, "euer": [{"zeile": z, "kz": kz, "label": lbl, "betrag": v,
                                    "text": f"Zeile {z} (Kz {kz}): {money(v)}"} for z, kz, lbl, v in form],
            "quelle": M79_FORM_JAHRE.get(year, "aus Vordruck 2025 übernommen - bitte abgleichen") + (" + eigene Korrekturen" if ov else ""),
            "hinweis": M79_FORM_HINWEIS, "anlage_n": m79_anlage_n(year)}


def m79_zeilen_get(year):
    year = int(year)
    tab = m79_form_table(year)
    ov = (get_settings().get("m79_zeilen") or {}).get(str(year)) or {}
    keys = ["_einnahmen_ku", "_einnahmen_regel", "_einnahmen_frei", "_ust_vereinnahmt", "_ust_erstattet"] + \
        [k for k in EUER_KATEGORIEN] + ["Fahrten Privat-Pkw (km-Pauschale)", "Homeoffice-Tagespauschale", "_vorsteuer",
                                        "Umsatzsteuer-Zahlung (Finanzamt)", "_summe"]
    seen, rows = set(), []
    names = {"_einnahmen_ku": "Einnahmen als Kleinunternehmer", "_einnahmen_regel": "Einnahmen netto (Regelbesteuerung)",
             "_einnahmen_frei": "Steuerfreie Einnahmen", "_ust_vereinnahmt": "Vereinnahmte Umsatzsteuer",
             "_ust_erstattet": "Erstattete Umsatzsteuer", "_vorsteuer": "Vorsteuer", "_summe": "Summe Betriebsausgaben"}
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        z, kz, lbl = tab.get(k, tab["Sonstige Betriebsausgaben"])
        rows.append({"key": k, "name": names.get(k, k), "zeile": z, "kz": kz, "label": lbl, "eigen": k in ov})
    return {"year": year, "rows": rows, "quelle": M79_FORM_JAHRE.get(year, ""), "hinweis": M79_FORM_HINWEIS}

# ---------------------------------------------------------------------------
# (a) DATEV Buchungsstapel
# ---------------------------------------------------------------------------
M79_COLS = ["Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs", "Basis-Umsatz", "WKZ Basis-Umsatz",
            "Konto", "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel", "Belegdatum", "Belegfeld 1", "Belegfeld 2", "Skonto",
            "Buchungstext", "Postensperre", "Diverse Adressnummer", "Geschäftspartnerbank", "Sachverhalt", "Zinssperre", "Beleglink"]


def _m79_belegfeld(v):
    v = re.sub(r"[^A-Za-z0-9$&%*+\-/]", "", str(v or ""))
    return v[:36]


def _m79_txt(v, n=60):
    t = re.sub(r"[\r\n\t;\"]+", " ", str(v or "")).strip()
    return t.encode("cp1252", "replace").decode("cp1252")[:n]


def _m79_amt(v):
    return f"{abs(float(v)):.2f}".replace(".", ",")


def _m79_cust_name(r):
    try:
        return inv_name(r)
    except Exception:
        return r.get("kdnr") or ""


def _m79_kreditor(partner, mem):
    key = norm_partner(partner) if "norm_partner" in globals() else (partner or "").strip().lower()
    if not key:
        return None
    if key in mem:
        return mem[key]
    used = set(mem.values())
    n = 70001
    while n in used:
        n += 1
    mem[key] = n
    return n


def _m79_rate_of(inv_row):
    """Regelbesteuerung (m80): {satz: (netto, ust)} for a stored invoice, else None"""
    if inv_row.get("ust_modus") != "regel":
        return None
    try:
        det = json.loads(inv_row.get("ust_detail") or "{}")
        return {float(k): (float(v[0]), float(v[1])) for k, v in (det.get("saetze") or {}).items()}
    except Exception:
        return None


def m79_bookings(von, bis, cfg=None):
    cfg = cfg or m79_cfg()
    K = m79_konten(cfg)
    bank, kasse = K["_bank"], K["_kasse"]
    out = []
    kred_mem = dict(get_settings().get("m79_kreditoren") or {})

    def add(datum, betrag, sh, konto, gegen, text, beleg="", bu="", file="", quelle="", ref=""):
        if not betrag or abs(betrag) < 0.005:
            return
        if betrag < 0:
            betrag, sh = -betrag, ("H" if sh == "S" else "S")
        out.append({"datum": datum, "betrag": round(betrag, 2), "sh": sh, "konto": konto, "gegen": gegen, "bu": bu,
                    "beleg": _m79_belegfeld(beleg), "text": _m79_txt(text), "file": file, "quelle": quelle, "ref": ref})

    # cash book links (m81): these belege / invoices go to the Kasse account
    kasse_beleg, kasse_inv, kasse_konto = {}, {}, {}
    if "m81_links" in globals():
        try:
            kasse_beleg, kasse_inv, kasse_konto = m81_links()
        except Exception:
            traceback.print_exc()
    # 1) paid invoices (Ist): Geldkonto an Erloese. Invoices with payment rows (m71: Teilzahlung, Skonto,
    #    Ausbuchung) are booked per payment with the amount really received - same as the EUER (paid_invoices).
    m71ids = set()
    if "m71_ids" in globals():
        try:
            m71ids = m71_ids()
        except Exception:
            traceback.print_exc()
    pays = []
    for r in q("SELECT * FROM invoices WHERE status='bezahlt' AND typ IN ('rechnung','storno') AND "
               "substr(COALESCE(NULLIF(bezahlt_am,''),datum),1,10) BETWEEN ? AND ?", (von, bis)):
        if r["id"] not in m71ids:
            pays.append((r, (r["bezahlt_am"] or r["datum"])[:10], float(r["summe"] or 0), None))
    if m71ids:
        # v2.1.0: status 'storniert' included (payments received before a cancellation stay income - same as the EUER)
        for z in q("SELECT z.datum zdatum, z.betrag zbetrag, z.quelle zquelle, i.* FROM m71_zahlung z JOIN invoices i ON i.id=z.invoice_id "
                   "WHERE z.art IN ('zahlung','teil') AND i.status IN ('offen','bezahlt','storniert') AND i.typ IN ('rechnung','storno') "
                   "AND substr(z.datum,1,10) BETWEEN ? AND ? ORDER BY z.datum, z.id", (von, bis)):
            r = {k: v for k, v in z.items() if k not in ("zdatum", "zbetrag", "zquelle")}
            pays.append((r, z["zdatum"][:10], round(float(z["zbetrag"] or 0), 2), z["zquelle"] or ""))
    ref_zahlart = {}

    def _zahlart(r):
        # a cancellation always carries zahlart 'Bar' (m02) - the refund goes the way the original was paid
        if r.get("typ") == "storno" and r.get("ref_id"):
            if r["ref_id"] not in ref_zahlart:
                o = q("SELECT zahlart FROM invoices WHERE id=?", (r["ref_id"],), one=True)
                ref_zahlart[r["ref_id"]] = (o or {}).get("zahlart") or ""
            return ref_zahlart[r["ref_id"]]
        return r.get("zahlart") or ""
    for r, d, paid, zq in pays:
        # v2.1.0: payment rows (m71) know their way - bank booking -> Bank, cash book -> Kasse; before, a bank partial
        # payment of an invoice whose rest was paid in cash went to the Kasse account as well
        if zq == "kasse":
            gk = kasse_konto.get(kasse_inv.get(r["id"])) or kasse
        elif zq == "bank":
            gk = bank
        else:
            gk = kasse_konto.get(kasse_inv.get(r["id"])) or (kasse if (_zahlart(r) == "Bar" or r["id"] in kasse_inv) else bank)
        name = _m79_cust_name(r)
        rates = _m79_rate_of(r)
        deb = (10000 + int(r["customer_id"])) if (cfg.get("debitoren") and r.get("customer_id") and 10000 + int(r["customer_id"]) < 70000) else None
        full = float(r["summe"] or 0)
        fac = (paid / full) if abs(full) > 0.004 else 1.0
        parts = []
        if rates:
            for satz, (net, ust) in rates.items():
                acc = K["_erloese_19"] if abs(satz - 19) < 0.01 else K["_erloese_7"] if abs(satz - 7) < 0.01 else K["_erloese_0"]
                parts.append((acc, round((net + ust) * fac, 2)))
            if parts:   # rounding rest onto the last part so the parts add up to the payment
                parts[-1] = (parts[-1][0], round(parts[-1][1] + paid - sum(p[1] for p in parts), 2))
        else:
            parts.append((K["_erloese_ku"], paid))
        # invoice date only if it lies in the same (fiscal) year and in the period, else the payment date
        # (a Belegdatum outside the Buchungsstapel period is rejected by DATEV)
        ed = r["datum"][:10] if (von <= r["datum"][:10] <= bis and _m79_wj_start(r["datum"][:10], cfg) == _m79_wj_start(d, cfg)) else d
        for acc, amt in parts:
            if deb:
                add(ed, amt, "S", deb, acc, f"{r['nr']} {name}", r["nr"], quelle="Rechnung", ref=r["id"])
                add(d, amt, "S", gk, deb, f"Zahlung {r['nr']} {name}", r["nr"], quelle="Zahlung", ref=r["id"])
            else:
                add(d, amt, "S", gk, acc, f"{r['nr']} {name}", r["nr"], quelle="Rechnung", ref=r["id"])
    # 2) belege (Ausgaben / sonstige Einnahmen)
    for b in q("SELECT * FROM belege WHERE typ IN ('ausgabe','einnahme') AND substr(datum,1,10) BETWEEN ? AND ? "
               "AND id NOT IN (SELECT beleg_id FROM assets WHERE beleg_id IS NOT NULL) ORDER BY datum, id", (von, bis)):
        gk = kasse_konto.get(kasse_beleg.get(b["id"])) or (kasse if (b["id"] in kasse_beleg or (b.get("quelle") or "") == "kasse") else bank)
        nr = b["nr"] or f"B{b['id']}"
        try:
            det = json.loads(b["details"] or "{}")
        except Exception:
            det = {}
        if b["typ"] == "ausgabe":
            acc = K.get(b["kategorie"] or "", K["Sonstige Betriebsausgaben"])
            vst = float(det.get("vorsteuer") or 0)
            bu = ""
            if abs(vst) > 0.004 and abs(float(b["betrag"] or 0)) > abs(vst):
                # credit notes (negative amount, negative Vorsteuer) get the same key - DATEV reverses the VSt
                ratio = abs(vst) / max(0.01, abs(float(b["betrag"])) - abs(vst)) * 100
                bu = "9" if abs(ratio - 19) < 1.5 else "8" if abs(ratio - 7) < 1.0 else ""
            amt_all = float(b["betrag"] or 0)
            splits = [(acc, amt_all)]
            if (b["kategorie"] or "").startswith("Bewirtung") and K.get("_bewirt_na"):
                # EUER counts 70 % - the non-deductible 30 % go to their own account (same result as the EUER)
                ab = round(amt_all * 0.7, 2)
                splits = [(acc, ab), (K["_bewirt_na"], round(amt_all - ab, 2))]
            if cfg.get("kreditoren") and (b["partner"] or "").strip():
                kr = _m79_kreditor(b["partner"], kred_mem)
                for i_, (a_, v_) in enumerate(splits):
                    add(b["datum"], v_, "S", a_, kr, f"{b['partner']} {b['notiz'] or ''}", nr, bu, (b["file"] or "") if i_ == 0 else "", "Beleg", b["id"])
                add(b["datum"], amt_all, "S", kr, gk, f"Zahlung {b['partner']}", nr, "", "", "Zahlung", b["id"])
            else:
                for i_, (a_, v_) in enumerate(splits):
                    add(b["datum"], v_, "H", gk, a_, f"{b['partner']} {b['notiz'] or ''}", nr, bu, (b["file"] or "") if i_ == 0 else "", "Beleg", b["id"])
        else:
            acc = K["_ust_zahlung"] if (b["kategorie"] or "") == "Umsatzsteuer-Erstattung" else K["_sonst_ertrag"]
            if acc == K["_sonst_ertrag"] and "m80_ein_split" in globals() and m80_ab() and (b["datum"] or "") >= m80_ab():
                # Regelbesteuerung: income with USt (e.g. cash sale m81) on the automatic revenue account of its rate
                sz_, _n, u_ = m80_ein_split(b)
                if u_:
                    acc = K["_erloese_19"] if abs(sz_ - 19) < 0.01 else K["_erloese_7"] if abs(sz_ - 7) < 0.01 else acc
            add(b["datum"], float(b["betrag"] or 0), "S", gk, acc, f"{b['partner']} {b['notiz'] or ''}", nr, "", b["file"] or "", "Einnahme", b["id"])
    # 3) cash book: private deposits/withdrawals and transit (no EUER effect)
    if "m81_datev_extra" in globals():
        try:
            for e_ in m81_datev_extra(von, bis, K):
                add(*e_)
        except Exception:
            traceback.print_exc()
    # 4) business trips with the private car (km allowance) as private deposit
    if cfg.get("km_buchen", True):
        s = get_settings()
        rate = float(s.get("km_dienst") or 0.30)
        for f in q("SELECT * FROM fahrten WHERE substr(datum,1,10) BETWEEN ? AND ? AND COALESCE(art,'dienst')='dienst'", (von, bis)):
            add(f["datum"], round(float(f["km"] or 0) * rate, 2), "S", K["_km"], K["_privat_ein"],
                f"Fahrt {f['ziel'] or ''} {num_de(float(f['km'] or 0), 0)} km", f"F{f['id']}", quelle="Fahrt", ref=f["id"])
    if cfg.get("kreditoren"):
        set_setting("m79_kreditoren", kred_mem)
    out.sort(key=lambda r: (r["datum"], r["beleg"]))
    return out


def _m79_wj_start(datum, cfg):
    """start (YYYY-MM-DD) of the fiscal year that contains datum"""
    wj = cfg.get("wj_beginn") or "01-01"
    if not re.fullmatch(r"\d\d-\d\d", wj):
        wj = "01-01"
    y = int(datum[:4])
    return f"{y}-{wj}" if datum[5:10] >= wj else f"{y - 1}-{wj}"


def _m79_wj_end(start):
    try:
        d = datetime.date.fromisoformat(start)
        return (d.replace(year=d.year + 1) - datetime.timedelta(days=1)).isoformat()
    except ValueError:
        return f"{start[:4]}-12-31"


def _m79_header(cfg, von, bis, bez):
    wj = _m79_wj_start(von, cfg).replace("-", "")
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "000"
    f = ['"EXTF"', "700", "21", '"Buchungsstapel"', "13", stamp, "", '"RE"', '""', '""',
         str(int(cfg.get("berater") or 0)), str(int(cfg.get("mandant") or 0)), wj, str(int(cfg.get("kontenlaenge") or 4)),
         von.replace("-", ""), bis.replace("-", ""), f'"{_m79_txt(bez, 30)}"', f'"{_m79_txt(cfg.get("kuerzel") or "", 2)}"',
         "1", "0", "1" if cfg.get("festschreibung") else "0", '"EUR"', "", '""', "", "", f'"{cfg["skr"]}"', "", "", '""', '""']
    return ";".join(f)


def m79_datev_csv(rows, cfg, von, bis):
    lines = [_m79_header(cfg, von, bis, f"PA Rechnung {von[:4]}"), ";".join(M79_COLS)]
    for r in rows:
        d = r["datum"]
        vals = [_m79_amt(r["betrag"]), f'"{r["sh"]}"', '"EUR"', "", "", "", str(r["konto"]), str(r["gegen"]),
                f'"{r["bu"]}"' if r["bu"] else "", d[8:10] + d[5:7], f'"{r["beleg"]}"', '""', "", f'"{r["text"]}"',
                "", "", "", "", "", ""]
        lines.append(";".join(vals))
    return ("\r\n".join(lines) + "\r\n").encode("cp1252", "replace")


def m79_datev_export(von, bis, mit_belegen=True, out_dir=None):
    cfg = m79_cfg()
    if not von or not bis or von > bis:
        raise ValueError("Bitte einen gültigen Zeitraum wählen.")
    warn = []
    if not int(cfg.get("berater") or 0) or not int(cfg.get("mandant") or 0):
        warn.append("Berater- und Mandantennummer fehlen (Einstellungen → DATEV & Formulare). DATEV verlangt beide beim Import.")
    rows_all = m79_bookings(von, bis, cfg)
    # one Buchungsstapel per fiscal year (DATEV rule)
    years = sorted({_m79_wj_start(r["datum"][:10], cfg) for r in rows_all}) or [_m79_wj_start(von, cfg)]
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    out_dir = out_dir or os.path.join(DATA_DIR, "Export")
    os.makedirs(out_dir, exist_ok=True)
    zp = os.path.join(out_dir, f"DATEV_{von}_{bis}_{stamp}.zip")
    nfiles, missing = 0, 0
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for ws in years:
            v_ = max(von, ws)
            b_ = min(bis, _m79_wj_end(ws))
            rows = [r for r in rows_all if _m79_wj_start(r["datum"][:10], cfg) == ws]
            z.writestr(f"EXTF_Buchungsstapel_{ws[:4]}_{v_}_{b_}.csv", m79_datev_csv(rows, cfg, v_, b_))
        if mit_belegen:
            used = set()
            for r in rows_all:
                if not r["file"]:
                    continue
                fp = r["file"] if os.path.isabs(r["file"]) else os.path.join(DATA_DIR, r["file"])
                if not os.path.isfile(fp):
                    missing += 1
                    continue
                base = r["beleg"] or "Beleg"
                ext = os.path.splitext(fp)[1].lower() or ".pdf"
                n, nm = 1, base + ext
                while nm.lower() in used:
                    n += 1
                    nm = f"{base}_{n}{ext}"
                used.add(nm.lower())
                z.write(fp, "Belege/" + nm)
                nfiles += 1
        z.writestr("LIESMICH.txt", ("DATEV-Export aus Pfeiffer-Audio Rechnung v" + APP_VERSION + "\r\n"
                                    f"Zeitraum {de_date(von)} - {de_date(bis)}, Kontenrahmen SKR{cfg['skr']}\r\n"
                                    f"Buchungen: {len(rows_all)}, Belegdateien: {nfiles}\r\n"
                                    "Die CSV-Datei(en) im DATEV-Format (EXTF) in DATEV Rechnungswesen über "
                                    "'Bestand > Importieren > ASCII-Daten' bzw. 'Stapelverarbeitung' einlesen.\r\n"
                                    "Belegdateien heissen wie Belegfeld 1 der Buchung.\r\n"
                                    "Kontenzuordnung ist ein Vorschlag - bitte mit dem Steuerberater abstimmen.\r\n").encode("cp1252", "replace"))
    if missing:
        warn.append(f"{missing} Belegdatei(en) nicht gefunden - Buchungen sind trotzdem enthalten.")
    if not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(os.path.dirname(zp))
    summe_s = round(sum(r["betrag"] for r in rows_all if r["sh"] == "S"), 2)
    summe_h = round(sum(r["betrag"] for r in rows_all if r["sh"] == "H"), 2)
    return {"ok": True, "path": zp, "buchungen": len(rows_all), "belege": nfiles, "warn": warn, "soll": summe_s, "haben": summe_h}

# ---------------------------------------------------------------------------
# Exports (Excel / PDF)
# ---------------------------------------------------------------------------


def _m79_ex_ausfuell(p):
    year = int(p.get("year") or datetime.date.today().year)
    a = m79_ausfuell(year)
    n = a["anlage_n"]
    out = [_sh(f"Anlage EÜR {year}", [("Zeile", "t", 8), ("Kz", "t", 8), ("Bezeichnung", "t", 50), ("Betrag", "m", 14)],
               [[str(r["zeile"]), str(r["kz"]), r["label"], r["betrag"]] for r in a["euer"]], a["hinweis"], False),
           _sh(f"Anlage N {year} (Lohnsteuerbescheinigung)", [("Nr. LStB", "t", 10), ("Bezeichnung", "t", 50), ("Betrag", "m", 14)],
               [[r["nr"], r["label"], r["betrag"]] for r in n["lstb"]], n["hinweis"], False),
           _sh(f"Werbungskosten {year}", [("Art", "t", 50), ("Info", "t", 34), ("Betrag", "m", 14)],
               [[w["label"], w["info"], w["betrag"]] for w in n["werbungskosten"]] +
               [["Summe (Pauschale " + money(n["wk_pauschale"]) + ")", "wirkt sich aus" if n["wk_wirkt"] else "unter der Pauschale", n["wk_summe"]]], "", False),
           _sh(f"Vorsorgeaufwand {year}", [("Art", "t", 60), ("Betrag", "m", 14)],
               [[v["label"], v["betrag"]] for v in n["vorsorge"]], "", False)]
    return out


def _m79_ex_datev(p):
    von = p.get("von") or f"{datetime.date.today().year}-01-01"
    bis = p.get("bis") or today()
    rows = m79_bookings(von, bis)
    return [_sh(f"DATEV-Buchungen {de_date(von)} - {de_date(bis)}",
                [("Datum", "d", 11), ("Umsatz", "m", 12), ("S/H", "t", 5), ("Konto", "t", 8), ("Gegenkonto", "t", 10), ("BU", "t", 4),
                 ("Belegfeld 1", "t", 16), ("Buchungstext", "t", 44), ("Quelle", "t", 10)],
                [[r["datum"], r["betrag"], r["sh"], str(r["konto"]), str(r["gegen"]), r["bu"], r["beleg"], r["text"], r["quelle"]] for r in rows],
                f"SKR{m79_cfg()['skr']} - Vorschlag, mit Steuerberater abstimmen", False)]


EXPORTS["m79_ausfuell"] = ("Ausfuellhilfe_EUER_N", _m79_ex_ausfuell)
EXPORTS["m79_datev"] = ("DATEV_Buchungen", _m79_ex_datev)

# ---------------------------------------------------------------------------
# Jahresbericht-PDF: Ausfuellhilfe als Anhang
# ---------------------------------------------------------------------------
@chain_step("jahresbericht_pdf", "m79_datev_euer")
def _m79_step_jahresbericht_pdf(_next, year):
    data = _next(year)
    try:
        if not pypdf:
            return data
        extra = export_pdf(_m79_ex_ausfuell({"year": year}), f"Ausfüllhilfe Steuererklärung {year}")
        w = pypdf.PdfWriter()
        for pg in pypdf.PdfReader(io.BytesIO(data)).pages:
            w.add_page(pg)
        for pg in pypdf.PdfReader(io.BytesIO(extra)).pages:
            w.add_page(pg)
        o = io.BytesIO()
        w.write(o)
        return o.getvalue()
    except Exception:
        traceback.print_exc()
        return data

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def m79_route_ausfuell(h, qs):
    return h._send(200, m79_ausfuell(int(qs.get("year") or datetime.date.today().year)))


def m79_route_zeilen(h, qs):
    return h._send(200, m79_zeilen_get(int(qs.get("year") or datetime.date.today().year)))


def m79_route_zeilen_save(h, d):
    year = str(int(d.get("year")))
    allv = get_settings().get("m79_zeilen") or {}
    if d.get("reset"):
        allv.pop(year, None)
    else:
        tab = m79_form_table(int(year))
        cur_ = {}
        for r in d.get("rows") or []:
            k = r.get("key")
            if not k:
                continue
            base = (dict(EUER_FORM, **M79_FORM_EXTRA)).get(k) or tab.get(k)
            new = (int(r.get("zeile") or 0), int(r.get("kz") or 0), str(r.get("label") or ""))
            if base and (new[0], new[1], new[2]) == tuple(base):
                continue
            cur_[k] = list(new)
        if cur_:
            allv[year] = cur_
        else:
            allv.pop(year, None)
    set_setting("m79_zeilen", allv)
    return h._send(200, dict(m79_zeilen_get(int(year)), ok=True))


def m79_route_cfg(h, qs):
    cfg = m79_cfg()
    k = m79_konten(cfg)
    base = M79_SKR[cfg["skr"]]
    rows = []
    for key in list(M79_KONTO_LABEL) + list(EUER_KATEGORIEN) + (["Umsatzsteuer-Zahlung (Finanzamt)"] if "Umsatzsteuer-Zahlung (Finanzamt)" not in EUER_KATEGORIEN else []):
        if key in (r["key"] for r in rows):
            continue
        rows.append({"key": key, "name": M79_KONTO_LABEL.get(key, key), "konto": k.get(key, base.get("Sonstige Betriebsausgaben")),
                     "standard": base.get(key), "eigen": str((cfg.get("konten") or {}).get(key, "")).strip() != ""})
    return h._send(200, {"cfg": {kk: v for kk, v in cfg.items() if kk != "konten"}, "konten": rows})


def m79_route_cfg_save(h, d):
    cfg = m79_cfg()
    for kk in ("berater", "mandant", "kontenlaenge"):
        if kk in d:
            try:
                cfg[kk] = int(str(d[kk]).strip() or 0)
            except Exception:
                raise ValueError(f"{kk.capitalize()}: bitte eine Zahl eintragen.")
    if cfg["berater"] and not (1001 <= cfg["berater"] <= 9999999):
        raise ValueError("Beraternummer: 1001 bis 9999999.")
    if cfg["mandant"] and not (1 <= cfg["mandant"] <= 99999):
        raise ValueError("Mandantennummer: 1 bis 99999.")
    if cfg["kontenlaenge"] not in (4, 5, 6, 7, 8):
        cfg["kontenlaenge"] = 4
    if d.get("skr") in M79_SKR and d["skr"] != cfg.get("skr"):
        cfg["skr"] = d["skr"]
        cfg["konten"] = {}      # other chart of accounts: own account numbers no longer fit
    for kk in ("debitoren", "kreditoren", "km_buchen", "festschreibung"):
        if kk in d:
            cfg[kk] = bool(d[kk])
    if "wj_beginn" in d and re.fullmatch(r"\d\d-\d\d", str(d["wj_beginn"] or "")):
        cfg["wj_beginn"] = d["wj_beginn"]
    if "kuerzel" in d:
        cfg["kuerzel"] = re.sub(r"[^A-Za-z]", "", str(d["kuerzel"] or ""))[:2].upper()
    if isinstance(d.get("konten"), dict):
        base = M79_SKR[cfg["skr"]]
        kon = {}
        for kk, v in d["konten"].items():
            v = str(v or "").strip()
            if v and v.isdigit() and int(v) != base.get(kk):
                kon[kk] = int(v)
        cfg["konten"] = kon
    set_setting("m79", cfg)
    return m79_route_cfg(h, {})


def m79_route_export(h, d):
    return h._send(200, m79_datev_export(d.get("von"), d.get("bis"), bool(d.get("belege", True))))


def m79_route_preview(h, qs):
    von, bis = qs.get("von"), qs.get("bis")
    rows = m79_bookings(von, bis)
    return h._send(200, {"ok": True, "n": len(rows), "rows": rows[:300], "skr": m79_cfg()["skr"],
                         "soll": round(sum(r["betrag"] for r in rows if r["sh"] == "S"), 2),
                         "haben": round(sum(r["betrag"] for r in rows if r["sh"] == "H"), 2)})


HOOK_GET["/api/m79/ausfuell"] = m79_route_ausfuell
HOOK_GET["/api/m79/zeilen"] = m79_route_zeilen
HOOK_POST["/api/m79/zeilen"] = m79_route_zeilen_save
HOOK_GET["/api/m79/cfg"] = m79_route_cfg
HOOK_POST["/api/m79/cfg"] = m79_route_cfg_save
HOOK_POST["/api/m79/export"] = m79_route_export
HOOK_GET["/api/m79/preview"] = m79_route_preview

# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------


def m79_selftest():
    err = []
    try:
        y = datetime.date.today().year
        s0 = get_settings().get("m79_zeilen")
        if not s0 and not (get_settings().get("m80") or {}).get("ab"):
            a, b = euer_form(y), _m79_orig_euer_form(y)
            if a != b:
                err.append("m79: Anlage EÜR weicht ohne Korrekturen von der bisherigen Berechnung ab")
        rows = m79_bookings(f"{y - 1}-01-01", f"{y}-12-31")
        csv_ = m79_datev_csv(rows, dict(m79_cfg(), berater=1001, mandant=1), f"{y}-01-01", f"{y}-12-31")
        lines = csv_.decode("cp1252").split("\r\n")
        if not lines[0].startswith('"EXTF";700;21;"Buchungsstapel";13;'):
            err.append("m79: DATEV-Kopfzeile falsch")
        if len(lines[0].split(";")) != 31:
            err.append(f"m79: DATEV-Kopfzeile hat {len(lines[0].split(';'))} statt 31 Felder")
        for ln in lines[2:]:
            if ln and len(ln.split(";")) != len(M79_COLS):
                err.append("m79: DATEV-Zeile mit falscher Spaltenzahl")
                break
        ids_ = m71_ids() if "m71_ids" in globals() else set()
        paid = sum(float(r["summe"] or 0) for r in q(
            "SELECT id, summe FROM invoices WHERE status='bezahlt' AND typ IN ('rechnung','storno') AND "
            "substr(COALESCE(NULLIF(bezahlt_am,''),datum),1,10) BETWEEN ? AND ?", (f"{y - 1}-01-01", f"{y}-12-31")) if r["id"] not in ids_)
        if ids_:
            paid += float(q("SELECT COALESCE(SUM(z.betrag),0) s FROM m71_zahlung z JOIN invoices i ON i.id=z.invoice_id "
                            "WHERE z.art IN ('zahlung','teil') AND i.status IN ('offen','bezahlt','storniert') AND i.typ IN ('rechnung','storno') "
                            "AND substr(z.datum,1,10) BETWEEN ? AND ?", (f"{y - 1}-01-01", f"{y}-12-31"), one=True)["s"] or 0)
        inc = sum((r["betrag"] if r["sh"] == "S" else -r["betrag"]) for r in rows if r["quelle"] == "Rechnung")
        if abs(inc - float(paid or 0)) > 0.02:
            err.append(f"m79: Summe Rechnungsbuchungen {inc:.2f} passt nicht zu bezahlten Rechnungen {float(paid or 0):.2f}")
        if _m79_belegfeld("RE 2026/0313 (x)") != "RE2026/0313x":
            err.append("m79: Belegfeld-Bereinigung falsch")
        n = m79_anlage_n(y)
        if len(n["lstb"]) != 8:
            err.append("m79: Anlage N unvollständig")
    except Exception as e:
        err.append(f"m79 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m79_selftest)
