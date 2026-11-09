# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m19_http
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

def ui_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
    return d if os.path.isdir(d) else res_path("ui")


def ui_core_js():
    """v3.2.0: the former inline script of ui.html, split into ui/kern_NN_*.js (one script, same order)"""
    d, out = ui_dir(), []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if re.fullmatch(r"kern_\d\d\w*\.js", fn):
                out.append(f"// ---- {fn} ----\n" + open(os.path.join(d, fn), encoding="utf-8").read())
    return "\n".join(out)


# v3.5.1: UI files merged in v3.1.0 - an old copy next to the merged file must not be loaded twice
UI_REPLACED = {"m44_bescheid.js": "m44_steuerjahr.js", "m45_jahr.js": "m44_steuerjahr.js", "m46_angleich.js": "m44_steuerjahr.js",
               "m98_gmail.js": "m98_mail.js", "m99_privat.js": "m98_mail.js", "m99c_outlook.js": "m98_mail.js"}
UI_SKIPPED = []


def ui_modules_js():
    d, out = ui_dir(), []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn in UI_REPLACED and os.path.isfile(os.path.join(d, UI_REPLACED[fn])):
                if fn not in UI_SKIPPED:
                    UI_SKIPPED.append(fn)
                continue
            if re.fullmatch(r"\w+\.js", fn) and not fn.startswith("kern_"):
                out.append(f"// ---- {fn} ----\n" + open(os.path.join(d, fn), encoding="utf-8").read())
    return "\n;\n".join(out)


class Handler(BaseHTTPRequestHandler):
    server_version = "PARechnung/" + APP_VERSION

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # v3.6.2: no program address in the Referer when a link opens another site; foreign pages cannot embed/read
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        return True

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _json(self):
        b = self._body()
        return json.loads(b.decode("utf-8")) if b else {}

    def _save_tmp(self):
        name = unquote(self.headers.get("X-Filename") or "datei")
        n = int(self.headers.get("Content-Length") or 0)
        tmp = os.path.join(DATA_DIR, "_tmp_" + uuid.uuid4().hex + os.path.splitext(name)[1])
        with open(tmp, "wb") as f:
            left = n
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        return tmp, os.path.basename(name)

    def _bad_host(self):
        # v2.0.6: DNS-rebinding protection - only requests addressed to this computer
        h = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if h not in ("127.0.0.1", "localhost", "::1", ""):
            return True
        # v2.1.1: requests started by a foreign web page (img/fetch/form from another site) are refused -
        # browsers mark them with Sec-Fetch-Site: cross-site; a top-level navigation (link) stays possible
        if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site" and \
                (self.headers.get("Sec-Fetch-Mode") or "").lower() != "navigate":
            return True
        return False

    def do_GET(self):
        if self._bad_host():
            return self._send(403, b"", "text/plain")
        try:
            u = urlparse(self.path)
            p = u.path
            qs = {k: v[0] for k, v in parse_qs(u.query).items()}
            r_ = ext_get(self, p, qs)
            if r_ is not None:
                return r_
            if p == "/ui/_kern.js":
                return self._send(200, ui_core_js(), "application/javascript; charset=utf-8")
            if p == "/ui/_all.js":
                return self._send(200, ui_modules_js(), "application/javascript; charset=utf-8")
            if p in ("/", "/index.html"):
                html = open(res_path("ui.html"), "rb").read()
                return self._send(200, html, "text/html; charset=utf-8")
            if p == "/logo":
                lp = os.path.join(ASSET_DIR, get_settings().get("logo") or "logo.jpg")
                if os.path.exists(lp):
                    return self._send(200, open(lp, "rb").read(), mimetypes.guess_type(lp)[0] or "image/jpeg")
                return self._send(404, b"", "text/plain")
            if p == "/api/bootstrap":
                return self._send(200, bootstrap())
            if p == "/api/invoice":
                return self._send(200, get_invoice(int(qs["id"])))
            if p.startswith("/preview/"):
                _, _, tok, idx = p.split("/")
                img = PREVIEW.get(tok, [])
                i = int(idx.split(".")[0])
                if i < len(img):
                    return self._send(200, img[i], "image/png")
                return self._send(404, b"", "text/plain")
            if p == "/api/invoice/pdf":
                inv = get_invoice(int(qs["id"]))
                if not inv:
                    return self._send(404, {"error": "not found"})
                # v2.1.0: header must stay latin-1 / without quotes (en dash or quote in the number gave error 500)
                fn_ = re.sub(r"[^0-9A-Za-z._-]", "_", str(inv["nr"] or ""))
                return self._send(200, render_invoice_pdf(inv), "application/pdf",
                                  {"Content-Disposition": f'inline; filename="rechnung_{fn_}.pdf"'})
            if p == "/api/stats":
                return self._send(200, stats(int(qs.get("year") or datetime.date.today().year)))
            if p == "/api/dups":
                return self._send(200, find_duplicates())
            if p == "/api/pickfile":
                fp_ = os.path.normpath(qs.get("path") or "")
                if fp_ not in PICKED or not os.path.isfile(fp_):
                    return self._send(403, b"", "text/plain")
                with open(fp_, "rb") as fh:
                    data = fh.read()
                return self._send(200, data, mimetypes.guess_type(fp_)[0] or "application/octet-stream")
            if p == "/api/stats/detail":
                yv = qs.get("year") or ""
                return self._send(200, stats_detail(int(yv) if yv.isdigit() else None))
            if p == "/api/tax":
                return self._send(200, tax_calc(int(qs.get("year") or datetime.date.today().year)))
            if p == "/api/project":
                return self._send(200, get_project(int(qs["id"])))
            if p == "/api/thumb":
                fp = os.path.abspath(os.path.join(DATA_DIR, qs.get("path") or ""))
                if os.path.normcase(os.path.commonpath([fp, os.path.abspath(DATA_DIR)])) != os.path.normcase(os.path.abspath(DATA_DIR)):
                    return self._send(403, b"", "text/plain")
                data = file_thumb(qs["path"])
                if data:
                    return self._send(200, data, "image/jpeg", {"Cache-Control": "max-age=3600"})
                return self._send(404, b"", "text/plain")
            if p == "/api/file":
                # v2.1.0: compare both sides as absolute paths (a relative or "..\" data folder gave error 500)
                root_ = os.path.abspath(DATA_DIR)
                fp = os.path.abspath(os.path.join(root_, qs.get("path") or ""))
                if os.path.normcase(os.path.commonpath([fp, root_])) != os.path.normcase(root_):
                    return self._send(403, b"", "text/plain")
                if not os.path.isfile(fp):
                    return self._send(404, b"", "text/plain")
                pb = pdf_plain_bytes(fp) if fp.lower().endswith(".pdf") else None
                return self._send(200, pb or open(fp, "rb").read(), mimetypes.guess_type(fp)[0] or "application/octet-stream")
            if p == "/api/customer/history":
                cid = int(qs["id"])
                return self._send(200, q("SELECT id, nr, datum, summe, status, titel FROM invoices WHERE customer_id=? ORDER BY datum DESC", (cid,)))
            if p == "/api/export/csv":
                year = int(qs["year"])
                e = euer(year)
                kz = lambda k: "Z{0} Kz{1}".format(*EUER_FORM.get(k, EUER_FORM["Sonstige Betriebsausgaben"])[:2])
                def _t(v):
                    # v2.1.0: text field - quote ; " and line breaks, neutralise formulas (= + - @ at the start)
                    v = str(v if v is not None else "").replace("\r", " ").replace("\n", " ")
                    if v[:1] in ("=", "+", "-", "@"):
                        v = "'" + v
                    return '"' + v.replace('"', '""') + '"' if (";" in v or '"' in v) else v

                def _row(*cells):
                    return ";".join(cells)
                lines = ["Typ;Datum;Bezahlt;Nr;Partner;Kategorie;Anlage EÜR;Betrag"]
                for r in e["paid_list"]:
                    lines.append(_row("Einnahme", de_date(r['datum']), de_date(r['bezahlt_am']), _t(r['nr']), _t(inv_name(r)), "Erlöse",
                                      kz('_einnahmen_ku'), num_de(r['summe'])))
                for r in e["einnahmen_list"]:
                    lines.append(_row("Einnahme", de_date(r['datum']), de_date(r['datum']), _t(r['nr']), _t(r['partner']), "Sonstige Erlöse",
                                      kz('_einnahmen_ku'), num_de(r['betrag'])))
                for r in e["ausgaben_list"]:
                    lines.append(_row("Ausgabe", de_date(r['datum']), "", _t(r['nr']), _t(r['partner']), _t(r['kategorie']),
                                      kz(r['kategorie'] or ''), "-" + num_de(r['betrag'])))
                for a in e["afa_list"]:
                    kk = "Arbeitsmittel / Equipment (GWG)" if a["methode"] == "gwg" else "Abschreibung (AfA)"
                    lines.append(_row("Ausgabe", f"31.12.{year}", "", "", _t(a['bezeichnung']), kk, kz(kk), "-" + num_de(a['afa'])))
                if e["fahrten"]["dienst_eur"]:
                    lines.append(_row("Ausgabe", f"31.12.{year}", "", "", f"Fahrten Privat-Pkw {num_de(e['fahrten']['dienst_km'], 1)} km", "Fahrtkosten",
                                      kz('_fahrten'), "-" + num_de(e['fahrten']['dienst_eur'])))
                if e["kategorien"].get("Homeoffice-Tagespauschale"):
                    lines.append(_row("Ausgabe", f"31.12.{year}", "", "", "Homeoffice-Tagespauschale", "Homeoffice", kz('_homeoffice'),
                                      "-" + num_de(e['kategorien']['Homeoffice-Tagespauschale'])))
                lines.append("")
                lines.append("Anlage EÜR (Summen);;;;;;;")
                for z, k_, lbl, v in euer_form(year):
                    lines.append(_row(f"Zeile {z}", f"Kz {k_}", "", "", _t(lbl), "", "", num_de(v)))
                out = os.path.join(DATA_DIR, "Export", f"EUER_{year}.csv")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                write_file(out, "\n".join(lines), text=True)
                open_path(out)
                return self._send(200, {"ok": True, "path": out})
            return self._send(404, {"error": "not found"})
        except ValueError as e:
            return self._send(200, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def _foreign(self):
        o = self.headers.get("Origin")
        if not o:
            return False
        pt = self.server.server_address[1]
        return o not in (f"http://127.0.0.1:{pt}", f"http://localhost:{pt}")

    def do_POST(self):
        if self._bad_host() or self._foreign():
            return self._send(403, {"ok": False, "error": "forbidden"})
        try:
            p = urlparse(self.path).path
            if p in HOOK_UPLOAD:
                tmp, name = self._save_tmp()
                return HOOK_UPLOAD[p](self, tmp, name)
            if p in EXT_UPLOADS:
                tmp, name = self._save_tmp()
                return ext_upload(self, p, tmp, name)
            if p in ("/api/upload/beleg", "/api/upload/project", "/api/upload/logo", "/api/upload/vdt", "/api/upload/anlage"):
                tmp, name = self._save_tmp()
                if p == "/api/upload/beleg":
                    return self._send(200, {"items": prepare_results(analyze_any(tmp, name), tmp, name)})
                if p == "/api/upload/anlage":
                    iid = int(self.headers.get("X-Invoice") or 0)
                    if iid:
                        # v2.1.0: same rule as /api/anlage/remove - a locked invoice keeps its attachments
                        li_ = q("SELECT locked FROM invoices WHERE id=?", (iid,), one=True)
                        if not li_ or li_["locked"]:
                            try:
                                os.remove(tmp)
                            except OSError:
                                pass
                            raise ValueError("Die Rechnung ist festgeschrieben - Anlagen können nicht mehr geändert werden."
                                             if li_ else "Rechnung nicht gefunden.")
                    rel = store_upload(tmp, name, "Anlagen")
                    bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            ("anlage", today(), name, "", 0, "", "Anlage zur Rechnung", rel, "{}", iid or None, now_iso()))
                    return self._send(200, {"ok": True, "id": bid, "file": rel, "partner": name})
                if p == "/api/upload/project":
                    pid = int(self.headers.get("X-Project"))
                    folder = unquote(self.headers.get("X-Folder") or "") or None
                    return self._send(200, add_project_file(pid, tmp, name, folder))
                if p == "/api/upload/logo":
                    ext = os.path.splitext(name)[1].lower() or ".png"
                    dst = os.path.join(ASSET_DIR, "logo_custom" + ext)
                    shutil.move(tmp, dst)
                    set_setting("logo", os.path.basename(dst))
                    return self._send(200, {"ok": True})
                if p == "/api/upload/vdt":
                    r = import_vdt(tmp)
                    os.remove(tmp)
                    return self._send(200, r)
            d = self._json()
            r_ = ext_post(self, p, d)
            if r_ is not None:
                return r_
            if p == "/api/customer/save":
                with DOC_LOCK:     # v2.1.0: two parallel saves got the same customer number
                    d["kdnr"] = str(d.get("kdnr") or "").strip()
                    if not d["kdnr"]:
                        k = get_settings()["next_kdnr"]
                        while q("SELECT id FROM customers WHERE kdnr=?", (k,), one=True):
                            k = inc_number(k)
                        d["kdnr"] = k
                        set_setting("next_kdnr", inc_number(k))
                    dupk = q("SELECT id FROM customers WHERE kdnr=?", (d["kdnr"],), one=True)
                    if dupk and str(dupk["id"]) != str(d.get("id") or ""):
                        return self._send(200, {"ok": False, "error": f"Kundennummer {d['kdnr']} ist schon vergeben."})
                    cols = ["kdnr", "anrede", "firma", "name", "strasse", "plz", "ort", "land", "tel", "mobil", "mail", "web", "notiz", "gruppe"]
                    if d.get("id"):
                        x(f"UPDATE customers SET {', '.join(c + '=?' for c in cols)} WHERE id=?", tuple(d.get(c, "") for c in cols) + (d["id"],))
                        cid = d["id"]
                    else:
                        cid = x(f"INSERT INTO customers ({', '.join(cols)}, created) VALUES ({','.join('?' * (len(cols) + 1))})",
                                tuple(d.get(c, "") for c in cols) + (now_iso(),))
                return self._send(200, {"ok": True, "id": cid})
            if p == "/api/customer/delete":
                n = q("SELECT COUNT(*) n FROM invoices WHERE customer_id=?", (d["id"],), one=True)["n"]
                if n:
                    return self._send(200, {"ok": False, "error": f"Kunde hat {n} Rechnung(en) und kann nicht gelöscht werden."})
                x("DELETE FROM customers WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/article/save":
                cols = ["nr", "name", "descr", "price", "unit", "cat", "active", "sort"]
                vals = tuple(d.get(c, "" if c not in ("price", "active", "sort") else 0) for c in cols)
                if d.get("id"):
                    x(f"UPDATE articles SET {', '.join(c + '=?' for c in cols)} WHERE id=?", vals + (d["id"],))
                    aid = d["id"]
                else:
                    aid = x(f"INSERT INTO articles ({', '.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
                return self._send(200, {"ok": True, "id": aid})
            if p == "/api/article/delete":
                x("DELETE FROM articles WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/text/save":
                if d.get("id"):
                    x("UPDATE texts SET kind=?, text=? WHERE id=?", (d["kind"], d["text"], d["id"]))
                else:
                    x("INSERT INTO texts (kind, text, sort) VALUES (?,?,99)", (d["kind"], d["text"]))
                return self._send(200, {"ok": True})
            if p == "/api/text/delete":
                x("DELETE FROM texts WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/invoice/save":
                iid, nr = save_invoice(d)
                return self._send(200, {"ok": True, "id": iid, "nr": nr})
            if p == "/api/invoice/preview":
                inv = dict(d)
                if not inv.get("nr"):
                    # v2.1.0: number of the document's own series (an offer showed the next INVOICE number)
                    inv["nr"] = next_doc_nr(inv.get("typ") or "rechnung")[1]
                pdf = render_invoice_pdf(inv)
                pngs = pdf_to_pngs(pdf)
                tok = uuid.uuid4().hex[:12]
                # v2.1.0: keep the last few previews - a slower older request no longer deletes the images
                # of the newer one (empty / stale preview while typing)
                for k_ in list(PREVIEW)[:-3]:
                    PREVIEW.pop(k_, None)
                PREVIEW[tok] = pngs
                return self._send(200, {"token": tok, "pages": len(pngs), "summe": round(sum(line_total(i) for i in inv.get("items") or []), 2)})
            if p == "/api/invoice/export":
                inv = get_invoice(int(d["id"]))
                if inv["status"] == "entwurf":
                    raise ValueError("Bitte den Entwurf erst fertigstellen (dann bekommt er eine Rechnungsnummer).")
                lock_invoice(inv["id"])
                s = get_settings()
                path = invoice_pdf_path(inv, s)
                write_file(path, render_invoice_pdf(inv, s))
                if d.get("open", True):
                    open_path(path)
                return self._send(200, {"ok": True, "path": path})
            if p == "/api/invoice/status":
                # v2.1.0: only payment states here - "entwurf"/"storniert" on an issued invoice took it out of
                # the revenue without a cancellation document (storno has its own route)
                if d.get("status") not in ("offen", "bezahlt"):
                    raise ValueError("Ungültiger Status.")
                if not q("SELECT id FROM invoices WHERE id=?", (d.get("id"),), one=True):
                    raise ValueError("Rechnung nicht gefunden.")
                x("UPDATE invoices SET status=?, bezahlt_am=?, updated=? WHERE id=?",
                  (d["status"], d.get("bezahlt_am") or (today() if d["status"] == "bezahlt" else ""), now_iso(), d["id"]))
                if d["status"] == "bezahlt":
                    lock_invoice(d["id"])
                return self._send(200, {"ok": True})
            if p == "/api/invoice/delete":
                r_ = q("SELECT locked, typ FROM invoices WHERE id=?", (d["id"],), one=True)
                if r_ and r_["locked"]:
                    raise ValueError("Festgeschriebene Rechnungen können nicht gelöscht werden - bitte stornieren.")
                x("UPDATE recurring SET aktiv=0 WHERE invoice_id=?", (d["id"],))
                x("DELETE FROM items WHERE invoice_id=?", (d["id"],))
                x("UPDATE project_entries SET invoice_id=NULL WHERE invoice_id=?", (d["id"],))
                x("UPDATE lessons SET invoice_id=NULL WHERE invoice_id=?", (d["id"],))
                x("UPDATE belege SET invoice_id=NULL WHERE invoice_id=?", (d["id"],))
                x("DELETE FROM mahnungen WHERE invoice_id=?", (d["id"],))
                x("DELETE FROM invoices WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/anlage/remove":
                b_ = q("SELECT i.locked FROM belege b LEFT JOIN invoices i ON i.id=b.invoice_id WHERE b.id=?", (d["id"],), one=True)
                if b_ and b_["locked"]:
                    raise ValueError("Die Rechnung ist festgeschrieben - Anlagen können nicht mehr geändert werden.")
                x("UPDATE belege SET invoice_id=NULL WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/beleg/save":
                return self._send(200, save_beleg(d))
            if p == "/api/beleg/update":
                old_ = q("SELECT b.invoice_id, i.locked FROM belege b LEFT JOIN invoices i ON i.id=b.invoice_id WHERE b.id=?", (d["id"],), one=True)
                new_ = q("SELECT locked FROM invoices WHERE id=?", (d.get("invoice_id"),), one=True) if d.get("invoice_id") else None
                if d.get("typ") == "anlage" and old_ and (old_["invoice_id"] or None) != (d.get("invoice_id") or None) and \
                        ((old_["locked"]) or (new_ and new_["locked"] and old_["invoice_id"] is not None)):
                    raise ValueError("Die Rechnung ist festgeschrieben - Anlagen können nicht mehr geändert werden.")
                x("UPDATE belege SET typ=?, datum=?, partner=?, nr=?, betrag=?, kategorie=?, notiz=?, details=?, invoice_id=?, project_id=? WHERE id=?",
                  (d["typ"], d["datum"], d.get("partner", ""), d.get("nr", ""), float(d.get("betrag") or 0), d.get("kategorie", ""),
                   d.get("notiz", ""), json.dumps(d.get("details") or {}, ensure_ascii=False), d.get("invoice_id") or None,
                   d.get("project_id") or None, d["id"]))
                try:
                    learn_correction(d)
                except Exception:
                    traceback.print_exc()
                return self._send(200, {"ok": True})
            if p == "/api/beleg/delete":
                x("DELETE FROM belege WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/beleg/discard":
                t = TMP.pop(d.get("token"), None)
                if t and os.path.exists(t["path"]):
                    os.remove(t["path"])
                return self._send(200, {"ok": True})
            if p == "/api/tax/save":
                r_ = q("SELECT data FROM taxyear WHERE year=?", (int(d["year"]),), one=True)
                cur_ = json.loads(r_["data"]) if r_ else {}
                cur_.update(d["inputs"] or {})
                x("INSERT OR REPLACE INTO taxyear (year, data) VALUES (?,?)", (int(d["year"]), json.dumps(cur_, ensure_ascii=False)))
                return self._send(200, tax_calc(int(d["year"])))
            if p == "/api/report/jahresbericht":
                year = int(d["year"])
                out = os.path.join(DATA_DIR, "Export", f"Jahresbericht_{year}.pdf")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                write_file(out, jahresbericht_pdf(year))
                if not os.environ.get("PA_RECHNUNG_NO_OPEN"):
                    open_path(out)
                return self._send(200, {"ok": True, "path": out})
            if p == "/api/report/year":
                year = int(d["year"])
                out = os.path.join(DATA_DIR, "Export", f"Jahresabrechnung_{year}.pdf")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                write_file(out, year_report_pdf(year))
                open_path(out)
                return self._send(200, {"ok": True, "path": out})
            if p == "/api/project/save":
                return self._send(200, {"ok": True, "id": save_project(d)})
            if p == "/api/project/delete":
                x("DELETE FROM project_files WHERE project_id=?", (d["id"],))
                x("DELETE FROM project_entries WHERE project_id=?", (d["id"],))
                x("UPDATE invoices SET project_id=NULL WHERE project_id=?", (d["id"],))
                x("DELETE FROM projects WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True, "info": "Projekt entfernt. Die Dateien bleiben im Projektordner erhalten."})
            if p == "/api/project/entry/save":
                cols = ["project_id", "datum", "art", "nr", "name", "descr", "qty", "unit", "price"]
                vals = tuple(d.get(c) if c not in ("qty", "price") else float(d.get(c) or 0) for c in cols)
                if d.get("id"):
                    x(f"UPDATE project_entries SET {', '.join(c + '=?' for c in cols)} WHERE id=?", vals + (d["id"],))
                else:
                    x(f"INSERT INTO project_entries ({', '.join(cols)}, created) VALUES ({','.join('?' * (len(cols) + 1))})", vals + (now_iso(),))
                return self._send(200, {"ok": True})
            if p == "/api/project/entry/delete":
                x("DELETE FROM project_entries WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/project/file/update":
                f = q("SELECT * FROM project_files WHERE id=?", (d["id"],), one=True)
                pr = q("SELECT * FROM projects WHERE id=?", (f["project_id"],), one=True)
                newfolder = d.get("folder", f["folder"])
                path = f["path"]
                if newfolder != f["folder"]:
                    base = ensure_project_folders(pr)
                    dst_dir = os.path.abspath(os.path.join(base, *(newfolder or "").replace("\\", "/").split("/")))
                    # v2.1.0: target must stay inside the project folder ("../.." moved the file anywhere)
                    if os.path.normcase(os.path.commonpath([dst_dir, os.path.abspath(base)])) != os.path.normcase(os.path.abspath(base)):
                        raise ValueError("Ungültiger Ordner.")
                    os.makedirs(dst_dir, exist_ok=True)
                    dst = os.path.join(dst_dir, f["name"])
                    root, ext = os.path.splitext(dst)
                    k = 2
                    while os.path.exists(dst):
                        dst = f"{root} ({k}){ext}"
                        k += 1
                    src = os.path.join(DATA_DIR, path)
                    if os.path.exists(src):
                        shutil.move(src, dst)
                        path = os.path.relpath(dst, DATA_DIR)
                        x("UPDATE project_files SET name=? WHERE id=?", (os.path.basename(dst), d["id"]))
                    else:
                        newfolder = f["folder"]
                x("UPDATE project_files SET folder=?, kind=?, note=?, path=? WHERE id=?",
                  (newfolder, d.get("kind", f["kind"]), d.get("note", f["note"]), path, d["id"]))
                THUMB_CACHE.pop(f["path"], None)
                return self._send(200, {"ok": True})
            if p == "/api/project/file/delete":
                x("DELETE FROM project_files WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True, "info": "Aus dem Projekt entfernt (Datei bleibt im Ordner)."})
            if p == "/api/project/sync":
                pr = get_project(int(d["id"]))
                base = pr["abs_dir"]
                known = {f["path"] for f in pr["files"]}
                added = 0
                for root, _, files in os.walk(base):
                    for fn in files:
                        rel = os.path.relpath(os.path.join(root, fn), DATA_DIR)
                        if rel in known:
                            continue
                        folder = os.path.relpath(root, base).replace("\\", "/")
                        folder = "" if folder == "." else folder
                        kind, _ = detect_kind(fn, pr["folders"])
                        x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
                          (pr["id"], folder, kind, fn, rel, os.path.getsize(os.path.join(root, fn)), "", now_iso()))
                        added += 1
                        if folder and folder not in pr["folders"]:
                            pr["folders"].append(folder)
                x("UPDATE projects SET folders=? WHERE id=?", (json.dumps(pr["folders"], ensure_ascii=False), pr["id"]))
                return self._send(200, {"ok": True, "added": added})
            if p == "/api/project/to_invoice":
                pr = get_project(int(d["id"]))
                ids = d.get("entry_ids") or [e["id"] for e in pr["entries"] if not e["invoice_id"]]
                ents = [e for e in pr["entries"] if e["id"] in ids]
                c = pr["customer"]
                s = get_settings()
                draft = {"customer_id": c["id"] if c else None, "kdnr": c["kdnr"] if c else "", "addr": address_lines(c),
                         "project_id": pr["id"], "datum": today(), "liefer": max([e["datum"] for e in ents] or [today()]),
                         "auftrag": pr["start"], "titel": f"Rechnung {pr['name']}", "toptext": s["default_top"],
                         "foottext": s["default_foot"], "zahlart": s.get("zahlart", "Ueberweisung"), "frist": s["frist"],
                         "items": [{"qty": e["qty"], "nr": e["nr"] or "", "name": e["name"],
                                    "descr": "\n".join(v for v in ((de_date(e["datum"]) + " " + (e["descr"] or "")).strip(),) if v),
                                    "price": e["price"], "rabatt": 0, "entry_id": e["id"]} for e in ents],
                         "entry_ids": ids}
                return self._send(200, draft)
            if p == "/api/template/save":
                if d.get("id"):
                    x("UPDATE templates SET name=?, bereich=?, folders=? WHERE id=?", (d["name"], d.get("bereich", ""), json.dumps(d["folders"], ensure_ascii=False), d["id"]))
                else:
                    x("INSERT INTO templates (name, bereich, folders) VALUES (?,?,?)", (d["name"], d.get("bereich", ""), json.dumps(d["folders"], ensure_ascii=False)))
                return self._send(200, {"ok": True})
            if p == "/api/template/delete":
                x("DELETE FROM templates WHERE id=?", (d["id"],))
                return self._send(200, {"ok": True})
            if p == "/api/settings/save":
                for k, v in d.items():
                    if k == "smtp_pass_new":
                        if v:
                            set_setting("smtp_pass", protect_secret(v))
                        continue
                    if k in ("smtp_pass", "tt_pass", "tt_session"):
                        continue
                    set_setting(k, v)
                return self._send(200, {"ok": True})
            if p == "/api/backup":
                fn = make_backup(True)
                err = copy_to_target(fn)
                open_path(BACKUP_DIR)
                return self._send(200, {"ok": True, "path": fn, "warn": err})
            if p == "/api/dups/ignore":
                return self._send(200, dup_ignore(d.get("sig")))
            if p == "/api/pick":
                return self._send(200, api_pick(d))
            if p == "/api/open":
                path = d.get("path", "")
                if not os.path.isabs(path):
                    path = os.path.join(DATA_DIR, path)
                if d.get("folder"):
                    path = path if os.path.isdir(path) else os.path.dirname(path)
                    os.makedirs(path, exist_ok=True)
                    return self._send(200, {"ok": open_path(path)})
                return self._send(200, {"ok": open_plain(path)})
            return self._send(404, {"error": "not found"})
        except ValueError as e:
            return self._send(200, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(e)})
