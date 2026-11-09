# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m26_vorlagen (v2.0.3)
# Vorlagen-Katalog: ein frei waehlbarer Ordner mit eigenen Vorlagen wird
# gescannt, jede Datei wird automatisch einer Kategorie zugeordnet (Dateiname,
# Ordnername, Dateityp und Inhalt; optional lokale KI) und als VERWEIS im
# Programm gefuehrt - es wird nichts kopiert, der Ordner bleibt wie er ist.
# Neu-Scan erkennt neue, geaenderte, entfernte und DOPPELTE Dateien (gleicher
# Inhalt -> nur das Original wird gefuehrt); eigene Korrekturen
# der Kategorie bleiben erhalten. Oeffnen, Kopie bearbeiten, In Projekt.
# Autor: T. Pfeiffer

VL_MAX = 5000
VL_TEXT_MAX_MB = 25
VL_SKIP = re.compile(r"^(~\$|\.|thumbs\.db$|desktop\.ini$)", re.I)
VL_ART = {"doc": "Word", "docx": "Word", "dot": "Word-Vorlage", "dotx": "Word-Vorlage", "docm": "Word", "odt": "Text (ODT)", "rtf": "Text",
          "xls": "Excel", "xlsx": "Excel", "xlsm": "Excel", "xlt": "Excel-Vorlage", "xltx": "Excel-Vorlage", "ods": "Tabelle (ODS)", "csv": "CSV",
          "pdf": "PDF", "ppt": "PowerPoint", "pptx": "PowerPoint", "potx": "PowerPoint-Vorlage", "txt": "Text", "md": "Text",
          "jpg": "Bild", "jpeg": "Bild", "png": "Bild", "svg": "Grafik", "zip": "Archiv", "msg": "E-Mail", "eml": "E-Mail", "oft": "Outlook-Vorlage",
          "qsys": "Q-SYS Design", "smw": "SIMPL Windows", "usp": "SIMPL+", "umc": "SIMPL Modul", "vtz": "VT Pro-e", "lpz": "Crestron Programm",
          "ipt": "Inventor Teil", "iam": "Inventor Baugruppe", "idw": "Inventor Zeichnung", "ipn": "Inventor Praesentation",
          "dwg": "AutoCAD", "dxf": "DXF", "step": "STEP", "stp": "STEP", "eaf": "EASE Focus"}

# category -> (label, extension hints, keyword list); keywords are regex fragments (lower case)
VL_KATS = [
    ("angebot", "Angebote & Kalkulation", (), [r"angebot", r"kalkulation", r"kostenvoranschlag", r"preisliste", r"leistungsverzeichnis", r"\blv\b", r"aufma(ss|ß)",
                                               r"nachtrag", r"offerte", r"quote", r"stundensatz", r"gesamtpreis", r"einzelpreis", r"gültig bis", r"gueltig bis"]),
    ("rechnung", "Rechnungen & Mahnungen", (), [r"rechnung", r"mahnung", r"zahlungserinnerung", r"gutschrift", r"storno", r"invoice", r"zahlbar",
                                               r"rechnungsnummer", r"abschlag", r"schlussrechnung", r"kleinunternehmer"]),
    ("brief", "Briefe & Anschreiben", (".dotx", ".dot"), [r"brief", r"anschreiben", r"briefbogen", r"briefkopf", r"sehr geehrte", r"mit freundlichen gr",
                                                          r"anlage[n]?:", r"betreff", r"kündigung", r"kuendigung"]),
    ("vertrag", "Verträge & AGB", (), [r"vertrag", r"\bagb\b", r"geschäftsbedingungen", r"geschaeftsbedingungen", r"wartungsvertrag", r"vereinbarung",
                                       r"datenschutz", r"\bavv\b", r"auftragsverarbeitung", r"haftung", r"vertragsparteien", r"laufzeit", r"kündigungsfrist"]),
    ("protokoll", "Protokolle & Übergabe", (), [r"protokoll", r"übergabe", r"uebergabe", r"abnahme", r"inbetriebnahme", r"einweisung", r"prüfprotokoll",
                                                r"pruefprotokoll", r"messprotokoll", r"\bdguv\b", r"\bvde\b", r"wartungsbericht", r"servicebericht", r"stundenzettel",
                                                r"arbeitsnachweis", r"regiebericht", r"unterschrift auftraggeber"]),
    ("checkliste", "Checklisten", (), [r"checkliste", r"check-liste", r"checklist", r"to-?do", r"packliste", r"\[ \]", r"☐", r"abhaken"]),
    ("formular", "Formulare", (), [r"formular", r"antrag", r"vordruck", r"bestellschein", r"auftragsformular", r"anmeldung", r"fragebogen", r"erfassungsbogen"]),
    ("schweissen", "Schweißen & Prüfung", (), [r"schwei(ss|ß)", r"\bwps\b", r"\bwpqr\b", r"\bpwps\b", r"iso 9606", r"en 1090", r"iso 3834", r"iso 15614",
                                               r"\bmag\b", r"\bwig\b", r"\btig\b", r"\bmig\b", r"\b135\b", r"\b141\b", r"\b111\b", r"nahtvorbereitung", r"zusatzwerkstoff",
                                               r"schutzgas", r"sichtprüfung", r"durchstrahlung", r"werkstoffzeugnis", r"leistungserklärung", r"\bce\b-?kennz"]),
    ("metallbau", "Metallbau & Zeichnungen", (".ipt", ".iam", ".idw", ".ipn", ".dwg", ".dxf", ".step", ".stp"),
     [r"zeichnung", r"geländer", r"gelaender", r"treppe", r"stahlbau", r"metallbau", r"stückliste", r"stueckliste", r"inventor", r"blech", r"profil",
      r"\bs235\b", r"\bs355\b", r"verzink", r"pulverbeschicht", r"statik", r"montageplan", r"schnitt", r"maßstab", r"masstab"]),
    ("av", "AV- & Medientechnik", (".qsys", ".smw", ".usp", ".umc", ".vtz", ".lpz", ".eaf"),
     [r"q-?sys", r"crestron", r"extron", r"\bdante\b", r"\bdsp\b", r"blockschaltbild", r"signalfluss", r"verkabelung", r"konferenz", r"medientechnik",
      r"beamer", r"display", r"lautsprecher", r"mikrofon", r"\buci\b", r"simpl", r"touchpanel", r"\bhdmi\b", r"\bhdbaset\b", r"rack", r"patch", r"kabelliste",
      r"raumsteuerung", r"\bavb\b"]),
    ("unterricht", "Unterricht & Kurse", (), [r"unterricht", r"\bkurs", r"schüler", r"schueler", r"lektion", r"lehrplan", r"übung", r"uebung", r"\bdj\b",
                                              r"workshop", r"schulung", r"teilnehmer", r"seminar", r"zertifikat", r"urkunde"]),
    ("buchhaltung", "Steuer & Buchhaltung", (), [r"\beür\b", r"\beuer\b", r"steuer", r"finanzamt", r"buchhaltung", r"kassenbuch", r"fahrtenbuch", r"reisekosten",
                                                 r"spesen", r"umsatzsteuer", r"vorsteuer", r"jahresabschluss", r"beleg"]),
    ("praesentation", "Präsentationen & Werbung", (".pptx", ".ppt", ".potx"), [r"präsentation", r"praesentation", r"flyer", r"werbung", r"logo", r"visitenkarte",
                                                                              r"broschüre", r"broschuere", r"plakat", r"portfolio", r"referenz", r"social"]),
    ("sonstiges", "Sonstiges", (), []),
]
VL_KAT_LABEL = {k: l for k, l, _, _ in VL_KATS}
VL_TEXT_EXT = {".pdf", ".docx", ".docm", ".dotx", ".xlsx", ".xlsm", ".xltx", ".odt", ".ods", ".txt", ".md", ".csv", ".rtf", ".doc", ".xls", ".pptx", ".potx", ".eml", ".msg"}
VL_SCAN = {"laeuft": False, "fortschritt": 0, "gesamt": 0, "datei": "", "ergebnis": None, "start": ""}
VL_LOCK = threading.Lock()


def vl_dir():
    return (get_settings().get("vorlagen_dir") or "").strip()


def vl_art(fn):
    ext = os.path.splitext(fn)[1].lower().lstrip(".")
    if ext in VL_ART:
        return VL_ART[ext]
    k = detect_kind(fn, [])[0]
    return k if k not in ("Sonstiges", "Dokument") else (ext.upper() or "Datei")


def _vl_schema():
    x("""CREATE TABLE IF NOT EXISTS vorlagen (id INTEGER PRIMARY KEY, rel TEXT UNIQUE, name TEXT, ordner TEXT, ext TEXT, art TEXT,
         groesse INTEGER, mtime REAL, kategorie TEXT, kategorie_auto TEXT, sicherheit REAL, begruendung TEXT, manuell INTEGER DEFAULT 0,
         schlagworte TEXT, auszug TEXT, notiz TEXT, status TEXT, gefunden TEXT, geaendert TEXT, benutzt INTEGER DEFAULT 0, zuletzt TEXT,
         hash TEXT, dublette_von INTEGER, original_fest INTEGER DEFAULT 0)""")
    for col, typ in (("hash", "TEXT"), ("dublette_von", "INTEGER"), ("original_fest", "INTEGER DEFAULT 0")):
        try:
            x(f"ALTER TABLE vorlagen ADD COLUMN {col} {typ}")
        except Exception:
            pass


def _vl_text(fp):
    ext = os.path.splitext(fp)[1].lower()
    if ext not in VL_TEXT_EXT:
        return ""
    try:
        if os.path.getsize(fp) > VL_TEXT_MAX_MB * 1048576:
            return ""
    except OSError:
        return ""
    name = os.path.basename(fp)
    tmp = None
    try:
        # Word/Excel/PowerPoint templates are normal OOXML files with another extension
        alias = {".dotx": ".docx", ".docm": ".docx", ".xltx": ".xlsx", ".xlsm": ".xlsx", ".potx": ".pptx"}.get(ext)
        src = fp
        if alias:
            tmp = os.path.join(DATA_DIR, "_tmp_vl_" + uuid.uuid4().hex[:8] + alias)
            shutil.copy2(fp, tmp)
            src, name = tmp, os.path.splitext(name)[0] + alias
        text, _, _ = extract_text_any(src, name, None)
        return (text or "")[:6000]
    except Exception:
        return ""
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _kwl(kw):
    """readable keyword label for the reason text"""
    k = re.sub(r"\(ss\|ß\)", "ß", kw)
    k = re.sub(r"\\b|\\s|-\?|[\\()?|\[\]^$*]", "", k)
    k = k.replace("\\", "")
    if k.strip() in ("", "☐"):
        return "Ankreuzkästchen"
    return k.strip() or kw


def _vl_hash(fp):
    h = hashlib.sha256()
    try:
        with open(fp, "rb") as f:
            for ch in iter(lambda: f.read(1 << 20), b""):
                h.update(ch)
        return h.hexdigest()
    except OSError:
        return ""


def vl_dedupe():
    """same content = duplicate; one original stays visible, copies are sorted out (files are NOT touched)"""
    x("UPDATE vorlagen SET dublette_von=NULL")
    groups = {}
    for r in q("SELECT id, rel, hash, manuell, original_fest, gefunden, benutzt FROM vorlagen WHERE status<>'fehlt' AND hash<>'' AND hash IS NOT NULL"):
        groups.setdefault(r["hash"], []).append(r)
    n = 0
    for rows in groups.values():
        if len(rows) < 2:
            continue
        def rank(r):
            nm = os.path.basename(r["rel"]).lower()
            copyish = 1 if re.search(r"kopie|copy|\(\d+\)|_\d+\.\w+$|duplikat", nm) else 0
            return (-(r["original_fest"] or 0), -(r["manuell"] or 0), copyish, r["rel"].count("/"), -(r["benutzt"] or 0), r["gefunden"] or "", r["rel"].lower())
        rows.sort(key=rank)
        keep = rows[0]
        for r in rows[1:]:
            x("UPDATE vorlagen SET dublette_von=? WHERE id=?", (keep["id"], r["id"]))
            n += 1
    return n


def vl_classify(name, ordner, text, s=None):
    """returns (kategorie, sicherheit 0..1, begruendung, schlagworte)"""
    fn = name.lower()
    fd = (ordner or "").lower().replace("\\", "/")
    tx = (text or "").lower()
    ext = os.path.splitext(fn)[1]
    scores, why = {}, {}
    for key, lbl, exts, kws in VL_KATS:
        sc, hits = 0.0, []
        if ext in exts:
            sc += 6
            hits.append(f"Dateityp {ext}")
        for kw in kws:
            if re.search(kw, fn):
                sc += 3
                hits.append(f"Name: {_kwl(kw)}")
            if fd and re.search(kw, fd):
                sc += 2.5
                hits.append(f"Ordner: {_kwl(kw)}")
            if tx:
                n = len(re.findall(kw, tx))
                if n:
                    sc += min(3.0, 0.8 + 0.4 * n)
                    hits.append(f"Inhalt: {_kwl(kw)}")
        if sc:
            scores[key], why[key] = sc, hits
    # learned: corrections in the same folder / with the same name stem
    for r in q("SELECT kategorie, COUNT(*) n FROM vorlagen WHERE manuell=1 AND ordner=? GROUP BY kategorie", (ordner or "",)):
        scores[r["kategorie"]] = scores.get(r["kategorie"], 0) + 2.0 * r["n"]
        why.setdefault(r["kategorie"], []).append("gelernt aus deinen Korrekturen im selben Ordner")
    if not scores:
        return "sonstiges", 0.0, "keine Merkmale gefunden", ""
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, bs = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    conf = round(min(0.99, (bs / (bs + second + 2.0)) * min(1.0, bs / 4.0) + 0.15), 2)
    hits = list(dict.fromkeys(why.get(best, [])))
    tags = sorted({h.split(": ", 1)[1] for h in hits if ": " in h})[:8]
    return best, conf, ", ".join(hits[:6]), ", ".join(tags)


def _vl_ki(name, ordner, text, s):
    """optional local AI for unclear files - returns category key or None"""
    if not s.get("ki_enabled"):
        return None
    try:
        keys = ", ".join(f"{k} ({l})" for k, l, _, _ in VL_KATS)
        prompt = (f"Ordne diese Vorlagen-Datei genau EINER Kategorie zu. Antworte nur mit JSON {{\"kategorie\": \"<schluessel>\"}}.\n"
                  f"Kategorien: {keys}\nDateiname: {name}\nOrdner: {ordner}\nInhalt (Auszug):\n{(text or '')[:1500]}")
        r = m55_llm(prompt, s, as_json=True)
        k = (r or {}).get("kategorie") if isinstance(r, dict) else None
        return k if k in VL_KAT_LABEL else None
    except Exception:
        return None


def vl_scan(force=False):
    """scan the folder; nothing is copied - only references are stored"""
    root = vl_dir()
    res = {"ok": True, "neu": 0, "geaendert": 0, "entfernt": 0, "unveraendert": 0, "gesamt": 0, "ki": 0, "doppelt": 0, "eindeutig": 0, "fehler": ""}
    if not root:
        res.update(ok=False, fehler="Kein Vorlagen-Ordner festgelegt.")
        return res
    if not os.path.isdir(root):
        res.update(ok=False, fehler="Der Vorlagen-Ordner ist nicht erreichbar (Laufwerk/NAS getrennt oder Ordner verschoben).")
        return res
    s = get_settings()
    files = []
    for base, dirs, fns in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not VL_SKIP.match(d))
        for fn in sorted(fns, key=str.lower):
            if not VL_SKIP.match(fn):
                files.append(os.path.join(base, fn))
            if len(files) >= VL_MAX:
                break
        if len(files) >= VL_MAX:
            res["fehler"] = f"Mehr als {VL_MAX} Dateien - nur die ersten {VL_MAX} wurden aufgenommen."
            break
    old = {r["rel"]: r for r in q("SELECT * FROM vorlagen")}
    seen = set()
    VL_SCAN.update(gesamt=len(files), fortschritt=0)
    now = now_iso()
    for i, fp in enumerate(files, 1):
        if i % 50 == 0 and os.path.normcase(vl_dir() or "") != os.path.normcase(root):
            res.update(ok=False, fehler="Vorlagen-Ordner wurde während des Scans geändert - Scan abgebrochen.")
            VL_SCAN["nochmal"] = True
            return res
        VL_SCAN.update(fortschritt=i, datei=os.path.basename(fp))
        rel = os.path.relpath(fp, root).replace("\\", "/")
        seen.add(rel)
        try:
            st_ = os.stat(fp)
        except OSError:
            continue
        o = old.get(rel)
        if o and o["status"] == "fehlt" and abs((o["mtime"] or 0) - st_.st_mtime) < 1 and o["groesse"] == st_.st_size and o.get("hash"):
            # v2.0.6: same file found again (e.g. folder re-selected / other drive letter) -> keep classification, no re-reading
            x("UPDATE vorlagen SET status='ok', geaendert=? WHERE id=?", (now, o["id"]))
            res["unveraendert"] += 1
            continue
        if o and not force and abs((o["mtime"] or 0) - st_.st_mtime) < 1 and o["groesse"] == st_.st_size and o["status"] != "fehlt":
            if not o.get("hash"):
                x("UPDATE vorlagen SET hash=? WHERE id=?", (_vl_hash(fp), o["id"]))
            res["unveraendert"] += 1
            continue
        name = os.path.basename(fp)
        ordner = os.path.dirname(rel)
        hsh = _vl_hash(fp)
        text = _vl_text(fp)
        kat, conf, why, tags = vl_classify(name, ordner, text, s)
        if conf < 0.45 and res.get("ki_calls", 0) < 40:   # v2.0.6: max. 40 KI questions per scan
            res["ki_calls"] = res.get("ki_calls", 0) + 1
            k2 = _vl_ki(name, ordner, text, s)
            if k2 and k2 != kat:
                kat, conf, why = k2, 0.6, "lokale KI (Merkmale waren unklar)"
                res["ki"] += 1
            elif k2:
                conf = max(conf, 0.6)
        ausz = re.sub(r"\s+", " ", text or "").strip()[:400]
        vals = dict(name=name, ordner=ordner, ext=os.path.splitext(name)[1].lower().lstrip("."), art=vl_art(name), groesse=st_.st_size,
                    mtime=st_.st_mtime, kategorie_auto=kat, sicherheit=conf, begruendung=why, schlagworte=tags, auszug=ausz, geaendert=now)
        if o and o["status"] == "fehlt" and o.get("hash") and o["hash"] != hsh:
            # v2.0.6: same name in another folder, but a different file -> do not inherit the manual category
            x("UPDATE vorlagen SET manuell=0, notiz='', dublette_von=NULL, original_fest=0 WHERE id=?", (o["id"],))
            o = dict(o, manuell=0)
        if o:
            final = o["kategorie"] if o["manuell"] else kat
            x("UPDATE vorlagen SET name=?, ordner=?, ext=?, art=?, groesse=?, mtime=?, kategorie=?, kategorie_auto=?, sicherheit=?, begruendung=?, "
              "schlagworte=?, auszug=?, status=?, geaendert=?, hash=? WHERE id=?",
              (vals["name"], vals["ordner"], vals["ext"], vals["art"], vals["groesse"], vals["mtime"], final, kat, conf, why, tags, ausz,
               "geaendert" if o["status"] != "fehlt" else "ok", now, hsh, o["id"]))
            res["geaendert"] += 1
        else:
            # v2.0.6: ids are never reused (letters keep pointing at the right template) + manual category by content
            mx = q("SELECT MAX(id) m FROM vorlagen", one=True)["m"] or 0
            nid = max(int(mx), int(s.get("vl_maxid") or 0)) + 1
            man = q("SELECT kategorie, notiz FROM vorlagen WHERE hash=? AND manuell=1 LIMIT 1", (hsh,), one=True) if hsh else None
            x("INSERT INTO vorlagen (id, rel, name, ordner, ext, art, groesse, mtime, kategorie, kategorie_auto, sicherheit, begruendung, manuell, "
              "schlagworte, auszug, status, gefunden, geaendert, hash, notiz) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (nid, rel, vals["name"], vals["ordner"], vals["ext"], vals["art"], vals["groesse"], vals["mtime"], man["kategorie"] if man else kat,
               kat, conf, why, 1 if man else 0, tags, ausz, "neu", now, now, hsh, (man["notiz"] if man else "") or ""))
            s["vl_maxid"] = nid
            res["neu"] += 1
    for rel, o in old.items():
        if rel not in seen and o["status"] != "fehlt":
            x("UPDATE vorlagen SET status='fehlt', geaendert=? WHERE id=?", (now, o["id"]))
            res["entfernt"] += 1
    try:
        set_setting("vl_maxid", int(s.get("vl_maxid") or 0))
    except Exception:
        pass
    res["doppelt"] = vl_dedupe()
    res["gesamt"] = len(seen)
    res["eindeutig"] = res["gesamt"] - res["doppelt"]
    set_setting("vorlagen_scan", {"zeit": now, "ordner": root, **{k: res[k] for k in ("neu", "geaendert", "entfernt", "gesamt", "doppelt", "eindeutig")}})
    return res


def _vl_scan_bg(force=False):
    if not VL_LOCK.acquire(blocking=False):
        VL_SCAN["nochmal"] = True   # v2.0.6: scan again when the running one is done
        return False
    def run():
        try:
            VL_SCAN.update(laeuft=True, ergebnis=None, start=now_iso(), fortschritt=0, gesamt=0, datei="")
            VL_SCAN["ergebnis"] = vl_scan(force)
        except Exception as e:
            traceback.print_exc()
            VL_SCAN["ergebnis"] = {"ok": False, "fehler": f"Scan abgebrochen: {e}"}
        finally:
            VL_SCAN["laeuft"] = False
            VL_LOCK.release()
            if VL_SCAN.pop("nochmal", False):
                _vl_scan_bg(True)
    threading.Thread(target=run, daemon=True).start()
    return True


def vl_list():
    root = vl_dir()
    rows = q("SELECT id, rel, name, ordner, ext, art, groesse, mtime, kategorie, kategorie_auto, sicherheit, begruendung, manuell, schlagworte, "
             "status, gefunden, notiz, benutzt, zuletzt, dublette_von, original_fest FROM vorlagen ORDER BY kategorie, lower(name)")
    byid = {r["id"]: r for r in rows}
    ndup = {}
    for r in rows:
        if r["dublette_von"]:
            k = byid.get(r["dublette_von"])
            r["original_rel"] = k["rel"] if k else ""
            ndup[r["dublette_von"]] = ndup.get(r["dublette_von"], 0) + 1
    for r in rows:
        r["kopien"] = ndup.get(r["id"], 0)
    for r in rows:
        r["kategorie_label"] = VL_KAT_LABEL.get(r["kategorie"], r["kategorie"])
        r["geaendert_datei"] = datetime.datetime.fromtimestamp(r["mtime"] or 0).strftime("%Y-%m-%d %H:%M") if r["mtime"] else ""
    counts = {}
    for r in rows:
        if r["status"] != "fehlt" and not r["dublette_von"]:
            counts[r["kategorie"]] = counts.get(r["kategorie"], 0) + 1
    return {"ok": True, "ordner": root, "erreichbar": bool(root) and os.path.isdir(root), "vorlagen": rows,
            "doppelt": sum(1 for r in rows if r["dublette_von"] and r["status"] != "fehlt"),
            "kategorien": [{"key": k, "label": l, "anzahl": counts.get(k, 0)} for k, l, _, _ in VL_KATS],
            "letzter_scan": get_settings().get("vorlagen_scan"), "scan": {k: VL_SCAN[k] for k in ("laeuft", "fortschritt", "gesamt", "datei", "ergebnis")}}


def _vl_get(vid):
    r = q("SELECT * FROM vorlagen WHERE id=?", (int(vid),), one=True)
    if not r:
        raise ValueError("Vorlage nicht gefunden.")
    root = vl_dir()
    if not root or not os.path.isdir(root):
        raise ValueError("Der Vorlagen-Ordner ist nicht erreichbar.")
    fp = os.path.abspath(os.path.join(root, r["rel"]))
    if os.path.commonpath([fp, os.path.abspath(root)]) != os.path.abspath(root) or not os.path.isfile(fp):
        raise ValueError("Die Datei liegt nicht mehr im Vorlagen-Ordner - bitte neu scannen.")
    return r, fp


def _vl_used(vid):
    x("UPDATE vorlagen SET benutzt=COALESCE(benutzt,0)+1, zuletzt=? WHERE id=?", (now_iso(), int(vid)))


def vl_set(d):
    p = (d.get("ordner") or "").strip().strip('"')
    if p:
        p = os.path.abspath(os.path.expanduser(p))
        if not os.path.isdir(p):
            raise ValueError("Diesen Ordner gibt es nicht.")
        if os.path.normcase(p) == os.path.normcase(os.path.abspath(DATA_DIR)):
            raise ValueError("Bitte einen eigenen Vorlagen-Ordner waehlen, nicht den Datenordner.")
    old = vl_dir()
    set_setting("vorlagen_dir", p)
    if os.path.normcase(old or "") != os.path.normcase(p or ""):
        # v2.0.6: another folder - keep the rows (ids stay unique for letters, manual categories are carried over
        # by content hash or same relative path), they are marked as missing until the new scan finds them
        x("UPDATE vorlagen SET status='fehlt' WHERE status<>'fehlt'")
    if p:
        _vl_scan_bg(force=True)
    return vl_list()


def vl_open(d):
    r, fp = _vl_get(d.get("id"))
    if d.get("ordner"):
        return {"ok": open_path(os.path.dirname(fp))}
    _vl_used(r["id"])
    return {"ok": open_plain(fp)}


def vl_copy(d):
    """editable copy in <Datenordner>/Vorlagen-Kopien or into a project; the template itself stays untouched"""
    r, fp = _vl_get(d.get("id"))
    name = (d.get("name") or "").strip() or os.path.basename(fp)
    root_, ext = os.path.splitext(name)
    if not root_.strip():
        root_ = os.path.splitext(os.path.basename(fp))[0]
    if not ext:
        ext = os.path.splitext(fp)[1]
    name = safe_name(root_ + ext)
    _vl_used(r["id"])
    pid = d.get("project_id")
    if pid:
        tmp = os.path.join(DATA_DIR, "_tmp_vorlage_" + uuid.uuid4().hex[:8] + ext)
        shutil.copy2(fp, tmp)
        try:
            res = add_project_file(int(pid), tmp, name, d.get("folder") or None)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return {"ok": True, "projekt": True, "datei": res}
    dst_dir = os.path.join(DATA_DIR, "Vorlagen-Kopien")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, time.strftime("%Y-%m-%d_") + name)
    r_, e_ = os.path.splitext(dst)
    k = 2
    while os.path.exists(dst):
        dst = f"{r_} ({k}){e_}"
        k += 1
    shutil.copy2(fp, dst)
    if d.get("oeffnen", True):
        open_plain(dst)
    return {"ok": True, "pfad": dst}


def vl_update(d):
    ids = [int(i) for i in (d.get("ids") or ([d["id"]] if d.get("id") else []))]
    if not ids:
        raise ValueError("Keine Vorlage gewaehlt.")
    if "kategorie" in d:
        k = d["kategorie"]
        if k == "_auto":
            for i in ids:
                x("UPDATE vorlagen SET kategorie=kategorie_auto, manuell=0 WHERE id=?", (i,))
        else:
            if k not in VL_KAT_LABEL:
                raise ValueError("Unbekannte Kategorie.")
            for i in ids:
                x("UPDATE vorlagen SET kategorie=?, manuell=1 WHERE id=?", (k, i))
    if "notiz" in d and len(ids) == 1:
        x("UPDATE vorlagen SET notiz=? WHERE id=?", (str(d["notiz"])[:500], ids[0]))
    if d.get("original") and len(ids) == 1:
        r = q("SELECT hash FROM vorlagen WHERE id=?", (ids[0],), one=True)
        if r and r["hash"]:
            x("UPDATE vorlagen SET original_fest=0 WHERE hash=?", (r["hash"],))
            x("UPDATE vorlagen SET original_fest=1 WHERE id=?", (ids[0],))
            vl_dedupe()
    if d.get("gesehen"):
        x(f"UPDATE vorlagen SET status='ok' WHERE status IN ('neu','geaendert') AND id IN ({','.join('?' * len(ids))})", ids)
    return {"ok": True}


def vl_forget_missing():
    n = q("SELECT COUNT(*) n FROM vorlagen WHERE status='fehlt'", one=True)["n"]
    x("DELETE FROM vorlagen WHERE status='fehlt'")
    return {"ok": True, "entfernt": n}


def _vl_boot(d):
    r = q("SELECT COUNT(*) n, SUM(CASE WHEN status='neu' THEN 1 ELSE 0 END) neu FROM vorlagen WHERE status<>'fehlt' AND dublette_von IS NULL", one=True)
    d["vorlagen"] = {"ordner": vl_dir(), "anzahl": r["n"] or 0, "neu": r["neu"] or 0,
                     "kategorien": [{"key": k, "label": l} for k, l, _, _ in VL_KATS]}


def _vl_start():
    """quick rescan at program start (only changed files are read again)"""
    time.sleep(20)
    if vl_dir() and os.path.isdir(vl_dir()):
        _vl_scan_bg(False)


# global search (Strg+K) also finds templates
@chain_step("global_search", "m26_vorlagen")
def _m26_step_global_search(_next, term):
    r = _next(term)
    if r and len(term.strip()) >= 2:
        t = f"%{term.strip()}%"
        try:
            r["Vorlagen"] = q("SELECT id, name title, ordner sub, kategorie FROM vorlagen WHERE status<>'fehlt' AND dublette_von IS NULL AND "
                              "(name LIKE ? OR ordner LIKE ? OR schlagworte LIKE ? OR auszug LIKE ? OR notiz LIKE ?) LIMIT 8", (t,) * 5)
            for x_ in r["Vorlagen"]:
                x_["sub"] = VL_KAT_LABEL.get(x_["kategorie"], "") + (f" · {x_['sub']}" if x_["sub"] else "")
        except Exception:
            pass
    return r


def _vl_selftest():
    errs = []
    tests = [("WPS_135_S355.pdf", "Schweissen", "Schweissanweisung pWPS nach ISO 15614 MAG 135", "schweissen"),
             ("Angebot_AV-Anlage.docx", "", "Angebot Nr. Einzelpreis Gesamtpreis gültig bis", "angebot"),
             ("Konferenzraum_Basis.qsys", "Q-SYS", "", "av"),
             ("Geländer_Treppe.idw", "Zeichnungen", "", "metallbau"),
             ("Übergabeprotokoll.docx", "Projekte", "Inbetriebnahme Einweisung Unterschrift Auftraggeber", "protokoll"),
             ("Briefbogen.dotx", "", "Sehr geehrte Damen und Herren, mit freundlichen Grüßen", "brief")]
    for name, folder, text, want in tests:
        k, c, why, _ = vl_classify(name, folder, text)
        if k != want:
            errs.append(f"{name}: {k} statt {want} ({why})")
    return errs


def _vl_selftest_dup():
    import tempfile
    errs = []
    t = tempfile.mkdtemp(prefix="pa_vl_")
    old = get_settings().get("vorlagen_dir")
    try:
        os.makedirs(os.path.join(t, "Angebote", "alt"))
        for rel, data in (("Angebote/Angebot_AV.docx", b"A" * 50), ("Angebote/alt/Angebot_AV - Kopie.docx", b"A" * 50),
                          ("Angebot_AV (1).docx", b"A" * 50), ("Angebote/Angebot_Metall.docx", b"B" * 50)):
            open(os.path.join(t, *rel.split("/")), "wb").write(data)
        x("DELETE FROM vorlagen")
        set_setting("vorlagen_dir", t)
        r = vl_scan(True)
        lst = vl_list()
        orig = [v["rel"] for v in lst["vorlagen"] if not v["dublette_von"]]
        if r["doppelt"] != 2 or sorted(orig) != ["Angebote/Angebot_AV.docx", "Angebote/Angebot_Metall.docx"]:
            errs.append(f"Dubletten falsch: doppelt={r['doppelt']} originale={orig}")
    finally:
        x("DELETE FROM vorlagen")
        set_setting("vorlagen_dir", old or "")
        shutil.rmtree(t, ignore_errors=True)
    return errs


HOOK_SELFTEST.append(_vl_selftest_dup)
HOOK_SCHEMA.append(_vl_schema)
HOOK_GET["/api/vorlagen"] = lambda h, qs: h._send(200, vl_list())
HOOK_GET["/api/vorlagen/scan_status"] = lambda h, qs: h._send(200, {k: VL_SCAN[k] for k in ("laeuft", "fortschritt", "gesamt", "datei", "ergebnis")})
HOOK_POST["/api/vorlagen/ordner"] = lambda h, d: h._send(200, vl_set(d))
HOOK_POST["/api/vorlagen/scan"] = lambda h, d: h._send(200, {"ok": True, "gestartet": _vl_scan_bg(bool(d.get("komplett")))})
HOOK_POST["/api/vorlagen/oeffnen"] = lambda h, d: h._send(200, vl_open(d))
HOOK_POST["/api/vorlagen/kopie"] = lambda h, d: h._send(200, vl_copy(d))
HOOK_POST["/api/vorlagen/update"] = lambda h, d: h._send(200, vl_update(d))
HOOK_POST["/api/vorlagen/fehlende_entfernen"] = lambda h, d: h._send(200, vl_forget_missing())
HOOK_BOOT.append(_vl_boot)
HOOK_START.append(_vl_start)
HOOK_SELFTEST.append(_vl_selftest)
