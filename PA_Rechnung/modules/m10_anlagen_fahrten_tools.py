# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m10_anlagen_fahrten_tools
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ---------------- AfA / assets ----------------


AFA_PRESETS = [("Computer / Hardware / Software", 1), ("Audio-/Video-/Konferenztechnik", 7), ("Werkzeug / Maschinen / Schweißgeräte", 10),
               ("Pkw", 6), ("Büromöbel", 13), ("Sonstiges", 5)]




def afa_cum(a, year):
    """cumulated depreciation up to end of 'year'"""
    d0 = d_iso(a["kaufdatum"])
    b = float(a["betrag"] or 0)
    if not d0 or year < d0.year:
        return 0.0
    ab = d_iso(a["abgang"])
    if ab and year >= ab.year:
        return b
    if (a["methode"] or "linear") in ("gwg", "sofort"):
        return b
    nd = max(float(a["nd_jahre"] or 1), 0.0833)
    if nd <= 1:
        return b  # digital assets (BMF 2021/2022): full deduction in year of purchase
    total_m = round(nd * 12)
    months = (year - d0.year) * 12 + (12 - d0.month + 1)
    return round(min(b, b * months / total_m), 2)


def afa_year(year):
    rows = []
    for a in q("SELECT * FROM assets ORDER BY kaufdatum"):
        v = round(afa_cum(a, year) - afa_cum(a, year - 1), 2)
        rest = round(float(a["betrag"] or 0) - afa_cum(a, year), 2)
        a["afa"] = v
        a["restwert"] = max(0.0, rest)
        rows.append(a)
    return rows


def gwg_check(brutto, datum=None):
    """GWG limit 800 EUR on the acquisition cost (par. 6 Abs. 2 EStG). With input tax deduction (Regelbesteuerung)
    that is the net price; a Kleinunternehmer cannot deduct input tax, so the gross price IS the acquisition cost."""
    b = float(brutto or 0)
    try:
        regel = (not get_settings().get("kleinunternehmer", True)) or ("m80_regel_on" in globals() and m80_regel_on(datum))
    except Exception:
        regel = False
    return (b / 1.19 if regel else b) <= 800.0

def _m10_boot(d):
    # v2.1.0: the UI shows the GWG hint on the same basis (Kleinunternehmer gross, Regelbesteuerung net)
    try:
        regel = (not get_settings().get("kleinunternehmer", True)) or ("m80_regel_on" in globals() and m80_regel_on(None))
        d["gwg_brutto"] = not regel
    except Exception:
        d["gwg_brutto"] = True


HOOK_BOOT.append(_m10_boot)

# ---------------- Fahrten / Homeoffice ----------------


def entfernungspauschale(km_einfach, year):
    km = math.floor(max(0, km_einfach))
    if year >= 2026:
        return km * 0.38
    return min(km, 20) * 0.30 + max(0, km - 20) * 0.38


def fahrten_year(year):
    s = get_settings()
    rows = q("SELECT * FROM fahrten WHERE substr(datum,1,4)=? ORDER BY datum", (str(year),))
    dienst_km = sum(float(r["km"] or 0) for r in rows if (r["art"] or "dienst") == "dienst")
    # Entfernungspauschale: once per working day (par. 9 Abs. 1 Nr. 4 EStG) - two entries on one day count once (longest distance)
    pdays = {}
    for r in rows:
        if r["art"] == "pendel":
            k_ = (r["datum"] or "")[:10]
            pdays[k_] = max(pdays.get(k_, 0.0), float(r["km"] or 0))
    pendel = sum(entfernungspauschale(v, year) for v in pdays.values())
    return {"rows": rows, "dienst_km": round(dienst_km, 1), "dienst_eur": round(dienst_km * float(s.get("km_dienst") or 0.30), 2),
            "pendel_eur": round(pendel, 2), "pendel_tage": len(pdays)}


def homeoffice_eur(t):
    tage = min(int(float(t.get("ho_tage") or 0)), 210)
    return round(tage * 6.0, 2)


def euer_form(year):
    e = euer(year)
    lines = {}

    def add(key, v):
        if not v:
            return
        z, kz, lbl = EUER_FORM.get(key, EUER_FORM["Sonstige Betriebsausgaben"])
        k = (z, kz)
        lines.setdefault(k, [z, kz, lbl, 0.0])
        lines[k][3] = round(lines[k][3] + v, 2)
    add("_einnahmen_ku", e["einnahmen"])
    for k, v in e["kategorien"].items():
        add(k, v)
    out = sorted(lines.values(), key=lambda r: (r[0], r[1]))
    out.append([75, 199, "Summe Betriebsausgaben", e["ausgaben"]])
    out.append([97, 219, "Steuerpflichtiger Gewinn/Verlust", e["gewinn"]])
    return out

# ---------------- BOM import (Inventor) ----------------


def read_table_file(path):
    low = path.lower()
    if low.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = [["" if v is None else str(v) for v in r] for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    text = _decode(open(path, "rb").read())
    sample = text[:4000]
    delim = max([";", "\t", ","], key=sample.count)
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim)]


def parse_mass_kg(v):
    v = (v or "").strip().lower().replace(",", ".")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(kg|g|t)?", v)
    if not m:
        return 0.0
    n = float(m.group(1))
    return n / 1000 if m.group(2) == "g" else (n * 1000 if m.group(2) == "t" else n)


def parse_bom(path):
    rows = read_table_file(path)
    hi = None
    for i, r in enumerate(rows[:30]):
        low = " ".join(c.lower() for c in r)
        if re.search(r"menge|anz|qty|quantity|stück|stueck", low) and re.search(r"beschreibung|benennung|description|bauteil|teil|part", low):
            hi = i
            break
    if hi is None:
        raise ValueError("Kopfzeile der Stückliste nicht erkannt (Spalten Menge und Benennung/Beschreibung erwartet).")
    head = [c.strip().lower() for c in rows[hi]]

    def col(*pats):
        for pat in pats:
            for i, h in enumerate(head):
                if re.search(pat, h):
                    return i
        return None
    c_pos = col(r"^pos|position|element|item")
    c_nr = col(r"bauteilnummer|teilenummer|part number|artikelnummer|sachnummer|zeichnungsnummer|nummer")
    c_desc = col(r"beschreibung|benennung|description|titel|bezeichnung")
    c_qty = col(r"menge|anz|qty|quantity|stück|stueck")
    c_unit = col(r"einheit|unit|^me$")
    c_mat = col(r"material|werkstoff")
    c_mass = col(r"masse|gewicht|mass|weight")
    out = []
    for r in rows[hi + 1:]:
        g = lambda i: (str(r[i]).strip() if i is not None and i < len(r) and r[i] is not None else "")
        name = g(c_desc) or g(c_nr)
        if not name:
            continue
        qv = g(c_qty)
        try:
            qty = float(re.sub(r"[^\d,.\-]", "", qv).replace(",", ".") or 1)
        except Exception:
            qty = 1.0
        out.append({"pos": g(c_pos), "nr": g(c_nr), "name": name, "qty": qty, "unit": g(c_unit) or "Stk",
                    "material": g(c_mat), "masse_kg": parse_mass_kg(g(c_mass))})
    return out

# ---------------- Certificates ----------------


CERT_TYPES = ["Schweißerprüfung (ISO 9606)", "Schweißverfahrensprüfung (WPQR)", "Schweißanweisung (WPS)",
              "EN 1090 Zertifikat", "Schweißaufsicht", "Prüfgerät / Kalibrierung", "Elektrofachkraft / DGUV V3",
              "Hersteller-Zertifizierung (Q-SYS, Crestron …)", "Sonstiges"]


def cert_warnings(days=60):
    t = datetime.date.today()
    out = []
    for z in q("SELECT * FROM zertifikate WHERE aktiv=1"):
        gb = d_iso(z["gueltig_bis"])
        if gb and gb <= t + datetime.timedelta(days=days):
            out.append({"id": z["id"], "bezeichnung": z["bezeichnung"], "person": z["person"], "art": "abgelaufen" if gb < t else "läuft ab",
                        "datum": gb.isoformat(), "tage": (gb - t).days})
        if z["bestaetigung_monate"]:
            base = d_iso(z["bestaetigt_am"]) or d_iso(z["ausgestellt"])
            if base:
                nb = add_months(base, int(z["bestaetigung_monate"]))
                if nb <= t + datetime.timedelta(days=30):
                    out.append({"id": z["id"], "bezeichnung": z["bezeichnung"], "person": z["person"], "art": "Bestätigung fällig",
                                "datum": nb.isoformat(), "tage": (nb - t).days})
    return sorted(out, key=lambda w: w["tage"])

# ---------------- Handover documentation ----------------


def handover_pdf(pid, file_ids, notes=""):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    p = get_project(pid)
    s = get_settings()
    files = [f for f in p["files"] if f["id"] in set(file_ids)] if file_ids is not None else p["files"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm,
                            title=f"Projektdokumentation {p['nr']}", author=s.get("inhaber", ""))
    ss = font_stylesheet()
    H = ParagraphStyle("h", parent=ss["Title"], fontSize=24, leading=28, alignment=0)
    N = ParagraphStyle("n", parent=ss["Normal"], fontSize=10, leading=14)
    el = [Spacer(1, 30 * mm)]
    lp = os.path.join(ASSET_DIR, s.get("logo") or "")
    if s.get("logo") and os.path.exists(lp):
        from reportlab.platypus import Image as RLImage
        try:
            img = ImageReader(lp)
            iw, ih = img.getSize()
            el.append(RLImage(lp, width=30 * mm * iw / ih, height=30 * mm))
            el.append(Spacer(1, 10 * mm))
        except Exception:
            pass
    el += [Paragraph("Projektdokumentation", H), Spacer(1, 4), Paragraph(f"<b>{esc_xml(p['nr'])} · {esc_xml(p['name'])}</b>", N),
           Paragraph(f"Kunde: {esc_xml((p['customer'] or {}).get('firma') or (p['customer'] or {}).get('name') or '-')}", N),
           Paragraph(f"Bereich: {esc_xml(p['bereich'])} · Zeitraum: {de_date(p['start'])} – {de_date(p['ende']) or 'laufend'}", N),
           Paragraph(f"Übergabe am {de_date(today())} · {esc_xml(s.get('inhaber', ''))}, {esc_xml(s.get('firma', ''))}", N)]
    if p.get("descr"):
        el += [Spacer(1, 8), Paragraph(esc_xml(p["descr"]).replace("\n", "<br/>"), N)]
    if notes:
        el += [Spacer(1, 8), Paragraph("<b>Hinweise zur Übergabe</b>", N), Paragraph(esc_xml(notes).replace("\n", "<br/>"), N)]
    el.append(PageBreak())
    el.append(Paragraph("Inhalt", ss["Heading1"]))
    rows = [["Nr.", "Ordner", "Datei", "Art", "Seite"]]
    embedded, other = [], []
    for f in files:
        fp = os.path.join(DATA_DIR, f["path"])
        ext = os.path.splitext(f["name"] or "")[1].lower()
        if os.path.exists(fp) and ext in (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"):
            embedded.append(f)
        else:
            other.append(f)
    for i, f in enumerate(embedded, 1):
        rows.append([str(i), (f["folder"] or "")[:34], (f["name"] or "")[:44], f["kind"] or "", "Anhang"])
    t = Table(rows, colWidths=[10 * mm, 48 * mm, 70 * mm, 30 * mm, 14 * mm], repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), FONT_B(), 8.5), ("FONT", (0, 1), (-1, -1), FONT_R(), 8.5),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f4fa")])]))
    el.append(t)
    if other:
        el += [Spacer(1, 10), Paragraph("Weitere Projektdateien (nicht eingebettet, im Projektordner enthalten)", ss["Heading3"])]
        rows = [["Ordner", "Datei", "Art"]] + [[(f["folder"] or "")[:40], (f["name"] or "")[:60], f["kind"] or ""] for f in other]
        t2 = Table(rows, colWidths=[55 * mm, 85 * mm, 32 * mm], repeatRows=1)
        t2.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), FONT_B(), 8.5), ("FONT", (0, 1), (-1, -1), FONT_R(), 8.5),
                                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black)]))
        el.append(t2)

    def onpage(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(GRAY)
        cv.drawString(20 * mm, 10 * mm, f"Projektdokumentation {p['nr']} · {p['name']}")
        cv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Seite {dc.page}")
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    data = buf.getvalue()
    if pypdf:
        from PIL import Image
        w = pypdf.PdfWriter()
        for pg in pypdf.PdfReader(io.BytesIO(data)).pages:
            w.add_page(pg)
        for f in embedded:
            fp = os.path.join(DATA_DIR, f["path"])
            try:
                if fp.lower().endswith(".pdf"):
                    for pg in pypdf.PdfReader(fp).pages:
                        w.add_page(pg)
                else:
                    im = Image.open(fp).convert("RGB")
                    b = io.BytesIO()
                    cv = rl_canvas.Canvas(b, pagesize=A4)
                    W, Hh = A4
                    iw, ih = im.size
                    sc = min((W - 60) / iw, (Hh - 110) / ih)
                    cv.setFont(FONT_B(), 10)
                    cv.drawString(30, Hh - 34, f["name"] or "")
                    cv.setFont(FONT_R(), 8)
                    cv.drawString(30, Hh - 46, f"{f['folder'] or ''} · {f['kind'] or ''}")
                    cv.drawImage(ImageReader(im), (W - iw * sc) / 2, (Hh - 60 - ih * sc) / 2, iw * sc, ih * sc)
                    cv.showPage()
                    cv.save()
                    for pg in pypdf.PdfReader(io.BytesIO(b.getvalue())).pages:
                        w.add_page(pg)
            except Exception:
                traceback.print_exc()
        o = io.BytesIO()
        w.write(o)
        data = o.getvalue()
    base = ensure_project_folders(q("SELECT * FROM projects WHERE id=?", (pid,), one=True))
    fp = os.path.join(base, safe_name(f"Uebergabe_{p['nr']}_{today()}.pdf"))
    write_file(fp, data)
    rel = os.path.relpath(fp, DATA_DIR)
    if not q("SELECT id FROM project_files WHERE path=?", (rel,), one=True):
        x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
          (pid, "", "Dokument", os.path.basename(fp), rel, len(data), "Übergabe-Dokumentation", now_iso()))
    return fp

# ---------------- Timer ----------------


def timer_stop(d):
    s = get_settings()
    t = s.get("timer")
    if not t:
        raise ValueError("Es läuft kein Timer.")
    start = datetime.datetime.fromisoformat(t["start"])
    hours = (datetime.datetime.now() - start).total_seconds() / 3600
    hours = max(0.25, math.ceil(hours * 4 - 1e-9) / 4)
    a = q("SELECT * FROM articles WHERE id=?", (d.get("article_id"),), one=True) if d.get("article_id") else None
    x("INSERT INTO project_entries (project_id, datum, art, nr, name, descr, qty, unit, price, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
      (t["project_id"], start.date().isoformat(), "Arbeitszeit", a["nr"] if a else "", (a["name"] if a else "Arbeitszeit"),
       (d.get("descr") or "") + f" ({start.strftime('%H:%M')}–{datetime.datetime.now().strftime('%H:%M')})",
       hours, "Std", float(a["price"]) if a else float(s.get("stundensatz") or 0), now_iso()))
    set_setting("timer", None)
    return {"ok": True, "stunden": hours, "project_id": t["project_id"]}

# ---------------- Search ----------------


def global_search(term):
    t = f"%{term.strip()}%"
    if len(term.strip()) < 2:
        return {}
    return {
        "Kunden": q("SELECT id, kdnr, COALESCE(NULLIF(firma,''), name) title, ort sub FROM customers WHERE kdnr LIKE ? OR firma LIKE ? OR name LIKE ? OR ort LIKE ? OR mail LIKE ? LIMIT 8", (t,) * 5),
        "Rechnungen & Angebote": q("SELECT id, nr title, typ, datum, summe, addr FROM invoices WHERE nr LIKE ? OR titel LIKE ? OR addr LIKE ? ORDER BY datum DESC LIMIT 10", (t,) * 3),
        "Projekte": q("SELECT id, nr, name title, bereich sub FROM projects WHERE nr LIKE ? OR name LIKE ? OR descr LIKE ? LIMIT 8", (t,) * 3),
        "Projektdateien": q("SELECT f.id, f.project_id, f.name title, f.folder sub, f.path FROM project_files f WHERE f.name LIKE ? OR f.note LIKE ? LIMIT 10", (t,) * 2),
        "Belege": q("SELECT id, partner title, nr, datum, betrag, typ FROM belege WHERE partner LIKE ? OR nr LIKE ? OR notiz LIKE ? ORDER BY datum DESC LIMIT 8", (t,) * 3),
        "Bausteine": q("SELECT id, nr, name title, price FROM articles WHERE nr LIKE ? OR name LIKE ? OR descr LIKE ? LIMIT 8", (t,) * 3),
        "Schüler": q("SELECT id, name title FROM students WHERE name LIKE ? LIMIT 8", (t,)),
        "Kurse": q("SELECT id, name title, rhythmus sub FROM kurse WHERE name LIKE ? OR notiz LIKE ? LIMIT 8", (t,) * 2),
        "Nachweise": q("SELECT id, bezeichnung title, person sub, gueltig_bis FROM zertifikate WHERE bezeichnung LIKE ? OR person LIKE ? OR nummer LIKE ? LIMIT 8", (t,) * 3),
    }

# ---------------- Update ----------------


def install_update(tmp_path):
    if not getattr(sys, "frozen", False) or not sys.platform.startswith("win"):
        raise ValueError("Update-Installation geht nur in der EXE unter Windows.")
    cur = sys.executable
    upd_dir = os.path.join(DATA_DIR, "_update")
    os.makedirs(upd_dir, exist_ok=True)
    new = os.path.join(upd_dir, "neu.exe")
    shutil.move(tmp_path, new)
    bat = os.path.join(upd_dir, "update.bat")
    open(bat, "w", encoding="utf-8").write(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "set N=0\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        ":loop\r\n"
        f'copy /y "{new}" "{cur}" >nul 2>&1 && goto ok\r\n'
        "set /a N+=1\r\n"
        "if %N% GEQ 40 goto fail\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        "goto loop\r\n"
        ":ok\r\n"
        f'start "" "{cur}"\r\n'
        "exit /b 0\r\n"
        ":fail\r\n"
        f'echo Update fehlgeschlagen > "{os.path.join(upd_dir, "update_fehler.txt")}"\r\n'
        f'start "" "{cur}"\r\n')
    flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    env = {k: v for k, v in os.environ.items() if not (k.startswith("_MEI") or k.startswith("_PYI") or k.startswith("PA_RECHNUNG_RES")
                                                      or k in ("PA_RECHNUNG_CORE_SOURCE", "PA_RECHNUNG_BUILTIN_VER", "PA_RECHNUNG_LAUNCHER"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=True, env=env)
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return {"ok": True}
