# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m44_steuerjahr  v3.1.0
# Steuerjahr - ab v3.1.0 in EINER Datei zusammengefasst aus:
#   m44_steuerbescheid  Steuerbescheid einfuegen, Werte auslesen, uebernehmen
#   m45_jahr            Seite "Jahr bearbeiten"
#   m46_angleich        Jahr an den Bescheid angleichen
# Reihenfolge der Teile = bisherige Lade-Reihenfolge (Verhalten unveraendert).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer


# ============================================================================
# Teil aus m44_steuerbescheid.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m44_steuerbescheid  v1.0.0 (ab Programm v2.6.0)
# Steuerbescheid einfuegen: PDF / Scan / Bild / Text in die Steuerakte legen, die Werte
# (festgesetzte ESt, Soli, KiSt, Lohnsteuer-Abzug, Vorauszahlungen, zvE, Bruttolohn,
# Werbungskosten, Einkuenfte, Erstattung / Nachzahlung, Bescheiddatum, Jahr, kuenftige
# Vorauszahlungen) automatisch erkennen, in einer Vorschau pruefen und in den
# Jahresabschluss uebernehmen. Aenderungsbescheide werden als Verlauf gemerkt.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M44_VERSION = "1.0.0"

# additional fields of the closing (shown automatically in the "Bescheid" block of the tax file)
for _k44, _l44 in (("kist_festgesetzt", "festgesetzte Kirchensteuer"), ("vz_angerechnet", "angerechnete ESt-Vorauszahlungen")):
    if not any(k == _k44 for k, _ in ABSCHLUSS_FELDER):
        ABSCHLUSS_FELDER.append((_k44, _l44))

M44_KEYS = ["est_festgesetzt", "soli_festgesetzt", "kist_festgesetzt", "lst_abzug", "vz_angerechnet", "erstattung",
            "zve", "einkuenfte_gewerbe", "bruttolohn", "wk", "mobilitaet"]
M44_ART = "Einkommensteuerbescheid"

# amounts: 1.234,56 / 1234,56 / 1.234 / 1234 (optionally with minus); no dates, no tax numbers
_M44_AMT = re.compile(r"(?<![\d.,/])(-\s?)?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}|\d+)(?![\d/]|,\d)(\s?-)?")


def _m44_clean(line):
    s = line.replace(" ", " ").replace("−", "-").replace("–", "-")
    s = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", " ", s)                 # dates
    s = re.sub(r"\b\d{2,5}/\d{3,4}/\d{3,5}\b", " ", s)                  # tax number
    s = re.sub(r"\d+(?:,\d+)?\s?%", " ", s)                              # percent
    s = re.sub(r"\b(?:Zeile|Kz|Kennzahl|Anlage|Nr\.?|Seite|§+)\s*\d+[a-z]?\b", " ", s, flags=re.I)
    s = re.sub(r"\b(?:19|20)\d{2}\b(?![.,]\d)", " ", s)                  # years
    return s


def _m44_num(tok):
    neg = bool(tok[0] or tok[2])
    v = float(tok[1].replace(".", "").replace(",", "."))
    return -v if neg else v


def _m44_amounts(line):
    return [_m44_num(m.groups()) for m in _M44_AMT.finditer(_m44_clean(line))]


def _m44_norm(text):
    t = (text or "").replace("\r", "\n").replace(" ", " ").replace("\f", "\n")
    t = t.replace("EUR", " ").replace("€", " ")
    # OCR / extraction variants of umlauts
    rep = {"Solidaritatszuschlag": "Solidaritätszuschlag", "Einkunfte": "Einkünfte", "Mobilitatspramie": "Mobilitätsprämie",
           "Kirchensteuer": "Kirchensteuer", "Betrage": "Beträge", "selbstandiger": "selbständiger", "Einkuenfte": "Einkünfte"}
    for a, b in rep.items():
        t = t.replace(a, b)
    return t


def _m44_lines(text):
    return [re.sub(r"[ \t]+", " ", ln).strip() for ln in _m44_norm(text).split("\n") if ln.strip()]


def _m44_colorder(lines, idx):
    """column order (est, soli, kist) from the nearest header line above the 'festgesetzt' row"""
    for j in range(idx, max(-1, idx - 8), -1):
        h = lines[j]
        pos = {"est": h.find("Einkommensteuer"), "soli": h.find("Solidarit"), "kist": h.find("Kirchensteuer")}
        found = {k: v for k, v in pos.items() if v >= 0}
        if len(found) >= 2:
            return [k for k, _ in sorted(found.items(), key=lambda kv: kv[1])]
    return ["est", "soli", "kist"]


def _m44_row(lines, rx, start=0):
    r = re.compile(rx, re.I)
    for i in range(start, len(lines)):
        if r.search(lines[i]):
            am = _m44_amounts(r.split(lines[i], 1)[-1])
            if not am and i + 1 < len(lines):
                am = _m44_amounts(lines[i + 1])   # values on the next line
            if am:
                return i, am
    return -1, []


def _m44_last(lines, rx, exclude=None):
    r = re.compile(rx, re.I)
    ex = re.compile(exclude, re.I) if exclude else None
    for ln in lines:
        if r.search(ln) and not (ex and ex.search(ln)):
            am = _m44_amounts(r.split(ln, 1)[-1])
            if am:
                return am[-1]
    return None


def m44_parse(text, year_hint=None):
    """-> dict(werte, year, datum, aenderung, vz_folge, gefunden, hinweise)"""
    L = _m44_lines(text)
    full = "\n".join(L)
    w, hinw = {}, []
    # ---- year ----
    year = None
    for rx in (r"(?:Bescheid|Einkommensteuer\w*)\s+(?:für|fuer)\s+(?:das\s+(?:Kalender)?jahr\s+)?((?:19|20)\d{2})",
               r"(?:Veranlagungszeitraum|Kalenderjahr|Steuerjahr|Jahr)\s*:?\s*((?:19|20)\d{2})",
               r"(?:für|fuer)\s+((?:19|20)\d{2})\s+über"):
        m = re.search(rx, full, re.I)
        if m:
            year = int(m.group(1))
            break
    if not year and year_hint:
        year = int(year_hint)
    # ---- date of the notice ----
    datum = ""
    m = re.search(r"(?:Datum|Bescheid\s+vom|Bescheiddatum|Ausfertigungsdatum)\s*:?\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", full, re.I)
    if not m:
        for ln in L[:40]:
            m = re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)", ln)
            if m and not re.search(r"geboren|Geburt|Frist|bis\s+zum|fällig|faellig|Zahlungs", ln, re.I):
                break
            m = None
    if m:
        try:
            datum = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            datum = ""
    aenderung = bool(re.search(r"geändert|geaendert|Änderungsbescheid|Aenderungsbescheid|berichtigt|Berichtigung", full, re.I))
    # ---- assessment table ----
    i, am = -1, []
    for rx_ in (r"festgesetzt\s+werden", r"festgesetzte\s+Steuer", r"^Festsetzung\b"):
        i, am = _m44_row(L, rx_)
        if i >= 0:
            break
    if i >= 0:
        order = _m44_colorder(L, i)
        for k, v in zip(order, am):
            w[{"est": "est_festgesetzt", "soli": "soli_festgesetzt", "kist": "kist_festgesetzt"}[k]] = abs(v)
        j, lam = _m44_row(L, r"(?:Steuerabzug\s+vom\s+Lohn|Lohnsteuer\s*\(?Abzug|einbehaltene\s+Lohnsteuer|anzurechnende\s+Lohnsteuer)", max(0, i - 3))
        if j >= 0:
            w["lst_abzug"] = abs(lam[0])
        j, vam = _m44_row(L, r"(?:ab|abzüglich|anzurechnende)?\s*Vorauszahlungen?\b(?!\s+(?:für|fuer|ab)\s)", max(0, i - 3))
        if j >= 0 and j < i + 12:
            w["vz_angerechnet"] = abs(vam[0])
        j, ram = _m44_row(L, r"verbleibende\s+(?:Beträge|Betraege|Steuer|Beträge)", i)
        if j >= 0:
            w["erstattung"] = round(-sum(ram), 2)
    else:
        for key, rx in (("est_festgesetzt", r"Einkommensteuer\s+(?:wird\s+)?festgesetzt\s+(?:auf|mit)?"),
                        ("soli_festgesetzt", r"Solidaritätszuschlag\s+(?:wird\s+)?festgesetzt\s+(?:auf|mit)?"),
                        ("kist_festgesetzt", r"Kirchensteuer\s+(?:wird\s+)?festgesetzt\s+(?:auf|mit)?")):
            v = _m44_last(L, rx)
            if v is not None:
                w[key] = abs(v)
        v = _m44_last(L, r"Steuerabzug\s+vom\s+Lohn|einbehaltene\s+Lohnsteuer")
        if v is not None:
            w["lst_abzug"] = abs(v)
    # explicit refund / payment sentence wins over the computed remainder
    m = re.search(r"(?:zu\s+erstatten|Erstattung(?:sbetrag)?|erstattet|Guthaben)[^\n\d-]{0,60}?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", full, re.I)
    m2 = re.search(r"(?:Nachzahlung|nachzuzahlen|zu\s+zahlen|bitte\s+zahlen\s+sie|Zahlungsbetrag|Abschlusszahlung)[^\n\d-]{0,60}?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", full, re.I)
    if not m:
        m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*(?:wird|werden)\s+(?:Ihnen\s+)?erstattet", full, re.I)
    if not m2:
        m2 = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*(?:sind|ist)\s+(?:noch\s+)?(?:nachzuzahlen|zu\s+zahlen)", full, re.I)
    if m and (not m2 or m.start() < m2.start()):
        w["erstattung"] = abs(_m44_num((None, m.group(1), None)))
    elif m2:
        w["erstattung"] = -abs(_m44_num((None, m2.group(1), None)))
    # ---- calculation part ----
    for key, rx, ex in (("zve", r"zu\s+versteuerndes\s+Einkommen", None),
                        ("bruttolohn", r"Bruttoarbeitslohn|steuerpflichtiger\s+Arbeitslohn|\bArbeitslohn\b", r"Versorgung"),
                        ("wk", r"Werbungskosten|Arbeitnehmer-?\s?Pauschbetrag", r"Sonderausgaben"),
                        ("mobilitaet", r"Mobilitätsprämie|Mobilitaetspraemie", None)):
        v = _m44_last(L, rx, ex)
        if v is not None:
            w[key] = abs(v) if key != "zve" else v
    ein = 0.0
    hit = False
    for rx in (r"(?:Einkünfte|Gewinn)\s+aus\s+Gewerbebetrieb", r"(?:Einkünfte|Gewinn)\s+aus\s+selbständiger\s+Arbeit"):
        v = _m44_last(L, rx)
        if v is not None:
            ein += v
            hit = True
    if hit:
        w["einkuenfte_gewerbe"] = round(ein, 2)
    # plausibility: refund missing -> compute from the table
    if "erstattung" not in w and "est_festgesetzt" in w and ("lst_abzug" in w or "vz_angerechnet" in w):
        soll = w["est_festgesetzt"] + w.get("soli_festgesetzt", 0) + w.get("kist_festgesetzt", 0)
        w["erstattung"] = round(w.get("lst_abzug", 0) + w.get("vz_angerechnet", 0) - soll, 2)
        hinw.append("Erstattung / Nachzahlung wurde aus festgesetzter Steuer minus Abzügen berechnet (im Bescheid nicht gefunden).")
    # ---- future prepayments ----
    vz = None
    for k_, ln in enumerate(L):
        if re.search(r"Vorauszahlung", ln, re.I):
            blk = " ".join(L[k_:k_ + 8])
            my = re.search(r"(?:ab|für|fuer|Kalenderjahr)\s+((?:19|20)\d{2})", blk, re.I)
            if not my or (year and int(my.group(1)) <= year):
                continue
            mj = re.search(r"Jahresbetrag\D{0,30}?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", blk, re.I)
            mq = re.search(r"(?:vierteljährlich|vierteljaehrlich|je\s+Quartal|jeweils|je)\D{0,30}?(\d{1,3}(?:\.\d{3})*,\d{2})", blk, re.I)
            if mj:
                vz = {"year": int(my.group(1)), "betrag": abs(_m44_num((None, mj.group(1), None)))}
            elif mq:
                vz = {"year": int(my.group(1)), "betrag": round(4 * abs(_m44_num((None, mq.group(1), None))), 2)}
            if vz:
                break
    for k in list(w):
        w[k] = round(float(w[k]), 2)
    gef = [k for k in M44_KEYS if k in w]
    if not gef:
        hinw.append("Im Dokument wurden keine Bescheid-Werte erkannt - bitte die Werte von Hand eintragen.")
    return {"werte": w, "year": year, "datum": datum, "aenderung": aenderung, "vz_folge": vz, "gefunden": gef, "hinweise": hinw}


def m44_text(path, filename):
    """text of the notice; scans and images via OCR when available -> (text, ocr_used)"""
    t = ""
    try:
        t, _used, _fmt = extract_text_any(path, filename)
    except Exception as e:
        if type(e).__name__ == "PasswordNeeded":
            raise
        traceback.print_exc()
    if len(re.sub(r"\s", "", t or "")) < 80:
        try:
            if ocr_available():
                # v2.6.7: a notice has many pages - the values are often on page 3 to 6 (before: only 3 pages were read)
                t_ = ocr_file(path, max_pages=12)
                if len(t_.strip()) > len((t or "").strip()):
                    return t_, True
        except Exception:
            traceback.print_exc()
    return t or "", False


def _m44_labels():
    return {k: l for k, l in ABSCHLUSS_FELDER}


def m44_result(year_hint, rel, doc_id, filename=""):
    fp = os.path.join(DATA_DIR, rel)
    try:
        text, ocr = m44_text(fp, filename or rel)
    except Exception as e:
        if type(e).__name__ == "PasswordNeeded":
            return {"ok": True, "id": doc_id, "year": year_hint, "werte": {}, "gefunden": [], "passwort": True,
                    "hinweise": ["Die PDF ist mit einem Passwort geschützt, das Standard-Passwort passt nicht. Werte bitte von Hand eintragen."]}
        raise
    p = m44_parse(text, year_hint)
    year = int(p["year"] or year_hint)
    if not text.strip():
        p["hinweise"].append("Aus der Datei konnte kein Text gelesen werden" + (
            (" – Texterkennung fehlgeschlagen: " + OCR_LAST["fehler"]) if OCR_LAST.get("fehler") else
            ("" if ocr_available() else " (Scan/Bild – Texterkennung gibt es nur unter Windows)")) + ".")
    ab = tax_inputs(year).get("abschluss") or {}
    return {"ok": True, "id": doc_id, "year": year, "year_hint": int(year_hint), "werte": p["werte"], "gefunden": p["gefunden"],
            "datum": p["datum"], "aenderung": p["aenderung"], "vz_folge": p["vz_folge"], "hinweise": p["hinweise"], "ocr": ocr,
            "bisher": {k: ab.get(k) for k in M44_KEYS}, "bisher_datum": ab.get("bescheid_datum") or "",
            "abgeschlossen": bool(ab.get("abgeschlossen")), "programm": abschluss_programm(year),
            "labels": _m44_labels(), "keys": M44_KEYS,
            "vz_aktuell": float(tax_inputs(p["vz_folge"]["year"]).get("vorauszahlung") or 0) if p["vz_folge"] else None}


def _m44_upload(h, tmp, name):
    hint = int(h.headers.get("X-Year") or datetime.date.today().year)
    # read once to find the real year of the notice, then file it under that year
    try:
        text, _ocr = m44_text(tmp, name)
        py = m44_parse(text, hint)["year"] or hint
    except Exception:
        py = hint
    py = int(py)
    aid = steuerakte_add(py, tmp, name, M44_ART, f"{M44_ART} {py}")
    row = q("SELECT * FROM steuerakte WHERE id=?", (aid,), one=True)
    res = m44_result(py, row["file"], aid, name)
    if res.get("datum"):
        x("UPDATE steuerakte SET datum=?, titel=? WHERE id=?",
          (res["datum"], f"{M44_ART} {py}" + (" (Änderung)" if res.get("aenderung") else ""), aid))
    return h._send(200, res)


def _m44_reparse(h, d):
    row = q("SELECT * FROM steuerakte WHERE id=?", (int(d["id"]),), one=True)
    if not row or not row["file"]:
        raise ValueError("Unterlage nicht gefunden.")
    return h._send(200, m44_result(int(row["year"]), row["file"], row["id"], row["file"]))


def m44_apply(d):
    year = int(d["year"])
    werte = {}
    for k, v in (d.get("werte") or {}).items():
        if k in M44_KEYS:
            werte[k] = None if v in (None, "") else round(float(v), 2)
    data = dict(werte)
    if d.get("bescheid_datum"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["bescheid_datum"]):
            raise ValueError("Ungültiges Bescheiddatum.")
        data["bescheid_datum"] = d["bescheid_datum"]
    ab0 = tax_inputs(year).get("abschluss") or {}
    if d.get("abgeschlossen") is not None:
        data["abgeschlossen"] = bool(d["abgeschlossen"])
        if data["abgeschlossen"] and not ab0.get("abgeschlossen"):
            data["abgeschlossen_am"] = today()
    # history: every applied notice (original + amendments) stays visible
    hist = list(ab0.get("bescheide") or [])
    hist.append({"datum": data.get("bescheid_datum") or "", "doc_id": d.get("id"), "aenderung": bool(d.get("aenderung")),
                 "werte": {k: v for k, v in werte.items() if v is not None}, "uebernommen": now_iso()})
    data["bescheide"] = hist[-20:]
    ab = abschluss_save(year, data)
    info = [f"{len([v for v in werte.values() if v is not None])} Werte in den Jahresabschluss {year} übernommen"]
    vz = d.get("vz_folge")
    if vz and vz.get("year") and vz.get("betrag") is not None:
        vy = int(vz["year"])
        r_ = q("SELECT data FROM taxyear WHERE year=?", (vy,), one=True)
        cur = json.loads(r_["data"]) if r_ else {}
        cur["vorauszahlung"] = round(float(vz["betrag"]), 2)
        x("INSERT OR REPLACE INTO taxyear (year, data) VALUES (?,?)", (vy, json.dumps(cur, ensure_ascii=False)))
        info.append(f"ESt-Vorauszahlungen {vy}: {money(cur['vorauszahlung'])} eingetragen")
    return {"ok": True, "abschluss": ab, "info": " · ".join(info)}


HOOK_UPLOAD["/api/upload/m44bescheid"] = _m44_upload
HOOK_POST["/api/m44/reparse"] = _m44_reparse
HOOK_POST["/api/m44/apply"] = lambda h, d: h._send(200, m44_apply(d))


M44_SAMPLE = """Finanzamt Köln-Ost                                   Datum 12.06.2025
Steuernummer 218/5123/4567
Bescheid für 2024
über Einkommensteuer, Solidaritätszuschlag und Kirchensteuer
Festsetzung                         Einkommensteuer   Solidaritätszuschlag   Kirchensteuer r.k.
festgesetzt werden                     8.412,00 €            0,00 €            0,00 €
ab Steuerabzug vom Lohn                7.950,00 €            0,00 €            0,00 €
ab Vorauszahlungen                     1.200,00 €            0,00 €            0,00 €
verbleibende Beträge                    -738,00 €            0,00 €            0,00 €
Der Betrag von 738,00 € wird erstattet.
Berechnungsgrundlagen
Einkünfte aus Gewerbebetrieb                                   14.230
Bruttoarbeitslohn                                              38.500
Werbungskosten                                                 -2.140
zu versteuerndes Einkommen                                     41.876
Vorauszahlungen
Die Vorauszahlungen ab 2025 werden festgesetzt: vierteljährlich je 300,00 € zum 10.03., 10.06., 10.09., 10.12.
"""


def m44_selftest():
    err = []
    try:
        p = m44_parse(M44_SAMPLE)
        w = p["werte"]
        exp = {"est_festgesetzt": 8412.0, "soli_festgesetzt": 0.0, "lst_abzug": 7950.0, "vz_angerechnet": 1200.0, "erstattung": 738.0,
               "einkuenfte_gewerbe": 14230.0, "bruttolohn": 38500.0, "wk": 2140.0, "zve": 41876.0}
        for k, v in exp.items():
            if abs(float(w.get(k, -999999)) - v) > 0.005:
                err.append(f"m44: {k} erkannt {w.get(k)} statt {v}")
        if p["year"] != 2024:
            err.append(f"m44: Jahr {p['year']} statt 2024")
        if p["datum"] != "2025-06-12":
            err.append(f"m44: Datum {p['datum']} statt 2025-06-12")
        if not p["vz_folge"] or p["vz_folge"]["year"] != 2025 or abs(p["vz_folge"]["betrag"] - 1200) > 0.01:
            err.append(f"m44: Vorauszahlung Folgejahr {p['vz_folge']}")
        p2 = m44_parse(M44_SAMPLE.replace("Der Betrag von 738,00 € wird erstattet.", "Bitte zahlen Sie 412,50 € bis zum 15.07.2025."))
        if abs(p2["werte"].get("erstattung", 0) + 412.5) > 0.005:
            err.append(f"m44: Nachzahlung {p2['werte'].get('erstattung')} statt -412,50")
    except Exception as e:
        err.append(f"m44 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m44_selftest)
print(f"INIT m44_steuerbescheid v{M44_VERSION}")


# ============================================================================
# Teil aus m45_jahr.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m45_jahr  v1.0.1 (ab Programm v2.6.0; v1.0.1 in v2.6.2: Belege mit Text-Details)
# Seite "Jahr bearbeiten": alles eines Jahres an einer Stelle - Rechnungen (Zahlstatus / Zahldatum),
# Ausgaben, sonstige Einnahmen, Gehalt (direkt in der Tabelle bearbeiten, neu anlegen, loeschen),
# Steuer-Angaben, Steuerbescheid & Jahresabschluss, Vollstaendigkeits-Pruefung.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M45_VERSION = "1.0.1"
M45_TYPEN = ("ausgabe", "einnahme", "gehalt", "anlage")
M45_FIELDS = ("typ", "datum", "partner", "nr", "betrag", "kategorie", "notiz")


def _m45_det(raw):
    """v1.0.1: details of a receipt as dict - older imports stored plain text or lists there"""
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        if isinstance(v, str):          # double-encoded JSON
            v = json.loads(v)
    except Exception:
        return {}
    return v if isinstance(v, dict) else {}


def _m45_date(s, year=None):
    s = (s or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise ValueError(f"Ungültiges Datum: {s or '(leer)'}")
    datetime.date.fromisoformat(s)
    return s


def m45_pruefung(year, inv, bel, ab):
    """completeness check of one year -> list of {stufe, text, tab}"""
    out = []
    add = lambda st, t, tab: out.append({"stufe": st, "text": t, "tab": tab})
    ys = str(year)
    rech = [i for i in inv if i["typ"] in ("rechnung", "storno") and i["datum"][:4] == ys]
    off = [i for i in rech if i["status"] == "offen"]
    ent = [i for i in rech if i["status"] == "entwurf"]
    ohne = [i for i in rech if i["status"] == "bezahlt" and not i["bezahlt_am"]]
    if off:
        add("hinweis", f"{len(off)} Rechnung(en) {year} noch offen ({money(sum(i['summe'] or 0 for i in off))}) - zählen erst bei Zahlung.", "re")
    if ent:
        add("hinweis", f"{len(ent)} Entwurf/Entwürfe mit Datum {year} - nicht fertiggestellt.", "re")
    if ohne:
        add("warnung", f"{len(ohne)} bezahlte Rechnung(en) ohne Zahldatum - Zuflussjahr unklar.", "re")
    aus = [b for b in bel if b["typ"] == "ausgabe"]
    ok_ = [b for b in aus if not (b["kategorie"] or "").strip()]
    if ok_:
        add("warnung", f"{len(ok_)} Ausgabe(n) ohne EÜR-Kategorie (zählen als „Sonstige Betriebsausgaben“).", "aus")
    null = [b for b in bel if not b["betrag"] and b["typ"] in ("ausgabe", "einnahme", "gehalt")]
    if null:
        add("warnung", f"{len(null)} Beleg(e) mit Betrag 0,00.", "aus")
    nofile = [b for b in aus if not b["file"] and not (b["partner"] or "").startswith(KORR_PARTNER)]
    if nofile:
        add("hinweis", f"{len(nofile)} Ausgabe(n) ohne Belegdatei (GoBD: Beleg aufbewahren).", "aus")
    geh = [b for b in bel if b["typ"] == "gehalt"]
    if geh:
        has_cert = any("lohnsteuerbescheinigung" in ((b["notiz"] or "") + (b["nr"] or "") + (b["details"] or "")).lower() for b in geh)
        mon = {b["datum"][5:7] for b in geh if b["datum"]}
        mk = ("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")
        fehlt = [mk[m - 1] for m in range(1, 13) if f"{m:02d}" not in mon]
        if fehlt and not has_cert and int(year) < datetime.date.today().year:
            add("hinweis", f"Gehaltsabrechnungen fehlen für: {', '.join(fehlt)} (oder Lohnsteuerbescheinigung einfügen).", "geh")
    if not ab.get("bescheid_datum") and int(year) < datetime.date.today().year:
        add("hinweis", f"Für {year} ist noch kein Steuerbescheid eingetragen.", "abs")
    if ab.get("abgeschlossen"):
        add("info", f"Das Jahr {year} ist als abgeschlossen markiert - Änderungen verändern den abgestimmten Stand.", "abs")
    return out


def _m45_angleich_hint(year):
    """v2.6.1: open differences to the tax notice (module m46)"""
    try:
        if "m46_plan" in globals():
            n = m46_plan(year)["offen"]
            if n:
                return [{"stufe": "warnung", "text": f"{n} Abweichung(en) zum Steuerbescheid {year} - im Reiter „Bescheid & Abschluss“ mit „An Bescheid angleichen“ beheben.", "tab": "abs"}]
    except Exception:
        traceback.print_exc()
    return []


def m45_data(year):
    year = int(year)
    ys = str(year)
    inv = q("SELECT i.id, i.nr, i.typ, i.datum, i.kdnr, i.customer_id, i.titel, i.summe, i.status, i.bezahlt_am, i.frist, i.locked, "
            "COALESCE(c.firma, c.name, i.kdnr) kunde FROM invoices i LEFT JOIN customers c ON c.id=i.customer_id "
            "WHERE i.typ IN ('rechnung','storno') AND (substr(i.datum,1,4)=? OR substr(COALESCE(i.bezahlt_am,''),1,4)=?) "
            "ORDER BY i.datum, i.nr", (ys, ys))
    for i in inv:
        i["zufluss"] = None
        if i["status"] == "bezahlt":
            try:
                zy, ten = zufluss_year(i)
                i["zufluss"], i["zehn_tage"] = zy, ten
            except Exception:
                i["zufluss"] = int((i["bezahlt_am"] or i["datum"])[:4])
    bel = q("SELECT id, typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id, created "
            "FROM belege WHERE substr(datum,1,4)=? AND typ IN ('ausgabe','einnahme','gehalt','anlage') ORDER BY datum, id", (ys,))
    for b in bel:
        dd = _m45_det(b["details"])
        b["korrektur"] = bool(dd.get("korrektur"))
        if b["typ"] == "gehalt":
            b["brutto"] = dd.get("brutto")
            b["netto"] = dd.get("netto")
            b["lst"] = dd.get("lst")
    ti = tax_inputs(year)
    ab = ti.get("abschluss") or {}
    e = euer(year)
    tc = tax_calc(year)
    return {"year": year, "rechnungen": inv, "belege": bel, "inputs": {k: v for k, v in ti.items() if k != "abschluss"},
            "abschluss": {k: v for k, v in ab.items() if k != "bescheide"}, "bescheide": ab.get("bescheide") or [],
            "euer": {k: v for k, v in e.items() if not k.endswith("_list")}, "calc": tc.get("calc"), "gehalt": tc.get("gehalt"),
            "differenz": tc.get("differenz"), "bereits_gezahlt": tc.get("bereits_gezahlt"),
            "kategorien": EUER_KATEGORIEN, "pruefung": m45_pruefung(year, inv, bel, ab) + _m45_angleich_hint(year),
            "akte": q("SELECT COUNT(*) n FROM steuerakte WHERE year=?", (year,), one=True)["n"]}


def m45_belege_save(d):
    rows = d.get("rows") or []
    done, errs = 0, []
    for r in rows:
        try:
            bid = int(r["id"])
            cur = q("SELECT * FROM belege WHERE id=?", (bid,), one=True)
            if not cur:
                raise ValueError("nicht gefunden")
            new = {k: cur[k] for k in M45_FIELDS}
            for k in M45_FIELDS:
                if k in r:
                    new[k] = r[k]
            new["datum"] = _m45_date(new["datum"])
            new["betrag"] = round(float(new["betrag"] or 0), 2)
            if new["typ"] not in M45_TYPEN:
                raise ValueError("unbekannte Art")
            if new["typ"] == "anlage" or cur["typ"] == "anlage":
                il = q("SELECT locked FROM invoices WHERE id=?", (cur["invoice_id"],), one=True) if cur["invoice_id"] else None
                if il and il["locked"] and new["typ"] != cur["typ"]:
                    raise ValueError("Anlage einer festgeschriebenen Rechnung")
            x("UPDATE belege SET typ=?, datum=?, partner=?, nr=?, betrag=?, kategorie=?, notiz=? WHERE id=?",
              (new["typ"], new["datum"], new["partner"] or "", new["nr"] or "", new["betrag"], new["kategorie"] or "", new["notiz"] or "", bid))
            done += 1
            try:
                learn_correction(dict(cur, **new, details=_m45_det(cur["details"])))
            except Exception:
                pass
        except Exception as e:
            errs.append(f"Beleg {r.get('id')}: {e}")
    return {"ok": True, "done": done, "errors": errs}


def m45_beleg_neu(d):
    typ = d.get("typ") or "ausgabe"
    if typ not in ("ausgabe", "einnahme", "gehalt"):
        raise ValueError("Unbekannte Art.")
    datum = _m45_date(d.get("datum"))
    det = {"manuell": True}
    if typ == "gehalt":
        b = round(float(d.get("betrag") or 0), 2)
        det.update({"brutto": float(d.get("brutto") or 0) or None, "netto": b})
    bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (typ, datum, (d.get("partner") or "").strip(), (d.get("nr") or "").strip(), round(float(d.get("betrag") or 0), 2),
             (d.get("kategorie") or "") if typ == "ausgabe" else (d.get("kategorie") or ""), (d.get("notiz") or "").strip(), "",
             json.dumps(det, ensure_ascii=False), None, None, now_iso()))
    return {"ok": True, "id": bid}


def m45_rechnungen_save(d):
    done, errs = 0, []
    for r in d.get("rows") or []:
        try:
            i = q("SELECT id, status, typ FROM invoices WHERE id=?", (int(r["id"]),), one=True)
            if not i:
                raise ValueError("nicht gefunden")
            st = r.get("status") or i["status"]
            if st not in ("offen", "bezahlt"):
                raise ValueError("nur offen / bezahlt möglich")
            if i["status"] in ("entwurf", "storniert"):
                raise ValueError(f"Status {i['status']} bleibt unverändert")
            if st == "bezahlt" and not (r.get("bezahlt_am") or "").strip():
                raise ValueError("Zahldatum fehlt (bestimmt das Steuerjahr)")
            bz = _m45_date(r.get("bezahlt_am")) if st == "bezahlt" else ""
            x("UPDATE invoices SET status=?, bezahlt_am=?, updated=? WHERE id=?", (st, bz, now_iso(), i["id"]))
            if st == "bezahlt":
                lock_invoice(i["id"])
            done += 1
        except Exception as e:
            errs.append(f"Rechnung {r.get('id')}: {e}")
    return {"ok": True, "done": done, "errors": errs}


HOOK_GET["/api/m45/jahr"] = lambda h, qs: h._send(200, m45_data(int(qs.get("year") or datetime.date.today().year)))
HOOK_POST["/api/m45/belege_save"] = lambda h, d: h._send(200, m45_belege_save(d))
HOOK_POST["/api/m45/beleg_neu"] = lambda h, d: h._send(200, m45_beleg_neu(d))
HOOK_POST["/api/m45/rechnungen_save"] = lambda h, d: h._send(200, m45_rechnungen_save(d))


def m45_selftest():
    err = []
    try:
        y = datetime.date.today().year - 1
        dd = m45_data(y)
        for k in ("rechnungen", "belege", "inputs", "euer", "pruefung"):
            if k not in dd:
                err.append(f"m45: Feld {k} fehlt")
        if _m45_det('"nur Text"') != {} or _m45_det("[1,2]") != {} or _m45_det('{"a": 1}') != {"a": 1}:
            err.append("m45: Beleg-Details mit Text/Liste nicht abgefangen")
        try:
            _m45_date("2025-02-30")
            err.append("m45: ungültiges Datum akzeptiert")
        except ValueError:
            pass
    except Exception as e:
        err.append(f"m45 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m45_selftest)
print(f"INIT m45_jahr v{M45_VERSION}")


# ============================================================================
# Teil aus m46_angleich.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m46_angleich  v1.0.0 (ab Programm v2.6.1)
# Jahr an den Steuerbescheid angleichen: alle Abweichungen Programm <-> Bescheid in einer Liste,
# mit einem Klick buchen:
#   - Gewinn / Einnahmen / Ausgaben  -> Korrekturbuchung (wie "Korrigieren")
#   - Bruttolohn / Lohnsteuer          -> Korrektureintrag Gehalt (Jahreswert)
#   - Werbungskosten                   -> Angabe "Werbungskosten tatsaechlich"
#   - ESt-Vorauszahlungen              -> Angabe Vorauszahlungen
#   - zu versteuerndes Einkommen       -> Abgleich-Betrag (Vorsorge/Sonderausgaben lt. Finanzamt)
#   - ESt, Soli, KiSt, Erstattung      -> Werte lt. Bescheid verwenden (Steuerberechnung, Kacheln, Jahresbericht)
# Alles einzeln zuruecknehmbar. Wird vom Programmkern in dessen Namensraum geladen.
# Autor: T. Pfeiffer

M46_VERSION = "1.0.0"


# ---------------- Steuerberechnung: zvE-Abgleich + Werte lt. Bescheid ----------------
@chain_step("tax_core", "m44_steuerjahr")
def _m46_step_tax_core(_next, year, gewinn, sal, t, wk_real):
    """zvE-Abgleich (Differenz Vorsorge/Sonderausgaben lt. Finanzamt) fliesst wie sonstige Einkuenfte ein"""
    ab_ = float(t.get("zve_abgleich") or 0)
    if ab_:
        t = dict(t)
        t["sonstige"] = float(t.get("sonstige") or 0) + ab_
    return _next(year, gewinn, sal, t, wk_real)


_m46_orig_tax_calc = chain_inner("tax_calc", "m44_steuerjahr")   # v3.1.0: the level below this module
def _m46_num(v):
    return None if v in (None, "") else float(v)


@chain_step("tax_calc", "m44_steuerjahr")
def _m46_step_tax_calc(_next, year):
    r = _next(year)
    try:
        for a_ in r.get("arbeitgeber") or []:
            if (a_.get("name") or "").startswith(KORR_PARTNER):
                a_["quelle"] = "Korrektur (Abgleich mit Bescheid)"
        ab = (r.get("inputs") or {}).get("abschluss") or {}
        r["calc_programm"] = dict(r["calc"])
        r["differenz_programm"] = r.get("differenz")
        if ab.get("bescheid_steuer") and _m46_num(ab.get("est_festgesetzt")) is not None:
            c = dict(r["calc"])
            for k, bk in (("est", "est_festgesetzt"), ("soli", "soli_festgesetzt"), ("kist", "kist_festgesetzt"), ("zve", "zve")):
                v = _m46_num(ab.get(bk))
                if v is not None:
                    c[k] = round(v, 2)
            c["gesamt"] = round(c["est"] + c["soli"] + c["kist"], 2)
            c["lt_bescheid"] = True
            r["calc"] = c
            er = _m46_num(ab.get("erstattung"))
            r["differenz"] = round(-er, 2) if er is not None else round(c["gesamt"] - r["bereits_gezahlt"], 2)
            r["bereits_gezahlt"] = round(c["gesamt"] - r["differenz"], 2)
            r["lt_bescheid"] = True
            r["tarif_hinweis"] = (f"Steuer {year} laut Bescheid" + (f" vom {de_date(ab['bescheid_datum'])}" if ab.get("bescheid_datum") else "") +
                                  " – Einkommensteuer, Soli, Kirchensteuer und Erstattung/Nachzahlung sind die festgesetzten Werte.")
    except Exception:
        traceback.print_exc()
    return r


# ---------------- Plan ----------------
def _m46_row(key, label, prog, soll, aktion, art, tol=0.5):
    diff = None if soll is None else round(soll - prog, 2)
    ok = soll is not None and abs(diff) < tol
    return {"key": key, "label": label, "programm": round(prog, 2), "bescheid": soll, "diff": diff, "ok": ok,
            "aktion": aktion, "art": art, "aktiv": soll is not None and not ok}


def m46_plan(year):
    year = int(year)
    t = tax_inputs(year)
    ab = t.get("abschluss") or {}
    tc = _m46_orig_tax_calc(year)
    e = tc["euer"]
    g = tc["gehalt"]
    c = tc["calc"]
    rows = []
    ein_s, aus_s = _m46_num(ab.get("eur_einnahmen")), _m46_num(ab.get("eur_ausgaben"))
    d_ein = d_aus = 0.0
    if ein_s is not None:
        rows.append(_m46_row("einnahmen", "Betriebseinnahmen (lt. Erklärung)", e["einnahmen"], ein_s, "Korrekturbuchung Einnahme", "buchung"))
        d_ein = rows[-1]["diff"] or 0.0
    if aus_s is not None:
        rows.append(_m46_row("ausgaben", "Betriebsausgaben (lt. Erklärung)", e["ausgaben"], aus_s, "Korrekturbeleg Ausgabe", "buchung"))
        d_aus = rows[-1]["diff"] or 0.0
    g_soll = _m46_num(ab.get("einkuenfte_gewerbe"))
    g_lbl = "Gewinn / Einkünfte Gewerbe (lt. Bescheid)"
    if g_soll is None:
        g_soll, g_lbl = _m46_num(ab.get("eur_gewinn")), "Gewinn (lt. Erklärung)"
    if g_soll is not None:
        prog_g = round(e["gewinn"] + d_ein - d_aus, 2)       # after the corrections above
        rows.append(_m46_row("gewinn", g_lbl, prog_g, g_soll, "Korrekturbuchung (Einnahme oder Ausgabe)", "buchung"))
    for key, lbl, prog in (("bruttolohn", "Bruttoarbeitslohn", g["brutto"]), ("lst_abzug", "Lohnsteuer (Abzug vom Lohn)", g["lst"])):
        soll = _m46_num(ab.get(key))
        if soll is not None:
            rows.append(_m46_row(key, lbl, prog, soll, "Korrektureintrag Gehalt (Jahreswert)", "buchung"))
    wk_s = _m46_num(ab.get("wk"))
    if wk_s is not None:
        prog = max(tc["wk_pauschale"], tc["wk_real"])
        r_ = _m46_row("wk", "Werbungskosten", prog, wk_s, "Angabe „Werbungskosten tatsächlich“ anpassen", "angabe")
        if not r_["ok"]:
            # target for the actual costs: bescheid value, or at most the lump sum when the office granted only that
            ziel = wk_s if wk_s > tc["wk_pauschale"] + 0.005 else min(tc["wk_real"], tc["wk_pauschale"])
            r_["wk_diff"] = round(ziel - tc["wk_real"], 2)
            if abs(r_["wk_diff"]) < 0.005:
                r_["ok"], r_["aktiv"] = True, False
        rows.append(r_)
    vz_s = _m46_num(ab.get("vz_angerechnet"))
    if vz_s is not None:
        rows.append(_m46_row("vorauszahlung", "ESt-Vorauszahlungen", float(t.get("vorauszahlung") or 0), vz_s, "Angabe Vorauszahlungen setzen", "angabe", 0.005))
    zve_s = _m46_num(ab.get("zve"))
    if zve_s is not None:
        r_ = _m46_row("zve", "zu versteuerndes Einkommen", c["zve"], zve_s, "Abgleich-Betrag (Vorsorge/Sonderausgaben lt. Finanzamt)", "abgleich", 1.0)
        r_["hinweis"] = "wird nach den Buchungen oben neu berechnet"
        r_["abgleich_bisher"] = float(t.get("zve_abgleich") or 0)
        rows.append(r_)
    est_s = _m46_num(ab.get("est_festgesetzt"))
    if est_s is not None:
        for key, lbl, prog, bk in (("est", "Einkommensteuer", c["est"], "est_festgesetzt"), ("soli", "Solidaritätszuschlag", c["soli"], "soli_festgesetzt"),
                                   ("kist", "Kirchensteuer", c["kist"], "kist_festgesetzt")):
            soll = _m46_num(ab.get(bk))
            if soll is not None:
                rows.append(_m46_row(key, lbl, prog, soll, "Wert lt. Bescheid verwenden", "steuer"))
        er = _m46_num(ab.get("erstattung"))
        if er is not None:
            rows.append(_m46_row("erstattung", "Erstattung (+) / Nachzahlung (−)", -tc["differenz"], er, "Wert lt. Bescheid verwenden", "steuer"))
        if ab.get("bescheid_steuer"):
            for r_ in rows:
                if r_["art"] == "steuer" and not r_["ok"]:
                    r_["ok"], r_["aktiv"], r_["fix"] = True, False, True
    offen = [r_ for r_ in rows if r_["aktiv"]]
    return {"year": year, "rows": rows, "offen": len(offen), "kategorien": EUER_KATEGORIEN,
            "bescheid": bool(ab.get("bescheid_datum") or est_s is not None), "bescheid_datum": ab.get("bescheid_datum") or "",
            "steuer_fix": bool(ab.get("bescheid_steuer")), "zve_abgleich": float(t.get("zve_abgleich") or 0),
            "hinweis": "" if rows else f"Für {year} sind noch keine Werte aus Bescheid oder Erklärung eingetragen."}


def _m46_set_input(year, key, val):
    r = q("SELECT data FROM taxyear WHERE year=?", (year,), one=True)
    dd = json.loads(r["data"]) if r else {}
    dd[key] = val
    x("INSERT OR REPLACE INTO taxyear (year, data) VALUES (?,?)", (year, json.dumps(dd, ensure_ascii=False)))


def m46_apply(d):
    year = int(d["year"])
    keys = set(d.get("keys") or [])
    datum = d.get("datum") or f"{year}-12-31"
    notiz = (d.get("notiz") or "").strip() or f"Angleichung an Steuerbescheid {year}"
    info, err = [], []
    plan = {r_["key"]: r_ for r_ in m46_plan(year)["rows"]}

    def book(feld, betrag, **kw):
        try:
            res = korr_book(dict({"year": year, "feld": feld, "betrag": betrag, "datum": datum, "notiz": notiz}, **kw))
            info.append(res.get("info") or feld)
        except Exception as ex:
            err.append(f"{feld}: {ex}")

    # 1. bookings (order matters: einnahmen/ausgaben before gewinn)
    for k in ("einnahmen", "ausgaben"):
        r_ = plan.get(k)
        if k in keys and r_ and not r_["ok"]:
            book(k, r_["diff"], kategorie=d.get("kategorie"))
    if "gewinn" in keys:
        r_ = m46_plan(year)
        g = next((x_ for x_ in r_["rows"] if x_["key"] == "gewinn"), None)
        if g and not g["ok"]:
            book("gewinn", g["diff"], via=d.get("gewinn_via") or "einnahmen", kategorie=d.get("kategorie"))
    for k in ("bruttolohn", "lst_abzug"):
        r_ = plan.get(k)
        if k in keys and r_ and not r_["ok"]:
            book(k, r_["diff"])
    r_ = plan.get("wk")
    if "wk" in keys and r_ and not r_["ok"] and abs(r_.get("wk_diff") or 0) >= 0.005:
        book("wk", r_["wk_diff"])
    r_ = plan.get("vorauszahlung")
    if "vorauszahlung" in keys and r_ and not r_["ok"]:
        _m46_set_input(year, "vorauszahlung", round(r_["bescheid"], 2))
        info.append(f"ESt-Vorauszahlungen {year} auf {money(r_['bescheid'])} gesetzt.")
    # 2. zvE: recompute after the bookings, converge in up to 3 steps (rounding to full euros)
    if "zve" in keys and plan.get("zve") and plan["zve"]["bescheid"] is not None:
        soll = plan["zve"]["bescheid"]
        for _ in range(3):
            t = tax_inputs(year)
            cur = _m46_orig_tax_calc(year)["calc"]["zve"]
            diff = round(soll - cur, 2)
            if abs(diff) < 1.0:
                break
            _m46_set_input(year, "zve_abgleich", round(float(t.get("zve_abgleich") or 0) + diff, 2))
        neu = float(tax_inputs(year).get("zve_abgleich") or 0)
        info.append(f"zvE-Abgleich {year}: {money(neu)} (Vorsorge/Sonderausgaben lt. Finanzamt).")
    # 3. tax values lt. Bescheid
    if keys & {"est", "soli", "kist", "erstattung"}:
        abschluss_save(year, {"bescheid_steuer": True})
        info.append("Einkommensteuer, Soli, Kirchensteuer und Erstattung/Nachzahlung laut Bescheid werden verwendet.")
    abschluss_save(year, {"angeglichen_am": now_iso()})
    p = m46_plan(year)
    return {"ok": True, "info": info, "errors": err, "plan": p}


def m46_reset(d):
    """take back the zvE adjustment and/or the tax values lt. Bescheid (bookings: list of corrections)"""
    year = int(d["year"])
    out = []
    if d.get("zve", True):
        _m46_set_input(year, "zve_abgleich", 0.0)
        out.append("zvE-Abgleich entfernt")
    if d.get("steuer", True):
        abschluss_save(year, {"bescheid_steuer": False})
        out.append("Steuer wieder nach Programmberechnung")
    return {"ok": True, "info": " · ".join(out), "plan": m46_plan(year)}


HOOK_GET["/api/m46/plan"] = lambda h, qs: h._send(200, m46_plan(int(qs.get("year") or datetime.date.today().year - 1)))
HOOK_POST["/api/m46/apply"] = lambda h, d: h._send(200, m46_apply(d))
HOOK_POST["/api/m46/reset"] = lambda h, d: h._send(200, m46_reset(d))


def m46_selftest():
    err = []
    try:
        y = datetime.date.today().year - 1
        p = m46_plan(y)
        if "rows" not in p:
            err.append("m46: Plan ohne Zeilen")
        # zvE adjustment flows 1:1 into the taxable income
        sal0 = {k: 0.0 for k in ("brutto", "lst", "soli", "kist", "rv", "kv", "pv", "av", "netto")}
        t0 = tax_inputs(2099)
        a = tax_core(2025, 30000.0, sal0, t0, 0.0)
        b = tax_core(2025, 30000.0, sal0, dict(t0, zve_abgleich=-1500.0), 0.0)
        if abs((a["zve"] - b["zve"]) - 1500) > 1:
            err.append(f"m46: zvE-Abgleich wirkt nicht ({a['zve']} / {b['zve']})")
    except Exception as e:
        err.append(f"m46 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m46_selftest)
print(f"INIT m46_angleich v{M46_VERSION}")
