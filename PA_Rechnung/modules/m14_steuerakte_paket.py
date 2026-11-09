# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m14_steuerakte_paket
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# v1.5.0  Steuerakte / Jahresabschluss, Daten-Paket (Export + Einspielen), 10-Tage-Regel
# ----------------------------------------------------------------------------
STEUER_ARTEN = ["Einkommensteuerbescheid", "Steuerberechnung / Bescheiddaten", "Steuererklärung / Anlage EÜR",
                "Lohnsteuerbescheinigung", "Lohn- und Gehaltsabrechnungen", "Kontoauszüge (Jahr)", "Jahressteuerbescheinigung Bank",
                "Jahresabschluss / eigene Übersicht", "Rechnungen (Sammlung)", "Sonstiges"]
ABSCHLUSS_FELDER = [("eur_einnahmen", "Betriebseinnahmen lt. Erklärung"), ("eur_ausgaben", "Betriebsausgaben lt. Erklärung"),
                    ("eur_gewinn", "Gewinn/Verlust lt. Erklärung"), ("einkuenfte_gewerbe", "Einkünfte Gewerbe/selbst. lt. Bescheid"),
                    ("bruttolohn", "Bruttoarbeitslohn lt. Bescheid"), ("wk", "Werbungskosten lt. Bescheid"),
                    ("zve", "zu versteuerndes Einkommen"), ("est_festgesetzt", "festgesetzte Einkommensteuer"),
                    ("soli_festgesetzt", "festgesetzter Solidaritätszuschlag"), ("lst_abzug", "Abzug vom Lohn (Lohnsteuer)"),
                    ("mobilitaet", "Mobilitätsprämie"), ("erstattung", "Erstattung (+) / Nachzahlung (−)")]


# top-level folders below DATA_DIR from which a data package may bring files (lower case)
PKG_FILE_DIRS = {"belege", "e-mails", "eingang", "dokumente", "briefe", "projekte", "unterricht"}


def _pkg_inside(root, rel):
    try:
        r_ = os.path.realpath(root)
        p_ = os.path.realpath(os.path.join(root, rel))
        return os.path.commonpath([p_, r_]) == r_
    except ValueError:
        return False


def regular_customer(cid, kdnr, year):
    n = q("SELECT COUNT(*) n FROM invoices WHERE typ='rechnung' AND status NOT IN ('entwurf','storniert') AND substr(datum,1,4)=? AND (customer_id=? OR kdnr=?)",
          (str(year), cid, kdnr), one=True)["n"]
    return n >= 4


def zufluss_year(r):
    """year of payment incl. 10-day rule (par. 11 Abs. 1 S. 2 EStG) for regularly recurring income"""
    bez = r["bezahlt_am"] or r["datum"]
    y = int(bez[:4])
    try:
        # v2.0.6: 10-Tage-Regel - Zahlung 01.-10.01. UND Faelligkeit zwischen 22.12. und 10.01.
        if bez[5:7] == "01" and int(bez[8:10]) <= 10 and r["datum"][:4] == str(y - 1):
            due = d_iso(r["datum"]) + datetime.timedelta(days=_frist(r["frist"]))
            if datetime.date(y - 1, 12, 22) <= due <= datetime.date(y, 1, 10) and regular_customer(r["customer_id"], r["kdnr"], y - 1):
                return y - 1, True
    except Exception:
        pass
    return y, False


def paid_invoices(year):
    out = []
    for r in q("SELECT * FROM invoices WHERE status='bezahlt' AND typ IN ('rechnung','storno') AND "
               "substr(COALESCE(NULLIF(bezahlt_am,''),datum),1,4) IN (?,?)", (str(year), str(year + 1))):
        y, ten = zufluss_year(r)
        if y == year:
            r = dict(r)
            r["zehn_tage"] = ten
            out.append(r)
    return out


def steuerakte(year):
    t = tax_inputs(year)
    return {"year": year, "docs": q("SELECT * FROM steuerakte WHERE year=? ORDER BY art, datum, id", (year,)),
            "abschluss": t.get("abschluss") or {}, "felder": ABSCHLUSS_FELDER, "arten": STEUER_ARTEN,
            "programm": {k: v for k, v in euer(year).items() if not k.endswith("_list")},
            "vergleich": abschluss_programm(year), "korrekturen": korr_list(year), "kategorien": EUER_KATEGORIEN}


def steuerakte_add(year, tmp, name, art="Sonstiges", titel="", datum="", notiz=""):
    rel = store_upload(tmp, name, os.path.join("Steuer", str(year)))
    return x("INSERT INTO steuerakte (year, art, titel, datum, file, notiz, created) VALUES (?,?,?,?,?,?,?)",
             (int(year), art, titel or os.path.splitext(name)[0], datum or "", rel, notiz or "", now_iso()))


def abschluss_save(year, data):
    r = q("SELECT data FROM taxyear WHERE year=?", (int(year),), one=True)
    d = json.loads(r["data"]) if r else {}
    ab = d.get("abschluss") or {}
    ab.update(data)
    d["abschluss"] = ab
    x("INSERT OR REPLACE INTO taxyear (year, data) VALUES (?,?)", (int(year), json.dumps(d, ensure_ascii=False)))
    return ab

# ---------------- Daten-Paket ----------------


def file_sha(rel):
    fp = os.path.join(DATA_DIR, rel or "")
    if not rel or not os.path.isfile(fp):
        return ""
    h = hashlib.sha1()
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_package(path=None, years=None):
    """write all data incl. files into one zip (merge-able into another installation)"""
    ys = [str(y) for y in (years or [])]
    yf = (lambda d: (not ys) or (d or "")[:4] in ys)
    inv = [dict(i) for i in q("SELECT * FROM invoices") if yf(i["datum"])]
    for i in inv:
        i["items"] = q("SELECT * FROM items WHERE invoice_id=? ORDER BY pos", (i["id"],))
        c = q("SELECT kdnr FROM customers WHERE id=?", (i["customer_id"],), one=True) if i["customer_id"] else None
        i["customer_kdnr"] = c["kdnr"] if c else i["kdnr"]
        pr = q("SELECT nr FROM projects WHERE id=?", (i["project_id"],), one=True) if i["project_id"] else None
        i["project_nr"] = pr["nr"] if pr else None
        m_ = re.search(r"(Belege[\\/].+?\.(?:pdf|PDF|xml))", i["notiz"] or "")
        i["orig_file"] = m_.group(1) if m_ else None
    iid_ = get_settings().get("install_id") or uuid.uuid4().hex[:12]
    set_setting("install_id", iid_)
    bel = [dict(b) for b in q("SELECT * FROM belege") if yf(b["datum"])]
    for b in bel:
        b["uid"] = json.loads(b["details"] or "{}").get("_uid") or f"{iid_}:{b['id']}"
        iv = q("SELECT nr FROM invoices WHERE id=?", (b["invoice_id"],), one=True) if b["invoice_id"] else None
        b["invoice_nr"] = iv["nr"] if iv else None
        pr = q("SELECT nr FROM projects WHERE id=?", (b["project_id"],), one=True) if b["project_id"] else None
        b["project_nr"] = pr["nr"] if pr else None
        b["sha"] = file_sha(b["file"])
    tx = [dict(t) for t in q("SELECT * FROM bank_tx") if yf(t["datum"])]
    for t in tx:
        iv = q("SELECT nr FROM invoices WHERE id=?", (t["invoice_id"],), one=True) if t["invoice_id"] else None
        t["invoice_nr"] = iv["nr"] if iv else None
    projs = [dict(p) for p in q("SELECT * FROM projects") if yf(p["start"]) or p["id"] in {i["project_id"] for i in inv}]
    for p in projs:
        c = q("SELECT kdnr FROM customers WHERE id=?", (p["customer_id"],), one=True) if p["customer_id"] else None
        p["customer_kdnr"] = c["kdnr"] if c else None
        p["files"] = []
        for f in q("SELECT * FROM project_files WHERE project_id=?", (p["id"],)):
            p["files"].append(dict(f))
    akte = [dict(a, sha=file_sha(a["file"])) for a in q("SELECT * FROM steuerakte") if (not ys) or str(a["year"]) in ys]
    pkg = {"format": "PA-Rechnung-Datenpaket", "version": APP_VERSION, "created": now_iso(),
           "customers": q("SELECT * FROM customers"), "invoices": inv, "belege": bel, "bank_tx": tx,
           "kontostand": [k for k in q("SELECT * FROM kontostand") if yf(k["datum"]) or (ys and k["datum"] == f"{min(int(y) for y in ys) - 1}-12-31")],
           "taxyear": {str(r["year"]): json.loads(r["data"]) for r in q("SELECT * FROM taxyear") if (not ys) or str(r["year"]) in ys},
           "steuerakte": akte, "projects": projs}
    path = path or os.path.join(DATA_DIR, "Export", datetime.datetime.now().strftime("Datenpaket_%Y%m%d_%H%M.zip"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("paket.json", json.dumps(pkg, ensure_ascii=False, default=str, indent=1))
        done = set()
        for rel in [b["file"] for b in bel] + [a["file"] for a in akte] + [json.loads(b["details"] or "{}").get("xml") for b in bel]:
            if rel and rel not in done and os.path.isfile(os.path.join(DATA_DIR, rel)):
                z.write(os.path.join(DATA_DIR, rel), "files/" + rel.replace("\\", "/"))
                done.add(rel)
        for i in inv:
            rel = i.get("orig_file")
            if rel and rel not in done and os.path.isfile(os.path.join(DATA_DIR, rel)):
                z.write(os.path.join(DATA_DIR, rel), "files/" + rel.replace("\\", "/"))
                done.add(rel)
        for p in projs:
            for f in p["files"]:
                ap = os.path.join(DATA_DIR, f["path"] or "")
                if os.path.isfile(ap):
                    z.write(ap, f"projekte/{p['nr']}/{f['id']}_{os.path.basename(f['path'])}")
    return path


def import_package(zpath):
    """merge a data package into this installation; existing data is never overwritten"""
    st = {k: 0 for k in ("kunden", "rechnungen", "rechnungen_aktualisiert", "belege", "bank", "kontostand", "steuerakte",
                         "projekte", "projektdateien", "uebersprungen")}
    with zipfile.ZipFile(zpath) as z:
        try:
            pkg = json.loads(z.read("paket.json").decode("utf-8"))
        except KeyError:
            raise ValueError("Keine gültige Datenpaket-Datei (paket.json fehlt).")
        if pkg.get("format") != "PA-Rechnung-Datenpaket":
            raise ValueError("Unbekanntes Paketformat.")
        names = set(z.namelist())

        def put_file(rel, sha=""):
            """copy files/<rel> into DATA_DIR; returns rel path actually used"""
            if not rel:
                return ""
            src = "files/" + rel.replace("\\", "/")
            if src not in names:
                return ""
            if os.path.isabs(rel) or os.path.splitdrive(rel)[0] or re.match(r"^[A-Za-z]:", rel):
                return ""   # v2.0.6: no absolute paths / drive letters from a package
            safe = os.path.normpath(rel.replace("/", os.sep)).lstrip("\\/")
            if safe.startswith("..") or not _pkg_inside(DATA_DIR, safe):
                return ""
            # only files below the data folders the export really writes (Belege incl. Steuer/Nachweise/Anlagen,
            # mail / inbox files and documents) - never Programm/, _umzug.json, settings or other top-level files
            parts_ = [p_ for p_ in re.split(r"[\\/]", safe) if p_]
            if len(parts_) < 2 or parts_[0].lower() not in PKG_FILE_DIRS or any(":" in p_ for p_ in parts_):
                return ""
            dst = os.path.join(DATA_DIR, safe)
            if os.path.exists(dst):
                if sha and file_sha(safe) == sha:
                    return safe
                base, ext = os.path.splitext(safe)
                safe = f"{base}_{uuid.uuid4().hex[:6]}{ext}"
                dst = os.path.join(DATA_DIR, safe)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open(src) as fi, open(dst, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            return safe

        cmap = {}
        for c in pkg.get("customers", []):
            ex = q("SELECT id, firma, name FROM customers WHERE kdnr=?", (c["kdnr"],), one=True)
            _nm = lambda r_: re.sub(r"\W", "", ((r_.get("firma") or "") + (r_.get("name") or "")).lower())
            if ex and (_nm(ex) == _nm(c) or not _nm(c)):
                cmap[c["kdnr"]] = ex["id"]
                continue
            if ex:
                # same customer number, different customer: was it already taken over under another number
                # (earlier import of the same package)? -> match by name + address instead of creating it again
                _ad = lambda r_: re.sub(r"\W", "", ((r_.get("strasse") or "") + (r_.get("plz") or "") + (r_.get("ort") or "")).lower())
                twin = None
                if _nm(c):
                    for r_ in q("SELECT * FROM customers WHERE kdnr<>?", (c["kdnr"],)):
                        if _nm(r_) == _nm(c) and (not _ad(c) or not _ad(r_) or _ad(r_) == _ad(c)):
                            twin = r_
                            break
                if twin:
                    cmap[c["kdnr"]] = twin["id"]
                    continue
                # v2.0.6: same customer number, different customer -> new number instead of mixing them up
                k_ = get_settings()["next_kdnr"]
                while q("SELECT id FROM customers WHERE kdnr=?", (k_,), one=True):
                    k_ = inc_number(k_)
                set_setting("next_kdnr", inc_number(k_))
                st.setdefault("konflikte", []).append(f"Kunde {c['kdnr']} ({c.get('firma') or c.get('name')}) gibt es hier schon als anderen Kunden - angelegt als {k_}")
                old_k = c["kdnr"]
                c = dict(c, kdnr=k_)
                cols = [k for k in ("kdnr", "anrede", "firma", "name", "strasse", "plz", "ort", "land", "tel", "mobil", "mail", "web", "notiz", "gruppe") if k in c]
                cmap[old_k] = x(f"INSERT INTO customers ({','.join(cols)}, created) VALUES ({','.join('?' * len(cols))},?)",
                                tuple(c[k] for k in cols) + (now_iso(),))
                st["kunden"] += 1
                continue
            cols = [k for k in ("kdnr", "anrede", "firma", "name", "strasse", "plz", "ort", "land", "tel", "mobil", "mail", "web", "notiz", "gruppe") if k in c]
            cmap[c["kdnr"]] = x(f"INSERT INTO customers ({','.join(cols)}, created) VALUES ({','.join('?' * len(cols))},?)",
                                tuple(c[k] for k in cols) + (now_iso(),))
            st["kunden"] += 1
        pmap = {}
        for p in pkg.get("projects", []):
            ex = q("SELECT * FROM projects WHERE nr=? AND name=?", (p["nr"], p["name"]), one=True)
            if ex:
                pid = ex["id"]
            else:
                pid = save_project({"nr": p["nr"] if not q("SELECT id FROM projects WHERE nr=?", (p["nr"],), one=True) else "",
                                    "name": p["name"], "customer_id": cmap.get(p.get("customer_kdnr")), "bereich": p.get("bereich") or "Sonstiges",
                                    "status": p.get("status") or "aktiv", "start": p.get("start"), "ende": p.get("ende"), "descr": p.get("descr") or "",
                                    "folders": json.loads(p.get("folders") or "[]"), "budget": p.get("budget") or 0})
                st["projekte"] += 1
            pmap[p["nr"]] = pid
            pr = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
            for f in p.get("files", []):
                src = f"projekte/{p['nr']}/{f['id']}_{os.path.basename(f['path'] or '')}"
                if src not in names or q("SELECT id FROM project_files WHERE project_id=? AND name=? AND COALESCE(folder,'')=?",
                                         (pid, f["name"], f["folder"] or ""), one=True):
                    continue
                base = ensure_project_folders(pr)
                parts_ = [p_ for p_ in re.split(r"[\\/]", f["folder"] or "") if p_ not in ("", ".", "..")]
                dst_dir = os.path.join(base, *[safe_name(p_) for p_ in parts_]) if parts_ else base
                if not _pkg_inside(base, os.path.relpath(dst_dir, base)):
                    continue   # v2.0.6: never write outside the project folder
                os.makedirs(dst_dir, exist_ok=True)
                dst = os.path.join(dst_dir, safe_name(f["name"]))
                if os.path.exists(dst):   # v2.0.6: never overwrite an existing file
                    b_, e_ = os.path.splitext(dst)
                    dst = f"{b_}_{uuid.uuid4().hex[:6]}{e_}"
                with z.open(src) as fi, open(dst, "wb") as fo:
                    shutil.copyfileobj(fi, fo)
                x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
                  (pid, f["folder"], f["kind"], f["name"], os.path.relpath(dst, DATA_DIR), f["size"], f["note"], f["added"] or now_iso()))
                st["projektdateien"] += 1
        imap = {}
        for i in pkg.get("invoices", []):
            ex = q("SELECT * FROM invoices WHERE nr=?", (i["nr"],), one=True)
            if ex:
                same = abs((ex["summe"] or 0) - (i["summe"] or 0)) < 0.01
                if not (same and (ex["datum"] or "") == (i["datum"] or "")):
                    # v2.0.6: same number, but a different document (two installations counted separately) -> do not touch, report
                    st.setdefault("konflikte", []).append(f"Rechnung {i['nr']}: im Paket {num_de(i['summe'] or 0)} € vom {de_date(i['datum'])}, "
                                                          f"hier {num_de(ex['summe'] or 0)} € vom {de_date(ex['datum'])} - nicht übernommen")
                    continue
                imap[i["nr"]] = ex["id"]
                if ex["status"] == "offen" and i["status"] == "bezahlt":
                    x("UPDATE invoices SET status='bezahlt', bezahlt_am=?, locked=1 WHERE id=?", (i["bezahlt_am"], ex["id"]))
                    st["rechnungen_aktualisiert"] += 1
                elif same and (ex["source"] or "") in ("seed", "import", "vdt", "") and (ex["bezahlt_am"] or "") in ("", ex["datum"]) and \
                        (ex["status"], ex["bezahlt_am"] or "") != (i["status"], i["bezahlt_am"] or "") and i["status"] in ("bezahlt", "offen"):
                    # imported/seeded invoice without own payment record -> take the reconciled payment data
                    x("UPDATE invoices SET status=?, bezahlt_am=?, locked=? WHERE id=?",
                      (i["status"], i["bezahlt_am"] or "", 1 if i["status"] == "bezahlt" else ex["locked"], ex["id"]))
                    st["rechnungen_aktualisiert"] += 1
                if same and not (ex["notiz"] or "").strip() and (i["notiz"] or "").strip():
                    nz = i["notiz"]
                    if i.get("orig_file"):
                        nr_ = put_file(i["orig_file"])
                        nz = nz.replace(i["orig_file"], nr_ or i["orig_file"])
                    x("UPDATE invoices SET notiz=? WHERE id=?", (nz, ex["id"]))
                continue
            data = dict(nr=i["nr"], customer_id=cmap.get(i.get("customer_kdnr")), kdnr=i["kdnr"], addr=json.loads(i["addr"] or "[]"),
                        datum=i["datum"], liefer=i["liefer"], auftrag=i["auftrag"], titel=i["titel"], toptext=i["toptext"],
                        foottext=i["foottext"], zahlart=i["zahlart"], frist=i["frist"], status=i["status"], bezahlt_am=i["bezahlt_am"],
                        source=i["source"] or "import", notiz=i["notiz"] or "", typ=i.get("typ") or "rechnung",
                        project_id=pmap.get(i.get("project_nr")),
                        items=[dict(qty=it["qty"], nr=it["nr"], name=it["name"], descr=it["descr"], price=it["price"],
                                    rabatt=it.get("rabatt") or 0, unit=it.get("unit") or "") for it in i["items"]])
            if i.get("orig_file"):
                newrel = put_file(i["orig_file"])
                if newrel and newrel != i["orig_file"]:
                    data["notiz"] = data["notiz"].replace(i["orig_file"], newrel)
            iid, _nr = save_invoice(data, bump=False)
            if i.get("locked"):
                x("UPDATE invoices SET locked=1 WHERE id=?", (iid,))
            imap[i["nr"]] = iid
            st["rechnungen"] += 1
        bmap = {}
        uids = {}
        for r_ in q("SELECT id, details FROM belege WHERE instr(details, '\"_uid\"') > 0"):
            try:
                uids[json.loads(r_["details"])["_uid"]] = r_["id"]
            except Exception:
                pass
        for b in pkg.get("belege", []):
            ex = None
            if b.get("uid") and b["uid"] in uids:
                bmap[b["id"]] = uids[b["uid"]]
                st["uebersprungen"] += 1
                continue
            if b.get("sha"):
                for c in q("SELECT id, file FROM belege WHERE typ=? AND datum=? AND abs(betrag-?)<0.005", (b["typ"], b["datum"], b["betrag"] or 0)):
                    if file_sha(c["file"]) == b["sha"]:
                        ex = c
                        break
            if not ex:
                ex = q("SELECT id FROM belege WHERE typ=? AND datum=? AND abs(betrag-?)<0.005 AND COALESCE(nr,'')=? AND COALESCE(partner,'')=? "
                       "AND instr(COALESCE(details,''), '\"_uid\"') = 0",(b["typ"], b["datum"], b["betrag"] or 0, b["nr"] or "", b["partner"] or ""), one=True)
            if ex:
                bmap[b["id"]] = ex["id"]
                st["uebersprungen"] += 1
                continue
            rel = put_file(b["file"], b.get("sha", ""))
            det = json.loads(b["details"] or "{}")
            if b.get("uid"):
                det["_uid"] = b["uid"]
            if det.get("xml"):
                det["xml"] = put_file(det["xml"]) or det["xml"]
            bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id, created, quelle) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (b["typ"], b["datum"], b["partner"], b["nr"], b["betrag"], b["kategorie"], b["notiz"], rel,
                     json.dumps(det, ensure_ascii=False), imap.get(b.get("invoice_nr")), pmap.get(b.get("project_nr")),
                     b.get("created") or now_iso(), b.get("quelle") or "paket"))
            bmap[b["id"]] = bid
            if b.get("uid"):
                uids[b["uid"]] = bid
            st["belege"] += 1
            try:
                if b["typ"] in ASSIST_TYPES and b["typ"] != "anlage":
                    learn_sample(b["typ"], b["kategorie"] if b["typ"] == "ausgabe" else "", b["partner"], "", bid)
            except Exception:
                pass
        for t in pkg.get("bank_tx", []):
            if q("SELECT id FROM bank_tx WHERE hash=?", (t["hash"],), one=True):
                continue
            x("INSERT INTO bank_tx (hash, datum, betrag, name, zweck, iban, invoice_id, beleg_id, status, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (t["hash"], t["datum"], t["betrag"], t["name"], t["zweck"], t["iban"], imap.get(t.get("invoice_nr")),
               bmap.get(t.get("beleg_id")), t["status"], t.get("created") or now_iso()))
            st["bank"] += 1
        for k in pkg.get("kontostand", []):
            if not q("SELECT id FROM kontostand WHERE datum=?", (k["datum"],), one=True):
                x("INSERT INTO kontostand (datum, saldo, quelle, created) VALUES (?,?,?,?)", (k["datum"], k["saldo"], k["quelle"], k.get("created") or now_iso()))
                st["kontostand"] += 1
        for y, data in (pkg.get("taxyear") or {}).items():
            r = q("SELECT data FROM taxyear WHERE year=?", (int(y),), one=True)
            cur = json.loads(r["data"]) if r else {}
            for k_, v_ in data.items():
                if k_ not in cur or cur[k_] in (None, "", 0, 0.0, False, {}):
                    cur[k_] = v_
            x("INSERT OR REPLACE INTO taxyear (year, data) VALUES (?,?)", (int(y), json.dumps(cur, ensure_ascii=False)))
        for a in pkg.get("steuerakte", []):
            dup = False
            for c in q("SELECT file FROM steuerakte WHERE year=? AND titel=?", (a["year"], a["titel"])):
                if file_sha(c["file"]) == a.get("sha"):
                    dup = True
            if dup:
                continue
            rel = put_file(a["file"], a.get("sha", ""))
            x("INSERT INTO steuerakte (year, art, titel, datum, file, notiz, created) VALUES (?,?,?,?,?,?,?)",
              (a["year"], a["art"], a["titel"], a["datum"], rel, a["notiz"], a.get("created") or now_iso()))
            st["steuerakte"] += 1
    MODEL_CACHE.clear()
    THUMB_CACHE.clear()
    return st


# ---------------- v1.6.0: decrypted view of password PDFs ----------------
VIEW_DIR = os.path.join(DATA_DIR, "_Ansicht")
shutil.rmtree(VIEW_DIR, ignore_errors=True)


def pdf_plain_bytes(fp):
    """Encrypted PDF -> decrypted bytes (standard / saved passwords), else None."""
    try:
        r = pypdf.PdfReader(fp)
        if not r.is_encrypted:
            return None
        r2, used = pdf_open(fp)
        if used is None:
            return None
        w = pypdf.PdfWriter()
        for pg in r2.pages:
            w.add_page(pg)
        b = io.BytesIO()
        w.write(b)
        return b.getvalue()
    except Exception:
        return None


def open_plain(path):
    if path.lower().endswith(".pdf") and os.path.isfile(path):
        pb = pdf_plain_bytes(path)
        if pb:
            os.makedirs(VIEW_DIR, exist_ok=True)
            dst = os.path.join(VIEW_DIR, os.path.basename(path))
            try:
                open(dst, "wb").write(pb)
                return open_path(dst)
            except Exception:
                pass
    return open_path(path)


# ---------------- v1.6.0: bulk actions (multi select) ----------------
TRASH_DIR = "_Papierkorb"


def trash_file(rel, table="belege"):
    if not rel or os.path.isabs(rel):
        return
    fp = os.path.join(DATA_DIR, rel)
    if not os.path.isfile(fp):
        return
    norm = rel.replace("\\", "/")
    for t_ in ("belege", "steuerakte", "zertifikate"):
        if q(f"SELECT COUNT(*) n FROM {t_} WHERE REPLACE(file, char(92), '/')=?", (norm,), one=True)["n"]:
            return  # still used by another entry
    dd = os.path.join(DATA_DIR, TRASH_DIR, time.strftime("%Y-%m-%d"))
    os.makedirs(dd, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(fp))
    dst, n = os.path.join(dd, base + ext), 1
    while os.path.exists(dst):
        dst = os.path.join(dd, f"{base}_{n}{ext}")
        n += 1
    try:
        shutil.move(fp, dst)
    except Exception:
        pass


def _valid_date(v):
    try:
        return datetime.date.fromisoformat(str(v or "")[:10]).isoformat()
    except ValueError:
        raise ValueError("Ungültiges Datum")


def bulk_action(d):
    kind, action, val = d.get("kind"), d.get("action"), d.get("value")
    raw_ids = d.get("ids") or []
    if not isinstance(raw_ids, list):
        raise ValueError("ids muss eine Liste sein.")
    if kind == "tmp":
        ids = [str(i) for i in raw_ids if i not in (None, "")]
    else:
        ids = []
        for i in raw_ids:
            if i in (None, ""):
                continue
            try:
                ids.append(int(i))
            except (TypeError, ValueError):
                raise ValueError(f"Ungültige ID: {i!r}")
    done, skip, errs, paths = 0, 0, [], []

    def fail(msg):
        nonlocal skip
        skip += 1
        if msg not in errs:
            errs.append(msg)

    for raw in ids:
        i = raw
        try:
            if kind == "beleg":
                b = q("SELECT b.*, i.locked AS inv_locked FROM belege b LEFT JOIN invoices i ON i.id=b.invoice_id WHERE b.id=?", (i,), one=True)
                if not b:
                    continue
                if action != "export" and b["invoice_id"] and b["inv_locked"]:
                    fail("Belege festgeschriebener Rechnungen (Anlagen) bleiben unverändert.")
                    continue
                if action == "delete":
                    x("DELETE FROM belege WHERE id=?", (i,))
                    x("DELETE FROM beleg_learn WHERE beleg_id=?", (i,))
                    x("UPDATE bank_tx SET beleg_id=NULL WHERE beleg_id=?", (i,))
                    x("UPDATE assets SET beleg_id=NULL WHERE beleg_id=?", (i,))
                    trash_file(b["file"])
                elif action == "kategorie":
                    x("UPDATE belege SET kategorie=? WHERE id=?", (val or "", i))
                elif action == "typ":
                    if val not in ("ausgabe", "einnahme", "gehalt", "anlage"):
                        raise ValueError("Unbekannte Art")
                    x("UPDATE belege SET typ=? WHERE id=?", (val, i))
                elif action == "projekt":
                    try:
                        pid_ = int(val) if val not in (None, "") else None
                    except (TypeError, ValueError):
                        raise ValueError("Ungültiges Projekt")
                    if pid_ is not None and not q("SELECT id FROM projects WHERE id=?", (pid_,), one=True):
                        raise ValueError("Projekt nicht gefunden")
                    x("UPDATE belege SET project_id=? WHERE id=?", (pid_, i))
                elif action == "datum":
                    x("UPDATE belege SET datum=? WHERE id=?", (_valid_date(val), i))
                elif action == "export":
                    if b["file"] and os.path.isfile(os.path.join(DATA_DIR, b["file"])):
                        paths.append(os.path.join(DATA_DIR, b["file"]))
                    else:
                        fail("Einige Belege haben keine Datei.")
                        continue
                else:
                    raise ValueError("Unbekannte Aktion")
            elif kind == "invoice":
                r_ = q("SELECT * FROM invoices WHERE id=?", (i,), one=True)
                if not r_:
                    continue
                if action == "delete":
                    if r_["locked"]:
                        fail("Festgeschriebene Rechnungen können nicht gelöscht werden – bitte stornieren.")
                        continue
                    if callable(globals().get("inv_delete")):
                        # m65 cleans up all links (storno, references ...) - same path as the single delete
                        inv_delete(i)
                        done += 1
                        continue
                    x("UPDATE recurring SET aktiv=0 WHERE invoice_id=?", (i,))
                    x("DELETE FROM items WHERE invoice_id=?", (i,))
                    x("UPDATE project_entries SET invoice_id=NULL WHERE invoice_id=?", (i,))
                    x("UPDATE lessons SET invoice_id=NULL WHERE invoice_id=?", (i,))
                    x("UPDATE belege SET invoice_id=NULL WHERE invoice_id=?", (i,))
                    x("DELETE FROM mahnungen WHERE invoice_id=?", (i,))
                    x("DELETE FROM invoices WHERE id=?", (i,))
                elif action in ("bezahlt", "offen"):
                    if r_["status"] == "entwurf" or r_["typ"] not in ("rechnung", "storno"):
                        fail("Entwürfe, Angebote und Auftragsbestätigungen werden nicht als bezahlt markiert.")
                        continue
                    if r_["status"] == "storniert":
                        fail("Stornierte Rechnungen bleiben unverändert.")
                        continue
                    x("UPDATE invoices SET status=?, bezahlt_am=?, updated=? WHERE id=?",
                      (action, _valid_date(val or today()) if action == "bezahlt" else "", now_iso(), i))
                    if action == "bezahlt":
                        lock_invoice(i)
                elif action == "pdf":
                    inv = get_invoice(i)
                    if inv["status"] == "entwurf":
                        fail("Entwürfe haben noch keine Nummer – erst fertigstellen.")
                        continue
                    lock_invoice(i)
                    s = get_settings()
                    path = invoice_pdf_path(inv, s)
                    write_file(path, render_invoice_pdf(inv, s))
                    paths.append(path)
                else:
                    raise ValueError("Unbekannte Aktion")
            elif kind == "customer":
                if action == "delete":
                    n = q("SELECT COUNT(*) n FROM invoices WHERE customer_id=?", (i,), one=True)["n"]
                    if n:
                        fail("Kunden mit Rechnungen bleiben erhalten.")
                        continue
                    x("DELETE FROM customers WHERE id=?", (i,))
                elif action == "gruppe":
                    x("UPDATE customers SET gruppe=? WHERE id=?", (val or "", i))
                else:
                    raise ValueError("Unbekannte Aktion")
            elif kind == "article":
                if action == "delete":
                    x("DELETE FROM articles WHERE id=?", (i,))
                elif action in ("aktiv", "inaktiv"):
                    x("UPDATE articles SET active=? WHERE id=?", (1 if action == "aktiv" else 0, i))
                elif action == "kategorie":
                    x("UPDATE articles SET cat=? WHERE id=?", (val or "", i))
                else:
                    raise ValueError("Unbekannte Aktion")
            elif kind == "bank":
                if action == "delete":
                    x("DELETE FROM bank_tx WHERE id=?", (i,))
                elif action == "ignore":
                    x("UPDATE bank_tx SET status='ignore' WHERE id=?", (i,))
                else:
                    raise ValueError("Unbekannte Aktion")
            elif kind in ("asset", "fahrt", "zert", "steuerakte", "kontostand"):
                tbl = {"asset": "assets", "fahrt": "fahrten", "zert": "zertifikate", "steuerakte": "steuerakte", "kontostand": "kontostand"}[kind]
                if action != "delete":
                    raise ValueError("Unbekannte Aktion")
                row = q(f"SELECT * FROM {tbl} WHERE id=?", (i,), one=True)
                if not row:
                    continue
                x(f"DELETE FROM {tbl} WHERE id=?", (i,))
                if kind in ("zert", "steuerakte") and row["file"]:
                    trash_file(row["file"], tbl)
            elif kind == "pending":
                if action != "discard":
                    raise ValueError("Unbekannte Aktion")
                r_ = q("SELECT * FROM pending_belege WHERE id=?", (i,), one=True)
                if r_:
                    fp = os.path.join(DATA_DIR, r_["file"] or "")
                    if r_["file"] and os.path.isfile(fp):
                        os.remove(fp)
                    x("DELETE FROM pending_belege WHERE id=?", (r_["id"],))
            elif kind == "tmp":
                if action != "discard":
                    raise ValueError("Unbekannte Aktion")
                t = TMP.pop(str(raw), None)
                if t and os.path.isfile(t["path"]):
                    os.remove(t["path"])
            else:
                raise ValueError("Unbekannte Liste")
            done += 1
        except ValueError as e:
            fail(str(e))
        except Exception as e:
            traceback.print_exc()
            fail(f"Fehler bei Eintrag {raw}: {e}")
    out = {"ok": True, "done": done, "skipped": skip, "errors": errs}
    if paths and action == "export":
        dd = os.path.join(DATA_DIR, "Export", "Belege_" + time.strftime("%Y-%m-%d_%H%M%S"))
        os.makedirs(dd, exist_ok=True)
        for p_ in paths:
            base, ext = os.path.splitext(os.path.basename(p_))
            dst, n = os.path.join(dd, base + ext), 1
            while os.path.exists(dst):
                dst = os.path.join(dd, f"{base}_{n}{ext}")
                n += 1
            pb = pdf_plain_bytes(p_) if ext.lower() == ".pdf" and d.get("entschluesseln") else None
            if pb:
                open(dst, "wb").write(pb)
            else:
                shutil.copy2(p_, dst)
        out["folder"] = dd
        open_path(dd)
    elif paths:
        out["folder"] = os.path.dirname(paths[-1])
        open_path(out["folder"])
    return out
