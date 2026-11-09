# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m36_nachweise (v2.0.9)
# Nachweise & Zertifikate: viele Hersteller- und Branchen-Zertifikate
# (Q-SYS, Crestron, Extron, Audinate Dante, AVIXA, Biamp, Shure ...),
# eigene Arten frei definierbar, und Erkennung aus dem Zertifikat-PDF/Bild:
# Art, Bezeichnung, Nummer, Person, Ausstellungs- und Ablaufdatum.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M36_VERSION = "1.0.0"

# (art, gruppe, keywords for recognition, default validity in months or 0, confirmation months or 0)
CERT_CATALOG = [
    ("Schweißerprüfung (ISO 9606)", "Schweißen & Metallbau", [r"iso\s*9606", r"en\s*287", r"schwei(ß|ss)erpr(ü|ue)fung", r"welder qualification"], 0, 6),
    ("Schweißverfahrensprüfung (WPQR)", "Schweißen & Metallbau", [r"\bwpqr\b", r"iso\s*15614", r"verfahrenspr(ü|ue)fung"], 0, 0),
    ("Schweißanweisung (WPS)", "Schweißen & Metallbau", [r"\bwps\b", r"schwei(ß|ss)anweisung", r"iso\s*15609"], 0, 0),
    ("EN 1090 Zertifikat", "Schweißen & Metallbau", [r"en\s*1090", r"werkseigene produktionskontrolle", r"\bwpk\b"], 36, 0),
    ("Schweißaufsicht", "Schweißen & Metallbau", [r"schwei(ß|ss)aufsicht", r"iso\s*14731"], 0, 0),
    ("Schweißfachmann / -ingenieur (IWS / IWE / IWT)", "Schweißen & Metallbau", [r"schwei(ß|ss)fach(mann|ingenieur)", r"\biw[set]\b", r"international welding (specialist|engineer|technologist)", r"\bewf\b"], 0, 0),
    ("DVS-Lehrgang / Bediener (ISO 14732)", "Schweißen & Metallbau", [r"\bdvs\b", r"iso\s*14732"], 0, 0),
    ("Meisterbrief", "Schweißen & Metallbau", [r"meisterbrief", r"meisterpr(ü|ue)fung"], 0, 0),
    ("Prüfgerät / Kalibrierung", "Prüfmittel", [r"kalibrier", r"calibration certificate", r"pr(ü|ue)fprotokoll"], 12, 0),
    ("Elektrofachkraft / DGUV V3", "Elektro & Sicherheit", [r"elektrofachkraft", r"dguv\s*v(orschrift)?\s*3", r"bgv\s*a3"], 0, 0),
    ("EFKffT (festgelegte Tätigkeiten)", "Elektro & Sicherheit", [r"efkfft", r"festgelegte t(ä|ae)tigkeiten"], 0, 0),
    ("Sachkunde Rigging / SQQ2", "Elektro & Sicherheit", [r"rigging", r"\bsqq\s*2\b", r"dguv\s*v(orschrift)?\s*17", r"igvw"], 0, 0),
    ("Fachkraft / Meister Veranstaltungstechnik", "Elektro & Sicherheit", [r"veranstaltungstechnik"], 0, 0),
    ("Hubarbeitsbühne / PSA gegen Absturz", "Elektro & Sicherheit", [r"hubarbeitsb(ü|ue)hne", r"\bipaf\b", r"psa gegen absturz", r"absturzsicherung"], 0, 0),
    ("Erste Hilfe", "Elektro & Sicherheit", [r"erste[- ]hilfe", r"ersthelfer", r"first aid"], 24, 0),
    ("SCC / SCP", "Elektro & Sicherheit", [r"\bscc\b", r"\bscp\b", r"sicherheits certifikat contraktoren"], 120, 0),
    ("Stapler / Kran", "Elektro & Sicherheit", [r"stapler", r"flurf(ö|oe)rderzeug", r"kranf(ü|ue)hrer"], 0, 0),
    ("Q-SYS (Level 1 / 2 / Control / Reflect)", "AV-Hersteller", [r"q-?sys", r"\bqsc\b"], 0, 0),
    ("Crestron (DMC / Programmer)", "AV-Hersteller", [r"crestron", r"\bdmc-[a-z]", r"\bsimpl(\+|#|\s+windows|\b)", r"crestron masters"], 0, 0),
    ("Extron (AV Associate / Control Professional / XTP / DTP)", "AV-Hersteller", [r"extron", r"\bxtp\b", r"\bdtp\b", r"control professional", r"av associate"], 0, 0),
    ("Audinate Dante (Level 1 / 2 / 3)", "AV-Hersteller", [r"audinate", r"\bdante\b"], 0, 0),
    ("AVIXA (CTS / CTS-D / CTS-I)", "AV-Hersteller", [r"avixa", r"infocomm", r"\bcts(-[di])?\b", r"certified technology specialist"], 36, 0),
    ("Biamp (Tesira / Certified)", "AV-Hersteller", [r"biamp", r"tesira"], 0, 0),
    ("Shure (Microflex / Designer)", "AV-Hersteller", [r"\bshure\b", r"microflex"], 0, 0),
    ("Sennheiser (TeamConnect)", "AV-Hersteller", [r"sennheiser", r"teamconnect"], 0, 0),
    ("Bose Professional (ControlSpace)", "AV-Hersteller", [r"bose professional", r"controlspace"], 0, 0),
    ("Yamaha (CL/QL/Rivage / ProVisionaire)", "AV-Hersteller", [r"yamaha", r"provisionaire", r"rivage"], 0, 0),
    ("d&b audiotechnik (ArrayCalc / Soundscape)", "AV-Hersteller", [r"d&b", r"arraycalc", r"soundscape", r"d\s*&\s*b audiotechnik"], 0, 0),
    ("L-Acoustics (Soundvision / Systems)", "AV-Hersteller", [r"l-acoustics", r"soundvision"], 0, 0),
    ("Allen & Heath / DiGiCo / Midas", "AV-Hersteller", [r"allen\s*&\s*heath", r"digico", r"\bmidas\b"], 0, 0),
    ("Symetrix / ClearOne / Bosch / Televic", "AV-Hersteller", [r"symetrix", r"clearone", r"televic", r"bosch dicentis", r"dicentis"], 0, 0),
    ("AMX / Kramer / Lightware / Atlona / Barco", "AV-Hersteller", [r"\bamx\b", r"kramer", r"lightware", r"atlona", r"barco", r"clickshare"], 0, 0),
    ("Microsoft Teams Rooms / Zoom Rooms", "AV-Hersteller", [r"teams rooms", r"microsoft teams", r"zoom rooms"], 0, 0),
    ("Logitech / Yealink / Poly / Cisco Video", "AV-Hersteller", [r"logitech", r"yealink", r"\bpoly\b", r"polycom", r"cisco webex"], 0, 0),
    ("Netzwerk (Cisco CCNA / AVB-Milan / AES67)", "AV-Hersteller", [r"\bccna\b", r"\bccnp\b", r"\bavnu\b", r"\bmilan\b", r"aes67"], 36, 0),
    ("KNX Partner / Gebäudetechnik", "AV-Hersteller", [r"\bknx\b"], 0, 0),
    ("Ableton / Pro Tools / DJ-Software", "Audio & DJ", [r"ableton", r"pro tools", r"\bavid\b", r"rekordbox", r"alphatheta", r"pioneer dj", r"serato", r"native instruments", r"traktor"], 0, 0),
    ("Hersteller-Zertifizierung (sonstige)", "Sonstige", [r"certificate of (completion|achievement)", r"certified", r"zertifikat"], 0, 0),
    ("Sonstiges", "Sonstige", [], 0, 0),
]

# known course titles per vendor -> nicer "Bezeichnung"
CERT_TITLES = [
    (r"q-?sys\s+(level\s*(one|two|1|2)|control\s*\d{3}|reflect[\w\s]*|quantum[\w\s]*|video\s*\d{3}|cinema[\w\s]*|specialist[\w\s]*)", "Q-SYS {0}"),
    (r"dante\s+(certification\s+)?level\s*([123])", "Dante Certification Level {1}"),
    (r"(dmc-[a-z0-9-]+)", "Crestron {0}"),
    (r"(extron\s+(av associate|control professional|control specialist|xtp[\w ]*|dtp[\w ]*|network[\w ]*))", "{0}"),
    (r"\b(cts-[di]|cts)\b", "AVIXA {0}"),
]

_MON = {"jan": 1, "feb": 2, "mar": 3, "mär": 3, "maer": 3, "apr": 4, "may": 5, "mai": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "oct": 10, "okt": 10, "nov": 11, "dec": 12, "dez": 12}


def cert_types():
    eig = [t for t in (get_settings().get("cert_types_eigene") or []) if isinstance(t, str) and t.strip()]
    base = [c[0] for c in CERT_CATALOG]
    return [t for t in eig if t not in base] + base


CERT_TYPES = [c[0] for c in CERT_CATALOG]


def _date_cands(s):
    """all dates in s -> list of (position, date), any supported notation"""
    s = (s or "").lower().replace(",", " ")
    out = []

    def add(m, y, mo, dd):
        try:
            out.append((m.start(), datetime.date(int(y), int(mo), int(dd))))
        except (ValueError, TypeError):
            pass
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", s):
        add(m, m.group(1), m.group(2), m.group(3))
    for m in re.finditer(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b", s):
        add(m, m.group(3), m.group(2), m.group(1))
    for m in re.finditer(r"\b(\d{1,2})\.?\s+([a-zäöü]{3,9})\.?\s+(\d{4})\b", s):
        mo = _MON.get(m.group(2)[:3]) or _MON.get(m.group(2)[:4])
        if mo:
            add(m, m.group(3), mo, m.group(1))
    for m in re.finditer(r"\b([a-zäöü]{3,9})\.?\s+(\d{1,2})(st|nd|rd|th)?\s+(\d{4})\b", s):
        mo = _MON.get(m.group(1)[:3]) or _MON.get(m.group(1)[:4])
        if mo:
            add(m, m.group(4), mo, m.group(2))
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", s):
        a, b = int(m.group(1)), int(m.group(2))
        mo, dd = (a, b) if a <= 12 else (b, a)   # US style first
        add(m, m.group(3), mo, dd)
    return sorted(out, key=lambda r: r[0])


def _date_any(s):
    """first date (by position) in s"""
    c = _date_cands(s)
    return c[0][1] if c else None


_BIRTH = re.compile(r"\s*(of\s+birth|d'?anniversaire|de\s+naissance)", re.I)


def _near_date(text, labels):
    for lb in labels:
        for m in re.finditer(lb, text, re.I):
            if _BIRTH.match(text, m.end()):
                continue
            d = _date_any(text[m.end():m.end() + 60])
            if d and d.year >= 1990:
                return d
    return None


def cert_detect(text):
    t = text or ""
    low = t.lower()
    out = {}
    best, score = None, 0
    for art, grp, kws, val, conf in CERT_CATALOG:
        sc = sum(len(re.findall(k, low)) for k in kws)
        if art.startswith("Hersteller-Zertifizierung"):
            sc = min(sc, 1)
        if sc > score:
            best, score = (art, val, conf), sc
    if best:
        out["typ"] = best[0]
        if best[2]:
            out["bestaetigung_monate"] = best[2]
    for pat, fmt in CERT_TITLES:
        m = re.search(pat, low, re.I)
        if m:
            g = [re.sub(r"\s+", " ", (x_ or "")).strip() for x_ in m.groups()]
            g = [x_.title() if not re.match(r"^(cts|dmc)", x_, re.I) else x_.upper() for x_ in g]
            out["bezeichnung"] = fmt.format(*(g + [""] * 3)).replace("Q-Sys", "Q-SYS").strip()
            break
    if "bezeichnung" not in out:
        m = re.search(r"(?:successfully completed|has completed|for completing|course|kurs|lehrgang|schulung|training)[:\s]+([^\n]{4,80})", t, re.I)
        if m:
            out["bezeichnung"] = re.sub(r"\s+", " ", m.group(1)).strip(" .:-")
    m = re.search(r"(?:certificate|zertifikat|credential|certification|cert\.?)[\s-]*(?:id|no\.?|nr\.?|number|nummer)[\s:#.]*([A-Z0-9][A-Z0-9\-/.]{3,30})", t, re.I)
    if m:
        out["nummer"] = m.group(1).strip(".")
    m = re.search(r"(?i:this (?:is to )?certif(?:y|ies) that|awarded to|presented to|verliehen an|bescheinigt(?: hiermit)?,? dass|(?<!course )(?<!kurs)(?<!\w)name\b|teilnehmer(?:in)?\b)[:\s]+([A-ZÄÖÜ][\wÄÖÜäöüß.\-]+(?:[ \t]+[A-ZÄÖÜ][\wÄÖÜäöüß.\-]+){1,3})", t)
    if m:
        out["person"] = re.split(r"\s+(?:Geburtsdatum|Geb\.?|Geboren|Datum|Date|Born|Nr\.?|No\.?)\b", m.group(1).strip())[0].strip()
    aus = _near_date(t, [r"date of (issue|completion|award)", r"issued( on)?", r"completed( on)?", r"ausgestellt( am)?", r"ausstellungsdatum",
                         r"(?<!geburts)datum", r"(?<!birth )\bdate\b", r"awarded( on)?", r"achieved( on)?"])
    gb = _near_date(t, [r"valid (until|thru|through|to)", r"expir(es|y|ation)( date)?", r"g(ü|ue)ltig bis", r"g(ü|ue)ltigkeit", r"ablauf(datum)?",
                        r"renewal( date)?", r"recertif\w*( date)?"])
    if not aus:
        t_nb = re.sub(r"(geburtsdatum|geb\.|geboren am|date of birth|birth ?date)[:\s]*[^\n]{0,30}", " ", t, flags=re.I)
        ds = [d for d in (_date_any(m_.group(0)) for m_ in re.finditer(r"\d{1,2}\.\s?\d{1,2}\.\s?\d{4}|\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\.? \d{1,2},? \d{4}|\d{1,2}\.? [A-Za-zäöü]{3,9}\.? \d{4}", t_nb)) if d]
        ds = [d for d in ds if 1990 <= d.year <= datetime.date.today().year + 10]
        if ds:
            aus = min(ds)
            if not gb and len(ds) > 1 and max(ds) > aus and max(ds) > datetime.date.today() - datetime.timedelta(days=3650):
                gb = max(ds) if max(ds) > datetime.date.today() else None
    if aus:
        out["ausgestellt"] = aus.isoformat()
    if gb and (not aus or gb > aus):
        out["gueltig_bis"] = gb.isoformat()
    elif aus and best and best[1]:
        out["gueltig_bis"] = add_months(aus, int(best[1])).isoformat()
        out["gueltig_geschaetzt"] = True
    hersteller = {"Q-SYS": "QSC / Q-SYS", "Crestron": "Crestron", "Extron": "Extron", "Audinate": "Audinate", "AVIXA": "AVIXA"}
    for k, v in hersteller.items():
        if k.lower() in low:
            out["norm"] = v
            break
    if "norm" not in out:
        m = re.search(r"\b(ISO\s*\d{3,5}(?:-\d)?|EN\s*\d{3,5}(?:-\d)?|DGUV\s*V\s*\d+)\b", t)
        if m:
            out["norm"] = re.sub(r"\s+", " ", m.group(1))
    return out


def _cert_text(path, name):
    try:
        txt, _used, _fmt = extract_text_any(path, name)
    except Exception:
        txt = ""
    if ocr_need(txt) and ocr_available():
        try:
            t_ = ocr_file(path)
            txt = t_ if len(t_.strip()) > len((txt or "").strip()) else txt
        except Exception:
            traceback.print_exc()
    return txt or ""


def _zert_upload(h, tmp, name):
    txt = ""
    try:
        txt = _cert_text(tmp, name)
    except Exception:
        traceback.print_exc()
    rel = store_upload(tmp, name, "Nachweise")
    er = {}
    try:
        er = cert_detect(txt) if txt.strip() else {}
    except Exception:
        traceback.print_exc()
    return h._send(200, {"ok": True, "file": rel, "erkannt": er, "text_gefunden": bool(txt.strip())})


def cert_types_save(d):
    lst = [str(t).strip()[:80] for t in (d.get("eigene") or []) if str(t).strip()]
    set_setting("cert_types_eigene", sorted(set(lst), key=lst.index))
    return {"ok": True, "cert_types": cert_types(), "eigene": lst}


def _m36_boot(d):
    d["cert_types"] = cert_types()
    d["cert_groups"] = {c[0]: c[1] for c in CERT_CATALOG}
    d["cert_meta"] = {c[0]: {"gueltig": c[3], "bestaetigung": c[4]} for c in CERT_CATALOG}
    d["cert_types_eigene"] = get_settings().get("cert_types_eigene") or []


def _m36_selftest():
    err = []
    try:
        r = cert_detect("Certificate of Completion\nThis certifies that Thomas Pfeiffer\nhas successfully completed Q-SYS Level One\nDate: March 3, 2025\nCertificate ID: QSC-12345-AB")
        if r.get("typ", "").split(" ")[0] != "Q-SYS" or r.get("ausgestellt") != "2025-03-03" or r.get("nummer") != "QSC-12345-AB":
            err.append("Nachweise: Erkennung Q-SYS fehlerhaft " + json.dumps(r, ensure_ascii=False))
        r = cert_detect("Audinate Dante Certification Level 3 awarded to Max Muster 14.02.2026")
        if not r.get("typ", "").startswith("Audinate") or "Level 3" not in r.get("bezeichnung", ""):
            err.append("Nachweise: Erkennung Dante fehlerhaft")
    except Exception as e:
        err.append(f"Nachweise: {e}")
    return err


HOOK_UPLOAD["/api/upload/zert"] = _zert_upload
HOOK_POST["/api/zert/types"] = lambda h, d: h._send(200, cert_types_save(d))
def cert_erkennen(rel):
    rel = str(rel or "")
    base = os.path.realpath(DATA_DIR)
    fp = os.path.realpath(os.path.join(DATA_DIR, rel))
    if not rel or os.path.commonpath([base, fp]) != base or not os.path.isfile(fp):
        raise ValueError("Datei nicht gefunden (nur Dateien im Datenordner).")
    return {"ok": True, "erkannt": cert_detect(_cert_text(fp, os.path.basename(fp)))}


HOOK_POST["/api/zert/erkennen"] = lambda h, d: h._send(200, cert_erkennen(d.get("file")))
HOOK_BOOT.append(_m36_boot)
HOOK_SELFTEST.append(_m36_selftest)
