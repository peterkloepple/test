# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m16_jahresbericht
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ---------------- v1.6.1: Jahresbericht (annual business report) ----------------
JB_MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONTHS_LONG = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
JB_ACC = colors.HexColor("#5b3fd6")
JB_ACC2 = colors.HexColor("#e07a6a")
JB_ACC3 = colors.HexColor("#2f9e72")
JB_INK = colors.HexColor("#1e1a2b")
JB_GRAY = colors.HexColor("#6c6880")
JB_LINE = colors.HexColor("#e4e1ee")
JB_SOFT = colors.HexColor("#f3f1fb")
def _m(v):
    return money(v).replace(" EUR", " €")


JB_PAL = ["#5b3fd6", "#e07a6a", "#2f9e72", "#d9a441", "#3a8fd6", "#a04fc0", "#7d8597", "#c75b8f", "#5fa8a0", "#b8873a"]


def _int(v, default=0):
    m_ = re.match(r"\s*-?\d+", str(v if v is not None else ""))
    return int(m_.group(0)) if m_ else default


def _jb_num(v):
    """number from float/int or German/English formatted text, else None"""
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v or "").strip().replace("€", "").replace("EUR", "").strip()
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _pde(v):
    return f"{v:.1f}".replace(".", ",")


def _pct(a, b):
    if not b:
        return None
    return round(100.0 * (a - b) / abs(b), 1)


def _days(a, b):
    try:
        return (datetime.date.fromisoformat(b[:10]) - datetime.date.fromisoformat(a[:10])).days
    except Exception:
        return None


def saldo_at(iso):
    r = q("SELECT saldo, datum FROM kontostand WHERE datum<=? ORDER BY datum DESC, id DESC LIMIT 1", (iso,), one=True)
    return (r["saldo"], r["datum"]) if r else (None, None)


def euer_months(year, st=None, e=None):
    ys = str(year)
    st = st or stats(year)
    e = e or euer(year)
    mon = [{"m": x["m"], "umsatz": x["umsatz"], "anzahl": x["anzahl"], "zufluss": 0.0, "ausgaben": 0.0} for x in st["months"]]
    for r in e["paid_list"]:
        dd = (r["bezahlt_am"] or r["datum"] or "")[:10]
        if len(dd) < 7:
            continue
        mi = int(dd[5:7]) - 1 if dd[:4] == ys else (11 if dd[:4] > ys else 0)
        mon[mi]["zufluss"] += r["summe"] or 0
    for r in e["einnahmen_list"]:
        mon[int(r["datum"][5:7]) - 1]["zufluss"] += r["betrag"] or 0
    for r in e["ausgaben_list"]:
        mon[int(r["datum"][5:7]) - 1]["ausgaben"] += (r["betrag"] or 0) * (0.7 if (r["kategorie"] or "").startswith("Bewirtung") else 1.0)
    for x in mon:
        x["zufluss"], x["ausgaben"] = round(x["zufluss"], 2), round(x["ausgaben"], 2)
    return mon, round(e["ausgaben"] - sum(x["ausgaben"] for x in mon), 2)


def jahresbericht_data(year):
    year = int(year)
    ys = str(year)
    st = stats(year)
    e = euer(year)
    e_vj = euer(year - 1)
    st_vj_total = round(sum(r["summe"] for r in year_invoices(year - 1)), 2)
    invs = [r for r in year_invoices(year) if r["typ"] == "rechnung"]
    d = {"year": year, "stats": st, "euer": e, "vj": {"umsatz": st_vj_total, "einnahmen": e_vj["einnahmen"], "ausgaben": e_vj["ausgaben"],
                                                     "gewinn": e_vj["gewinn"]}}
    d["anzahl_rechnungen"] = len(invs)
    d["avg_rechnung"] = round(st["total"] / len(invs), 2) if invs else 0.0
    d["max_rechnung"] = max((r["summe"] for r in invs), default=0.0)
    # customers
    first = {}
    for r in q(f"SELECT customer_id, MIN(datum) d FROM invoices WHERE customer_id IS NOT NULL AND {COUNT_SQL} GROUP BY customer_id"):
        first[r["customer_id"]] = r["d"]
    d["kunden_aktiv"] = len(st["kunden"])
    d["neukunden"] = [c for c in st["kunden"] if c["customer_id"] and (first.get(c["customer_id"]) or "")[:4] == ys]
    d["top_anteil"] = st["kunden"][0]["anteil"] if st["kunden"] else 0
    # payment behaviour
    pays = []
    late = 0
    for r in q("SELECT * FROM invoices WHERE typ='rechnung' AND status='bezahlt' AND substr(datum,1,4)=? AND bezahlt_am<>''", (ys,)):
        dd = _days(r["datum"], r["bezahlt_am"])
        if dd is None:
            continue
        pays.append(dd)
        if dd > (_int(r.get("frist"), 7) or 7):
            late += 1
    pays.sort()
    d["zahlung"] = {"n": len(pays), "avg": round(sum(pays) / len(pays), 1) if pays else None,
                    "median": pays[len(pays) // 2] if pays else None, "spaet": late,
                    "mahnungen": q("SELECT COUNT(*) n FROM mahnungen WHERE substr(datum,1,4)=?", (ys,), one=True)["n"]}
    stich = today() if year >= datetime.date.today().year else f"{ys}-12-31"
    d["stichtag"] = stich
    d["offen_list"] = q("SELECT * FROM invoices WHERE typ='rechnung' AND datum<=? AND (status='offen' OR (status='bezahlt' AND bezahlt_am>?)) "
                        "ORDER BY datum", (stich, stich))
    # expenses by supplier
    sup = {}
    for r in e["ausgaben_list"]:
        k = (r["partner"] or "ohne Angabe").strip()
        s_ = sup.setdefault(k, {"name": k, "summe": 0.0, "anzahl": 0})
        s_["summe"] += r["betrag"]
        s_["anzahl"] += 1
    d["lieferanten"] = sorted(({**v, "summe": round(v["summe"], 2)} for v in sup.values()), key=lambda v: -v["summe"])
    # months on EUER basis (10-day rule, other income, expenses) so the year adds up to the EUER result
    mon, jp = euer_months(year, st, e)
    d["monate"] = mon
    d["jahresposten"] = jp
    st = dict(st, months=mon)
    # quarters
    qs = []
    for qi in range(4):
        ms = st["months"][qi * 3:qi * 3 + 3]
        qs.append({"q": qi + 1, "umsatz": round(sum(m["umsatz"] for m in ms), 2), "zufluss": round(sum(m["zufluss"] for m in ms), 2),
                   "ausgaben": round(sum(m["ausgaben"] for m in ms), 2), "anzahl": sum(m["anzahl"] for m in ms)})
    d["quartale"] = qs
    # bank
    s0, d0 = saldo_at(f"{year - 1}-12-31")
    s1, d1 = saldo_at(f"{year}-12-31")
    mon = []
    for m in range(1, 13):
        r = q("SELECT saldo FROM kontostand WHERE substr(datum,1,7)=? ORDER BY datum DESC, id DESC LIMIT 1", (f"{ys}-{m:02d}",), one=True)
        mon.append(r["saldo"] if r else None)
    bt = q("SELECT COALESCE(SUM(CASE WHEN betrag>0 THEN betrag END),0) ein, COALESCE(SUM(CASE WHEN betrag<0 THEN betrag END),0) aus, COUNT(*) n "
           "FROM bank_tx WHERE substr(datum,1,4)=?", (ys,), one=True)
    d["bank"] = {"start": s0, "start_datum": d0, "ende": s1, "ende_datum": d1, "monate": mon,
                 "ein": round(bt["ein"], 2), "aus": round(bt["aus"], 2), "n": bt["n"]}
    # salary + tax
    sal, emp = salary_sum(year)
    d["gehalt"], d["arbeitgeber"] = sal, emp
    try:
        tc = tax_calc(year)
        d["steuer"] = {"est": tc["calc"]["gesamt"], "gezahlt": tc["bereits_gezahlt"], "differenz": tc["differenz"], "zve": tc["calc"]["zve"],
                       "anteil_selbst": tc["anteil_selbst"], "grenz": tc["grenzsteuersatz"]}
    except Exception:
        d["steuer"] = None
    d["abschluss"] = tax_inputs(year).get("abschluss") or {}
    # assets, trips, teaching, certificates
    d["afa"] = [a for a in afa_year(year) if a["afa"] or (a["kaufdatum"] or "")[:4] == ys]
    fy = fahrten_year(year)
    d["fahrten"] = {k: v for k, v in fy.items() if k != "rows"}
    d["fahrten"]["anzahl"] = len(fy["rows"])
    ls = q("SELECT * FROM lessons WHERE substr(datum,1,4)=? AND (status IS NULL OR status='' OR status='stattgefunden')", (ys,))
    d["unterricht"] = {"stunden": len(ls), "dauer": round(sum(float(l_["dauer"] or 0) for l_ in ls), 1),
                       "schueler": len({l_["student_id"] for l_ in ls})}
    try:
        d["nachweise"] = cert_warnings(90)
    except Exception:
        d["nachweise"] = []
    d["belege_n"] = q("SELECT COUNT(*) n FROM belege WHERE substr(datum,1,4)=?", (ys,), one=True)["n"]
    return d


def _jb_bar(labels, series, w, h, money_axis=True):
    from reportlab.graphics.shapes import Drawing, String, Rect
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    dr = Drawing(w, h)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 38, 26, w - 48, h - 46
    bc.data = [[float(v or 0) for v in s_[1]] for s_ in series]
    bc.categoryAxis.categoryNames = labels
    bc.categoryAxis.labels.fontName = FONT_R()
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fillColor = JB_GRAY
    bc.categoryAxis.strokeColor = JB_LINE
    bc.valueAxis.labels.fontName = FONT_R()
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.labels.fillColor = JB_GRAY
    bc.valueAxis.strokeColor = None
    bc.valueAxis.gridStrokeColor = JB_LINE
    bc.valueAxis.visibleGrid = True
    bc.valueAxis.labelTextFormat = (lambda v: f"{v:,.0f}".replace(",", ".")) if money_axis else None
    mx = max([max([float(v or 0) for v in s_[1]] or [0]) for s_ in series] or [0])
    mn = min([min([float(v or 0) for v in s_[1]] or [0]) for s_ in series] + [0])
    bc.valueAxis.valueMin = mn * 1.1 if mn < 0 else 0
    bc.valueAxis.valueMax = mx * 1.12 if mx > 0 else 1
    bc.groupSpacing = 6
    bc.barSpacing = 1
    for i, s_ in enumerate(series):
        bc.bars[i].fillColor = s_[2]
        bc.bars[i].strokeColor = None
    dr.add(bc)
    x = 38
    for name, _, col in series:
        dr.add(Rect(x, h - 11, 8, 8, fillColor=col, strokeColor=None))
        dr.add(String(x + 11, h - 10, name, fontName=FONT_R(), fontSize=7.5, fillColor=JB_INK))
        x += 18 + len(name) * 4.2
    return dr


def _jb_line(labels, vals, w, h, col=JB_ACC, fill=True):
    from reportlab.graphics.shapes import Drawing, PolyLine, Polygon, String, Line, Circle
    dr = Drawing(w, h)
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 1:
        dr.add(String(10, h / 2, "keine Daten", fontName=FONT_R(), fontSize=8, fillColor=JB_GRAY))
        return dr
    ys_ = [v for _, v in pts]
    mn, mx = min(ys_ + [0]), max(ys_ + [0])
    raw = ((mx - mn) or 1) / 4
    mag = 10 ** math.floor(math.log10(raw))
    step = next(f * mag for f in (1, 2, 2.5, 5, 10) if f * mag >= raw)
    mn, mx = math.floor(mn / step) * step, math.ceil(mx / step) * step
    rg = (mx - mn) or 1
    nt = int(round(rg / step))
    x0, y0, ww, hh = 40, 18, w - 50, h - 28
    X = lambda i: x0 + i * ww / max(1, len(labels) - 1)
    Y = lambda v: y0 + (v - mn) / rg * hh
    for k in range(nt + 1):
        v = mn + step * k
        dr.add(Line(x0, Y(v), x0 + ww, Y(v), strokeColor=JB_LINE, strokeWidth=0.5))
        dr.add(String(x0 - 4, Y(v) - 2.5, f"{v:,.0f}".replace(",", "."), fontName=FONT_R(), fontSize=6.5, fillColor=JB_GRAY, textAnchor="end"))
    if mn < 0 < mx:
        dr.add(Line(x0, Y(0), x0 + ww, Y(0), strokeColor=JB_GRAY, strokeWidth=0.7))
    for i, lb in enumerate(labels):
        dr.add(String(X(i), 5, lb, fontName=FONT_R(), fontSize=6.8, fillColor=JB_GRAY, textAnchor="middle"))
    flat = []
    for i, v in pts:
        flat += [X(i), Y(v)]
    if fill and len(pts) > 1:
        base = Y(max(mn, 0)) if mn >= 0 else Y(0)
        poly = [X(pts[0][0]), base] + flat + [X(pts[-1][0]), base]
        dr.add(Polygon(poly, fillColor=colors.Color(col.red, col.green, col.blue, alpha=0.12), strokeColor=None))
    if len(pts) > 1:
        dr.add(PolyLine(flat, strokeColor=col, strokeWidth=1.6))
    for i, v in pts:
        dr.add(Circle(X(i), Y(v), 1.8, fillColor=col, strokeColor=colors.white, strokeWidth=0.5))
    return dr


def _jb_hbars(items, w, maxn=10, col=JB_ACC, fmt=None):
    from reportlab.graphics.shapes import Drawing, String, Rect
    items = items[:maxn]
    rowh = 15
    h = max(20, rowh * len(items) + 4)
    dr = Drawing(w, h)
    mx = max([v for _, v in items] or [1]) or 1
    lw, vw = w * 0.36, 62
    bw = w - lw - vw - 6
    for i, (lb, v) in enumerate(items):
        y = h - (i + 1) * rowh + 3
        t = lb if len(lb) <= 34 else lb[:33] + "…"
        dr.add(String(0, y + 2, t, fontName=FONT_R(), fontSize=7.8, fillColor=JB_INK))
        dr.add(Rect(lw, y, bw, 9, fillColor=JB_SOFT, strokeColor=None))
        dr.add(Rect(lw, y, max(1.5, bw * max(v, 0) / mx), 9, fillColor=col if not isinstance(col, list) else colors.HexColor(col[i % len(col)]), strokeColor=None))
        dr.add(String(w, y + 2, (fmt or _m)(v), fontName=FONT_B(), fontSize=7.8, fillColor=JB_INK, textAnchor="end"))
    return dr


def _jb_donut(items, size=120):
    from reportlab.graphics.shapes import Drawing, Circle
    from reportlab.graphics.charts.piecharts import Pie
    dr = Drawing(size, size)
    vals = [max(0.0, v) for _, v in items] or [1]
    if not sum(vals):
        vals = [1]
    p = Pie()
    p.x = p.y = 4
    p.width = p.height = size - 8
    p.data = vals
    p.labels = None
    p.slices.strokeColor = colors.white
    p.slices.strokeWidth = 1
    for i in range(len(vals)):
        p.slices[i].fillColor = colors.HexColor(JB_PAL[i % len(JB_PAL)])
    dr.add(p)
    dr.add(Circle(size / 2, size / 2, size * 0.26, fillColor=colors.white, strokeColor=None))
    return dr


def jahresbericht_pdf(year):
    year = int(year)
    from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, PageBreak,
                                    NextPageTemplate)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    s = get_settings()
    D = jahresbericht_data(year)
    st, e, vj = D["stats"], D["euer"], D["vj"]
    firma = s.get("firma") or ""
    inh = s.get("inhaber") or ""
    W, H = A4
    N = ParagraphStyle("n", fontName=FONT_R(), fontSize=9, leading=13, textColor=JB_INK)
    NS = ParagraphStyle("ns", parent=N, fontSize=8, leading=11, textColor=JB_GRAY)
    H1 = ParagraphStyle("h1", fontName=FONT_B(), fontSize=19, leading=23, textColor=JB_INK, spaceAfter=2)
    KIC = ParagraphStyle("k", fontName=FONT_B(), fontSize=7.5, leading=9, textColor=JB_ACC, spaceAfter=2)
    H2 = ParagraphStyle("h2", fontName=FONT_B(), fontSize=11.5, leading=15, textColor=JB_INK, spaceBefore=10, spaceAfter=5)
    LEAD = ParagraphStyle("lead", parent=N, fontSize=10, leading=15)
    TV = ParagraphStyle("tv", fontName=FONT_B(), fontSize=15, leading=18, textColor=JB_INK)
    TL = ParagraphStyle("tl", fontName=FONT_R(), fontSize=7.5, leading=9, textColor=JB_GRAY)
    TD = ParagraphStyle("td", fontName=FONT_R(), fontSize=7.5, leading=9, textColor=JB_GRAY)
    CW = W - 36 * mm

    def delta(a, b, good_up=True):
        p_ = _pct(a, b)
        if p_ is None:
            return "<font color='#6c6880'>kein Vorjahr</font>"
        up = p_ >= 0
        col = "#2f9e72" if (up == good_up) else "#c4453c"
        return f"<font color='{col}'>{'+' if up else '-'}{_pde(abs(p_))} %</font> <font color='#6c6880'>ggü. {year - 1}</font>"

    def tile(label, value, sub=""):
        return [Paragraph(label.upper(), TL), Paragraph(value, TV), Paragraph(sub, TD)]

    def tiles(cells, cols=4):
        rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
        pads = []
        for ri, r in enumerate(rows):
            while len(r) < cols:
                pads.append(("BACKGROUND", (len(r), ri), (len(r), ri), colors.white))
                r.append("")
        t = Table(rows, colWidths=[CW / cols] * cols)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), JB_SOFT), ("BOX", (0, 0), (-1, -1), 0, colors.white),
                               ("LINEAFTER", (0, 0), (-2, -1), 3, colors.white), ("LINEBELOW", (0, 0), (-1, -2), 3, colors.white),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 7)] + pads))
        return t

    def tbl(rows, widths, right=(), total=False):
        rows = [[Paragraph(str(c), ParagraphStyle("c", parent=N, fontSize=8, leading=10,
                                                  fontName=FONT_B() if (ri == 0 or (total and ri == len(rows) - 1)) else FONT_R(),
                                                  textColor=JB_GRAY if ri == 0 else JB_INK, alignment=2 if ci in right else 0))
                 if not hasattr(c, "wrap") else c for ci, c in enumerate(r)] for ri, r in enumerate(rows)]
        t = Table(rows, colWidths=widths, repeatRows=1)
        sty = [("LINEBELOW", (0, 0), (-1, 0), 0.8, JB_INK), ("LINEBELOW", (0, 1), (-1, -1), 0.3, JB_LINE),
               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
               ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if total:
            sty += [("LINEABOVE", (0, -1), (-1, -1), 0.8, JB_INK), ("BACKGROUND", (0, -1), (-1, -1), JB_SOFT)]
        t.setStyle(TableStyle(sty))
        return t

    def section(kicker, title, intro=None):
        out = [Paragraph(kicker.upper(), KIC), Paragraph(title, H1)]
        if intro:
            out.append(Paragraph(intro, NS))
        out.append(Spacer(1, 8))
        return out

    def two(a, b, wa=0.5):
        t = Table([[a, b]], colWidths=[CW * wa, CW * (1 - wa)])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 10),
                               ("RIGHTPADDING", (1, 0), (1, -1), 0)]))
        return t

    m = st["months"]
    tday = datetime.date.today()
    laufend = year == tday.year
    nmon = tday.month if laufend else 12
    stand = de_date(today()) if laufend else f"31.12.{year}"
    best = max(m, key=lambda x: x["umsatz"]) if any(x["umsatz"] for x in m) else None
    cum, run = [], 0.0
    for x in m:
        run += x["zufluss"] - x["ausgaben"]
        cum.append(round(run, 2))
    if D["jahresposten"]:
        run -= D["jahresposten"]
        cum[nmon - 1] = round(cum[nmon - 1] - D["jahresposten"], 2)
    if laufend:
        cum = [v if i < nmon else None for i, v in enumerate(cum)]
    top_cat = max(e["kategorien"].items(), key=lambda kv: kv[1]) if e["kategorien"] else None
    marge = round(100 * e["gewinn"] / e["einnahmen"], 1) if e["einnahmen"] else None

    # ---------- summary text ----------
    sm = []
    if st["total"]:
        p_ = _pct(st["total"], vj["umsatz"])
        sm.append(f"Im Jahr {year} wurden <b>{D['anzahl_rechnungen']} Rechnungen</b> über insgesamt <b>{_m(st['total'])}</b> gestellt"
                  + (f" – {'ein Plus' if p_ >= 0 else 'ein Minus'} von {_pde(abs(p_))} % gegenüber {year - 1} ({_m(vj['umsatz'])})" if p_ is not None else "") + ".")
    else:
        sm.append(f"Im Jahr {year} wurden keine Rechnungen gestellt.")
    sm.append(f"Auf dem Konto gingen Betriebseinnahmen von <b>{_m(e['einnahmen'])}</b> ein, die Betriebsausgaben betrugen <b>{_m(e['ausgaben'])}</b>. "
              f"Das ergibt einen {'Gewinn' if e['gewinn'] >= 0 else 'Verlust'} von <b>{_m(abs(e['gewinn']))}</b>"
              + (f" (Umsatzrendite {_pde(marge)} %)" if marge is not None and e["gewinn"] >= 0 else "") + ".")
    if best:
        sm.append(f"Stärkster Monat war der <b>{MONTHS_LONG[best['m'] - 1]}</b> mit {_m(best['umsatz'])} Umsatz.")
    if st["kunden"]:
        k0 = st["kunden"][0]
        sm.append(f"Wichtigster Kunde: <b>{esc_xml(k0['name'])}</b> mit {_pde(k0['anteil'])} % des Umsatzes"
                  + (f"; insgesamt {D['kunden_aktiv']} Kunden, davon {len(D['neukunden'])} neu." if D["kunden_aktiv"] > 1 else "."))
    if top_cat:
        sm.append(f"Größter Ausgabenposten: <b>{esc_xml(top_cat[0])}</b> ({_m(top_cat[1])}).")
    if D["offen_list"]:
        sm.append(f"Zum Stichtag {de_date(D['stichtag'])} waren <b>{len(D['offen_list'])} Rechnung(en)</b> über {_m(sum(r['summe'] for r in D['offen_list']))} offen.")
    if D["bank"]["ende"] is not None:
        sm.append(f"Kontostand am {de_date(D['bank']['ende_datum'])}: <b>{_m(D['bank']['ende'])}</b>.")

    el = [NextPageTemplate("body"), PageBreak()]
    # ---------- 1 overview ----------
    el += section("Überblick", f"Das Jahr {year} auf einen Blick",
                  f"Laufendes Geschäftsjahr – Stand {stand}. Alle Werte bis heute, Vergleich mit dem gesamten Vorjahr." if laufend else None)
    el.append(tiles([
        tile("Umsatz (gestellt)", _m(st["total"]), delta(st["total"], vj["umsatz"])),
        tile("Betriebseinnahmen", _m(e["einnahmen"]), delta(e["einnahmen"], vj["einnahmen"])),
        tile("Betriebsausgaben", _m(e["ausgaben"]), delta(e["ausgaben"], vj["ausgaben"], good_up=False)),
        tile("Gewinn / Verlust", f"<font color='{'#2f9e72' if e['gewinn'] >= 0 else '#c4453c'}'>{_m(e['gewinn'])}</font>", delta(e["gewinn"], vj["gewinn"])),
        tile("Rechnungen", str(D["anzahl_rechnungen"]), f"Ø {_m(D['avg_rechnung'])} · max. {_m(D['max_rechnung'])}"),
        tile("Kunden", str(D["kunden_aktiv"]), f"{len(D['neukunden'])} Neukunden · Top-Kunde {D['top_anteil']:.0f} %"),
        tile("Offene Forderungen", _m(sum(r["summe"] for r in D["offen_list"])), f"{len(D['offen_list'])} Rechnung(en)"),
        tile("Kontostand", _m(D["bank"]["ende"]) if D["bank"]["ende"] is not None else "–",
             (f"am {de_date(D['bank']['ende_datum'])}" if D["bank"]["ende_datum"] else "") +
             (f" · Anfang {_m(D['bank']['start'])}" if D["bank"]["start"] is not None else "")),
    ]))
    el.append(Spacer(1, 12))
    el.append(Paragraph("Zusammenfassung", H2))
    el.append(Paragraph(" ".join(sm), LEAD))
    el.append(Spacer(1, 10))
    el.append(Paragraph("Umsatz und Ausgaben je Monat", H2))
    el.append(_jb_bar(JB_MONTHS, [("Umsatz (gestellt)", [x["umsatz"] for x in m], JB_ACC), ("Zahlungseingang", [x["zufluss"] for x in m], JB_ACC3),
                                  ("Ausgaben", [x["ausgaben"] for x in m], JB_ACC2)], CW, 175))
    el.append(Paragraph("Ergebnis kumuliert (Betriebseinnahmen minus Betriebsausgaben, laufende Summe)", H2))
    el.append(_jb_line(JB_MONTHS, cum, CW, 120, JB_ACC3 if run >= 0 else JB_ACC2))

    # ---------- 2 revenue ----------
    el += [PageBreak()] + section("Umsatz", "Umsatz &amp; Ergebnis im Jahresverlauf",
                                  "Umsatz = gestellte Rechnungen nach Rechnungsdatum. Zahlungseingang = Betriebseinnahmen nach Zahlungsdatum (Zuflussprinzip, "
                                  "10-Tage-Regel um den Jahreswechsel). Ausgaben = Belege nach Belegdatum; Abschreibungen und Pauschalen als Jahresposten. "
                                  "Die Summenzeile entspricht der EÜR.")
    rows = [["Monat", "Rechnungen", "Umsatz", "Zahlungseingang", "Ausgaben", "Saldo"]]
    for x in m:
        rows.append([MONTHS_LONG[x["m"] - 1], str(x["anzahl"]), _m(x["umsatz"]), _m(x["zufluss"]), _m(x["ausgaben"]), _m(round(x["zufluss"] - x["ausgaben"], 2))])
    if D["jahresposten"]:
        rows.append(["Jahresposten (AfA, Fahrten, Homeoffice)", "", "", "", _m(D["jahresposten"]), _m(-D["jahresposten"])])
    rows.append(["Summe", str(sum(x["anzahl"] for x in m)), _m(sum(x["umsatz"] for x in m)), _m(e["einnahmen"]),
                 _m(e["ausgaben"]), _m(e["gewinn"])])
    el.append(tbl(rows, [CW * 0.2, CW * 0.12, CW * 0.17, CW * 0.18, CW * 0.16, CW * 0.17], right=(1, 2, 3, 4, 5), total=True))
    el.append(Paragraph("Quartale", H2))
    rows = [["Quartal", "Rechnungen", "Umsatz", "Zahlungseingang", "Ausgaben", "Anteil am Umsatz"]]
    for x in D["quartale"]:
        rows.append([f"Q{x['q']}", str(x["anzahl"]), _m(x["umsatz"]), _m(x["zufluss"]), _m(x["ausgaben"]),
                     f"{(100 * x['umsatz'] / st['total']) if st['total'] else 0:.1f} %".replace(".", ",")])
    el.append(tbl(rows, [CW * 0.16, CW * 0.14, CW * 0.17, CW * 0.19, CW * 0.16, CW * 0.18], right=(1, 2, 3, 4, 5)))
    el.append(Paragraph("Zahlungsverhalten", H2))
    z = D["zahlung"]
    el.append(tiles([
        tile("Ø Zahlungsdauer", f"{str(z['avg']).replace('.', ',')} Tage" if z["avg"] is not None else "–", f"Median {z['median']} Tage" if z["median"] is not None else ""),
        tile("Bezahlte Rechnungen", str(z["n"]), "mit Zahlungsdatum"),
        tile("Nach Frist bezahlt", str(z["spaet"]), "später als Zahlungsziel"),
        tile("Mahnungen", str(z["mahnungen"]), f"im Jahr {year}")]))
    if D["offen_list"]:
        el.append(Paragraph(f"Offene Rechnungen zum {de_date(D['stichtag'])}", H2))
        rows = [["Nr.", "Datum", "Kunde", "Tage offen", "Betrag"]]
        for r in D["offen_list"][:20]:
            rows.append([esc_xml(r["nr"] or ""), de_date(r["datum"]), esc_xml(inv_name(r)[:50]), str(_days(r["datum"], D["stichtag"]) or 0), _m(r["summe"])])
        el.append(tbl(rows, [CW * 0.14, CW * 0.14, CW * 0.44, CW * 0.12, CW * 0.16], right=(3, 4)))

    # ---------- 3 customers & services ----------
    el += [PageBreak()] + section("Kunden &amp; Leistungen", "Wer kauft was?")
    if st["kunden"]:
        legend = [[Paragraph(f"<font name='ZapfDingbats' color='{JB_PAL[i % len(JB_PAL)]}'>n</font>  {esc_xml(c['name'][:30])}", NS),
                   Paragraph(f"{c['anteil']:.1f} %".replace(".", ","), ParagraphStyle("r", parent=NS, alignment=2))]
                  for i, c in enumerate(st["kunden"][:8])]
        lt = Table(legend, colWidths=[CW * 0.33, CW * 0.12])
        lt.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        el.append(Paragraph("Umsatzanteile der Kunden", H2))
        el.append(two(_jb_donut([(c["name"], c["summe"]) for c in st["kunden"][:8]] +
                                ([("Rest", sum(c["summe"] for c in st["kunden"][8:]))] if len(st["kunden"]) > 8 else []), 130), lt, 0.42))
        rows = [["#", "Kunde", "Rechnungen", "Umsatz", "Anteil"]]
        for i, c in enumerate(st["kunden"][:15]):
            neu = " <font color='#2f9e72' size='6.5'>NEU</font>" if c in D["neukunden"] else ""
            rows.append([str(i + 1), Paragraph(esc_xml(c["name"]) + neu, ParagraphStyle("c", parent=N, fontSize=8, leading=10)), str(c["anzahl"]),
                         _m(c["summe"]), f"{c['anteil']:.1f} %".replace(".", ",")])
        el.append(Spacer(1, 6))
        el.append(tbl(rows, [CW * 0.06, CW * 0.5, CW * 0.13, CW * 0.17, CW * 0.14], right=(2, 3, 4)))
        if D["top_anteil"] >= 50:
            el.append(Spacer(1, 4))
            el.append(Paragraph(f"Hinweis: Ein Kunde steht für {D['top_anteil']:.0f} % des Umsatzes – hohe Abhängigkeit von einem Auftraggeber.", NS))
    else:
        el.append(Paragraph("Keine Rechnungen in diesem Jahr.", N))
    if st["leistungen"]:
        lm = {}
        for x in st["leistungen"]:
            k_ = (x["name"] or x["nr"] or "–").strip()
            o_ = lm.setdefault(k_, {"name": k_, "menge": 0.0, "summe": 0.0})
            o_["menge"] += x["menge"] or 0
            o_["summe"] += x["summe"]
        ll = sorted(lm.values(), key=lambda v: -v["summe"])
        el.append(Paragraph("Leistungen / Bausteine nach Umsatz", H2))
        el.append(_jb_hbars([(x["name"] + (f"  ({x['menge']:g}×)".replace(".", ",") if x["menge"] else ""), round(x["summe"], 2)) for x in ll],
                            CW, 12, col=JB_PAL))
    if st["bereiche"]:
        el.append(Paragraph("Projekte &amp; Bereiche", H2))
        el.append(_jb_hbars(sorted(st["bereiche"].items(), key=lambda kv: -kv[1]), CW, 8, col=JB_ACC3))
        rows = [["Projekt", "Bereich", "Rechnungen", "Umsatz"]] + [[esc_xml(((p_["nr"] or "") + " " + (p_["name"] or ""))[:55]), esc_xml(p_["bereich"] or ""), str(p_["anzahl"]), _m(p_["summe"])]
                                                                for p_ in st["projekte"][:12]]
        el.append(Spacer(1, 4))
        el.append(tbl(rows, [CW * 0.5, CW * 0.2, CW * 0.13, CW * 0.17], right=(2, 3)))

    # ---------- 4 expenses ----------
    el += [PageBreak()] + section("Ausgaben", "Wofür das Geld ausgegeben wurde",
                                  "Betriebsausgaben laut EÜR (Bewirtung zu 70 %), inklusive Abschreibungen, km-Pauschale und Homeoffice-Pauschale.")
    cats = sorted(e["kategorien"].items(), key=lambda kv: -kv[1])
    if cats:
        el.append(Paragraph("Ausgaben nach Kategorie", H2))
        el.append(_jb_hbars(cats, CW, 14, col=JB_ACC2))
        rows = [["Kategorie", "Betrag", "Anteil", f"Vorjahr {year - 1}"]]
        e_vj = euer(year - 1)
        for k, v in cats:
            rows.append([esc_xml(k), _m(v), f"{(100 * v / e['ausgaben']) if e['ausgaben'] else 0:.1f} %".replace(".", ","),
                         _m(e_vj["kategorien"].get(k, 0)) if e_vj["kategorien"].get(k) else "–"])
        rows.append(["Summe Betriebsausgaben", _m(e["ausgaben"]), "100 %", _m(e_vj["ausgaben"]) if e_vj["ausgaben"] else "–"])
        el.append(Spacer(1, 6))
        el.append(tbl(rows, [CW * 0.5, CW * 0.18, CW * 0.12, CW * 0.2], right=(1, 2, 3), total=True))
    else:
        el.append(Paragraph("Keine Betriebsausgaben erfasst.", N))
    if D["lieferanten"]:
        el.append(Paragraph("Größte Lieferanten / Zahlungsempfänger", H2))
        rows = [["Lieferant", "Belege", "Summe"]] + [[esc_xml(x["name"][:60]), str(x["anzahl"]), _m(x["summe"])] for x in D["lieferanten"][:12]]
        el.append(tbl(rows, [CW * 0.62, CW * 0.14, CW * 0.24], right=(1, 2)))

    # ---------- 5 bank, salary, tax ----------
    el += [PageBreak()] + section("Liquidität &amp; Steuer", "Konto, Einkommen und Steuer")
    b = D["bank"]
    el.append(tiles([
        tile("Konto 01.01.", _m(b["start"]) if b["start"] is not None else "–", de_date(b["start_datum"]) if b["start_datum"] else "kein Stand erfasst"),
        tile("Konto " + (stand[:6] if not laufend else "aktuell"), _m(b["ende"]) if b["ende"] is not None else "–", de_date(b["ende_datum"]) if b["ende_datum"] else "kein Stand erfasst"),
        tile("Geldeingänge (Bank)", _m(b["ein"]), f"{b['n']} Buchungen im Jahr"),
        tile("Geldausgänge (Bank)", _m(abs(b["aus"])), "alle Abbuchungen inkl. privat")]))
    if any(v is not None for v in b["monate"]):
        el.append(Paragraph("Kontostand je Monatsende", H2))
        el.append(_jb_line(JB_MONTHS, b["monate"], CW, 120, JB_ACC))
    g = D["gehalt"]
    if g.get("brutto"):
        el.append(Paragraph("Einkommen aus Anstellung", H2))
        rows = [["Arbeitgeber", "Quelle", "Brutto", "Lohnsteuer", "Netto"]] + [[esc_xml(a["name"]), a["quelle"], _m(a["brutto"]), _m(a["lst"]), _m(a["netto"])]
                                                                            for a in D["arbeitgeber"]]
        if len(D["arbeitgeber"]) > 1:
            rows.append(["Summe", "", _m(g["brutto"]), _m(g["lst"]), _m(g["netto"])])
        el.append(tbl(rows, [CW * 0.3, CW * 0.24, CW * 0.16, CW * 0.14, CW * 0.16], right=(2, 3, 4), total=len(D["arbeitgeber"]) > 1))
        ges = round(g["brutto"] + e["gewinn"], 2)
        el.append(Spacer(1, 4))
        el.append(Paragraph(f"Gesamteinkünfte vor Steuern (Bruttolohn + Gewinn aus Selbstständigkeit): <b>{_m(ges)}</b>"
                            + (f" – davon {_pde(100 * e['gewinn'] / ges)} % selbstständig" if ges > 0 and e["gewinn"] > 0 else "") + ".", N))
    ab = D["abschluss"]
    if _jb_num(ab.get("est_festgesetzt")) is not None or _jb_num(ab.get("erstattung")) is not None:
        el.append(Paragraph("Steuerbescheid", H2))
        rows = [["Position", "Betrag"]]
        for k_, lb in (("zve", "Zu versteuerndes Einkommen"), ("est_festgesetzt", "Festgesetzte Einkommensteuer"), ("soli_festgesetzt", "Solidaritätszuschlag"),
                       ("lst_abzug", "Abzug Lohnsteuer"), ("erstattung", "Erstattung (+) / Nachzahlung (−)")):
            if _jb_num(ab.get(k_)) is not None:
                rows.append([lb, _m(_jb_num(ab[k_]))])
        el.append(tbl(rows, [CW * 0.7, CW * 0.3], right=(1,)))
        if ab.get("bescheid_datum"):
            el.append(Paragraph(f"Bescheid vom {de_date(ab['bescheid_datum'])}" + (" · Jahr abgeschlossen" if ab.get("abgeschlossen") else ""), NS))
    elif D["steuer"] and (g.get("brutto") or e["gewinn"]):
        t_ = D["steuer"]
        el.append(Paragraph("Steuer-Schätzung (noch kein Bescheid)", H2))
        el.append(tbl([["Position", "Betrag"], ["Zu versteuerndes Einkommen (geschätzt)", _m(t_["zve"])], ["Einkommensteuer + Soli + KiSt", _m(t_["est"])],
                       ["Bereits gezahlt (Lohnsteuer, Vorauszahlungen)", _m(t_["gezahlt"])],
                       ["Voraussichtlich " + ("Nachzahlung" if t_["differenz"] > 0 else "Erstattung"), _m(abs(t_["differenz"]))],
                       ["Steueranteil der Selbstständigkeit", _m(t_["anteil_selbst"])]], [CW * 0.7, CW * 0.3], right=(1,)))
        el.append(Paragraph("Schätzung nach Tarif – ersetzt keine Steuerberatung.", NS))

    # ---------- 6 more ----------
    more = []
    if D["afa"]:
        more.append(Paragraph("Anlagen &amp; Abschreibungen", H2))
        rows = [["Gegenstand", "Kauf", "Anschaffung", f"AfA {year}", "Restwert"]] + [[esc_xml((a["bezeichnung"] or "")[:45]), de_date(a["kaufdatum"]), _m(a["betrag"]), _m(a["afa"]), _m(a["restwert"])]
                                                                                for a in D["afa"]]
        more.append(tbl(rows, [CW * 0.4, CW * 0.14, CW * 0.16, CW * 0.14, CW * 0.16], right=(2, 3, 4)))
    f_ = D["fahrten"]
    u_ = D["unterricht"]
    extra = []
    if f_["anzahl"]:
        extra += [tile("Dienstfahrten", f"{str(f_['dienst_km']).replace('.', ',')} km", f"{_m(f_['dienst_eur'])} Betriebsausgabe"),
                  tile("Fahrten zur Arbeit", f"{f_['pendel_tage']} Tage", f"{_m(f_['pendel_eur'])} Werbungskosten")]
    if u_["stunden"]:
        extra += [tile("Unterrichtsstunden", str(u_["stunden"]), f"{str(u_['dauer']).replace('.', ',')} Std. · {u_['schueler']} Schüler")]
    mu = [x["umsatz"] for x in m if x["umsatz"]]
    extra += [tile("Erfasste Belege", str(D["belege_n"]), f"im Jahr {year}"),
              tile("Bankbuchungen", str(D["bank"]["n"]), f"im Jahr {year}"),
              tile("Ø Umsatz je Monat", _m(round(st["total"] / nmon, 2)), f"{len(mu)} von {nmon} Monaten mit Umsatz"),
              tile("Ø Ausgaben je Monat", _m(round(e["ausgaben"] / nmon, 2)), "inkl. Jahresposten")]
    more.append(Paragraph("Weitere Kennzahlen", H2))
    more.append(tiles(extra, 4))
    if D["nachweise"]:
        more.append(Paragraph("Nachweise mit Handlungsbedarf (nächste 90 Tage)", H2))
        rows = [["Nachweis", "Person", "Status", "Datum"]] + [[esc_xml(z_.get("bezeichnung") or ""), esc_xml(z_.get("person") or ""), z_.get("art") or "", de_date(z_.get("datum") or "")]
                                                             for z_ in D["nachweise"][:10]]
        more.append(tbl(rows, [CW * 0.42, CW * 0.24, CW * 0.18, CW * 0.16]))
    jahre = [y_ for y_ in st["jahre"] if y_["year"] <= year]
    if len(jahre) > 1:
        more.append(Paragraph("Mehrjahresvergleich", H2))
        more.append(_jb_bar([str(y_["year"]) for y_ in jahre], [("Einnahmen", [y_["einnahmen"] for y_ in jahre], JB_ACC3),
                                                               ("Ausgaben", [y_["ausgaben"] for y_ in jahre], JB_ACC2),
                                                               ("Gewinn", [y_["gewinn"] for y_ in jahre], JB_ACC)], CW, 160))
        rows = [["Jahr", "Umsatz", "Einnahmen", "Ausgaben", "Gewinn", "Veränderung Gewinn"]]
        prev = None
        for y_ in jahre:
            rows.append([str(y_["year"]), _m(y_["umsatz"]), _m(y_["einnahmen"]), _m(y_["ausgaben"]), _m(y_["gewinn"]),
                         (_m(round(y_["gewinn"] - prev, 2)) if prev is not None else "–")])
            prev = y_["gewinn"]
        more.append(tbl(rows, [CW * 0.1, CW * 0.18, CW * 0.18, CW * 0.18, CW * 0.18, CW * 0.18], right=(1, 2, 3, 4, 5)))
    el += [PageBreak()] + section("Anhang", "Anlagen, Aktivitäten &amp; Vergleich") + more
    el.append(Spacer(1, 14))
    el.append(Paragraph("Grundlage: alle im Programm erfassten Rechnungen, Belege, Bankbuchungen und Kontostände. Umsatzzahlen nach Rechnungsdatum, "
                        "EÜR-Werte nach Zuflussprinzip – Abweichungen zwischen „Umsatz“ und „Einnahmen“ entstehen durch offene oder im Folgejahr bezahlte Rechnungen. "
                        f"Erstellt am {de_date(today())} mit {APP_NAME} v{APP_VERSION}.", NS))

    # ---------- page templates ----------
    logo = os.path.join(ASSET_DIR, s.get("logo") or "logo.jpg")

    def cover(c, doc):
        c.saveState()
        c.setFillColor(JB_INK)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(JB_ACC)
        c.rect(0, H * 0.36, W, 6, fill=1, stroke=0)
        if os.path.exists(logo):
            try:
                ir = ImageReader(logo)
                iw, ih = ir.getSize()
                hh = 26 * mm
                ww = hh * iw / ih
                c.setFillColor(colors.white)
                c.roundRect(20 * mm - 3, H - 30 * mm - hh - 3, ww + 6, hh + 6, 4, fill=1, stroke=0)
                c.drawImage(ir, 20 * mm, H - 30 * mm - hh, ww, hh, mask="auto")
            except Exception:
                pass
        c.setFillColor(colors.HexColor("#b9acf5"))
        c.setFont(FONT_B(), 11)
        c.drawString(20 * mm, H * 0.36 + 60 * mm, "JAHRESBERICHT")
        c.setFillColor(colors.white)
        c.setFont(FONT_B(), 64)
        c.drawString(20 * mm, H * 0.36 + 34 * mm, str(year))
        c.setFont(FONT_R(), 15)
        c.drawString(20 * mm, H * 0.36 + 20 * mm, firma)
        c.setFillColor(colors.HexColor("#cfc8e6"))
        c.setFont(FONT_R(), 10)
        c.drawString(20 * mm, H * 0.36 + 13 * mm, inh)
        c.setFont(FONT_R(), 9)
        y = H * 0.36 - 22 * mm
        for lb, v in (("Umsatz", _m(st["total"])), ("Gewinn / Verlust", _m(e["gewinn"])), ("Rechnungen", str(D["anzahl_rechnungen"])),
                      ("Kunden", str(D["kunden_aktiv"]))):
            c.setFillColor(colors.HexColor("#9b93b8"))
            c.setFont(FONT_R(), 8)
            c.drawString(20 * mm, y, lb.upper())
            c.setFillColor(colors.white)
            c.setFont(FONT_B(), 16)
            c.drawString(20 * mm, y - 7 * mm, v)
            y -= 17 * mm
        c.setFillColor(colors.HexColor("#9b93b8"))
        c.setFont(FONT_R(), 8)
        c.drawString(20 * mm, 14 * mm, f"Zeitraum 01.01.{year} – {stand}{' (laufendes Jahr)' if laufend else ''} · erstellt am {de_date(today())}")
        c.restoreState()

    def body(c, doc):
        c.saveState()
        c.setFillColor(JB_ACC)
        c.rect(18 * mm, H - 12 * mm, 14, 2.2, fill=1, stroke=0)
        c.setFillColor(JB_GRAY)
        c.setFont(FONT_R(), 7.5)
        c.drawString(18 * mm + 18, H - 12.4 * mm, f"Jahresbericht {year} · {firma}")
        c.drawRightString(W - 18 * mm, 10 * mm, f"Seite {doc.page - 1}")
        c.setStrokeColor(JB_LINE)
        c.setLineWidth(0.5)
        c.line(18 * mm, 14 * mm, W - 18 * mm, 14 * mm)
        c.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, title=f"Jahresbericht {year}", author=inh, creator=f"{APP_NAME} v{APP_VERSION}")
    fr_c = Frame(0, 0, W, H, id="c")
    fr_b = Frame(18 * mm, 18 * mm, W - 36 * mm, H - 36 * mm, id="b", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[fr_c], onPage=cover), PageTemplate(id="body", frames=[fr_b], onPage=body)])
    doc.build([Spacer(1, 1)] + el)
    return buf.getvalue()
