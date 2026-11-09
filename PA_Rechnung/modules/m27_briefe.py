# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m27_briefe (v2.0.6)
# Briefe: neuer Dokument-Reiter "Brief" im Editor. Briefvorlage aus dem Vorlagen-Katalog (Word .docx/.dotx/.docm/.dotm,
# LibreOffice .odt/.ott) oder eigenes Briefpapier (PDF wie Rechnungen). Platzhalter wie {{Anschrift}}, [Betreff], «Datum}
# werden ersetzt - auch wenn Word sie intern zerstueckelt hat; die Formatierung bleibt erhalten. Ohne Platzhalter wird
# der Brief oben in die Vorlage eingefuegt. Die Vorlage selbst bleibt unveraendert - es entsteht immer eine neue Datei.
# v2.0.5: Reiter "Aus Vorlage" - jede Vorlage des Katalogs als neues Dokument. Word/LibreOffice/Excel-Vorlagen werden
# ausgefuellt (Platzhalter), alle anderen Dateien (PDF, Q-SYS, Zeichnungen ...) als Kopie angelegt.
# Autor: T. Pfeiffer

import html as _br_html
import tempfile

BR_FILL_EXT = {".docx", ".dotx", ".docm", ".dotm", ".odt", ".ott"}
BR_OUT_EXT = {".dotx": ".docx", ".dotm": ".docm", ".ott": ".odt", ".xltx": ".xlsx", ".xltm": ".xlsm", ".ots": ".ods"}
BR_WORD_EXT = {".docx", ".dotx", ".docm", ".dotm"}
BR_XL_EXT = {".xlsx", ".xltx", ".xlsm", ".xltm"}
BR_ODF_EXT = {".odt", ".ott", ".ods", ".ots"}
DOC_FILL_EXT = BR_WORD_EXT | BR_XL_EXT | BR_ODF_EXT
BR_KEYS = {
    "anschrift": "anschrift", "adresse": "anschrift", "empfaenger": "anschrift", "empfänger": "anschrift", "adressat": "anschrift",
    "firma": "firma", "name": "name", "kunde": "kunde", "strasse": "strasse", "straße": "strasse", "plz": "plz", "ort": "ort",
    "plz_ort": "plz_ort", "plzort": "plz_ort", "datum": "datum", "betreff": "betreff", "anrede": "anrede",
    "text": "text", "brieftext": "text", "inhalt": "text", "gruss": "gruss", "gruß": "gruss", "grussformel": "gruss",
    "grußformel": "gruss", "kundennummer": "kdnr", "kdnr": "kdnr", "kunden-nr": "kdnr", "absender": "absender",
    "inhaber": "inhaber", "unterschrift": "inhaber", "projekt": "projekt", "meinefirma": "meinefirma",
}
BR_PH_RE = re.compile(r"\{\{\s*([\wäöüÄÖÜß\-]+)\s*\}\}|«\s*([\wäöüÄÖÜß\-]+)\s*»|<<\s*([\wäöüÄÖÜß\-]+)\s*>>|\[\s*([\wäöüÄÖÜß\-]+)\s*\]")
BR_PH_HELP = ["{{Anschrift}}", "{{Datum}}", "{{Betreff}}", "{{Anrede}}", "{{Text}}", "{{Gruss}}", "{{Inhaber}}",
              "{{Name}}", "{{Firma}}", "{{Strasse}}", "{{PLZ}}", "{{Ort}}", "{{Kundennummer}}", "{{Projekt}}"]


def _br_schema():
    x("""CREATE TABLE IF NOT EXISTS briefe (id INTEGER PRIMARY KEY, datum TEXT, customer_id INTEGER, project_id INTEGER, kdnr TEXT,
         anschrift TEXT, betreff TEXT, anrede TEXT, text TEXT, gruss TEXT, vorlage_id INTEGER, vorlage_name TEXT, datei TEXT,
         erstellt TEXT, geaendert TEXT)""")
    try:
        x("ALTER TABLE briefe ADD COLUMN art TEXT DEFAULT 'brief'")
    except Exception:
        pass


def _br_key(m):
    k = next(g for g in m.groups() if g is not None)
    return BR_KEYS.get(k.lower().replace(" ", ""))




def _br_runs_fill(texts, vals):
    """texts: list of run texts of one paragraph; placeholders may span several runs. Replacement goes into the run
    where the placeholder starts, so the formatting of that run is kept. Returns (texts, count, keys)"""
    full = "".join(texts)
    ms = [m for m in BR_PH_RE.finditer(full) if _br_key(m)]
    if not ms:
        return texts, 0, []
    texts = list(texts)
    starts, p = [], 0
    for t in texts:
        starts.append(p)
        p += len(t)

    def run_of(pos):
        for i in range(len(texts) - 1, -1, -1):
            if starts[i] <= pos and (len(texts[i]) or i == 0):
                if pos < starts[i] + len(texts[i]) or i == len(texts) - 1:
                    return i
        return 0
    keys = []
    for m in reversed(ms):
        s, e = m.span()
        k = _br_key(m)
        keys.append(k)
        i, j = run_of(s), run_of(e - 1)
        v = vals.get(k, "")
        if i == j:
            texts[i] = texts[i][:s - starts[i]] + v + texts[i][e - starts[i]:]
        else:
            texts[i] = texts[i][:s - starts[i]] + v
            for kk in range(i + 1, j):
                texts[kk] = ""
            texts[j] = texts[j][e - starts[j]:]
    return texts, len(ms), keys


# ---------- Word (OOXML) ----------
W_P_RE = re.compile(r"<w:p[ >](?:(?!<w:p[ >]).)*?</w:p>", re.S)
W_T_RE = re.compile(r"(<w:t(?:\s[^>]*)?(?<!/)>)(.*?)(</w:t>)", re.S)   # v2.0.6: not <w:t .../>
_BR_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _br_clean(s):
    """v2.0.6: characters that are invalid in XML (Shift+Enter from Word = \\x0b ...) would corrupt the document"""
    return _BR_BAD.sub(lambda m: "\n" if m.group(0) in "\x0b\x0c" else "", str(s or ""))


def _w_text(s):
    s = _br_html.escape(_br_clean(s), quote=False)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", '</w:t><w:br/><w:t xml:space="preserve">').replace("\t", '</w:t><w:tab/><w:t xml:space="preserve">')
    return s


def _w_fill_span(span, vals, found):
    ts = list(W_T_RE.finditer(span))
    if not ts:
        return span, 0
    texts = [_br_html.unescape(t.group(2)) for t in ts]
    new, n, keys = _br_runs_fill(texts, vals)
    if not n:
        return span, 0
    found.extend(keys)
    out, last = [], 0
    for t, nt in zip(ts, new):
        out.append(span[last:t.start()])
        out.append('<w:t xml:space="preserve">' + _w_text(nt) + "</w:t>")
        last = t.end()
    out.append(span[last:])
    return "".join(out), n


def _w_fill(xml, vals, found):
    out, last, cnt = [], 0, 0
    for m in W_P_RE.finditer(xml):
        gap, n1 = _w_fill_gap(xml[last:m.start()], vals, found)
        par, n2 = _w_fill_span(m.group(0), vals, found)
        out += [gap, par]
        cnt += n1 + n2
        last = m.end()
    gap, n1 = _w_fill_gap(xml[last:], vals, found)
    out.append(gap)
    return "".join(out), cnt + n1


def _w_fill_gap(s, vals, found):
    """text outside innermost paragraphs (e.g. outer paragraph around a text box): replace per text node"""
    cnt = [0]

    def rep(t):
        new, n, keys = _br_runs_fill([_br_html.unescape(t.group(2))], vals)
        if not n:
            return t.group(0)
        cnt[0] += n
        found.extend(keys)
        return '<w:t xml:space="preserve">' + _w_text(new[0]) + "</w:t>"
    return W_T_RE.sub(rep, s), cnt[0]


def _w_par(text, bold=False, right=False):
    ppr = '<w:pPr><w:jc w:val="right"/></w:pPr>' if right else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    if not text:
        return f"<w:p>{ppr}</w:p>"
    return f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{_w_text(text)}</w:t></w:r></w:p>'


def _w_block(vals):
    ps = [_w_par(l) for l in (vals.get("anschrift") or "").split("\n")]
    ps += [_w_par(""), _w_par(vals.get("datum", ""), right=True), _w_par("")]
    if vals.get("betreff"):
        ps += [_w_par(vals["betreff"], bold=True), _w_par("")]
    if vals.get("anrede"):
        ps += [_w_par(vals["anrede"]), _w_par("")]
    ps += [_w_par(l) for l in (vals.get("text") or "").replace("\r\n", "\n").split("\n")]
    ps += [_w_par(""), _w_par(vals.get("gruss", "")), _w_par(""), _w_par(""), _w_par(vals.get("inhaber", ""))]
    return "".join(ps)


def _br_fill_ooxml(src, dst, vals, insert=True):
    with zipfile.ZipFile(src) as zi:
        items = [(i, zi.read(i.filename)) for i in zi.infolist()]
    found, total = [], 0
    out = []
    for info, data in items:
        n = info.filename
        if re.match(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$", n):
            xml, c = _w_fill(data.decode("utf-8"), vals, found)
            total += c
            data = xml.encode("utf-8")
        out.append([info, data])
    modus = "platzhalter"
    if not total and not insert:
        modus = "kopie"
    elif not total:
        modus = "eingefuegt"
        for o in out:
            if o[0].filename == "word/document.xml":
                xml = o[1].decode("utf-8")
                m = re.search(r"<w:body(?:\s[^>]*)?>", xml)
                if not m:
                    raise ValueError("Die Word-Vorlage ist beschaedigt (kein Dokumentinhalt).")
                o[1] = (xml[:m.end()] + _w_block(vals) + xml[m.end():]).encode("utf-8")
    for o in out:
        if o[0].filename == "[Content_Types].xml":
            ct = o[1].decode("utf-8")
            ct = ct.replace("wordprocessingml.template.main+xml", "wordprocessingml.document.main+xml")
            ct = ct.replace("ms-word.template.macroEnabledTemplate.main+xml", "ms-word.document.macroEnabled.main+xml")
            o[1] = ct.encode("utf-8")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, data in out:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zo.writestr(zi, data)
    return total, sorted(set(found)), modus


# ---------- Excel (OOXML) ----------
X_SI_RE = re.compile(r"<(si|is)>.*?</\1>", re.S)
X_T_RE = re.compile(r"(<t(?:\s[^>]*)?(?<!/)>)(.*?)(</t>)", re.S)
X_HF_RE = re.compile(r"(<(?:odd|even|first)(?:Header|Footer)>)(.*?)(</(?:odd|even|first)(?:Header|Footer)>)", re.S)


def _x_fill_xml(xml, vals, found):
    cnt = [0]

    def si(m):
        blk = m.group(0)
        ts = list(X_T_RE.finditer(blk))
        if not ts:
            return blk
        new, n, keys = _br_runs_fill([_br_html.unescape(t.group(2)) for t in ts], vals)
        if not n:
            return blk
        cnt[0] += n
        found.extend(keys)
        out, last = [], 0
        for t, nt in zip(ts, new):
            out += [blk[last:t.start()], '<t xml:space="preserve">' + _br_html.escape(_br_clean(nt), quote=False) + "</t>"]
            last = t.end()
        return "".join(out) + blk[last:]

    def hf(m):
        new, n, keys = _br_runs_fill([_br_html.unescape(m.group(2))], vals)
        if not n:
            return m.group(0)
        cnt[0] += n
        found.extend(keys)
        return m.group(1) + _br_html.escape(_br_clean(new[0]), quote=False) + m.group(3)
    xml = X_SI_RE.sub(si, xml)
    xml = X_HF_RE.sub(hf, xml)
    return xml, cnt[0]


def _br_fill_xlsx(src, dst, vals, insert=False):
    with zipfile.ZipFile(src) as zi:
        items = [(i, zi.read(i.filename)) for i in zi.infolist()]
    found, total, out = [], 0, []
    for info, data in items:
        n = info.filename
        if n == "xl/sharedStrings.xml" or re.match(r"xl/worksheets/sheet\d+\.xml$", n):
            xml, c = _x_fill_xml(data.decode("utf-8"), vals, found)
            total += c
            data = xml.encode("utf-8")
        if n == "[Content_Types].xml":
            data = data.replace(b"spreadsheetml.template.main+xml", b"spreadsheetml.sheet.main+xml") \
                       .replace(b"ms-excel.template.macroEnabled.main+xml", b"ms-excel.sheet.macroEnabled.main+xml")
        out.append((info, data))
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, data in out:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zo.writestr(zi, data)
    return total, sorted(set(found)), "platzhalter" if total else "kopie"


def doc_fill(fp, dst, vals, insert):
    ext = os.path.splitext(fp)[1].lower()
    fn = _br_fill_ooxml if ext in BR_WORD_EXT else _br_fill_xlsx if ext in BR_XL_EXT else _br_fill_odf
    return fn(fp, dst, vals, insert)


# ---------- LibreOffice (ODF) ----------
O_P_RE = re.compile(r"<text:(p|h)(?:\s[^>]*)?>(?:(?!<text:(?:p|h)[ >]).)*?</text:\1>", re.S)


def _o_text(s):
    s = _br_html.escape(_br_clean(s), quote=False).replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "<text:line-break/>").replace("\t", "<text:tab/>")
    return re.sub(r"  +", lambda m: " <text:s text:c=\"%d\"/>" % (len(m.group(0)) - 1), s)


def _o_fill_par(par, vals, found):
    toks = re.split(r"(<[^>]+>)", par)
    idx = [i for i, t in enumerate(toks) if t and not t.startswith("<")]
    if not idx:
        return par, 0
    new, n, keys = _br_runs_fill([_br_html.unescape(toks[i]) for i in idx], vals)
    if not n:
        return par, 0
    found.extend(keys)
    for i, nt in zip(idx, new):
        toks[i] = _o_text(nt)
    return "".join(toks), n


def _o_par(text):
    return f"<text:p>{_o_text(text)}</text:p>" if text else "<text:p/>"


def _br_fill_odf(src, dst, vals, insert=True):
    with zipfile.ZipFile(src) as zi:
        items = [(i, zi.read(i.filename)) for i in zi.infolist()]
    found, total = [], 0
    out = []
    for info, data in items:
        if info.filename in ("content.xml", "styles.xml"):
            xml = data.decode("utf-8")
            cnt = [0]

            def rep(m):
                p, c = _o_fill_par(m.group(0), vals, found)
                cnt[0] += c
                return p
            xml = O_P_RE.sub(rep, xml)
            total += cnt[0]
            data = xml.encode("utf-8")
        if info.filename == "mimetype":
            data = data.replace(b"-template", b"")
        if info.filename == "META-INF/manifest.xml":
            data = data.replace(b"opendocument.text-template", b"opendocument.text").replace(b"opendocument.spreadsheet-template", b"opendocument.spreadsheet")
        out.append([info, data])
    modus = "platzhalter"
    if not total and not insert:
        modus = "kopie"
    elif not total:
        modus = "eingefuegt"
        for o in out:
            if o[0].filename == "content.xml":
                xml = o[1].decode("utf-8")
                m = re.search(r"<office:text(?:\s[^>]*)?>(\s*<text:sequence-decls>.*?</text:sequence-decls>)?(\s*<office:forms[^>]*/>)?", xml, re.S)
                if not m:
                    raise ValueError("Die ODT-Vorlage ist beschaedigt (kein Textinhalt).")
                v = vals
                ps = [_o_par(l) for l in (v.get("anschrift") or "").split("\n")] + [_o_par(""), _o_par(v.get("datum", "")), _o_par("")]
                if v.get("betreff"):
                    ps += [_o_par(v["betreff"]), _o_par("")]
                if v.get("anrede"):
                    ps += [_o_par(v["anrede"]), _o_par("")]
                ps += [_o_par(l) for l in (v.get("text") or "").split("\n")]
                ps += [_o_par(""), _o_par(v.get("gruss", "")), _o_par(""), _o_par(""), _o_par(v.get("inhaber", ""))]
                o[1] = (xml[:m.end()] + "".join(ps) + xml[m.end():]).encode("utf-8")
    with zipfile.ZipFile(dst, "w") as zo:
        for info, data in out:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zo.writestr(zi, data)
    return total, sorted(set(found)), modus


def br_scan_template(fp):
    """which placeholders does a template contain (for the hint in the editor)"""
    ext = os.path.splitext(fp)[1].lower()
    keys = set()
    try:
        with zipfile.ZipFile(fp) as z:
            if ext in BR_XL_EXT:
                for n in z.namelist():
                    if n == "xl/sharedStrings.xml" or re.match(r"xl/worksheets/sheet\d+\.xml$", n):
                        xml = z.read(n).decode("utf-8", "replace")
                        for m in list(X_SI_RE.finditer(xml)) + list(X_HF_RE.finditer(xml)):
                            t = _br_html.unescape("".join(t.group(2) for t in X_T_RE.finditer(m.group(0))) if m.group(0).startswith(("<si", "<is")) else m.group(2))
                            keys |= {_br_key(mm) for mm in BR_PH_RE.finditer(t) if _br_key(mm)}
                return sorted(keys)
            names = [n for n in z.namelist() if re.match(r"word/(document|header\d*|footer\d*)\.xml$", n)] if ext in BR_WORD_EXT \
                else [n for n in ("content.xml", "styles.xml") if n in z.namelist()]
            for n in names:
                xml = z.read(n).decode("utf-8", "replace")
                if n.startswith("word/"):
                    for m in W_P_RE.finditer(xml):
                        t = "".join(_br_html.unescape(t.group(2)) for t in W_T_RE.finditer(m.group(0)))
                        keys |= {_br_key(mm) for mm in BR_PH_RE.finditer(t) if _br_key(mm)}
                else:
                    for m in O_P_RE.finditer(xml):
                        t = _br_html.unescape(re.sub(r"<[^>]+>", "", m.group(0)))
                        keys |= {_br_key(mm) for mm in BR_PH_RE.finditer(t) if _br_key(mm)}
    except Exception:
        return None
    return sorted(keys)


# ---------- own letterhead (PDF) ----------
def brief_pdf(b, vals, s=None):
    s = s or get_settings()
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(("Brief - " + (b.get("betreff") or "")).strip(" -"))
    c.setAuthor(s.get("inhaber", ""))
    c.setCreator(f"{APP_NAME} v{APP_VERSION}")

    def T(x0, base, text, size=10, bold=False, align="l", col=colors.black):
        c.setFillColor(col)
        c.setFont(FONT_B() if bold else FONT_R(), size)
        y = H - base
        (c.drawRightString if align == "r" else c.drawString)(x0, y, text)

    def hline(x1, x2, top, w=0.6, col=LINE):
        c.setStrokeColor(col)
        c.setLineWidth(w)
        c.line(x1, H - top, x2, H - top)

    def footer():
        hline(56.7, 552.8, 789.5, 0.6)
        for x0, txt, al in [(56, s.get("fuss1", ""), "l"), (174, s.get("fuss2", ""), "l"), (307, s.get("fuss3", ""), "l"), (552.8, s.get("fuss4", ""), "r")]:
            for k, ln in enumerate((txt or "").split("\n")[:4]):
                T(x0, 803 + 8 * k, ln, size=7, align=al)

    logo = s.get("logo") or ""
    lp = os.path.join(ASSET_DIR, logo)
    if logo and os.path.exists(lp):
        try:
            img = ImageReader(lp)
            iw, ih = img.getSize()
            sc = min(65.5 / iw, 99.0 / ih)
            c.drawImage(img, 481.6 + (65.5 - iw * sc) / 2, H - 20 - ih * sc, iw * sc, ih * sc, mask="auto")
        except Exception:
            pass
    T(557.3, 139.0, s.get("firma", ""), size=12, bold=True, align="r")
    snd = s.get("absender", "")
    T(56, 157.0, snd, size=8)
    hline(56, 56 + c.stringWidth(snd, FONT_R(), 8), 158.4, 0.5, colors.black)
    for k, ln in enumerate((vals.get("anschrift") or "").split("\n")[:7]):
        T(56, 181.0 + 13 * k, ln, size=11)
    meta = [("Datum", vals.get("datum", ""))]
    if vals.get("kdnr"):
        meta.insert(0, ("Kunden-Nr.", vals["kdnr"]))
    for (lbl, val), base in zip(meta, [236, 250][-len(meta):]):
        T(393, base, lbl, size=11)
        T(489, base, val, size=11)
    y = 304
    if vals.get("betreff"):
        for ln in simpleSplit(vals["betreff"], FONT_B(), 12, 497):
            T(56, y, ln, size=12, bold=True)
            y += 15
        y += 14
    else:
        y = 318
    page = [1]
    LIM = 760

    def newpage():
        footer()
        c.showPage()
        page[0] += 1
        T(557.3, 60, s.get("firma", ""), size=12, bold=True, align="r")
        T(56, 60, f"Brief vom {vals.get('datum', '')}  ·  Seite {page[0]}", size=10, col=GRAY)
        return 100

    lines = []
    if vals.get("anrede"):
        lines += [vals["anrede"], ""]
    for para in (vals.get("text") or "").replace("\r\n", "\n").split("\n"):
        lines += simpleSplit(para, FONT_R(), 10.5, 497) or [""]
    lines += ["", vals.get("gruss", ""), "", "", vals.get("inhaber", "")]
    for ln in lines:
        if y > LIM:
            y = newpage()
        T(56, y, ln, size=10.5)
        y += 14
    footer()
    c.save()
    return buf.getvalue()


# ---------- data ----------
def _br_cust(cid):
    return q("SELECT * FROM customers WHERE id=?", (int(cid),), one=True) if cid else None


def br_values(b, s=None):
    s = s or get_settings()
    addr = b.get("anschrift") or []
    if isinstance(addr, str):
        addr = [l for l in addr.split("\n") if l.strip()]
    cu = _br_cust(b.get("customer_id")) or {}
    plz_ort = next((l for l in reversed(addr) if re.match(r"^\s*(D-)?\d{4,5}\s", l)), "")
    i = addr.index(plz_ort) if plz_ort in addr else -1
    pr = q("SELECT nr, name FROM projects WHERE id=?", (int(b["project_id"]),), one=True) if b.get("project_id") else None
    name = (cu.get("name") or "").strip()
    return {
        "anschrift": "\n".join(addr), "firma": cu.get("firma") or "", "name": ((cu.get("anrede") or "") + " " + name).strip() if name else (addr[0] if addr else ""),
        "kunde": cu.get("firma") or name or (addr[0] if addr else ""),
        "strasse": cu.get("strasse") or (addr[i - 1] if i > 0 else ""),
        "plz": cu.get("plz") or (plz_ort.split()[0] if plz_ort else ""), "ort": cu.get("ort") or (" ".join(plz_ort.split()[1:]) if plz_ort else ""),
        "plz_ort": " ".join(x_ for x_ in (cu.get("plz"), cu.get("ort")) if x_) or plz_ort,
        "datum": de_date(b.get("datum") or today()), "betreff": b.get("betreff") or "", "anrede": b.get("anrede") or "",
        "text": b.get("text") or "", "gruss": b.get("gruss") or "", "kdnr": b.get("kdnr") or cu.get("kdnr") or "",
        "absender": s.get("absender", ""), "inhaber": s.get("inhaber", ""), "meinefirma": s.get("firma", ""),
        "projekt": (pr["nr"] + " " + pr["name"]).strip() if pr else "",
    }


def _br_row(r):
    d = dict(r)
    try:
        d["anschrift"] = json.loads(d.get("anschrift") or "[]")
    except Exception:
        d["anschrift"] = [l for l in (d.get("anschrift") or "").split("\n") if l.strip()]
    d["datei_abs"] = os.path.join(DATA_DIR, d["datei"]) if d.get("datei") else ""
    d["datei_da"] = bool(d["datei_abs"]) and os.path.isfile(d["datei_abs"])
    return d


def br_list():
    rows = [_br_row(r) for r in q("SELECT * FROM briefe ORDER BY datum DESC, id DESC")]
    return {"ok": True, "briefe": rows}


def br_get(bid):
    r = q("SELECT * FROM briefe WHERE id=?", (int(bid),), one=True)
    if not r:
        raise ValueError("Brief nicht gefunden.")
    return dict(_br_row(r), ok=True)


def br_save(d):
    addr = d.get("addr") if d.get("addr") is not None else d.get("anschrift")
    if isinstance(addr, str):
        addr = [l for l in addr.split("\n") if l.strip()]
    vid = d.get("vorlage_id")
    vid = int(vid) if str(vid or "").strip().isdigit() and int(vid) > 0 else None
    vname = ""
    if vid:
        r = q("SELECT name FROM vorlagen WHERE id=?", (vid,), one=True)
        vname = r["name"] if r else ""
    art = "vorlage" if d.get("art") == "vorlage" else "brief"
    vals = (d.get("datum") or today(), d.get("customer_id") or None, d.get("project_id") or None, d.get("kdnr") or "",
            json.dumps(addr or [], ensure_ascii=False), d.get("betreff") or "", d.get("anrede") or "", d.get("text") or "",
            d.get("gruss") or "", vid, vname, art, now_iso())
    bid = d.get("bid")
    if bid and q("SELECT id FROM briefe WHERE id=?", (int(bid),), one=True):
        x("UPDATE briefe SET datum=?, customer_id=?, project_id=?, kdnr=?, anschrift=?, betreff=?, anrede=?, text=?, gruss=?, vorlage_id=?, "
          "vorlage_name=?, art=?, geaendert=? WHERE id=?", vals + (int(bid),))
    else:
        bid = x("INSERT INTO briefe (datum, customer_id, project_id, kdnr, anschrift, betreff, anrede, text, gruss, vorlage_id, vorlage_name, "
                "art, geaendert, erstellt, datei) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'')", vals + (now_iso(),))
    if art == "brief":
        set_setting("brief_vorlage", vid or 0)
    if art == "brief" and (d.get("gruss") or "").strip():
        set_setting("brief_gruss", d["gruss"].strip())
    return int(bid)


def _br_tpl(vid):
    r, fp = _vl_get(vid)
    ext = os.path.splitext(fp)[1].lower()
    if ext not in BR_FILL_EXT:  # letters: Word/LibreOffice text only
        raise ValueError(f"Die Vorlage „{r['name']}“ ist kein ausfüllbares Format (Word .docx/.dotx oder LibreOffice .odt). "
                         "Bitte die Vorlage einmal in Word als .docx speichern.")
    return r, fp, ext


def _br_mark(path):
    try:
        w = dict(get_settings().get("br_written") or {})
        w[os.path.normcase(os.path.abspath(path))] = os.path.getmtime(path)
        if len(w) > 400:
            w = dict(sorted(w.items(), key=lambda kv: kv[1])[-300:])
        set_setting("br_written", w)
    except Exception:
        traceback.print_exc()


def _br_place(b, tmp, nm, out_ext, folder_brief):
    """moves tmp to its final place: same file again, project folder or <Datenordner>/<folder>/<Jahr>"""
    old = b.get("datei_abs")
    if old and os.path.isfile(old) and os.path.splitext(old)[1].lower() == out_ext:
        # v2.0.6: only overwrite if nobody edited the file since it was created (Word changes stay)
        known = (get_settings().get("br_written") or {}).get(os.path.normcase(os.path.abspath(old)))
        if known and abs(os.path.getmtime(old) - float(known)) < 2:
            os.replace(tmp, old)
            _br_mark(old)
            return old
        b = dict(b, datei_abs=None)
        nm = nm + " (neu)"
    if b.get("project_id"):
        pf = add_project_file(int(b["project_id"]), tmp, nm + out_ext, "Briefe" if folder_brief else None)
        p = q("SELECT path FROM project_files WHERE id=?", (pf["id"],), one=True)
        _br_mark(os.path.join(DATA_DIR, p["path"]))
        return os.path.join(DATA_DIR, p["path"])
    folder = os.path.join(DATA_DIR, "Briefe" if folder_brief else "Dokumente", (b["datum"] or today())[:4])
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, nm + out_ext)
    root_, k = os.path.splitext(dst)[0], 2
    while os.path.exists(dst):
        dst = f"{root_} ({k}){out_ext}"
        k += 1
    shutil.move(tmp, dst)
    _br_mark(dst)
    return dst


def doc_create(d):
    """v2.0.5: new document from any template of the catalog"""
    if not d.get("vorlage_id"):
        raise ValueError("Bitte eine Vorlage auswählen.")
    bid = br_save(dict(d, art="vorlage"))
    b = br_get(bid)
    vals = br_values(b)
    r, fp = _vl_get(b["vorlage_id"])
    ext = os.path.splitext(fp)[1].lower()
    out_ext = BR_OUT_EXT.get(ext, ext)
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}[ _-]*", "", os.path.splitext(r["name"])[0])
    extra = " - ".join(x_ for x_ in (vals["kunde"], b.get("betreff")) if x_)
    nm = safe_name(f"{b['datum']} {stem}{(' - ' + extra) if extra else ''}"[:110])
    tmp = os.path.join(DATA_DIR, "_tmp_dok_" + uuid.uuid4().hex[:8] + out_ext)
    res = {"ok": True, "id": bid, "platzhalter": 0, "felder": [], "modus": "kopie"}
    try:
        if ext in DOC_FILL_EXT:
            try:
                n, keys, modus = doc_fill(fp, tmp, vals, False)
                res.update(platzhalter=n, felder=keys, modus=modus)
            except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
                shutil.copy2(fp, tmp)
                res["hinweis"] = "Die Vorlage ließ sich nicht ausfüllen (beschädigt?) – sie wurde unverändert kopiert."
        else:
            shutil.copy2(fp, tmp)
        _vl_used(r["id"])
        dst = _br_place(b, tmp, nm, out_ext, False)
    except PermissionError:
        raise ValueError("Die Datei ist noch geöffnet. Bitte dort schließen und nochmal erstellen.")
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    rel = os.path.relpath(dst, DATA_DIR) if os.path.abspath(dst).startswith(os.path.abspath(DATA_DIR)) else dst
    x("UPDATE briefe SET datei=?, geaendert=? WHERE id=?", (rel, now_iso(), bid))
    res.update(datei=dst, name=os.path.basename(dst))
    if d.get("oeffnen"):
        res["geoeffnet"] = open_plain(dst) if dst.lower().endswith(".pdf") else open_path(dst)
    return res


def doc_preview(d):
    try:
        r, fp = _vl_get(d.get("vorlage_id"))
    except ValueError as e:
        return {"ok": True, "fehler": str(e)}
    ext = os.path.splitext(fp)[1].lower()
    res = {"ok": True, "name": r["name"], "ordner": r.get("ordner") or "", "kategorie": VL_KAT_LABEL.get(r.get("kategorie"), r.get("kategorie") or ""),
           "art": r.get("art") or "", "ausfuellbar": ext in DOC_FILL_EXT, "felder": [], "hilfe": BR_PH_HELP, "auszug": (r.get("auszug") or "")[:400]}
    if ext in DOC_FILL_EXT:
        keys = br_scan_template(fp)
        if keys is None:
            res.update(ausfuellbar=False, hinweis="Die Datei lässt sich nicht lesen – sie wird unverändert kopiert.")
        else:
            res["felder"] = keys
    return res


def br_create(d):
    if d.get("art") == "vorlage":
        return doc_create(d)
    bid = br_save(d)
    b = br_get(bid)
    vals = br_values(b)
    nm = safe_name(f"{b['datum']} Brief {vals['kunde'] or 'ohne Empfaenger'}{(' - ' + b['betreff']) if b['betreff'] else ''}"[:110])
    res = {"ok": True, "id": bid}
    tmp = os.path.join(DATA_DIR, "_tmp_brief_" + uuid.uuid4().hex[:8])
    if b.get("vorlage_id"):
        r, fp, ext = _br_tpl(b["vorlage_id"])
        out_ext = BR_OUT_EXT.get(ext, ext)
        tmp += out_ext
        try:
            n, keys, modus = doc_fill(fp, tmp, vals, True)
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
            raise ValueError(f"Die Vorlage „{r['name']}“ lässt sich nicht lesen (beschädigt oder kein echtes Word-/LibreOffice-Format). "
                             "Bitte in Word öffnen und neu als .docx speichern.")
        _vl_used(r["id"])
        res.update(platzhalter=n, felder=keys, modus=modus)
    else:
        out_ext = ".pdf"
        tmp += out_ext
        with open(tmp, "wb") as f:
            f.write(brief_pdf(b, vals))
        res.update(platzhalter=0, felder=[], modus="briefpapier")
    try:
        dst = _br_place(b, tmp, nm, out_ext, True)
    except PermissionError:
        raise ValueError("Die Datei ist noch geöffnet (z. B. in Word). Bitte dort schließen und nochmal erstellen.")
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    rel = os.path.relpath(dst, DATA_DIR) if os.path.abspath(dst).startswith(os.path.abspath(DATA_DIR)) else dst
    x("UPDATE briefe SET datei=?, geaendert=? WHERE id=?", (rel, now_iso(), bid))
    res.update(datei=dst, name=os.path.basename(dst))
    if d.get("oeffnen"):
        res["geoeffnet"] = open_plain(dst) if dst.lower().endswith(".pdf") else open_path(dst)
    return res


def br_preview(d):
    if d.get("art") == "vorlage":
        return doc_preview(d)
    vid = d.get("vorlage_id")
    vid = int(vid) if str(vid or "").strip().isdigit() and int(vid) > 0 else None
    if vid:
        try:
            r, fp, ext = _br_tpl(vid)
        except ValueError as e:
            return {"ok": True, "vorlage": True, "fehler": str(e)}
        keys = br_scan_template(fp)
        if keys is None:
            return {"ok": True, "vorlage": True, "fehler": f"Die Vorlage „{r['name']}“ lässt sich nicht lesen (beschädigt oder kein echtes "
                    "Word-/LibreOffice-Format). Bitte in Word öffnen und neu als .docx speichern."}
        return {"ok": True, "vorlage": True, "name": r["name"], "ordner": r.get("ordner") or "", "felder": keys or [],
                "modus": "platzhalter" if keys else "eingefuegt", "hilfe": BR_PH_HELP}
    b = dict(d, anschrift=d.get("addr") or d.get("anschrift") or [])
    pdf = brief_pdf(b, br_values(b))
    pngs = pdf_to_pngs(pdf)
    tok = uuid.uuid4().hex[:12]
    # keep the last few previews (like the invoice preview) - a parallel invoice preview keeps its images
    for k_ in list(PREVIEW)[:-3]:
        PREVIEW.pop(k_, None)
    PREVIEW[tok] = pngs
    return {"ok": True, "vorlage": False, "token": tok, "pages": len(pngs)}


def br_delete(d):
    x("DELETE FROM briefe WHERE id=?", (int(d["id"]),))
    return {"ok": True}


def br_open(d):
    b = br_get(d["id"])
    if not b["datei_da"]:
        raise ValueError("Die Brief-Datei wurde noch nicht erstellt oder ist nicht mehr vorhanden.")
    fp = b["datei_abs"]
    if d.get("ordner"):
        return {"ok": open_path(os.path.dirname(fp))}
    return {"ok": open_plain(fp) if fp.lower().endswith(".pdf") else open_path(fp)}


def _br_boot(S_):
    S_["brief"] = {"vorlage": get_settings().get("brief_vorlage") or 0, "gruss": get_settings().get("brief_gruss") or "Mit freundlichen Grüßen",
                   "anzahl": q("SELECT COUNT(*) AS n FROM briefe", one=True)["n"]}


# ---------- selftest ----------
def _br_mkdocx(path, body, header="", template=False):
    ct = "application/vnd.openxmlformats-officedocument.wordprocessingml." + ("template" if template else "document") + ".main+xml"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   f'<Override PartName="/word/document.xml" ContentType="{ct}"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   f"<w:body>{body}<w:sectPr/></w:body></w:document>")
        if header:
            z.writestr("word/header1.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">{header}</w:hdr>')


def _br_selftest():
    errs = []
    d = tempfile.mkdtemp(prefix="pa_brief_")
    vals = {"anschrift": "Musterfirma GmbH\nHerr Max Muster\nHauptstr. 1\n12345 Musterstadt", "datum": "24.10.2026", "betreff": "Ihre Anfrage <AV>",
            "anrede": "Sehr geehrter Herr Muster,", "text": "Zeile 1\nZeile 2 & mehr", "gruss": "Mit freundlichen Grüßen", "inhaber": "T. Pfeiffer"}
    try:
        src = os.path.join(d, "v.dotx")
        body = ('<w:p><w:r><w:t>{{Ansch</w:t></w:r><w:r><w:t>rift}}</w:t></w:r></w:p>'
                '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">Betreff: </w:t></w:r><w:r><w:t>[Bet</w:t></w:r><w:r><w:t>reff]</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>{{Text}}</w:t></w:r></w:p><w:p><w:r><w:t>[Frist] bleibt</w:t></w:r></w:p>')
        _br_mkdocx(src, body, header='<w:p><w:r><w:t>&#171;Datum&#187;</w:t></w:r></w:p>', template=True)
        n, keys, modus = _br_fill_ooxml(src, os.path.join(d, "o.docx"), vals)
        with zipfile.ZipFile(os.path.join(d, "o.docx")) as z:
            doc = z.read("word/document.xml").decode()
            hdr = z.read("word/header1.xml").decode()
            ct = z.read("[Content_Types].xml").decode()
        if n != 4 or modus != "platzhalter":
            errs.append(f"Brief: {n} Platzhalter ersetzt (erwartet 4)")
        if "Musterfirma GmbH</w:t><w:br/>" not in doc or "{{" in doc or "Ihre Anfrage &lt;AV&gt;" not in doc:
            errs.append("Brief: zerstückelte Platzhalter/Zeilenumbrüche nicht korrekt ersetzt")
        if '<w:b/></w:rPr><w:t xml:space="preserve">Betreff: </w:t>' not in doc:
            errs.append("Brief: Formatierung des Betreff-Labels verloren")
        if "[Frist] bleibt" not in doc:
            errs.append("Brief: unbekannter Platzhalter wurde verändert")
        if "24.10.2026" not in hdr:
            errs.append("Brief: Platzhalter in der Kopfzeile nicht ersetzt")
        if "template.main" in ct:
            errs.append("Brief: .dotx wurde nicht in ein Dokument umgewandelt")
        src2 = os.path.join(d, "leer.docx")
        _br_mkdocx(src2, "<w:p/>")
        n2, _, modus2 = _br_fill_ooxml(src2, os.path.join(d, "o2.docx"), vals)
        with zipfile.ZipFile(os.path.join(d, "o2.docx")) as z:
            doc2 = z.read("word/document.xml").decode()
        if modus2 != "eingefuegt" or "Zeile 2 &amp; mehr" not in doc2 or "<w:b/>" not in doc2:
            errs.append("Brief: Einfügen ohne Platzhalter fehlgeschlagen")
        if br_scan_template(src) != ["anschrift", "betreff", "datum", "text"]:
            errs.append(f"Brief: Platzhalter-Erkennung liefert {br_scan_template(src)}")
        odt = os.path.join(d, "v.ott")
        with zipfile.ZipFile(odt, "w") as z:
            z.writestr("mimetype", "application/vnd.oasis.opendocument.text-template")
            z.writestr("content.xml", '<?xml version="1.0" encoding="UTF-8"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                       'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
                       '<text:p>{{Betr<text:span>eff}}</text:span></text:p><text:p>{{Anschrift}}</text:p></office:text></office:body></office:document-content>')
        n3, _, _ = _br_fill_odf(odt, os.path.join(d, "o.odt"), vals)
        with zipfile.ZipFile(os.path.join(d, "o.odt")) as z:
            c3 = z.read("content.xml").decode()
            mt = z.read("mimetype")
        if n3 != 2 or "Ihre Anfrage &lt;AV&gt;" not in c3 or "<text:line-break/>" not in c3 or mt != b"application/vnd.oasis.opendocument.text":
            errs.append("Brief: ODT-Vorlage nicht korrekt ausgefüllt")
        xl = os.path.join(d, "v.xltx")
        with zipfile.ZipFile(xl, "w") as z:
            z.writestr("[Content_Types].xml", '<Types><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml"/></Types>')
            z.writestr("xl/sharedStrings.xml", '<sst><si><t>Kunde: {{Firma}}</t></si><si><r><t>[Da</t></r><r><rPr><b/></rPr><t>tum]</t></r></si><si><t>Menge</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row><c t="inlineStr"><is><t>{{Betreff}}</t></is></c></row></sheetData>'
                       '<headerFooter><oddHeader>&amp;L{{Kundennummer}}</oddHeader></headerFooter></worksheet>')
        vx = dict(vals, firma="Musterfirma GmbH", kdnr="K-7")
        if br_scan_template(xl) != ["betreff", "datum", "firma", "kdnr"]:
            errs.append(f"Dokument: Excel-Platzhalter-Erkennung liefert {br_scan_template(xl)}")
        n4, _, m4 = _br_fill_xlsx(xl, os.path.join(d, "o.xlsx"), vx)
        with zipfile.ZipFile(os.path.join(d, "o.xlsx")) as z:
            ss = z.read("xl/sharedStrings.xml").decode()
            sh = z.read("xl/worksheets/sheet1.xml").decode()
            ct4 = z.read("[Content_Types].xml").decode()
        if n4 != 4 or "Kunde: Musterfirma GmbH" not in ss or "24.10.2026" not in ss or "Ihre Anfrage &lt;AV&gt;" not in sh or "&amp;LK-7" not in sh \
                or "template.main" in ct4 or "<t>Menge</t>" not in ss:
            errs.append("Dokument: Excel-Vorlage nicht korrekt ausgefüllt")
        _n5, _, m5 = _br_fill_ooxml(src2, os.path.join(d, "o5.docx"), vals, insert=False)
        if m5 != "kopie":
            errs.append("Dokument: Word-Vorlage ohne Platzhalter wurde verändert")
        if not brief_pdf({"betreff": "Test"}, dict(vals, text="Absatz\n" * 120)).startswith(b"%PDF"):
            errs.append("Brief: PDF auf eigenem Briefpapier nicht erzeugt")
    except Exception as e:
        errs.append(f"Brief: Ausnahme {e}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return errs


HOOK_SCHEMA.append(_br_schema)
HOOK_BOOT.append(_br_boot)
HOOK_SELFTEST.append(_br_selftest)
HOOK_GET["/api/briefe"] = lambda h, qs: h._send(200, br_list())
HOOK_GET["/api/brief"] = lambda h, qs: h._send(200, br_get(qs.get("id") or 0))
HOOK_POST["/api/brief/save"] = lambda h, d: h._send(200, {"ok": True, "id": br_save(d)})
HOOK_POST["/api/brief/erstellen"] = lambda h, d: h._send(200, br_create(d))
HOOK_POST["/api/brief/preview"] = lambda h, d: h._send(200, br_preview(d))
HOOK_POST["/api/brief/delete"] = lambda h, d: h._send(200, br_delete(d))
HOOK_POST["/api/dokument/erstellen"] = lambda h, d: h._send(200, doc_create(d))
HOOK_POST["/api/brief/oeffnen"] = lambda h, d: h._send(200, br_open(d))
