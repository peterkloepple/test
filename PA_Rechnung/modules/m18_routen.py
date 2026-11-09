# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m18_routen
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

def ext_get(h, p, qs):
    if p in HOOK_GET:
        return HOOK_GET[p](h, qs)
    if p == "/api/search":
        return h._send(200, global_search(qs.get("q", "")))
    if p == "/api/unterricht/month":
        r_ = lesson_month(qs["year"], qs["month"], qs.get("customer_id"))
        r_["payers"] = lesson_payers(qs["year"], qs["month"])
        return h._send(200, r_)
    if p == "/api/afa":
        return h._send(200, afa_year(int(qs.get("year") or datetime.date.today().year)))
    if p == "/api/fahrten":
        return h._send(200, fahrten_year(int(qs.get("year") or datetime.date.today().year)))
    if p == "/api/mail/prepare":
        return h._send(200, mail_prepare(int(qs["doc_id"]) if qs.get("doc_id") else None, int(qs["mahnung_id"]) if qs.get("mahnung_id") else None))
    if p == "/api/assist/status":
        return h._send(200, assist_status())
    if p == "/api/update/info":
        return h._send(200, update_info())
    if p == "/api/steuerakte":
        return h._send(200, steuerakte(int(qs.get("year") or datetime.date.today().year)))
    if p == "/api/kontostand":
        return h._send(200, {"info": kontostand_info(), "liste": q("SELECT * FROM kontostand ORDER BY datum DESC")})
    if p == "/api/pending/list":
        return h._send(200, pending_list())
    if p == "/api/bank/history":
        return h._send(200, q("SELECT * FROM bank_tx ORDER BY datum DESC LIMIT 500"))
    return None


def ext_upload(h, p, tmp, name):
    try:
        if p == "/api/upload/bank":
            pw = unquote(h.headers.get("X-Password") or "") or None
            low_ = name.lower()
            sal = None
            try:
                if low_.endswith(".pdf") or open(tmp, "rb").read(5) == b"%PDF-":
                    text_ = pdf_text_all(tmp, pw)
                    if ocr_need(text_) and ocr_available():
                        try:
                            t_ = ocr_file(tmp, pw)
                            text_ = t_ if len(t_.strip()) > len(text_.strip()) else text_
                        except Exception:
                            traceback.print_exc()
                    txs = parse_bank_pdf(tmp, text_)
                    sal = saldo_from_text(text_)
                elif low_.endswith((".xlsx", ".xlsm", ".xls")):
                    data_ = bank_table_bytes(tmp, pw)
                    txs = parse_bank_csv(data_)
                    sal = saldo_from_csv(data_)
                else:
                    data_ = open(tmp, "rb").read()
                    txs = parse_bank_csv(data_)
                    sal = saldo_from_csv(data_)
            except PasswordNeeded as e_:
                return h._send(200, {"ok": False, "needs_password": True, "wrong": e_.wrong,
                                     "error": "Passwort falsch." if e_.wrong else "Der Kontoauszug ist passwortgeschützt."})
            except ValueError:
                raise
            except Exception as e_:
                traceback.print_exc()
                return h._send(200, {"ok": False, "error": f"Datei konnte nicht gelesen werden ({type(e_).__name__}). Bitte als CSV exportieren oder ein anderes PDF versuchen."})
            finally:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            saved = store_saldo(sal, name, txs)
            return h._send(200, {"ok": True, "tx": bank_suggest(txs), "saldo": saved})
        if p == "/api/upload/bom":
            rows = parse_bom(tmp)
            os.remove(tmp)
            return h._send(200, {"ok": True, "rows": rows, "preise": get_settings().get("materialpreise") or {}})
        if p == "/api/upload/zert":
            rel = store_upload(tmp, name, "Nachweise")
            return h._send(200, {"ok": True, "file": rel})
        if p == "/api/upload/steuer":
            aid = steuerakte_add(int(h.headers.get("X-Year") or datetime.date.today().year), tmp, name,
                                 unquote(h.headers.get("X-Art") or "") or "Sonstiges")
            return h._send(200, {"ok": True, "id": aid})
        if p == "/api/upload/paket":
            try:
                res = import_package(tmp)
            finally:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            return h._send(200, {"ok": True, "result": res})
        if p == "/api/upload/update":
            with open(tmp, "rb") as f_:
                magic = f_.read(4)
            if magic.startswith(b"PK"):
                try:
                    res = install_paupdate(tmp, allow_same=h.headers.get("X-Force") == "1")
                finally:
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
                res["restart"] = restart_app(1.5)
                return h._send(200, res)
            if not name.lower().endswith(".exe") and magic[:2] != b"MZ":
                raise ValueError("Bitte eine Update-Datei (.paupdate) oder eine Programm-EXE auswählen.")
            return h._send(200, install_update(tmp))
    except ValueError as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return h._send(200, {"ok": False, "error": str(e)})
    return h._send(404, {"error": "not found"})


TIMER_LOCK = threading.Lock()


def ext_post(h, p, d):
    if p in HOOK_POST:
        return HOOK_POST[p](h, d)
    ok = lambda extra=None: h._send(200, dict({"ok": True}, **(extra or {})))
    if p == "/api/assist/retrain":
        if d.get("reset"):
            x("DELETE FROM beleg_learn")
        n = retrain_from_files()
        return ok({"n": n, "status": assist_status()})
    if p == "/api/assist/kitest":
        s_ = dict(get_settings(), **{k: v for k, v in d.items() if k.startswith("ki_")})
        try:
            r = llm_classify("Rechnung Nr. 4711 vom 02.10.2026\nThomann GmbH\nMikrofonstativ 1 Stk 39,00 EUR\nRechnungsbetrag 39,00 EUR", s_)
            return ok({"model": r.get("_model"), "antwort": r})
        except Exception as e_:
            return h._send(200, {"ok": False, "error": f"Keine Verbindung: {e_}"})
    if p == "/api/export":
        return h._send(200, run_export(d))
    if p == "/api/bulk":
        return h._send(200, bulk_action(d))
    if p == "/api/update/activate":
        r_ = activate_version(str(d.get("version") or "builtin"))
        r_["restart"] = restart_app()
        return h._send(200, r_)
    if p == "/api/update/restart":
        return ok({"restart": restart_app()})
    if p == "/api/update/hinweis_ok":
        try:
            os.remove(os.path.join(APP_DIR, "hinweis.json"))
        except Exception:
            pass
        return ok()
    if p == "/api/abschluss/korrektur":
        return ok(korr_book(d))
    if p == "/api/abschluss/korrektur_undo":
        return ok(korr_undo(d))
    if p == "/api/steuerakte/save":
        return ok({"abschluss": abschluss_save(int(d["year"]), d.get("abschluss") or {})})
    if p == "/api/steuerakte/delete":
        x("DELETE FROM steuerakte WHERE id=?", (int(d["id"]),))
        return ok()
    if p == "/api/steuerakte/update":
        x("UPDATE steuerakte SET art=?, titel=?, datum=?, notiz=? WHERE id=?", (d.get("art"), d.get("titel"), d.get("datum"), d.get("notiz"), int(d["id"])))
        return ok()
    if p == "/api/paket/export":
        path = export_package(years=d.get("years") or None)
        try:
            open_path(os.path.dirname(path))
        except Exception:
            pass
        return ok({"path": path, "size": os.path.getsize(path)})
    if p == "/api/beleg/unlock":
        return h._send(200, unlock_beleg(d))
    if p == "/api/beleg/pwclear":
        set_setting("beleg_pw", [])
        return ok()
    if p == "/api/kontostand/save":
        store_saldo({"saldo": float(d["saldo"]), "datum": d.get("datum") or today()}, d.get("quelle") or "von Hand")
        return ok({"info": kontostand_info()})
    if p == "/api/kontostand/delete":
        x("DELETE FROM kontostand WHERE id=?", (int(d["id"]),))
        return ok({"info": kontostand_info()})
    if p == "/api/pending/discard":
        r_ = q("SELECT * FROM pending_belege WHERE id=?", (int(d["id"]),), one=True)
        if r_:
            fp = os.path.join(DATA_DIR, r_["file"])
            if os.path.exists(fp):
                os.remove(fp)
            x("DELETE FROM pending_belege WHERE id=?", (r_["id"],))
        return ok()
    if p == "/api/eingang/scan":
        return ok({"n": eingang_scan(force=True), "dir": eingang_dir()})
    if p == "/api/eingang/open":
        d_ = eingang_dir()
        os.makedirs(d_, exist_ok=True)
        open_path(d_)
        return ok({"dir": d_})
    if p == "/api/invoice/storno":
        sid, snr = storno_invoice(int(d["id"]))
        return ok({"id": sid, "nr": snr})
    if p == "/api/invoice/convert":
        nid, nnr = convert_doc(int(d["id"]), d["to"])
        return ok({"id": nid, "nr": nnr})
    if p == "/api/invoice/offer_status":
        x("UPDATE invoices SET status=? WHERE id=? AND typ IN ('angebot','auftrag')", (d["status"], d["id"]))
        return ok()
    if p == "/api/mahnung/create":
        return h._send(200, create_mahnung(int(d["id"]), d.get("stufe")))
    if p == "/api/mail/send":
        return h._send(200, mail_send(d))
    if p == "/api/mail/test":
        s = get_settings()
        send_mail(s["smtp_user"], "", "Test - Pfeiffer-Audio Rechnung", "Der E-Mail-Versand funktioniert.", [])
        return ok()
    if p == "/api/bank/apply":
        return h._send(200, bank_apply(d.get("items") or []))
    if p == "/api/recurring/save":
        cols = ["name", "invoice_id", "intervall", "naechstes", "aktiv"]
        if not d.get("id"):
            cols.append("created")
            d["created"] = now_iso()
        _crud("recurring", cols, d)
        made = run_schedules()
        return ok({"erzeugt": len(made)})
    if p == "/api/recurring/delete":
        x("DELETE FROM recurring WHERE id=?", (d["id"],))
        return ok()
    if p == "/api/recurring/run":
        return ok({"erzeugt": len(run_schedules())})
    if p == "/api/vertrag/save":
        _crud("vertraege", ["name", "customer_id", "project_id", "intervall", "naechste", "preis", "article_id", "beschreibung",
                            "auto_rechnung", "vorlauf", "aktiv", "notiz"], d, num=("preis",))
        return ok()
    if p == "/api/vertrag/delete":
        x("DELETE FROM vertraege WHERE id=?", (d["id"],))
        return ok()
    if p == "/api/vertrag/done":
        return h._send(200, vertrag_done(int(d["id"]), d.get("datum")))
    if p == "/api/student/save":
        if d.get("person_customer_id"):
            ex = q("SELECT id FROM students WHERE person_customer_id=? AND id!=?", (d["person_customer_id"], d.get("id") or 0), one=True)
            if ex:
                raise ValueError("Dieser Kunde ist bereits als Schüler angelegt.")
        sid = _crud("students", ["name", "customer_id", "article_id", "modus", "dauer", "rhythmus", "aktiv", "notiz", "sort", "person_customer_id"], d, num=("dauer",))
        if d.get("kurs_ids") is not None:
            want = {int(k) for k in d["kurs_ids"]}
            have = {r["kurs_id"] for r in q("SELECT kurs_id FROM kurs_members WHERE student_id=?", (sid,))}
            for k in want - have:
                x("INSERT OR IGNORE INTO kurs_members (kurs_id, student_id, seit) VALUES (?,?,?)", (k, sid, today()))
            for k in have - want:
                x("DELETE FROM kurs_members WHERE kurs_id=? AND student_id=?", (k, sid))
        return ok({"id": sid})
    if p == "/api/student/from_customers":
        ids = [student_for_customer(int(c), d.get("article_id"), d.get("payer")) for c in d.get("customer_ids") or []]
        return ok({"ids": ids})
    if p == "/api/kurs/save":
        kid = _crud("kurse", ["name", "article_id", "customer_id", "modus", "dauer", "rhythmus", "aktiv", "notiz", "start", "ende", "farbe", "sort"], d, num=("dauer",))
        return ok({"id": kid})
    if p == "/api/kurs/delete":
        if q("SELECT id FROM lessons WHERE kurs_id=? AND invoice_id IS NOT NULL", (d["id"],), one=True):
            x("UPDATE kurse SET aktiv=0 WHERE id=?", (d["id"],))
            return ok({"info": "Kurs hat abgerechnete Stunden - wurde deaktiviert statt gelöscht."})
        x("DELETE FROM lessons WHERE kurs_id=? AND invoice_id IS NULL", (d["id"],))
        x("DELETE FROM kurs_members WHERE kurs_id=?", (d["id"],))
        x("DELETE FROM kurse WHERE id=?", (d["id"],))
        return ok()
    if p == "/api/kurs/add":
        kid = int(d["kurs_id"])
        k = q("SELECT * FROM kurse WHERE id=?", (kid,), one=True)
        sids = [int(v) for v in d.get("student_ids") or []]
        for cid in d.get("customer_ids") or []:
            sids.append(student_for_customer(int(cid), None, None if k["customer_id"] else int(cid)))
        for sid in sids:
            x("INSERT OR IGNORE INTO kurs_members (kurs_id, student_id, seit) VALUES (?,?,?)", (kid, sid, today()))
        return ok({"n": len(sids)})
    if p == "/api/kurs/remove":
        x("DELETE FROM kurs_members WHERE kurs_id=? AND student_id=?", (d["kurs_id"], d["student_id"]))
        return ok()
    if p == "/api/kurs/toggle_day":
        return ok(kurs_toggle_day(int(d["kurs_id"]), d["datum"]))
    if p == "/api/unterricht/bill_all":
        made = lessons_bill_all(int(d["year"]), int(d["month"]))
        return ok({"ids": made})
    if p == "/api/student/delete":
        if q("SELECT id FROM lessons WHERE student_id=? AND invoice_id IS NOT NULL", (d["id"],), one=True):
            x("UPDATE students SET aktiv=0 WHERE id=?", (d["id"],))
            return ok({"info": "Hat abgerechnete Stunden - wurde deaktiviert statt gelöscht."})
        x("DELETE FROM lessons WHERE student_id=?", (d["id"],))
        x("DELETE FROM students WHERE id=?", (d["id"],))
        return ok()
    if p == "/api/lesson/toggle":
        kid = d.get("kurs_id") or None
        ex = q("SELECT * FROM lessons WHERE student_id=? AND datum=? AND COALESCE(kurs_id,0)=?", (d["student_id"], d["datum"], kid or 0), one=True)
        if ex:
            if ex["invoice_id"]:
                raise ValueError("Diese Stunde ist bereits abgerechnet.")
            x("DELETE FROM lessons WHERE id=?", (ex["id"],))
            return ok({"state": None})
        x("INSERT INTO lessons (student_id, datum, dauer, status, notiz, kurs_id) VALUES (?,?,?,?,?,?)",
          (d["student_id"], d["datum"], float(d["dauer"]) if d.get("dauer") else None, d.get("status") or "stattgefunden", d.get("notiz", ""), kid))
        return ok({"state": "stattgefunden"})
    if p == "/api/lesson/save":
        _crud("lessons", ["student_id", "datum", "dauer", "status", "notiz"], d, num=("dauer",))
        return ok()
    if p == "/api/unterricht/to_invoice":
        return h._send(200, lessons_to_invoice(int(d["customer_id"]), d["year"], d["month"], d.get("attach", True)))
    if p == "/api/asset/save":
        _crud("assets", ["bezeichnung", "kategorie", "kaufdatum", "betrag", "nd_jahre", "methode", "beleg_id", "seriennr",
                         "standort", "notiz", "abgang", "project_id"], d, num=("betrag", "nd_jahre"))
        return ok()
    if p == "/api/asset/delete":
        x("DELETE FROM assets WHERE id=?", (d["id"],))
        return ok()
    if p == "/api/fahrt/save":
        _crud("fahrten", ["datum", "ziel", "zweck", "km", "art", "project_id", "customer_id", "notiz"], d, num=("km",))
        return ok()
    if p == "/api/fahrt/delete":
        x("DELETE FROM fahrten WHERE id=?", (d["id"],))
        return ok()
    if p == "/api/zert/save":
        _crud("zertifikate", ["typ", "bezeichnung", "person", "nummer", "norm", "ausgestellt", "gueltig_bis", "bestaetigt_am",
                              "bestaetigung_monate", "file", "notiz", "aktiv"], d)
        return ok()
    if p == "/api/zert/delete":
        x("DELETE FROM zertifikate WHERE id=?", (d["id"],))
        return ok()
    if p == "/api/project/bom_apply":
        n = 0
        for r in d.get("rows") or []:
            if not r.get("use", True):
                continue
            x("INSERT INTO project_entries (project_id, datum, art, nr, name, descr, qty, unit, price, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (d["project_id"], today(), "Material", r.get("nr", "")[:40], r.get("name", "")[:120],
               " · ".join(v for v in (r.get("material", ""), (num_de(r["masse_kg"], 2) + " kg") if r.get("masse_kg") else "") if v),
               float(r.get("qty") or 1), r.get("unit") or "Stk", float(r.get("vk") or 0), now_iso()))
            n += 1
        if d.get("preise"):
            set_setting("materialpreise", d["preise"])
        return ok({"n": n})
    if p == "/api/project/handover":
        if not d.get("file_ids"):
            raise ValueError("Bitte mindestens eine Datei auswählen.")
        fp = handover_pdf(int(d["id"]), d["file_ids"], d.get("notes", ""))
        open_path(fp)
        return ok({"path": fp})
    if p == "/api/timer/start":
        with TIMER_LOCK:   # v2.1.1: never overwrite a running timer (its time would be lost)
            if get_settings().get("timer"):
                return h._send(200, {"ok": False, "error": "Es läuft bereits eine Stoppuhr - zuerst stoppen oder verwerfen."})
            set_setting("timer", {"project_id": int(d["project_id"]), "start": datetime.datetime.now().isoformat(timespec="seconds")})
        return ok()
    if p == "/api/timer/stop":
        return h._send(200, timer_stop(d))
    if p == "/api/timer/cancel":
        set_setting("timer", None)
        return ok()
    return None
