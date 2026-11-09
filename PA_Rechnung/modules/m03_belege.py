# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m03_belege
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# PDF text + document recognition
# ----------------------------------------------------------------------------

def pdf_text(path_or_bytes):
    if not pypdf:
        return ""
    try:
        r = pypdf.PdfReader(io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes)
        parts = []
        for pg in r.pages[:6]:
            try:
                parts.append(pg.extract_text(extraction_mode="layout") or "")
            except Exception:
                parts.append(pg.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        return ""


# v2.1.0: amounts must not start or end inside another number - "1,200.00" was read as "1,20" + "0.00"
# and the "26.10" of a date "26.10.2026" counted as an amount
AMT = (r"(?<![\d.,])(?:-?\d{1,3}(?:\.\d{3})*,\d{2}-?|-?\d+,\d{2}-?|-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+\.\d{2})"
       r"(?!\d|[.,]\d)")
# label lines that only carry a net / partial value (used with avoid= in first_amount_after)
NET_LINE = r"netto|\bnet\b|exkl|excl|zzgl|ohne (?:mwst|ust)|subtotal|zwischensumme"


def first_amount_after(text, patterns, prefer="first", avoid=None):
    lines = text.split("\n")
    for pat in patterns:
        hits = [i for i, line in enumerate(lines) if re.search(pat, line, re.I)]
        if avoid:
            # v2.1.0: "Gesamtbetrag netto 950,00" / "Gesamtbetrag brutto 1.130,50" -> take the gross line
            hits = [i for i in hits if not re.search(avoid, lines[i], re.I)] + [i for i in hits if re.search(avoid, lines[i], re.I)]
        for i in hits:
            line = lines[i]
            tail = re.split(pat, line, maxsplit=1, flags=re.I)[-1]
            am = re.findall(AMT, tail)
            if am:
                v = parse_amount(am[0] if prefer == "first" else am[-1])
                return abs(v)
            # amount in a table row below the label (e.g. "Nettobetrag  MwSt.  Endbetrag" / "66,39  19  79,00")
            col = re.search(pat, line, re.I).start()
            for nxt in lines[i + 1:i + 3]:
                am = [(m.start(), m.group(0)) for m in re.finditer(AMT, nxt)]
                if am:
                    best = min(am, key=lambda a: abs(a[0] - col))
                    return abs(parse_amount(best[1] if abs(best[0] - col) < 25 else am[-1][1]))
    return 0.0


DATE_MONTHS = {"januar": 1, "january": 1, "jan": 1, "februar": 2, "february": 2, "feb": 2, "märz": 3, "maerz": 3, "march": 3, "mär": 3,
               "mrz": 3, "mar": 3, "april": 4, "apr": 4, "mai": 5, "may": 5, "juni": 6, "june": 6, "jun": 6, "juli": 7, "july": 7, "jul": 7,
               "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "oktober": 10, "october": 10, "okt": 10, "oct": 10,
               "november": 11, "nov": 11, "dezember": 12, "december": 12, "dez": 12, "dec": 12}
_MON_RE = "|".join(sorted(DATE_MONTHS, key=len, reverse=True))
DATE_PATTERNS = (
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2}|\d{2})\b"), "dmy"),
    (re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"), "ymd"),                                                  # 2026-10-14
    (re.compile(r"\b(\d{1,2})\.?\s+(" + _MON_RE + r")\.?\s+(20\d{2})\b", re.I), "dMy"),                   # 14. Oktober 2026 / 14 Oct 2026
    (re.compile(r"\b(" + _MON_RE + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b", re.I), "Mdy"),    # October 14, 2026
)


def find_dates(text):
    """v2.1.0: also ISO dates and dates with German/English month names; result in text order"""
    found = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text or ""):
            try:
                if kind == "dmy":
                    iso = iso_from_de(m.group(0))
                elif kind == "ymd":
                    iso = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
                elif kind == "dMy":
                    iso = datetime.date(int(m.group(3)), DATE_MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
                else:
                    iso = datetime.date(int(m.group(3)), DATE_MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
            except Exception:
                iso = ""
            if iso:
                found.append((m.start(), iso))
    return [iso for _p, iso in sorted(found)]


def _label_value(text, label, value_fn):
    """value behind a label on the same line, else in the line below under the label (table header)"""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for m in re.finditer(label, line, re.I):
            v = value_fn(line[m.end():])
            if v:
                return v
            for nxt in lines[i + 1:i + 2]:
                seg = nxt[max(0, m.start() - 3):m.start() + 40]
                v = value_fn(seg)
                if v:
                    return v
    return ""


SUM_LABEL = r"(?<!zwischen)(?<!zwischen-)(?<!netto)(?<!teil)summe"
TOTAL_LABEL = r"(?<!sub)(?<!sub-)(?<!sub )total"


def foreign_currency(text):
    """'USD', 'GBP', 'CHF' ... when the document shows foreign amounts and no Euro at all"""
    t = text or ""
    if re.search(r"€|\beur\b|\beuro\b", t, re.I):
        return ""
    for cur, rx in (("USD", r"\bUSD\b|US\$|\$\s?\d|\d\s?\$"), ("GBP", r"\bGBP\b|£"), ("CHF", r"\bCHF\b|\bSFr\b"),
                    ("PLN", r"\bPLN\b|\bzł"), ("SEK", r"\bSEK\b"), ("DKK", r"\bDKK\b"), ("JPY", r"\bJPY\b|¥"), ("CNY", r"\bCNY\b|\bRMB\b")):
        if re.search(rx, t):
            return cur
    return ""


def _first_date(s):
    d_ = find_dates((s or "")[:60])
    return d_[0] if d_ else ""


def _doc_number(s):
    # the number must contain a digit (else "Rechnungsnummer   Kundennummer" took the next header word);
    # blocks of digits separated by single spaces belong together ("1234 5678 9012")
    m = re.match(r"\s*\.?\s*:?\s*((?=[\w\-/]*\d)[A-Z0-9][\w\-/]{2,}(?: \d{3,})*)", s or "", re.I)
    return m.group(1) if m else ""


# category keywords that also occur inside ordinary words or as amount labels
_CAT_SPECIAL = {"total": r"(?<![a-z])total(?:energies\b|\s+(?:tankstelle|station|deutschland|service))", "buch": r"buch\b|bücher"}


def guess_category(text):
    """v2.1.0: keywords only at the start of a word ("esso" no longer hits "Prozessor", "obi" not "Mobilfunk",
    "avid" not "David"); "Total"/"Subtotal" with an amount is no petrol station"""
    low = (text or "").lower()
    for keys, cat in VENDOR_CATEGORY:
        for k in keys:
            pat = _CAT_SPECIAL.get(k) or (r"(?<![a-zäöüß])" + re.escape(k))
            if re.search(pat, low):
                return cat
    return "Sonstige Betriebsausgaben"


def guess_partner(text, s):
    own = [s.get("firma", "").lower(), s.get("inhaber", "").lower()]
    absl = (s.get("absender") or "").lower()
    own += [p.strip() for p in re.split(r"[,·|]", absl) if len(p.strip()) > 5]
    for line in text.split("\n")[:25]:
        l = re.sub(r"\s{2,}", " | ", line.strip())
        part = l.split(" | ")[0].strip()
        if len(part) < 3 or re.search(r"\d{2}\.\d{2}\.", part):
            continue
        if any(o and o in part.lower() for o in own):
            continue
        if re.match(r"^\d{5}\s", part) or re.search(r"(straße|str\.|strasse|weg|gasse|platz)\s*\d", part, re.I):
            continue
        if re.match(r"^(rechnung|invoice|seite|page|datum|kunden|beleg|quittung|herrn|frau|an)\b", part, re.I):
            continue
        if re.search(r"[A-Za-zÄÖÜäöü]{3,}", part):
            return part[:80]
    return ""


def parse_own_invoice(text):
    """Parse an invoice created by this program or the old program (same layout)."""
    def field(lbl):
        m = re.search(lbl + r"\s+(\S+)", text)
        return m.group(1) if m else ""
    lines = text.split("\n")
    hi = next((i for i, l in enumerate(lines) if re.match(r"\s*Pos\.\s", l)), None)
    if hi is None:
        return None
    pre = [l.strip() for l in lines[:hi] if l.strip()]
    inv = dict(nr=field(r"Rechnung Nr\."), datum=iso_from_de(field(r"\bDatum")), liefer=iso_from_de(field("Lieferdatum")),
               auftrag=iso_from_de(field("Auftragsdatum")), kdnr=field(r"Kunden-Nr\."))
    inv["toptext"] = pre[-1] if pre else ""
    inv["titel"] = re.split(r"\s{2,}", pre[-2])[0] if len(pre) > 1 else "Rechnung"
    items, cur = [], None
    skipping = False
    old_layout = bool(re.search(r"Pos\.\s+Nr\.\s+Beschreibung\s+Anzahl", lines[hi]))
    for l in lines[hi + 1:]:
        if "Gesamtbetrag" in l or "Zahlbetrag" in l:
            break
        if "Übertrag" in l:
            skipping = True
            continue
        if skipping:
            if re.match(r"\s*Pos\.\s", l):
                skipping = False
            continue
        if old_layout:
            mo = re.match(r"\s+(\d+)\s+(\S+)\s+(.+?)\s{2,}([\d.,]+)\s+([\d.,]+) EUR(?:\s+([\d,]+) %)?\s+(?:[\d.,]+ EUR\s+)?([\d.,]+) EUR", l)
            m = None
            if mo:
                cur = dict(qty=parse_amount(mo.group(4)) if "," in mo.group(4) else float(mo.group(4)), nr=mo.group(2),
                           name=mo.group(3).strip(), price=parse_amount(mo.group(5)),
                           rabatt=parse_amount(mo.group(6)) if mo.group(6) else 0.0, descr=[])
                items.append(cur)
                continue
        else:
            m = re.match(r"\s+(\d+)\s+([\d,]+)\s+(\S+)\s+(.+?)\s{2,}([\d.,]+) EUR(?:\s+([\d,]+) %)?\s+([\d.,]+) EUR", l)
        if m:
            cur = dict(qty=parse_amount(m.group(2)) if "," in m.group(2) else float(m.group(2)), nr=m.group(3),
                       name=m.group(4).strip(), price=parse_amount(m.group(5)),
                       rabatt=parse_amount(m.group(6)) if m.group(6) else 0.0, descr=[])
            items.append(cur)
        elif cur and l.strip():
            cur["descr"].append(l.strip())
    for it in items:
        it["descr"] = "\n".join(it["descr"])
    inv["items"] = items
    low = text.lower()
    inv["zahlart"] = "PayPal" if "paypal bezahlen" in low else ("Ueberweisung" if "zahlbetrag" in low else "Bar")
    m = re.search(r"binnen (\d+) Tagen", text)
    inv["frist"] = int(m.group(1)) if m else 7
    if inv["toptext"] and m:
        inv["toptext"] = inv["toptext"].replace(f"binnen {m.group(1)} Tagen", "binnen [Frist] Tagen")
    # address: lines between sender line and meta labels (left part)
    addr = []
    for l in lines[:hi]:
        if "Lieferdatum" in l or "Auftragsdatum" in l or re.search(r"\bSeite\b", l) or re.search(r"\bDatum\b", l):
            left = re.split(r"\s{3,}", l.strip())[0]
            if left and not re.match(r"(Lieferdatum|Auftragsdatum|Seite|Datum|Kunden-Nr|Rechnung Nr)", left):
                addr.append(left)
    inv["addr"] = addr
    inv["summe"] = round(sum(line_total(i) for i in items), 2)
    return inv


def analyze_pdf(path, filename, pw=None, pre_text=None, pre_fmt=None):
    s = get_settings()
    low_fn = filename.lower()
    used_pw = None
    fmt = pre_fmt or FORMAT_NAMES.get(os.path.splitext(low_fn)[1], "Datei")
    if low_fn.endswith(".xml"):
        try:
            info = parse_einvoice_xml(open(path, "rb").read())
        except Exception:
            info = None
        if info:
            r = einvoice_result(info, s)
            r.update(filename=filename, text="")
            return r
    if low_fn.endswith(".pdf") and pre_text is None:
        # v2.1.0: also for password protected ZUGFeRD/Factur-X PDFs (standard / saved / entered password)
        emb = pdf_embedded_xml(path, pw)
        if emb:
            r = einvoice_result(emb[0], s)
            r.update(filename=filename, text="")
            if emb[2]:
                r["_pw"] = emb[2]
                r["details"]["passwortgeschuetzt"] = True
                if pw is None:
                    r["hint"] = "Passwortgeschützt – mit gespeichertem Passwort geöffnet. " + r["hint"]
            return r
    if pre_text is not None:
        text = pre_text
    else:
        try:
            text, used_pw, fmt = extract_text_any(path, filename, pw)
        except PasswordNeeded:
            raise
        except Exception:
            traceback.print_exc()
            text = ""
    ocr_used = False
    ocr_err = ""
    # v2.6.7: also password protected scans (password goes to the OCR), also PDFs with only a few stray characters,
    # also HEIC photos; the reason of a failed OCR is shown in the hint
    if ocr_need(text) and ocr_available() and (low_fn.endswith(".pdf") or low_fn.endswith(IMAGE_EXT) or low_fn.endswith((".heic", ".heif"))):
        try:
            t_ = ocr_file(path, used_pw or pw)
            if len(t_.strip()) > len(text.strip()):
                text = t_
                ocr_used = True
        except Exception as e:
            traceback.print_exc()
            ocr_err = OCR_LAST.get("fehler") or str(e)[:200]
    low = text.lower()
    res = {"typ": "ausgabe", "confidence": 0.4, "datum": "", "partner": "", "nr": "", "betrag": 0.0,
           "kategorie": "Sonstige Betriebsausgaben", "details": {}, "hint": "", "filename": filename,
           "text": text[:4000], "format": fmt}
    if used_pw:
        res["_pw"] = used_pw
        res["details"]["passwortgeschuetzt"] = True
    if not text.strip():
        if low_fn.endswith(".pdf") or low_fn.endswith(IMAGE_EXT) or low_fn.endswith((".heic", ".heif")):
            if ocr_err:
                h_ = f"Kein Text gefunden (Scan/Foto). Texterkennung fehlgeschlagen: {ocr_err} – Bitte Art und Werte selbst eintragen."
            elif not ocr_available():
                h_ = "Kein Text gefunden (Scan/Foto). Windows-Texterkennung nicht verfügbar (nur unter Windows 10/11) - Bitte Art und Werte selbst eintragen."
            else:
                h_ = "Kein Text gefunden (Scan/Foto) – auch die Texterkennung hat nichts gelesen (Bild zu hell/unscharf?). Bitte Art und Werte selbst eintragen."
        else:
            h_ = f"{fmt}: Inhalt nicht auslesbar – die Datei wird trotzdem als Beleg abgelegt. Bitte Art und Werte selbst eintragen."
        res.update(typ="ausgabe", confidence=0.0, hint=h_)
        return res
    dates = find_dates(text)
    res["datum"] = dates[0] if dates else ""
    own_iban = re.sub(r"\s", "", s.get("iban", "")).lower()
    firm = (s.get("firma") or "").lower()
    head = low[:1500]
    own_ids = [t.lower() for t in re.findall(r"\bDE\d{9}\b|\b\d{3}/\d{4}/\d{4}\b", " ".join(s.get(k, "") for k in ("fuss1", "fuss2", "fuss3", "fuss4")))]
    flat = re.sub(r"\s", "", low)
    has_own_id = (own_iban and own_iban in flat) or any(t.replace(" ", "") in flat for t in own_ids)
    firm_n = re.sub(r"[^a-z0-9äöü]", "", firm)
    is_own = bool(firm and (firm in head or (firm_n and firm_n in re.sub(r"[^a-z0-9äöü]", "", head))) and "rechnung nr" in low and "pos." in low and has_own_id)
    own_parsed = parse_own_invoice(text) if is_own else None
    if own_parsed is not None and not own_parsed["items"]:
        is_own = False
    if "lohnsteuerbescheinigung" in low:
        res["typ"] = "gehalt"
        res["confidence"] = 0.95
        res["details"] = salary_fields(text, year_doc=True)
        res["betrag"] = res["details"].get("brutto", 0.0)
        res["partner"] = salary_employer(text) or guess_partner(text, s)
        res["hint"] = "Lohnsteuerbescheinigung erkannt (Jahreswerte)."
    elif re.search(r"(verdienst|entgelt|gehalts|lohn|bezüge)abrechnung|abrechnung der brutto|brutto/netto|gesamt-?brutto", low):
        res["typ"] = "gehalt"
        res["confidence"] = 0.9
        res["details"] = salary_fields(text, year_doc=False)
        res["betrag"] = res["details"].get("brutto", 0.0)
        res["partner"] = salary_employer(text) or guess_partner(text, s)
        res["hint"] = "Gehaltsabrechnung erkannt (Monatswerte)."
    elif is_own:
        p = own_parsed
        res["typ"] = "eigene_rechnung"
        res["confidence"] = 0.95
        res["parsed"] = p
        if p:
            res.update(nr=p["nr"], datum=p["datum"], betrag=p["summe"], partner=(p["addr"] or [""])[0])
            ex = q("SELECT id FROM invoices WHERE nr=?", (p["nr"],), one=True)
            res["hint"] = "Eigene Ausgangsrechnung erkannt." + (" Diese Nummer existiert bereits und wird nicht doppelt angelegt." if ex else " Wird ins Rechnungsarchiv übernommen.")
    elif re.search(r"dozentenabrechnung|honorarabrechnung|stundennachweis|leistungsnachweis|teilnehmerliste|abrechnung für", low):
        res["typ"] = "anlage"
        res["confidence"] = 0.8
        res["partner"] = guess_partner(text, s)
        res["betrag"] = first_amount_after(text, [r"gesamtsumme", SUM_LABEL, r"gesamt"], "last", avoid=NET_LINE)
        res["hint"] = "Abrechnung/Nachweis erkannt - kann als Anlage an eine Rechnung gehängt werden."
    elif re.search(r"\bgutschrift\b|auszahlung an sie|honorar", low) and not re.search(r"rechnungsbetrag|zu zahlen", low):
        res["typ"] = "einnahme"
        res["confidence"] = 0.6
        res["partner"] = guess_partner(text, s)
        res["betrag"] = first_amount_after(text, [r"gutschriftsbetrag", r"auszahlungsbetrag", r"gesamtbetrag", SUM_LABEL], "last", avoid=NET_LINE)
        res["nr"] = _label_value(text, r"gutschrifts?-?\s?(?:nr|nummer)\b", _doc_number)
        res["datum"] = _label_value(text, r"gutschriftsdatum|belegdatum|(?<![a-zäöüß])datum\b", _first_date) or res["datum"]
        res["hint"] = "Gutschrift / Einnahme erkannt."
    else:
        res["typ"] = "ausgabe"
        res["confidence"] = 0.7 if re.search(r"rechnung|invoice|quittung|kassenbon|beleg|receipt", low) else 0.3
        res["partner"] = guess_partner(text, s)
        # v2.1.0: "Zwischensumme"/"Nettosumme"/"Subtotal" are no final amount; net lines of a label only as last resort
        res["betrag"] = first_amount_after(text, [r"rechnungsbetrag", r"gesamtbetrag", r"zu zahlen(?:der betrag)?",
                                                   r"endbetrag", r"gesamtsumme", r"brutto(?:betrag)?", r"amount due|total due|grand total",
                                                   TOTAL_LABEL, SUM_LABEL], "last", avoid=NET_LINE)
        res["nr"] = _label_value(text, r"rechnungs?-?\s?(?:nr|nummer)\b|invoice\s*(?:no\b|number|#)|beleg-?(?:nr|nummer)\b", _doc_number)
        # v2.1.0: the invoice date wins over other dates; "Lieferdatum"/"Faelligkeitsdatum" no longer count as "Datum"
        res["datum"] = (_label_value(text, r"rechnungsdatum|belegdatum|invoice\s+date|date\s+of\s+invoice", _first_date)
                        or _label_value(text, r"(?<![a-zäöüß])datum\b|(?<![a-z])(?<!due )date\b", _first_date) or res["datum"])
        res["kategorie"] = guess_category(text)
        res["hint"] = "Eingangsrechnung / Ausgabe erkannt." if res["confidence"] > 0.5 else "Art unsicher - bitte prüfen."
    if res["typ"] in ("ausgabe", "einnahme") and res["betrag"]:
        cur = foreign_currency(text)
        if cur:
            res.setdefault("warnungen", []).append(f"Beträge in {cur} – das Programm rechnet in Euro: bitte den Euro-Betrag (Kontoauszug) eintragen.")
    if fmt not in ("PDF", "Bild", "E-Mail"):
        res["hint"] = f"Gelesen aus {fmt}-Datei. " + res["hint"]
    if used_pw and pw is None:
        res["hint"] = "Passwortgeschützt – mit gespeichertem Passwort geöffnet. " + res["hint"]
    if ocr_used:
        res["confidence"] = round(res["confidence"] * 0.8, 2)
        res["hint"] = "Per Windows-Texterkennung gelesen - bitte Werte prüfen. " + res["hint"]
    if res["typ"] == "ausgabe" and res["betrag"] and res["kategorie"].startswith("Arbeitsmittel") and not gwg_check(res["betrag"]):
        res["anlage_vorschlag"] = True
        res["hint"] += " Über der GWG-Grenze von 800 € (Kleinunternehmer: brutto, sonst netto) - als Anlagegut (AfA) erfassen."
    if res["typ"] == "gehalt":
        per = res["details"].get("periode", "")
        mons = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]
        m = re.match(r"(\w+) (20\d{2})", per.lower().replace("maerz", "märz"))
        m2 = re.match(r"(\d{2})/(20\d{2})", per)
        if res["details"].get("zeitraum") == "jahr":
            ym = re.findall(r"\b(20\d{2})\b", text)
            if ym:
                res["datum"] = f"{max(ym, key=ym.count)}-12-31"
        elif m and m.group(1) in mons:
            res["datum"] = f"{m.group(2)}-{mons.index(m.group(1)) + 1:02d}-28"
        elif m2:
            res["datum"] = f"{m2.group(2)}-{m2.group(1)}-28"
    return res


def salary_employer(text):
    for pat in (r"arbeitgeber\s*:?\s*(.+)", r"firma\s*:?\s*(.+)"):
        m = re.search(pat, text, re.I)
        if m:
            v = re.split(r"\s{2,}", m.group(1).strip())[0]
            if len(v) > 2:
                return v[:80]
    return ""


def salary_fields(text, year_doc):
    d = {"zeitraum": "jahr" if year_doc else "monat"}
    if year_doc:
        d["brutto"] = first_amount_after(text, [r"bruttoarbeitslohn"])
        d["lst"] = first_amount_after(text, [r"einbehaltene lohnsteuer"])
        d["soli"] = first_amount_after(text, [r"einbehaltener solidarit"])
        d["kist"] = first_amount_after(text, [r"einbehaltene kirchensteuer des arbeitnehmers", r"einbehaltene kirchensteuer"])
        d["rv"] = first_amount_after(text, [r"arbeitnehmeranteil.{0,40}rentenvers", r"rentenversicherung"])
        d["kv"] = first_amount_after(text, [r"arbeitnehmerbeitr.{0,30}krankenvers", r"krankenversicherung"])
        d["pv"] = first_amount_after(text, [r"arbeitnehmerbeitr.{0,30}pflegevers", r"pflegeversicherung"])
        d["av"] = first_amount_after(text, [r"arbeitnehmerbeitr.{0,30}arbeitslosenvers", r"arbeitslosenversicherung"])
        d["netto"] = 0.0
    else:
        d["brutto"] = first_amount_after(text, [r"gesamt[- ]?brutto", r"steuer[- ]?brutto", r"brutto[- ]?(?:bezug|bezüge|verdienst|lohn|gehalt|entgelt)", r"\bbrutto\b"])
        d["lst"] = first_amount_after(text, [r"lohnsteuer(?!klasse|-?id|tage|-?ident)"])
        d["soli"] = first_amount_after(text, [r"solidarit"])
        d["kist"] = first_amount_after(text, [r"kirchensteuer", r"\bkist\b"])
        d["kv"] = first_amount_after(text, [r"krankenvers", r"\bkv[- ]?beitrag", r"\bkv\b"])
        d["rv"] = first_amount_after(text, [r"rentenvers", r"\brv[- ]?beitrag", r"\brv\b"])
        d["av"] = first_amount_after(text, [r"arbeitslosenvers", r"\bav[- ]?beitrag", r"\bav\b"])
        d["pv"] = first_amount_after(text, [r"pflegevers", r"\bpv[- ]?beitrag", r"\bpv\b"])
        d["netto"] = first_amount_after(text, [r"auszahlungsbetrag", r"auszahlung", r"überweisungsbetrag", r"nettoverdienst", r"netto"])
    m = re.search(r"(januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+(20\d{2})", text, re.I)
    if m:
        d["periode"] = f"{m.group(1).capitalize()} {m.group(2)}"
    else:
        m = re.search(r"\b(0[1-9]|1[0-2])[./](20\d{2})\b", text)
        if m:
            d["periode"] = f"{m.group(1)}/{m.group(2)}"
    return d


def detect_kind(name, folders):
    low = name.lower()
    ext = os.path.splitext(low)[1]
    rules = {k: (keys, exts) for k, keys, exts in KIND_RULES}
    kind = None
    # 1) unambiguous file types win
    for k in ("CAD-Zeichnung", "Q-SYS / AV-Programm", "Audio"):
        if ext in rules[k][1]:
            kind = k
            break
    # 2) keywords in the file name
    if not kind:
        for k in ("Schweißdokument", "Blockschaltbild", "Stückliste", "Zeichnung"):
            keys, exts = rules[k]
            if any(kw in low for kw in keys):
                if k == "Stückliste" and ext not in (".xlsx", ".xls", ".csv", ".pdf", ".ods"):
                    continue
                if k == "Zeichnung" and ext not in (".pdf", ".svg", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
                    continue
                kind = k
                break
    # 3) generic by extension
    if not kind:
        for k in ("Blockschaltbild", "Foto", "Stückliste", "Dokument"):
            if ext in (rules[k][1] or ()):
                kind = k
                break
    kind = kind or "Sonstiges"
    folder = ""
    for h in KIND_FOLDER_HINTS.get(kind, ()):
        folder = next((f for f in folders if h in f.lower()), "")
        if folder:
            break
    if not folder and kind in ("Schweißdokument", "Stückliste"):
        folder = next((f for f in folders if "doku" in f.lower()), "")
    if not folder and folders:
        folder = folders[0]
    return kind, folder


# ----------------------------------------------------------------------------
# Belege
# ----------------------------------------------------------------------------

def store_upload(tmp_path, filename, sub):
    y = str(datetime.date.today().year)
    d = os.path.join(BELEG_DIR, sub, y)
    os.makedirs(d, exist_ok=True)
    base = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6] + "_" + safe_name(filename)
    dst = fit_path(d, base)     # v2.6.3: long names stay below MAX_PATH
    shutil.move(tmp_path, dst)
    return os.path.relpath(dst, DATA_DIR)


TMP = {}


def _beleg_num(v, what="Betrag"):
    """number from the UI: float/int, '12.50' or German '12,50' / '1.234,56'"""
    if v is None or isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s_ = str(v).strip()
    if not s_:
        return 0.0
    try:
        return float(parse_amount(s_))
    except Exception:
        raise ValueError(f"{what} „{s_}“ ist keine gültige Zahl.")


_BELEG_SAVE_LOCK = threading.Lock()


def save_beleg(d):
    # v2.6.3: validate and convert everything BEFORE the token / the inbox entry are consumed and the file is
    # filed - an error afterwards (e.g. Betrag "12,50") left the file orphaned in "Belege" and the entry was gone
    d = dict(d)
    d["betrag"] = _beleg_num(d.get("betrag"))
    if d.get("als_anlage"):
        d["anlage_nd"] = _beleg_num(d.get("anlage_nd"), "Nutzungsdauer") or 5.0
    if d.get("datum"):
        dd_ = d_iso(str(d["datum"]))
        if not dd_:
            raise ValueError(f"Datum „{d['datum']}“ ist ungültig.")
        d["datum"] = dd_.isoformat()
    pend = int(d["pending_id"]) if str(d.get("pending_id") or "").strip() else None
    tok = d.get("token")
    with _BELEG_SAVE_LOCK:      # double click: the second call finds the token gone
        tmp = TMP.pop(tok, None) if tok else None
    if tok and tmp is None:
        return {"ok": False, "error": "Dieser Beleg wurde bereits übernommen."}
    moved = []
    try:
        res = _save_beleg_core(d, tmp, moved)
    except Exception:
        # restore: file back to its temp place, token valid again, inbox entry untouched
        for dst_, src_ in moved:
            try:
                if os.path.exists(dst_) and not os.path.exists(src_):
                    shutil.move(dst_, src_)
            except Exception:
                traceback.print_exc()
        if tok and tmp is not None:
            TMP[tok] = tmp
        raise
    if pend:
        x("DELETE FROM pending_belege WHERE id=?", (pend,))
    return res


def _save_beleg_core(d, tmp, moved):
    def _learn(bid_=None):
        try:
            if d.get("typ") in ASSIST_TYPES and d.get("lernen", True):
                learn_sample(d.get("typ"), d.get("kategorie") if d.get("typ") == "ausgabe" else "", d.get("partner"), d.get("text") or "", bid_)
        except Exception:
            traceback.print_exc()
    typ = d.get("typ")
    rel = ""
    if typ == "eigene_rechnung" and d.get("parsed") and q("SELECT id FROM invoices WHERE nr=?", (d["parsed"].get("nr"),), one=True):
        # v2.1.0: checked before filing - the PDF was moved to "Eigene Rechnungen" without any entry pointing to it
        if tmp:
            try:
                os.remove(tmp["path"])
            except Exception:
                pass
        return {"ok": True, "info": f"Rechnung {d['parsed'].get('nr')} existiert schon - nicht doppelt angelegt."}
    if tmp and tmp.get("pw"):
        d["details"] = dict(d.get("details") or {}, passwortgeschuetzt=True)
    if tmp and os.path.exists(tmp["path"]):
        rel = store_upload(tmp["path"], tmp["name"], {"gehalt": "Gehalt", "anlage": "Anlagen", "eigene_rechnung": "Eigene Rechnungen",
                                                        "einnahme": "Einnahmen"}.get(typ, "Ausgaben"))
        moved.append((os.path.join(DATA_DIR, rel), tmp["path"]))
    elif d.get("file"):
        # v2.1.0: only an existing file inside the data folder (the route took any path, e.g. "..\\..\\Windows\\...")
        f_ = str(d["file"])
        ab_ = os.path.abspath(os.path.join(DATA_DIR, f_))
        if not os.path.isabs(f_) and ab_.startswith(os.path.abspath(DATA_DIR) + os.sep) and os.path.isfile(ab_):
            rel = os.path.relpath(ab_, DATA_DIR)
    if typ == "eigene_rechnung" and d.get("parsed"):
        p = d["parsed"]
        c = q("SELECT * FROM customers WHERE kdnr=?", (p.get("kdnr"),), one=True)
        data = dict(nr=p["nr"], customer_id=c["id"] if c else None, kdnr=p.get("kdnr", ""),
                    addr=p.get("addr") or (address_lines(c) if c else []), datum=p.get("datum"),
                    liefer=p.get("liefer"), auftrag=p.get("auftrag"), titel=p.get("titel", "Rechnung"),
                    toptext=p.get("toptext", ""), foottext=get_settings()["default_foot"], zahlart=p.get("zahlart"),
                    frist=p.get("frist", 7), status=d.get("status") or "bezahlt",
                    bezahlt_am=d.get("bezahlt_am") or p.get("datum"), source="import", items=p["items"],
                    notiz="Importiert aus PDF: " + rel)
        iid, nr = save_invoice(data, bump=False)
        _learn()
        return {"ok": True, "invoice_id": iid, "info": f"Rechnung {nr} ins Archiv übernommen."}
    det = d.get("details") or {}
    if rel.lower().endswith(".xml") and det.get("einvoice"):
        try:
            vp = os.path.join(DATA_DIR, rel[:-4] + "_Ansicht.pdf")
            write_file(vp, einvoice_view_pdf(det["einvoice"]))
            det["xml"] = rel
            rel = os.path.relpath(vp, DATA_DIR)
            d["details"] = det
        except Exception:
            traceback.print_exc()
    bank_row = None
    if typ in ("ausgabe", "einnahme") and float(d.get("betrag") or 0):
        bank_row = q("SELECT id FROM belege WHERE typ=? AND quelle='bank' AND (file IS NULL OR file='') AND abs(betrag-?)<0.01 "
                     "AND julianday(datum) BETWEEN julianday(?)-10 AND julianday(?)+10 LIMIT 1",
                     (typ, float(d.get("betrag") or 0), d.get("datum") or today(), d.get("datum") or today()), one=True)
    bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (typ, d.get("datum") or today(), d.get("partner", ""), d.get("nr", ""), float(d.get("betrag") or 0),
             d.get("kategorie", ""), d.get("notiz", ""), rel, json.dumps(d.get("details") or {}, ensure_ascii=False),
             d.get("invoice_id") or None, d.get("project_id") or None, now_iso()))
    if bank_row:
        # v2.0.6: bank booking keeps its link -> points to the new beleg
        x("UPDATE bank_tx SET beleg_id=? WHERE beleg_id=?", (bid, bank_row["id"]))
        x("DELETE FROM belege WHERE id=?", (bank_row["id"],))
    _learn(bid)
    if typ == "ausgabe" and d.get("als_anlage"):
        b_ = float(d.get("betrag") or 0)
        x("INSERT INTO assets (bezeichnung, kategorie, kaufdatum, betrag, nd_jahre, methode, beleg_id, seriennr, standort, notiz, project_id) "
          "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          (d.get("anlage_name") or d.get("partner") or "Anlagegut", d.get("anlage_kat") or "Sonstiges", d.get("datum") or today(), b_,
           float(d.get("anlage_nd") or 5), "gwg" if gwg_check(b_) else "linear", bid, d.get("anlage_sn", ""), "", d.get("notiz", ""),
           d.get("project_id") or None))
    return {"ok": True, "id": bid, "info": "Mit der Bank-Buchung zusammengeführt (nicht doppelt gezählt)." if bank_row else None}
