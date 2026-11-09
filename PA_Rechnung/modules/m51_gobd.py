# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m51_gobd
# GoBD: Aenderungsprotokoll (audit_log, nur anfuegbar, Hash-Kette) + Verfahrensdokumentation (PDF).
# Protokolliert ueber Ummanteln von x() (SQL-Musterfilter) und save_invoice().
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M51_VERSION = "1.0.0"
M51_TABLES = {"invoices": "Rechnung", "items": "Position", "belege": "Beleg", "customers": "Kunde", "bank_tx": "Bank"}
M51_SKIP = {"updated", "created"}
M51_MAXROWS = 500
_M51_READY = [False]
_m51_tl = threading.local()
_M51_RX = re.compile(r"^\s*(INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+([A-Za-z_]\w*)", re.I)
_M51_WHERE = re.compile(r"\bWHERE\b", re.I)
_m51_orig_x = chain_inner("x", "m51_gobd")   # v3.1.0: the level below this module
def m51_schema():
    _m51_orig_x("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, zeit TEXT, bereich TEXT, datensatz_id INTEGER, "
                "aktion TEXT, feld TEXT, alt TEXT, neu TEXT, info TEXT, quelle TEXT, hash TEXT)")
    _m51_orig_x("CREATE INDEX IF NOT EXISTS ix_audit_ber ON audit_log(bereich, datensatz_id)")
    _m51_orig_x("CREATE INDEX IF NOT EXISTS ix_audit_zeit ON audit_log(zeit)")
    _m51_orig_x("CREATE TRIGGER IF NOT EXISTS audit_log_no_upd BEFORE UPDATE ON audit_log "
                "BEGIN SELECT RAISE(ABORT, 'Das Aenderungsprotokoll ist nur anfuegbar.'); END")
    _m51_orig_x("CREATE TRIGGER IF NOT EXISTS audit_log_no_del BEFORE DELETE ON audit_log "
                "BEGIN SELECT RAISE(ABORT, 'Das Aenderungsprotokoll ist nur anfuegbar.'); END")
    _M51_READY[0] = True
    if not q("SELECT id FROM audit_log LIMIT 1", one=True):
        n = q("SELECT (SELECT COUNT(*) FROM invoices) i, (SELECT COUNT(*) FROM belege) b, (SELECT COUNT(*) FROM customers) c", one=True)
        m51_log("System", None, "Protokoll gestartet", "", "", "",
                f"Bestand bei Start: {n['i']} Dokumente, {n['b']} Belege, {n['c']} Kunden")


HOOK_SCHEMA.append(m51_schema)

# ---------------------------------------------------------------------------
# Writing (append only, hash chain)
# ---------------------------------------------------------------------------


def _m51_s(v, n=1000):
    if v is None:
        return ""
    if isinstance(v, float):
        v = f"{v:.2f}" if abs(v - round(v, 2)) < 1e-9 else repr(v)
    v = str(v)
    return v if len(v) <= n else v[:n] + " …"


def _m51_hash(prev, row):
    return hashlib.sha256(("|".join([prev or ""] + [_m51_s(v, 100000) for v in row])).encode("utf-8")).hexdigest()


def m51_log(bereich, rid, aktion, feld="", alt="", neu="", info="", quelle=None):
    if not _M51_READY[0]:
        return
    try:
        with DB_LOCK:
            last = q("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1", one=True)
            row = [now_iso(), bereich, rid if rid is None else int(rid), aktion, _m51_s(feld, 100), _m51_s(alt), _m51_s(neu),
                   _m51_s(info, 300), quelle or getattr(_m51_tl, "quelle", "") or ""]
            h = _m51_hash(last["hash"] if last else "", row)
            sql_ = ("INSERT INTO audit_log (zeit, bereich, datensatz_id, aktion, feld, alt, neu, info, quelle, hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)")
            if getattr(_m51_tl, "batch", False):
                CON.execute(sql_, tuple(row) + (h,))   # v2.0.6: committed together with the data change
            else:
                _m51_orig_x(sql_, tuple(row) + (h,))
    except Exception:
        traceback.print_exc()


def _m51_info(tbl, r):
    if not r:
        return ""
    try:
        if tbl == "invoices":
            return f"{DOC_TYPES.get(r.get('typ') or 'rechnung', {}).get('title', 'Dokument')} {r.get('nr') or ''}".strip()
        if tbl == "items":
            inv = q("SELECT nr FROM invoices WHERE id=?", (r.get("invoice_id"),), one=True)
            return f"Pos. {r.get('pos')} zu {inv['nr'] if inv else '?'}: {(r.get('name') or '')[:40]}"
        if tbl == "belege":
            return f"{r.get('typ') or ''} {de_date(r.get('datum'))} {(r.get('partner') or '')[:40]} {money(float(r.get('betrag') or 0))}"
        if tbl == "customers":
            return f"{r.get('kdnr') or ''} {r.get('firma') or r.get('name') or ''}".strip()
        if tbl == "bank_tx":
            return f"{de_date(r.get('datum'))} {money(float(r.get('betrag') or 0))} {(r.get('name') or '')[:40]}"
    except Exception:
        pass
    return ""


def _m51_summary(tbl, r):
    keys = {"invoices": ("nr", "typ", "datum", "summe", "status"), "items": ("invoice_id", "pos", "qty", "name", "price", "total"),
            "belege": ("typ", "datum", "partner", "nr", "betrag", "kategorie", "invoice_id"),
            "customers": ("kdnr", "firma", "name", "ort"), "bank_tx": ("datum", "betrag", "name", "invoice_id", "beleg_id", "status")}.get(tbl, ())
    return "; ".join(f"{k}={_m51_s(r.get(k), 80)}" for k in keys if r.get(k) not in (None, ""))

# ---------------------------------------------------------------------------
# Wrapper around x(): light SQL pattern filter
# ---------------------------------------------------------------------------


def _m51_sup():
    return getattr(_m51_tl, "sup", frozenset())


@chain_step("x", "m51_gobd")
def _m51_step_x(_next, sql, args=()):
    if not _M51_READY[0]:
        return _next(sql, args)
    m = _M51_RX.match(sql)
    if not m:
        return _next(sql, args)
    tbl = m.group(2).lower()
    if tbl not in M51_TABLES or tbl in _m51_sup():
        return _next(sql, args)
    verb = m.group(1)[:6].upper()
    with DB_LOCK:
        before = None
        if verb in ("UPDATE", "DELETE") and not isinstance(args, dict):
            try:
                wm = _M51_WHERE.search(sql)
                a = list(args or ())
                if wm:
                    nset = sql[:wm.start()].count("?")
                    before = q(f"SELECT * FROM {tbl} WHERE {sql[wm.end():]} LIMIT {M51_MAXROWS + 1}", a[nset:])
                else:
                    before = q(f"SELECT * FROM {tbl} LIMIT {M51_MAXROWS + 1}")
            except Exception:
                before = None
                m51_log(M51_TABLES[tbl], None, "Änderung (nicht auswertbar)" if verb == "UPDATE" else "Löschung (nicht auswertbar)",
                        "", "", "", _m51_s(sql, 200))
        # v2.0.6: data change + its log entries in ONE transaction / one commit (was 1 + n commits)
        try:
            cur = CON.execute(sql, args)
            rid = cur.lastrowid
        except Exception:
            try:
                CON.rollback()
            except Exception:
                pass
            raise
        _m51_tl.batch = True
        try:
            _m51_after(tbl, verb, before, rid)
        except Exception:
            traceback.print_exc()
        finally:
            _m51_tl.batch = False
            CON.commit()
        return rid


def _m51_after(tbl, verb, before, rid):
    lbl = M51_TABLES[tbl]
    if verb == "INSERT":
        r = q(f"SELECT * FROM {tbl} WHERE rowid=?", (rid,), one=True) if rid else None
        if r:
            m51_log(lbl, r.get("id"), "angelegt", "", "", _m51_summary(tbl, r), _m51_info(tbl, r))
        return
    if not before:
        return
    if len(before) > M51_MAXROWS:
        m51_log(lbl, None, "Massenänderung" if verb == "UPDATE" else "Massenlöschung", "", f"> {M51_MAXROWS} Datensätze", "", "")
        return
    if verb == "DELETE":
        for r in before:
            m51_log(lbl, r.get("id"), "gelöscht", "", _m51_summary(tbl, r), "", _m51_info(tbl, r))
        return
    ids = [r["id"] for r in before if r.get("id") is not None]
    if not ids:
        return
    now = {r["id"]: r for r in q(f"SELECT * FROM {tbl} WHERE id IN ({','.join('?' * len(ids))})", ids)}
    for o in before:
        n = now.get(o.get("id"))
        if not n:
            continue
        for k, v in n.items():
            if k in M51_SKIP:
                continue
            ov = o.get(k)
            if ov == v or (ov in (None, "") and v in (None, "")):
                continue
            try:
                if ov is not None and v is not None and abs(float(ov) - float(v)) < 1e-9:
                    continue
            except Exception:
                pass
            m51_log(lbl, n["id"], "geändert", k, ov, v, _m51_info(tbl, n))

# ---------------------------------------------------------------------------
# Wrapper around save_invoice(): one compact entry instead of item noise
# ---------------------------------------------------------------------------
def _m51_inv_snap(iid):
    r = q("SELECT * FROM invoices WHERE id=?", (iid,), one=True)
    if not r:
        return None
    its = q("SELECT pos, qty, nr, name, descr, price, rabatt, total FROM items WHERE invoice_id=? ORDER BY pos", (iid,))
    r["_items"] = its
    return r


def _m51_items_txt(its):
    if not its:
        return "keine Positionen"
    parts = [f"{num_de(float(i['qty'] or 0), 2)} x {(i['name'] or '')[:40]} à {num_de(float(i['price'] or 0), 2)}"
             + (f" -{num_de(float(i['rabatt']), 1)}%" if i.get("rabatt") else "") + f" = {num_de(float(i['total'] or 0), 2)}" for i in its]
    return f"{len(its)} Pos.: " + " | ".join(parts)


@chain_step("save_invoice", "m51_gobd")
def _m51_step_save_invoice(_next, d, bump=True):
    if not _M51_READY[0]:
        return _next(d, bump)
    iid0 = d.get("id")
    old = _m51_inv_snap(iid0) if iid0 else None
    prev = _m51_sup()
    _m51_tl.sup = prev | {"invoices", "items"}
    try:
        res = _next(d, bump)
    finally:
        _m51_tl.sup = prev
    try:
        iid = res[0]
        new = _m51_inv_snap(iid)
        info = _m51_info("invoices", new)
        if not old:
            m51_log("Rechnung", iid, "angelegt", "", "", _m51_summary("invoices", new) + " · " + _m51_items_txt(new["_items"]), info)
        else:
            for k, v in new.items():
                if k in M51_SKIP or k == "_items":
                    continue
                ov = old.get(k)
                if ov == v or (ov in (None, "") and v in (None, "")):
                    continue
                try:
                    if ov is not None and v is not None and abs(float(ov) - float(v)) < 1e-9:
                        continue
                except Exception:
                    pass
                m51_log("Rechnung", iid, "geändert", k, ov, v, info)
            key = lambda its: [(round(float(i["qty"] or 0), 4), i["nr"] or "", i["name"] or "", i["descr"] or "",
                                round(float(i["price"] or 0), 4), round(float(i["rabatt"] or 0), 4)) for i in its]
            if key(old["_items"]) != key(new["_items"]):
                m51_log("Rechnung", iid, "geändert", "Positionen", _m51_items_txt(old["_items"]), _m51_items_txt(new["_items"]), info)
    except Exception:
        traceback.print_exc()
    return res

# ---------------------------------------------------------------------------
# Reading / verify / export
# ---------------------------------------------------------------------------


def m51_query(p):
    where, args = [], []
    if p.get("bereich"):
        where.append("bereich=?")
        args.append(p["bereich"])
    if p.get("aktion"):
        where.append("aktion=?")
        args.append(p["aktion"])
    if p.get("von"):
        where.append("zeit>=?")
        args.append(p["von"])
    if p.get("bis"):
        where.append("zeit<=?")
        args.append(p["bis"] + " 23:59:59")
    if p.get("rid"):
        where.append("datensatz_id=?")
        args.append(int(p["rid"]))
    if (p.get("q") or "").strip():
        t = "%" + p["q"].strip() + "%"
        where.append("(info LIKE ? OR feld LIKE ? OR alt LIKE ? OR neu LIKE ?)")
        args += [t, t, t, t]
    w = (" WHERE " + " AND ".join(where)) if where else ""
    total = q("SELECT COUNT(*) n FROM audit_log" + w, args, one=True)["n"]
    lim = min(int(p.get("limit") or 300), 20000)
    off = int(p.get("offset") or 0)
    rows = q(f"SELECT id, zeit, bereich, datensatz_id, aktion, feld, alt, neu, info, quelle FROM audit_log{w} ORDER BY id DESC LIMIT ? OFFSET ?",
             args + [lim, off])
    return {"total": total, "rows": rows}


def m51_verify():
    prev = ""
    n = 0
    for r in q("SELECT * FROM audit_log ORDER BY id"):
        row = [r["zeit"], r["bereich"], r["datensatz_id"], r["aktion"], r["feld"], r["alt"], r["neu"], r["info"], r["quelle"]]
        if _m51_hash(prev, row) != r["hash"]:
            return {"ok": False, "n": n, "fehler_id": r["id"], "text": f"Hash-Kette bei Eintrag {r['id']} unterbrochen - Protokoll wurde außerhalb des Programms verändert."}
        prev = r["hash"]
        n += 1
    return {"ok": True, "n": n, "text": f"{n} Einträge geprüft - Hash-Kette vollständig."}


def ex_gobd_log(p):
    # v2.0.6: export ALL entries (was cut off after 20,000)
    rows, off = [], 0
    while True:
        part = m51_query(dict(p, limit=20000, offset=off))
        rows += part["rows"]
        off += 20000
        if off >= part["total"] or not part["rows"]:
            break
    data = [[r["zeit"], r["bereich"], r["datensatz_id"] or "", r["aktion"], r["feld"] or "", r["alt"] or "", r["neu"] or "", r["info"] or ""] for r in rows]
    return [_sh("Änderungsprotokoll (GoBD)", [("Zeit", "t", 18), ("Bereich", "t", 10), ("ID", "n", 6), ("Aktion", "t", 11), ("Feld", "t", 12),
                                              ("Alt", "t", 32), ("Neu", "t", 32), ("Kurzinfo", "t", 30)], data,
                f"{len(data)} Einträge", False)]


EXPORTS["gobd_log"] = ("GoBD_Protokoll", ex_gobd_log)


def m51_route_log(h, qs):
    r = m51_query(qs)
    r["bereiche"] = [x_["bereich"] for x_ in q("SELECT DISTINCT bereich FROM audit_log ORDER BY bereich")]
    return h._send(200, r)


def m51_route_verify(h, qs):
    return h._send(200, m51_verify())


def m51_route_doku(h, d):
    out = os.path.join(DATA_DIR, "Export", f"Verfahrensdokumentation_{today()}.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_file(out, verfahrensdoku_pdf(d.get("notiz") or ""))
    m51_log("System", None, "Verfahrensdokumentation erzeugt", "", "", os.path.basename(out), "")
    if d.get("open", True) and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(out)
    return h._send(200, {"ok": True, "path": out})


HOOK_GET["/api/m51/log"] = m51_route_log
HOOK_GET["/api/m51/verify"] = m51_route_verify
HOOK_POST["/api/m51/verfahrensdoku"] = m51_route_doku

# ---------------------------------------------------------------------------
# Verfahrensdokumentation (PDF)
# ---------------------------------------------------------------------------


def verfahrensdoku_pdf(notiz=""):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    s = get_settings()
    try:
        sd = m50_seller(s)
    except Exception:
        sd = {"name": s.get("firma", ""), "inhaber": s.get("inhaber", ""), "strasse": "", "plz": "", "ort": "", "steuernr": "", "ustid": ""}
    ACC = colors.HexColor("#5b3fd6")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                            title="Verfahrensdokumentation", author="T. Pfeiffer", subject="Verfahrensdokumentation nach GoBD",
                            creator=f"{APP_NAME} v{APP_VERSION}")
    ss = font_stylesheet()
    H1 = ParagraphStyle("vh1", parent=ss["Heading1"], fontName=FONT_B(), fontSize=20, leading=24, spaceAfter=4)
    H2 = ParagraphStyle("vh2", parent=ss["Heading2"], fontName=FONT_B(), fontSize=12.5, spaceBefore=12, spaceAfter=5, textColor=ACC)
    N = ParagraphStyle("vn", parent=ss["Normal"], fontName=FONT_R(), fontSize=9.4, leading=13, spaceAfter=4)
    B = ParagraphStyle("vb", parent=N, leftIndent=12, bulletIndent=2, spaceAfter=2)
    SM = ParagraphStyle("vs", parent=N, fontSize=7.8, leading=10, textColor=colors.HexColor("#666666"))
    E = esc_xml

    def bl(items):
        return [Paragraph(E(t) if not t.startswith("<") else t, B, bulletText="•") for t in items]

    def kv(rows):
        t = Table([[Paragraph("<b>" + E(a) + "</b>", N), Paragraph(E(b), N)] for a, b in rows], colWidths=[52 * mm, 118 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    n_log = q("SELECT COUNT(*) n, MIN(zeit) a FROM audit_log", one=True) if _M51_READY[0] else {"n": 0, "a": ""}
    adr = ", ".join(v for v in (sd.get("strasse"), " ".join(v for v in (sd.get("plz"), sd.get("ort")) if v)) if v)
    bereiche = sorted({p["bereich"] for p in q("SELECT DISTINCT bereich FROM projects WHERE bereich IS NOT NULL AND bereich!=''")})
    tgt = (s.get("backup_target") or "").strip()
    el = []
    el.append(Paragraph("Verfahrensdokumentation", H1))
    el.append(Paragraph("zur ordnungsmäßigen Führung und Aufbewahrung von Büchern, Aufzeichnungen und Unterlagen in elektronischer Form (GoBD)", N))
    el.append(Paragraph(f"Stand: {de_date(today())} · Autor: T. Pfeiffer · erstellt mit {E(APP_NAME)} v{APP_VERSION}", SM))
    el.append(Spacer(1, 6))
    hint = Table([[Paragraph("<b>Hinweis:</b> Dieses Dokument ist eine automatisch erzeugte <b>Vorlage</b>. Es beschreibt die vom Programm "
                             "unterstützten Abläufe und ist <b>vom Unternehmer zu prüfen</b>, an die tatsächliche Arbeitsweise anzupassen, "
                             "zu unterschreiben und bei Änderungen fortzuschreiben. Es ersetzt keine steuerliche Beratung.", N)]],
                 colWidths=[170 * mm])
    hint.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#efeafe")), ("BOX", (0, 0), (-1, -1), 0.6, ACC),
                              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el.append(hint)

    el.append(Paragraph("1. Allgemeine Beschreibung", H2))
    el.append(kv([("Unternehmen", sd.get("name") or s.get("firma", "")), ("Inhaber", sd.get("inhaber") or s.get("inhaber", "")),
                  ("Anschrift", adr or s.get("absender", "")), ("Steuernummer", sd.get("steuernr") or "–"),
                  ("USt-IdNr.", sd.get("ustid") or "–"), ("Rechtsform", "Einzelunternehmen"),
                  ("Tätigkeitsbereiche", ", ".join(bereiche) or "laut Gewerbeanmeldung / Fragebogen zur steuerlichen Erfassung"),
                  ("Umsatzsteuer", "Kleinunternehmer nach § 19 UStG – kein Ausweis von Umsatzsteuer" if s.get("kleinunternehmer", True) else "Regelbesteuerung"),
                  ("Gewinnermittlung", "Einnahmen-Überschuss-Rechnung (§ 4 Abs. 3 EStG), Zufluss-/Abflussprinzip"),
                  ("Weitere Einkünfte", "Nichtselbstständige Tätigkeit (Gehalt) – getrennt erfasst"),
                  ("Eingesetzte Software", f"{APP_NAME} v{APP_VERSION} (eigenentwickelt, Windows-Programm, Python + HTML-Oberfläche), "
                                           f"{len(MODULES_LOADED)} Programmmodule"),
                  ("Datenhaltung", f"SQLite-Datenbank und Belegdateien im Datenordner: {DATA_DIR}"),
                  ("Verantwortlich", "Der Inhaber führt sämtliche Buchhaltungs- und Verwaltungstätigkeiten selbst aus.")]))

    el.append(Paragraph("2. Belegfluss (Eingang → Erkennung → Prüfung → Buchung)", H2))
    el.append(Paragraph("<b>Eingangsbelege</b> (Rechnungen von Lieferanten, Quittungen, Gehaltsabrechnungen, Gutschriften):", N))
    el += bl(["<b>Eingang:</b> Belege gelangen als Datei (PDF, Bild, Office, E-Rechnung XML/ZUGFeRD) per Drag &amp; Drop, Dateiauswahl oder "
              "über den überwachten Eingangsordner" + (f" ({E(s.get('eingang_dir'))})" if s.get("eingang_dir") else "") + " in das Programm. "
              "Papierbelege werden eingescannt bzw. fotografiert.",
              "<b>Erkennung:</b> Das Programm liest den Text aus (bei Bildern Windows-Texterkennung), erkennt E-Rechnungen maschinell aus den "
              "XML-Daten und schlägt Art, Datum, Partner, Betrag und EÜR-Kategorie vor (Regeln und lernender Assistent"
              + (", optional lokale KI ohne Datenübertragung ins Internet" if s.get("ki_enabled") else "") + ").",
              "<b>Prüfung:</b> Jeder Vorschlag wird vom Inhaber kontrolliert und bei Bedarf korrigiert. Unsichere Belege "
              f"(Sicherheit unter {int(float(s.get('auto_schwelle') or 0.9) * 100)} %) landen in einer Prüfliste und werden erst nach "
              "Bestätigung gebucht. Plausibilitätsprüfungen (Datum, Betrag, Dubletten, Kontoauszug statt Beleg) weisen auf Fehler hin.",
              "<b>Buchung und Ablage:</b> Der Beleg wird mit Datum, Partner, Betrag und Kategorie in der Datenbank gespeichert; die "
              "Originaldatei wird unverändert unter „Belege/&lt;Art&gt;/&lt;Jahr&gt;“ abgelegt und mit der Buchung verknüpft. "
              "Bei E-Rechnungen ist die XML-Datei das Original; zusätzlich wird eine Sichtansicht (PDF) erzeugt.",
              "<b>Zahlungen:</b> Kontoauszüge (CSV/PDF/Excel) werden im Bank-Abgleich eingelesen; Umsätze werden Rechnungen bzw. "
              "Belegen zugeordnet. Die Zuordnung wird protokolliert."])
    el.append(Paragraph("<b>Ausgangsrechnungen</b> werden ausschließlich im Programm erstellt (Rechnungseditor), als PDF ausgegeben und "
                        "auf Wunsch per E-Mail versendet. Optional wird eine E-Rechnung (XRechnung/ZUGFeRD) erzeugt. "
                        "Der Zahlungseingang wird manuell oder über den Bank-Abgleich erfasst.", N))

    el.append(Paragraph("3. Rechnungsnummernkreis", H2))
    el += bl([f"Rechnungen und Storno-Rechnungen: ein gemeinsamer, fortlaufender Nummernkreis (nächste Nummer derzeit {E(s.get('next_nr', ''))}).",
              f"Angebote ({E(s.get('next_angnr', ''))}) und Auftragsbestätigungen ({E(s.get('next_abnr', ''))}) haben eigene Nummernkreise.",
              "Jede Nummer ist in der Datenbank eindeutig (technische Sperre gegen doppelte Vergabe).",
              "Entwürfe erhalten nur eine vorläufige Kennung (E-…) und bekommen die endgültige Nummer erst beim Fertigstellen – "
              "dadurch entstehen keine Lücken durch verworfene Entwürfe.",
              "Fehlerhafte Rechnungen werden nicht gelöscht, sondern durch eine Storno-Rechnung mit eigener Nummer aufgehoben."])

    el.append(Paragraph("4. Festschreibung", H2))
    el.append(Paragraph("Eine Rechnung wird automatisch festgeschrieben, sobald sie als PDF ausgegeben, per E-Mail versendet, als E-Rechnung "
                        "exportiert oder als bezahlt markiert wird. Festgeschriebene Rechnungen können im Programm weder geändert noch "
                        "gelöscht werden; Korrekturen erfolgen ausschließlich über Stornierung und Neuausstellung. "
                        "Der Zustand ist in der Rechnungsliste mit einem Schloss gekennzeichnet.", N))

    el.append(Paragraph("5. Datensicherung", H2))
    el += bl(["Automatische tägliche Sicherung der Datenbank beim Programmbetrieb (Datei „backup_auto_JJJJMMTT.zip“ im Ordner Backup), "
              "es werden die letzten 30 Sicherungen aufbewahrt.",
              "Manuelle Vollsicherung inkl. aller Belegdateien über Einstellungen → Daten, Backup &amp; Update.",
              "Externes Sicherungsziel: " + (E(tgt) + " (Kopie jeder Sicherung, 30 Generationen)" if tgt else
                                             "<b>derzeit nicht eingerichtet</b> – Empfehlung: externes Laufwerk oder NAS eintragen."),
              "Empfehlung: mindestens monatlich eine Vollsicherung auf einem getrennt gelagerten Datenträger; Rücksicherung jährlich testen."])

    el.append(Paragraph("6. Aufbewahrung", H2))
    el.append(kv([("10 Jahre", "Bücher und Aufzeichnungen, Jahresabschlüsse/EÜR, Inventare sowie die zum Verständnis erforderlichen "
                               "Arbeitsanweisungen und Organisationsunterlagen (u. a. diese Verfahrensdokumentation)"),
                  ("8 Jahre", "Buchungsbelege, insbesondere Eingangs- und Ausgangsrechnungen, Kontoauszüge (Frist seit 01.01.2025 "
                              "nach dem Bürokratieentlastungsgesetz IV)"),
                  ("6 Jahre", "Empfangene und abgesandte Handels- und Geschäftsbriefe (z. B. Angebote, Auftragsbestätigungen, Korrespondenz)"),
                  ("Fristbeginn", "Ende des Kalenderjahres, in dem die Unterlage entstanden bzw. die letzte Eintragung gemacht wurde"),
                  ("Form", "Elektronisch eingegangene Unterlagen (z. B. E-Rechnungen) werden im Originalformat elektronisch aufbewahrt "
                           "und bleiben während der Frist maschinell auswertbar.")]))
    el.append(Paragraph("Fristen nach § 147 AO / § 14b UStG, Stand 2025 – bitte bei Gesetzesänderungen prüfen. Daten werden im Programm "
                        "nicht automatisch gelöscht.", SM))

    el.append(Paragraph("7. Zugriffsschutz", H2))
    el += bl(["Das Programm läuft auf dem Windows-Rechner des Inhabers; der Zugang ist durch das passwortgeschützte Windows-Benutzerkonto gesichert.",
              "Die Programmoberfläche ist nur lokal auf diesem Rechner erreichbar (127.0.0.1); Anfragen fremder Webseiten werden abgewiesen.",
              "Gespeicherte Zugangsdaten (z. B. E-Mail-Passwort) werden mit der Windows-Datenschutz-API verschlüsselt abgelegt.",
              "Nur der Inhaber hat Zugriff auf den Datenordner; Sicherungen sind entsprechend aufzubewahren."])

    el.append(Paragraph("8. Änderungsprotokoll", H2))
    el.append(Paragraph("Alle Neuanlagen, Änderungen und Löschungen von Rechnungen (inkl. Positionen und Status), Belegen, Kunden und "
                        "Bank-Zuordnungen werden automatisch mit Zeitpunkt, Bereich, Datensatz, Feld sowie altem und neuem Wert in der "
                        "Tabelle „audit_log“ protokolliert. Das Protokoll ist nur anfügbar: Änderungen und Löschungen sind technisch "
                        "gesperrt; jeder Eintrag ist zusätzlich über eine Hash-Kette (SHA-256) mit dem vorherigen verknüpft, sodass "
                        "nachträgliche Manipulationen außerhalb des Programms erkennbar sind. Einsicht, Prüfung und Export (Excel/PDF) "
                        "über Einstellungen → Protokoll (GoBD).", N))
    el.append(Paragraph(f"Derzeit {n_log['n']} Protokolleinträge" + (f", geführt seit {de_date((n_log['a'] or '')[:10])}." if n_log.get("a") else "."), SM))

    el.append(Paragraph("9. Internes Kontrollsystem (IKS)", H2))
    el += bl(["Plausibilitätsprüfungen beim Belegimport (Datum, Betrag, doppelte Belege, Zuordnung zum richtigen Jahr).",
              "Dublettensuche für Rechnungen und Belege.",
              "Abgleich der Bankumsätze mit offenen Rechnungen und Belegen; offene Posten und Mahnwesen mit Fristenüberwachung.",
              "Überwachung der Kleinunternehmergrenzen mit Hochrechnung und Warnung vor dem Überschreiten.",
              "Festschreibung von Rechnungen und lückenlose Nummernvergabe (siehe 3. und 4.).",
              "Jahresabschluss: Abgleich der Programmwerte mit Steuererklärung und Steuerbescheid.",
              "Da der Inhaber allein arbeitet, ist ein Vier-Augen-Prinzip nicht möglich. Ersatzweise erfolgt eine monatliche "
              "Durchsicht von offenen Posten, Bankabgleich und Änderungsprotokoll."])
    if notiz.strip():
        el.append(Paragraph("10. Ergänzungen des Unternehmers", H2))
        for para in notiz.strip().split("\n"):
            if para.strip():
                el.append(Paragraph(E(para.strip()), N))
    el.append(Spacer(1, 18))
    sig = Table([["", "", ""], ["Ort, Datum", "", "Unterschrift Inhaber"]], colWidths=[70 * mm, 20 * mm, 70 * mm], rowHeights=[22, 12])
    sig.setStyle(TableStyle([("LINEABOVE", (0, 1), (0, 1), 0.6, colors.black), ("LINEABOVE", (2, 1), (2, 1), 0.6, colors.black),
                             ("FONT", (0, 1), (-1, 1), FONT_R(), 8), ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#666666"))]))
    el.append(KeepTogether([Paragraph("Änderungshistorie dieser Dokumentation", H2),
                            kv([(de_date(today()), f"Erstellung aus Vorlage ({APP_NAME} v{APP_VERSION}) – T. Pfeiffer")]), Spacer(1, 18), sig]))

    def onpage(cv, dc):
        cv.saveState()
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(colors.HexColor("#777777"))
        cv.drawString(20 * mm, 10 * mm, f"Verfahrensdokumentation · Stand {de_date(today())} · T. Pfeiffer")
        cv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Seite {dc.page}")
        cv.setStrokeColor(ACC)
        cv.setLineWidth(1.2)
        cv.line(20 * mm, A4[1] - 12 * mm, A4[0] - 18 * mm, A4[1] - 12 * mm)
        cv.restoreState()
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    return buf.getvalue()

# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------


def m51_selftest():
    err = []
    try:
        if not _M51_READY[0]:
            return ["m51: audit_log nicht initialisiert"]
        n0 = q("SELECT COUNT(*) n FROM audit_log", one=True)["n"]
        cid = x("INSERT INTO customers (kdnr, firma, name, created) VALUES (?,?,?,?)", ("ZZTEST51", "Selbsttest", "Test", now_iso()))
        x("UPDATE customers SET ort=? WHERE id=?", ("Teststadt", cid))
        x("DELETE FROM customers WHERE id=?", (cid,))
        rows = q("SELECT aktion, feld FROM audit_log WHERE bereich='Kunde' AND datensatz_id=? ORDER BY id", (cid,))
        akt = [r["aktion"] for r in rows]
        if akt[:1] != ["angelegt"] or "geändert" not in akt or akt[-1:] != ["gelöscht"]:
            err.append(f"m51: Protokoll Kunde unvollständig: {akt}")
        try:
            _m51_orig_x("DELETE FROM audit_log WHERE id=(SELECT MAX(id) FROM audit_log)")
            err.append("m51: audit_log ließ sich löschen (Trigger fehlt)")
        except sqlite3.Error:
            pass
        if not m51_verify()["ok"]:
            err.append("m51: Hash-Kette ungültig")
        if q("SELECT COUNT(*) n FROM audit_log", one=True)["n"] < n0 + 3:
            err.append("m51: zu wenige Protokolleinträge")
        if len(verfahrensdoku_pdf()) < 2000:
            err.append("m51: Verfahrensdokumentation leer")
    except Exception as e:
        err.append(f"m51 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m51_selftest)
