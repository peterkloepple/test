# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m04_statistik_steuer
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# Statistics, EUER, tax
# ----------------------------------------------------------------------------

def _tarif_row(year):
    # v2.6.3: years outside the table use the nearest stored year
    return TARIF.get(year) or TARIF[max(TARIF) if year > max(TARIF) else min(TARIF)]


def tarif(zve, year):
    t = _tarif_row(year)
    gfb, z2, a2, z3, a3, c3, c4, c5, _ = t
    x_ = math.floor(max(0, zve))
    if x_ <= gfb:
        e = 0
    elif x_ <= z2:
        y = (x_ - gfb) / 10000
        e = (a2 * y + 1400) * y
    elif x_ <= z3:
        z = (x_ - z2) / 10000
        e = (a3 * z + 2397) * z + c3
    elif x_ <= 277825:
        e = 0.42 * x_ - c4
    else:
        e = 0.45 * x_ - c5
    return math.floor(e)


def soli_calc(est, year):
    fg = _tarif_row(year)[8]
    if est <= fg:
        return 0.0
    return round(min(est * 0.055, (est - fg) * 0.119), 2)


def year_invoices(year):
    return q(f"SELECT * FROM invoices WHERE substr(datum,1,4)=? AND {COUNT_SQL}", (str(year),))


# salary_sum(): definiert in m25_gehalt_fix (v2.1.0: alte, nie benutzte Fassung entfernt)


def euer(year):
    ys = str(year)
    paid = paid_invoices(year)
    other_in = q("SELECT * FROM belege WHERE typ='einnahme' AND substr(datum,1,4)=?", (ys,))
    out = q("SELECT * FROM belege WHERE typ='ausgabe' AND substr(datum,1,4)=? AND id NOT IN "
            "(SELECT beleg_id FROM assets WHERE beleg_id IS NOT NULL)", (ys,))
    open_ = q("SELECT * FROM invoices WHERE status='offen' AND typ IN ('rechnung','storno') AND substr(datum,1,4)=?", (ys,))
    ein = round(sum(r["summe"] for r in paid) + sum(r["betrag"] for r in other_in), 2)
    cats = {}
    for r in out:
        k = r["kategorie"] or "Sonstige Betriebsausgaben"
        v = r["betrag"] * (0.7 if k.startswith("Bewirtung") else 1.0)
        cats[k] = round(cats.get(k, 0) + v, 2)
    afa_rows = afa_year(year)
    for a in afa_rows:
        if a["afa"]:
            k = "Arbeitsmittel / Equipment (GWG)" if (a["methode"] or "") == "gwg" else "Abschreibung (AfA)"
            cats[k] = round(cats.get(k, 0) + a["afa"], 2)
    fy = fahrten_year(year)
    if fy["dienst_eur"]:
        cats["Fahrten Privat-Pkw (km-Pauschale)"] = fy["dienst_eur"]
    ti = tax_inputs(year)
    if ti.get("ho_zuordnung", "selbst") == "selbst" and homeoffice_eur(ti):
        cats["Homeoffice-Tagespauschale"] = homeoffice_eur(ti)
    aus = round(sum(cats.values()), 2)
    return {"einnahmen": ein, "einnahmen_rechnungen": round(sum(r["summe"] for r in paid), 2),
            "einnahmen_sonstige": round(sum(r["betrag"] for r in other_in), 2),
            "ausgaben": aus, "kategorien": cats, "gewinn": round(ein - aus, 2),
            "offen": round(sum(r["summe"] for r in open_), 2), "offen_anzahl": len(open_),
            "paid_list": paid, "ausgaben_list": out, "einnahmen_list": other_in, "afa_list": [a for a in afa_rows if a["afa"]],
            "fahrten": {k: v for k, v in fy.items() if k != "rows"}}


def tax_inputs(year):
    r = q("SELECT data FROM taxyear WHERE year=?", (year,), one=True)
    d = {"kist": False, "kist_satz": 9.0, "wk": 0.0, "vorsorge_extra": 0.0, "sonder": 0.0,
         "vorauszahlung": 0.0, "sonstige": 0.0, "gewerblich": False, "hebesatz": 475.0, "splitting": False,
         "partner_zve": 0.0, "ho_tage": 0, "ho_zuordnung": "selbst"}
    if r:
        d.update(json.loads(r["data"]))
    return d


def tax_core(year, gewinn, sal, t, wk_real):
    """income tax estimate for one profit value (shared by tax_calc and the m54 tax reserve)"""
    wk_p = 1230.0 if year >= 2023 else 1200.0
    nsa = max(0.0, sal["brutto"] - max(wk_p, wk_real)) if sal["brutto"] > 0 else 0.0
    gde = nsa + gewinn + float(t["sonstige"] or 0)
    kvb = sal["kv"] * 0.96 + sal["pv"]
    vors = sal["rv"] + kvb + max(0.0, min(1900.0 - kvb, sal["av"])) + float(t["vorsorge_extra"] or 0)
    sond = max(36.0, float(t["sonder"] or 0))
    zve = max(0.0, math.floor(gde - vors - sond))
    split = bool(t.get("splitting"))
    pz = float(t.get("partner_zve") or 0)

    def est_of(z):
        return 2 * tarif((z + pz) / 2, year) if split else tarif(z, year)
    est = est_of(zve)
    est_tarif = est
    gew = {"messbetrag": 0.0, "gewst": 0.0, "anrechnung": 0.0}
    if t.get("gewerblich") and gewinn > 24500:
        mb = math.floor((math.floor(gewinn / 100) * 100 - 24500) * 0.035)
        gew["messbetrag"] = mb
        gew["gewst"] = round(mb * float(t["hebesatz"] or 400) / 100, 2)
        gew["anrechnung"] = min(4.0 * mb, est, gew["gewst"])
        est = est - gew["anrechnung"]
    # Soli: base is the income tax after par. 35 (GewSt credit); splitting doubles the exemption limit
    so = soli_calc(est, year) if not split else round(2 * soli_calc(est / 2, year), 2)
    # KiSt: par. 51a Abs. 2 S. 3 EStG - the par. 35 credit does NOT reduce the church tax base
    ki = round(est_tarif * float(t["kist_satz"] or 9) / 100, 2) if t.get("kist") else 0.0
    grenz = round(est_of(zve + 100) - est_tarif, 1) if zve > 0 else 0.0
    return dict(nsa=round(nsa, 2), gde=round(gde, 2), vorsorge=round(vors, 2), sonder=sond, zve=zve,
                est=round(est, 2), soli=so, kist=ki, gesamt=round(est + so + ki, 2), gew=gew, grenz=grenz)


def tax_calc(year):
    e = euer(year)
    sal, emp = salary_sum(year)
    t = tax_inputs(year)
    wk_p = 1230.0 if year >= 2023 else 1200.0
    fy = fahrten_year(year)
    wk_real = float(t["wk"] or 0) + fy["pendel_eur"] + (homeoffice_eur(t) if t.get("ho_zuordnung") == "gehalt" else 0.0)
    full = tax_core(year, e["gewinn"], sal, t, wk_real)
    grenz = full.pop("grenz", 0.0)
    without = tax_core(year, 0.0, sal, t, wk_real)
    without.pop("grenz", None)
    paid = round(sal["lst"] + sal["soli"] + sal["kist"] + float(t["vorauszahlung"] or 0), 2)
    # par. 19 UStG: same basis in both years (invoices by date + other income), like the m52 KU monitor
    vj_other = q("SELECT COALESCE(SUM(betrag),0) s FROM belege WHERE typ='einnahme' AND substr(datum,1,4)=?", (str(year - 1),), one=True)["s"]
    umsatz = round(sum(r["summe"] for r in year_invoices(year)) + e["einnahmen_sonstige"], 2)
    umsatz_vj = round(sum(r["summe"] for r in year_invoices(year - 1)) + float(vj_other or 0), 2)
    return {"year": year, "euer": {k: v for k, v in e.items() if not k.endswith("_list")}, "gehalt": sal,
            "arbeitgeber": emp, "inputs": t, "calc": full, "ohne_selbst": without,
            # GewSt is paid on top; the par. 35 credit is already contained in full["gesamt"]
            "anteil_selbst": round(full["gesamt"] - without["gesamt"] + full["gew"]["gewst"], 2),
            "bereits_gezahlt": paid, "differenz": round(full["gesamt"] - paid, 2), "grenzsteuersatz": grenz,
            "wk_pauschale": wk_p, "wk_real": round(wk_real, 2), "pendel_eur": fy["pendel_eur"], "umsatz": umsatz, "umsatz_vj": umsatz_vj,
            "ku_ok": umsatz_vj <= 25000 and umsatz <= 100000,
            "euer_form": euer_form(year),
            "tarif_hinweis": "" if year in TARIF else f"Für {year} sind die Tarifwerte von {max(TARIF) if year > max(TARIF) else min(TARIF)} hinterlegt."}


def euer_totals(year):
    """v2.0.6: only the three totals (cached in m60 - the year comparison needs no full EUER)"""
    e = getattr(euer, "_m60_orig", euer)(year)
    return {"einnahmen": e["einnahmen"], "ausgaben": e["ausgaben"], "gewinn": e["gewinn"]}


def stats(year):
    ys = str(year)
    invs = year_invoices(year)
    months = [{"m": i + 1, "umsatz": 0.0, "zufluss": 0.0, "ausgaben": 0.0, "anzahl": 0} for i in range(12)]

    def _mi(v):
        # v2.6.3: month index of a stored date; an invalid date ("2025-13-01", "2025") broke the whole statistics
        d_ = d_iso(v)
        return d_.month - 1 if d_ else None
    for r in invs:
        mi = _mi(r["datum"])
        if mi is None:
            continue
        months[mi]["umsatz"] += r["summe"] or 0
        months[mi]["anzahl"] += 1
    for r in q("SELECT * FROM invoices WHERE status='bezahlt' AND typ IN ('rechnung','storno') AND substr(COALESCE(NULLIF(bezahlt_am,''),datum),1,4)=?", (ys,)):
        mi = _mi(r["bezahlt_am"] or r["datum"])
        if mi is not None:
            months[mi]["zufluss"] += r["summe"] or 0
    for r in q("SELECT * FROM belege WHERE typ='ausgabe' AND substr(datum,1,4)=? AND id NOT IN (SELECT beleg_id FROM assets WHERE beleg_id IS NOT NULL)", (ys,)):
        mi = _mi(r["datum"])
        if mi is not None:
            months[mi]["ausgaben"] += (r["betrag"] or 0) * (0.7 if (r["kategorie"] or "").startswith("Bewirtung") else 1.0)
    for m in months:
        for k in ("umsatz", "zufluss", "ausgaben"):
            m[k] = round(m[k], 2)
    total = round(sum(r["summe"] for r in invs), 2)
    cust = {}
    for r in invs:
        key = r["customer_id"] or r["kdnr"]
        c = cust.get(key)
        if c is None:   # v2.0.6: name only once per customer
            c = cust[key] = {"customer_id": r["customer_id"], "kdnr": r["kdnr"], "name": inv_name(r), "anzahl": 0, "summe": 0.0}
        c["anzahl"] += 1
        c["summe"] += r["summe"]
    cids_ = [c["customer_id"] for c in cust.values() if c["customer_id"]]
    cmap_ = {}
    for i0 in range(0, len(cids_), 500):
        part = cids_[i0:i0 + 500]
        for cu in q(f"SELECT id, firma, name FROM customers WHERE id IN ({','.join('?' * len(part))})", part):
            cmap_[cu["id"]] = cu
    for c in cust.values():
        cu = cmap_.get(c["customer_id"]) if c["customer_id"] else None
        if cu:
            c["name"] = cu["firma"] or cu["name"]
        c["summe"] = round(c["summe"], 2)
        c["anteil"] = round(100 * c["summe"] / total, 1) if total else 0
    serv = {}
    ids = [r["id"] for r in invs]
    if ids:
        rows = q(f"SELECT * FROM items WHERE invoice_id IN ({','.join('?' * len(ids))})", ids)
        for it in rows:
            key = (it["nr"] or "") + "|" + (it["name"] or "")
            s_ = serv.setdefault(key, {"nr": it["nr"], "name": it["name"], "menge": 0.0, "summe": 0.0, "anzahl": 0})
            s_["menge"] += it["qty"]
            s_["summe"] += it["total"]
            s_["anzahl"] += 1
    for s_ in serv.values():
        s_["summe"] = round(s_["summe"], 2)
        s_["menge"] = round(s_["menge"], 2)
        s_["anteil"] = round(100 * s_["summe"] / total, 1) if total else 0
    proj = []
    sums_ = {r["project_id"]: r for r in q(f"SELECT project_id, COALESCE(SUM(summe),0) s, COUNT(*) n FROM invoices WHERE project_id IS NOT NULL "
                                           f"AND substr(datum,1,4)=? AND {COUNT_SQL} GROUP BY project_id", (ys,))}
    for p in q("SELECT * FROM projects"):
        su = sums_.get(p["id"]) or {"s": 0, "n": 0}
        if su["n"]:
            proj.append({"id": p["id"], "nr": p["nr"], "name": p["name"], "bereich": p["bereich"], "summe": round(su["s"], 2), "anzahl": su["n"]})
    bereich = {}
    for p in proj:
        bereich[p["bereich"] or "Sonstiges"] = round(bereich.get(p["bereich"] or "Sonstiges", 0) + p["summe"], 2)
    years = []
    for r in q("SELECT DISTINCT substr(datum,1,4) y FROM invoices WHERE typ IN ('rechnung','storno') UNION SELECT DISTINCT substr(datum,1,4) FROM belege ORDER BY 1"):
        if not r["y"]:
            continue
        yy = int(r["y"])
        e = euer_totals(yy)
        years.append({"year": yy, "umsatz": round(sum(i["summe"] for i in year_invoices(yy)), 2),
                      "einnahmen": e["einnahmen"], "ausgaben": e["ausgaben"], "gewinn": e["gewinn"]})
    return {"year": year, "total": total, "anzahl": len(invs), "months": months,
            "kunden": sorted(cust.values(), key=lambda c: -c["summe"]),
            "leistungen": sorted(serv.values(), key=lambda s_: -s_["summe"]),
            "projekte": sorted(proj, key=lambda p: -p["summe"]), "bereiche": bereich, "jahre": years}

# ----------------------------------------------------------------------------
# Year report PDF
# ----------------------------------------------------------------------------

# esc_xml(): definiert in m09_erechnung_ocr (v2.1.0: alte, nie benutzte Fassung entfernt)


def year_report_pdf(year):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    s = get_settings()
    tc = tax_calc(year)
    st = stats(year)
    e = euer(year)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Jahresabrechnung {year}", author=s.get("inhaber", ""))
    ss = font_stylesheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName=FONT_B(), fontSize=18, spaceAfter=4)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=FONT_B(), fontSize=12, spaceBefore=12, spaceAfter=6,
                        textColor=colors.HexColor("#4b2fbf"))
    N = ParagraphStyle("n", parent=ss["Normal"], fontName=FONT_R(), fontSize=9, leading=12)
    SM = ParagraphStyle("s", parent=N, fontSize=7.5, textColor=GRAY, leading=10)

    def tbl(rows, widths, total_row=False, right_cols=()):
        t = Table(rows, colWidths=widths, repeatRows=1)
        sty = [("FONT", (0, 0), (-1, 0), FONT_B(), 8.5), ("FONT", (0, 1), (-1, -1), FONT_R(), 8.5),
               ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f4fa")]),
               ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)]
        for cidx in right_cols:
            sty.append(("ALIGN", (cidx, 0), (cidx, -1), "RIGHT"))
        if total_row:
            sty += [("FONT", (0, -1), (-1, -1), FONT_B(), 8.5), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ebe7fb"))]
        t.setStyle(TableStyle(sty))
        return t

    el = [Paragraph(f"Jahresabrechnung {year}", H1),
          Paragraph(f"{esc_xml(s.get('firma', ''))} · {esc_xml(s.get('inhaber', ''))} · erstellt am {de_date(today())}", N), Spacer(1, 8)]
    el.append(Paragraph("1. Einnahmen-Überschuss-Rechnung (EÜR)", H2))
    rows = [["Position", "Betrag"], ["Betriebseinnahmen aus Rechnungen (bezahlt)", money(e["einnahmen_rechnungen"])],
            ["Sonstige Betriebseinnahmen", money(e["einnahmen_sonstige"])], ["Summe Betriebseinnahmen", money(e["einnahmen"])]]
    for k in EUER_KATEGORIEN:
        if e["kategorien"].get(k):
            rows.append(["   " + k, "- " + money(e["kategorien"][k])])
    for k, v in e["kategorien"].items():
        if k not in EUER_KATEGORIEN:
            rows.append(["   " + k, "- " + money(v)])
    rows.append(["Summe Betriebsausgaben", "- " + money(e["ausgaben"])])
    rows.append(["Gewinn / Verlust", money(e["gewinn"])])
    el.append(tbl(rows, [120 * mm, 50 * mm], True, (1,)))
    el.append(Spacer(1, 4))
    el.append(Paragraph(f"Zuflussprinzip: Einnahmen zählen im Jahr des Zahlungseingangs. Offene Rechnungen {year}: "
                        f"{e['offen_anzahl']} Stück, {money(e['offen'])} (nicht enthalten).", SM))
    el.append(Paragraph("Übertrag in die Anlage EÜR (Zeilen/Kennzahlen gemäß Formular 2025)", H2))
    rows = [["Zeile", "Kz", "Bezeichnung", "Betrag"]] + [[str(z), str(k_), Paragraph(lbl, N), money(v)] for z, k_, lbl, v in euer_form(year)]
    el.append(tbl(rows, [14 * mm, 14 * mm, 112 * mm, 30 * mm], False, (3,)))
    el.append(Paragraph("Zeilennummern können sich im Formular des jeweiligen Jahres verschieben - bitte beim Übertrag die Kennzahl (Kz) verwenden.", SM))
    if e["afa_list"] or e["fahrten"]["dienst_km"]:
        el.append(Paragraph("Abschreibungen und Fahrten", H2))
        rows = [["Position", "Details", "Betrag"]]
        for a_ in e["afa_list"]:
            rows.append([(a_["bezeichnung"] or "")[:40], ("GWG Sofortabzug" if a_["methode"] == "gwg" else f"linear {num_de(a_['nd_jahre'], 0)} J., Rest {money(a_['restwert'])}"), money(a_["afa"])])
        if e["fahrten"]["dienst_km"]:
            rows.append(["Fahrten mit Privat-Pkw", f"{num_de(e['fahrten']['dienst_km'], 1)} km × {num_de(float(s.get('km_dienst') or 0.3), 2)} €", money(e["fahrten"]["dienst_eur"])])
        el.append(tbl(rows, [60 * mm, 80 * mm, 30 * mm], False, (2,)))
    el.append(Paragraph("2. Kleinunternehmerregelung (§19 UStG)", H2))
    el.append(Paragraph(f"Umsatz {year}: <b>{money(tc['umsatz'])}</b> (Grenze laufendes Jahr 100.000 EUR) · "
                        f"Umsatz {year - 1}: <b>{money(tc['umsatz_vj'])}</b> (Grenze Vorjahr 25.000 EUR) · "
                        f"Status: <b>{'Kleinunternehmer möglich' if tc['ku_ok'] else 'Grenze überschritten - bitte prüfen!'}</b>", N))
    el.append(Paragraph("3. Nichtselbstständige Arbeit (Gehalt)", H2))
    g = tc["gehalt"]
    rows = [["Arbeitgeber", "Quelle", "Brutto", "Lohnsteuer", "Soli", "KiSt", "RV+KV+PV+AV"]]
    for a in tc["arbeitgeber"]:
        rows.append([a["name"][:22], "LStB" if a["quelle"].startswith("Lohn") else a["quelle"].split(" ")[0] + " Monate", money(a["brutto"]), money(a["lst"]), money(a["soli"]), money(a["kist"]),
                     money(a["rv"] + a["kv"] + a["pv"] + a["av"])])
    rows.append(["Summe", "", money(g["brutto"]), money(g["lst"]), money(g["soli"]), money(g["kist"]),
                 money(g["rv"] + g["kv"] + g["pv"] + g["av"])])
    el.append(tbl(rows, [36 * mm, 30 * mm, 21 * mm, 21 * mm, 18 * mm, 18 * mm, 26 * mm], True, (2, 3, 4, 5, 6)))
    el.append(Paragraph("4. Steuerschätzung Einkommensteuer", H2))
    cc = tc["calc"]
    rows = [["Position", "Betrag"],
            ["Einkünfte nichtselbstständige Arbeit (Brutto - Werbungskosten)", money(cc["nsa"])],
            ["Einkünfte aus selbstständiger/gewerblicher Tätigkeit (Gewinn)", money(e["gewinn"])],
            ["Sonstige Einkünfte", money(float(tc["inputs"]["sonstige"] or 0))],
            ["Gesamtbetrag der Einkünfte", money(cc["gde"])],
            ["- Vorsorgeaufwendungen (vereinfacht)", "- " + money(cc["vorsorge"])],
            ["- Sonderausgaben", "- " + money(cc["sonder"])],
            ["Zu versteuerndes Einkommen", money(cc["zve"])],
            ["Einkommensteuer (§32a EStG " + str(year) + (", Splitting" if tc["inputs"].get("splitting") else ", Grundtarif") + ")", money(cc["est"])],
            ["Solidaritätszuschlag", money(cc["soli"])], ["Kirchensteuer", money(cc["kist"])]]
    if cc["gew"]["gewst"]:
        rows.append(["Gewerbesteuer (separat an Gemeinde)", money(cc["gew"]["gewst"])])
    rows += [["Steuer gesamt (ESt + Soli + KiSt)", money(cc["gesamt"])],
             ["- bereits gezahlt (Lohnsteuer, Soli, KiSt, Vorauszahlungen)", "- " + money(tc["bereits_gezahlt"])],
             ["Voraussichtliche " + ("Nachzahlung" if tc["differenz"] >= 0 else "Erstattung"), money(abs(tc["differenz"]))]]
    el.append(tbl(rows, [120 * mm, 50 * mm], True, (1,)))
    el.append(Spacer(1, 4))
    el.append(Paragraph(f"Davon entfällt auf die Selbstständigkeit ca. <b>{money(tc['anteil_selbst'])}</b> "
                        f"(Empfehlung als Rücklage). Grenzsteuersatz ca. {num_de(tc['grenzsteuersatz'], 1)} %.", N))
    el.append(Paragraph("Hinweis: Schätzung nach vereinfachtem Verfahren, ersetzt keine Steuerberatung und keinen Steuerbescheid.", SM))
    el.append(PageBreak())
    el.append(Paragraph("5. Statistik Kunden", H2))
    rows = [["Kunde", "Rechnungen", "Umsatz", "Anteil"]] + [[k["name"][:50], str(k["anzahl"]), money(k["summe"]), num_de(k["anteil"], 1) + " %"] for k in st["kunden"]]
    rows.append(["Summe", str(st["anzahl"]), money(st["total"]), "100 %"])
    el.append(tbl(rows, [90 * mm, 25 * mm, 30 * mm, 25 * mm], True, (1, 2, 3)))
    el.append(Paragraph("6. Statistik Leistungen / Bausteine", H2))
    rows = [["Art.", "Leistung", "Menge", "Umsatz", "Anteil"]] + [[l["nr"] or "", (l["name"] or "")[:45], num_de(l["menge"], 2), money(l["summe"]), num_de(l["anteil"], 1) + " %"] for l in st["leistungen"]]
    el.append(tbl(rows, [16 * mm, 82 * mm, 22 * mm, 30 * mm, 20 * mm], False, (2, 3, 4)))
    el.append(Paragraph("7. Monatsübersicht", H2))
    mn = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    rows = [["Monat", "Rechnungen", "Umsatz (Rechnungsdatum)", "Zufluss", "Ausgaben"]]
    for m in st["months"]:
        rows.append([mn[m["m"] - 1], str(m["anzahl"]), money(m["umsatz"]), money(m["zufluss"]), money(m["ausgaben"])])
    rows.append(["Summe", str(st["anzahl"]), money(st["total"]), money(sum(m["zufluss"] for m in st["months"])), money(sum(m["ausgaben"] for m in st["months"]))])
    el.append(tbl(rows, [22 * mm, 24 * mm, 44 * mm, 40 * mm, 40 * mm], True, (1, 2, 3, 4)))
    el.append(PageBreak())
    el.append(Paragraph("8. Einnahmen - Rechnungsliste", H2))
    rows = [["Nr.", "Datum", "Bezahlt", "Kunde", "Betrag"]]
    for r in sorted(e["paid_list"], key=lambda r: r["nr"] or ""):
        rows.append([r["nr"], de_date(r["datum"]), de_date(r["bezahlt_am"]), inv_name(r)[:40], money(r["summe"])])
    for r in e["einnahmen_list"]:
        rows.append([r["nr"] or "-", de_date(r["datum"]), de_date(r["datum"]), (r["partner"] or "")[:40], money(r["betrag"])])
    rows.append(["", "", "", "Summe", money(e["einnahmen"])])
    el.append(tbl(rows, [24 * mm, 22 * mm, 22 * mm, 72 * mm, 30 * mm], True, (4,)))
    el.append(Paragraph("9. Ausgaben - Belegliste", H2))
    rows = [["Datum", "Lieferant", "Beleg-Nr.", "Kategorie", "Betrag"]]
    for r in sorted(e["ausgaben_list"], key=lambda r: r["datum"] or ""):
        rows.append([de_date(r["datum"]), (r["partner"] or "")[:28], (r["nr"] or "")[:16], (r["kategorie"] or "")[:30], money(r["betrag"])])
    rows.append(["", "", "", "Summe (Bewirtung zu 70 %)", money(e["ausgaben"])])
    el.append(tbl(rows, [20 * mm, 45 * mm, 26 * mm, 50 * mm, 29 * mm], True, (4,)))
    ab = (tax_inputs(year).get("abschluss") or {})
    akte = q("SELECT * FROM steuerakte WHERE year=? ORDER BY art, datum", (year,))
    if ab or akte:
        el.append(PageBreak())
        el.append(Paragraph(f"10. Jahresabschluss {year}: Abgleich mit Steuererklärung und Bescheid", H2))
        if ab.get("abgeschlossen"):
            el.append(Paragraph(f"<b>Jahr abgeschlossen</b>{' am ' + de_date(ab.get('abgeschlossen_am')) if ab.get('abgeschlossen_am') else ''}"
                                f"{' · Bescheid vom ' + de_date(ab.get('bescheid_datum')) if ab.get('bescheid_datum') else ''}", N))
        def mv(v):
            return money(float(v)) if v not in (None, "") else "–"
        rows = [["Position", "Programm (Buchungen)", "lt. Erklärung / Bescheid", "Differenz"]]
        for key, lbl, prog in (("eur_einnahmen", "Betriebseinnahmen", e["einnahmen"]), ("eur_ausgaben", "Betriebsausgaben", e["ausgaben"]),
                               ("eur_gewinn", "Gewinn / Verlust", e["gewinn"])):
            v = ab.get(key)
            rows.append([lbl, money(prog), mv(v), money(round(prog - float(v), 2)) if v not in (None, "") else "–"])
        el.append(tbl(rows, [55 * mm, 38 * mm, 42 * mm, 35 * mm], False, (1, 2, 3)))
        rows = [["Bescheid / Festsetzung", "Betrag"]]
        for key, lbl in ABSCHLUSS_FELDER[3:]:
            if ab.get(key) not in (None, ""):
                rows.append([lbl, mv(ab.get(key))])
        if len(rows) > 1:
            el.append(Spacer(1, 6))
            el.append(tbl(rows, [110 * mm, 60 * mm], False, (1,)))
        if ab.get("notizen"):
            el.append(Spacer(1, 6))
            el.append(Paragraph("<b>Anmerkungen</b>", N))
            for n_ in ab["notizen"]:
                el.append(Paragraph("• " + esc_xml(n_), N))
        if akte:
            el.append(Spacer(1, 6))
            rows = [["Unterlage", "Art", "Datum"]]
            for a in akte:
                rows.append([(a["titel"] or "")[:60], (a["art"] or "")[:34], de_date(a["datum"]) if a["datum"] else ""])
            el.append(Paragraph("<b>Steuerakte</b>", N))
            el.append(tbl(rows, [95 * mm, 50 * mm, 25 * mm]))
    tz = [r for r in e["paid_list"] if r.get("zehn_tage")]
    if tz:
        el.append(Paragraph("Nach der 10-Tage-Regel (§ 11 Abs. 1 Satz 2 EStG) diesem Jahr zugeordnet: " +
                            ", ".join(f"{esc_xml(r['nr'])} (bezahlt {de_date(r['bezahlt_am'])})" for r in tz), SM))

    def onpage(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(GRAY)
        cv.drawString(20 * mm, 10 * mm, f"Jahresabrechnung {year} · {s.get('firma', '')}")
        cv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Seite {dc.page}")
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    return buf.getvalue()


def _m04_tarif_selftest():
    # v2.6.3: reference values par. 32a EStG (Grundtabelle) and Soli exemption limit per year
    errs = []
    for zve, year, exp in ((20000, 2023, 1956), (10908, 2023, 0), (11784, 2024, 0), (12096, 2025, 0), (12348, 2026, 0)):
        got = tarif(zve, year)
        if got != exp:
            errs.append(f"ESt-Tarif {year}: zvE {zve} ergibt {got}, erwartet {exp}")
    for est, year, exp in ((17543, 2023, 0.0), (17643, 2023, 11.9), (19950, 2025, 0.0)):
        got = soli_calc(est, year)
        if abs(got - exp) > 0.005:
            errs.append(f"Soli {year}: ESt {est} ergibt {got}, erwartet {exp}")
    return errs


HOOK_SELFTEST.append(_m04_tarif_selftest)
